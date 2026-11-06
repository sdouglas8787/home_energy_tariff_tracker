"""Fetch half-hourly readings straight from the Bright / Glowmarkt API.

Same data as the manual CSV export, without the drag-and-drop: authenticate,
find your electricity and gas consumption resources, and pull every half-hour
since the last one already in the store. Results are merged by hh.import_files
alongside anything sitting in the inbox, so the API is an addition, never a
requirement -- no credentials, no network, or a bad login just means the run
carries on with the CSV path exactly as before.

Only the *consumption* resources (kWh) are read. Glowmarkt also exposes .cost
resources, but they apply standing charges as a whole-day lump rather than
spreading them across the day, so any period shorter than a day is missing its
share. Costs here come from the Tariffs tab instead, which handles standing
charges properly -- don't swap in the cost endpoints without accounting for it.

Credentials live in data/input/bright_account.txt (gitignored), token and
resource ids are cached in data/system/bright_state.json. The token Glowmarkt
issues lasts 7 days; we reuse it until an hour before it expires.

API reference: https://bitbucket.org/ijosh/brightglowmarkt/src/master/
"""
from __future__ import annotations
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

API = "https://api.glowmarkt.com/api/v0-1"
APP_ID = "b0f1b774-a586-4f72-9edd-27ead8aa7a8d"     # Bright's public sample application id
LONDON = ZoneInfo("Europe/London")
MAX_DAYS = 10               # the API caps a PT30M query at 10 days per request
BACKFILL_DAYS = 400         # first run: reach back past Bright's ~13-month window
HALF_HOUR = 1800


# --- credentials & cached state -------------------------------------------------

def read_account(path):
    """Read data/input/bright_account.txt -- `key = value` lines, # for comments.

    Returns None when the file is missing or the fields are still the placeholders,
    which is the signal to skip the API entirely and use the inbox.
    """
    try:
        text = Path(path).read_text()
    except Exception:
        return None
    acct = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        acct[k.strip().lower()] = v.strip()
    user, pwd = acct.get("username", ""), acct.get("password", "")
    if not user or not pwd or "@" not in user or user.startswith("your"):
        return None
    return {"username": user, "password": pwd,
            "application_id": acct.get("application_id") or APP_ID}


def _load_state(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return {}


def _save_state(path, state):
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, indent=2))
    except Exception:
        pass


# --- API plumbing ---------------------------------------------------------------

def _call(path, token=None, app_id=APP_ID, body=None, params=None, timeout=30):
    url = f"{API}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"Content-Type": "application/json", "applicationId": app_id}
    if token:
        headers["token"] = token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _authenticate(account):
    d = _call("auth", app_id=account["application_id"],
              body={"username": account["username"], "password": account["password"],
                    "applicationId": account["application_id"]})
    if not d.get("valid") or not d.get("token"):
        raise RuntimeError(d.get("error") or "login rejected")
    return d["token"], int(d.get("exp") or 0)


def _token(account, state):
    """Reuse the cached token until an hour before it expires, else log in again."""
    tok, exp = state.get("token"), state.get("token_exp", 0)
    if tok and exp > time.time() + 3600:
        return tok, False
    tok, exp = _authenticate(account)
    state["token"], state["token_exp"] = tok, exp
    return tok, True


def _fuel_of(classifier, name=""):
    s = f"{classifier} {name}".lower()
    if "cost" in s:                       # cost resources: see the module docstring
        return None
    if "consumption" not in s:
        return None
    if "electricity" in s or "elec" in s:
        return "Electricity"
    if "gas" in s:
        return "Gas"
    return None


