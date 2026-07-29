from pathlib import Path

# config.py lives at  <root>/program/excel/config.py  ->  parents[2] is the project root
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

# --- the two places you touch ---
INPUT_FILE = DATA / "input" / "Home_Energy_Inputs.xlsx"      # you edit this
HH_INBOX = DATA / "half-hourly-inbox"                        # drag Bright CSV exports here

# --- what you open (generated) ---
REPORTS = DATA / "reports"
OUTPUT_FILE = REPORTS / "Energy_Analysis_Output.xlsx"
HTML_FILE = REPORTS / "Energy_Report.html"

# --- auto-managed, leave alone ---
SYSTEM = DATA / "system"
WEATHER_CACHE = SYSTEM / "weather_cache.json"
FORECAST_LOG = SYSTEM / "forecast_log.csv"
HH_STORE = SYSTEM / "half_hourly_store.csv"
HH_ARCHIVE = SYSTEM / "half-hourly-archive"                  # inbox files filed here after import

# backwards-compat alias
OUTPUT_DIR = REPORTS
