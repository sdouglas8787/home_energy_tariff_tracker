from pathlib import Path

# config.py lives at  <root>/program/excel/config.py  ->  parents[2] is the project root
ROOT = Path(__file__).resolve().parents[2]
INPUT_FILE = ROOT / "data" / "input" / "Home_Energy_Inputs.xlsx"
OUTPUT_DIR = ROOT / "data" / "output"
OUTPUT_FILE = OUTPUT_DIR / "Energy_Analysis_Output.xlsx"
HTML_FILE = OUTPUT_DIR / "Energy_Report.html"
WEATHER_CACHE = ROOT / "data" / "weather_cache.json"
FORECAST_LOG = ROOT / "data" / "forecast_log.csv"
