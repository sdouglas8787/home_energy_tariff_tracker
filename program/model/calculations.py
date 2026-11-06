from __future__ import annotations
from collections import defaultdict
from datetime import date, timedelta
from calendar import monthrange
from model.models import Reading, Tariff


def distribute_interval(start_date, end_date, total_usage):
    """Spread usage between two readings evenly across the days in between."""
    days = (end_date - start_date).days
    if days <= 0:
        return []
    daily = total_usage / days
    return [(start_date + timedelta(days=i + 1), daily) for i in range(days)]


def calculate_daily_usage(readings, gas_kwh_per_unit):
    """Turn cumulative meter readings into per-day kWh, plus a validation log.

    Gas readings are volumes and are converted to kWh here; electricity is
    already in kWh. Returns (daily_rows, validation_rows).
    """
    grouped = defaultdict(list)
    for r in readings:
        grouped[r.fuel.lower()].append(r)
    output = []
    validation = []
    for fuel, rows in grouped.items():
        rows.sort(key=lambda x: x.date)
        for previous, current in zip(rows, rows[1:]):
            delta = current.reading - previous.reading
            days = (current.date - previous.date).days
            status = "OK"
            if days <= 0:
                status = "Duplicate/out-of-order date"
            elif delta < 0:
                status = "Negative usage / possible meter reset"
            elif current.read_type.lower() == "estimated" or previous.read_type.lower() == "estimated":
                status = "Includes estimated reading"
            validation.append([fuel.title(), previous.date, current.date, days, delta, status])
            if days <= 0 or delta < 0:
                continue
            usage = delta
            if fuel == "gas":
                factor = gas_kwh_per_unit
                if current.meter_unit.lower() == "ft3":
                    factor *= 2.83   # 1 ft3 = 0.0283 m3, applied before the kWh factor
                usage *= factor
            for d, value in distribute_interval(previous.date, current.date, usage):
                output.append([d, fuel.title(), value])
    return output, validation


def aggregate_monthly(daily_rows):
    agg = defaultdict(lambda: {"Electricity": 0.0, "Gas": 0.0, "days": set()})
    for d, fuel, usage in daily_rows:
        key = (d.year, d.month)
        agg[key][fuel] += usage
        agg[key]["days"].add(d)
    rows = []
    for (year, month), vals in sorted(agg.items()):
        rows.append([date(year, month, 1), vals["Electricity"], vals["Gas"], len(vals["days"])])
    return rows


def annualised_usage(monthly_rows, analysis_end, fallback_e, fallback_g, adj_e, adj_g):
    """Estimate a full year of usage from the trailing 12 months of readings.

    Falls back to the manual annual figures when too few days are covered.
    """
    start = analysis_end - timedelta(days=365)
    e = g = 0.0
    covered = 0
    for month, ekwh, gkwh, days in monthly_rows:
        month_end = date(month.year, month.month, monthrange(month.year, month.month)[1])
        if month_end >= start and month <= analysis_end:
            e += ekwh
            g += gkwh
            covered += days
    if covered < 240:
        e, g = fallback_e, fallback_g
        method = "Fallback annual usage (not enough readings yet)"
    else:
        scale = 365 / covered
        e *= scale
        g *= scale
        method = f"Annualised from {covered} covered days"
    return e * (1 + adj_e), g * (1 + adj_g), method


MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def build_insights(daily_rows, monthly_rows):
    """Derive seasonality, best/worst months & days, and year-on-year trend.

    daily_rows:   [date, fuel, kWh]  (kWh spread evenly across each read interval)
    monthly_rows: [month_date, elec_kWh, gas_kWh, covered_days]
    Returns {fuel: {seasonality, best_month, worst_month, best_day, worst_day, yoy}}.
    """
    out = {}
    for fuel_key, idx in (("Electricity", 1), ("Gas", 2)):
        # seasonality: average kWh/day for each calendar month (1..12)
        by_cal_month = defaultdict(list)
        for d, fuel, kwh in daily_rows:
            if fuel == fuel_key:
                by_cal_month[d.month].append(kwh)
        seasonality = {m: sum(v) / len(v) for m, v in by_cal_month.items()}

        # best/worst calendar month by avg kWh/day (ignore very partial months)
        months = [(m, row[idx], days, row[idx] / days)
                  for row in monthly_rows for m, days in [(row[0], row[3])] if days >= 20]
        best_month = min(months, key=lambda x: x[3]) if months else None   # lowest = "best"
        worst_month = max(months, key=lambda x: x[3]) if months else None

        # best/worst day (lowest/highest daily kWh)
        days_list = [(d, kwh) for d, fuel, kwh in daily_rows if fuel == fuel_key]
        best_day = min(days_list, key=lambda x: x[1]) if days_list else None
        worst_day = max(days_list, key=lambda x: x[1]) if days_list else None

        # year-on-year: same calendar month across adjacent years, avg kWh/day
        per_ym = {(m.year, m.month): row[idx] / days
                  for row in monthly_rows for m, days in [(row[0], row[3])] if days >= 20}
        pairs = [(mo, (avg - prev) / prev)
                 for (yr, mo), avg in per_ym.items()
                 for prev in [per_ym.get((yr - 1, mo))] if prev and prev > 0]
        yoy = None
        if pairs:
            pct = sum(p for _, p in pairs) / len(pairs)
            direction = "up" if pct > 0.02 else "down" if pct < -0.02 else "flat"
            yoy = {"pct": pct, "direction": direction, "n_pairs": len(pairs)}

        out[fuel_key] = {"seasonality": seasonality, "best_month": best_month,
                         "worst_month": worst_month, "best_day": best_day,
                         "worst_day": worst_day, "yoy": yoy}
    return out


DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def _weighted_avgday(monthly_rows, idx, half_life=12.0):
    """Average kWh/day for each calendar month, weighting recent years more.

    Weight halves every `half_life` months, so the latest year dominates — this
    is the recency-weighted (weighted-R12) view that tracks a falling/rising
    trend faster than a plain 12-month average.
    """
    full = [r for r in monthly_rows if r[3] >= 20]
    if not full:
        return {}
    ref = max(r[0] for r in full)
    by_month = defaultdict(list)
    for r in full:
        age = (ref.year - r[0].year) * 12 + (ref.month - r[0].month)
        by_month[r[0].month].append((r[idx] / r[3], 0.5 ** (age / half_life)))
    out = {}
    for m, vals in by_month.items():
        den = sum(w for _, w in vals)
        out[m] = sum(v * w for v, w in vals) / den if den else 0.0
    return out


def weighted_annual_usage(monthly_rows, adj_e, adj_g, fallback_e, fallback_g, half_life=12.0):
    """Annual forecast from the recency-weighted seasonal profile (12 months)."""
    covered = sum(r[3] for r in monthly_rows if r[3] >= 20)
    e_prof = _weighted_avgday(monthly_rows, 1, half_life)
    g_prof = _weighted_avgday(monthly_rows, 2, half_life)
    if covered < 240 or len(e_prof) < 12 or len(g_prof) < 12:
        return fallback_e * (1 + adj_e), fallback_g * (1 + adj_g), "Fallback annual usage (not enough readings yet)"
    e = sum(e_prof[m] * DAYS_IN_MONTH[m - 1] for m in range(1, 13))
    g = sum(g_prof[m] * DAYS_IN_MONTH[m - 1] for m in range(1, 13))
    return e * (1 + adj_e), g * (1 + adj_g), f"Recency-weighted seasonal ({int(half_life)}-month half-life)"


