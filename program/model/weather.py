"""Standalone weather fetch (Open-Meteo archive API — free, no key).

Brings the fetch logic in-house so the tool has no external project dependency.
Uses urllib (no extra package), caches daily temperatures to disk, and fails
gracefully offline (returns whatever is cached, or nothing).
"""
from __future__ import annotations
import json
import urllib.request
import urllib.parse
from collections import defaultdict
from pathlib import Path

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HDD_BASE = 15.5   # °C — standard UK heating base temperature


def _load(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return {}


def _save(p, data):
    try:
        Path(p).write_text(json.dumps(data))
    except Exception:
        pass


def get_monthly_weather(lat, lon, start, end, cache_file):
    """Return {(year, month): {"temp": mean°C, "hdd": heating-degree-days, "days": n}}.

    Heating-degree-days measure how cold a period was (Σ max(0, 15.5 − dailyMean)),
    which is what drives gas heating demand. Fetches once and caches; offline it
    just uses the cache.
    """
    key = f"{lat:.3f},{lon:.3f}"
    cache = _load(cache_file)
    daily = cache.get(key, {})
    s, e = start.isoformat(), end.isoformat()
    fields = ["temperature_2m_mean", "temperature_2m_max", "temperature_2m_min", "precipitation_sum"]
    # re-fetch if range or the newer fields aren't fully cached
    have = daily.get(s) if isinstance(daily.get(s), dict) else None
    if have is None or e not in daily:
        try:
            q = urllib.parse.urlencode({
                "latitude": lat, "longitude": lon, "start_date": s, "end_date": e,
                "daily": ",".join(fields), "timezone": "Europe/London"})
            with urllib.request.urlopen(f"{ARCHIVE_URL}?{q}", timeout=20) as r:
                d = json.load(r)
            times = d["daily"]["time"]
            for i, t in enumerate(times):
                rec = {f: d["daily"][f][i] for f in fields}
                if rec["temperature_2m_mean"] is not None:
                    daily[t] = rec
            cache[key] = daily
            _save(cache_file, cache)
        except Exception:
            pass                                        # offline: use whatever is cached

    agg = defaultdict(list)
    for t, rec in daily.items():
        if s <= t <= e and isinstance(rec, dict):
            y, m, _ = t.split("-")
            agg[(int(y), int(m))].append(rec)
    out = {}
    for (y, m), recs in agg.items():
        means = [r["temperature_2m_mean"] for r in recs]
        out[(y, m)] = {
            "temp": sum(means) / len(means),
            "tmax": max(r["temperature_2m_max"] for r in recs if r.get("temperature_2m_max") is not None),
            "tmin": min(r["temperature_2m_min"] for r in recs if r.get("temperature_2m_min") is not None),
            "rain": sum(r.get("precipitation_sum") or 0 for r in recs),
            "hdd": sum(max(0.0, HDD_BASE - v) for v in means), "days": len(recs)}
    return out
