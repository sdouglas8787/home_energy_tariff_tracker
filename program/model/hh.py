"""Half-hourly smart-meter data: import, persist, and profile.

Takes half-hours from either route -- Bright / Glowmarkt CSV exports (columns:
epochTimestamp, kWh, dateTime) or the API fetch in bright.py -- and appends them
into a local store de-duplicated by (fuel, timestamp) so history builds up
beyond Bright's rolling 13-month window, and turns them into a
time-of-day / day-of-week load profile plus a time-of-use tariff simulator.

Timestamps are UTC in the export; everything here converts to Europe/London so
"after dinner" and "Saturday morning" mean local clock time.
"""
from __future__ import annotations
import csv
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")


def _reject_outliers(store, k=6.0, floor=3.0, win=7 * 48):
    """Dynamic outlier filter: a reading is dropped only if it dwarfs its own
    neighbourhood (more than k x the max of the surrounding ~7 days), never a
    fixed ceiling, so a genuinely heavy day is kept. Returns (clean, rejected)."""
    clean, rejected = [], []
    for fuel in ("Electricity", "Gas"):
        recs = sorted((r for r in store if r[0] == fuel), key=lambda x: x[1])
        vals = [r[2] for r in recs]
        n = len(recs)
        for i, (f, e, v) in enumerate(recs):
            neigh = vals[max(0, i - win):i] + vals[i + 1:i + 1 + win]
            ref = max(neigh) if neigh else v
            if v > max(floor, k * ref):
                rejected.append((f, e, v, ref))
            else:
                clean.append((f, e, v))
    return clean, rejected


def _fuel_from_name(name):
    n = name.lower()
    if "elec" in n:
        return "Electricity"
    if "gas" in n:
        return "Gas"
    return None


def import_files(folder, store_path, archive_dir=None, extra=None):
    """Import every CSV in `folder`, merge into `store_path` (de-duplicated), then
    move the processed files into `archive_dir` so the inbox is left empty.

    `extra` is an optional list of (fuel, epoch, kwh) triples from another source --
    the Bright API fetch -- merged on the same de-duplication key, so whichever route
    the data arrives by, a half-hour is only ever stored once.

    An empty inbox after a run is your confirmation the files were read. Nothing is
    deleted; originals are filed in the archive. Returns (records, files_imported).
    """
    import shutil
    folder = Path(folder)
    store = load_store(store_path)
    seen = {(r[0], r[1]) for r in store}
    added = 0
    files = 0
    for fuel, epoch, kwh in extra or []:
        key = (fuel, epoch)
        if key in seen or kwh < 0:
            continue
        seen.add(key)
        store.append((fuel, epoch, kwh))
        added += 1
    for f in sorted(folder.glob("*.csv")) if folder.exists() else []:
        fuel = _fuel_from_name(f.name)
        if not fuel:
            continue
        with open(f, newline="") as fh:
            for row in csv.DictReader(fh):
                epoch = int(row["epochTimestamp"])
                key = (fuel, epoch)
                if key in seen:
                    continue
                kwh = float(row["kWh"])
                if kwh < 0:                          # negative = not a consumption reading
                    continue
                seen.add(key)
                store.append((fuel, epoch, kwh))
                added += 1
        files += 1
        if archive_dir:                                     # file the processed export away
            Path(archive_dir).mkdir(parents=True, exist_ok=True)
            dest = Path(archive_dir) / f.name
            if dest.exists():
                dest = dest.with_name(f"{f.stem}__{int(f.stat().st_mtime)}{f.suffix}")
            shutil.move(str(f), str(dest))
    rejected = []
    if added:
        store, rejected = _reject_outliers(store)     # dynamic, neighbourhood-based
        store.sort(key=lambda r: (r[0], r[1]))
        _save_store(store_path, store)
    return store, files, rejected


def load_store(path):
    try:
        with open(path, newline="") as fh:
            return [(r["fuel"], int(r["epoch"]), float(r["kwh"])) for r in csv.DictReader(fh)]
    except Exception:
        return []


_load_store = load_store          # kept for anything still using the old name


def _save_store(path, store):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["fuel", "epoch", "kwh"])
        w.writerows(store)


def _local(epoch):
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(LONDON)


