from __future__ import annotations
from pathlib import Path
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import CellIsRule
from openpyxl.utils import get_column_letter

# ---- palette (restrained, corporate) ----
INK = "1F2A44"; NAVY = "1F3864"; BAND = "2E5395"; MUTE = "6B7280"
CARD = "F2F5FA"; RULE = "D9DEE8"
GREEN_T = "2E7D32"; GREEN_F = "E2EFDA"; RED_T = "C0392B"; RED_F = "FBE4E4"
WHITE = "FFFFFF"
GBP = '£#,##0;[Red]-£#,##0'
GBP2 = '£#,##0.00;[Red]-£#,##0.00'
KWH = '#,##0" kWh"'
NUM = '#,##0.00;[Red]-#,##0.00'

FONT = "Calibri"
SIDE = Side(style="thin", color=RULE)
BOX = Border(left=SIDE, right=SIDE, top=SIDE, bottom=SIDE)
L = Alignment(horizontal="left", vertical="center", indent=1)
LTOP = Alignment(horizontal="left", vertical="top", wrap_text=True, indent=1)
C = Alignment(horizontal="center", vertical="center")


def _base(ws):
    ws.sheet_view.showGridLines = False


def _title(ws, title, subtitle, span):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=span)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=span)
    t = ws.cell(1, 1, title)
    t.font = Font(name=FONT, size=20, bold=True, color=WHITE)
    t.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    for c in range(1, span + 1):
        ws.cell(1, c).fill = PatternFill("solid", fgColor=NAVY)
    s = ws.cell(2, 1, subtitle)
    s.font = Font(name=FONT, size=10, color=MUTE)
    s.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 34
    ws.row_dimensions[2].height = 18


def _section(ws, row, text, span):
    cell = ws.cell(row, 1, text.upper())
    cell.font = Font(name=FONT, size=11, bold=True, color=BAND)
    cell.alignment = Alignment(horizontal="left", vertical="center")
    for c in range(1, span + 1):
        ws.cell(row, c).border = Border(bottom=Side(style="thin", color=BAND))
    ws.row_dimensions[row].height = 22


def _card(ws, r, c, w, label, value, numfmt=None, color=NAVY, sub=None, sub_color=MUTE):
    for rr in range(r, r + 3):
        for cc in range(c, c + w):
            cell = ws.cell(rr, cc)
            cell.fill = PatternFill("solid", fgColor=CARD)
            cell.border = BOX
    ws.merge_cells(start_row=r, start_column=c, end_row=r, end_column=c + w - 1)
    ws.merge_cells(start_row=r + 1, start_column=c, end_row=r + 1, end_column=c + w - 1)
    ws.merge_cells(start_row=r + 2, start_column=c, end_row=r + 2, end_column=c + w - 1)
    lab = ws.cell(r, c, label.upper()); lab.font = Font(name=FONT, size=8, bold=True, color=MUTE); lab.alignment = L
    val = ws.cell(r + 1, c, value); val.font = Font(name=FONT, size=15, bold=True, color=color); val.alignment = L
    if numfmt:
        val.number_format = numfmt
    sc = ws.cell(r + 2, c, sub if sub is not None else "")
    sc.font = Font(name=FONT, size=9, color=sub_color); sc.alignment = L
    ws.row_dimensions[r].height = 15
    ws.row_dimensions[r + 1].height = 24
    ws.row_dimensions[r + 2].height = 15


def _arrow(direction):
    return {"up": "▲", "down": "▼", "flat": "▬"}.get(direction, "")


def _yoy_text(yoy):
    if not yoy:
        return "not enough history", MUTE
    a = _arrow(yoy["direction"])
    colour = RED_T if yoy["direction"] == "up" else GREEN_T if yoy["direction"] == "down" else MUTE
    return f"{a} {abs(yoy['pct']) * 100:.0f}% vs last year", colour


def _mlabel(dt):
    return dt.strftime("%b %Y")


