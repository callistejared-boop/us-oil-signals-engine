"""Elliott Wave -- rule-based impulse/correction validation.

Honesty upfront: fully automated Elliott Wave counting is notoriously
unreliable even in professional software -- multiple valid counts can
coexist at any moment, and wave labeling is inherently a judgment call
that depends on the analyst's chosen degree. This module does NOT claim
to produce "the" correct wave count, and no document in this project's
review taught Elliott Wave at all (it wasn't in any of the 8 uploaded
files). What it does instead is narrower and genuinely checkable: it
tests whether the most recent 6-swing sequence satisfies R.N. Elliott's
three hard, objective rules for a valid 5-wave impulse -- standard
technical-analysis literature, not extracted from any uploaded document:

  1. Wave 2 never retraces beyond the start of wave 1 (100% retracement).
  2. Wave 3 is never the shortest of waves 1, 3, and 5.
  3. Wave 4 never enters wave 1's price territory (true for a standard
     impulse; diagonals are the one textbook exception and are out of
     scope here -- flagged as a known limitation, not silently ignored).

A sequence that passes all three is a rule-VALID impulse candidate --
still not proof of "the" count, but a real, falsifiable test that most
invalid or hand-wavy wave counts fail immediately. A confirmed impulse
(wave 5 already printed a confirmed swing extreme) implies the next
expected move is a corrective (A-B-C, opposite direction) leg; that's
the only forward-looking claim this module makes.

Fail-safe throughout: any computation issue -> neutral read, never raises.
"""
from __future__ import annotations

import pandas as pd

from . import structure as st

LOOKBACK = 400


def validate_impulse(points: list, direction: str) -> dict:
    """points = 6 Swing objects [P0..P5] (wave start + 5 wave-ends).
    Returns {"valid": bool, "failed_rules": [str, ...]}."""
    prices = [p.price for p in points]
    p0, p1, p2, p3, p4, p5 = prices
    len1, len3, len5 = abs(p1 - p0), abs(p3 - p2), abs(p5 - p4)

    if direction == "long":
        rule1_ok = p2 > p0     # wave 2 doesn't retrace past wave-1 start
        rule3_ok = p4 > p1     # wave 4 doesn't overlap wave-1 territory
    else:
        rule1_ok = p2 < p0
        rule3_ok = p4 < p1
    rule2_ok = not (len3 < len1 and len3 < len5)   # wave 3 not the shortest

    failed = []
    if not rule1_ok:
        failed.append("rule1: wave 2 retraced beyond wave 1's start")
    if not rule2_ok:
        failed.append("rule2: wave 3 is the shortest of waves 1/3/5")
    if not rule3_ok:
        failed.append("rule3: wave 4 overlaps wave 1's price territory")
    return {"valid": not failed, "failed_rules": failed}


def detect(df: pd.DataFrame, lookback: int = LOOKBACK) -> dict:
    """Checks the most recent 6 confirmed swings for a rule-valid 5-wave
    impulse. Returns {"impulse": "long"/"short"/None, "expected_correction":
    str|None, "wave5_price": float|None, "note": str}."""
    try:
        sub = df.tail(lookback).reset_index(drop=True)
        swings = st.find_swings(sub["High"].values, sub["Low"].values, k=st.SWING_K)
        if len(swings) < 6:
            return {"impulse": None, "expected_correction": None, "wave5_price": None,
                    "note": "elliott wave: insufficient swing structure (need 6 confirmed swings)"}
        pts = swings[-6:]
        kinds = [s.kind for s in pts]
        if kinds == ["L", "H", "L", "H", "L", "H"]:
            direction = "long"
        elif kinds == ["H", "L", "H", "L", "H", "L"]:
            direction = "short"
        else:
            return {"impulse": None, "expected_correction": None, "wave5_price": None,
                    "note": "elliott wave: last 6 swings don't alternate into a clean 5-wave shape"}

        v = validate_impulse(pts, direction)
        if not v["valid"]:
            return {"impulse": None, "expected_correction": None, "wave5_price": None,
                    "note": "elliott wave: candidate impulse breaks " + "; ".join(v["failed_rules"])}

        expected_correction = "short" if direction == "long" else "long"
        wave5_price = pts[-1].price
        return {"impulse": direction, "expected_correction": expected_correction,
                "wave5_price": wave5_price,
                "note": f"elliott wave: rule-valid 5-wave {direction} impulse complete at "
                        f"{wave5_price:.2f} -> expect {expected_correction} A-B-C correction"}
    except Exception:  # noqa: BLE001
        return {"impulse": None, "expected_correction": None, "wave5_price": None,
                "note": "elliott wave: unavailable"}


def alignment(df: pd.DataFrame, direction: str, lookback: int = LOOKBACK) -> dict:
    """Does a just-completed, rule-valid impulse's expected corrective leg
    match the trade's `direction`? Soft signal -> {supports: True/False/None,
    note}. No confirmed impulse -> neutral, not a warning."""
    try:
        d = detect(df, lookback)
        if d["impulse"] is None:
            return {"supports": None, "note": d["note"]}
        supports = d["expected_correction"] == direction
        return {"supports": supports, "note": d["note"]}
    except Exception:  # noqa: BLE001
        return {"supports": None, "note": "elliott wave: unavailable"}
