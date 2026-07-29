"""What's driving the bill: a small ordinary-least-squares regression that splits
daily usage into weather-driven heating vs a weather-independent base.

Model per fuel:  daily_kWh ~ b0 + b1*HDD + b2*weekend + b3*trend
  HDD  = heating-degree-days that day = max(0, 15.5 - mean_temp)
  weekend = 1 on Sat/Sun
  trend = years since the first day (captures a rising/falling baseline)

Pure Python (no numpy): the normal equations give a 4x4 system solved by
Gaussian elimination. Returns coefficients, R^2, and an annual kWh attribution.
"""
from __future__ import annotations
from collections import defaultdict

HDD_BASE = 15.5


def daily_usage_from_hh(store, fuel):
    from model.hh import _local
    d = defaultdict(float)
    for f, epoch, kwh in store:
        if f == fuel:
            d[_local(epoch).date()] += kwh
    return dict(d)


def _solve(A, b):
    """Solve A x = b for a small square system (Gaussian elimination, partial pivot)."""
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            return None
        M[c], M[p] = M[p], M[c]
        piv = M[c][c]
        M[c] = [v / piv for v in M[c]]
        for r in range(n):
            if r != c and M[r][c]:
                f = M[r][c]
                M[r] = [a - f * b_ for a, b_ in zip(M[r], M[c])]
    return [M[i][n] for i in range(n)]


def fit_drivers(daily_usage, daily_temp):
    """Fit the model; return coefficients, R^2 and the annualised kWh breakdown."""
    dates = sorted(d for d in daily_usage if d in daily_temp)
    if len(dates) < 30:
        return None
    d0 = dates[0]
    rows, y = [], []
    for d in dates:
        hdd = max(0.0, HDD_BASE - daily_temp[d])
        wknd = 1.0 if d.weekday() >= 5 else 0.0
        trend = (d - d0).days / 365.0
        rows.append([1.0, hdd, wknd, trend])
        y.append(daily_usage[d])
    n, k = len(rows), 4
    # normal equations X'X b = X'y
    xtx = [[sum(rows[i][a] * rows[i][b] for i in range(n)) for b in range(k)] for a in range(k)]
    xty = [sum(rows[i][a] * y[i] for i in range(n)) for a in range(k)]
    coef = _solve(xtx, xty)
    if coef is None:
        return None
    pred = [sum(coef[a] * rows[i][a] for a in range(k)) for i in range(n)]
    ybar = sum(y) / n
    ss_res = sum((y[i] - pred[i]) ** 2 for i in range(n))
    ss_tot = sum((v - ybar) ** 2 for v in y) or 1.0
    r2 = 1 - ss_res / ss_tot
    b0, b1, b2, b3 = coef

    span = (dates[-1] - d0).days + 1
    scale = 365.0 / span
    hdd_sum = sum(r[1] for r in rows)
    wknd_sum = sum(r[2] for r in rows)
    trend_sum = sum(r[3] for r in rows)
    heating = max(0.0, b1 * hdd_sum) * scale
    base = (b0 * n + b2 * wknd_sum + b3 * trend_sum) * scale
    total = sum(y) * scale
    other = total - heating - base                       # residual attribution
    return {
        "r2": r2, "per_hdd": b1, "n": n,
        "annual_total": total, "heating_kwh": heating,
        "base_kwh": max(0.0, base + other),              # fold residual into base
        "heating_share": heating / total if total else 0,
    }
