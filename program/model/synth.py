"""Derive meter readings from half-hourly data.

A meter reading is a running total; half-hourly data is what happened in each
half hour. So the two are the same information seen from different ends, and
given one real reading to anchor on, the half-hours since it add up to what the
meter must say now.

That is worth doing twice over:

  * Forward -- your last real reading is often weeks old, and the forecast only
    ever sees metered data. Deriving readings past it lets the model use history
    you already have on disk rather than waiting for you to go and read the meter.

  * Backward -- between two readings you actually took, the half-hours in between
    should add up to the difference. When they don't, one of the two readings is
    wrong (a transposed digit, a misread dial, a wrong gas conversion), and that
    is worth telling you about.

Derived values are written to their own column in the workbook, never over a real
reading. If you later go back and fill in what the meter actually said, the
cross-check picks the pair up on the next run and tells you if they disagree.

A derived reading is as-at midnight ending its date, whereas you read the meter
at whatever time of day you happened to be passing. That is a real difference of
up to a day's usage, so the cross-check tolerance allows for it rather than
crying wolf every time.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
MIN_SLOTS = 46          # of 48: a day missing more than an hour is not a full day
CADENCE_DAYS = 7        # how often to lay down a derived reading past the last real one
FT3_TO_M3 = 2.83        # matches calculate_daily_usage


def daily_kwh(store, fuel, min_slots=MIN_SLOTS):
    """{local date: kWh} for days the meter reported (near) completely.

    Partial days are dropped rather than counted low -- a half-covered day would
    understate a derived reading and every reading built on top of it.
    """
    sums, counts = {}, {}
    for f, epoch, kwh in store:
        if f != fuel:
            continue
        d = datetime.fromtimestamp(epoch, timezone.utc).astimezone(LONDON).date()
        sums[d] = sums.get(d, 0.0) + kwh
        counts[d] = counts.get(d, 0) + 1
    return {d: v for d, v in sums.items() if counts[d] >= min_slots}


def last_complete_day(store, fuels=("Electricity", "Gas")):
    """The most recent day EVERY fuel covers completely.

    Deliberately the earliest of the per-fuel ends, not the latest. aggregate_monthly
    counts a month's days across both fuels at once, so extending one fuel past the
    other would leave a month looking well covered while a fuel sat near zero in it,
    and the seasonal profile would take that as a real month. Both fuels move together
    or neither does.
    """
    ends = []
    for fuel in fuels:
        days = daily_kwh(store, fuel)
        if not days:
            return None
        ends.append(max(days))
    return min(ends)


def _factor(gas_factor, unit):
    """kWh per unit of whatever the meter counts in."""
    return gas_factor * FT3_TO_M3 if str(unit).lower() == "ft3" else gas_factor


def _to_meter_units(kwh, fuel, unit, gas_factor):
    return kwh / _factor(gas_factor, unit) if fuel == "Gas" else kwh


def derive(store, readings, gas_factor, limit=None, cadence_days=CADENCE_DAYS):
    """Work out what the meter would have said, on dates we can stand behind.

    Returns {fuel: {date: reading}} in the meter's own units (kWh for electricity,
    m3/ft3 for gas). A date only appears when every day between its anchor and it
    was completely covered -- one missing day and the running total is wrong, so we
    say nothing instead of guessing.

    Two kinds of date get a value: every real reading after the first (anchored on
    the reading before it, which is what makes the cross-check possible), and dates
    past the last real reading, laid down every `cadence_days` plus the latest day
    available, so there is something to fill in retrospectively without a row per day.
    """
    out = {}
    by_fuel = {}
    for r in readings:
        by_fuel.setdefault(r.fuel, []).append(r)

    for fuel, rows in by_fuel.items():
        rows = sorted(rows, key=lambda r: r.date)
        daily = daily_kwh(store, fuel)
        if not daily:
            continue
        end = max(daily) if limit is None else min(max(daily), limit)
        vals = {}

        # 1. each real reading, predicted from the one before it
        for prev, cur in zip(rows, rows[1:]):
            span = [prev.date + timedelta(days=i + 1) for i in range((cur.date - prev.date).days)]
            if span and all(d in daily for d in span):
                kwh = sum(daily[d] for d in span)
                vals[cur.date] = prev.reading + _to_meter_units(kwh, fuel, cur.meter_unit, gas_factor)

        # 2. forward from the last real reading, while the days stay unbroken
        anchor = rows[-1]
        cum = 0.0
        d = anchor.date + timedelta(days=1)
        while d <= end and d in daily:
            cum += daily[d]
            if (d - anchor.date).days % cadence_days == 0 or d == end:
                vals[d] = anchor.reading + _to_meter_units(cum, fuel, anchor.meter_unit, gas_factor)
            d += timedelta(days=1)

        out[fuel] = vals
    return out


def cross_check(derived, readings, tolerance_pct=0.05):
    """Compare what you read against what the half-hours say, in validation-row shape.

    Only flags a genuine disagreement: the allowance is 5% of the interval's own
    consumption, or one and a half days of it, whichever is larger. The day-and-a-half
    covers reading the meter at teatime one visit and breakfast the next, which is not
    an anomaly however different the numbers look.
    """
    rows = []
    by_fuel = {}
    for r in readings:
        by_fuel.setdefault(r.fuel, []).append(r)

    for fuel, rs in by_fuel.items():
        rs = sorted(rs, key=lambda r: r.date)
        for prev, cur in zip(rs, rs[1:]):
            expected = (derived.get(fuel) or {}).get(cur.date)
            if expected is None:
                continue
            actual_delta = cur.reading - prev.reading
            days = (cur.date - prev.date).days
            if days <= 0 or actual_delta <= 0:
                continue                       # already flagged by the usual validation
            diff = cur.reading - expected
            allowance = max(abs(actual_delta) * tolerance_pct,
                            abs(actual_delta) / days * 1.5)
            if abs(diff) > allowance:
                pct = diff / actual_delta * 100
                rows.append([fuel, prev.date, cur.date, days, round(actual_delta, 2),
                             f"Half-hourly disagrees: meter says {actual_delta:,.1f}, "
                             f"half-hourly says {actual_delta - diff:,.1f} ({pct:+.0f}%)"])
    return rows
