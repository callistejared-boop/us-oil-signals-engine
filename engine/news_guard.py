"""Economic-news blackout guard.

Gold whipsaws violently around high-impact USD releases (NFP, CPI, FOMC,
PPI, rate decisions). Entering just before them is how track records get
destroyed. This module fetches the week's high-impact calendar and lets the
engine stand aside inside a blackout window, and surfaces the next event in
every briefing.

Data: ForexFactory's free weekly JSON. If it can't be fetched (offline,
blocked), the guard fails OPEN (no blackout) but says so — it never blocks
trading silently on a fetch error.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
PRE_MIN = 20     # blackout starts this many minutes BEFORE an event
POST_MIN = 15    # ...and ends this many minutes AFTER
RELEVANT = {"USD", "ALL"}   # gold is priced in USD; USD news dominates


def _parse_dt(s: str):
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def fetch_events(url: str = FEED_URL) -> list:
    """Return high-impact, USD-relevant events as (dt_utc, title) tuples."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    data = json.loads(raw)
    out = []
    for e in data:
        if str(e.get("impact", "")).lower() != "high":
            continue
        if str(e.get("country", "")).upper() not in RELEVANT:
            continue
        dt = _parse_dt(e.get("date", ""))
        if dt:
            out.append((dt, f"{e.get('country','')} {e.get('title','event')}"))
    out.sort(key=lambda x: x[0])
    return out


def evaluate(now=None) -> dict:
    """Return blackout status + next event. Fails open on any error."""
    now = now or datetime.now(timezone.utc)
    try:
        events = fetch_events()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "blackout": False, "note": f"calendar unavailable ({exc})",
                "next": None, "next_in_min": None}

    blackout, active = False, None
    nxt, nxt_in = None, None
    for dt, title in events:
        delta_min = (dt - now).total_seconds() / 60.0
        if -POST_MIN <= delta_min <= PRE_MIN:
            blackout, active = True, (title, round(delta_min))
        if delta_min > 0 and nxt is None:
            nxt, nxt_in = title, round(delta_min)
    return {"ok": True, "blackout": blackout, "active": active,
            "next": nxt, "next_in_min": nxt_in, "note": ""}


def line(status: dict) -> str:
    """One-line human summary for the briefing."""
    if not status.get("ok"):
        return f"NEWS: calendar unavailable — trading normally ({status.get('note','')})"
    if status.get("blackout"):
        t, mins = status["active"]
        when = f"in {mins} min" if mins >= 0 else f"{-mins} min ago"
        return f"NEWS BLACKOUT: high-impact {t} {when} — standing aside."
    if status.get("next"):
        h, m = divmod(int(status["next_in_min"]), 60)
        return f"NEXT HIGH-IMPACT: {status['next']} in {h}h{m:02d}m."
    return "NEWS: no high-impact USD events left this week."