def build_backtest(monthly_rows):
    """Out-of-sample walk-forward test of the model's core assumption.

    The model assumes next year resembles last year (trailing-12-month basis).
    So we test it honestly with a seasonal-naive walk-forward: for each month
    that has the same calendar month one year earlier, "forecast" it using only
    that prior year's value, then compare to what actually happened. Usage is
    normalised to average kWh/day to remove month-length / partial-month noise.

    Returns {fuel: {points:[{month, forecast, actual, error_pct}], mape, bias, n}}.
    """
    out = {}
    for fuel_key, idx in (("Electricity", 1), ("Gas", 2)):
        avgday = {(row[0].year, row[0].month): row[idx] / row[3]
                  for row in monthly_rows if row[3] >= 20}
        points = []
        for (yr, mo), actual in sorted(avgday.items()):
            forecast = avgday.get((yr - 1, mo))
            if forecast and forecast > 0:
                points.append({"month": date(yr, mo, 1), "forecast": forecast,
                               "actual": actual, "error_pct": (actual - forecast) / forecast})
        if points:
            mape = sum(abs(p["error_pct"]) for p in points) / len(points)
            bias = sum(p["error_pct"] for p in points) / len(points)
            out[fuel_key] = {"points": points, "mape": mape, "bias": bias, "n": len(points)}
        else:
            out[fuel_key] = {"points": [], "mape": None, "bias": None, "n": 0}
    return out


