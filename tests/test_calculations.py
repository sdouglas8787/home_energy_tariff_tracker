from datetime import date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "program"))

from model.models import Reading, Tariff
from model.calculations import build_montecarlo, calculate_daily_usage, compare_tariffs


def _tariff(**kw):
    base = dict(supplier="X", tariff_name="", tariff_type="Fixed", start_date=None, end_date=None,
                elec_unit_p=20, elec_sc_p=50, gas_unit_p=5, gas_sc_p=25, exit_fee=0, incentive=0,
                notes="", is_current=False)
    base.update(kw)
    return Tariff(**base)


def test_separate_standing_charges():
    # vat_change_date=None keeps this a plain arithmetic check; VAT has its own tests
    result = compare_tariffs([_tariff()], 1000, 2000, False, False, vat_change_date=None)[0]
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


# --- costing a year that contains a switch ------------------------------------

def _year_ahead(**kw):
    """compare_tariffs over a fixed window, so the assertions don't move with the date."""
    base = dict(start=date(2026, 8, 30), price_rise=0.08, vat_change_date=None)
    base.update(kw)
    return base


def test_an_expiring_tariff_is_costed_as_what_replaces_it():
    # a fix with 39 days left cannot be held for a year: the rest of the year is
    # the same rates plus the assumed renewal rise, and that is what to rank against
    current = _tariff(supplier="BG", elec_unit_p=20, elec_sc_p=0, gas_sc_p=0,
                      end_date=date(2026, 10, 8), is_current=True)
    rows = compare_tariffs([current], 3650, 0, False, False, **_year_ahead())
    held, renewed = 39, 365 - 39
    assert round(rows[0]["Expected_Annual_Cost_GBP"], 2) == round(
        10 * held * 20 / 100 + 10 * renewed * 20 * 1.08 / 100, 2)
    # the flat rate-card figure is still available, and is lower -- that is the point
    assert rows[0]["Cost_At_Todays_Rates_GBP"] < rows[0]["Expected_Annual_Cost_GBP"]


def test_a_replacement_deal_wins_even_though_its_rate_looks_worse():
    # exactly the trap: today's rate is cheaper, but it ends, and the ranking used to
    # call that a saving of zero
    current = _tariff(supplier="BG", elec_unit_p=20, elec_sc_p=0, gas_sc_p=0,
                      end_date=date(2026, 10, 8), is_current=True)
    offer = _tariff(supplier="Fuse", elec_unit_p=21, elec_sc_p=0, gas_sc_p=0,
                    start_date=date(2026, 10, 8))
    rows = compare_tariffs([current, offer], 3650, 0, False, False, **_year_ahead())
    assert rows[0]["Supplier"] == "Fuse"            # 21p beats 20p once 20p becomes 21.6p
    assert rows[0]["Saving_vs_Current_GBP"] > 0
    # both plans carry the 39 days still to run on the current fix
    assert rows[0]["Days_On_This_Tariff"] == 365 - 39


def test_a_deal_you_cannot_start_yet_has_no_early_switch_price():
    current = _tariff(supplier="BG", end_date=date(2026, 10, 8), exit_fee=100, is_current=True)
    later = _tariff(supplier="Fuse", start_date=date(2026, 10, 8))
    now = _tariff(supplier="Open", start_date=None)
    rows = {r["Supplier"]: r for r in
            compare_tariffs([current, later, now], 1000, 0, True, False, **_year_ahead())}
    assert rows["Fuse"]["Cost_Switch_Today_GBP"] is None      # not open to you until October
    assert rows["Open"]["Cost_Switch_Today_GBP"] is not None
    # leaving early is charged your own tariff's exit fee, not the new one's
    assert rows["Open"]["Cost_Switch_Today_GBP"] > rows["Open"]["Expected_Annual_Cost_GBP"]


def test_usage_follows_the_seasons_when_a_forecast_is_available():
    from datetime import date as _d
    winter_heavy = {"Gas": [{"month": _d(2026, m, 1), "forecast": (30 if m in (12, 1, 2) else 1)}
                            for m in list(range(9, 13)) + list(range(1, 10))],
                    "Electricity": []}
    t = _tariff(elec_unit_p=0, elec_sc_p=0, gas_sc_p=0, gas_unit_p=10)
    flat = compare_tariffs([t], 0, 3650, False, False, **_year_ahead())[0]
    shaped = compare_tariffs([t], 0, 3650, False, False, **_year_ahead(forward=winter_heavy))[0]
    # same annual kWh either way -- the shape only matters once rates differ by segment
    assert round(flat["Gas_Cost_GBP"], 2) == round(shaped["Gas_Cost_GBP"], 2) == 365.0


