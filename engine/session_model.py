"""AMD / Power of Three / Judas Swing session model.

Provenance note, said plainly: these names ("Power of Three", "AMD Model",
"Judas Swing", "Silver Bullet", "Market Maker Model") appear in the
uploaded "Smart Money 200-Page Master Guide" (pages 57-63), but that
document turned out to be templated boilerplate with no unique operational
rule behind any of its page titles (confirmed by spot-checking a dozen
pages across different modules -- Fibonacci, risk math, SMC structure --
all sharing identical generic paragraphs). This implementation is standard
ICT/SMC domain knowledge (these are widely-taught, well-established
concepts outside that specific document), not something extracted from its
content.

The model: a session is expected to move in three phases -- Accumulation
(Asian session, a tight range builds while big players position quietly),
Manipulation (London session, price makes a deceptive move -- the "Judas
Swing" -- that sweeps the Asian range in one direction to trigger retail
stops/entries the wrong way), and Distribution (New York session, the real
move plays out in the OPPOSITE direction from the Judas Swing).

This module uses the same session-hour convention already established
elsewhere in the engine (ict.py / structure.in_killzone): Asian 00:00-06:00
UTC, London kill zone 07:00-10:00 UTC, New York kill zone 12:00-15:00 UTC.
It is a pragmatic proxy, not a claim of perfect session detection --
documented the same way breaker_blocks.py flags its own mitigation-zone
proxy rather than overstating precision.

Fail-safe throughout: any computation issue -> neutral read, never raises.
"""
from __future__ import annotations

import pandas as pd

LOOKBACK = 400
ASIAN_HOURS = range(0, 6)
LONDON_KZ_HOURS = range(7, 10)
NY_KZ_START_HOUR = 12


def asian_range_for_day(df: pd.DataFrame, day) -> tuple | None:
    mask = (df.index.date == day) & (df.index.hour.isin(list(ASIAN_HOURS)))
    seg = df[mask]
    if seg.empty:
        return None
    return float(seg["High"].max()), float(seg["Low"].min())


def judas_swing(df: pd.DataFrame, lookback: int = LOOKBACK) -> dict | None:
    """For the most recent day(s) with both an Asian block and a London
    kill-zone block, did London price sweep beyond the Asian high or low
    and then close back inside the Asian range (the deceptive "Judas"
    move)? Returns {"day", "direction" (the expected NY continuation),
    "swept" ("high"|"low"), "level"} for the most recent qualifying day, or
    None if no such move is found."""
    try:
        sub = df.tail(lookback)
        if sub.empty:
            return None
        candidate_days = sorted({sub.index[-1].date(),
                                 (sub.index[-1] - pd.Timedelta(days=1)).date()}, reverse=True)
        for day in candidate_days:
            arange = asian_range_for_day(sub, day)
            if arange is None:
                continue
            hi, lo = arange
            london_mask = (sub.index.date == day) & (sub.index.hour.isin(list(LONDON_KZ_HOURS)))
            london = sub[london_mask]
            if london.empty:
                continue

            swept_high = london[london["High"] > hi]
            if not swept_high.empty:
                idx0 = swept_high.index[0]
                later = sub[sub.index > idx0]
                if not later.empty and (later["Close"] < hi).any():
                    return {"day": day, "direction": "short", "swept": "high", "level": hi}

            swept_low = london[london["Low"] < lo]
            if not swept_low.empty:
                idx0 = swept_low.index[0]
                later = sub[sub.index > idx0]
                if not later.empty and (later["Close"] > lo).any():
                    return {"day": day, "direction": "long", "swept": "low", "level": lo}
        return None
    except Exception:  # noqa: BLE001
        return None


def alignment(df: pd.DataFrame, direction: str, lookback: int = LOOKBACK) -> dict:
    """Does today's Judas Swing (if any) imply a New York continuation that
    matches `direction`? Soft signal -> {supports: True/False/None, note}.
    Only relevant once price is actually in/past the NY kill zone on the
    same day the swing was detected -- before that it's informational only,
    not yet a confirmation."""
    try:
        js = judas_swing(df, lookback)
        if js is None:
            return {"supports": None, "note": "session model: no Judas Swing detected"}
        now = df.index[-1]
        if now.date() != js["day"]:
            return {"supports": None, "note": "session model: Judas Swing was from a prior day, stale"}
        if now.hour < NY_KZ_START_HOUR:
            return {"supports": None,
                    "note": f"session model: Judas Swing confirmed (swept {js['swept']} "
                            f"{js['level']:.2f}), awaiting NY session"}
        supports = (js["direction"] == "long") == (direction == "long")
        return {"supports": supports,
                "note": f"session model: Judas Swing swept {js['swept']} {js['level']:.2f} "
                        f"-> NY continuation expected {js['direction']}"}
    except Exception:  # noqa: BLE001
        return {"supports": None, "note": "session model: unavailable"}
