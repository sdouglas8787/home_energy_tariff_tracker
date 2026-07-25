from __future__ import annotations
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Reading:
    """One meter reading. Electricity is always kWh; gas is a volume (m3/ft3)."""
    date: date
    fuel: str            # "Electricity" or "Gas"
    reading: float
    read_type: str       # "Actual" or "Estimated"
    meter_unit: str      # "kWh" for electricity; "m3" / "ft3" for gas


@dataclass(frozen=True)
class Tariff:
    supplier: str
    tariff_name: str
    tariff_type: str     # Fixed / Tracker / Variable
    start_date: date | None
    end_date: date | None
    elec_unit_p: float
    elec_sc_p: float
    gas_unit_p: float
    gas_sc_p: float
    exit_fee: float
    incentive: float
    notes: str
    is_current: bool = False   # tagged "Yes" in the Current? column