def list_resources(token, app_id=APP_ID):
    """Every electricity/gas consumption resource on the account.

    Returns [{"id", "fuel", "unit", "name"}]. Walks the virtual entities, then asks
    each resource for its classifier and baseUnit so we know the fuel and whether
    the meter is reporting kWh or volume.
    """
    out = []
    for ve in _call("virtualentity/", token, app_id) or []:
        for res in ve.get("resources") or []:
            rid = res.get("resourceId")
            if not rid:
                continue
            classifier, name, unit = res.get("classifier"), res.get("name", ""), res.get("baseUnit")
            if not classifier or not unit:
                try:
                    full = _call(f"resource/{rid}", token, app_id)
                    classifier = classifier or full.get("classifier")
                    name = name or full.get("name", "")
                    unit = unit or full.get("baseUnit")
                except Exception:
                    continue
            fuel = _fuel_of(classifier or "", name)
            if fuel:
                out.append({"id": rid, "fuel": fuel, "unit": (unit or "").lower(), "name": name})
    return out


def _readings(token, app_id, rid, start, end):
    """One PT30M chunk, asked for and returned in UTC.

    Glowmarkt stores everything in UTC and reads `from`/`to` in whatever timezone
    `offset` names (minutes from UTC, negated -- BST is -60). Passing 0 with UTC
    timestamps keeps the whole exchange in the same frame the CSV exports use, so
    nothing needs shifting at either end and BST changes nothing.

    `nulls=1` matters as much: without it a half-hour with no reading comes back as
    0.0, indistinguishable from a genuine zero, which would quietly drag down the
    baseload and the load profile. With it, gaps are null and we drop them.
    """
    fmt = "%Y-%m-%dT%H:%M:%S"
    d = _call(f"resource/{rid}/readings", token, app_id, params={
        "period": "PT30M", "function": "sum", "offset": 0, "nulls": 1,
        "from": start.astimezone(timezone.utc).strftime(fmt),
        "to": end.astimezone(timezone.utc).strftime(fmt)})
    pairs = []
    for row in d.get("data") or []:
        if not row or len(row) < 2 or row[1] is None:
            continue
        ts, val = int(row[0]), float(row[1])
        if ts % HALF_HOUR == 0 and val >= 0:        # negative = not a consumption reading
            pairs.append((ts, val))
    return pairs


def first_reading(token, app_id, rid):
    """When this meter's history starts, so a first run doesn't ask for empty months."""
    try:
        d = _call(f"resource/{rid}/first-time", token, app_id)
        val = d.get("data", d) if isinstance(d, dict) else d
        if isinstance(val, dict):                      # {"data": {"firstTs": 1750806000}}
            val = val.get("firstTs", val.get("firstTime"))
        if isinstance(val, (int, float)):
            return datetime.fromtimestamp(val, timezone.utc)
        return datetime.fromisoformat(str(val).replace("Z", "")).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def request_catchup(token, app_id, rid):
    """Ask the DCC for anything it hasn't sent yet (SMETS2 meters lag by days).

    Asynchronous -- it triggers a fetch rather than returning data, so today's run
    may still miss the newest half-hours and pick them up next time. We fire it for
    every meter before reading anything, so the pull that follows gives it time to
    land. Failure is ignored: it is an optimisation, not a step.
    """
    try:
        _call(f"resource/{rid}/catchup", token, app_id, timeout=15)
        return True
    except Exception:
        return False


# --- timestamp frame ------------------------------------------------------------

def _as_utc(ts):
    """Reinterpret a timestamp that is really London wall-clock seconds as true UTC."""
    wall = datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None)
    return int(wall.replace(tzinfo=LONDON).timestamp())


def _detect_mode(pairs, stored):
    """Are the API's timestamps true UTC, or London wall-clock dressed as epochs?

    It should always be UTC -- we ask with offset=0 and Glowmarkt stores in UTC --
    but getting this wrong would silently put every BST reading an hour out, so it is
    worth confirming rather than trusting. The CSV exports the store was built from
    are true UTC, so where the two overlap we score both readings of the timestamp
    against known values. In winter the two are identical and the question is moot;
    we only commit when the overlap spans BST. Returns "utc", "local" or None.
    """
    scores = {}
    for mode in ("utc", "local"):
        diffs = [abs(stored[e] - v) for ts, v in pairs
                 for e in (ts if mode == "utc" else _as_utc(ts),) if e in stored]
        if len(diffs) >= 48:
            scores[mode] = sum(diffs) / len(diffs)
    if len(scores) < 2 or all(_as_utc(ts) == ts for ts, _ in pairs):
        return None                                   # no overlap, or GMT-only: can't tell
    best = min(scores, key=scores.get)
    other = max(scores, key=scores.get)
    if scores[best] <= 0.001 or scores[best] * 4 < scores[other]:
        return best
    return None


