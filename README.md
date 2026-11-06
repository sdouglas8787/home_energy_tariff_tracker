# Home Energy Tariff Tracker

Work out your household's real electricity and gas usage from meter readings,
forecast a full year, and see which UK dual-fuel tariff is cheapest.

**One workbook = one home.** Everything you touch lives in the `data` folder.

## Folders

```
data/
  input/               Home_Energy_Inputs.xlsx   (you EDIT this)
                       bright_account.txt        (optional, see below)
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
3. The report opens by itself when the run finishes. (Run with `--no-open` if you
   would rather it didn't. If you keep the report open in a browser tab, remember
   it is a file on disk — the tab needs a refresh to show a new run.)

The output is a **single file that is overwritten every run** — it always shows
the latest picture, with a "Generated" date/time on the Dashboard. There is no
build-up of dated files to tidy.

## Half-hourly data: automatic, or drag-and-drop

Your smart meter's half-hourly readings are what power the load profile, the
"always-on" figure, the time-of-use savings and the heating/base split. There
are two ways to get them in, and you can use either or both.

**Automatic (electricity and gas).** Rename
`data/input/bright_account.example.txt` to `bright_account.txt` and put in the
email and password you use in the Bright app. From then on every run downloads
whatever is new by itself. The first run reaches back about a year and takes a
few minutes; after that it is quick. The file stays on your computer and is
excluded from git — don't share it or put it in a screenshot.

**Manual.** Export CSVs from Bright and drop them in `data/half-hourly-inbox/`,
as before. Export at **half-hourly** granularity: a monthly or daily export has
the right column names but numbers far too big, and they'll be thrown out as
implausible.

Nothing breaks if you skip both, or if the login fails, or you're offline — the
run simply carries on without new half-hourly data. Readings that arrive by both
routes are stored once, so there's no double counting.

## Derived readings

A meter reading is a running total, and half-hourly data is what happened in each
half hour — so given one real reading to anchor on, the half-hours since it add up
to what the meter must say now. The run writes that into a **Derived_Reading**
column on the Electricity and Gas tabs, and uses it on any date where you have not
entered a reading of your own. Your readings always win; the derived column is
never written over the one you type in.

This does two things:

- **Your forecast stops waiting for you.** It used to run only as far as your last
  meter reading. Now it runs to the last day the half-hourly data covers.
- **It checks your readings.** Between two readings you took, the half-hours in
  between should add up to the difference. When they don't, one of them is wrong —
  a transposed digit, a misread dial — and it is flagged in Reading_Validation.
  Fill in a real reading next to a derived one later and the same check applies.

Derived rows are laid down weekly rather than daily, so the tabs stay readable, and
only where every day since the anchor was fully reported. Both fuels are extended
to the same date: a month's coverage is counted across both at once, so letting one
run ahead of the other would make the forecast think a month was near-zero.

The workbook is copied to `data/system/workbook-backups/` before the first write of
any day. If Excel has the workbook open, nothing is written and the run says so —
close it and run again.

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

## How tariffs are costed

Every option is priced across **the same next 365 days**, not as a standalone rate
card. That matters when your current deal is ending:

- The days still to run on your current fix are included in *every* option, because
  you are having those days whatever you decide.
- When your fix ends, the option you are considering takes over.
- If you do nothing, your own rates carry on at the **`Assumed yearly price rise %
  at renewal`** from the Home tab. A rate you agreed two years ago is not one you
  get to keep, so that — not today's expiring rate — is what everything is ranked
  against.
- Usage is spread across the year using the seasonal forecast, so a switch landing
  in October is costed differently from one landing in June.
- A tariff you cannot start yet is not offered as a switch-today option. Where one
  is available now, it is also costed with your current tariff's exit fee, so you
  can see whether buying out early pays.

Without this, an old fix looks unbeatable right up to the day it lapses and the
tool reports a saving of £0 for switching — while the same page tells you to lock
in a new deal. Both figures now come from the same calculation.

## What the output shows

- **Dashboard** — forecast usage, the best-value tariff, and a cost chart.
- **Monthly_Usage** — kWh per month for each fuel, with a trend chart.
- **Tariff_Comparison** — every tariff costed and ranked, savings vs your
  current tariff shaded green/red.
- **Reading_Validation** — flags gaps, estimated reads, and meter resets.
- **Assumptions** — the settings used, for transparency.

Three more sheets in the Excel are plain tidy tables, there to be pivoted rather
than read: **Daily Usage** (one row per day per fuel, with a Complete_Day flag),
**Load Profile** (average kWh per half-hour slot by fuel and weekday), and
**Half Hourly** (every interval, with weekday/hour/month columns already broken
out). No merged cells or banners, and an AutoFilter on each — select the sheet and
insert a PivotTable. Daily Usage reconciles exactly to Half Hourly.

## Moving house

1. `File → Save As` the input workbook under the new address.
2. Delete the old readings and tariffs (clear the yellow cells).
3. Enter the new meter's opening reading and the new tariffs.

The old home stays intact in its own file as your history.

## Gas accuracy

Gas meters record volume, not energy. The default factor is 11.1868 kWh per m³.
Suppliers use a slightly varying calorific value, so this is a close analytical
estimate rather than a replacement for the actual bill.
