"""Checks for deriving meter readings from half-hourly data."""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "program"))

from model import synth
from model.models import Reading

DAY = date(2026, 2, 1)


def _store(fuel, start, days, per_half_hour=0.125, slots=48):
    """A tidy store: `days` days from `start`, `slots` half-hours each.

    0.125 kWh a half-hour = exactly 6 kWh a day, and every total below is exact in
    binary floating point, so the assertions can compare without a tolerance.
    """
    base = int(datetime.combine(start, datetime.min.time(), timezone.utc).timestamp())
    return [(fuel, base + d * 86400 + s * 1800, per_half_hour)
            for d in range(days) for s in range(slots)]


def _read(d, value, fuel="Electricity", unit="kWh", read_type="Actual"):
    return Reading(d, fuel, value, read_type, unit)


# --- day completeness ---------------------------------------------------------

def test_partial_days_are_not_counted_as_whole_ones():
    store = _store("Electricity", DAY, 3) + _store("Electricity", DAY + timedelta(days=3), 1, slots=20)
    daily = synth.daily_kwh(store, "Electricity")
    assert sorted(daily) == [DAY, DAY + timedelta(days=1), DAY + timedelta(days=2)]
    assert daily[DAY] == 6.0               # 48 half-hours at 0.125


def test_both_fuels_gate_the_end_date():
    # electricity runs a week longer than gas; the limit is where BOTH are complete,
    # because a month counts its days across the two fuels at once
    store = _store("Electricity", DAY, 14) + _store("Gas", DAY, 7)
    assert synth.last_complete_day(store) == DAY + timedelta(days=6)
    assert synth.last_complete_day(_store("Electricity", DAY, 3)) is None   # no gas at all


# --- deriving -----------------------------------------------------------------

def test_reading_is_anchor_plus_the_half_hours_since():
    store = _store("Electricity", DAY, 21)
    anchor = _read(DAY - timedelta(days=1), 1000.0)
    vals = synth.derive(store, [anchor], gas_factor=11.1868)["Electricity"]
    # cadence lays one down every 7 days, and always the last day available
    assert sorted(vals) == [DAY + timedelta(days=n) for n in (6, 13, 20)]
    assert vals[DAY + timedelta(days=6)] == 1000.0 + 7 * 6.0      # seven whole days at 6 kWh


def test_gas_is_converted_back_into_the_unit_the_meter_counts_in():
    store = _store("Gas", DAY, 8)                                  # 6 kWh/day
    anchor = _read(DAY - timedelta(days=1), 500.0, fuel="Gas", unit="m3")
    vals = synth.derive(store, [anchor], gas_factor=11.1868)["Gas"]
    d = DAY + timedelta(days=6)
    assert vals[d] == 500.0 + (7 * 6.0) / 11.1868                  # kWh back to m3

    ft3 = synth.derive(store, [_read(DAY - timedelta(days=1), 500.0, fuel="Gas", unit="ft3")],
                       gas_factor=11.1868)["Gas"]
    assert ft3[d] == 500.0 + (7 * 6.0) / (11.1868 * synth.FT3_TO_M3)


def test_a_gap_in_the_half_hours_stops_the_running_total():
    # day 3 is only half reported, so nothing from day 3 onwards can be trusted
    store = (_store("Electricity", DAY, 3)
             + _store("Electricity", DAY + timedelta(days=3), 1, slots=10)
             + _store("Electricity", DAY + timedelta(days=4), 20))
    vals = synth.derive(store, [_read(DAY - timedelta(days=1), 1000.0)],
                        gas_factor=11.1868)["Electricity"]
    assert all(d < DAY + timedelta(days=3) for d in vals)


def test_readings_you_took_are_never_overwritten():
    store = _store("Electricity", DAY, 30)
    reads = [_read(DAY - timedelta(days=1), 1000.0), _read(DAY + timedelta(days=9), 1234.0)]
    vals = synth.derive(store, reads, gas_factor=11.1868)["Electricity"]
    # the date of a real reading gets a derived value too -- that is the cross-check --
    # and the forward run anchors on the later real reading, not the derived one
    assert vals[DAY + timedelta(days=9)] == 1000.0 + 10 * 6.0
    assert vals[DAY + timedelta(days=16)] == 1234.0 + 7 * 6.0


# --- cross-check --------------------------------------------------------------

def test_a_misread_meter_is_flagged():
    store = _store("Electricity", DAY, 30)
    good = _read(DAY - timedelta(days=1), 1000.0)
    # half-hourly says 60 kWh over ten days; the meter claims 148 (a transposed digit)
    reads = [good, _read(DAY + timedelta(days=9), 1148.0)]
    rows = synth.cross_check(synth.derive(store, reads, gas_factor=11.1868), reads)
    assert len(rows) == 1
    assert "Half-hourly disagrees" in rows[0][5]


def test_reading_the_meter_at_a_different_time_of_day_is_not_an_anomaly():
    store = _store("Electricity", DAY, 30)
    good = _read(DAY - timedelta(days=1), 1000.0)
    # out by most of a day's usage: that is when you happened to look, not a fault
    reads = [good, _read(DAY + timedelta(days=9), 1000.0 + 10 * 6.0 + 4.0)]
    assert synth.cross_check(synth.derive(store, reads, gas_factor=11.1868), reads) == []


# --- tidy tables for pivoting -------------------------------------------------

def test_pivot_tables_are_tidy_and_agree_with_each_other():
    from model.hh import pivot_tables
    store = _store("Electricity", DAY, 3) + _store("Gas", DAY, 3, per_half_hour=0.25)
    tables = {name: (headers, rows) for name, headers, rows, _ in pivot_tables(store)}

    hh_headers, hh_rows = tables["Half Hourly"]
    assert len(hh_rows) == len(store)                       # one record per interval
    assert all(len(r) == len(hh_headers) for r in hh_rows)  # no ragged rows to break a pivot

    daily_headers, daily_rows = tables["Daily Usage"]
    assert len(daily_rows) == 6                             # 3 days x 2 fuels
    kwh = daily_headers.index("kWh")
    # the daily sheet must reconcile to the half-hourly one, or a pivot of either misleads
    assert round(sum(r[kwh] for r in daily_rows), 6) == round(sum(k for _, _, k in store), 6)
    assert all(r[daily_headers.index("Complete_Day")] == "Yes" for r in daily_rows)


def test_the_profile_averages_whole_days_only():
    from model.hh import pivot_tables
    # two full Sundays, and a third only half reported: the half day must not drag the mean
    sunday = date(2026, 2, 1)                               # a Sunday
    store = (_store("Electricity", sunday, 1)
             + _store("Electricity", sunday + timedelta(days=7), 1)
             + _store("Electricity", sunday + timedelta(days=14), 1, per_half_hour=0.001, slots=10))
    headers, rows = next((h, r) for n, h, r, _ in pivot_tables(store) if n == "Load Profile")
    sundays = [r for r in rows if r[headers.index("Weekday")] == "Sunday"]
    assert sundays and all(r[headers.index("Days_Averaged")] == 2 for r in sundays)
    assert all(r[headers.index("Average_kWh")] == 0.125 for r in sundays)
