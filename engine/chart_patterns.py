"""Classical multi-swing chart pattern recognition — built directly from the
chart-pattern chapters of "Candlesticks, Fibonacci, and Chart Pattern Trading
Tools" (Bulkowski-style structural formations, the last of the 8 uploaded
documents to get a dedicated module).

Gap this closes: every other module in the engine reasons about a single
swing, a single candle, or a single zone. Nothing names the *multi-swing
geometry* traders actually draw on a chart — a head and shoulders, a double
top, a converging triangle — even though the source book treats this as the
foundation of technical trading and gives each pattern an explicit,
mechanical confirmation rule and profit target. This module gives that
geometry a name, the book's own confirmation rule, and a measured-move
target, then feeds it into confluence as one more soft confirmation source.

Patterns detected, each anchored on the most recent confirmed swing
structure (structure.find_swings — no duplicate swing logic here):
  Reversal:      Double Top / Double Bottom, Triple Top / Triple Bottom,
                 Head & Shoulders / Inverse Head & Shoulders
  Continuation:  Ascending / Descending / Symmetrical Triangle,
                 Rising / Falling Wedge, Bullish / Bearish Rectangle
  Caution-only:  Broadening Formation (the book calls this "the most
                 difficult chart pattern to trade" — flagged, never scored
                 as directional, matching how the book itself treats it)

Confirmation is always a CLOSING-price break of the pattern's defining line
(neckline, trendline, or horizontal level) — the book is explicit that a
wick-only break doesn't count, so this module only ever checks Close.
Profit targets use the book's own measured-move rules: swing height (double
top/bottom), total peak-to-valley distance (triple top/bottom), lowest-
valley-to-highest-peak (head & shoulders), or high-to-low of the formation
(triangles/wedges/rectangles) — projected from the breakout point.

Trendline shapes (triangle/wedge/rectangle/broadening) are fit with a
pragmatic proxy: least-squares regression over the last few confirmed swing
highs and swing lows, classified by slope (flat vs. rising vs. falling) and
whether the two lines are converging, roughly parallel, or diverging. The
book itself draws these by eye; this is the closest honestly-computable
approximation, documented the same way volume_profile.py and
breaker_blocks.py flag their own approximations rather than overstating them.

Fail-safe throughout: any computation issue -> neutral read, never raises.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import structure as st

LOOKBACK = 400
LEVEL_TOL_ATR_MULT = 0.35   # peaks/valleys within this are "the same level"
FLAT_SLOPE_ATR_MULT = 0.05  # trendline slope (price/bar) below this = "flat"
CONVERGE_RATIO = 0.75       # gap must shrink to this fraction to count as converging
DIVERGE_RATIO = 1.30        # gap must grow to this fraction to count as broadening
RECT_RATIO_BAND = (0.7, 1.4)  # gap must stay roughly this stable for a rectangle
MAX_TRENDLINE_POINTS = 4    # use up to the last N swing highs / lows for the fit


def _linfit(pts):
    """Least-squares line through (idx, price) points. Falls back to a flat
    line at the mean price if fewer than 2 distinct x-values are available."""
    xs = np.array([p.idx for p in pts], dtype=float)
    ys = np.array([p.price for p in pts], dtype=float)
    if len(xs) < 2 or np.allclose(xs, xs[0]):
        return 0.0, float(ys.mean())
    slope, intercept = np.polyfit(xs, ys, 1)
    return float(slope), float(intercept)


def _double_top_bottom(sub: pd.DataFrame, swings: list, atr_val: float) -> list:
    tol = LEVEL_TOL_ATR_MULT * atr_val
    last_close = float(sub["Close"].iloc[-1])
    highs = [s for s in swings if s.kind == "H"]
    lows = [s for s in swings if s.kind == "L"]
    out = []

    if len(highs) >= 2:
        h1, h2 = highs[-2], highs[-1]
        if abs(h1.price - h2.price) <= tol:
            between = [s for s in lows if h1.idx < s.idx < h2.idx]
            if between:
                valley = min(between, key=lambda s: s.price)
                confirmed = last_close < valley.price
                target = (valley.price - (max(h1.price, h2.price) - valley.price)
                          if confirmed else None)
                out.append({
                    "pattern": "double_top", "direction": "bear" if confirmed else None,
                    "confirmed": confirmed, "target": target,
                    "note": f"double top {h1.price:.2f}/{h2.price:.2f}, "
                            f"neckline {valley.price:.2f}"
                            f"{' (confirmed close-below)' if confirmed else ' (forming)'}"})

    if len(lows) >= 2:
        l1, l2 = lows[-2], lows[-1]
        if abs(l1.price - l2.price) <= tol:
            between = [s for s in highs if l1.idx < s.idx < l2.idx]
            if between:
                peak = max(between, key=lambda s: s.price)
                confirmed = last_close > peak.price
                target = (peak.price + (peak.price - min(l1.price, l2.price))
                          if confirmed else None)
                out.append({
                    "pattern": "double_bottom", "direction": "bull" if confirmed else None,
                    "confirmed": confirmed, "target": target,
                    "note": f"double bottom {l1.price:.2f}/{l2.price:.2f}, "
                            f"neckline {peak.price:.2f}"
                            f"{' (confirmed close-above)' if confirmed else ' (forming)'}"})
    return out


def _triple_top_bottom(sub: pd.DataFrame, swings: list, atr_val: float) -> list:
    tol = LEVEL_TOL_ATR_MULT * atr_val
    last_close = float(sub["Close"].iloc[-1])
    highs = [s for s in swings if s.kind == "H"]
    lows = [s for s in swings if s.kind == "L"]
    out = []

    if len(highs) >= 3:
        h1, h2, h3 = highs[-3], highs[-2], highs[-1]
        prices = [h1.price, h2.price, h3.price]
        if max(prices) - min(prices) <= tol:
            between = [s for s in lows if h1.idx < s.idx < h3.idx]
            if len(between) >= 2:
                v_pre3 = max(between, key=lambda s: s.idx)
                confirmed = last_close < v_pre3.price
                height = max(prices) - min(s.price for s in between)
                target = v_pre3.price - height if confirmed else None
                out.append({
                    "pattern": "triple_top", "direction": "bear" if confirmed else None,
                    "confirmed": confirmed, "target": target,
                    "note": f"triple top ~{h2.price:.2f}, low-before-3rd-peak "
                            f"{v_pre3.price:.2f}"
                            f"{' (confirmed close-below)' if confirmed else ' (forming)'}"})

    if len(lows) >= 3:
        l1, l2, l3 = lows[-3], lows[-2], lows[-1]
        prices = [l1.price, l2.price, l3.price]
        if max(prices) - min(prices) <= tol:
            between = [s for s in highs if l1.idx < s.idx < l3.idx]
            if len(between) >= 2:
                p_pre3 = max(between, key=lambda s: s.idx)
                confirmed = last_close > p_pre3.price
                height = max(s.price for s in between) - min(prices)
                target = p_pre3.price + height if confirmed else None
                out.append({
                    "pattern": "triple_bottom", "direction": "bull" if confirmed else None,
                    "confirmed": confirmed, "target": target,
                    "note": f"triple bottom ~{l2.price:.2f}, high-before-3rd-trough "
                            f"{p_pre3.price:.2f}"
                            f"{' (confirmed close-above)' if confirmed else ' (forming)'}"})
    return out


def _head_and_shoulders(sub: pd.DataFrame, swings: list, atr_val: float) -> list:
    tol = LEVEL_TOL_ATR_MULT * atr_val
    last_close = float(sub["Close"].iloc[-1])
    idx_now = len(sub) - 1
    out = []
    if len(swings) < 5:
        return out
    last5 = swings[-5:]
    kinds = [s.kind for s in last5]

    if kinds == ["H", "L", "H", "L", "H"]:
        p1, v1, p2, v2, p3 = last5
        if p2.price > p1.price and p2.price > p3.price and abs(p1.price - p3.price) <= tol:
            slope = (v2.price - v1.price) / max(v2.idx - v1.idx, 1)
            neckline_now = v1.price + slope * (idx_now - v1.idx)
            confirmed = last_close < neckline_now
            measured_move = p2.price - min(v1.price, v2.price)
            target = neckline_now - measured_move if confirmed else None
            out.append({
                "pattern": "head_and_shoulders", "direction": "bear" if confirmed else None,
                "confirmed": confirmed, "target": target,
                "note": f"head & shoulders, head {p2.price:.2f}, neckline now "
                        f"{neckline_now:.2f}"
                        f"{' (confirmed close-below)' if confirmed else ' (forming)'}"})

    if kinds == ["L", "H", "L", "H", "L"]:
        v1, p1, v2, p2, v3 = last5
        if v2.price < v1.price and v2.price < v3.price and abs(v1.price - v3.price) <= tol:
            slope = (p2.price - p1.price) / max(p2.idx - p1.idx, 1)
            neckline_now = p1.price + slope * (idx_now - p1.idx)
            confirmed = last_close > neckline_now
            measured_move = max(p1.price, p2.price) - v2.price
            target = neckline_now + measured_move if confirmed else None
            out.append({
                "pattern": "inverse_head_and_shoulders",
                "direction": "bull" if confirmed else None,
                "confirmed": confirmed, "target": target,
                "note": f"inverse head & shoulders, head {v2.price:.2f}, neckline now "
                        f"{neckline_now:.2f}"
                        f"{' (confirmed close-above)' if confirmed else ' (forming)'}"})
    return out


def _trendline_pattern(sub: pd.DataFrame, swings: list, atr_val: float):
    highs = [s for s in swings if s.kind == "H"]
    lows = [s for s in swings if s.kind == "L"]
    if len(highs) < 2 or len(lows) < 2:
        return None
    highs_used = highs[-MAX_TRENDLINE_POINTS:]
    lows_used = lows[-MAX_TRENDLINE_POINTS:]

    slope_h, icpt_h = _linfit(highs_used)
    slope_l, icpt_l = _linfit(lows_used)
    idx_start = min(highs_used[0].idx, lows_used[0].idx)
    idx_end = len(sub) - 1

    gap_start = (slope_h * idx_start + icpt_h) - (slope_l * idx_start + icpt_l)
    gap_end = (slope_h * idx_end + icpt_h) - (slope_l * idx_end + icpt_l)
    if gap_start <= 0 or gap_end <= 0:
        return None  # lines already crossed — not a valid formation
    ratio = gap_end / gap_start

    flat = FLAT_SLOPE_ATR_MULT * atr_val
    h_flat, l_flat = abs(slope_h) <= flat, abs(slope_l) <= flat

    shape = None
    if slope_h > flat and slope_l < -flat and ratio >= DIVERGE_RATIO:
        shape = "broadening_formation"
    elif h_flat and l_flat and RECT_RATIO_BAND[0] <= ratio <= RECT_RATIO_BAND[1]:
        shape = "rectangle"
    elif ratio <= CONVERGE_RATIO:
        if h_flat and slope_l > flat:
            shape = "ascending_triangle"
        elif l_flat and slope_h < -flat:
            shape = "descending_triangle"
        elif slope_h < -flat and slope_l > flat:
            shape = "symmetrical_triangle"
        elif slope_h > flat and slope_l > flat:
            shape = "rising_wedge"
        elif slope_h < -flat and slope_l < -flat:
            shape = "falling_wedge"

    if shape is None:
        return None

    if shape == "broadening_formation":
        return {"pattern": shape, "direction": None, "confirmed": False, "target": None,
                "note": "broadening formation present - the literature's own "
                        "'hardest pattern to trade': no directional read taken"}

    height = max(s.price for s in highs_used) - min(s.price for s in lows_used)
    if height <= 0:
        return None
    high_now = slope_h * idx_end + icpt_h
    low_now = slope_l * idx_end + icpt_l
    last_close = float(sub["Close"].iloc[-1])

    if last_close > high_now:
        direction, confirmed, target = "bull", True, high_now + height
    elif last_close < low_now:
        direction, confirmed, target = "bear", True, low_now - height
    else:
        direction, confirmed, target = None, False, None

    label = shape.replace("_", " ")
    status = f"breakout {direction}" if confirmed else "forming, unconfirmed"
    return {"pattern": shape, "direction": direction, "confirmed": confirmed,
            "target": target, "note": f"{label} ({status})"}


def detect(df: pd.DataFrame, lookback: int = LOOKBACK) -> dict:
    """Scan for chart patterns over the last `lookback` bars. Returns
    {"patterns": [{"pattern", "direction", "confirmed", "target", "note"}, ...],
    "note": summary str}. Only patterns with a genuine closing-price
    confirmation carry a direction; unconfirmed/forming patterns are still
    surfaced in the note for context but direction is None."""
    try:
        sub = df.tail(lookback).reset_index(drop=True)
        if len(sub) < 30:
            return {"patterns": [], "note": "chart patterns: insufficient bars"}
        atr_val = float(st.atr(sub).iloc[-1])
        if not atr_val or atr_val <= 0 or pd.isna(atr_val):
            return {"patterns": [], "note": "chart patterns: ATR unavailable"}
        swings = st.find_swings(sub["High"].values, sub["Low"].values, k=st.SWING_K)
        if len(swings) < 2:
            return {"patterns": [], "note": "chart patterns: insufficient swing structure"}

        found = []
        found += _double_top_bottom(sub, swings, atr_val)
        found += _triple_top_bottom(sub, swings, atr_val)
        found += _head_and_shoulders(sub, swings, atr_val)
        tp = _trendline_pattern(sub, swings, atr_val)
        if tp is not None:
            found.append(tp)

        if not found:
            return {"patterns": [], "note": "chart patterns: none detected"}
        names = ", ".join(f["pattern"].replace("_", " ") for f in found)
        return {"patterns": found, "note": f"chart patterns: {names}"}
    except Exception:  # noqa: BLE001
        return {"patterns": [], "note": "chart patterns: unavailable"}


def alignment(df: pd.DataFrame, direction: str) -> dict:
    """Does the most recently CONFIRMED chart pattern support or warn
    against `direction`? Soft signal -> {supports: True/False/None, note}.
    Only confirmed (closing-price breakout already happened) patterns count
    — a pattern still 'forming' never supports or opposes a trade."""
    try:
        d = detect(df)
        confirmed = [p for p in d["patterns"] if p["confirmed"] and p["direction"] is not None]
        if not confirmed:
            return {"supports": None, "note": d["note"]}
        pick = confirmed[-1]
        supports = (pick["direction"] == "bull") == (direction == "long")
        return {"supports": supports, "note": f"chart pattern: {pick['note']}"}
    except Exception:  # noqa: BLE001
        return {"supports": None, "note": "chart patterns: unavailable"}
