from __future__ import annotations
from datetime import datetime, date
from pathlib import Path
from openpyxl import load_workbook
from model.models import Reading, Tariff


def as_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def as_float(value, default=0.0):
    return float(value) if value not in (None, "") else default


def load_inputs(path: Path):
    """Read the four-tab input workbook.

    Returns (settings, readings, tariffs). One workbook = one home, so there
    is no property key on any row.
    """
    wb = load_workbook(path, data_only=True)

    settings = {}
    for row in wb["Home"].iter_rows(min_row=2, values_only=True):
        if row and row[0]:
            settings[str(row[0])] = row[1]

    readings = []
    for row in wb["Electricity"].iter_rows(min_row=2, values_only=True):
        if not row[0] or row[1] in (None, ""):
            continue
        readings.append(Reading(as_date(row[0]), "Electricity", as_float(row[1]),
                                 str(row[2] or "Actual"), "kWh"))

    for row in wb["Gas"].iter_rows(min_row=2, values_only=True):
        if not row[0] or row[1] in (None, ""):
            continue
        readings.append(Reading(as_date(row[0]), "Gas", as_float(row[1]),
                                 str(row[3] or "Actual"), str(row[2] or "m3")))

    tariffs = []
    # Tariffs has a two-row banded header (ELECTRICITY / GAS), data from row 3.
    # Columns: Current? | Supplier | Tariff_Name | Type | Start | End |
    #          Elec_Unit | Elec_SC | Gas_Unit | Gas_SC | Exit | Incentive | Notes
    for row in wb["Tariffs"].iter_rows(min_row=3, values_only=True):
        if not row[1]:                       # skip rows with no supplier
            continue
        tariffs.append(Tariff(
            str(row[1]), str(row[2] or ""), str(row[3] or ""), as_date(row[4]), as_date(row[5]),
            as_float(row[6]), as_float(row[7]), as_float(row[8]), as_float(row[9]),
            as_float(row[10]), as_float(row[11]), str(row[12] or ""),
            is_current=str(row[0]).strip().lower() in {"yes", "y", "true", "1"},
        ))

    bills = []
    if "Bills" in wb.sheetnames:
        for row in wb["Bills"].iter_rows(min_row=2, values_only=True):
            if not row[0] or row[1] in (None, ""):
                continue
            bills.append((as_date(row[0]), as_float(row[1])))
        bills.sort(key=lambda b: b[0])

    return settings, readings, tariffs, bills
