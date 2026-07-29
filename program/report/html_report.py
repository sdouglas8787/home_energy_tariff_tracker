"""Render a self-contained, executive-grade HTML dashboard from the analysis.

No external assets — inline CSS/SVG only, so it opens in any browser and can be
shared as a single file. Theme-aware (light/dark) with a manual toggle.
"""
from __future__ import annotations
from statistics import pstdev
from model.calculations import MONTHS, _weighted_avgday

# Series (CVD-safe blue/orange) + semantic accents. Values are theme tokens in CSS.
ELEC = "var(--elec)"
GAS = "var(--gas)"


def _mlab(d):
    return f"{MONTHS[d.month]} {d.year % 100:02d}"


def _money(v, dp=0):
    return f"£{v:,.{dp}f}"


# ----------------------------- small SVG helpers -----------------------------
def _line(points):
    return "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points)


def _time_axis(months, sx, H):
    """Two-tier x-axis: month abbreviations, with the year as a band beneath."""
    parts = []
    n = len(months)
    for i, m in enumerate(months):
        parts.append(f'<text x="{sx(i):.1f}" y="{H - 22:.1f}" class="xtick">{MONTHS[m.month]}</text>')
    i = 0
    while i < n:
        j = i
        while j + 1 < n and months[j + 1].year == months[i].year:
            j += 1
        xc = (sx(i) + sx(j)) / 2
        parts.append(f'<text x="{xc:.1f}" y="{H - 5:.1f}" class="yearlab">{months[i].year}</text>')
        if i > 0:
            xd = (sx(i - 1) + sx(i)) / 2
            parts.append(f'<line x1="{xd:.1f}" y1="{H - 34:.1f}" x2="{xd:.1f}" y2="{H - 14:.1f}" class="yeardiv"/>')
        i = j + 1
    return "".join(parts)


def _tracking_svg(hist, fwd, color):
    """Actual vs forecast line, 95% forward cone, 'today' divider."""
    W, H = 900, 250
    ml, mr, mt, mb = 44, 14, 16, 42
    x0, x1, y0, y1 = ml, W - mr, mt, H - mb
    months = [p["month"] for p in hist] + [p["month"] for p in fwd]
    n = len(months)
    if n < 2:
        return f'<svg viewBox="0 0 {W} {H}" class="chart"></svg>'
    vals = [p["actual"] for p in hist] + [p["forecast"] for p in hist] \
        + [p["forecast"] for p in fwd] + [p["hi"] for p in fwd]
    vmax = max(vals) * 1.1 or 1
    vmin = 0

    def sx(i):
        return x0 + (x1 - x0) * i / (n - 1)

    def sy(v):
        return y1 - (y1 - y0) * (v - vmin) / (vmax - vmin)

    parts = []
    # y gridlines
    for t in range(5):
        v = vmax * t / 4
        y = sy(v)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{x0 - 6:.1f}" y="{y + 3:.1f}" class="ytick">{v:.0f}</text>')
    parts.append(_time_axis(months, sx, H))
    hist_n = len(hist)
    # forward 95% band (cone)
    if fwd:
        top = [(sx(hist_n + j), sy(p["hi"])) for j, p in enumerate(fwd)]
        bot = [(sx(hist_n + j), sy(p["lo"])) for j, p in enumerate(fwd)]
        # anchor cone to last actual
        anchor = (sx(hist_n - 1), sy(hist[-1]["actual"]))
        band = [anchor] + top + list(reversed(bot)) + [anchor]
        parts.append(f'<path d="{_line(band)} Z" class="band"/>')
        divx = (sx(hist_n - 1) + sx(hist_n)) / 2
        parts.append(f'<line x1="{divx:.1f}" y1="{y0}" x2="{divx:.1f}" y2="{y1}" class="today"/>')
        parts.append(f'<text x="{divx + 4:.1f}" y="{y0 + 10}" class="todaylab">forecast →</text>')
    # forecast line (dashed) across all
    fc_pts = [(sx(i), sy(p["forecast"])) for i, p in enumerate(hist + fwd)]
    parts.append(f'<path d="{_line(fc_pts)}" class="fc" style="stroke:{color}"/>')
    # actual line (solid) + markers
    ac_pts = [(sx(i), sy(p["actual"])) for i, p in enumerate(hist)]
    parts.append(f'<path d="{_line(ac_pts)}" class="ac" style="stroke:{color}"/>')
    for (x, y), p in zip(ac_pts, hist):
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" style="fill:{color}">'
                     f'<title>{_mlab(p["month"])} — actual {p["actual"]:.1f}, forecast {p["forecast"]:.1f} '
                     f'kWh/day ({p["error_pct"] * 100:+.0f}%)</title></circle>')
    return f'<svg viewBox="0 0 {W} {H}" class="chart">{"".join(parts)}</svg>'


def _residual_svg(hist, color_pos, color_neg):
    W, H = 620, 84
    ml, mr, mt, mb = 44, 14, 8, 8
    x0, x1, y0, y1 = ml, W - mr, mt, H - mb
    n = len(hist)
    if n < 1:
        return ""
    mx = max((abs(p["error_pct"]) for p in hist), default=0.1) or 0.1
    mid = (y0 + y1) / 2
    bw = (x1 - x0) / n * 0.5

    def cx(i):
        return x0 + (x1 - x0) * (i + 0.5) / n

    parts = [f'<line x1="{x0}" y1="{mid:.1f}" x2="{x1}" y2="{mid:.1f}" class="grid"/>']
    for i, p in enumerate(hist):
        e = p["error_pct"]
        h = (mid - y0) * abs(e) / mx
        y = mid - h if e >= 0 else mid
        col = color_neg if e > 0 else color_pos   # over-forecast (actual>fc) is +; under is -
        parts.append(f'<rect x="{cx(i) - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" '
                     f'height="{h:.1f}" rx="1.5" style="fill:{col}"/>')
        parts.append(f'<text x="{cx(i):.1f}" y="{(y - 3) if e >= 0 else (y + h + 10):.1f}" '
                     f'class="rlab">{e * 100:+.0f}%</text>')
    return f'<svg viewBox="0 0 {W} {H}" class="chart resid">{"".join(parts)}</svg>'


def _seasonality_svg(es, gs):
    W, H = 640, 250
    ml, mr, mt, mb = 40, 14, 16, 26
    x0, x1, y0, y1 = ml, W - mr, mt, H - mb
    xs = list(range(1, 13))
    vmax = max([es.get(m, 0) for m in xs] + [gs.get(m, 0) for m in xs] + [1]) * 1.1

    def sx(i):
        return x0 + (x1 - x0) * i / 11

    def sy(v):
        return y1 - (y1 - y0) * v / vmax

    parts = []
    for t in range(5):
        v = vmax * t / 4
        y = sy(v)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{x0 - 6:.1f}" y="{y + 3:.1f}" class="ytick">{v:.0f}</text>')
    for i, m in enumerate(xs):
        parts.append(f'<text x="{sx(i):.1f}" y="{H - 8}" class="xtick">{MONTHS[m]}</text>')
    for series, col in ((gs, "var(--gas)"), (es, "var(--elec)")):
        pts = [(sx(i), sy(series.get(m, 0))) for i, m in enumerate(xs)]
        area = pts + [(sx(11), y1), (sx(0), y1)]
        parts.append(f'<path d="{_line(area)} Z" class="area" style="fill:{col}"/>')
        parts.append(f'<path d="{_line(pts)}" class="sl" style="stroke:{col}"/>')
    return f'<svg viewBox="0 0 {W} {H}" class="chart">{"".join(parts)}</svg>'


def _by_year_avgday(monthly, idx):
    d = {}
    for r in monthly:
        if r[3] >= 20:
            d.setdefault(r[0].year, {})[r[0].month] = r[idx] / r[3]
    return d


def _by_year_index(monthly, idx):
    """Each year's monthly avg/day indexed to 100 at that year's first month."""
    base = _by_year_avgday(monthly, idx)
    out = {}
    for yr, ms in base.items():
        first = ms[min(ms)]
        if first:
            out[yr] = {m: v / first * 100 for m, v in ms.items()}
    return out


def _by_year_cost(bills):
    d = {}
    for dt, amt in bills:
        d.setdefault(dt.year, {})[dt.month] = amt
    return d


def _yoy_overlay_svg(by_year, decimals=1):
    """Jan–Dec x-axis, one line per calendar year (recent years drawn darker)."""
    W, H, ml, mr, mt, mb = 900, 260, 48, 86, 16, 30
    x0, x1, y0, y1 = ml, W - mr, mt, H - mb
    years = sorted(by_year)
    vals = [v for y in years for v in by_year[y].values()]
    if not vals:
        return f'<svg viewBox="0 0 {W} {H}" class="chart"></svg>'
    vmax = max(vals) * 1.1 or 1

    def sx(m):
        return x0 + (x1 - x0) * (m - 1) / 11

    def sy(v):
        return y1 - (y1 - y0) * v / vmax

    ramp = ["#c3cbd4", "#93b0cf", "#5a8fbf", "#2e6fb0", "#1f3864"]
    parts = []
    for t in range(5):
        v = vmax * t / 4
        y = sy(v)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{x0 - 6:.1f}" y="{y + 3:.1f}" class="ytick">{v:,.0f}</text>')
    for m in range(1, 13):
        parts.append(f'<text x="{sx(m):.1f}" y="{H - 8}" class="xtick">{MONTHS[m]}</text>')
    n = len(years)
    for i, yr in enumerate(years):
        col = ramp[-1] if n <= 1 else ramp[min(len(ramp) - 1, round(i / (n - 1) * (len(ramp) - 1)))]
        ms = sorted(by_year[yr])
        pts = [(sx(m), sy(by_year[yr][m])) for m in ms]
        parts.append(f'<path class="sl" style="stroke:{col}" d="{_line(pts)}"/>')
        for m in ms:
            parts.append(f'<circle cx="{sx(m):.1f}" cy="{sy(by_year[yr][m]):.1f}" r="2.5" style="fill:{col}">'
                         f'<title>{MONTHS[m]} {yr}: {by_year[yr][m]:,.{decimals}f}</title></circle>')
        ly = y0 + 14 + i * 16
        parts.append(f'<line x1="{x1 + 12}" y1="{ly}" x2="{x1 + 28}" y2="{ly}" style="stroke:{col};stroke-width:2.4"/>')
        parts.append(f'<text x="{x1 + 32}" y="{ly + 3}" class="xtick" style="text-anchor:start">{yr}</text>')
    return f'<svg viewBox="0 0 {W} {H}" class="chart">{"".join(parts)}</svg>'


def _season_from_monthly(sub):
    from collections import defaultdict
    ebm, gbm = defaultdict(list), defaultdict(list)
    for row in sub:
        if row[3] >= 20:
            ebm[row[0].month].append(row[1] / row[3])
            gbm[row[0].month].append(row[2] / row[3])
    es = {m: sum(v) / len(v) for m, v in ebm.items()}
    gs = {m: sum(v) / len(v) for m, v in gbm.items()}
    return es, gs


def _monthly_line_svg(sub, idx, color):
    W, H = 960, 210
    ml, mr, mt, mb = 46, 14, 14, 42
    x0, x1, y0, y1 = ml, W - mr, mt, H - mb
    n = len(sub)
    if n < 1:
        return f'<svg viewBox="0 0 {W} {H}" class="chart"></svg>'
    vals = [row[idx] for row in sub]
    vmax = (max(vals) or 1) * 1.1

    def sx(i):
        return (x0 + x1) / 2 if n == 1 else x0 + (x1 - x0) * i / (n - 1)

    def sy(v):
        return y1 - (y1 - y0) * v / vmax

    parts = []
    for t in range(5):
        v = vmax * t / 4
        y = sy(v)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{x0 - 6:.1f}" y="{y + 3:.1f}" class="ytick">{v:.0f}</text>')
    parts.append(_time_axis([row[0] for row in sub], sx, H))
    pts = [(sx(i), sy(v)) for i, v in enumerate(vals)]
    parts.append(f'<path d="{_line(pts)}" class="sl" style="stroke:{color}"/>')
    for i, (x, y) in enumerate(pts):
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" style="fill:{color}">'
                     f'<title>{_mlab(sub[i][0])}: {vals[i]:,.0f} kWh</title></circle>')
    return f'<svg viewBox="0 0 {W} {H}" class="chart">{"".join(parts)}</svg>'


def _key_numbers(sub, rates):
    """Side-by-side Metric | Electricity | Gas for the selected window."""
    e = sum(r[1] for r in sub)
    g = sum(r[2] for r in sub)
    days = sum(r[3] for r in sub) or 1
    eu, esc, gu, gsc = rates if rates else (0, 0, 0, 0)
    e_cost = e * eu / 100 + days * esc / 100
    g_cost = g * gu / 100 + days * gsc / 100
    e_stand, g_stand = days * esc / 100, days * gsc / 100
    metrics = [
        ("Used", f"{e:,.0f} kWh", f"{g:,.0f} kWh"),
        ("Per day", f"{e / days:.1f} kWh", f"{g / days:.1f} kWh"),
        ("Cost (current tariff)", _money(e_cost), _money(g_cost)),
        ("— standing charge", f"{_money(e_stand)} ({(e_stand / e_cost if e_cost else 0):.0%})",
         f"{_money(g_stand)} ({(g_stand / g_cost if g_cost else 0):.0%})"),
    ]
    head = '<tr><th></th><th>Electricity</th><th>Gas</th></tr>'
    body = "".join(f'<tr><td>{m}</td><td class="num">{ev}</td><td class="num">{gv}</td></tr>'
                   for m, ev, gv in metrics)
    return f'<thead>{head}</thead><tbody>{body}</tbody>'


def _highlights_from_monthly(sub):
    months = [(row[0], row[1] / row[3], row[2] / row[3]) for row in sub if row[3] >= 20]
    if not months:
        return '<tr><td>Lightest month</td><td>—</td><td>—</td></tr>'

    def f(mn, v):
        return f"{_mlab(mn)} ({v:.0f}/day)"

    eb, ew = min(months, key=lambda x: x[1]), max(months, key=lambda x: x[1])
    gb, gw = min(months, key=lambda x: x[2]), max(months, key=lambda x: x[2])
    return (f'<tr><td>Lightest month</td><td>{f(eb[0], eb[1])}</td><td>{f(gb[0], gb[2])}</td></tr>'
            f'<tr><td>Heaviest month</td><td>{f(ew[0], ew[1])}</td><td>{f(gw[0], gw[2])}</td></tr>')


def _trend_span(yoy):
    """Coloured trend chip: down = green (using less), up = red, flat = neutral."""
    if not yoy:
        return '<b>—</b>'
    a = {"up": "▲", "down": "▼", "flat": "▬"}[yoy["direction"]]
    col = {"up": "var(--neg)", "down": "var(--pos)", "flat": "var(--text)"}[yoy["direction"]]
    return f'<b style="color:{col}">{a} {abs(yoy["pct"]) * 100:.0f}%</b>'


_SEASONS = [("Winter", (12, 1, 2), "Dec–Feb", 90), ("Spring", (3, 4, 5), "Mar–May", 92),
            ("Summer", (6, 7, 8), "Jun–Aug", 92), ("Autumn", (9, 10, 11), "Sep–Nov", 91)]


