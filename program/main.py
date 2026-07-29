from __future__ import annotations
import sys
from datetime import date, datetime
from pathlib import Path

# Allow running as `python program/main.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from excel.config import (INPUT_FILE, OUTPUT_FILE, HTML_FILE, WEATHER_CACHE, FORECAST_LOG,
                          HH_INBOX, HH_STORE, HH_ARCHIVE)
from excel.workbook_io import load_inputs
from model.calculations import (
    calculate_daily_usage, aggregate_monthly, weighted_annual_usage, compare_tariffs,
    build_insights, build_walkforward, build_forward, build_montecarlo,
)
from model.weather import get_monthly_weather
from model.forecast_log import append_forecast, load_tracking
from model.hh import (import_files, build_profile, simulate_discount, best_slots,
                      baseload_by_month, day_matrix)
from excel.export_report import export_output
from report.html_report import render_html


def yes(value):
    return str(value).strip().lower() in {"yes", "y", "true", "1"}


def main():
    settings, readings, tariffs, bills = load_inputs(INPUT_FILE)
    if not readings:
        raise ValueError("No meter readings found in the Electricity or Gas tabs.")

    gas_factor = float(settings.get("Gas conversion (kWh per unit)") or 11.1868)
    daily, validation = calculate_daily_usage(readings, gas_factor)
    monthly = aggregate_monthly(daily)

    end = settings.get("Analysis date")
    if isinstance(end, datetime):
        end = end.date()
    if not isinstance(end, date):
        end = max(r.date for r in readings)   # blank in the workbook = use latest reading

    e_adj = float(settings.get("Electricity usage tweak", 0) or 0)
    g_adj = float(settings.get("Gas usage tweak", 0) or 0)
    backtest = build_walkforward(monthly)         # out-of-sample test of the real model
    forward = build_forward(monthly, backtest)    # recency-weighted, bias-corrected

    from calendar import monthrange

    def _annual(fuel, adj):
        pts = forward.get(fuel, [])
        if len(pts) < 12:
            return None
        return sum(p["forecast"] * monthrange(p["month"].year, p["month"].month)[1] for p in pts) * (1 + adj)

    ea, ga = _annual("Electricity", e_adj), _annual("Gas", g_adj)
    if ea and ga:
        e, g, method = ea, ga, "Recency-weighted seasonal, bias-corrected (walk-forward)"
    else:
        e, g, method = weighted_annual_usage(
            monthly, e_adj, g_adj,
            float(settings.get("Backup yearly electricity (kWh)", 4407)),
            float(settings.get("Backup yearly gas (kWh)", 11867)))

    inc_exit = yes(settings.get("Charge exit fees when switching?"))
    inc_incent = yes(settings.get("Apply sign-up incentives?"))
    comparisons = compare_tariffs(tariffs, e, g, inc_exit, inc_incent)
    insights = build_insights(daily, monthly)
    mc = build_montecarlo((e, g), backtest, tariffs, inc_exit, inc_incent)

    lat = float(settings.get("Latitude", 51.5074) or 51.5074)
    lon = float(settings.get("Longitude", -0.1278) or -0.1278)
    from datetime import timedelta
    w_start = min(r.date for r in readings)
    w_end = min(max(r.date for r in readings), date.today() - timedelta(days=1))
    weather = get_monthly_weather(lat, lon, w_start, w_end, WEATHER_CACHE)

    append_forecast(FORECAST_LOG, date.today().isoformat(), forward)
    tracking = load_tracking(FORECAST_LOG, monthly)
    annual_actual = sum(a for _, a in bills[-12:]) if len(bills) >= 12 else None

    # half-hourly load profile + time-of-use discount examples (electricity)
    hh_store, hh_files, hh_rejected = import_files(HH_INBOX, HH_STORE, HH_ARCHIVE)
    hh_profile = build_profile(hh_store) if hh_store else None
    elec_rate = comparisons[0]["Elec_Unit_p"] if comparisons else 23.41
    for c in comparisons:
        if c.get("Is_Current") == "Yes":
            elec_rate = c["Elec_Unit_p"]
    tou = []
    if hh_store:
        windows = [("Weekday evenings 4-7pm", [(set(range(5)), 16, 19)]),
                   ("Every day 4-7pm", [(None, 16, 19)]),
                   ("Sunday 9am-5pm", [({6}, 9, 17)]),
                   ("Overnight 12-5am", [(None, 0, 5)])]
        for lab, win in windows:
            s = simulate_discount(hh_store, "Electricity", win, 0.5, elec_rate)
            tou.append((lab, s["annual_kwh_in_window"], s["annual_saving"]))
    slots8 = best_slots(hh_profile["Electricity"], 8, 0.5, elec_rate) \
        if (hh_profile and hh_profile.get("Electricity")) else None
    if hh_profile and hh_profile.get("Electricity"):
        hh_profile["Electricity"]["baseload_series"] = baseload_by_month(hh_store, "Electricity")

    # driver regression: split usage into weather-driven heating vs weather-independent base
    from model.weather import get_daily_temps
    from model.drivers import daily_usage_from_hh, fit_drivers
    temps = get_daily_temps(WEATHER_CACHE, lat, lon)
    gas_rate = next((c["Gas_Unit_p"] for c in comparisons if c.get("Is_Current") == "Yes"),
                    comparisons[0]["Gas_Unit_p"] if comparisons else 6.1)
    drivers = {}
    if hh_store and temps:
        for fu in ("Gas", "Electricity"):
            drivers[fu] = fit_drivers(daily_usage_from_hh(hh_store, fu), temps)

    # ranked actions: (annual £, action, confidence, why)
    best = comparisons[0] if comparisons else None
    best_saving = best["Saving_vs_Current_GBP"] if best else 0
    actions = []
    if best and best_saving > 1:
        actions.append((best_saving, "Switch to the cheapest tariff for your usage", "high",
                        "exact, costed on your forecast usage"))
    if hh_profile and hh_profile.get("Electricity"):
        always = hh_profile["Electricity"]["baseload_kwh_per_h"] * 8760 * elec_rate / 100
        actions.append((always * 0.5, "Find and cut the 'always-on' background draw", "medium",
                        f"~{always:,.0f}/yr runs 24/7; even halving it is worth this"))
    if drivers.get("Gas") and drivers["Gas"]:
        gas_heat = drivers["Gas"]["heating_kwh"] * gas_rate / 100
        actions.append((gas_heat * 0.08, "Turn the thermostat down 1°C", "medium",
                        f"~8% of your {gas_heat:,.0f}/yr heating gas (from the driver model)"))
    if slots8:
        actions.append((slots8["annual_saving"], "Use the 8 discount slots on your peak hours", "medium",
                        "more again if you shift the dishwasher/washing into a slot"))
    actions.sort(reverse=True, key=lambda a: a[0])
    if hh_files:
        print(f"Half-hourly: imported {hh_files} file(s), filed to archive ({len(hh_store):,} intervals total)")
    if hh_rejected:
        from datetime import datetime as _dt, timezone as _tz
        from excel.config import SYSTEM
        with open(SYSTEM / "rejected_readings.csv", "w") as f:
            f.write("fuel,timestamp_utc,kwh,neighbour_max\n")
            for fu, ep, v, ref in hh_rejected:
                f.write(f"{fu},{_dt.fromtimestamp(ep, _tz.utc).isoformat()},{v},{ref:.3f}\n")
        print(f"Half-hourly: rejected {len(hh_rejected)} implausible reading(s) "
              f"(logged to data/system/rejected_readings.csv)")

    day_data = day_matrix(hh_store, "Electricity") if hh_store else (None, None, None)

    generated = datetime.now().strftime("%d %b %Y %H:%M")
    address = str(settings.get("Property address", ""))
    export_output(OUTPUT_FILE, address, (e, g), method, monthly, comparisons, validation,
                  settings, generated, insights)
    render_html(HTML_FILE, address, (e, g), method, comparisons, insights, backtest,
                forward, generated, settings, monthly, weather, tracking, annual_actual, bills, mc,
                hh_profile, tou, slots8, drivers, actions, gas_rate, day_data)

    print(f"Created {OUTPUT_FILE}")
    print(f"Created {HTML_FILE}")
    print(f"Analysis end date: {end:%d %b %Y}  ({method})")
    print(f"Forecast usage: {e:,.0f} kWh electricity; {g:,.0f} kWh gas")
    if comparisons:
        best = comparisons[0]
        print(f"Best tariff: {best['Supplier']} — {best['Tariff_Name']} "
              f"at £{best['Expected_Annual_Cost_GBP']:,.2f}/year")


if __name__ == "__main__":
    main()
