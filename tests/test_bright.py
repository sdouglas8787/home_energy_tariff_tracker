"""Checks for the Bright / Glowmarkt API fetch and how it merges with the inbox."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "program"))

from model import bright
from model.hh import import_files, load_store


# --- credentials --------------------------------------------------------------

def test_account_read_from_key_value_file(tmp_path):
    f = tmp_path / "acct.txt"
    f.write_text("# a comment\nusername = me@example.com\npassword = s3cret\n\n")
    acct = bright.read_account(f)
    assert acct["username"] == "me@example.com"
    assert acct["password"] == "s3cret"
    assert acct["application_id"] == bright.APP_ID       # falls back to the default


def test_untouched_template_and_missing_file_are_ignored(tmp_path):
    template = Path(__file__).resolve().parents[1] / "data/input/bright_account.example.txt"
    assert bright.read_account(template) is None         # placeholders must not count as set up
    assert bright.read_account(tmp_path / "nope.txt") is None
    blank = tmp_path / "blank.txt"
    blank.write_text("username = me@example.com\npassword =\n")
    assert bright.read_account(blank) is None


# --- resource classification --------------------------------------------------

def test_only_consumption_resources_are_used():
    assert bright._fuel_of("electricity.consumption") == "Electricity"
    assert bright._fuel_of("gas.consumption") == "Gas"
    # cost resources are excluded: they lump the standing charge onto one point in
    # the day, so any sub-day slice of them is wrong. Costing happens from Tariffs.
    assert bright._fuel_of("electricity.consumption.cost") is None
    assert bright._fuel_of("gas.consumption.cost") is None
    assert bright._fuel_of("electricity.export") is None


# --- timestamp frame ----------------------------------------------------------

def _epoch(iso):
    return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp())


def test_local_timestamps_are_shifted_back_in_summer_only():
    summer = _epoch("2026-07-01T12:00:00")               # BST: London is UTC+1
    assert bright._as_utc(summer) == summer - 3600
    winter = _epoch("2026-01-01T12:00:00")               # GMT: nothing to correct
    assert bright._as_utc(winter) == winter


def test_mode_detection_matches_readings_against_known_history():
    base = _epoch("2026-07-01T00:00:00")
    stored = {base + i * 1800: 0.1 + i * 0.01 for i in range(200)}
    # API hands back the same series stamped in London wall-clock time (an hour ahead)
    local_pairs = [(e + 3600, v) for e, v in stored.items()]
    assert bright._detect_mode(local_pairs, stored) == "local"
    assert bright._detect_mode([(e, v) for e, v in stored.items()], stored) == "utc"


def test_mode_detection_declines_to_guess_without_evidence():
    base = _epoch("2026-01-01T00:00:00")                 # GMT: both readings identical
    stored = {base + i * 1800: 0.2 for i in range(200)}
    assert bright._detect_mode([(e, v) for e, v in stored.items()], stored) is None
    winter = {base + i * 1800: 0.2 for i in range(4)}    # too little overlap to judge
    assert bright._detect_mode([(e, v) for e, v in winter.items()], winter) is None


# --- the readings query ---

def test_readings_are_requested_in_utc_with_gaps_marked(monkeypatch):
    sent = {}

    def fake_call(path, token=None, app_id=None, body=None, params=None, timeout=30):
        sent.update(path=path, params=params)
        return {"data": [[1767225600, 0.25], [1767227400, None], [1767229201, 0.1],
                         [1767231000, -1.0], [1767232800, 0.4]]}

    monkeypatch.setattr(bright, "_call", fake_call)
    start = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
    pairs = bright._readings("tok", "app", "res-1", start, datetime(2026, 7, 11, tzinfo=timezone.utc))

    # offset 0 keeps the request in the same UTC frame as the stored CSV history,
    # and nulls=1 stops missing half-hours arriving as a convincing 0.0
    assert sent["params"]["offset"] == 0
    assert sent["params"]["nulls"] == 1
    assert sent["params"]["from"] == "2026-07-01T00:00:00"      # UTC, not 01:00 BST
    assert sent["params"]["period"] == "PT30M"
    # null, unaligned and negative rows are all dropped
    assert pairs == [(1767225600, 0.25), (1767232800, 0.4)]


# --- merging with the inbox ---------------------------------------------------

def test_api_records_merge_without_duplicating_the_csv_route(tmp_path):
    store = tmp_path / "store.csv"
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    base = _epoch("2026-02-01T00:00:00")
    (inbox / "electricity consumption.csv").write_text(
        "epochTimestamp,kWh,dateTime\n"
        f"{base},0.20,x\n{base + 1800},0.30,x\n")
    # the API returns one half-hour the CSV already had, plus one it did not
    api = [("Electricity", base + 1800, 0.30), ("Electricity", base + 3600, 0.40)]

    rows, files, rejected = import_files(inbox, store, tmp_path / "archive", extra=api)
    assert files == 1
    assert sorted(r[1] for r in rows) == [base, base + 1800, base + 3600]
    assert not rejected

    # a second run with the same API data adds nothing and leaves the store alone
    rows2, files2, _ = import_files(inbox, store, tmp_path / "archive", extra=api)
    assert files2 == 0
    assert len(load_store(store)) == len(rows) == len(rows2)


def test_first_reading_reads_the_nested_timestamp(monkeypatch):
    # the API answers {"data": {"firstTs": ...}}, not a bare value
    monkeypatch.setattr(bright, "_call", lambda *a, **k: {
        "status": "OK", "classifier": "gas.consumption", "data": {"firstTs": 1750806000}})
    got = bright.first_reading("tok", "app", "res-1")
    assert got is not None and got.year == 2025 and got.month == 6
