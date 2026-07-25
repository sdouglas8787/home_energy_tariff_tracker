# Data dictionary

All input lives in `data/input/Home_Energy_Inputs.xlsx`. Only the yellow cells
are for you to edit.

## Home
| Setting | Meaning |
|---|---|
| Address | Label only; does not affect the maths. |
| Gas_kWh_per_Unit | kWh per unit of gas volume. 11.1868 for a metric (m³) meter. |
| Analysis_End_Date | The "as of" date for the 12-month forecast. Blank = latest reading. |
| Fallback_Annual_Electricity_kWh | Used only when there are too few readings. |
| Fallback_Annual_Gas_kWh | Used only when there are too few readings. |
| Forecast_Electricity_Adjustment | Fractional tweak to expected usage, e.g. -0.05 for 5% lower. |
| Forecast_Gas_Adjustment | Fractional tweak to expected gas usage. |
| Include_Exit_Fee | Yes/No — add each tariff's exit fee to its cost. |
| Include_Incentive | Yes/No — subtract each tariff's sign-up incentive. |

## Electricity / Gas
| Column | Meaning |
|---|---|
| Date | Date of the meter read. |
| Meter_Reading(_kWh) | The cumulative number shown on the meter. Electricity is kWh; gas is a volume. |
| Meter_Unit (gas only) | m³ or ft³. |
| Read_Type | Actual or Estimated. Estimated reads are flagged in validation. |

## Tariffs
Rates are entered in **pence**; exit fees and incentives in **pounds**. Each
supplier row carries separate electricity and gas standing charges. A supplier
named exactly `Current tariff` is used as the savings baseline.
