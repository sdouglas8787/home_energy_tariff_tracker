from datetime import date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "program"))

from model.models import Reading, Tariff
from model.calculations import calculate_daily_usage, compare_tariffs


def _tariff(**kw):
    base = dict(supplier="X", tariff_name="", tariff_type="Fixed", start_date=None, end_date=None,
                elec_unit_p=20, elec_sc_p=50, gas_unit_p=5, gas_sc_p=25, exit_fee=0, incentive=0,
                notes="", is_current=False)
    base.update(kw)
    return Tariff(**base)


def test_separate_standing_charges():
    result = compare_tariffs([_tariff()], 1000, 2000, False, False)[0]
    assert result["Standing_Cost_GBP"] == 365 * (50 + 25) / 100


def test_gas_conversion():
    readings = [
        Reading(date(2026, 1, 1), "Gas", 100, "Actual", "m3"),
        Reading(date(2026, 1, 2), "Gas", 101, "Actual", "m3"),
    ]
    daily, _ = calculate_daily_usage(readings, 11.1868)
    assert round(daily[0][2], 4) == 11.1868


def test_saving_vs_current():
    current = _tariff(supplier="British Gas", elec_unit_p=30, is_current=True)
    cheaper = _tariff(supplier="Other", elec_unit_p=20)
    rows = compare_tariffs([current, cheaper], 1000, 0, False, False)
    best = rows[0]
    assert best["Supplier"] == "Other"
    assert best["Saving_vs_Current_GBP"] > 0
    assert best["Is_Current"] == ""
