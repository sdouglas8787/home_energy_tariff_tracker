"""Write derived meter readings back into the input workbook, in their own column.

The workbook is yours -- this only ever adds to a column named Derived_Reading,
never to the column you type in. Where a date has no reading of yours, the run
uses the derived one; where it has both, they get compared and any disagreement
is reported. Fill a real reading in later and the derived value stays beside it
as the thing to check against.

Two safety rules, because this edits a file you own:
  * if Excel has the workbook open, nothing is written -- Excel would overwrite it
    on save and the run would look like it had worked
  * the first write of any day copies the workbook aside first
"""
from __future__ import annotations
import shutil
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

NAVY = "FF17365D"
DERIVED_FILL = "FFEFEFEF"      # grey, not the yellow that means "you type here"
HEADERS = {"Electricity": "Derived_Reading_kWh", "Gas": "Derived_Reading"}
DATE_COL = 1


def is_open_in_excel(path):
    """Excel leaves a ~$name.xlsx lock file beside an open workbook."""
    p = Path(path)
    return (p.parent / f"~${p.name}").exists()


def _backup(path, backup_dir):
    dest = Path(backup_dir) / f"{Path(path).stem}_{date.today():%Y-%m-%d}{Path(path).suffix}"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    return dest


def _column_for(ws, header):
    """Find the derived column by name, or add it after the last used one."""
    for c in range(1, ws.max_column + 1):
        if str(ws.cell(1, c).value or "").strip() == header:
            return c
    col = ws.max_column + 1
    cell = ws.cell(1, col, header)
    like = ws.cell(1, col - 1)
    cell.fill = PatternFill("solid", fgColor=NAVY)
    cell.font = Font(name=like.font.name, bold=True, color="FFFFFFFF")
    cell.alignment = Alignment(horizontal="center")
    cell.border = like.border.copy()
    ws.column_dimensions[cell.column_letter].width = 18
    return col


def _row_index(ws):
    """{date: row} for rows that have a date, plus the first free row."""
    rows, first_free = {}, None
    for r in range(2, ws.max_row + 2):
        v = ws.cell(r, DATE_COL).value
        if v in (None, ""):
            first_free = first_free or r
            continue
        d = v.date() if isinstance(v, datetime) else v
        rows[d] = r
        first_free = None
    return rows, first_free or ws.max_row + 1


def write_derived(path, derived, backup_dir, log=print):
    """Put the derived readings into the workbook. Returns (updated, added) counts.

    Existing rows get their derived value filled in beside whatever you typed; dates
    with no row at all are appended, date and derived value only, leaving your reading
    column empty for you to complete if you ever want to.
    """
    if is_open_in_excel(path):
        log("Derived readings: workbook is open in Excel — nothing written. "
            "Close it and run again.")
        return 0, 0
    if not any(derived.values()):
        return 0, 0

    _backup(path, backup_dir)
    wb = load_workbook(path)
    updated = added = 0

    for fuel, values in derived.items():
        if fuel not in wb.sheetnames or not values:
            continue
        ws = wb[fuel]
        col = _column_for(ws, HEADERS.get(fuel, "Derived_Reading"))
        rows, free = _row_index(ws)
        template = ws.cell(2, DATE_COL)                 # copy the date formatting in use
        number_format = ws.cell(2, 2).number_format

        for d in sorted(values):
            row = rows.get(d)
            if row is None:
                row = free
                free += 1
                dc = ws.cell(row, DATE_COL, datetime.combine(d, datetime.min.time()))
                dc.number_format = template.number_format
                dc.border = template.border.copy()
                dc.fill = template.fill.copy()
                added += 1
            else:
                updated += 1
            cell = ws.cell(row, col, round(values[d], 2))
            cell.number_format = number_format
            cell.fill = PatternFill("solid", fgColor=DERIVED_FILL)

    wb.save(path)
    return updated, added
