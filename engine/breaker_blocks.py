"""Breaker blocks, mitigation blocks, and inversion FVGs — advanced ICT/SMC
concepts from the institutional-trading literature review (ICT Institutional
SMC Trading, The Institutional Trading Bible) that weren't yet in the engine.

These describe what happens AFTER an order block or FVG fails, not just
whether one exists right now:

  * Breaker block: a prior order block that price closed clean through
    (invalidating it in its original direction). It flips polarity — a
    broken bullish OB becomes resistance (bearish breaker) on retest, and
    vice versa. This is genuinely new information: the existing
    `ict.order_block()` only ever reports the most recent OB candidate, it
    never tracks what happened to older ones after they failed.
  * Inversion FVG (IFVG): an FVG is normally "filled" when price wicks back
    into its near edge (already tracked by structure.find_fvgs). It
    INVERTS when a later bar's CLOSE trades fully through the far edge —
    a materially stronger statement than a wick-fill — and then acts as
    the opposite kind of level on the next retest.
  * Mitigation block (pragmatic proxy): a swing point that structure has
    since broken (BOS/CHoCH away from it) and price is now returning to.
    The book's definition is somewhat qualitative ("where institutions
    close remaining positions"); this module implements the closest
    honestly-computable proxy — a broken swing level being retested — and
    is documented as an approximation, the same way `volume_profile.py`
    flags its own tick-volume approximation rather than overstating it.

  * Rejection block (from ICT Institutional SMC Trading, David Woods): a
    session high or low (Asia/London/NY) that price sweeps with a wick and
    then rejects sharply away from -- the book's own description is that
    "the session's high and low tend to be just liquidity" and that a
    rejection is materially STRONGER when it was preceded by inducement
    (a smaller, earlier liquidity grab that lured traders the wrong way
    first). This is genuinely new: nothing else in the engine currently
    scores a session-extreme sweep-and-reject on its own.

Fail-safe throughout: any computation issue -> neutral read, never raises.
"""
from __future__ import annotations

import pandas as pd

from . import structure as st

LOOKBACK = 300
PROXIMITY_ATR_MULT = 0.5
REJECTION_WICK_MULT = 1.3   # rejection wick must be >= this x the body to count
REJECTION_LOOKAHEAD = 3     # bars after the sweep to confirm the reject held


def find_inversion_fvgs(df: pd.DataFrame, lookback: int = LOOKBACK) -> list:
    """Return FVGs whose far edge has since been CLOSED through (not just
    wicked into) — these flip polarity. Each item:
    {"kind": "bull"->"bear" or "bear"->"bull" (new acting kind),
     "top": float, "bottom": float, "inverted_idx": int}."""
    try:
        sub = df.tail(lookback).reset_index(drop=True)
        gaps = st.find_fvgs(sub)
        close = sub["Close"].values
        out = []
        for g in gaps:
            far_edge = g.bottom if g.kind == "bull" else g.top
            seg = close[g.created_idx + 1:]
            if g.kind == "bull":
                hit = next((j for j, c in enumerate(seg) if c < far_edge), None)
            else:
                hit = next((j for j, c in enumerate(seg) if c > far_edge), None)
            if hit is not None:
                inverted_idx = g.created_idx + 1 + hit
                out.append({
                    "kind": "bear" if g.kind == "bull" else "bull",
                    "top": g.top, "bottom": g.bottom,
                    "inverted_idx": inverted_idx,
                })
        return out
    except Exception:  # noqa: BLE001
        return []


def find_breaker_blocks(df: pd.DataFrame, lookback: int = LOOKBACK) -> list:
    """Scan recent displacement candles (the same OB heuristic as
    ict.order_block, applied to every candidate, not just the latest) and
    report which have since been closed through and flipped to breakers.
    Each item: {"kind": "bull"->"bear" or "bear"->"bull", "top": float,
    "bottom": float, "broken_idx": int}."""
    try:
        sub = df.tail(lookback).reset_index(drop=True)
        o, c, h, l = sub["Open"].values, sub["Close"].values, sub["High"].values, sub["Low"].values
        avg_range = pd.Series(h - l).rolling(20).mean().values
        out = []
        for i in range(2, len(sub) - 1):
            if pd.isna(avg_range[i]):
                continue
            # bullish OB candidate: last bearish candle before a strong bull displacement
            if c[i] > o[i] and (c[i] - o[i]) > 1.2 * avg_range[i] and c[i - 1] < o[i - 1]:
                ob_top, ob_bottom = h[i - 1], l[i - 1]
                seg = c[i + 1:]
                hit = next((j for j, cc in enumerate(seg) if cc < ob_bottom), None)
                if hit is not None:
                    out.append({"kind": "bear", "top": float(ob_top), "bottom": float(ob_bottom),
                               "broken_idx": i + 1 + hit})
            # bearish OB candidate: last bullish candle before a strong bear displacement
            if c[i] < o[i] and (o[i] - c[i]) > 1.2 * avg_range[i] and c[i - 1] > o[i - 1]:
                ob_top, ob_bottom = h[i - 1], l[i - 1]
                seg = c[i + 1:]
                hit = next((j for j, cc in enumerate(seg) if cc > ob_top), None)
                if hit is not None:
                    out.append({"kind": "bull", "top": float(ob_top), "bottom": float(ob_bottom),
                               "broken_idx": i + 1 + hit})
        return out
    except Exception:  # noqa: BLE001
        return []