def build_profile(store):
    """Per fuel: average kWh per (weekday, hour) and per hour, baseload, peak, totals.

    weekday: 0=Mon..6=Sun. Values are average kWh consumed in that clock hour.
    """
    out = {}
    for fuel in ("Electricity", "Gas"):
        recs = [r for r in store if r[0] == fuel]
        if len(recs) < 48:
            out[fuel] = None
            continue
        # sum the half-hours into each (date, weekday, hour) bucket = that day's hourly kWh
        hourly = {}
        for _, epoch, kwh in recs:
            dt = _local(epoch)
            k = (dt.date(), dt.weekday(), dt.hour)
            hourly[k] = hourly.get(k, 0.0) + kwh
        # average across days for each (weekday, hour) and each hour
        by_wh_sum, by_wh_n = {}, {}
        by_h_sum, by_h_n = {}, {}
        for (d, wd, h), v in hourly.items():
            by_wh_sum[(wd, h)] = by_wh_sum.get((wd, h), 0.0) + v
            by_wh_n[(wd, h)] = by_wh_n.get((wd, h), 0) + 1
            by_h_sum[h] = by_h_sum.get(h, 0.0) + v
            by_h_n[h] = by_h_n.get(h, 0) + 1
        wh = {k: by_wh_sum[k] / by_wh_n[k] for k in by_wh_sum}
        by_hour = {h: by_h_sum[h] / by_h_n[h] for h in by_h_sum}
        days = len({d for (d, _, _) in hourly})
        total = sum(kwh for _, _, kwh in recs)
        annual = total / days * 365 if days else 0
        baseload_h = min(by_hour, key=by_hour.get)
        peak_wh = max(wh, key=wh.get)
        out[fuel] = {
            "wh": wh, "by_hour": by_hour, "days": days, "annual": annual,
            "baseload_kwh_per_h": by_hour[baseload_h], "baseload_hour": baseload_h,
            "peak_wd": peak_wh[0], "peak_hour": peak_wh[1], "peak_kwh": wh[peak_wh],
            "start": _local(recs[0][1]).date(), "end": _local(recs[-1][1]).date(),
        }
    return out


def day_matrix(store, fuel="Electricity", ndays=21):
    """For inspecting a single day against its 'typical'. Returns:
      recent  = the last `ndays` dates (with data)
      days    = {date: [48 half-hour kWh values]}
      typ     = {weekday: [48 half-hour average kWh]} across near-complete days
    slot index = hour*2 + (0 if <30 min else 1), so 0 = 00:00-00:30 ... 47 = 23:30-24:00.
    """
    from collections import defaultdict
    days = {}
    for f, e, k in store:
        if f != fuel:
            continue
        dt = _local(e)
        slot = dt.hour * 2 + (1 if dt.minute >= 30 else 0)
        days.setdefault(dt.date(), [None] * 48)[slot] = k
    wsum = defaultdict(lambda: [0.0] * 48)
    wn = defaultdict(lambda: [0] * 48)
    for d, arr in days.items():
        if sum(v is not None for v in arr) >= 40:      # near-complete days feed the typical
            for s in range(48):
                if arr[s] is not None:
                    wsum[d.weekday()][s] += arr[s]
                    wn[d.weekday()][s] += 1
    typ = {wd: [(wsum[wd][s] / wn[wd][s]) if wn[wd][s] else 0.0 for s in range(48)] for wd in wsum}
    recent = sorted(days)[-ndays:]
    return recent, days, typ


def baseload_by_month(store, fuel="Electricity"):
    """Typical overnight draw (01:00-05:00 local mean, kWh/h) per calendar month.

    A rising line means something new is running around the clock; a drop after you
    switch something off shows up here on the next import.
    """
    from datetime import date
    buckets = {}
    for f, epoch, kwh in store:
        if f != fuel:
            continue
        dt = _local(epoch)
        if 1 <= dt.hour < 5:
            buckets.setdefault((dt.year, dt.month), []).append(kwh)
    out = []
    for (y, m), vals in sorted(buckets.items()):
        out.append((date(y, m, 1), sum(vals) / len(vals) * 2))   # half-hours -> per hour
    return out