def _season_yoy_card(monthly, rates, corr):
    """By season (3 months, £ for the whole season) with a forecast for next season."""
    from collections import defaultdict
    model = {1: {m: v * corr[1] for m, v in _weighted_avgday(monthly, 1).items()},
             2: {m: v * corr[2] for m, v in _weighted_avgday(monthly, 2).items()}}

    def season_profile(idx):
        agg = defaultdict(list)
        for r in monthly:
            if r[3] < 20:
                continue
            for sname, months, _lab, _d in _SEASONS:
                if r[0].month in months:
                    sy = r[0].year + 1 if r[0].month == 12 else r[0].year   # Dec → next winter
                    agg[(sname, sy)].append(r[idx] / r[3])
                    break
        return {k: sum(v) / len(v) for k, v in agg.items()}

    sp = {1: season_profile(1), 2: season_profile(2)}

    def fuel_cell(idx, sname, months, days, rate):
        s = sp[idx]
        syrs = sorted({sy for (nm, sy) in s if nm == sname})
        if not syrs:
            return "—"
        cur = s[(sname, max(syrs))]
        # historical: latest season vs the one a year before
        if (sname, max(syrs) - 1) in s and s[(sname, max(syrs) - 1)]:
            prev = s[(sname, max(syrs) - 1)]
            pct = (cur - prev) / prev
            y = {"pct": pct, "direction": "up" if pct > 0.02 else "down" if pct < -0.02 else "flat"}
            dcost = (cur - prev) * days * rate / 100
            mcol = "var(--pos)" if dcost < -0.5 else "var(--neg)" if dcost > 0.5 else "var(--muted)"
            money = ("−" + _money(abs(dcost)) if dcost < 0 else "+" + _money(dcost))
            hist = f'{_trend_span(y)} <span style="color:{mcol};font-size:12px">{money}</span>'
        else:
            hist = '<span class="tsub">— no prior year —</span>'
        # forecast: model's expected cost for the coming season, and change vs this year
        avail = [model[idx][m] for m in months if m in model[idx]]
        fcline = ""
        if avail:
            fc_ad = sum(avail) / len(avail)
            fc_cost = fc_ad * days * rate / 100
            chg = fc_ad / cur - 1 if cur else 0
            fy = {"pct": chg, "direction": "up" if chg > 0.02 else "down" if chg < -0.02 else "flat"}
            fcline = f'<div class="tsub">forecast next: £{fc_cost:,.0f} {_trend_span(fy)}</div>'
        return f'{hist}{fcline}'

    rows = []
    for sname, months, lab, days in _SEASONS:
        rows.append(f'<tr><td><b>{sname}</b><span class="tsub"> ({lab})</span></td>'
                    f'<td class="num">{fuel_cell(1, sname, months, days, rates[0])}</td>'
                    f'<td class="num">{fuel_cell(2, sname, months, days, rates[2])}</td></tr>')
    return ('<div class="card"><h3>Trend by season <span class="hint">£ = whole 3-month season</span></h3>'
            '<p class="note">Top line: latest season vs the year before (arrow green = down, £ = saving on '
            'current rates, for the full season). Bottom line: the model\'s <b>forecast cost for the coming '
            'season</b> and how it compares with this year.</p>'
            '<table><thead><tr><th>Season</th><th>Electricity</th><th>Gas</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def _win_trend(sub, monthly_full, idx):
    """Windowed year-on-year, comparing the window's months with the same months a
    year earlier. Partial months are completed with the model (month-to-date actual
    + forecast for the remaining days) so an incomplete current month is comparable."""
    from calendar import monthrange
    prof = _weighted_avgday(monthly_full, idx)
    totmap = {}
    for r in monthly_full:
        y, m, d = r[0].year, r[0].month, r[3]
        cal = monthrange(y, m)[1]
        if d >= 25:
            totmap[(y, m)] = r[idx]
        elif prof.get(m):                               # complete a partial month
            totmap[(y, m)] = r[idx] + prof[m] * max(0, cal - d)
    errs = []
    for r in sub:
        cur = totmap.get((r[0].year, r[0].month))
        py = totmap.get((r[0].year - 1, r[0].month))
        if cur and py and py > 0:
            errs.append((cur - py) / py)
    if not errs:
        return None
    pct = sum(errs) / len(errs)
    return {"pct": pct, "direction": "up" if pct > 0.02 else "down" if pct < -0.02 else "flat"}


def _combined_svg(sub, monthly_full, fwd_pts, idx, color, show_forecast, corr=1.0):
    """Monthly usage (actual) with an optional forecast overlay, 95% cone and an
    aligned model-error strip. `show_forecast` picks the tight or extended variant."""
    from calendar import monthrange
    totmap = {(r[0].year, r[0].month): r[idx] for r in monthly_full}
    daymap = {(r[0].year, r[0].month): r[3] for r in monthly_full}
    hist_months = [r[0] for r in sub]
    actual = [r[idx] for r in sub]
    days = [r[3] for r in sub]
    full = [i for i in range(len(sub)) if days[i] >= 25]     # complete months only
    fwd_months = [p["month"] for p in fwd_pts] if show_forecast else []
    all_m = hist_months + fwd_months
    n = len(all_m)
    W, ml, mr, mt = 960, 48, 14, 14
    x0, x1 = ml, W - mr
    if show_forecast:
        H, y0, y1, rtop, rbot = 300, 16, 168, 192, 248
        rmid = (rtop + rbot) / 2
    else:
        H, y0, y1 = 210, 14, 172
    if n < 2:
        return f'<svg viewBox="0 0 {W} {H}" class="chart"></svg>'

    def sx(i):
        return x0 + (x1 - x0) * i / (n - 1)

    prof = _weighted_avgday(monthly_full, idx)               # the model's seasonal profile
    pymap = {(r[0].year, r[0].month): r[idx] for r in monthly_full if r[3] >= 25}
    fc = [None] * n
    for i, mo in enumerate(all_m):
        if i >= len(hist_months):
            fc[i] = fwd_pts[i - len(hist_months)]["forecast"] * monthrange(mo.year, mo.month)[1]
        elif prof.get(mo.month):
            # bias-corrected model forecast. For a full month, match its covered days (fair error);
            # for the partial current month, use the FULL calendar month so the forecast shows where
            # the month is heading (the actual stays as month-to-date).
            covered = daymap.get((mo.year, mo.month))
            cal = monthrange(mo.year, mo.month)[1]
            d = cal if (covered is None or covered < 25) else covered
            fc[i] = prof[mo.month] * d * corr
    band = []
    if show_forecast:
        for j, mo in enumerate(fwd_months):
            dm = monthrange(mo.year, mo.month)[1]
            band.append((len(hist_months) + j, fwd_pts[j]["lo"] * dm, fwd_pts[j]["hi"] * dm))
    # when forecast is shown, complete the part-month = actual-so-far + forecast for the remaining days
    plot_actual = list(actual)
    completed_i = None
    if show_forecast:
        for i in range(len(hist_months)):
            if i not in full and prof.get(hist_months[i].month):
                mo = hist_months[i]
                rem = max(0, monthrange(mo.year, mo.month)[1] - days[i])
                plot_actual[i] = actual[i] + prof[mo.month] * corr * rem
                completed_i = i
    vmax = max(plot_actual + [v for v in fc if v] + [hi for _, _, hi in band] + [1]) * 1.1

    def sy(v):
        return y1 - (y1 - y0) * v / vmax

    parts = []
    for t in range(5):
        v = vmax * t / 4
        y = sy(v)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{x0 - 6:.1f}" y="{y + 3:.1f}" class="ytick">{v:.0f}</text>')
    parts.append(_time_axis(all_m, sx, H))
    if show_forecast and band:
        top = [(sx(i), sy(hi)) for i, lo, hi in band]
        bot = [(sx(i), sy(lo)) for i, lo, hi in band]
        anchor = (sx(len(hist_months) - 1), sy(actual[-1]))
        parts.append(f'<path class="band" d="{_line([anchor] + top + list(reversed(bot)) + [anchor])} Z"/>')
        divx = (sx(len(hist_months) - 1) + sx(len(hist_months))) / 2
        parts.append(f'<line class="today" x1="{divx:.1f}" y1="{y0}" x2="{divx:.1f}" y2="{y1}"/>')
        parts.append(f'<text class="todaylab" x="{divx + 4:.1f}" y="{y0 + 10}">forecast →</text>')
        # projected % movement: next 12 months forecast vs the trailing 12 full months
        fwd_total = sum(fwd_pts[j]["forecast"] * monthrange(mo.year, mo.month)[1]
                        for j, mo in enumerate(fwd_months))
        trail_rows = [r for r in sorted(monthly_full, key=lambda r: r[0]) if r[3] >= 25][-12:]
        trail = sum(r[idx] for r in trail_rows)
        if trail > 0:
            fp = fwd_total / trail - 1
            a = "▲" if fp > 0.02 else "▼" if fp < -0.02 else "▬"
            fcol = "var(--neg)" if fp > 0.02 else "var(--pos)" if fp < -0.02 else "var(--muted)"
            lx = sx(len(hist_months) + max(0, len(fwd_months) - 1) / 2)
            parts.append(f'<text x="{lx:.1f}" y="{y0 + 24:.1f}" style="fill:{fcol};font-size:13px;'
                         f'font-weight:700;text-anchor:middle">next 12 months {a} {abs(fp) * 100:.0f}%</text>')
    if show_forecast:
        fcpts = [(sx(i), sy(fc[i])) for i in range(n) if fc[i] is not None]
        if len(fcpts) > 1:
            parts.append(f'<path class="fc" style="stroke:{color}" d="{_line(fcpts)}"/>')
        for i in range(n):                                   # forecast markers + tooltips
            if fc[i] is None:
                continue
            mo = all_m[i]
            tip = f'{_mlab(mo)} — forecast\n{fc[i]:,.0f} kWh'
            py = pymap.get((mo.year - 1, mo.month))
            if py:
                tip += f'\nvs last year {py:,.0f} kWh ({(fc[i] - py) / py * 100:+.0f}%)'
            parts.append(f'<circle cx="{sx(i):.1f}" cy="{sy(fc[i]):.1f}" r="2.6" class="fcm" style="stroke:{color}">'
                         f'<title>{tip}</title></circle>')
    # actual line through COMPLETE months only (so a partial current month doesn't dip the line)
    line_idx = sorted(set(full + ([completed_i] if completed_i is not None else [])))
    acpts = [(sx(i), sy(plot_actual[i])) for i in line_idx]
    if len(acpts) > 1:
        parts.append(f'<path class="ac" style="stroke:{color}" d="{_line(acpts)}"/>')
    for i in range(len(hist_months)):
        x, y = sx(i), sy(plot_actual[i])
        partial = i not in full
        if i == completed_i:                          # part-month completed with forecast
            tt = (f'{_mlab(hist_months[i])}: {plot_actual[i]:,.0f} kWh full-month estimate '
                  f'({actual[i]:,.0f} so far + forecast for the rest)')
            style = f'fill:{color}'
        elif partial:
            tt = f'{_mlab(hist_months[i])}: {actual[i]:,.0f} kWh (partial, {days[i]} days)'
            style = f'fill:none;stroke:{color};stroke-width:1.5'
        else:
            tt = f'{_mlab(hist_months[i])}: {actual[i]:,.0f} kWh'
            if fc[i]:
                tt += f'\nforecast: {fc[i]:,.0f} kWh (err {(actual[i] - fc[i]) / fc[i] * 100:+.0f}%)'
            py = pymap.get((hist_months[i].year - 1, hist_months[i].month))
            if py:
                tt += f'\nlast year: {py:,.0f} kWh ({(actual[i] - py) / py * 100:+.0f}%)'
            style = f'fill:{color}'
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" style="{style}"><title>{tt}</title></circle>')
    if show_forecast:
        res = [(i, (actual[i] - fc[i]) / fc[i]) for i in full if fc[i]]   # skip partial months
        if res:
            rmax = max(abs(e) for _, e in res) or 0.1
            parts.append(f'<line x1="{x0}" y1="{rmid:.1f}" x2="{x1}" y2="{rmid:.1f}" class="grid"/>')
            parts.append(f'<text x="{x0}" y="{rtop - 3:.1f}" class="rlab" style="text-anchor:start">model error (actual vs forecast)</text>')
            bw = (x1 - x0) / n * 0.5
            for i, e in res:
                h = (rmid - rtop) * abs(e) / rmax
                y = rmid - h if e < 0 else rmid
                col = "var(--pos)" if e < 0 else "var(--neg)"
                parts.append(f'<rect x="{sx(i) - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="1.5" '
                             f'style="fill:{col}"><title>{_mlab(hist_months[i])}: {e * 100:+.0f}% vs forecast</title></rect>')
    return f'<svg viewBox="0 0 {W} {H}" class="chart">{"".join(parts)}</svg>'


def _kpi(label, value, sub="", cls="", big=False):
    return (f'<div class="tile {cls}{" span2" if big else ""}">'
            f'<div class="klabel">{label}</div>'
            f'<div class="kvalue{" hero" if big else ""}">{value}</div>'
            f'<div class="ksub">{sub}</div></div>')


def _bias_chip(bt):
    if not bt or bt.get("bias") is None:
        return '<span class="chip">no history</span>'
    b = bt["bias"] * 100
    if abs(b) < 3:
        return f'<span class="chip flat">on target ({b:+.0f}%)</span>'
    word = "over-forecasting" if b < 0 else "under-forecasting"
    cls = "pos" if b < 0 else "neg"
    return f'<span class="chip {cls}">{word} ({b:+.0f}%)</span>'


def _reliability(bt):
    pts = bt.get("points", []) if bt else []
    if not pts:
        return "—"
    errs = [p["error_pct"] for p in pts]
    sigma = pstdev(errs) if len(errs) >= 2 else (bt.get("mape") or 0.15)
    within = sum(1 for e in errs if abs(e) <= 1.96 * sigma)
    return f"{within}/{len(pts)} months in band"


def _temp_line_svg(weather, monthly):
    """Monthly mean temperature line over the data period."""
    keys = [(r[0].year, r[0].month, r[0]) for r in monthly if (r[0].year, r[0].month) in weather]
    if len(keys) < 2:
        return '<svg viewBox="0 0 960 200" class="chart"></svg>'
    W, H, ml, mr, mt, mb = 960, 200, 46, 14, 14, 42
    x0, x1, y0, y1 = ml, W - mr, mt, H - mb
    temps = [weather[(y, m)]["temp"] for y, m, _ in keys]
    vmin, vmax = min(temps) - 2, max(temps) + 2
    n = len(keys)

    def sx(i):
        return x0 + (x1 - x0) * i / (n - 1)

    def sy(v):
        return y1 - (y1 - y0) * (v - vmin) / (vmax - vmin)

    parts = []
    for t in range(5):
        v = vmin + (vmax - vmin) * t / 4
        y = sy(v)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{x0 - 6:.1f}" y="{y + 3:.1f}" class="ytick">{v:.0f}°</text>')
    parts.append(_time_axis([k[2] for k in keys], sx, H))
    pts = [(sx(i), sy(temps[i])) for i in range(n)]
    parts.append(f'<path class="sl" style="stroke:#7c9aad" d="{_line(pts)}"/>')
    for i, (x, y) in enumerate(pts):
        yy, mm, _ = keys[i]
        w = weather[(yy, mm)]
        tip = (f'{MONTHS[mm]} {yy}\nmean {w["temp"]:.1f}°C\nhigh {w.get("tmax", 0):.0f}°C\n'
               f'low {w.get("tmin", 0):.0f}°C\nrain {w.get("rain", 0):.0f} mm\nheating-degree-days {w["hdd"]:.0f}')
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" style="fill:#7c9aad"><title>{tip}</title></circle>')
    return f'<svg viewBox="0 0 {W} {H}" class="chart">{"".join(parts)}</svg>'


def _weather_overlay_svg(weather, monthly):
    """Rainfall (light-blue columns), gas & electricity (kWh/day, left axis) and
    temperature (°C, right axis) on a shared month axis."""
    keys = [(r[0].year, r[0].month, r[0], r[2] / r[3], r[1] / r[3]) for r in monthly
            if r[3] >= 20 and (r[0].year, r[0].month) in weather]
    if len(keys) < 2:
        return '<svg viewBox="0 0 900 230" class="chart"></svg>'
    W, H, ml, mr, mt, mb = 900, 230, 48, 52, 16, 42
    x0, x1, y0, y1 = ml, W - mr, mt, H - mb
    temps = [weather[(y, m)]["temp"] for y, m, _, _, _ in keys]
    gas = [g for _, _, _, g, _ in keys]
    elec = [e for _, _, _, _, e in keys]
    rain = [weather[(y, m)].get("rain", 0) or 0 for y, m, _, _, _ in keys]
    tmin, tmax = min(temps) - 2, max(temps) + 2
    umax = max(gas + elec) * 1.1 or 1                        # shared kWh/day scale
    rmax = max(rain) or 1
    n = len(keys)

    def sx(i):
        return x0 + (x1 - x0) * i / (n - 1)

    def syu(v):
        return y1 - (y1 - y0) * v / umax

    def syt(v):
        return y1 - (y1 - y0) * (v - tmin) / (tmax - tmin)

    parts = []
    # rainfall columns first (background, light blue, scaled to lower half so it doesn't dominate)
    bw = (x1 - x0) / n * 0.55
    for i in range(n):
        h = (y1 - y0) * 0.45 * rain[i] / rmax
        parts.append(f'<rect x="{sx(i) - bw / 2:.1f}" y="{y1 - h:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                     f'rx="1.5" style="fill:#cfe3f5;opacity:.7"><title>{_mlab(keys[i][2])}: {rain[i]:.0f} mm rain</title></rect>')
    for t in range(5):
        uv = umax * t / 4
        y = syu(uv)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{x0 - 6:.1f}" y="{y + 3:.1f}" class="ytick">{uv:.0f}</text>')
        tv = tmin + (tmax - tmin) * t / 4
        parts.append(f'<text x="{x1 + 6:.1f}" y="{syt(tv) + 3:.1f}" class="ytick" style="text-anchor:start;fill:var(--muted)">{tv:.0f}°</text>')
    parts.append(_time_axis([k[2] for k in keys], sx, H))
    # temperature (grey dashed, right axis)
    tp = [(sx(i), syt(temps[i])) for i in range(n)]
    parts.append(f'<path class="sl" style="stroke:#8aa0b2;stroke-dasharray:4 3" d="{_line(tp)}"/>')
    for i in range(n):
        parts.append(f'<circle cx="{tp[i][0]:.1f}" cy="{tp[i][1]:.1f}" r="2.4" style="fill:#8aa0b2">'
                     f'<title>{_mlab(keys[i][2])}: {temps[i]:.1f}°C, {weather[(keys[i][0], keys[i][1])]["hdd"]:.0f} HDD</title></circle>')
    # usage lines (toggle-able): gas + electricity, shared left axis
    parts.append('<g class="wgas">')
    for series, col, name in ((gas, "var(--gas)", "gas"), (elec, "var(--elec)", "electricity")):
        pts = [(sx(i), syu(series[i])) for i in range(n)]
        parts.append(f'<path class="sl" style="stroke:{col}" d="{_line(pts)}"/>')
        for i in range(n):
            parts.append(f'<circle cx="{pts[i][0]:.1f}" cy="{pts[i][1]:.1f}" r="2.6" style="fill:{col}">'
                         f'<title>{_mlab(keys[i][2])}: {series[i]:.1f} kWh/day {name}</title></circle>')
    parts.append('</g>')
    return f'<svg viewBox="0 0 {W} {H}" class="chart">{"".join(parts)}</svg>'


def _weather_card(weather, monthly, gi):
    if not weather:
        return ('<div class="card"><h3>Weather context</h3>'
                '<p class="note">Weather data unavailable (offline). It will load next time you run online.</p></div>')
    gmap = {(r[0].year, r[0].month): r[2] for r in monthly}
    kph = {(y, m): gmap[(y, m)] / w["hdd"] for (y, m), w in weather.items()
           if w["hdd"] > 30 and gmap.get((y, m))}
    pairs = [(kph[(y, m)] - kph[(y - 1, m)]) / kph[(y - 1, m)]
             for (y, m) in kph if (y - 1, m) in kph and kph[(y - 1, m)] > 0]
    norm = sum(pairs) / len(pairs) if pairs else None
    raw = gi["yoy"]["pct"] if gi["yoy"] else None
    if norm is not None and raw is not None:
        rw = f"{'down' if raw < 0 else 'up'} {abs(raw) * 100:.0f}%"
        nw = f"{'down' if norm < 0 else 'up'} {abs(norm) * 100:.0f}%"
        takeaway = (f"Raw gas use is <b>{rw}</b> year-on-year. Adjusted for how cold it actually was "
                    f"(per heating-degree-day), the underlying change is <b>{nw}</b> — "
                    + ("so most of the change is genuine, not just weather."
                       if abs(norm) >= abs(raw) * 0.6 else
                       "so a good part of the change was milder/colder weather, not behaviour."))
    else:
        takeaway = "Gas heating demand tracks temperature closely — colder months use far more gas."
    return (f'<div class="card" id="wxcard"><h3>Weather context '
            f'<span style="float:right"><button id="wxtoggle" class="rbtn on">Usage overlay: on</button></span></h3>'
            f'<div class="legend"><span><i style="border-color:var(--gas)"></i>gas</span>'
            f'<span><i style="border-color:var(--elec)"></i>electricity</span>'
            f'<span><i style="border-color:#8aa0b2"></i>temperature (°C, right)</span>'
            f'<span><i style="border-color:#cfe3f5;border-top-width:8px"></i>rainfall (mm)</span></div>'
            f'<p class="note">Usage (kWh/day, left) against temperature (right) and rainfall — '
            f'gas tracks the cold closely; electricity is far flatter. Hover for detail.</p>'
            f'{_weather_overlay_svg(weather, monthly)}'
            f'<p class="note" style="margin-top:8px">{takeaway}</p></div>')


def _mc_range_svg(stats):
    rows = stats[:7]
    if not rows:
        return ""
    W, rowh, ptop, pbot, labelw = 900, 32, 10, 30, 190
    x0, x1 = labelw, W - 24
    lo = min(s["p5"] for s in rows) * 0.985
    hi = max(s["p95"] for s in rows) * 1.015
    H = ptop + len(rows) * rowh + pbot

    def sx(v):
        return x0 + (x1 - x0) * (v - lo) / (hi - lo)

    parts = []
    for t in range(5):
        v = lo + (hi - lo) * t / 4
        x = sx(v)
        parts.append(f'<line x1="{x:.1f}" y1="{ptop}" x2="{x:.1f}" y2="{ptop + len(rows) * rowh:.1f}" class="grid"/>')
        parts.append(f'<text x="{x:.1f}" y="{H - 10}" class="xtick">£{v:,.0f}</text>')
    for i, s in enumerate(rows):
        y = ptop + i * rowh + rowh / 2
        col = "var(--gas)" if s["type"].lower() in ("tracker", "variable") else "var(--elec)"
        parts.append(f'<line x1="{sx(s["p5"]):.1f}" x2="{sx(s["p95"]):.1f}" y1="{y:.1f}" y2="{y:.1f}" '
                     f'style="stroke:{col};stroke-width:9;stroke-linecap:round;opacity:.3"/>')
        parts.append(f'<circle cx="{sx(s["p50"]):.1f}" cy="{y:.1f}" r="5" style="fill:{col}">'
                     f'<title>{s["supplier"]} — {s["type"]}\nmost likely £{s["p50"]:,.0f}\n'
                     f'90% range £{s["p5"]:,.0f}–£{s["p95"]:,.0f}</title></circle>')
        lab = s["supplier"] + (" ★" if s["is_current"] else "")
        parts.append(f'<text x="0" y="{y + 4:.1f}" class="xtick" style="text-anchor:start;fill:var(--text)">{lab}</text>')
        parts.append(f'<text x="{sx(s["p50"]):.1f}" y="{y - 9:.1f}" class="rlab">£{s["p50"]:,.0f}</text>')
    return f'<svg viewBox="0 0 {W} {H}" class="chart">{"".join(parts)}</svg>'


def _mc_card(mc):
    if not mc or not mc.get("tariffs"):
        return ""
    best = mc["tariffs"][0]
    prob = mc.get("prob_tracker_beats_current")
    head = (f'On <b>{best["supplier"]}</b> there\'s a 90% chance your annual cost lands '
            f'<b>{_money(best["p5"])}–{_money(best["p95"])}</b> (most likely {_money(best["p50"])}).')
    prob_line = ""
    if prob is not None:
        prob_line = (f' A tracker beats your current fixed tariff in <b>{prob * 100:.0f}%</b> of simulations — '
                     f'likely cheaper, but the wide orange ranges are the market risk.')
    return (f'<div class="card"><h3>Cost range &amp; risk <span class="hint">{mc["n"]:,} simulations</span></h3>'
            f'<p class="note">{head}{prob_line}</p>'
            f'<div class="legend"><span><i style="border-color:var(--elec)"></i>fixed (price-certain)</span>'
            f'<span><i style="border-color:var(--gas)"></i>tracker/variable (moves with market)</span></div>'
            f'{_mc_range_svg(mc["tariffs"])}'
            f'<p class="note">Bars = 90% range; dot = most likely. Usage varies per the model\'s own error; '
            f'tracker prices assume ±{mc["price_vol"] * 100:.0f}% market volatility.</p></div>')


def _cost_lines_svg(rows):
    """Four monthly cost lines (each toggle-able): usage & standing, per fuel."""
    W, H, ml, mr, mt, mb = 960, 250, 48, 150, 16, 42
    x0, x1, y0, y1 = ml, W - mr, mt, H - mb
    n = len(rows)
    if n < 2:
        return ""
    series = [("cl-tot", 8, "total", "#33415c"), ("cl-eu", 4, "electricity usage", "var(--elec)"),
              ("cl-gu", 6, "gas usage", "var(--gas)"), ("cl-es", 5, "electricity standing", "#7fb2e6"),
              ("cl-gs", 7, "gas standing", "#e0a866")]
    vmax = max(max(r[i] for _, i, _, _ in series) for r in rows) * 1.1 or 1

    def sx(k):
        return x0 + (x1 - x0) * k / (n - 1)

    def sy(v):
        return y1 - (y1 - y0) * v / vmax

    parts = []
    for t in range(5):
        v = vmax * t / 4
        y = sy(v)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{x0 - 6:.1f}" y="{y + 3:.1f}" class="ytick">£{v:.0f}</text>')
    parts.append(_time_axis([r[0] for r in rows], sx, H))
    for k, (cls, idx, name, col) in enumerate(series):
        pts = [(sx(j), sy(r[idx])) for j, r in enumerate(rows)]
        g = [f'<g class="{cls}"><path class="sl" style="stroke:{col}" d="{_line(pts)}"/>']
        for j, r in enumerate(rows):
            g.append(f'<circle cx="{pts[j][0]:.1f}" cy="{pts[j][1]:.1f}" r="2.3" style="fill:{col}">'
                     f'<title>{_mlab(r[0])} — {name}: {_money(r[idx])}</title></circle>')
        g.append('</g>')
        parts.append("".join(g))
        ly = y0 + 12 + k * 17
        parts.append(f'<rect x="{x1 + 12}" y="{ly - 8:.1f}" width="12" height="3" rx="1.5" style="fill:{col}"/>')
        parts.append(f'<text x="{x1 + 28}" y="{ly - 2:.1f}" class="xtick" style="text-anchor:start">{name}</text>')
    return f'<svg viewBox="0 0 {W} {H}" class="chart">{"".join(parts)}</svg>'


def _cost_pivot(rows, fc_rows, partial_fc_row, extract, is_money, partial_ym):
    """Year × month heat-map pivot. Actual months shaded (white text on dark cells),
    the part-month current cell marked *, forecast months toggle-able."""
    from collections import defaultdict
    grid, kind = defaultdict(dict), defaultdict(dict)     # kind: a=actual, p=part-month, f=forecast
    fullvals = []
    for r in rows:
        v = extract(r)
        grid[r[0].year][r[0].month] = v
        if (r[0].year, r[0].month) == partial_ym:
            kind[r[0].year][r[0].month] = "p"
        else:
            kind[r[0].year][r[0].month] = "a"
            fullvals.append(v)
    for r in fc_rows:
        if r[0].month not in grid[r[0].year]:
            grid[r[0].year][r[0].month] = extract(r)
            kind[r[0].year][r[0].month] = "f"
    vmax = max(fullvals) if fullvals else 1

    def fmt(v):
        return _money(v) if is_money else f"{v:,.0f}"

    agg_defs = [("q1", "Q1", [1, 2, 3]), ("q2", "Q2", [4, 5, 6]), ("q3", "Q3", [7, 8, 9]),
                ("q4", "Q4", [10, 11, 12]), ("h1", "H1", list(range(1, 7))),
                ("h2", "H2", list(range(7, 13))), ("year", "Year", list(range(1, 13)))]
    head = ("<tr><th></th>" + "".join(f"<th>{MONTHS[m]}</th>" for m in range(1, 13))
            + "".join(f'<th class="agg agg-{k}">{lab}</th>' for k, lab, _ in agg_defs) + "</tr>")
    p_completed = extract(partial_fc_row) if partial_fc_row is not None else None
    body = []
    for y in sorted(grid):
        cells = []
        for m in range(1, 13):
            if m not in grid[y]:
                cells.append('<td class="num" style="color:var(--border)">·</td>')
                continue
            v, k = grid[y][m], kind[y][m]
            if k == "f":
                cells.append(f'<td class="num fcell" title="{MONTHS[m]} {y}: forecast {fmt(v)}">'
                             f'<span class="fv">{fmt(v)}</span></td>')
            elif k == "p":
                # part-month: actual-so-far, or (forecast on) MTD + forecast for the rest of the month
                fv = fmt(p_completed) if p_completed is not None else ""
                cells.append(f'<td class="num pcell" title="{MONTHS[m]} {y}: {fmt(v)} so far; '
                             f'full-month estimate {fv}"><span class="av">{fmt(v)}*</span>'
                             f'<span class="fv">{fv}</span></td>')
            else:
                # shade by change vs the SAME month a year earlier (red = up, green = down),
                # so genuine spikes/savings show — not just the obvious winter peak
                prev = grid.get(y - 1, {}).get(m)
                pk = kind.get(y - 1, {}).get(m)
                if prev and prev > 0 and pk == "a":
                    pct = (v - prev) / prev
                    inten = 0.12 + 0.62 * min(1.0, abs(pct) / 0.4)
                    white = "color:#fff;" if inten > 0.5 else ""
                    if pct > 0.02:
                        bg = f"rgba(192,57,43,{inten:.2f});{white}"
                    elif pct < -0.02:
                        bg = f"rgba(46,138,87,{inten:.2f});{white}"
                    else:
                        bg = "transparent"
                    tip = f"{MONTHS[m]} {y}: {fmt(v)} ({pct * 100:+.0f}% vs {y - 1})"
                else:
                    bg, tip = "transparent", f"{MONTHS[m]} {y}: {fmt(v)} (no prior year)"
                cells.append(f'<td class="num" title="{tip}" style="background:{bg}">{fmt(v)}</td>')
        # aggregates: 'av' = actual (part-month = month-to-date); 'fvsum' = forecast-inclusive
        # (part-month completed + future forecast months) — shown when the forecast toggle is on
        mvals_a, mvals_all = {}, {}
        for m in grid[y]:
            k2 = kind[y][m]
            if k2 == "a":
                mvals_a[m] = grid[y][m]
                mvals_all[m] = grid[y][m]
            elif k2 == "p":
                mvals_a[m] = grid[y][m]
                if p_completed is not None:
                    mvals_all[m] = p_completed
            elif k2 == "f":
                mvals_all[m] = grid[y][m]

        def qs(d, ms):
            got = [d[m] for m in ms if m in d]
            return (sum(got), len(got)) if got else (None, 0)

        for k, _lab, ms in agg_defs:
            exp = len(ms)
            av, av_n = qs(mvals_a, ms)
            fvs, fv_n = qs(mvals_all, ms)

            def span(cls, val, cnt):
                if val is None:
                    return f'<span class="{cls}">·</span>'
                dagger = f'<span class="pmark">†</span>' if cnt < exp else ""
                return f'<span class="{cls}" title="{cnt} of {exp} months: {fmt(val)}">{fmt(val)}{dagger}</span>'

            cells.append(f'<td class="num agg agg-{k}">{span("av", av, av_n)}{span("fvsum", fvs, fv_n)}</td>')
        body.append(f'<tr><td><b>{y}</b></td>{"".join(cells)}</tr>')
    return f'<table class="pivot"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table>'


def _cost_tab(monthly, rates, forward):
    from calendar import monthrange
    eu, esc, gu, gsc = rates

    def make_row(m, e_kwh, g_kwh, days):
        euc, es = e_kwh * eu / 100, days * esc / 100
        guc, gs = g_kwh * gu / 100, days * gsc / 100
        return (m, days, e_kwh, g_kwh, euc, es, guc, gs, euc + es + guc + gs)

    rows = [make_row(m, e_kwh, g_kwh, days) for m, e_kwh, g_kwh, days in sorted(monthly, key=lambda r: r[0])]
    partial_ym = (rows[-1][0].year, rows[-1][0].month) if rows and rows[-1][1] < 25 else None
    line_rows = [r for r in rows if r[1] >= 25]              # drop the part-month so lines don't dip

    # forecast rows (future full months) from the bias-corrected forward projection
    fe = {p["month"]: p["forecast"] for p in forward.get("Electricity", [])}
    fg = {p["month"]: p["forecast"] for p in forward.get("Gas", [])}
    fc_rows = []
    for mo in sorted(set(fe) | set(fg)):
        days = monthrange(mo.year, mo.month)[1]
        fc_rows.append(make_row(mo, fe.get(mo, 0) * days, fg.get(mo, 0) * days, days))

    # nowcast for the part-month current month = actual-so-far + forecast for the remaining days
    def _avgday_for_month(fdict, month):
        for d, val in fdict.items():
            if d.month == month:
                return val
        return 0.0

    partial_fc_row = None
    if partial_ym:
        pr = rows[-1]
        cal = monthrange(pr[0].year, pr[0].month)[1]
        rem = max(0, cal - pr[1])
        e_full = pr[2] + _avgday_for_month(fe, pr[0].month) * rem
        g_full = pr[3] + _avgday_for_month(fg, pr[0].month) * rem
        partial_fc_row = make_row(pr[0], e_full, g_full, cal)

    # backcast: months before the first real reading (e.g. Jan–Sep 2024) via the seasonal model,
    # so early-year quarters/halves fill in when the forecast is shown
    if rows:
        from datetime import date as _date
        first = rows[0][0]
        for mm in range(1, first.month):
            days = monthrange(first.year, mm)[1]
            fc_rows.append(make_row(_date(first.year, mm, 1),
                                    _avgday_for_month(fe, mm) * days, _avgday_for_month(fg, mm) * days, days))

    full12 = [r for r in rows if r[1] >= 25][-12:]
    standing = sum(r[5] + r[7] for r in full12)
    total = sum(r[8] for r in full12)
    usage = total - standing
    spct = standing / total if total else 0

    metrics = [   # additive: electricity usage + gas usage + standing charge = total cost
        ("total", "Total cost", lambda r: r[8], True),
        ("eu", "Electricity usage", lambda r: r[4], True),
        ("gu", "Gas usage", lambda r: r[6], True),
        ("standing", "Standing charge", lambda r: r[5] + r[7], True),
        ("usage", "Usage (kWh)", lambda r: r[2] + r[3], False),
    ]
    pbtns, pviews = [], []
    for i, (k, lab, ext, money) in enumerate(metrics):
        onp = i == 0
        pbtns.append(f'<button class="rbtn{" on" if onp else ""}" data-p="{k}">{lab}</button>')
        pviews.append(f'<div class="pv{" active" if onp else ""}" data-p="{k}">'
                      f'<div style="overflow-x:auto">'
                      f'{_cost_pivot(rows, fc_rows, partial_fc_row, ext, money, partial_ym)}</div></div>')

    return (
        '<div class="headline">'
        f'Standing charges cost <b>{_money(standing)}/yr</b> — that\'s <b>{spct:.0%}</b> of your bill, '
        f'paid before you use any energy. Usage is the other <b>{_money(usage)}</b> ({1 - spct:.0%}).</div>'
        '<h3 class="sec">Monthly cost — usage vs standing charge</h3>'
        '<div class="card" id="costcard"><p class="note">On your current tariff rates (complete months only). '
        'Standing charge is a flat daily fee (nearly level lines); usage varies with the seasons. Toggle any line off:</p>'
        '<div class="ranges"><span class="rlabel">Show:</span>'
        '<button class="rbtn on" data-cl="tot">Total cost</button>'
        '<button class="rbtn on" data-cl="eu">Elec usage</button>'
        '<button class="rbtn on" data-cl="gu">Gas usage</button>'
        '<button class="rbtn on" data-cl="es">Elec standing</button>'
        '<button class="rbtn on" data-cl="gs">Gas standing</button></div>'
        f'{_cost_lines_svg(line_rows)}</div>'
        '<h3 class="sec">Spot spikes &amp; trends</h3>'
        '<div class="card nofc show-year" id="pivotcard"><p class="note">Years down, months across. Cells are '
        'shaded by <b>change vs the same month a year earlier</b> — <span style="color:#c0392b">red = higher</span>, '
        '<span style="color:#2e8a57">green = lower</span> — so real spikes/savings stand out, not the usual winter '
        'peak. <b>*</b> = part-month; <b style="color:#8257c9">forecasts (incl. backcast for 2024) show in purple</b>; '
        '<span class="pmark">†</span> = fewer months than usual. Electricity usage + Gas usage + Standing charge = Total.</p>'
        f'<div class="ranges"><span class="rlabel">Show:</span>{"".join(pbtns)}'
        '<span style="margin-left:auto;display:flex;gap:8px;align-items:center">'
        '<select id="aggpick" class="aggsel"><option value="year">Year</option>'
        '<option value="q1">Q1</option><option value="q2">Q2</option><option value="q3">Q3</option>'
        '<option value="q4">Q4</option><option value="h1">H1</option><option value="h2">H2</option>'
        '<option value="none">No summary</option></select>'
        '<button id="pvfc" class="rbtn">Add forecast</button></span></div>'
        f'{"".join(pviews)}</div>')


def _day_inspector(recent, days, typ):
    """Month -> week -> day picker. Data is embedded once and the chosen day is
    drawn client-side (solid) against its weekday-typical (dashed grey), so the
    whole history is browsable without pre-rendering hundreds of charts."""
    if not days:
        return ""
    import json
    day_js = {d.isoformat(): [round(v, 3) if v is not None else None for v in arr]
              for d, arr in sorted(days.items())}
    typ_js = {str(wd): [round(v, 3) for v in arr] for wd, arr in typ.items()}
    data = json.dumps(day_js, separators=(",", ":"))
    tdata = json.dumps(typ_js, separators=(",", ":"))
    script = _DAY_JS.replace("__DAYS__", data).replace("__TYP__", tdata)
    return (
        '<h3 class="sec">Inspect a day (test your changes)</h3>'
        '<div class="card" id="daycard"><p class="note">Pick a month, then a week, then a day to see that '
        'day\'s half-hourly electricity (solid) against the <span style="color:#8aa0b2">typical for that '
        'weekday</span> (dashed) &mdash; a Monday is compared to your average Monday, and so on. Switch '
        'something off and the solid line dips below the dashed one at that time, which is how you confirm '
        'the effect yourself.</p>'
        '<div class="ranges">'
        '<span class="rlabel">Month</span>'
        '<select id="m_month" class="aggsel" style="width:auto"></select>'
        '<span class="rlabel" style="margin-left:12px">Week</span>'
        '<select id="m_week" class="aggsel" style="width:auto"></select>'
        '<span class="rlabel" style="margin-left:12px">Day</span>'
        '<select id="m_day" class="aggsel" style="width:auto"></select></div>'
        '<div id="m_svg"></div>'
        '<div id="m_note" class="wtrend" style="margin-top:6px"></div>'
        f'{script}</div>')


_DAY_JS = """<script>(function(){
var DAYS=__DAYS__,TYP=__TYP__;
var dows=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
var mons=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
var keys=Object.keys(DAYS).sort();
var mSel=document.getElementById('m_month'),wSel=document.getElementById('m_week'),dSel=document.getElementById('m_day');
var box=document.getElementById('m_svg'),note=document.getElementById('m_note');
function pd(k){var p=k.split('-');return new Date(+p[0],+p[1]-1,+p[2]);}
function pad(n){return (n<10?'0':'')+n;}
function iso(d){return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());}
function monday(k){var d=pd(k),wd=(d.getDay()+6)%7;d.setDate(d.getDate()-wd);return iso(d);}
function lab(k){var d=pd(k);return dows[(d.getDay()+6)%7]+' '+pad(d.getDate())+' '+mons[d.getMonth()];}
var months=[];keys.forEach(function(k){var ym=k.slice(0,7);if(months.indexOf(ym)<0)months.push(ym);});
months.sort();months.reverse();
mSel.innerHTML=months.map(function(ym){var p=ym.split('-');return '<option value="'+ym+'">'+mons[+p[1]-1]+' '+p[0]+'</option>';}).join('');
function weeks(ym){var ws=[];keys.forEach(function(k){if(k.slice(0,7)===ym){var mo=monday(k);if(ws.indexOf(mo)<0)ws.push(mo);}});ws.sort();ws.reverse();return ws;}
function daysOf(mo){var ds=keys.filter(function(k){return monday(k)===mo;});ds.sort();ds.reverse();return ds;}
function fillWeeks(){var ws=weeks(mSel.value);
wSel.innerHTML=ws.map(function(mo){var d=pd(mo),e=new Date(d);e.setDate(e.getDate()+6);
return '<option value="'+mo+'">Mon '+pad(d.getDate())+' '+mons[d.getMonth()]+' \\u2013 Sun '+pad(e.getDate())+' '+mons[e.getMonth()]+'</option>';}).join('');fillDays();}
function fillDays(){var ds=daysOf(wSel.value);
dSel.innerHTML=ds.map(function(k){return '<option value="'+k+'">'+lab(k)+'</option>';}).join('');draw();}
function ln(p){return p.map(function(q,i){return (i?'L':'M')+q[0].toFixed(1)+' '+q[1].toFixed(1);}).join(' ');}
function draw(){var k=dSel.value;if(!k||!DAYS[k]){box.innerHTML='';note.innerHTML='';return;}
var day=DAYS[k],wd=(pd(k).getDay()+6)%7,tp=TYP[wd]||[];
var W=900,H=200,ml=44,mr=12,mt=14,mb=30,x1=W-mr,y1=H-mb,i;
var vmax=0.1;for(i=0;i<48;i++){if(day[i]!=null&&day[i]>vmax)vmax=day[i];if(tp[i]!=null&&tp[i]>vmax)vmax=tp[i];}vmax*=1.1;
function sx(i){return ml+(x1-ml)*i/47;}function sy(v){return y1-(y1-mt)*v/vmax;}
var s='',t;for(t=0;t<5;t++){var vv=vmax*t/4,y=sy(vv);
s+='<line x1="'+ml+'" y1="'+y.toFixed(1)+'" x2="'+x1+'" y2="'+y.toFixed(1)+'" class="grid"/>';
s+='<text x="'+(ml-6)+'" y="'+(y+3).toFixed(1)+'" class="ytick">'+vv.toFixed(1)+'</text>';}
for(var h=0;h<24;h+=3){s+='<text x="'+sx(h*2).toFixed(1)+'" y="'+(H-8)+'" class="xtick">'+pad(h)+'</text>';}
var tpts=[];for(i=0;i<48;i++)tpts.push([sx(i),sy(tp[i]||0)]);
s+='<path class="fc" style="stroke:#8aa0b2" d="'+ln(tpts)+'"/>';
var dpts=[];for(i=0;i<48;i++)if(day[i]!=null)dpts.push([sx(i),sy(day[i])]);
if(dpts.length>1)s+='<path class="ac" style="stroke:var(--elec)" d="'+ln(dpts)+'"/>';
box.innerHTML='<svg viewBox="0 0 900 200" class="chart">'+s+'</svg>';
var dt=0,tt=0,filled=0;for(i=0;i<48;i++){if(day[i]!=null){dt+=day[i];filled++;}tt+=(tp[i]||0);}
if(filled<44){note.innerHTML='Partial day: <b>'+dt.toFixed(1)+' kWh</b> so far over '+filled+' of 48 half-hours. '+
'The smart-meter feed lags about 2 days, so the most recent days fill in on a later import.';}
else{var diff=dt-tt,pct=tt?Math.round(diff/tt*100):0;
note.innerHTML='This '+dows[wd]+': <b>'+dt.toFixed(1)+' kWh</b> vs a typical '+dows[wd]+' <b>'+tt.toFixed(1)+' kWh</b> &mdash; '+
(diff<=0?'<span style=\\"color:var(--pos)\\">'+Math.abs(pct)+'% lower</span>':'<span style=\\"color:var(--neg)\\">'+pct+'% higher</span>')+'.';}}
mSel.addEventListener('change',fillWeeks);
wSel.addEventListener('change',fillDays);
dSel.addEventListener('change',draw);
fillWeeks();
})();</script>"""


def _drivers_card(drivers, elec_rate, gas_rate):
    if not drivers or not drivers.get("Gas"):
        return ""

    def bar(fuel, rate):
        d = drivers.get(fuel)
        if not d:
            return ""
        heat = d["heating_kwh"] * rate / 100
        base = d["base_kwh"] * rate / 100
        tot = heat + base or 1
        hp = heat / tot * 100
        return (
            f'<p style="font-size:14px;margin:10px 0 4px"><b>{fuel}</b> — the model explains '
            f'<b>{d["r2"] * 100:.0f}%</b> of your daily use.</p>'
            f'<div class="dbar"><span class="dh" style="width:{hp:.0f}%">heating {_money(heat)}</span>'
            f'<span class="dbse" style="width:{100 - hp:.0f}%">base {_money(base)}</span></div>')

    return (
        '<div class="card"><h3>What is driving your bill</h3>'
        '<p class="note">A regression splits each fuel into weather-driven <b>heating</b> (rises with the '
        'cold) and a weather-independent <b>base</b> (hot water, cooking, and the always-on load). '
        'The percentage is how much of the day-to-day variation the model explains.</p>'
        f'{bar("Gas", gas_rate)}{bar("Electricity", elec_rate)}'
        '<p class="note">Gas is mostly heating, so the thermostat and insulation are the levers. Electricity '
        'is mostly base, so the always-on draw is the lever, not the weather.</p></div>')


def _actions_tab(actions):
    if not actions:
        return ('<div class="card"><h3>What should I do?</h3><p class="note">Add your readings, tariffs and '
                'half-hourly data and this becomes a ranked list of exactly what saves you the most.</p></div>')
    conf = {"high": "var(--pos)", "medium": "var(--gas)", "low": "var(--muted)"}
    rows = "".join(
        f'<tr><td class="num money"><b>{_money(v)}</b><span class="u">/yr</span></td>'
        f'<td><div class="tname">{what}</div><div class="tsub">{why}</div></td>'
        f'<td class="num"><span class="chip" style="color:{conf.get(c, "var(--muted)")};'
        f'border-color:{conf.get(c, "var(--muted)")}">{c}</span></td></tr>'
        for v, what, c, why in actions)
    total = sum(v for v, *_ in actions)
    return (
        '<div class="headline">Do these, biggest first. Together they are worth on the order of '
        f'<b>{_money(total)}/yr</b>, though some overlap. Confidence shows how sure the number is.</div>'
        '<h3 class="sec">Ranked by £ per year</h3>'
        '<div class="card"><table class="acts"><thead><tr><th>Saving</th><th>Action</th><th>Confidence</th>'
        f'</tr></thead><tbody>{rows}</tbody></table>'
        '<p class="note">Each figure is backed by a tab: switching by the Monte-Carlo range, the always-on by '
        'your half-hourly baseload, the thermostat by the driver model, the slots by your load profile.</p></div>')


def _hh_heatmap_svg(wh, color, preselect):
    """Clickable 7x24 heat-map. `preselect` is a set of (wd,hour) marked selected."""
    W, H, ml, mt, mb = 960, 330, 50, 30, 26
    x0, x1, y0, y1 = ml, W - 12, mt, H - mb
    if not wh:
        return ""
    vmax = max(wh.values()) or 1
    cw = (x1 - x0) / 24
    rh = (y1 - y0) / 7
    dows = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    parts = []
    for h in range(0, 24, 2):        # label every 2 hours, top and bottom
        parts.append(f'<text x="{x0 + (h + 0.5) * cw:.1f}" y="{y0 - 10:.1f}" class="xtick">{h:02d}</text>')
        parts.append(f'<text x="{x0 + (h + 0.5) * cw:.1f}" y="{y1 + 16:.1f}" class="xtick">{h:02d}</text>')
    for wd in range(7):
        parts.append(f'<text x="{x0 - 8:.1f}" y="{y0 + (wd + 0.62) * rh:.1f}" class="ytick">{dows[wd]}</text>')
        for h in range(24):
            v = wh.get((wd, h), 0.0)
            a = 0.05 + 0.9 * (v / vmax) ** 0.85          # stronger contrast
            sel = " sel" if (wd, h) in preselect else ""
            parts.append(f'<rect class="slot{sel}" data-k="{wd}-{h}" x="{x0 + h * cw + 0.6:.1f}" '
                         f'y="{y0 + wd * rh + 0.6:.1f}" width="{cw - 1.2:.1f}" height="{rh - 1.2:.1f}" rx="2" '
                         f'style="fill:{color};fill-opacity:{a:.2f}">'
                         f'<title>{dows[wd]} {h:02d}:00 — {v:.2f} kWh (click to pick)</title></rect>')
    return f'<svg id="hhmap" viewBox="0 0 {W} {H}" class="chart">{"".join(parts)}</svg>'


def _baseload_month_svg(series, color="#7c9aad"):
    """Line of overnight baseload (kWh/h) per month."""
    if len(series) < 2:
        return ""
    W, H, ml, mr, mt, mb = 960, 200, 46, 14, 14, 42
    x0, x1, y0, y1 = ml, W - mr, mt, H - mb
    vals = [v for _, v in series]
    vmax = max(vals) * 1.15 or 1
    n = len(series)

    def sx(i):
        return x0 + (x1 - x0) * i / (n - 1)

    def sy(v):
        return y1 - (y1 - y0) * v / vmax

    parts = []
    for t in range(5):
        v = vmax * t / 4
        y = sy(v)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{x0 - 6:.1f}" y="{y + 3:.1f}" class="ytick">{v:.2f}</text>')
    parts.append(_time_axis([d for d, _ in series], sx, H))
    pts = [(sx(i), sy(v)) for i, (_, v) in enumerate(series)]
    parts.append(f'<path class="sl" style="stroke:{color}" d="{_line(pts)}"/>')
    for i, (d, v) in enumerate(series):
        parts.append(f'<circle cx="{pts[i][0]:.1f}" cy="{pts[i][1]:.1f}" r="3" style="fill:{color}">'
                     f'<title>{_mlab(d)}: {v:.2f} kWh/h overnight</title></circle>')
    return f'<svg viewBox="0 0 {W} {H}" class="chart">{"".join(parts)}</svg>'


def _hh_tab(profile, tou, slots8, elec_rate, elec_standing=0.0, day_data=(None, None, None)):
    if not profile or not profile.get("Electricity"):
        return ('<div class="card"><h3>Time of use</h3><p class="note">Drop your half-hourly CSV exports '
                '(from Bright / Glow) into <b>data/input/half_hourly</b> and re-run. This tab will then show '
                'when you use power, your always-on baseload, and what time-of-use tariffs would save.</p></div>')
    e = profile["Electricity"]
    g = profile.get("Gas")
    dows = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    always_on = e["baseload_kwh_per_h"] * 8760
    always_cost = always_on * elec_rate / 100
    base_share = always_on / e["annual"] if e["annual"] else 0
    top = sorted(e["by_hour"].items(), key=lambda x: -x[1])[:5]
    gas_line = (f' Gas heating peaks <b>{dows[g["peak_wd"]]} {g["peak_hour"]:02d}:00</b>.' if g else "")

    high = base_share > 0.5
    flag = (' That is <b>unusually high</b> (a typical home is 20 to 40%), so something is very likely '
            'drawing power around the clock without you realising.') if high else ""
    always_card = (
        '<div class="card"><h3>"Always on" (baseload)</h3>'
        f'<p class="note">At your quietest hour (around {e["baseload_hour"]:02d}:00, asleep, nothing in use) '
        f'you still draw about <b>{e["baseload_kwh_per_h"]:.2f} kWh every hour</b>. That constant background '
        f'load is roughly <b>{always_on:,.0f} kWh a year</b> (~<b>{_money(always_cost)}/yr</b>), about '
        f'<b>{base_share:.0%}</b> of your electricity.{flag}</p>'
        '<p class="note">Likely suspects at that level: a second or old fridge/freezer, an aquarium or wine '
        'fridge, electric hot-water recirculation or an immersion left on, underfloor heating or a '
        'dehumidifier, or a stack of always-on electronics. To find it, switch things off one at a time and '
        'watch whether the overnight level drops.</p></div>')

    slot_card = ""
    if slots8:
        chosen = ", ".join(f'<b>{d} {h:02d}:00</b>' for d, h, _ in slots8["slots"])
        per = slots8["per_kwh_saved"] * 100
        slot_card = (
            '<div class="card"><h3>Your 8 best discount hours (the ScottishPower offer)</h3>'
            f'<p class="note">You get eight one-hour 50%-off slots a week. Placed on your heaviest hours they '
            f'land on: {chosen}.</p>'
            f'<p style="font-size:14px;margin:6px 0">From your current usage those slots save about '
            f'<b>{_money(slots8["annual_saving"])}/yr</b>. Every extra kWh you deliberately shift into a slot '
            f'saves another <b>{per:.0f}p</b>.</p>'
            f'<p class="note">So moving flexible loads into a slot pays: a dishwasher cycle (~1.2 kWh) run in '
            f'a discounted hour instead of a normal one saves ~{1.2 * slots8["per_kwh_saved"] * 100:.0f}p, and '
            f'the washing machine (~0.8 kWh) ~{0.8 * slots8["per_kwh_saved"] * 100:.0f}p. Run both in-slot a '
            f'few times a week and the offer is worth noticeably more than the headline.</p></div>')

    tou_rows = "".join(
        f'<tr><td>{lab}</td><td class="num">{kwh:,.0f} kWh</td>'
        f'<td class="num" style="color:var(--pos)">{_money(save)}/yr</td></tr>'
        for lab, kwh, save in tou)

    # interactive slot picker: pre-select the 8 heaviest hours, embed the profile for live JS
    preselect = {k for k, _ in sorted(e["wh"].items(), key=lambda kv: -kv[1])[:8]}
    wh_js = "{" + ",".join(f'"{wd}-{h}":{v:.3f}' for (wd, h), v in e["wh"].items()) + "}"
    picker_js = (
        '<script>(function(){'
        f'var WH={wh_js},RATE={elec_rate};'
        'function nmax(){return Math.max(1,+document.getElementById("slotn").value||8);}'
        'function disc(){return (+document.getElementById("slotpct").value||50)/100;}'
        'function sel(){return Array.prototype.slice.call(document.querySelectorAll("#hhmap .slot.sel"));}'
        'function recalc(){var s=sel(),k=0;s.forEach(function(r){k+=WH[r.dataset.k]||0;});'
        'var save=k*disc()*RATE/100*52;'
        'document.getElementById("slotout").innerHTML="Selected <b>"+s.length+"/"+nmax()+'
        '"</b> slots, <b>"+k.toFixed(1)+" kWh/week</b>, saving <b>\\u00a3"+Math.round(save)+'
        '"/yr</b> at "+Math.round(disc()*100)+"% off";}'
        'function trim(){var s=sel();if(s.length>nmax()){'
        's.sort(function(a,b){return (WH[a.dataset.k]||0)-(WH[b.dataset.k]||0);});'
        'while(s.length>nmax()){s.shift().classList.remove("sel");}}recalc();}'
        'document.querySelectorAll("#hhmap .slot").forEach(function(r){'
        'r.addEventListener("click",function(){'
        'if(!r.classList.contains("sel")&&sel().length>=nmax())return;'
        'r.classList.toggle("sel");recalc();});});'
        'document.getElementById("slotn").addEventListener("input",trim);'
        'document.getElementById("slotpct").addEventListener("input",recalc);'
        'recalc();})();</script>')

    # Economy 7 day/night what-if, live against the real hourly split
    ha = {h: e["by_hour"].get(h, 0) * 365 for h in range(24)}
    hourly_js = "[" + ",".join(f"{ha[h]:.1f}" for h in range(24)) + "]"
    total_e = sum(ha.values())
    e7_card = (
        '<h3 class="sec">Would a cheap-night tariff (Economy 7) help?</h3>'
        '<div class="card"><p class="note">Economy 7 gives a cheaper night rate but a higher day rate. '
        'Only ~23% of your electricity is overnight, so it wins only if the night rate is much lower, or you '
        'shift usage. Enter a quote and compare it to your current flat tariff, live.</p>'
        '<table class="wtab"><tbody>'
        f'<tr><td class="wf">Day rate (p/kWh)</td><td><input id="e7d" type="number" step="0.01" value="{elec_rate:.2f}"></td></tr>'
        f'<tr><td class="wf">Night rate (p/kWh)</td><td><input id="e7n" type="number" step="0.01" value="{elec_rate * 0.5:.2f}"></td></tr>'
        f'<tr><td class="wf">Standing (p/day)</td><td><input id="e7s" type="number" step="0.01" value="{elec_standing:.2f}"></td></tr>'
        '<tr><td class="wf">Night from (hour)</td><td><input id="e7a" type="number" min="0" max="23" value="0"></td></tr>'
        '<tr><td class="wf">Night to (hour)</td><td><input id="e7b" type="number" min="1" max="24" value="7"></td></tr>'
        '</tbody></table><div id="e7out" class="wtrend"></div>'
        '<script>(function(){'
        f'var H={hourly_js},FLAT={elec_rate},FSTD={elec_standing},TOT={total_e:.0f};'
        'function calc(){'
        'var dr=+document.getElementById("e7d").value||0,nr=+document.getElementById("e7n").value||0,'
        'st=+document.getElementById("e7s").value||0,a=+document.getElementById("e7a").value||0,'
        'b=+document.getElementById("e7b").value||0,night=0;'
        'for(var h=0;h<24;h++){var w=(a<=b)?(h>=a&&h<b):(h>=a||h<b);if(w)night+=H[h];}'
        'var day=TOT-night,e7=day*dr/100+night*nr/100+365*st/100,flat=TOT*FLAT/100+365*FSTD/100,d=flat-e7;'
        'document.getElementById("e7out").innerHTML="Economy 7: <b>\\u00a3"+Math.round(e7)+"/yr</b> vs your '
        'flat tariff <b>\\u00a3"+Math.round(flat)+"</b> &mdash; "+(d>=0?"<span style=\\"color:var(--pos)\\">saves '
        '\\u00a3"+Math.round(d)+"/yr</span>":"<span style=\\"color:var(--neg)\\">costs \\u00a3"+Math.round(-d)+'
        '" more/yr</span>")+" ("+Math.round(night)+" kWh night / "+Math.round(day)+" kWh day).";}'
        '["e7d","e7n","e7s","e7a","e7b"].forEach(function(id){'
        'document.getElementById(id).addEventListener("input",calc);});calc();})();</script></div>')

    baseload_card = ""
    if e.get("baseload_series"):
        baseload_card = (
            '<h3 class="sec">Always on, over time (phantom-load hunt)</h3>'
            '<div class="card"><p class="note">Your overnight draw (kWh per hour, 1am to 5am) each month. '
            'A flat line means a permanent device; a step down after you switch something off is the proof '
            'you found it. Re-import after unplugging a suspect and watch this drop.</p>'
            f'{_baseload_month_svg(e["baseload_series"])}</div>')

    return (
        '<div class="headline">'
        f'Your electricity peaks in the evening (dinner and dishwasher), and about <b>{base_share:.0%}</b> of '
        f'it is "always on". Both are levers: shift the evening load into a discount slot, and hunt down the '
        f'background draw.</div>'
        '<h3 class="sec">Pick your discount slots</h3>'
        '<div class="card"><p class="note">Average electricity per hour, by day and time (darker = more). '
        '<b>Click cells to choose slots</b> and the saving updates live. Your heaviest hours are pre-selected. '
        'This is usage (kWh); the standing charge is a flat daily fee that does not vary by time, so it is not '
        'shown here.</p>'
        '<div class="ranges"><span class="rlabel">Slots</span>'
        '<input id="slotn" type="number" min="1" max="24" value="8" class="aggsel" style="width:70px">'
        '<span class="rlabel" style="margin-left:12px">Discount %</span>'
        '<input id="slotpct" type="number" min="1" max="100" value="50" class="aggsel" style="width:70px"></div>'
        f'{_hh_heatmap_svg(e["wh"], "var(--elec)", preselect)}'
        f'<div id="slotout" class="wtrend" style="margin-top:8px"></div>'
        f'<p class="note">Busiest hours: {", ".join(f"<b>{h:02d}:00</b> ({v:.2f})" for h, v in top)}. '
        f'Peak is {dows[e["peak_wd"]]} {e["peak_hour"]:02d}:00.{gas_line}</p>{picker_js}</div>'
        f'<h3 class="sec">The 8-slot offer, on your current usage</h3>{slot_card}'
        f'{e7_card}'
        f'<h3 class="sec">Always on</h3>{always_card}'
        f'{baseload_card}'
        f'{_day_inspector(*day_data)}'
        '<h3 class="sec">Other discount windows</h3>'
        '<div class="card"><p class="note">Your real usage in each window and the saving if it were 50% off, '
        'for comparison.</p>'
        '<table><thead><tr><th>Discount window</th><th>Your usage in it</th><th>Saving at 50% off</th>'
        f'</tr></thead><tbody>{tou_rows}</tbody></table></div>')


def _dd_card(dd, forecast_cost, actual_cost, balance):
    if not dd or dd <= 0:
        return ('<div class="card"><h3>Direct debit check</h3>'
                '<p class="note">Enter your <b>Monthly direct debit (£)</b> on the Home tab to see whether '
                'you\'re paying too much (building credit) or too little (heading for a bill).</p></div>')
    annual = dd * 12
    yearly = forecast_cost                             # forward-looking: the year AHEAD
    surplus = annual - yearly                          # +ve = DD exceeds cost → building credit
    p1 = (f'You pay <b>{_money(dd, 2)}/mo</b> ({_money(annual)}/yr). Your <b>forecast</b> cost for the '
          f'year ahead is <b>{_money(yearly)}</b>')
    if actual_cost:
        p1 += f' (you were charged {_money(actual_cost)} over the last 12 months).'
    else:
        p1 += '.'
    col = "var(--text)"
    if balance is not None and float(balance) != 0:
        bal = float(balance)
        state = f'{_money(abs(bal), 2)} in {"debit" if bal < 0 else "credit"}'
        if bal < 0:
            needed = (yearly - bal) / 12
            if surplus > 5:
                yrs = -bal / surplus
                verdict = (f"You're currently <b>{state}</b>. Your DD is about {_money(surplus)}/yr above your cost, "
                           f"so at this rate the debit clears in ~{yrs:.1f} years. To clear it within a year, "
                           f"raise the DD to about <b>{_money(needed, 0)}/mo</b>.")
                col = "var(--text)"
            else:
                verdict = (f"You're <b>{state}</b> and your DD barely covers your yearly cost, so the debit "
                           f"won't clear on its own — you'd need about <b>{_money(needed, 0)}/mo</b> to clear it "
                           f"within a year, or expect a DD increase.")
                col = "var(--neg)"
        else:
            verdict = f"You're <b>{state}</b> — comfortably ahead; you could lower your DD."
            col = "var(--pos)"
    elif abs(surplus) < 60:
        verdict = "About right — your DD roughly matches your yearly cost."
    elif surplus > 0:
        verdict, col = f"You pay <b>{_money(surplus)}/yr</b> more than it costs — building credit.", "var(--pos)"
    else:
        verdict, col = f"You pay <b>{_money(-surplus)}/yr</b> less than it costs — building debit.", "var(--neg)"
    check = ""
    if actual_cost and forecast_cost:
        check = (f'<p class="note">Model check: the tool estimated {_money(forecast_cost)} vs your actual '
                 f'{_money(actual_cost)} — within {abs(forecast_cost - actual_cost) / actual_cost * 100:.0f}%.</p>')
    return (f'<div class="card"><h3>Direct debit check</h3>'
            f'<p class="note">{p1}</p>'
            f'<p style="font-size:14px;color:{col};margin:6px 0 2px">{verdict}</p>'
            f'<p class="note">Direct debits are flat but usage is seasonal — credit builds in summer, '
            f'debit in winter; the yearly balance is what matters.</p>{check}</div>')


def _tracking_card(tracking):
    if not tracking:
        return ('<div class="card"><h3>Forecast track record</h3>'
                '<p class="note">Now recording each run\'s forecast. As you add real readings for '
                'future months, this will show how close the forecast was — and flag outliers or misreads.</p></div>')
    mape = sum(abs(t["error"]) for t in tracking) / len(tracking)
    rows = "".join(
        f'<tr><td>{MONTHS[int(t["month"][5:7])]} {t["month"][2:4]}</td><td>{t["fuel"]}</td>'
        f'<td class="num">{t["forecast"]:,.0f}</td><td class="num">{t["actual"]:,.0f}</td>'
        f'<td class="num" style="color:{"var(--neg)" if abs(t["error"]) > 0.15 else "var(--muted)"}">'
        f'{t["error"] * 100:+.0f}%</td></tr>' for t in tracking)
    return (f'<div class="card"><h3>Forecast track record '
            f'<span class="hint">{len(tracking)} graded · {(1 - mape) * 100:.0f}% accurate</span></h3>'
            f'<p class="note">Forecasts we logged earlier vs the actuals you have since entered. '
            f'Large errors (red) may be a genuine change — or a misread worth checking.</p>'
            f'<table><thead><tr><th>Month</th><th>Fuel</th><th>Forecast</th><th>Actual</th>'
            f'<th>Error</th></tr></thead><tbody>{rows}</tbody></table></div>')


def render_html(path, address, usage, method, comparisons, insights, backtest,
                forward, generated, settings, monthly, weather, tracking, annual_actual, bills, mc,
                hh_profile=None, tou=None, slots8=None, drivers=None, actions=None, gas_rate=0.0,
                day_data=(None, None, None)):
    best = comparisons[0] if comparisons else None
    ei, gi = insights["Electricity"], insights["Gas"]
    ebt, gbt = backtest.get("Electricity", {}), backtest.get("Gas", {})

    current_row = next((c for c in comparisons if c.get("Is_Current") == "Yes"), None)
    cheapest_fixed = min((c for c in comparisons if c["Type"].lower() == "fixed"),
                         key=lambda c: c["Expected_Annual_Cost_GBP"], default=None)
    rates = ((current_row or (best or {})).get("Elec_Unit_p", 0),
             (current_row or (best or {})).get("Elec_SC_p_day", 0),
             (current_row or (best or {})).get("Gas_Unit_p", 0),
             (current_row or (best or {})).get("Gas_SC_p_day", 0))
    current_cost = current_row["Expected_Annual_Cost_GBP"] if current_row \
        else (best["Expected_Annual_Cost_GBP"] if best else 0)

    # Deterministic (no-AI) suggestions for the what-if panel
    best_saving = best["Saving_vs_Current_GBP"] if best else 0
    standing_year = 365 * (rates[1] + rates[3]) / 100
    standing_pct = standing_year / current_cost if current_cost else 0
    gas_share = usage[1] / (usage[0] + usage[1]) if (usage[0] + usage[1]) else 0
    sugg = []
    sugg.append('<span id="sug_standing"></span>')   # updated live from the selected/entered rates
    sugg.append(f"Every 1p/kWh off electricity ≈ <b>{_money(usage[0] / 100)}/yr</b>; off gas ≈ <b>{_money(usage[1] / 100)}/yr</b> (same on any tariff).")
    sugg.append(f"Gas is <b>{gas_share:.0%}</b> of your energy — heating is the biggest lever (thermostat, insulation).")
    suggestions = "".join(f"<li>{s}</li>" for s in sugg)

    infl = float(settings.get("Assumed yearly price rise % at renewal", 8) or 8) / 100
    renewal_cost = current_cost * (1 + infl)

    # what-if tariff picker (dropdown fills the rate boxes; you can then overwrite)
    wf_opts = ['<option value="cur">— Reset to your current tariff —</option>']
    wf_js = []
    j = 0
    for c in comparisons:
        if c.get("Is_Current") == "Yes":
            continue                                       # don't list the tariff you're already on
        wf_opts.append(f'<option value="{j}">{c["Supplier"]} — {c["Tariff_Name"]}</option>')
        wf_js.append(f'{{eu:{c["Elec_Unit_p"]},esc:{c["Elec_SC_p_day"]},'
                     f'gu:{c["Gas_Unit_p"]},gsc:{c["Gas_SC_p_day"]}}}')
        j += 1
    tariff_options = "".join(wf_opts)
    tariff_js = "[" + ",".join(wf_js) + "]"

    # Best actions ranked by £/year saved (deterministic; no supplier names — those change)
    acts = []
    if best and best_saving > 1:
        acts.append((best_saving, "Move to the cheapest tariff for your usage",
                     "compare in the what-if below"))
    gas_unit_cost = usage[1] * rates[2] / 100
    elec_unit_cost = usage[0] * rates[0] / 100
    acts.append((gas_unit_cost * 0.08, "Turn the thermostat down 1°C", "≈8% of heating gas"))
    # only suggest cutting a fuel that is actually rising (don't tell you to cut one that's already falling)
    if gi["yoy"] and gi["yoy"]["direction"] == "up":
        acts.append((gas_unit_cost * 0.10, "Cut gas use 10% (it's up this year)", "draughts, shorter heating hours"))
    if ei["yoy"] and ei["yoy"]["direction"] == "up":
        acts.append((elec_unit_cost * 0.10, "Cut electricity use 10% (it's up this year)", "standby, appliances"))
    acts.sort(reverse=True, key=lambda a: a[0])
    # credit the fuel(s) already falling
    good = []
    for nm, y, cost in (("Electricity", ei["yoy"], elec_unit_cost), ("Gas", gi["yoy"], gas_unit_cost)):
        if y and y["direction"] == "down":
            good.append(f"{nm.lower()} is already down {abs(y['pct']) * 100:.0f}% "
                        f"(~{_money(cost * abs(y['pct']))}/yr saved)")
    actions_note = ("On track: " + "; ".join(good) + " — keep it up.") if good else ""
    sw_actions = "".join(
        f'<tr><td class="num money"><b>{_money(v)}</b><span class="u">/yr</span></td>'
        f'<td><div class="tname">{what}</div><div class="tsub">{why}</div></td></tr>'
        for v, what, why in acts if v >= 1)

    # ---- Part 1 tiles: current usage & performance ----
    acc_e = f"{(1 - ebt['mape']) * 100:.0f}%" if ebt.get("mape") is not None else "—"
    acc_g = f"{(1 - gbt['mape']) * 100:.0f}%" if gbt.get("mape") is not None else "—"
    cur_tiles = []
    if current_row:
        cur_tiles.append(_kpi("Current tariff", f"{current_row['Supplier']}",
                              f"{current_row['Tariff_Name']} · {_money(current_row['Expected_Annual_Cost_GBP'])}/yr",
                              big=True))
    cur_tiles.append(_kpi("Forecast annual usage",
                          f"{usage[0]:,.0f}<span class='u'>kWh elec</span>",
                          f"gas {usage[1]:,.0f} kWh"))
    cur_tiles.append(_kpi("Forecast accuracy", f"{acc_e}<span class='u'>elec</span>",
                          f"gas {acc_g} · walk-forward test"))
    cur_tiles.append(_kpi("Model reliability", _reliability(gbt).split(" ")[0],
                          f"gas {_reliability(gbt)} within band"))

    # ---- Part 2 tiles: if you switch ----
    switch_tiles = []
    if best:
        switch_tiles.append(_kpi("Best value tariff", f"{best['Supplier']}",
                                 f"{best['Tariff_Name']} · {_money(best['Expected_Annual_Cost_GBP'])}/yr",
                                 big=True))
        sv = best["Saving_vs_Current_GBP"]
        arrow = "▼" if sv >= 0 else "▲"
        switch_tiles.append(_kpi("Saving vs current", f"{arrow} {_money(abs(sv))}",
                                 f"{_money(best['Monthly_Equivalent_GBP'])}/mo",
                                 cls="pos" if sv >= 0 else "neg"))
    if cheapest_fixed:
        fsv = cheapest_fixed["Saving_vs_Current_GBP"]
        switch_tiles.append(_kpi("Cheapest fixed (price-certain)", f"{cheapest_fixed['Supplier']}",
                                 f"{_money(cheapest_fixed['Expected_Annual_Cost_GBP'])}/yr · "
                                 f"{('save ' + _money(abs(fsv))) if fsv >= 0 else ('+' + _money(-fsv))}"))
    switch_tiles.append(_kpi("Options compared", f"{len(comparisons)}",
                             "suppliers ranked below"))
    tiles = "".join(cur_tiles)
    switch_tiles = "".join(switch_tiles)

    # Leaderboard — grouped by tariff type so like compares with like
    maxc = max((c["Expected_Annual_Cost_GBP"] for c in comparisons), default=1)
    best_key = id(comparisons[0]) if comparisons else None

    def _lb_row(rank, c):
        sv = c["Saving_vs_Current_GBP"]
        svcls = "pos" if sv > 0 else "neg" if sv < 0 else ""
        svtxt = "—" if abs(sv) < 0.5 else f"{'▼' if sv > 0 else '▲'} {_money(abs(sv))}"
        barw = c["Expected_Annual_Cost_GBP"] / maxc * 100
        return (
            f'<tr class="{"win" if id(c) == best_key else ""}">'
            f'<td class="rank">{rank}</td>'
            f'<td><div class="tname">{c["Supplier"]}'
            f'{" <span class=\'now\'>current</span>" if c.get("Is_Current") else ""}'
            f'{" <span class=\'now win\'>cheapest</span>" if id(c) == best_key else ""}</div>'
            f'<div class="tsub">{c["Tariff_Name"]}</div></td>'
            f'<td class="num">{c["Elec_Unit_p"]:.2f}<span class="u">p</span></td>'
            f'<td class="num">{c["Gas_Unit_p"]:.2f}<span class="u">p</span></td>'
            f'<td class="num money"><div class="barwrap"><span class="bar" style="width:{barw:.0f}%"></span>'
            f'<b>{_money(c["Expected_Annual_Cost_GBP"])}</b></div></td>'
            f'<td class="num {svcls}">{svtxt}</td></tr>')

    groups = {}
    for c in comparisons:
        groups.setdefault(c["Type"] or "Other", []).append(c)
    glabels = {"Fixed": "Fixed — price-certain", "Tracker": "Tracker — moves with the market",
               "Variable": "Variable"}
    lb = []
    for typ in ["Fixed", "Tracker", "Variable"] + [t for t in groups if t not in ("Fixed", "Tracker", "Variable")]:
        if typ not in groups:
            continue
        lb.append(f'<tr class="grp"><td colspan="6">{glabels.get(typ, typ)}</td></tr>')
        for rank, c in enumerate(groups[typ], 1):
            lb.append(_lb_row(rank, c))
    leaderboard = "".join(lb)

    # bias-correction factors (from the walk-forward), applied to the forecast in the charts
    ecorr = 1 + max(-0.3, min(0.3, ebt.get("bias") or 0))
    gcorr = 1 + max(-0.3, min(0.3, gbt.get("bias") or 0))

    # Interactive look-back ranges over the monthly history (pre-rendered, toggled by JS)
    presets = [("3m", "3 months", 3), ("6m", "6 months", 6), ("12m", "12 months", 12),
               ("18m", "18 months", 18), ("24m", "2 years", 24), ("all", "All", None)]
    default_r = "12m"
    btns, views = [], []
    for key, label, n in presets:
        sub = monthly[-n:] if n else monthly
        es, gs = _season_from_monthly(sub)
        season = _seasonality_svg(es, gs)
        keynums = _key_numbers(sub, rates)
        et, gt = _win_trend(sub, monthly, 1), _win_trend(sub, monthly, 2)
        e_off = _combined_svg(sub, monthly, forward.get("Electricity", []), 1, "var(--elec)", False, ecorr)
        e_on = _combined_svg(sub, monthly, forward.get("Electricity", []), 1, "var(--elec)", True, ecorr)
        g_off = _combined_svg(sub, monthly, forward.get("Gas", []), 2, "var(--gas)", False, gcorr)
        g_on = _combined_svg(sub, monthly, forward.get("Gas", []), 2, "var(--gas)", True, gcorr)
        on = key == default_r
        btns.append(f'<button class="rbtn{" on" if on else ""}" data-r="{key}">{label}</button>')
        views.append(
            f'<div class="rv{" active" if on else ""}" data-r="{key}">'
            f'<div class="card"><h3>Electricity — usage &amp; forecast</h3>'
            f'<p class="note">{_trend_span(et)} vs the same {label.lower()} a year earlier · '
            f'hover a point · Forecast toggle above.</p>'
            f'<div class="fcv fc-off">{e_off}</div><div class="fcv fc-on">{e_on}</div></div>'
            f'<div class="card" style="margin-top:14px"><h3>Gas — usage &amp; forecast</h3>'
            f'<p class="note">{_trend_span(gt)} vs the same {label.lower()} a year earlier · '
            f'green error bar = used less than the model forecast.</p>'
            f'<div class="fcv fc-off">{g_off}</div><div class="fcv fc-on">{g_on}</div></div>'
            f'<div class="cols" style="margin-top:14px">'
            f'<div class="card"><h3>Seasonality</h3><p class="note">average kWh/day by month</p>'
            f'<div class="legend"><span><i style="border-color:var(--elec)"></i>electricity</span>'
            f'<span><i style="border-color:var(--gas)"></i>gas</span></div>{season}</div>'
            f'<div class="card"><h3>Key numbers <span class="hint">over {label.lower()} '
            f'— use the Look back buttons above to change</span></h3>'
            f'<table>{keynums}</table></div>'
            f'</div></div>')
    range_buttons = "".join(btns)
    rangeviews = "".join(views)
    # Compare-years overlay (metric-selectable, pre-rendered + toggled)
    metrics = [
        ("gas", "Gas usage — kWh/day", _yoy_overlay_svg(_by_year_avgday(monthly, 2), 1)),
        ("elec", "Electricity usage — kWh/day", _yoy_overlay_svg(_by_year_avgday(monthly, 1), 1)),
        ("cost", "Total cost (gas + electricity) — £/month", _yoy_overlay_svg(_by_year_cost(bills), 0)),
        ("gidx", "Gas indexed (100 = that year's January)", _yoy_overlay_svg(_by_year_index(monthly, 2), 0)),
        ("eidx", "Electricity indexed (100 = that year's January)", _yoy_overlay_svg(_by_year_index(monthly, 1), 0)),
    ]
    mbtns, mviews = [], []
    for i, (k, lab, svg) in enumerate(metrics):
        onm = i == 0
        short = {"gas": "Gas kWh", "elec": "Elec kWh", "cost": "Total cost £",
                 "gidx": "Gas index", "eidx": "Elec index"}[k]
        mbtns.append(f'<button class="rbtn{" on" if onm else ""}" data-m="{k}">{short}</button>')
        mviews.append(f'<div class="mv{" active" if onm else ""}" data-m="{k}">'
                      f'<p class="note">{lab} — each line is a year, so you compare the same months across years.</p>'
                      f'{svg}</div>')
    compare_card = (f'<div class="card"><div class="ranges"><span class="rlabel">Compare:</span>'
                    f'{"".join(mbtns)}</div>{"".join(mviews)}</div>')

    weather_card = _weather_card(weather, monthly, gi)
    tracking_card = _tracking_card(tracking)
    season_card = _season_yoy_card(monthly, rates, {1: ecorr, 2: gcorr})
    cost_tab = _cost_tab(monthly, rates, forward)
    hh_tab = _hh_tab(hh_profile, tou or [], slots8, rates[0], rates[1], day_data)
    drivers_card = _drivers_card(drivers, rates[0], gas_rate)
    actions_tab = _actions_tab(actions or [])
    dd_card = _dd_card(float(settings.get("Monthly direct debit (£)", 0) or 0), current_cost,
                       annual_actual, settings.get("Account balance (£, - if in debit)"))
    mc_card = _mc_card(mc)

    _SENSITIVE = ("MPAN", "MPRN", "GUID", "IHD", "MAC")   # never put meter IDs in the shareable report
    assumptions = "".join(
        f'<tr><td>{k}</td><td>{"" if v is None else v}</td></tr>'
        for k, v in settings.items()
        if not str(k).startswith("—") and not any(t in str(k).upper() for t in _SENSITIVE))

    # one-line headline (always visible above the tabs)
    hl = []
    if best and best_saving > 1:
        risk = " (variable — market risk)" if best["Type"].lower() in ("tracker", "variable") else ""
        hl.append(f'Cheapest option saves ~<b>{_money(best_saving)}/yr</b>{risk}')
    _dd = float(settings.get("Monthly direct debit (£)", 0) or 0)
    _bal = settings.get("Account balance (£, - if in debit)")
    if _dd > 0 and _bal is not None and float(_bal) < 0:
        hl.append(f"you're <b>{_money(abs(float(_bal)))}</b> in debit")
    if ei["yoy"]:
        hl.append(f'electricity {_plain_yoy(ei["yoy"])} vs last year')
    headline = " &nbsp;·&nbsp; ".join(hl) or "Add your readings and tariffs to see recommendations."

    has_tracker = any(c["Type"].lower() in ("tracker", "variable") for c in comparisons)
    tracker_note = ('<p class="risk">⚠ Tracker/variable rates can change — this ranking is a '
                    'snapshot of today\'s rates. The "cheapest fixed" tile above is your '
                    'price-certain option.</p>') if has_tracker else ""

    html = _PAGE.format(
        address=address or "Home", generated=generated, method=method.lower(),
        tiles=tiles, switch_tiles=switch_tiles, leaderboard=leaderboard, tracker_note=tracker_note,
        range_buttons=range_buttons, rangeviews=rangeviews, weather_card=weather_card,
        tracking_card=tracking_card, dd_card=dd_card, compare_card=compare_card, mc_card=mc_card,
        season_card=season_card, headline=headline, cost_tab=cost_tab, hh_tab=hh_tab,
        drivers_card=drivers_card, actions_tab=actions_tab,
        tariff_options=tariff_options, tariff_js=tariff_js,
        suggestions=suggestions, sw_actions=sw_actions, actions_note=actions_note, assumptions=assumptions,
        e_kwh=round(usage[0]), g_kwh=round(usage[1]), current_cost=round(current_cost),
        cur_eu=rates[0], cur_esc=rates[1], cur_gu=rates[2], cur_gsc=rates[3],
        renewal=round(renewal_cost), infl_pct=round(infl * 100),
        current_disp=_money(current_cost), renewal_disp=_money(renewal_cost),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def _plain_yoy(yoy):
    if not yoy:
        return "—"
    a = {"up": "▲", "down": "▼", "flat": "▬"}[yoy["direction"]]
    return f"{a} {abs(yoy['pct']) * 100:.0f}%"


def _yoy_span(yoy):
    if not yoy:
        return '<span class="chip">no history</span>'
    a = {"up": "▲", "down": "▼", "flat": "▬"}[yoy["direction"]]
    cls = "neg" if yoy["direction"] == "up" else "pos" if yoy["direction"] == "down" else "flat"
    return f'<span class="chip {cls}">{a} {abs(yoy["pct"]) * 100:.0f}%</span>'


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Home Energy Report</title>
<style>
:root{{
  --bg:#f6f8fb; --surface:#ffffff; --surface2:#f0f4f9; --text:#0f1b2d; --muted:#5b6b7f;
  --border:#e2e8f0; --elec:#2e6fb0; --gas:#c6741b; --pos:#1f8a70; --neg:#c0392b;
  --band:rgba(46,111,176,.12); --hero:#12314f;
}}
@media (prefers-color-scheme:dark){{
  :root{{ --bg:#0b0f16; --surface:#141a24; --surface2:#1b2330; --text:#e6ecf3; --muted:#93a1b0;
    --border:#232c39; --elec:#5aa9f0; --gas:#f0a93b; --pos:#38b48b; --neg:#e4685a;
    --band:rgba(90,169,240,.14); --hero:#dce7f3; }}
}}
:root[data-theme="dark"]{{ --bg:#0b0f16; --surface:#141a24; --surface2:#1b2330; --text:#e6ecf3;
  --muted:#93a1b0; --border:#232c39; --elec:#5aa9f0; --gas:#f0a93b; --pos:#38b48b; --neg:#e4685a;
  --band:rgba(90,169,240,.14); --hero:#dce7f3; }}
:root[data-theme="light"]{{ --bg:#f6f8fb; --surface:#ffffff; --surface2:#f0f4f9; --text:#0f1b2d;
  --muted:#5b6b7f; --border:#e2e8f0; --elec:#2e6fb0; --gas:#c6741b; --pos:#1f8a70; --neg:#c0392b;
  --band:rgba(46,111,176,.12); --hero:#12314f; }}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-variant-numeric:tabular-nums;line-height:1.4}}
.wrap{{max-width:1120px;margin:0 auto;padding:28px 22px 60px}}
header{{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;
  border-bottom:1px solid var(--border);padding-bottom:16px;margin-bottom:22px}}
h1{{font-size:23px;margin:0;letter-spacing:-.02em}}
.sub{{color:var(--muted);font-size:13px;margin-top:4px}}
.toggle{{background:var(--surface);border:1px solid var(--border);color:var(--muted);
  border-radius:8px;padding:7px 12px;font-size:12px;cursor:pointer}}
.part{{display:flex;align-items:baseline;gap:12px;margin:34px 0 14px;
  padding-bottom:10px;border-bottom:2px solid var(--elec)}}
.part.switch{{border-bottom-color:var(--pos)}}
.part h2{{margin:0;font-size:19px;text-transform:none;letter-spacing:-.01em;color:var(--text)}}
.pnum{{font-size:11px;text-transform:uppercase;letter-spacing:.1em;font-weight:700;color:#fff;
  background:var(--elec);border-radius:5px;padding:3px 8px}}
.part.switch .pnum{{background:var(--pos)}}
h3.sec{{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);
  margin:22px 0 12px;font-weight:600}}
.risk{{font-size:12px;color:var(--neg);margin:10px 4px 4px}}
.ranges{{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:6px 0 14px}}
.rlabel{{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-right:4px}}
.rbtn{{background:var(--surface);border:1px solid var(--border);color:var(--muted);border-radius:8px;
  padding:6px 12px;font-size:12px;font-weight:600;cursor:pointer}}
.rbtn.on{{background:var(--elec);border-color:var(--elec);color:#fff}}
.rv{{display:none}} .rv.active{{display:block}}
.mv{{display:none}} .mv.active{{display:block}}
.pv{{display:none}} .pv.active{{display:block}}
#costcard.hide-tot .cl-tot,#costcard.hide-eu .cl-eu,#costcard.hide-gu .cl-gu,#costcard.hide-es .cl-es,#costcard.hide-gs .cl-gs{{display:none}}
.pivot{{font-size:12px;border-collapse:collapse}} .pivot th,.pivot td{{padding:6px 8px;text-align:right;white-space:nowrap;border:1px solid var(--border)}}
.pivot th:first-child,.pivot td:first-child{{text-align:left}}
.pivot th{{background:none;color:var(--muted);border-bottom:1px solid var(--border)}}
.pivot .agg{{background:var(--surface2);font-weight:600;border-left:2px solid var(--border)}}
.pivot th.agg{{background:var(--surface2)}}
.pivot .fcell{{font-style:italic;color:#8257c9;font-weight:600}}
.pivot .pcell{{background:var(--surface2)}} .pivot .pcell .fv{{font-style:italic;color:#8257c9;font-weight:600}}
.dv{{display:none}} .dv.active{{display:block}}
.chart .slot{{cursor:pointer;stroke:var(--bg);stroke-width:1}}
.chart .slot.sel{{stroke:var(--text);stroke-width:2.5}}
.dbar{{display:flex;height:30px;border-radius:8px;overflow:hidden;margin:4px 0 2px;font-size:12px;font-weight:600}}
.dbar span{{display:flex;align-items:center;justify-content:center;color:#fff;white-space:nowrap;min-width:0}}
.dbar .dh{{background:var(--gas)}} .dbar .dbse{{background:var(--elec)}}
#pivotcard.nofc .fv,#pivotcard.nofc .fvsum{{display:none}}
#pivotcard.nofc .fcell::after{{content:"·";color:var(--border)}}
#pivotcard:not(.nofc) .av{{display:none}}
.pmark{{color:var(--neg);font-size:9px;vertical-align:super;margin-left:1px}}
#pivotcard .agg{{display:none}}
#pivotcard.show-q1 .agg-q1,#pivotcard.show-q2 .agg-q2,#pivotcard.show-q3 .agg-q3,#pivotcard.show-q4 .agg-q4,#pivotcard.show-h1 .agg-h1,#pivotcard.show-h2 .agg-h2,#pivotcard.show-year .agg-year{{display:table-cell}}
.aggsel{{background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:6px 9px;font-size:12px}}
.headline{{background:var(--surface);border:1px solid var(--border);border-left:4px solid var(--elec);
  border-radius:10px;padding:12px 16px;margin:18px 0 4px;font-size:14px;color:var(--text)}}
.headline b{{color:var(--hero)}}
.dsec{{border:1px solid var(--border);border-radius:12px;margin:14px 0;background:var(--surface);overflow:hidden}}
.dsec>summary{{cursor:pointer;padding:14px 16px;font-size:12px;text-transform:uppercase;letter-spacing:.08em;
  color:var(--muted);font-weight:600;list-style:none}}
.dsec>summary::-webkit-details-marker{{display:none}}
.dsec>summary::before{{content:"\\25B8  ";color:var(--elec)}}
.dsec[open]>summary::before{{content:"\\25BE  "}}
.dsec[open]>summary{{border-bottom:1px solid var(--border)}}
.dsec>.card{{border:none;border-radius:0;margin:0}}
.tabbar{{display:flex;gap:4px;border-bottom:1px solid var(--border);margin:24px 0 18px}}
.tab{{background:none;border:none;border-bottom:2px solid transparent;color:var(--muted);
  padding:10px 16px;font-size:15px;font-weight:600;cursor:pointer;margin-bottom:-1px}}
.tab.on{{color:var(--text);border-bottom-color:var(--elec)}}
.tabpane{{display:none}} .tabpane.active{{display:block}}
.wtrend{{font-size:13px;color:var(--muted);margin:2px 0 12px}} .wtrend b{{color:var(--text)}}
.fcv{{display:block}}
.wrap.hidefc .fc-on{{display:none}} .wrap:not(.hidefc) .fc-off{{display:none}}
#wxcard.hidegas .wgas{{display:none}}
.hint{{float:right;font-size:10px;font-weight:400;color:var(--muted);text-transform:none;letter-spacing:0}}
.chart .yearlab{{fill:var(--text);font-size:11px;font-weight:600;text-anchor:middle}}
.chart .yeardiv{{stroke:var(--border);stroke-width:1}}
.chart .fcm{{fill:var(--surface);stroke-width:1.5}}
tr.grp td{{background:var(--surface2);font-weight:700;font-size:11px;text-transform:uppercase;
  letter-spacing:.06em;color:var(--muted);padding:7px 8px}}
.now.win{{color:var(--pos);border-color:var(--pos)}}
.wcard{{display:flex;gap:26px;flex-wrap:wrap}}
.wleft{{flex:1;min-width:300px}} .wright{{flex:1;min-width:260px}}
@media (min-width:760px){{.wright{{border-left:1px solid var(--border);padding-left:24px}}}}
.wref{{font-size:13px;color:var(--muted);margin-bottom:12px;line-height:1.6}} .wref b{{color:var(--text)}}
.wbig b{{font-size:32px;color:var(--hero);font-weight:700}}
.acts td{{padding:10px 8px;border-bottom:1px solid var(--border);vertical-align:middle}}
.acts td.money{{white-space:nowrap;width:1%}} .acts td.money b{{font-size:17px;color:var(--pos)}}
.wsug{{margin-top:16px}} .wsug ul{{margin:6px 0 0;padding-left:18px}}
.wsug li{{font-size:12.5px;color:var(--muted);margin:6px 0;line-height:1.45}} .wsug b{{color:var(--text)}}
.wpick{{display:block;font-size:12px;color:var(--muted);margin:0 0 12px}}
.wpick select{{margin-left:8px;background:var(--bg);border:1px solid var(--border);color:var(--text);
  border-radius:8px;padding:7px 10px;font-size:13px;max-width:280px}}
.wtab{{max-width:440px;margin:4px 0 12px}} .wtab th{{text-align:right}} .wtab th:first-child{{text-align:left}}
.wtab td.wf{{font-weight:600}} .wtab td{{text-align:right}}
.wtab input{{width:120px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text);
  padding:7px 9px;font-size:14px;text-align:right;font-variant-numeric:tabular-nums}}
.wout{{font-size:14px;color:var(--muted);display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.wout b{{font-size:22px;color:var(--hero)}} #wf_reset{{cursor:pointer}}
h2{{font-size:12px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);
  margin:30px 0 12px;font-weight:600}}
.grid{{display:grid;gap:14px}}
.tiles{{grid-template-columns:repeat(6,1fr)}}
.tile{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 15px}}
.tile.span2{{grid-column:span 2}}
.klabel{{font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);font-weight:600}}
.kvalue{{font-size:21px;font-weight:650;margin-top:7px;letter-spacing:-.02em}}
.kvalue.hero{{font-size:26px;color:var(--hero)}}
.kvalue .u{{font-size:12px;color:var(--muted);font-weight:500;margin-left:4px}}
.ksub{{font-size:12px;color:var(--muted);margin-top:5px}}
.tile.pos .kvalue{{color:var(--pos)}} .tile.neg .kvalue{{color:var(--neg)}}
.cols{{display:grid;grid-template-columns:1.15fr .85fr;gap:18px;align-items:start}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 16px 10px}}
.card h3{{font-size:14px;margin:0 0 2px}} .card .note{{font-size:12px;color:var(--muted);margin:0 0 6px}}
.chart{{width:100%;height:auto;display:block}}
.chart .grid{{stroke:var(--border);stroke-width:1}}
.chart .ytick,.chart .xtick{{fill:var(--muted);font-size:10px}}
.chart .ytick{{text-anchor:end}} .chart .xtick{{text-anchor:middle}}
.chart .band{{fill:var(--band);stroke:none}}
.chart .fc{{fill:none;stroke-width:2;stroke-dasharray:5 4;opacity:.9}}
.chart .ac{{fill:none;stroke-width:2.4}}
.chart .today{{stroke:var(--muted);stroke-width:1;stroke-dasharray:2 3}}
.chart .todaylab{{fill:var(--muted);font-size:10px}}
.chart .area{{opacity:.12;stroke:none}} .chart .sl{{fill:none;stroke-width:2.4}}
.chart .rlab{{fill:var(--muted);font-size:9px;text-anchor:middle}}
.legend{{display:flex;gap:16px;font-size:11.5px;color:var(--muted);margin:2px 2px 6px}}
.legend i{{display:inline-block;width:14px;height:0;border-top-width:2.4px;border-top-style:solid;
  vertical-align:middle;margin-right:5px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);
  font-weight:600;padding:6px 8px;border-bottom:1px solid var(--border)}}
td{{padding:8px;border-bottom:1px solid var(--border);vertical-align:middle}}
td.num{{text-align:right;white-space:nowrap}} td.rank{{color:var(--muted);width:22px}}
tr.win td{{background:var(--surface2)}} tr.win .tname{{font-weight:700}}
.tname{{font-weight:600}} .tsub{{font-size:11px;color:var(--muted)}}
.now{{font-size:9px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);
  border:1px solid var(--border);border-radius:10px;padding:1px 6px;margin-left:5px;font-weight:600}}
td.t{{color:var(--muted);font-size:12px}} .u{{font-size:10px;color:var(--muted)}}
td.pos{{color:var(--pos);font-weight:600}} td.neg{{color:var(--neg);font-weight:600}}
.barwrap{{position:relative;display:flex;justify-content:flex-end;align-items:center;min-width:120px}}
.bar{{position:absolute;left:0;height:16px;background:var(--surface2);border-radius:4px}}
.barwrap b{{position:relative;font-weight:600}}
.chip{{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11.5px;font-weight:600;
  border:1px solid var(--border);color:var(--muted)}}
.chip.pos{{color:var(--pos);border-color:var(--pos)}} .chip.neg{{color:var(--neg);border-color:var(--neg)}}
.foot{{margin-top:26px;padding-top:14px;border-top:1px solid var(--border);color:var(--muted);font-size:11.5px}}
.foot table{{max-width:520px;font-size:12px;margin-top:8px}} .foot td{{border-bottom:1px solid var(--border)}}
@media (max-width:820px){{.tiles{{grid-template-columns:repeat(2,1fr)}}.tile.span2{{grid-column:span 2}}.cols{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="wrap hidefc">
<header>
  <div><h1>Home Energy Report</h1><div class="sub">{address} · generated {generated}</div></div>
  <button class="toggle" onclick="var r=document.documentElement,d=r.getAttribute('data-theme')==='dark';r.setAttribute('data-theme',d?'light':'dark')">◑ theme</button>
</header>

<div class="headline">{headline}</div>

<div class="tabbar">
  <button class="tab on" data-t="todo">What to do</button>
  <button class="tab" data-t="current">Current performance</button>
  <button class="tab" data-t="costs">Cost breakdown</button>
  <button class="tab" data-t="timeofuse">Time of use</button>
  <button class="tab" data-t="switch">Switching</button>
  <button class="tab" data-t="info">Info</button>
</div>

<section class="tabpane active" data-t="todo">
{actions_tab}
</section>

<section class="tabpane" data-t="current">
<div class="grid tiles">{tiles}</div>
<h3 class="sec">Are you paying the right amount?</h3>
{dd_card}
<h3 class="sec">How the home uses energy — over your chosen period</h3>
<div class="ranges"><span class="rlabel">Period:</span>{range_buttons}
  <button id="fctoggle" class="rbtn" style="margin-left:auto">Show forecast</button></div>
<p class="note" style="margin:0 0 12px">These buttons drive the charts, the trend %, and Key numbers below.
  <b>Year-on-year is identical for any 12-month-plus window</b> (it always compares the same matched months) —
  pick <b>3 months</b> or <b>6 months</b> to see the trend change.</p>
{rangeviews}

<h3 class="sec">Trend by season</h3>
{season_card}

<details class="dsec"><summary>Compare years — same months side by side</summary>{compare_card}</details>
<details class="dsec"><summary>Forecast accuracy over time</summary>{tracking_card}</details>
<details class="dsec"><summary>Weather — usage vs temperature &amp; rainfall</summary>{weather_card}</details>
</section>

<section class="tabpane" data-t="costs">
<h3 class="sec">What is driving your bill</h3>
{drivers_card}
{cost_tab}
</section>

<section class="tabpane" data-t="timeofuse">
{hh_tab}
</section>

<section class="tabpane" data-t="switch">
<h3 class="sec">Best actions — ranked by £/year saved</h3>
<div class="card"><table class="acts"><tbody>{sw_actions}</tbody></table>
<p class="note" style="color:var(--pos)">{actions_note}</p>
<p class="note">Switch figures are exact for your forecast usage; behaviour figures (thermostat, cutting use) are typical estimates.</p></div>

<div class="grid tiles">{switch_tiles}</div>

<h3 class="sec">What-if — try your own rates</h3>
<div class="card wcard">
  <div class="wleft">
    <p class="note">Pick a tariff to fill the boxes, then overwrite any rate. For your forecast usage
      ({e_kwh:,} kWh electricity, {g_kwh:,} kWh gas).</p>
    <label class="wpick">Start from: <select id="wf_pick">{tariff_options}</select></label>
    <table class="wtab"><thead><tr><th></th><th>Unit (p/kWh)</th><th>Standing (p/day)</th></tr></thead>
    <tbody>
      <tr><td class="wf">Electricity</td>
        <td><input id="wf_eu" type="number" step="0.001" value="{cur_eu}"></td>
        <td><input id="wf_esc" type="number" step="0.001" value="{cur_esc}"></td></tr>
      <tr><td class="wf">Gas</td>
        <td><input id="wf_gu" type="number" step="0.001" value="{cur_gu}"></td>
        <td><input id="wf_gsc" type="number" step="0.001" value="{cur_gsc}"></td></tr>
    </tbody></table>
    <button id="wf_reset" class="rbtn">Reset to current tariff</button>
  </div>
  <div class="wright">
    <div class="wref">Your current tariff <b>{current_disp}/yr</b> &nbsp;·&nbsp;
      at renewal (+{infl_pct}%) <b>{renewal_disp}/yr</b></div>
    <div class="klabel">This tariff would cost</div>
    <div class="wbig"><b id="wcost">—</b></div>
    <div id="wsave" class="chip">—</div>
    <div id="wsave2" class="chip" style="margin-top:6px">—</div>
    <p class="note" style="margin-top:8px"><b>Renewal</b> = your current tariff if it re-prices at
      +{infl_pct}% when the fix ends (edit on the Home tab). Beating renewal means locking a new deal now pays off.</p>
    <div class="wsug"><div class="klabel">Ways to cut your bill</div><ul>{suggestions}</ul></div>
  </div>
</div>

<h3 class="sec">Cost range &amp; risk — Monte Carlo</h3>
{mc_card}
</section>

<section class="tabpane" data-t="info">
<h3 class="sec">Method</h3>
<div class="card"><p class="note">
  <b>Usage basis:</b> {method}. The forecast is a recency-weighted seasonal model (recent months
  weighted more), <b>bias-corrected</b> by a walk-forward test — at each past month the model is
  rebuilt on only-earlier data, predicted, and compared to the actual, and the average error is used
  to calibrate the forecast. The 95% band reflects that test's error spread. Gas volumes are converted
  to kWh; a supplier's calorific value varies, so figures are a close estimate, not a bill.
</p></div>
<h3 class="sec">Assumptions (from your Home tab)</h3>
<div class="card"><table><tbody>{assumptions}</tbody></table></div>
</section>
</div>
<script>
document.querySelectorAll('.rbtn[data-r]').forEach(function(b){{
  b.addEventListener('click',function(){{
    var r=b.dataset.r;
    document.querySelectorAll('.rbtn[data-r]').forEach(function(x){{x.classList.toggle('on',x.dataset.r===r);}});
    document.querySelectorAll('.rv').forEach(function(v){{v.classList.toggle('active',v.dataset.r===r);}});
  }});
}});
document.querySelectorAll('.rbtn[data-m]').forEach(function(b){{
  b.addEventListener('click',function(){{
    var k=b.dataset.m;
    document.querySelectorAll('.rbtn[data-m]').forEach(function(x){{x.classList.toggle('on',x.dataset.m===k);}});
    document.querySelectorAll('.mv').forEach(function(v){{v.classList.toggle('active',v.dataset.m===k);}});
  }});
}});
document.querySelectorAll('.rbtn[data-cl]').forEach(function(b){{
  b.addEventListener('click',function(){{
    var c=document.getElementById('costcard'); b.classList.toggle('on');
    c.classList.toggle('hide-'+b.dataset.cl, !b.classList.contains('on'));
  }});
}});
document.querySelectorAll('.rbtn[data-p]').forEach(function(b){{
  b.addEventListener('click',function(){{
    var k=b.dataset.p;
    document.querySelectorAll('.rbtn[data-p]').forEach(function(x){{x.classList.toggle('on',x.dataset.p===k);}});
    document.querySelectorAll('.pv').forEach(function(v){{v.classList.toggle('active',v.dataset.p===k);}});
  }});
}});
var _pvfc=document.getElementById('pvfc');
if(_pvfc){{_pvfc.addEventListener('click',function(){{
  var p=document.getElementById('pivotcard'); p.classList.toggle('nofc');
  var on=!p.classList.contains('nofc');
  _pvfc.textContent=on?'Hide forecast':'Add forecast'; _pvfc.classList.toggle('on',on);
}});}}
var _agg=document.getElementById('aggpick');
if(_agg){{_agg.addEventListener('change',function(){{
  var p=document.getElementById('pivotcard');
  ['q1','q2','q3','q4','h1','h2','year'].forEach(function(x){{p.classList.remove('show-'+x);}});
  if(this.value!=='none') p.classList.add('show-'+this.value);
}});}}
document.querySelectorAll('.tab').forEach(function(t){{
  t.addEventListener('click',function(){{
    var k=t.dataset.t;
    document.querySelectorAll('.tab').forEach(function(x){{x.classList.toggle('on',x.dataset.t===k);}});
    document.querySelectorAll('.tabpane').forEach(function(p){{p.classList.toggle('active',p.dataset.t===k);}});
  }});
}});
var _wx=document.getElementById('wxcard'), _wxb=document.getElementById('wxtoggle');
if(_wxb){{_wxb.addEventListener('click',function(){{
  _wx.classList.toggle('hidegas');
  var on=!_wx.classList.contains('hidegas');
  _wxb.textContent='Gas overlay: '+(on?'on':'off'); _wxb.classList.toggle('on',on);
}});}}
var _wrap=document.querySelector('.wrap'), _fcb=document.getElementById('fctoggle');
_fcb.addEventListener('click',function(){{
  _wrap.classList.toggle('hidefc');
  var showing=!_wrap.classList.contains('hidefc');
  _fcb.textContent=showing?'Hide forecast':'Show forecast';
  _fcb.classList.toggle('on',showing);
}});
var E_KWH={e_kwh}, G_KWH={g_kwh}, CUR={current_cost}, RENEWAL={renewal};
function gbp(v){{return '£'+Math.round(v).toLocaleString('en-GB');}}
function whatif(){{
  var eu=+document.getElementById('wf_eu').value||0, esc=+document.getElementById('wf_esc').value||0,
      gu=+document.getElementById('wf_gu').value||0, gsc=+document.getElementById('wf_gsc').value||0;
  var c=E_KWH*eu/100 + G_KWH*gu/100 + 365*(esc+gsc)/100;
  document.getElementById('wcost').textContent=gbp(c);
  var s=CUR-c, el=document.getElementById('wsave');
  el.textContent=(s>=0?'save '+gbp(s):gbp(-s)+' more')+' vs current';
  el.className='chip '+(s>=0?'pos':'neg');
  var s2=RENEWAL-c, el2=document.getElementById('wsave2');
  el2.textContent=(s2>=0?'save '+gbp(s2):gbp(-s2)+' more')+' vs renewal (+{infl_pct}%)';
  el2.className='chip '+(s2>=0?'pos':'neg');
  var stand=365*(esc+gsc)/100, sp=c>0?Math.round(stand/c*100):0;
  document.getElementById('sug_standing').innerHTML='Standing charges cost <b>'+gbp(stand)
    +'/yr</b> ('+sp+'% of this tariff), paid before you use any energy.';
}}
var WF_DEFAULTS={{wf_eu:{cur_eu},wf_esc:{cur_esc},wf_gu:{cur_gu},wf_gsc:{cur_gsc}}};
var TARIFFS={tariff_js};
function wfSet(eu,esc,gu,gsc){{
  document.getElementById('wf_eu').value=eu;document.getElementById('wf_esc').value=esc;
  document.getElementById('wf_gu').value=gu;document.getElementById('wf_gsc').value=gsc;whatif();
}}
document.getElementById('wf_pick').addEventListener('change',function(){{
  if(this.value==='cur'){{wfSet(WF_DEFAULTS.wf_eu,WF_DEFAULTS.wf_esc,WF_DEFAULTS.wf_gu,WF_DEFAULTS.wf_gsc);}}
  else{{var t=TARIFFS[+this.value];wfSet(t.eu,t.esc,t.gu,t.gsc);}}
}});
['wf_eu','wf_esc','wf_gu','wf_gsc'].forEach(function(id){{
  document.getElementById(id).addEventListener('input',whatif);
}});
document.getElementById('wf_reset').addEventListener('click',function(){{
  for(var k in WF_DEFAULTS){{document.getElementById(k).value=WF_DEFAULTS[k];}}
  whatif();
}});
whatif();
</script>
</body>
</html>"""
