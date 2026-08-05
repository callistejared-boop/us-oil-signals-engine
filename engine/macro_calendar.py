"""Day 11 — Standardized economic event/calendar model.

REUSE, NOT DUPLICATION: `engine.news_guard` already fetches the week's
high-impact USD calendar (ForexFactory's free feed) and implements the
blackout-window logic every entry alert already stands aside for. This
module does NOT re-fetch — it calls `news_guard.fetch_events()` for the
raw (datetime, title) list and wraps each one in a standardized `Event`
shape the mandate asks for: classified by expected importance, affected
assets, historical volatility impact, timing, and uncertainty.

Classification is a small, disclosed KEYWORD table (`EVENT_CATEGORIES`),
not a fitted model — same "disclosed engineering judgment, not a fitted
number" convention as every other qualitative table in this codebase
(Day 6's confidence tiers, Day 9's `EXPECTANCY_DECLINE_R`). It supports
future event studies (a future experiment could measure realized
volatility around each category and refine these tiers with EVIDENCE) but
this module itself never gates or delays a trade — see
`news_guard.evaluate()` for the (unchanged, pre-existing) blackout logic
that already does that job; this module is a read-only, richer VIEW of
the same underlying event list, not a new gate.
"""
from __future__ import annotations

from datetime import datetime, timezone

# category -> (importance, historical_vol_impact, keywords). `importance`
# and `historical_vol_impact` are the same disclosed 3-tier scale
# (low/medium/high) used elsewhere in this codebase's qualitative tables.
# Keyword matching is case-insensitive substring match on the event title
# news_guard.py already extracts (format: "{country} {title}").
EVENT_CATEGORIES = [
    ("central_bank", "high", "high", [
        "fomc", "interest rate decision", "fed chair", "rate decision",
        "monetary policy statement", "ecb press conference", "boe rate",
    ]),
    ("inflation", "high", "high", ["cpi", "ppi", "pce price index", "inflation"]),
    ("employment", "high", "high", [
        "non-farm employment", "nonfarm payroll", "unemployment claims",
        "unemployment rate", "employment change", "average hourly earnings",
    ]),
    ("growth", "medium", "medium", ["gdp", "retail sales", "ism manufacturing", "ism services"]),
    ("housing", "low", "low", ["housing starts", "building permits", "home sales"]),
    ("energy", "medium", "medium", ["crude oil inventories", "eia", "opec"]),
    ("sentiment", "low", "low", ["consumer confidence", "consumer sentiment", "pmi"]),
]

# Which asset classes each category is understood to move — disclosed,
# not fitted. Every category affects XAUUSD/EURUSD (USD-priced, dominant
# USD-news sensitivity per news_guard.py's own RELEVANT={"USD","ALL"}
# filter) and WTIUSD (also USD-priced; energy category doubly so).
# BTCUSD's macro-news sensitivity is real but generally more muted/delayed
# than gold's — included for every category but disclosed as the weaker
# linkage per engine.risk_sentiment's own documented BTC treatment.
_DEFAULT_ASSETS = ["XAUUSD", "EURUSD", "WTIUSD", "BTCUSD"]


def _classify(title: str):
    t = (title or "").lower()
    for category, importance, vol_impact, keywords in EVENT_CATEGORIES:
        if any(kw in t for kw in keywords):
            return category, importance, vol_impact
    return "other", "medium", "medium"


def _fetch_raw():
    from . import news_guard
    return news_guard.fetch_events()


def get_events(now=None, raw_events=None) -> list:
    """Standardized Event list: [{title, category, importance,
    historical_vol_impact, affected_assets, when_utc, minutes_until,
    timing, uncertainty}, ...], sorted by time. `raw_events` lets callers
    (and tests) pass an explicit (dt, title) list instead of fetching live
    — mirrors this codebase's `d=`/`rows=` override convention used
    throughout (engine.risk_sentiment.alignment, engine.edge_decay_monitor,
    etc.) so this module is independently testable offline. Never raises —
    a fetch failure returns `[]`, not an exception."""
    now = now or datetime.now(timezone.utc)
    try:
        raw = raw_events if raw_events is not None else _fetch_raw()
    except Exception:  # noqa: BLE001
        return []
    out = []
    for dt, title in raw:
        try:
            category, importance, vol_impact = _classify(title)
            minutes_until = round((dt - now).total_seconds() / 60.0)
            timing = ("past" if minutes_until < 0 else
                     "imminent" if minutes_until <= 60 else
                     "today" if minutes_until <= 24 * 60 else "upcoming")
            # Uncertainty: scheduled-macro-data releases carry real
            # surprise risk (actual vs. consensus) even though the TIMING
            # is known — disclosed as a qualitative tier, not a modeled
            # probability this platform has no basis to compute.
            uncertainty = "high" if importance == "high" else "medium" if importance == "medium" else "low"
            out.append({
                "title": title, "category": category, "importance": importance,
                "historical_vol_impact": vol_impact, "affected_assets": list(_DEFAULT_ASSETS),
                "when_utc": dt.isoformat(), "minutes_until": minutes_until,
                "timing": timing, "uncertainty": uncertainty,
            })
        except Exception:  # noqa: BLE001
            continue
    out.sort(key=lambda e: e["when_utc"])
    return out


def upcoming(category: str = None, now=None, raw_events=None, within_hours: float = None) -> list:
    """Events at/after `now`, optionally filtered by category and/or a
    lookahead window. Never raises."""
    try:
        events = get_events(now=now, raw_events=raw_events)
        events = [e for e in events if e["minutes_until"] >= 0]
        if category:
            events = [e for e in events if e["category"] == category]
        if within_hours is not None:
            events = [e for e in events if e["minutes_until"] <= within_hours * 60]
        return events
    except Exception:  # noqa: BLE001
        return []


def next_event(category: str = None, now=None, raw_events=None):
    ev = upcoming(category=category, now=now, raw_events=raw_events)
    return ev[0] if ev else None


def summary(now=None, raw_events=None) -> dict:
    """One structured summary — counts by category/importance plus the
    single next event overall. Never raises."""
    try:
        events = get_events(now=now, raw_events=raw_events)
        by_category = {}
        for e in events:
            by_category.setdefault(e["category"], 0)
            by_category[e["category"]] += 1
        nxt = next_event(now=now, raw_events=raw_events)
        return {
            "n_events_this_week": len(events), "by_category": by_category,
            "next_event": nxt,
            "note": ("Calendar is USD-relevant events only (per news_guard.py's own "
                    "RELEVANT filter) — this is a genuine scope limitation, disclosed, "
                    "not silently assumed complete for non-USD-driven catalysts."),
        }
    except Exception as exc:  # noqa: BLE001
        return {"n_events_this_week": 0, "by_category": {}, "next_event": None,
               "error": f"summary error: {exc}"}


def line(now=None, raw_events=None) -> str:
    nxt = next_event(now=now, raw_events=raw_events)
    if not nxt:
        return "MACRO CALENDAR: no upcoming high-impact USD events found."
    h, m = divmod(int(nxt["minutes_until"]), 60)
    return (f"MACRO CALENDAR: next {nxt['category']} event — {nxt['title']} "
           f"in {h}h{m:02d}m (importance={nxt['importance']}, "
           f"vol-impact={nxt['historical_vol_impact']})")


if __name__ == "__main__":
    print(line())