# --- the one function main.py calls ---------------------------------------------

def fetch_new(store_path, account_path, state_path, gas_factor=None, log=print):
    """Pull every half-hour recorded since the store's latest one, per fuel.

    Returns (records, note) where records are (fuel, epoch, kwh) triples ready for
    hh.import_files to merge, and note is a one-line summary (or None when the API
    was not used at all). Any failure is reported and swallowed -- the run continues
    on whatever is in the inbox.
    """
    from model.hh import load_store

    account = read_account(account_path)
    if not account:
        return [], None

    state = _load_state(state_path)
    try:
        token, fresh = _token(account, state)
        resources = state.get("resources")
        if not resources or fresh:
            resources = list_resources(token, account["application_id"])
            state["resources"] = resources
    except urllib.error.HTTPError as e:
        log(f"Bright: login failed ({e.code}) — using the inbox only. "
            f"Check username/password in {Path(account_path).name}.")
        return [], None
    except Exception as e:
        log(f"Bright: could not reach the API ({e}) — using the inbox only.")
        return [], None

    if not resources:
        log("Bright: no electricity or gas consumption meters found on that account.")
        return [], None

    store = load_store(store_path)
    stored = {}
    last = {}
    for fuel, epoch, kwh in store:
        last[fuel] = max(last.get(fuel, 0), epoch)
        stored[(fuel, epoch)] = kwh

    now = datetime.now(timezone.utc)
    mode = state.get("timestamp_mode")
    records, failures = [], 0

    # nudge the DCC first for every meter, then read: the pulls below give the
    # asynchronous catchup time to land before we ask for that meter's data
    for res in resources:
        request_catchup(token, account["application_id"], res["id"])

    for res in resources:
        fuel, rid = res["fuel"], res["id"]
        unit = res.get("unit") or "kwh"
        volume = unit not in ("kwh", "kw", "wh")     # some gas meters report m3
        if volume and not gas_factor:
            log(f"Bright: skipping {fuel} meter — reports {unit}, no conversion factor.")
            continue
        if last.get(fuel):
            # re-ask for the last 2 days as well: DCC half-hours arrive late
            start = datetime.fromtimestamp(last[fuel] + HALF_HOUR, timezone.utc) - timedelta(days=2)
        else:
            start = now - timedelta(days=BACKFILL_DAYS)
            began = first_reading(token, account["application_id"], rid)
            if began and began > start:
                start = began            # newer meter: don't ask for months that don't exist
        got = 0
        while start < now:
            end = min(start + timedelta(days=MAX_DAYS), now)
            try:
                pairs = _readings(token, account["application_id"], rid, start, end)
            except Exception as e:
                failures += 1
                if failures >= 3:
                    log(f"Bright: stopped after repeated errors ({e}); kept what arrived.")
                    start = now
                    break
                start = end
                continue
            if mode is None and pairs:
                mode = _detect_mode(pairs, {e: v for (f, e), v in stored.items() if f == fuel})
                if mode:
                    state["timestamp_mode"] = mode
            for ts, val in pairs:
                epoch = ts if (mode or "utc") == "utc" else _as_utc(ts)
                records.append((fuel, epoch, val * gas_factor if volume else val))
                got += 1
            start = end
            time.sleep(0.15)                         # be gentle with a free API
        log(f"Bright: {fuel} — {got:,} half-hours retrieved.")

    _save_state(state_path, state)
    if mode is None and records:
        log("Bright: could not confirm the API's timezone against your history "
            "(needs overlapping British Summer Time data); assuming UTC.")
    fresh_count = sum(1 for r in records if (r[0], r[1]) not in stored)
    note = f"fetched {len(records):,} half-hours from Bright ({fresh_count:,} new)"
    return records, note
