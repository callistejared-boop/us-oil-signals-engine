"""Real EIA crude inventory data — the one macro input that genuinely needs a
credential only the user can obtain (free, instant, no card required).

Get a key: https://www.eia.gov/opendata/register.php  then set
EIA_API_KEY=... in .env (or config.eia_api_key). Without a key this module
returns None everywhere and the rest of the pipeline is unaffected — the
news-sentiment feed already mentions inventory headlines qualitatively, this
just adds the actual weekly build/draw number when available.

Series: PET.WCESTUS1.W = weekly U.S. ending stocks of crude oil (thousand
barrels), the number markets react to every Wednesday (EIA) / Tuesday (API).
"""
from __future__ import annotations

import json
import pathlib
import urllib.parse
import urllib.request
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "eia_cache.json"
SERIES = "PET.WCESTUS1.W"
URL = "https://api.eia.gov/v2/seriesid/" + SERIES


def _key():
    try:
        from . import config
        return getattr(config.load(), "eia_api_key", "") or ""
    except Exception:  # noqa: BLE001
        return ""


def fetch(timeout=15):
    """Latest two weekly crude-stock readings -> {value, prior, change_kb,
    period}. Returns None if no key configured or the request fails."""
    key = _key()
    if not key:
        return None
    try:
        url = URL + "?" + urllib.parse.urlencode({"api_key": key})
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = json.load(r)
        rows = data.get("response", {}).get("data", [])
        if len(rows) < 2:
            return None
        rows.sort(key=lambda r: r.get("period", ""), reverse=True)
        latest, prior = rows[0], rows[1]
        change = float(latest["value"]) - float(prior["value"])
        out = {"value": float(latest["value"]), "prior": float(prior["value"]),
               "change_kb": round(change, 0), "period": latest.get("period"),
               "asof": date.today().isoformat()}
        try:
            CACHE_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        return out
    except Exception:  # noqa: BLE001
        return None


def read_cached(max_age_days=8):
    try:
        d = json.loads(CACHE_PATH.read_text())
        if (date.today() - date.fromisoformat(d["asof"])).days > max_age_days:
            return None
        return d
    except Exception:  # noqa: BLE001
        return None


def note():
    """One-line human summary for the note/dashboard, or a setup hint."""
    d = read_cached() or fetch()
    if not d:
        return ("EIA inventory: not configured — get a free key at "
                "eia.gov/opendata/register.php and set EIA_API_KEY in .env")
    kb = d["change_kb"]
    verb = "BUILD" if kb > 0 else "DRAW" if kb < 0 else "flat"
    lean = "bearish" if kb > 0 else "bullish" if kb < 0 else "neutral"
    return (f"EIA crude stocks ({d['period']}): {verb} {abs(kb):,.0f}kb "
            f"({lean} for price)")


if __name__ == "__main__":
    print(note())