def best_slots(profile_fuel, n, discount, unit_p):
    """Pick the n most valuable one-hour slots in a week to apply a % discount to.

    Uses the (weekday, hour) load profile. Returns the chosen slots and the annual
    saving if those n hours each week are discounted at your current rate.
    """
    wh = profile_fuel["wh"]
    ranked = sorted(wh.items(), key=lambda kv: -kv[1])[:n]
    weekly_kwh = sum(v for _, v in ranked)
    annual_saving = weekly_kwh * discount * unit_p / 100 * 52
    dows = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    slots = [(dows[wd], h, v) for (wd, h), v in ranked]
    return {"slots": slots, "weekly_kwh": weekly_kwh, "annual_saving": annual_saving,
            "per_kwh_saved": discount * unit_p / 100}


def simulate_discount(store, fuel, windows, discount, unit_p):
    """Annual £ saving from a % discount applied in given local-time windows.

    windows: list of (weekdays, start_hour, end_hour). weekdays is a set of 0..6
    (or None for every day); the window is [start_hour, end_hour).
    """
    recs = [r for r in store if r[0] == fuel]
    if not recs:
        return None
    days = len({_local(e).date() for _, e, _ in recs}) or 1
    in_window = 0.0
    for _, epoch, kwh in recs:
        dt = _local(epoch)
        for wds, s, e in windows:
            if (wds is None or dt.weekday() in wds) and s <= dt.hour < e:
                in_window += kwh
                break
    annual_kwh = in_window / days * 365
    saving = annual_kwh * discount * unit_p / 100
    return {"annual_kwh_in_window": annual_kwh, "annual_saving": saving}


DOW = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def pivot_tables(store, min_slots=46):
    """Tidy tables of the half-hourly data, shaped for PivotTables.

    One record per row, no merged cells, no title banners -- select the sheet, insert
    a PivotTable, and the columns are already the dimensions you would want: fuel,
    date, month, weekday, hour, and whether the day was completely reported.

    Returns [(sheet name, headers, rows, {column: number format})], which is what
    export_output writes out verbatim.
    """
    from collections import defaultdict
    from datetime import date as _date

    KWH3 = '#,##0.000'
    half_hourly, daily_counts, daily_sums = [], defaultdict(int), defaultdict(float)

    for fuel, epoch, kwh in sorted(store, key=lambda r: (r[0], r[1])):
        dt = _local(epoch)
        slot = dt.hour * 2 + (1 if dt.minute >= 30 else 0)
        half_hourly.append([dt.date(), dt.strftime("%H:%M"), fuel, kwh, DOW[dt.weekday()],
                            dt.hour, slot, _date(dt.year, dt.month, 1),
                            "Yes" if dt.weekday() >= 5 else "No"])
        daily_counts[(fuel, dt.date())] += 1
        daily_sums[(fuel, dt.date())] += kwh

    daily = []
    for (fuel, d), total in sorted(daily_sums.items()):
        n = daily_counts[(fuel, d)]
        daily.append([d, fuel, total, n, "Yes" if n >= min_slots else "No",
                      DOW[d.weekday()], _date(d.year, d.month, 1),
                      "Yes" if d.weekday() >= 5 else "No"])

    # average shape of a day, by fuel and weekday -- the load profile as a flat table
    sums, counts = defaultdict(float), defaultdict(int)
    for d, t, fuel, kwh, wd, hour, slot, month, we in half_hourly:
        if daily_counts[(fuel, d)] >= min_slots:          # whole days only, or the mean sags
            sums[(fuel, wd, slot)] += kwh
            counts[(fuel, wd, slot)] += 1
    profile = []
    for (fuel, wd, slot), total in sorted(sums.items(), key=lambda kv: (kv[0][0], DOW.index(kv[0][1]), kv[0][2])):
        profile.append([fuel, wd, f"{slot // 2:02d}:{'30' if slot % 2 else '00'}", slot,
                        total / counts[(fuel, wd, slot)], counts[(fuel, wd, slot)]])

    return [
        ("Daily Usage",
         ["Date", "Fuel", "kWh", "Half_Hours_Reported", "Complete_Day", "Weekday", "Month", "Weekend"],
         daily, {"kWh": KWH3, "Date": "yyyy-mm-dd", "Month": "mmm yyyy"}),
        ("Load Profile",
         ["Fuel", "Weekday", "Time", "Slot", "Average_kWh", "Days_Averaged"],
         profile, {"Average_kWh": KWH3}),
        ("Half Hourly",
         ["Date", "Time", "Fuel", "kWh", "Weekday", "Hour", "Slot", "Month", "Weekend"],
         half_hourly, {"kWh": KWH3, "Date": "yyyy-mm-dd", "Month": "mmm yyyy"}),
    ]
