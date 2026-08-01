"""Balanced Price Range (BPR) and Consequent Encroachment (CE).

Provenance note, said plainly: both names come from the uploaded "Smart
Money 200-Page Master Guide" (Page 51: "Balanced Price Range", Page 52:
"Consequent Encroachment"), but that document turned out to be templated
boilerplate -- every page shares identical generic paragraphs with only the
title swapped in, giving no unique operational rule for either concept.
This implementation is standard ICT/SMC domain knowledge (the concepts are
well-established outside that specific document), not something extracted
from its content.

BPR: two Fair Value Gaps of OPPOSITE kind that overlap in price -- price
printed an inefficient gap moving one way, then shortly after, an
inefficient gap moving the other way, and the two gaps' price ranges
overlap. That overlap represents genuine two-sided order flow (both a
buy-side and a sell-side inefficiency at the same level) rather than a
one-sided imbalance, so ICT teaching treats it as a more reliable
support/resistance/re-entry zone than either FVG alone.

CE: the midpoint (50%) of a gap or a BPR. structure.find_fvgs() already
exposes this as FVG.mid, but ICT teaching treats the midpoint specifically
(not "anywhere in the gap") as the level price is expected to react to on
a retest, so this module surfaces it as its own explicit signal.

Fail-safe throughout: any computation issue -> neutral read, never raises.
"""
from __future__ import annotations

import pandas as pd

from . import structure as st

LOOKBACK = 300
PROXIMITY_ATR_MULT = 0.3
FRESH_GAP_SPAN = 60   # the two FVGs forming a BPR must be within this many bars of each other


def find_bprs(df: pd.DataFrame, lookback: int = LOOKBACK) -> list:
    """Overlapping bull/bear FVG pairs. Each item:
    {"top": float, "bottom": float, "ce": float (midpoint),
     "bull_idx": int, "bear_idx": int}."""
    try:
        sub = df.tail(lookback).reset_index(drop=True)
        gaps = st.find_fvgs(sub)
        bulls = [g for g in gaps if g.kind == "bull"]
        bears = [g for g in gaps if g.kind == "bear"]
        out = []
        for bg in bulls:
            for rg in bears:
                if abs(bg.created_idx - rg.created_idx) > FRESH_GAP_SPAN:
                    continue
                top = min(bg.top, rg.top)
                bottom = max(bg.bottom, rg.bottom)
                if top > bottom:  # genuine overlap, not just adjacency
                    out.append({"top": top, "bottom": bottom, "ce": (top + bottom) / 2.0,
                               "bull_idx": bg.created_idx, "bear_idx": rg.created_idx})
        return out
    except Exception:  # noqa: BLE001
        return []


def alignment(df: pd.DataFrame, direction: str, price: float, atr_val: float,
             lookback: int = LOOKBACK) -> dict:
    """Is price sitting at/near a fresh BPR or its consequent-encroachment
    midpoint? Soft signal -> {supports: True/False/None, note}. A BPR is
    directionally neutral by construction (it's two-sided balance, not a
    directional zone), so proximity alone is treated as support for
    EITHER direction -- it's evidence of a real reaction level, not a bias."""
    try:
        tol = max(atr_val, 1e-6) * PROXIMITY_ATR_MULT
        bprs = find_bprs(df, lookback)
        if not bprs:
            return {"supports": None, "note": "BPR/CE: no balanced price range nearby"}
        fresh = sorted(bprs, key=lambda b: -max(b["bull_idx"], b["bear_idx"]))[:5]
        for b in fresh:
            if b["bottom"] - tol <= price <= b["top"] + tol:
                return {"supports": True,
                        "note": f"BPR/CE: price inside balanced range "
                                f"{b['bottom']:.2f}-{b['top']:.2f} (CE {b['ce']:.2f})"}
            if abs(price - b["ce"]) <= tol:
                return {"supports": True,
                        "note": f"BPR/CE: price at consequent encroachment {b['ce']:.2f}"}
        return {"supports": None, "note": "BPR/CE: no fresh balanced range at price"}
    except Exception:  # noqa: BLE001
        return {"supports": None, "note": "BPR/CE: unavailable"}
