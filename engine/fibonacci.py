"""Fibonacci retracement + extension confluence — from the institutional
trading literature review (The Institutional Trading Bible ch.8,
Candlesticks/Fibonacci/Chart Pattern Trading).

Gap this closes: `mean_reversion.py` already computes retracement targets
(23.6/38.2/50/61.8/78.6%) for its own display purposes, and the ICT OTE
zone (62-79%) is really just the golden-ratio retracement band under a
different name. But nothing in the engine computes Fibonacci EXTENSION
levels (127.2/161.8/200%), which the literature treats as the primary tool
for setting realistic profit targets beyond the immediate swing, and
nothing scores confluence between a Fib level and the trade's actual
entry/stop/target prices.

This module is target/level-focused rather than entry-timing-focused (that
job already belongs to OTE/pivots/breaker-blocks): does the trade's own
entry sit on a real Fibonacci retracement level, and do its targets line
up with real Fibonacci extension levels? That's two independent, genuinely
new pieces of confluence evidence.

Also adds three-point (A-B-C) Fibonacci EXPANSION, genuinely distinct from
the two-point extension above: extension projects beyond a single swing,
while expansion measures a full A-B-C zigzag (impulse, then correction) and
projects where the next leg (the "D" point) could reach, using the A-B
leg's size applied from C. Note on the "Golden Zone" concept named in the
Smart Money 200-page guide: it isn't implemented separately here because
it's already covered -- it's the same 61.8-79% band the engine already
trades as the ICT OTE zone (see ict_confluence.py), just under a different
name in that document. Building a second, differently-named copy of the
same thing would be padding, not a real gap.

Fail-safe throughout: any computation issue -> neutral read, never raises.
"""
from __future__ import annotations

import pandas as pd

from . import structure as st

RETRACEMENT_LEVELS = (0.236, 0.382, 0.5, 0.618, 0.705, 0.786)
EXTENSION_LEVELS = (1.272, 1.618, 2.0)
EXPANSION_LEVELS = (0.618, 1.0, 1.272, 1.618)
PROXIMITY_ATR_MULT = 0.25


def retracements(swing_high: float, swing_low: float) -> dict:
    r = float(swing_high) - float(swing_low)
    if r <= 0:
        return {}
    return {f"{p*100:.1f}%": round(swing_high - p * r, 4) for p in RETRACEMENT_LEVELS}


def extensions(swing_high: float, swing_low: float, direction: str) -> dict:
    """Extension targets projected beyond the swing, in the trade direction.
    Longs project up from the high; shorts project down from the low."""
    r = float(swing_high) - float(swing_low)
    if r <= 0:
        return {}
    if direction == "long":
        return {f"{p*100:.1f}%": round(swing_high + (p - 1.0) * r, 4) for p in EXTENSION_LEVELS}
    return {f"{p*100:.1f}%": round(swing_low - (p - 1.0) * r, 4) for p in EXTENSION_LEVELS}


def _nearest(levels: dict, price: float):
    if not levels:
        return None, None
    name = min(levels, key=lambda k: abs(levels[k] - price))
    return name, levels[name]


def alignment(swing_high: float, swing_low: float, direction: str,
             entry: float, target: float, atr_val: float) -> dict:
    """Does the entry sit on a real retracement level, and does the target
    sit on a real extension level? Soft signal -> {supports: True/False/None,
    note}."""
    try:
        tol = max(atr_val, 1e-6) * PROXIMITY_ATR_MULT
        retr = retracements(swing_high, swing_low)
        ext = extensions(swing_high, swing_low, direction)
        hits = []

        r_name, r_val = _nearest(retr, entry)
        entry_hit = r_name is not None and abs(r_val - entry) <= tol
        if entry_hit:
            hits.append(f"entry at Fib {r_name} retracement ({r_val:.2f})")

        e_name, e_val = _nearest(ext, target)
        target_hit = e_name is not None and abs(e_val - target) <= tol
        if target_hit:
            hits.append(f"target at Fib {e_name} extension ({e_val:.2f})")

        if not hits:
            return {"supports": None, "note": "fibonacci: no retracement/extension confluence"}
        supports = True   # confluence found is always supportive; absence is neutral, not a warning
        return {"supports": supports, "note": "fibonacci: " + "; ".join(hits)}
    except Exception:  # noqa: BLE001
        return {"supports": None, "note": "fibonacci: unavailable"}


def expansions(a: float, b: float, c: float, direction: str) -> dict:
    """Three-point (A-B-C) Fibonacci expansion: projects the next leg (D)
    from point C using the size of the A-B leg. 'long' projects upward from
    C, 'short' projects downward -- direction should match the expected
    continuation, not necessarily the sign of (b - a)."""
    ab = abs(float(b) - float(a))
    if ab <= 0:
        return {}
    sign = 1 if direction == "long" else -1
    return {f"{p*100:.1f}%": round(float(c) + sign * p * ab, 4) for p in EXPANSION_LEVELS}


def _last_abc(df: pd.DataFrame, lookback: int = 300):
    """Most recent three confirmed swings, used as a pragmatic proxy A-B-C
    zigzag. Returns (a_price, b_price, c_price) or None if unavailable or
    the swings don't alternate cleanly (kind A != kind B != kind C)."""
    sub = df.tail(lookback).reset_index(drop=True)
    swings = st.find_swings(sub["High"].values, sub["Low"].values, k=st.SWING_K)
    if len(swings) < 3:
        return None
    a, b, c = swings[-3], swings[-2], swings[-1]
    if a.kind == b.kind or b.kind == c.kind:
        return None
    return a.price, b.price, c.price


def alignment_abc(df: pd.DataFrame, direction: str, price: float, atr_val: float,
                  lookback: int = 300) -> dict:
    """Does `price` sit near a genuine A-B-C expansion level projected from
    the most recent 3-swing zigzag? Soft signal ->
    {supports: True/False/None, note}. Absence is neutral, not a warning --
    matching how the two-point extension/retracement alignment() behaves."""
    try:
        abc = _last_abc(df, lookback)
        if abc is None:
            return {"supports": None, "note": "fibonacci ABC: no clean 3-swing zigzag available"}
        a, b, c = abc
        exp = expansions(a, b, c, direction)
        name, val = _nearest(exp, price)
        tol = max(atr_val, 1e-6) * PROXIMITY_ATR_MULT
        if name is None or abs(val - price) > tol:
            return {"supports": None, "note": "fibonacci ABC: no expansion confluence at price"}
        return {"supports": True,
                "note": f"fibonacci ABC: price at {name} expansion ({val:.2f}, "
                        f"A={a:.2f} B={b:.2f} C={c:.2f})"}
    except Exception:  # noqa: BLE001
        return {"supports": None, "note": "fibonacci ABC: unavailable"}


def lines(swing_high: float, swing_low: float, direction: str) -> list:
    retr = retracements(swing_high, swing_low)
    ext = extensions(swing_high, swing_low, direction or "long")
    out = []
    if retr:
        out.append("Fib retracement: " + " | ".join(f"{k} {v:.2f}" for k, v in retr.items()))
    if ext:
        out.append("Fib extension: " + " | ".join(f"{k} {v:.2f}" for k, v in ext.items()))
    return out
