# Home Energy Tariff Tracker

Work out your household's real electricity and gas usage from meter readings,
forecast a full year, and see which UK dual-fuel tariff is cheapest.

**One workbook = one home.** Everything you touch lives in the `data` folder.

## Folders

```
data/
  input/               Home_Energy_Inputs.xlsx   (you EDIT this)
  half-hourly-inbox/   drag Bright/Glow CSV exports here (auto-filed after a run)
  reports/             Energy_Report.html + Excel (you OPEN these)
  system/              caches, logs, half-hourly history (LEAVE ALONE)
run/      double-click to set up and run
program/  the code (model = the maths, excel = reading/writing the workbook)
info/     notes and an archived copy of the old workbook
tests/    automated checks
```
See `data/READ ME FIRST.txt` for what goes where.

## First-time setup (once)

- **Mac:** double-click `run/setup_mac.command`
- **Windows:** double-click `run/setup_windows.bat`

This builds a local Python environment and installs what's needed.

## Each time you want an update

1. Open `data/input/Home_Energy_Inputs.xlsx` and fill in the **yellow cells**.
2. Run it:
   - **Mac:** double-click `run/run_mac.command`
   - **Windows:** double-click `run/run_windows.bat`
3. Open `data/reports/Energy_Report.html`.

The output is a **single file that is overwritten every run** — it always shows
the latest picture, with a "Generated" date/time on the Dashboard. There is no
build-up of dated files to tidy.

## The input workbook (4 tabs)

- **Home** — address, gas conversion factor, forecast assumptions, and the
  Yes/No switches for exit fees and incentives. `Analysis_End_Date` can be left
  blank to use your latest reading automatically.
- **Electricity** — one row per meter read: date and the kWh number on the meter.
- **Gas** — one row per meter read: date, the number on the meter, and the unit
  (m³ or ft³). Conversion to kWh is automatic.
- **Tariffs** — one row per supplier option. Unit rates and standing charges are
  entered in **pence**; exit fees and incentives in **pounds**. Add a row to add
  an option — nothing else needs changing.

Only the yellow cells are for you. To add readings or tariffs, just append rows.

## What the output shows

- **Dashboard** — forecast usage, the best-value tariff, and a cost chart.
- **Monthly_Usage** — kWh per month for each fuel, with a trend chart.
- **Tariff_Comparison** — every tariff costed and ranked, savings vs your
  current tariff shaded green/red.
- **Reading_Validation** — flags gaps, estimated reads, and meter resets.
- **Assumptions** — the settings used, for transparency.

## Moving house

1. `File → Save As` the input workbook under the new address.
2. Delete the old readings and tariffs (clear the yellow cells).
3. Enter the new meter's opening reading and the new tariffs.

The old home stays intact in its own file as your history.

## Gas accuracy

Gas meters record volume, not energy. The default factor is 11.1868 kWh per m³.
Suppliers use a slightly varying calorific value, so this is a close analytical
estimate rather than a replacement for the actual bill.