def test_the_simulation_uses_the_same_blended_rates_as_the_ranking():
    current = _tariff(supplier="BG", elec_unit_p=20, elec_sc_p=0, gas_sc_p=0,
                      end_date=date(2026, 10, 8), is_current=True)
    offer = _tariff(supplier="Fuse", elec_unit_p=21, elec_sc_p=0, gas_sc_p=0,
                    start_date=date(2026, 10, 8))
    rows = compare_tariffs([current, offer], 3650, 0, False, False, **_year_ahead())
    mc = build_montecarlo((3650, 0), {}, [current, offer], False, False, comparisons=rows)
    # the two rankings on the same page must not contradict each other
    assert mc["tariffs"][0]["supplier"] == rows[0]["Supplier"] == "Fuse"


# --- the electricity VAT cut ---------------------------------------------------

VAT = dict(start=date(2026, 8, 30), price_rise=0.0, vat_change_date=date(2026, 10, 1),
           vat_revert_date=date(2027, 4, 1), vat_in_rates=0.05, vat_after=0.0)
VAT_DAYS = (date(2027, 4, 1) - date(2026, 10, 1)).days      # the holiday, 182 days


def test_vat_cut_applies_to_electricity_from_the_change_date():
    # rates are quoted including 5% VAT, so at 0% the electricity side falls by 1/1.05
    t = _tariff(elec_unit_p=20, elec_sc_p=0, gas_unit_p=0, gas_sc_p=0)
    row = compare_tariffs([t], 3650, 0, False, False, **VAT)[0]
    full = 365 - VAT_DAYS                         # days still charged at 5%
    assert round(row["Electricity_Cost_GBP"], 4) == round(
        10 * full * 20 / 100 + 10 * VAT_DAYS * 20 / 100 / 1.05, 4)


def test_vat_cut_applies_to_the_electricity_standing_charge_too():
    # VAT is charged on the whole electricity bill, not just the units
    t = _tariff(elec_unit_p=0, elec_sc_p=50, gas_unit_p=0, gas_sc_p=25)
    row = compare_tariffs([t], 0, 0, False, False, **VAT)[0]
    full = 365 - VAT_DAYS
    assert round(row["Standing_Cost_GBP"], 4) == round(
        (full * 50 + VAT_DAYS * 50 / 1.05 + 365 * 25) / 100, 4)


def test_vat_cut_leaves_gas_alone():
    gas_only = _tariff(elec_unit_p=0, elec_sc_p=0, gas_unit_p=8, gas_sc_p=30)
    with_vat = compare_tariffs([gas_only], 0, 3650, False, False, **VAT)[0]
    without = compare_tariffs([gas_only], 0, 3650, False, False,
                              **{**VAT, "vat_change_date": None})[0]
    assert with_vat["Expected_Annual_Cost_GBP"] == without["Expected_Annual_Cost_GBP"]


def test_vat_cut_barely_moves_the_ranking_because_it_hits_everyone():
    cheap = _tariff(supplier="A", elec_unit_p=24, gas_unit_p=8)
    dear = _tariff(supplier="B", elec_unit_p=27, gas_unit_p=8)
    with_vat = compare_tariffs([cheap, dear], 3941, 10407, False, False, **VAT)
    without = compare_tariffs([cheap, dear], 3941, 10407, False, False,
                              **{**VAT, "vat_change_date": None})
    assert [r["Supplier"] for r in with_vat] == [r["Supplier"] for r in without] == ["A", "B"]
    # everyone gets cheaper, so it is awareness of the bill, not a reason to switch
    assert with_vat[0]["Expected_Annual_Cost_GBP"] < without[0]["Expected_Annual_Cost_GBP"]


def test_the_vat_holiday_ends_and_the_rate_goes_back_up():
    t = _tariff(elec_unit_p=20, elec_sc_p=0, gas_unit_p=0, gas_sc_p=0)
    holiday = compare_tariffs([t], 3650, 0, False, False, **VAT)[0]
    forever = compare_tariffs([t], 3650, 0, False, False,
                              **{**VAT, "vat_revert_date": None})[0]
    # treating a six-month holiday as permanent would flatter the year by the difference
    assert holiday["Electricity_Cost_GBP"] > forever["Electricity_Cost_GBP"]