def find_mitigation_zones(df: pd.DataFrame, lookback: int = LOOKBACK) -> list:
    """Pragmatic proxy for mitigation blocks: swing points that structure
    has broken (a later close traded through them), i.e. levels the market
    has already invalidated and could return to 'mitigate'. Each item:
    {"kind": "bull"->support-to-revisit or "bear"->resistance-to-revisit,
     "price": float, "broken_idx": int}."""
    try:
        sub = df.tail(lookback).reset_index(drop=True)
        swings = st.find_swings(sub["High"].values, sub["Low"].values, k=3)
        close = sub["Close"].values
        out = []
        for s in swings:
            seg = close[s.confirmed_idx + 1:]
            if s.kind == "H":
                hit = next((j for j, cc in enumerate(seg) if cc > s.price), None)
                if hit is not None:
                    out.append({"kind": "bull", "price": s.price,
                               "broken_idx": s.confirmed_idx + 1 + hit})
            else:
                hit = next((j for j, cc in enumerate(seg) if cc < s.price), None)
                if hit is not None:
                    out.append({"kind": "bear", "price": s.price,
                               "broken_idx": s.confirmed_idx + 1 + hit})
        return out
    except Exception:  # noqa: BLE001
        return []


def find_rejection_blocks(df: pd.DataFrame, lookback: int = LOOKBACK) -> list:
    """Session-extreme sweep-and-reject: a bar that takes out the prior
    N-bar high/low with its wick, closes back inside, and is followed by a
    hold (price doesn't return through the wick tip within REJECTION_LOOKAHEAD
    bars). Flagged as an "inducement" case (stronger per the source book)
    when a smaller opposite-direction wick swept a nearby level shortly
    before it -- a two-step lure-then-reject sequence. Each item:
    {"kind": "bull"->rejection off a low or "bear"->rejection off a high,
     "price": float (the wick extreme), "idx": int, "inducement": bool}."""
    try:
        sub = df.tail(lookback).reset_index(drop=True)
        o, c, h, l = sub["Open"].values, sub["Close"].values, sub["High"].values, sub["Low"].values
        n = len(sub)
        out = []
        for i in range(10, n - REJECTION_LOOKAHEAD):
            prior_hi = h[max(0, i - 10):i].max()
            prior_lo = l[max(0, i - 10):i].min()
            body = abs(c[i] - o[i])
            upper_wick = h[i] - max(o[i], c[i])
            lower_wick = min(o[i], c[i]) - l[i]

            # bearish rejection: wick sweeps above prior high, closes back below it
            if h[i] > prior_hi and c[i] < prior_hi and upper_wick > 0                     and upper_wick >= REJECTION_WICK_MULT * max(body, 1e-9):
                held = h[i + 1:i + 1 + REJECTION_LOOKAHEAD].max() < h[i] if i + 1 < n else True
                if held:
                    inducement = i >= 4 and l[i - 4:i - 1].min() < l[max(0, i - 8):i - 4].min()
                    out.append({"kind": "bear", "price": float(h[i]), "idx": i,
                               "inducement": bool(inducement)})

            # bullish rejection: wick sweeps below prior low, closes back above it
            if l[i] < prior_lo and c[i] > prior_lo and lower_wick > 0                     and lower_wick >= REJECTION_WICK_MULT * max(body, 1e-9):
                held = l[i + 1:i + 1 + REJECTION_LOOKAHEAD].min() > l[i] if i + 1 < n else True
                if held:
                    inducement = i >= 4 and h[i - 4:i - 1].max() > h[max(0, i - 8):i - 4].max()
                    out.append({"kind": "bull", "price": float(l[i]), "idx": i,
                               "inducement": bool(inducement)})
        return out
    except Exception:  # noqa: BLE001
        return []


def _fresh(items, idx_key, n_bars, min_bars_ago=0):
    """Only the most recent handful count as 'fresh' — old broken levels
    that were never retested lose relevance."""
    return sorted(items, key=lambda x: -x[idx_key])[:n_bars]


def alignment(df: pd.DataFrame, direction: str, price: float, atr_val: float) -> dict:
    """Is price currently sitting at/near a fresh breaker block, inversion
    FVG, mitigation zone, or a just-confirmed rejection block that supports
    `direction`? Soft signal -> {supports: True/False/None, note}."""
    try:
        tol = max(atr_val, 1e-6) * PROXIMITY_ATR_MULT
        want_kind = "bull" if direction == "long" else "bear"
        hits, against = [], []

        for b in _fresh(find_breaker_blocks(df), "broken_idx", 8):
            if b["bottom"] - tol <= price <= b["top"] + tol:
                (hits if b["kind"] == want_kind else against).append(
                    f"breaker block {b['bottom']:.2f}-{b['top']:.2f} ({b['kind']})")

        for g in _fresh(find_inversion_fvgs(df), "inverted_idx", 8):
            if g["bottom"] - tol <= price <= g["top"] + tol:
                (hits if g["kind"] == want_kind else against).append(
                    f"inversion FVG {g['bottom']:.2f}-{g['top']:.2f} ({g['kind']})")

        for m in _fresh(find_mitigation_zones(df), "broken_idx", 10):
            if abs(price - m["price"]) <= tol:
                (hits if m["kind"] == want_kind else against).append(
                    f"mitigation zone {m['price']:.2f} ({m['kind']})")

        for r in _fresh(find_rejection_blocks(df), "idx", 6):
            if abs(price - r["price"]) <= tol:
                tag = " +inducement" if r["inducement"] else ""
                (hits if r["kind"] == want_kind else against).append(
                    f"rejection block {r['price']:.2f} ({r['kind']}{tag})")

        if not hits and not against:
            return {"supports": None, "note": "breaker/mitigation: no fresh zone at price"}
        supports = bool(hits) and not against
        if hits and against:
            supports = len(hits) >= len(against)
        note = "breaker/mitigation: " + "; ".join((hits + against)[:3])
        return {"supports": supports, "note": note}
    except Exception:  # noqa: BLE001
        return {"supports": None, "note": "breaker/mitigation: unavailable"}