def _add_months(d, k):
    m = d.month - 1 + k
    return date(d.year + m // 12, m % 12 + 1, 1)


def build_forward(monthly_rows, backtest, months_ahead=12):
    """Project the next N months (avg kWh/day) with a 95% band.

    Forecast = seasonal-naive (most recent value for that calendar month).
    Band width comes from the walk-forward error spread, so the cone reflects
    how wrong the model has actually been.
    """
    from statistics import pstdev
    out = {}
    full = [r for r in monthly_rows if r[3] >= 20]
    if not full:
        return {"Electricity": [], "Gas": []}
    last_d = max(r[0] for r in full)
    for fuel_key, idx in (("Electricity", 1), ("Gas", 2)):
        prof = _weighted_avgday(monthly_rows, idx)      # recency-weighted seasonal profile
        if not prof:
            out[fuel_key] = []
            continue
        errs = [p["error_pct"] for p in backtest.get(fuel_key, {}).get("points", [])]
        sigma = pstdev(errs) if len(errs) >= 2 else (backtest.get(fuel_key, {}).get("mape") or 0.15)
        # bias-correct: the walk-forward shows how far the model has systematically missed,
        # so nudge the forecast by that mean error (capped), then the band is the remaining spread.
        bias = max(-0.3, min(0.3, backtest.get(fuel_key, {}).get("bias") or 0.0))
        corr = 1 + bias
        pts = []
        for k in range(1, months_ahead + 1):
            nm = _add_months(last_d, k)
            fc = prof.get(nm.month)
            if fc is None:
                continue
            fcc = fc * corr
            pts.append({"month": nm, "forecast": fcc,
                        "lo": max(0.0, fcc * (1 - 1.96 * sigma)), "hi": fcc * (1 + 1.96 * sigma)})
        out[fuel_key] = pts
    return out


def build_walkforward(monthly_rows, min_history=6):
    """Out-of-sample test of the ACTUAL model (recency-weighted seasonal).

    For each month, rebuild the model using only earlier months, predict that
    month, then compare to the actual. Tests the real forecaster (not just the
    naive baseline) and extends automatically as more history accrues.
    """
    rows = sorted(monthly_rows, key=lambda r: r[0])
    out = {}
    for fuel_key, idx in (("Electricity", 1), ("Gas", 2)):
        points = []
        for i, target in enumerate(rows):
            if target[3] < 25:                       # skip partial target months
                continue
            prior = rows[:i]                          # only data strictly before this month
            if len({r[0].month for r in prior if r[3] >= 20}) < min_history:
                continue
            prof = _weighted_avgday(prior, idx)
            pm = prof.get(target[0].month)
            if not pm:                                # calendar month never seen before
                continue
            forecast = pm * target[3]
            actual = target[idx]
            if forecast:
                points.append({"month": target[0], "forecast": forecast, "actual": actual,
                               "error_pct": (actual - forecast) / forecast})
        if points:
            mape = sum(abs(p["error_pct"]) for p in points) / len(points)
            bias = sum(p["error_pct"] for p in points) / len(points)
            out[fuel_key] = {"points": points, "mape": mape, "bias": bias, "n": len(points)}
        else:
            out[fuel_key] = {"points": [], "mape": None, "bias": None, "n": 0}
    return out


def effective_rates(comparisons, e_kwh, g_kwh):
    """The blended rates each option works out at over the forward year.

    compare_tariffs has already costed the segments -- your fix until it ends, then
    the new deal, then a renewal rise on anything that lapses. Dividing that cost
    back out by usage gives one set of rates per option that carries all of it, so
    anything else pricing a year (the simulation below) stays consistent with the
    ranking instead of quietly reverting to today's rate card.
    """
    out = {}
    for c in comparisons or []:
        out[(c["Supplier"], c["Tariff_Name"])] = (
            c["Electricity_Cost_GBP"] * 100 / e_kwh if e_kwh else c["Elec_Unit_p"],
            c["Gas_Cost_GBP"] * 100 / g_kwh if g_kwh else c["Gas_Unit_p"],
            c["Standing_Cost_GBP"] * 100 / 365,
        )
    return out


def build_montecarlo(usage, errors, tariffs, include_exit, include_incentive,
                     n=3000, price_vol=0.12, seed=42, comparisons=None):
    """Simulate annual cost under uncertain usage (and tracker prices).

    Usage varies per the model's own out-of-sample errors; tracker/variable unit
    rates drift with a shared market shock each simulation, fixed tariffs don't.
    Returns per-tariff p5/p50/p95 and the chance a tracker beats the current fix.

    Rates come from `comparisons` when given, so an expiring tariff is simulated as
    what it becomes rather than what it costs today -- otherwise this would rank an
    ending fix cheapest and disagree with the ranking on the same page.
    """
    import random
    rnd = random.Random(seed)
    e0, g0 = usage
    e_e = [p["error_pct"] for p in errors.get("Electricity", {}).get("points", [])] or [0.0]
    g_e = [p["error_pct"] for p in errors.get("Gas", {}).get("points", [])] or [0.0]
    # de-mean so the simulation is centred on the point forecast (spread, not a shifted median)
    e_m, g_m = sum(e_e) / len(e_e), sum(g_e) / len(g_e)
    e_r = [x - e_m for x in e_e]
    g_r = [x - g_m for x in g_e]
    rates = effective_rates(comparisons, e0, g0)
    cur_i = next((i for i, t in enumerate(tariffs) if t.is_current), None)
    trk_i = [i for i, t in enumerate(tariffs) if t.tariff_type.lower() in ("tracker", "variable")]
    per = [[] for _ in tariffs]
    tracker_beats = 0
    for _ in range(n):
        em = 1 + sum(rnd.choice(e_r) for _ in range(12)) / 12    # annual usage multiplier (centred at 1)
        gm = 1 + sum(rnd.choice(g_r) for _ in range(12)) / 12
        drift = rnd.gauss(0, price_vol)                          # shared market move for trackers
        sim = []
        for t in tariffs:
            pd = drift if t.tariff_type.lower() in ("tracker", "variable") else 0.0
            e_p, g_p, sc_p = rates.get((t.supplier, t.tariff_name),
                                       (t.elec_unit_p, t.gas_unit_p, t.elec_sc_p + t.gas_sc_p))
            c = (e0 * em * e_p * (1 + pd) / 100 + g0 * gm * g_p * (1 + pd) / 100
                 + 365 * sc_p / 100
                 + (t.exit_fee if include_exit else 0) - (t.incentive if include_incentive else 0))
            sim.append(c)
        for i, c in enumerate(sim):
            per[i].append(c)
        if cur_i is not None and trk_i and min(sim[i] for i in trk_i) < sim[cur_i]:
            tracker_beats += 1

    def pct(a, q):
        a = sorted(a)
        k = (len(a) - 1) * q
        f = int(k)
        return a[f] + (a[min(f + 1, len(a) - 1)] - a[f]) * (k - f)

    stats = [{"supplier": t.supplier, "name": t.tariff_name, "type": t.tariff_type,
              "is_current": t.is_current, "p5": pct(per[i], .05), "p50": pct(per[i], .5),
              "p95": pct(per[i], .95)} for i, t in enumerate(tariffs)]
    stats.sort(key=lambda s: s["p50"])
    return {"n": n, "tariffs": stats, "price_vol": price_vol,
            "prob_tracker_beats_current": (tracker_beats / n) if (cur_i is not None and trk_i) else None}


# Electricity VAT drops from 5% to 0% for the winter -- 1 Oct 2026 to 31 Mar 2027 -- and
# then goes back to 5%. It is a holiday, not a cut, and treating it as permanent would
# overstate the saving across the rest of the year. Rates are quoted including VAT, so
# for those months the electricity side of the bill -- unit rate AND standing charge --
# falls by 1/1.05. It applies to every tariff alike, so it moves what you pay rather
# than which deal wins.
# Suppliers cannot charge an exit fee in the closing days of a fixed term (Ofgem sets
# this at 49; suppliers commonly apply 50). So a deal that starts inside this window is
# an early switch on paper but a free one in practice -- which is often the whole
# difference between a deal being worth taking and not.
EXIT_FEE_FREE_DAYS = 50

VAT_CHANGE_DATE = date(2026, 10, 1)
VAT_REVERT_DATE = date(2027, 4, 1)      # None would make the holiday permanent
VAT_IN_RATES = 0.05
VAT_AFTER = 0.0


def _vat_multipliers(start, days, change_date, vat_in_rates, vat_after, revert_date=None):
    """Per-day multiplier on the electricity side of a bill; 1.0 outside the holiday."""
    if change_date is None or vat_after is None:
        return [1.0] * days
    factor = (1 + vat_after) / (1 + (vat_in_rates or 0.0))
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        inside = d >= change_date and (revert_date is None or d < revert_date)
        out.append(factor if inside else 1.0)
    return out


def _daily_usage(forward, e_kwh, g_kwh, start, days):
    """Split the forecast year into per-day kWh, shaped by season.

    A switch that lands in October is not the same as one that lands in June: the
    months you spend on each tariff decide what it costs you. The forward forecast
    already knows the shape of your year, so we use it as a weighting and scale it
    to the annual totals, which keeps the comparison consistent with the headline
    figure. With no forecast to hand, the year is flat -- as it was before.
    """
    months = {}
    for fuel, key in (("Electricity", "e"), ("Gas", "g")):
        for point in (forward or {}).get(fuel, []):
            m = point["month"]
            months.setdefault((m.year, m.month), {})[key] = point["forecast"]
    e_w, g_w = [], []
    for i in range(days):
        d = start + timedelta(days=i)
        got = months.get((d.year, d.month), {})
        e_w.append(got.get("e", 1.0))
        g_w.append(got.get("g", 1.0))
    # scale to the window: e_kwh is a YEAR's usage, so a two-year window must get two
    # years of it. Normalising to the window total instead would silently halve it.
    years = days / 365
    e_sum, g_sum = (sum(e_w) or 1.0) / years, (sum(g_w) or 1.0) / years
    return ([e_kwh * w / e_sum for w in e_w], [g_kwh * w / g_sum for w in g_w])


def _segments(candidate, current, start, window_end, switch_date, rise):
    """The run of tariffs you would actually be on, as (from, to, tariff, rate multiplier).

    The multiplier is 1.0 while a fix holds and 1 + the assumed rise once it lapses,
    because a rate agreed two years ago is not one you can keep. That is the whole
    point: an expiring tariff has to be costed as what replaces it.
    """
    segs = []
    at = start
    if current is not None and switch_date > at:          # time still to run on your fix
        segs.append((at, min(switch_date, window_end), current, 1.0))
        at = min(switch_date, window_end)
    available = candidate.start_date if (candidate.start_date and candidate.start_date > at) else at
    if available > at and current is not None:            # a gap before the new deal starts
        segs.append((at, min(available, window_end), current, 1 + rise))
        at = min(available, window_end)
    if at < window_end:
        lapses = candidate.end_date if (candidate.end_date and at < candidate.end_date < window_end) else None
        if lapses:
            segs.append((at, lapses, candidate, 1.0))
            # after it lapses the rise compounds once a year, not once ever. Over a single
            # year that is the same number; over two it is the whole argument for fixing.
            year, n = lapses, 1
            while year < window_end:
                nxt = min(year + timedelta(days=365), window_end)
                segs.append((year, nxt, candidate, (1 + rise) ** n))
                year, n = nxt, n + 1
        else:
            segs.append((at, window_end, candidate, 1.0))
    return segs


def _cost(segments, e_daily, g_daily, start, vat=None):
    """Add up a run of segments. Returns (electricity, gas, standing) in pounds.

    `vat` is a per-day multiplier on electricity only. It has to be applied day by day
    rather than to the total, because the change lands mid-window -- and to the standing
    charge as well as the unit rate, since VAT is charged on the whole electricity bill.
    """
    vat = vat or [1.0] * len(e_daily)
    e_cost = g_cost = standing = 0.0
    for seg_start, seg_end, t, mult in segments:
        i, j = (seg_start - start).days, (seg_end - start).days
        i, j = max(0, i), min(len(e_daily), j)
        if j <= i:
            continue
        e_cost += sum(e_daily[k] * vat[k] for k in range(i, j)) * t.elec_unit_p * mult / 100
        g_cost += sum(g_daily[i:j]) * t.gas_unit_p * mult / 100
        standing += (sum(vat[i:j]) * t.elec_sc_p + (j - i) * t.gas_sc_p) * mult / 100
    return e_cost, g_cost, standing


def compare_tariffs(tariffs, e_kwh, g_kwh, include_exit, include_incentive,
                    start=None, forward=None, price_rise=0.0, window_days=365,
                    vat_change_date=VAT_CHANGE_DATE, vat_in_rates=VAT_IN_RATES,
                    vat_after=VAT_AFTER, vat_revert_date=VAT_REVERT_DATE,
                    exit_fee_free_days=EXIT_FEE_FREE_DAYS):
    """Cost each tariff over the SAME next year and rank cheapest first.

    Every option is priced across one window starting today, so they are genuinely
    comparable: the days still to run on your current fix are included in all of
    them, because you are having those days whatever you choose. When your fix ends
    the candidate takes over, and if you do nothing your own rates carry on at
    `price_rise` -- a rate you agreed two years ago is not one you keep.

    That baseline is the point. Ranking against today's expiring rate makes an old
    fix look unbeatable right up to the day it lapses, and reports a saving of zero
    for switching. Ranking against what you would actually pay from the expiry date
    shows which deal is worth taking.

    Where a tariff cannot start until later, switching early is not an option and
    Cost_Switch_Today_GBP is None. Where it can, that column costs going now and
    pays your current tariff's exit fee (the fee you would actually be charged --
    it is for leaving, not for arriving).
    """
    start = start or date.today()
    window_end = start + timedelta(days=window_days)
    e_daily, g_daily = _daily_usage(forward, e_kwh, g_kwh, start, window_days)
    vat = _vat_multipliers(start, window_days, vat_change_date, vat_in_rates, vat_after,
                           vat_revert_date)
    rise = price_rise or 0.0

    current = next((t for t in tariffs if t.is_current), None)
    # you are on your fix until it ends; with no end date there is nothing to wait for
    at_expiry = current.end_date if (current and current.end_date and current.end_date > start) else start

    rows = []
    baseline = None
    for t in tariffs:
        is_do_nothing = current is not None and t is current
        # Start_Date is when the deal actually begins, not merely when it becomes
        # available. A deal that has to start before your fix ends makes you leave
        # early, and leaving early is what an exit fee is for -- so the two are the
        # same fact and the cost has to follow the date.
        switch_date = start if is_do_nothing else (
            t.start_date if (t.start_date and t.start_date > start) else at_expiry)
        segs = _segments(t, current, start, window_end, switch_date, rise)
        e_cost, g_cost, standing = _cost(segs, e_daily, g_daily, start, vat)
        gross = e_cost + g_cost + standing
        incentive = t.incentive if include_incentive else 0
        leaves_early = bool(not is_do_nothing and current is not None
                            and current.end_date and switch_date < current.end_date)
        # ...but leaving early is free once you are inside the run-out window
        free_from = (current.end_date - timedelta(days=exit_fee_free_days)
                     if (current and current.end_date) else None)
        chargeable = bool(leaves_early and free_from and switch_date < free_from)
        fee = current.exit_fee if (chargeable and include_exit and current) else 0
        expected = gross - incentive + fee

        # switching today instead of waiting: only real if the deal is open to you now
        early = None
        if not is_do_nothing and not (t.start_date and t.start_date > start):
            early_segs = _segments(t, current, start, window_end, start, rise)
            ec, gc, sc = _cost(early_segs, e_daily, g_daily, start, vat)
            fee = (current.exit_fee if (current and include_exit) else 0)
            early = ec + gc + sc + fee - incentive

        # this tariff's own rates held for a whole year, ignoring when it starts or ends.
        # Not the ranking figure -- it is the reference the report re-prices at renewal,
        # and what you would quote someone comparing rate cards.
        flat = (e_kwh * t.elec_unit_p / 100 + g_kwh * t.gas_unit_p / 100
                + 365 * (t.elec_sc_p + t.gas_sc_p) / 100 - incentive)
        on_candidate = sum((min(b, window_end) - a).days for a, b, ta, _ in segs if ta is t)
        if is_do_nothing:
            baseline = expected
        rows.append({
            "Supplier": t.supplier, "Tariff_Name": t.tariff_name, "Type": t.tariff_type,
            "Is_Current": "Yes" if t.is_current else "",
            "Start_Date": t.start_date, "End_Date": t.end_date,
            "Elec_Unit_p": t.elec_unit_p, "Elec_SC_p_day": t.elec_sc_p,
            "Gas_Unit_p": t.gas_unit_p, "Gas_SC_p_day": t.gas_sc_p,
            "Electricity_Cost_GBP": e_cost, "Gas_Cost_GBP": g_cost, "Standing_Cost_GBP": standing,
            "Gross_Annual_Cost_GBP": gross, "Exit_Fee_GBP": t.exit_fee, "Incentive_GBP": t.incentive,
            "Expected_Annual_Cost_GBP": expected, "Monthly_Equivalent_GBP": expected / 12,
            "Cost_Switch_Today_GBP": early, "Cost_At_Todays_Rates_GBP": flat,
            "Switch_Date": switch_date,
            "Leaves_Current_Early": ("Yes, fee-free" if (leaves_early and not chargeable)
                                     else "Yes" if leaves_early else ""),
            "Exit_Fee_Applied_GBP": fee,
            "Days_On_This_Tariff": on_candidate,
            "Notes": t.notes,
        })

    rows.sort(key=lambda x: x["Expected_Annual_Cost_GBP"])
    if baseline is None:
        baseline = rows[0]["Expected_Annual_Cost_GBP"] if rows else 0
    for r in rows:
        r["Saving_vs_Current_GBP"] = baseline - r["Expected_Annual_Cost_GBP"]
        r["Saving_Switch_Today_GBP"] = (None if r["Cost_Switch_Today_GBP"] is None
                                        else baseline - r["Cost_Switch_Today_GBP"])
    return rows