def test_a_deal_that_must_start_early_pays_to_leave_early():
    # the real trap: a cheaper deal whose window closes before your fix ends is not
    # cheaper at all once the exit fee lands
    current = _tariff(supplier="BG", elec_unit_p=24, elec_sc_p=0, gas_sc_p=0,
                      end_date=date(2026, 10, 8), exit_fee=200, is_current=True)
    early = _tariff(supplier="Fuse", elec_unit_p=23, elec_sc_p=0, gas_sc_p=0,
                    start_date=date(2026, 9, 29))          # must start before the fix ends
    at_expiry = _tariff(supplier="EON", elec_unit_p=23.5, elec_sc_p=0, gas_sc_p=0,
                        start_date=date(2026, 10, 8))
    rows = {r["Supplier"]: r for r in
            compare_tariffs([current, early, at_expiry], 3941, 0, True, False,
                            exit_fee_free_days=0, **_year_ahead())}

    assert rows["Fuse"]["Leaves_Current_Early"] == "Yes"
    assert rows["Fuse"]["Exit_Fee_Applied_GBP"] == 200      # the fee is your tariff's, not theirs
    assert rows["EON"]["Leaves_Current_Early"] == ""
    assert rows["EON"]["Exit_Fee_Applied_GBP"] == 0
    # cheapest rate, dearest outcome -- and the ranking has to say so
    assert rows["Fuse"]["Elec_Unit_p"] < rows["EON"]["Elec_Unit_p"]
    assert rows["Fuse"]["Expected_Annual_Cost_GBP"] > rows["EON"]["Expected_Annual_Cost_GBP"]


def test_switching_at_expiry_is_never_charged_an_exit_fee():
    current = _tariff(supplier="BG", end_date=date(2026, 10, 8), exit_fee=200, is_current=True)
    at_expiry = _tariff(supplier="EON", start_date=date(2026, 10, 8))
    rows = {r["Supplier"]: r for r in
            compare_tariffs([current, at_expiry], 1000, 1000, True, False, **_year_ahead())}
    assert rows["EON"]["Exit_Fee_Applied_GBP"] == 0


def test_leaving_early_is_free_inside_the_run_out_window():
    # switching 9 days before a fix ends is an early switch that costs nothing, and a
    # deal priced as if it cost £200 would be wrongly rejected
    current = _tariff(supplier="BG", elec_unit_p=24, elec_sc_p=0, gas_sc_p=0,
                      end_date=date(2026, 10, 8), exit_fee=200, is_current=True)
    early = _tariff(supplier="Fuse", elec_unit_p=23, elec_sc_p=0, gas_sc_p=0,
                    start_date=date(2026, 9, 29))
    rows = {r["Supplier"]: r for r in
            compare_tariffs([current, early], 3941, 0, True, False,
                            exit_fee_free_days=50, **_year_ahead())}
    assert rows["Fuse"]["Exit_Fee_Applied_GBP"] == 0
    assert rows["Fuse"]["Leaves_Current_Early"] == "Yes, fee-free"
    assert rows["Fuse"]["Saving_vs_Current_GBP"] > 0        # cheapest rate now actually wins


def test_leaving_well_before_the_run_out_window_still_costs():
    current = _tariff(supplier="BG", elec_unit_p=24, elec_sc_p=0, gas_sc_p=0,
                      end_date=date(2027, 6, 1), exit_fee=200, is_current=True)
    early = _tariff(supplier="Fuse", elec_unit_p=23, elec_sc_p=0, gas_sc_p=0,
                    start_date=date(2026, 9, 29))
    rows = {r["Supplier"]: r for r in
            compare_tariffs([current, early], 3941, 0, True, False,
                            exit_fee_free_days=50, **_year_ahead())}
    assert rows["Fuse"]["Exit_Fee_Applied_GBP"] == 200


def test_a_two_year_window_gets_two_years_of_usage():
    t = _tariff(elec_unit_p=20, elec_sc_p=0, gas_unit_p=0, gas_sc_p=0)
    one = compare_tariffs([t], 3650, 0, False, False, **_year_ahead())[0]
    two = compare_tariffs([t], 3650, 0, False, False, window_days=730, **_year_ahead())[0]
    # same annual usage, twice the window, twice the bill -- not the same bill spread thin
    assert round(two["Electricity_Cost_GBP"], 2) == round(one["Electricity_Cost_GBP"] * 2, 2)
