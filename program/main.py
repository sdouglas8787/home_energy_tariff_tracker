from __future__ import annotations
import sys
from datetime import date, datetime
from pathlib import Path

# Allow running as `python program/main.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from excel.config import INPUT_FILE, OUTPUT_FILE, HTML_FILE, WEATHER_CACHE, FORECAST_LOG
from excel.workbook_io import load_inputs
from model.calculations import (
    calculate_daily_usage, aggregate_monthly, weighted_annual_usage, compare_tariffs,
    build_insights, build_walkforward, build_forward, build_montecarlo,
)
from model.weather import get_monthly_weather
from model.forecast_log import append_forecast, load_tracking
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

    generated = datetime.now().strftime("%d %b %Y %H:%M")
    address = str(settings.get("Property address", ""))
    export_output(OUTPUT_FILE, address, (e, g), method, monthly, comparisons, validation,
                  settings, generated, insights)
    render_html(HTML_FILE, address, (e, g), method, comparisons, insights, backtest,
                forward, generated, settings, monthly, weather, tracking, annual_actual, bills, mc)

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
