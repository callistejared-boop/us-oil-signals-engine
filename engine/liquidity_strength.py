"""Strong vs. weak liquidity confirmation layer.

ICT/SMC teaching commonly distinguishes a "strong" high/low (defended by
real displacement away from it -> unlikely to be swept easily, a genuine
structural level) from a "weak" one (no strong reaction after it formed ->
undefended, a high-probability "draw on liquidity" target the algo is more
likely to run). structure.classify_swing_strength() implements this as a
pragmatic proxy (move-away-from-swing size vs. ATR over a short reaction
window). This module turns that classification into a soft confirmation
signal: if the nearest liquidity pool in the trade's direction is WEAK, that
supports the trade (a sweep-and-continue is a common, tradeable outcome);
if the nearest pool is STRONG, that's a caution (it may hold as real
resistance/support rather than get run).

Note on provenance: this concept and its name appear in the uploaded
"Smart Money 200-Page Master Guide", but that document turned out to be
templated boilerplate -- every page shares identical generic paragraphs
with only the title swapped in, so it gave no unique operational rule.
This implementation is standard ICT/SMC domain knowledge, not something
extracted from that document's specific content. Said plainly here rather
than overclaiming it as document-derived.

Fail-safe throughout: any computation issue -> neutral read, never raises.
"""
from __future__ import annotations

import pandas as pd

from . import structure as st

LOOKBACK = 300
REACTION_BARS = 5
REACTION_MULT = 1.5


def nearest_labelled_pool(df: pd.DataFrame, price: float, direction: str,
                          lookback: int = LOOKBACK):
    """Nearest swing-based liquidity pool ahead of price in the trade's
    direction, labelled 'strong' or 'weak'. Returns dict or None."""
    sub = df.tail(lookback).reset_index(drop=True)
    if len(sub) < 20:
        return None
    atr_val = float(st.atr(sub).iloc[-1])
    if not atr_val or atr_val <= 0 or pd.isna(atr_val):
        return None
    swings = st.find_swings(sub["High"].values, sub["Low"].values, k=st.SWING_K)
    labelled = st.classify_swing_strength(sub, swings, atr_val,
                                          reaction_bars=REACTION_BARS,
                                          reaction_mult=REACTION_MULT)
    want_kind = "H" if direction == "long" else "L"
    candidates = [s for s in labelled if s.kind == want_kind and s.strength
                  and ((direction == "long" and s.price > price)
                       or (direction == "short" and s.price < price))]
    if not candidates:
        return None
    nearest = min(candidates, key=lambda s: abs(s.price - price))
    return {"price": nearest.price, "strength": nearest.strength}


def alignment(df: pd.DataFrame, direction: str, price: float) -> dict:
    """Soft signal -> {supports: True/False/None, note}. WEAK nearest pool
    in the trade's direction supports it (sweep-and-continue is likely);
    STRONG nearest pool is a caution (may hold, not get swept)."""
    try:
        pool = nearest_labelled_pool(df, price, direction)
        if pool is None:
            return {"supports": None, "note": "liquidity strength: no labelled pool nearby"}
        if pool["strength"] == "weak":
            return {"supports": True,
                    "note": f"liquidity strength: weak {('high' if direction == 'long' else 'low')} "
                            f"at {pool['price']:.2f} - undefended, likely sweep target"}
        return {"supports": False,
                "note": f"liquidity strength: strong {('high' if direction == 'long' else 'low')} "
                        f"at {pool['price']:.2f} - defended, may hold as real resistance/support"}
    except Exception:  # noqa: BLE001
        return {"supports": None, "note": "liquidity strength: unavailable"}
