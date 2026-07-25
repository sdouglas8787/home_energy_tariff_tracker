"""Persist each run's forward forecast so later actuals can grade it.

Every run appends the forecast it made for future months. When you add real
readings for those months, `load_tracking` joins the earliest forecast we made
with the actual, so you can see how close we were (and spot outliers/misreads).
"""
from __future__ import annotations
import csv
from calendar import monthrange
from pathlib import Path

FIELDS = ["run_date", "fuel", "month", "forecast_kwh"]


def _read(path):
    try:
        with open(path, newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def append_forecast(path, run_date, forward):
    """Log the monthly forecast totals for this run (idempotent per run_date)."""
    existing = _read(path)
    have = {(r["run_date"], r["fuel"], r["month"]) for r in existing}
    new = []
    for fuel, pts in forward.items():
        for p in pts:
            m = p["month"]
            key = (run_date, fuel, m.isoformat())
            if key in have:
                continue
            total = p["forecast"] * monthrange(m.year, m.month)[1]
            new.append({"run_date": run_date, "fuel": fuel,
                        "month": m.isoformat(), "forecast_kwh": round(total, 1)})
    if not new:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    write_header = not existing
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            w.writeheader()
        w.writerows(new)


def load_tracking(path, monthly):
    """Match the earliest logged forecast for each month against the actual."""
    rows = _read(path)
    if not rows:
        return []
    actual = {(r[0].year, r[0].month): (r[1], r[2], r[3]) for r in monthly}
    idxmap = {"Electricity": 0, "Gas": 1}
    earliest = {}
    for r in rows:
        k = (r["fuel"], r["month"])
        if k not in earliest or r["run_date"] < earliest[k]["run_date"]:
            earliest[k] = r
    out = []
    for (fuel, month), r in earliest.items():
        y, m, _ = month.split("-")
        a = actual.get((int(y), int(m)))
        if not a or a[2] < 25:                       # only graded once a full actual exists
            continue
        av = a[idxmap[fuel]]
        fcv = float(r["forecast_kwh"])
        out.append({"fuel": fuel, "month": month, "forecast": fcv, "actual": av,
                    "error": (av - fcv) / fcv if fcv else 0.0, "forecast_made": r["run_date"]})
    out.sort(key=lambda x: (x["month"], x["fuel"]))
    return out