def export_output(path, address, usage, method, monthly, comparisons, validation,
                  settings, generated, insights):
    wb = Workbook()

    # ============================ EXECUTIVE SUMMARY ============================
    ws = wb.active; ws.title = "Executive Summary"
    _base(ws)
    SPAN = 8
    for col in range(1, SPAN + 1):
        ws.column_dimensions[get_column_letter(col)].width = 15.5
    _title(ws, "Home Energy Report", f"{address}    |    Generated {generated}", SPAN)

    best = comparisons[0] if comparisons else None
    _section(ws, 4, "Headline", SPAN)
    if best:
        _card(ws, 5, 1, 2, "Recommended tariff", f"{best['Supplier']}", sub=best["Tariff_Name"])
        _card(ws, 5, 3, 2, "Expected annual cost", best["Expected_Annual_Cost_GBP"], GBP,
              sub=f"{best['Type']} tariff")
        sv = best["Saving_vs_Current_GBP"]
        _card(ws, 5, 5, 2, "Saving vs current", sv, GBP,
              color=GREEN_T if sv >= 0 else RED_T,
              sub="per year" if sv >= 0 else "more expensive")
        _card(ws, 5, 7, 2, "Monthly equivalent", best["Monthly_Equivalent_GBP"], GBP2, sub="per month")

    e_yoy, e_col = _yoy_text(insights["Electricity"]["yoy"])
    g_yoy, g_col = _yoy_text(insights["Gas"]["yoy"])
    gas_worst = insights["Gas"]["worst_month"]
    gas_best = insights["Gas"]["best_month"]
    _section(ws, 9, "Usage outlook", SPAN)
    _card(ws, 10, 1, 2, "Forecast electricity", usage[0], KWH, sub=e_yoy, sub_color=e_col)
    _card(ws, 10, 3, 2, "Forecast gas", usage[1], KWH, sub=g_yoy, sub_color=g_col)
    if gas_worst:
        _card(ws, 10, 5, 2, "Peak gas month", f"{_mlabel(gas_worst[0])}",
              sub=f"{gas_worst[3]:.0f} kWh/day avg")
    if gas_best:
        _card(ws, 10, 7, 2, "Lightest gas month", f"{_mlabel(gas_best[0])}",
              sub=f"{gas_best[3]:.0f} kWh/day avg")

    _section(ws, 14, "Recommendation", SPAN)
    ws.merge_cells(start_row=15, start_column=1, end_row=16, end_column=SPAN)
    if best:
        sv = best["Saving_vs_Current_GBP"]
        verb = f"save about £{sv:,.0f} a year" if sv >= 0 else f"cost about £{-sv:,.0f} a year more"
        narrative = (f"Switching to {best['Supplier']} ({best['Tariff_Name']}) is expected to "
                     f"{verb} versus your current tariff, at £{best['Expected_Annual_Cost_GBP']:,.0f} "
                     f"per year (£{best['Monthly_Equivalent_GBP']:,.0f}/month). Electricity use is "
                     f"trending {insights['Electricity']['yoy']['direction'] if insights['Electricity']['yoy'] else 'flat'} "
                     f"year-on-year and gas "
                     f"{insights['Gas']['yoy']['direction'] if insights['Gas']['yoy'] else 'flat'}. "
                     f"Usage basis: {method.lower()}.")
    else:
        narrative = "No tariffs entered — add options on the Tariffs tab to see a recommendation."
    nc = ws.cell(15, 1, narrative)
    nc.font = Font(name=FONT, size=10, color=INK); nc.alignment = LTOP
    ws.row_dimensions[15].height = 30

    _section(ws, 18, "Lowest-cost options", SPAN)
    ws.append([]) if False else None
    hdr = ["Supplier", "Tariff", "Type", "Annual cost", "Saving vs current", "Monthly"]
    for i, h in enumerate(hdr, 1):
        cell = ws.cell(19, i, h)
        cell.fill = PatternFill("solid", fgColor=NAVY); cell.font = Font(name=FONT, bold=True, color=WHITE); cell.alignment = C
    row = 20
    for r in comparisons[:6]:
        ws.cell(row, 1, r["Supplier"]); ws.cell(row, 2, r["Tariff_Name"]); ws.cell(row, 3, r["Type"])
        ws.cell(row, 4, r["Expected_Annual_Cost_GBP"]).number_format = GBP
        sc = ws.cell(row, 5, r["Saving_vs_Current_GBP"]); sc.number_format = GBP
        sc.font = Font(name=FONT, color=GREEN_T if r["Saving_vs_Current_GBP"] >= 0 else RED_T)
        ws.cell(row, 6, r["Monthly_Equivalent_GBP"]).number_format = GBP2
        for c in range(1, 7):
            ws.cell(row, c).border = BOX
        row += 1

    if comparisons:
        chart = BarChart(); chart.type = "bar"; chart.title = "Expected annual cost (£)"
        chart.legend = None
        n = min(6, len(comparisons))
        chart.add_data(Reference(ws, min_col=4, min_row=19, max_row=19 + n), titles_from_data=True)
        chart.set_categories(Reference(ws, min_col=1, min_row=20, max_row=19 + n))
        chart.height = 6.5; chart.width = 18
        ws.add_chart(chart, f"A{row + 1}")

    # =============================== USAGE INSIGHTS ===============================
    ws = wb.create_sheet("Usage Insights")
    _base(ws)
    for col in range(1, 9):
        ws.column_dimensions[get_column_letter(col)].width = 15.5
    _title(ws, "Usage Insights", "Seasonality, extremes and year-on-year trend", 8)

    _section(ws, 4, "Seasonality — average kWh per day by month", 8)
    ws.cell(5, 1, "Month"); ws.cell(5, 2, "Electricity"); ws.cell(5, 3, "Gas")
    for c in range(1, 4):
        cell = ws.cell(5, c); cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.font = Font(name=FONT, bold=True, color=WHITE); cell.alignment = C
    es = insights["Electricity"]["seasonality"]; gs = insights["Gas"]["seasonality"]
    from model.calculations import MONTHS
    for m in range(1, 13):
        r = 5 + m
        ws.cell(r, 1, MONTHS[m]).alignment = C
        ec = ws.cell(r, 2, round(es.get(m, 0), 1)); ec.number_format = "0.0"; ec.alignment = C
        gc = ws.cell(r, 3, round(gs.get(m, 0), 1)); gc.number_format = "0.0"; gc.alignment = C
        for c in range(1, 4):
            ws.cell(r, c).border = BOX
    chart = LineChart(); chart.title = "Average kWh/day through the year"; chart.y_axis.title = "kWh/day"
    chart.add_data(Reference(ws, min_col=2, max_col=3, min_row=5, max_row=17), titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=1, min_row=6, max_row=17))
    chart.height = 7.5; chart.width = 16
    ws.add_chart(chart, "E5")

    _section(ws, 20, "Highlights", 8)
    hi = [["", "Electricity", "Gas"]]

    def _mo(x):
        return f"{_mlabel(x[0])}  ({x[3]:.1f}/day)" if x else "—"

    def _dy(x):
        return f"{x[0]:%d %b %Y}  ({x[1]:.1f})" if x else "—"

    ei, gi = insights["Electricity"], insights["Gas"]
    rows = [
        ["Lightest month (avg/day)", _mo(ei["best_month"]), _mo(gi["best_month"])],
        ["Heaviest month (avg/day)", _mo(ei["worst_month"]), _mo(gi["worst_month"])],
        ["Lowest-use day (kWh)", _dy(ei["best_day"]), _dy(gi["best_day"])],
        ["Highest-use day (kWh)", _dy(ei["worst_day"]), _dy(gi["worst_day"])],
        ["Year-on-year trend", _yoy_text(ei["yoy"])[0], _yoy_text(gi["yoy"])[0]],
    ]
    ws.cell(21, 1, "");
    for i, h in enumerate(["Metric", "Electricity", "Gas"], 1):
        cell = ws.cell(21, i, h); cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.font = Font(name=FONT, bold=True, color=WHITE); cell.alignment = C
    for ri, rvals in enumerate(rows, 22):
        for ci, v in enumerate(rvals, 1):
            cell = ws.cell(ri, ci, v)
            cell.alignment = C if ci > 1 else L
            cell.border = BOX
            if rvals[0] == "Year-on-year trend" and ci > 1:
                yoy = (ei if ci == 2 else gi)["yoy"]
                if yoy:
                    cell.font = Font(name=FONT, bold=True,
                                     color=RED_T if yoy["direction"] == "up" else GREEN_T if yoy["direction"] == "down" else MUTE)
        ws.column_dimensions["A"].width = 26
    note = ws.cell(28, 1, "Note: usage is spread evenly between meter readings, so daily figures are "
                          "only as precise as how often you read the meter (gas is read less often than electricity).")
    ws.merge_cells("A28:H29"); note.font = Font(name=FONT, size=9, italic=True, color=MUTE); note.alignment = LTOP

    # ============================== TARIFF COMPARISON ==============================
    ws = wb.create_sheet("Tariff Comparison")
    _base(ws)
    keys = list(comparisons[0].keys()) if comparisons else []
    if keys:
        for i, k in enumerate(keys, 1):
            cell = ws.cell(1, i, k); cell.fill = PatternFill("solid", fgColor=NAVY)
            cell.font = Font(name=FONT, bold=True, color=WHITE); cell.alignment = C
        for r in comparisons:
            ws.append([r[k] for k in keys])
        for col_idx, key in enumerate(keys, start=1):
            fmt = GBP2 if key.endswith("_GBP") else (NUM if key.endswith(("_p", "_p_day")) else None)
            if not fmt:
                continue
            for row in ws.iter_rows(min_col=col_idx, max_col=col_idx, min_row=2):
                for cell in row:
                    if isinstance(cell.value, (int, float)):
                        cell.number_format = fmt
        save_col = keys.index("Saving_vs_Current_GBP") + 1
        letter = get_column_letter(save_col)
        rng = f"{letter}2:{letter}{len(comparisons) + 1}"
        ws.conditional_formatting.add(rng, CellIsRule(operator="greaterThan", formula=["0"], fill=PatternFill("solid", fgColor=GREEN_F)))
        ws.conditional_formatting.add(rng, CellIsRule(operator="lessThan", formula=["0"], fill=PatternFill("solid", fgColor=RED_F)))
    _autosize(ws)
    ws.freeze_panes = "A2"

    # ============================== MONTHLY USAGE ==============================
    ws = wb.create_sheet("Monthly Usage")
    _base(ws)
    for i, h in enumerate(["Month", "Electricity_kWh", "Gas_kWh", "Covered_Days"], 1):
        cell = ws.cell(1, i, h); cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.font = Font(name=FONT, bold=True, color=WHITE); cell.alignment = C
    for r in monthly:
        ws.append(r)
    for c in ws["A"][1:]:
        c.number_format = "mmm yyyy"
    for c in ws["B"][1:] + ws["C"][1:]:
        c.number_format = "0.0"
    if len(monthly) > 1:
        chart = LineChart(); chart.title = "Monthly usage (kWh)"; chart.y_axis.title = "kWh"
        chart.add_data(Reference(ws, min_col=2, max_col=3, min_row=1, max_row=len(monthly) + 1), titles_from_data=True)
        chart.set_categories(Reference(ws, min_col=1, min_row=2, max_row=len(monthly) + 1))
        chart.height = 8; chart.width = 15; ws.add_chart(chart, "F2")
    _autosize(ws)
    ws.freeze_panes = "A2"

    # ============================== READING VALIDATION ==============================
    ws = wb.create_sheet("Reading Validation")
    _base(ws)
    for i, h in enumerate(["Fuel", "Previous_Date", "Current_Date", "Days", "Reading_Delta", "Status"], 1):
        cell = ws.cell(1, i, h); cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.font = Font(name=FONT, bold=True, color=WHITE); cell.alignment = C
    for r in validation:
        ws.append(r)
    _autosize(ws)
    ws.freeze_panes = "A2"

    # ============================== ASSUMPTIONS ==============================
    ws = wb.create_sheet("Assumptions")
    _base(ws)
    for i, h in enumerate(["Setting", "Value"], 1):
        cell = ws.cell(1, i, h); cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.font = Font(name=FONT, bold=True, color=WHITE); cell.alignment = C
    _sensitive = ("MPAN", "MPRN", "GUID", "IHD", "MAC")   # keep meter IDs out of the shared output
    for k, v in settings.items():
        if any(t in str(k).upper() for t in _sensitive):
            continue
        ws.append([k, v])
    _autosize(ws)

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def _autosize(ws, max_width=34):
    for index, column in enumerate(ws.iter_cols(), start=1):
        letter = get_column_letter(index)
        width = min(max((len(str(c.value)) if c.value is not None else 0) for c in column) + 2, max_width)
        ws.column_dimensions[letter].width = max(10, width)
