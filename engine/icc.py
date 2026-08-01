"""ICC -- Indication, Correction, Continuation.

Provenance note, said plainly: this framework is named in the uploaded
"Smart Money 200-Page Master Guide" (pages 77-88: Confluence, Zone
Refinement, Indication, Correction, Continuation, Failed Indication,
Continuation Confirmation, ICC Entry Logic/Risk Placement, ICC with
ICT/SMC/Fibonacci) -- but that document is templated boilerplate with no
unique operational rule behind any page title (confirmed by spot-checking
across multiple modules). This implementation is a plain-language reading
of the framework's own name, checked directly against swing structure --
not something extracted from that document's content.

  Indication:   a swing forms and price moves away from it, suggesting a
                directional bias (P0 -> P1).
  Correction:   price pulls back against that indication without fully
                retracing past its origin (P1 -> P2).
  Continuation: price resumes beyond P1 in the indication's original
                direction, confirming the read.

This is deliberately a simpler, single-degree, 3-point check -- closer to
just wave 1-2-3 of an impulse than the full 5-wave elliott_wave.py rule
set, and distinct from trend_quality.py's continuation_ok (which reads
EMA-stack/ADX momentum, not swing geometry). Not a Layer-1 origination
method: confirmation only, same as everything else feeding confluence.py.

Fail-safe throughout: any computation issue -> neutral read, never raises.
"""
from __future__ import annotations

import pandas as pd

from . import structure as st

LOOKBACK = 300


def read(df: pd.DataFrame, lookback: int = LOOKBACK) -> dict:
    """Returns {"phase": "continuation"/"correction"/None, "direction":
    "long"/"short"/None, "note": str}."""
    try:
        sub = df.tail(lookback).reset_index(drop=True)
        swings = st.find_swings(sub["High"].values, sub["Low"].values, k=st.SWING_K)
        if len(swings) < 3:
            return {"phase": None, "direction": None,
                    "note": "ICC: insufficient swing structure (need 3 confirmed swings)"}
        p0, p1, p2 = swings[-3], swings[-2], swings[-1]
        if p0.kind == p1.kind or p1.kind == p2.kind:
            return {"phase": None, "direction": None,
                    "note": "ICC: last 3 swings don't form a clean indication/correction sequence"}

        last_close = float(sub["Close"].iloc[-1])
        direction = "long" if p1.price > p0.price else "short"
        if direction == "long":
            correction_valid = p0.price < p2.price < p1.price
            continuation = last_close > p1.price
        else:
            correction_valid = p1.price < p2.price < p0.price
            continuation = last_close < p1.price

        if not correction_valid:
            return {"phase": None, "direction": None,
                    "note": "ICC: no valid indication -> correction sequence "
                            f"(P0 {p0.price:.2f}, P1 {p1.price:.2f}, P2 {p2.price:.2f})"}

        phase = "continuation" if continuation else "correction"
        return {"phase": phase, "direction": direction,
                "note": f"ICC: indication {direction} (P0 {p0.price:.2f} -> P1 {p1.price:.2f}), "
                        f"correction to {p2.price:.2f}, phase={phase}"}
    except Exception:  # noqa: BLE001
        return {"phase": None, "direction": None, "note": "ICC: unavailable"}


def alignment(df: pd.DataFrame, direction: str, lookback: int = LOOKBACK) -> dict:
    """Soft signal -> {supports: True/False/None, note}. Only a confirmed
    CONTINUATION phase counts as support/opposition; a correction still in
    progress is neutral (too early to say), not a warning."""
    try:
        r = read(df, lookback)
        if r["phase"] is None:
            return {"supports": None, "note": r["note"]}
        if r["phase"] != "continuation":
            return {"supports": None, "note": r["note"] + " (correction still in progress)"}
        supports = r["direction"] == direction
        return {"supports": supports, "note": r["note"]}
    except Exception:  # noqa: BLE001
        return {"supports": None, "note": "ICC: unavailable"}
