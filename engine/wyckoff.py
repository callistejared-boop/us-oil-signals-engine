"""Wyckoff method layer — mapped onto the ICT primitives we already compute.

Wyckoff and ICT/SMC describe the same institutional behaviour with different
vocabulary, so this module is mostly a translation + confirmation layer
rather than new detection logic:

  * Spring   = bullish liquidity sweep below range support that reclaims
               (ict_confluence.liquidity_sweep, direction="long")
  * Upthrust = bearish liquidity sweep above range resistance that reclaims
               (ict_confluence.liquidity_sweep, direction="short")
  * SOS (Sign of Strength) / SOW (Sign of Weakness) = a momentum candle
    (price_action.momentum_candle) breaking away from the range in the
    trade direction, on expanding range (regime.atr_percentile rising).
  * Phase = accumulation / markup / distribution / markdown, reusing
    regime.classify's phase field directly (same range-position + trend
    logic Wyckoff analysts use by hand).
  * Composite operator behaviour = effort-vs-result divergence: large
    range/volume with little net price progress suggests absorption
    (an institutional operator building a position quietly).
"""
from __future__ import annotations

from . import ict_confluence as icf
from . import price_action as pa
from . import regime as rg


def spring_or_upthrust(df15, direction):
    ok, level, ago = icf.liquidity_sweep(df15, direction)
    if not ok:
        return None
    return {"event": "spring" if direction == "long" else "upthrust",
            "level": level, "bars_ago": ago}


def sign_of_strength_weakness(df15, direction, atr_val):
    mom = pa.momentum_candle(df15, atr_val=atr_val)
    if mom is None:
        return None
    if (direction == "long" and mom == "bull") or (direction == "short" and mom == "bear"):
        return "SOS" if direction == "long" else "SOW"
    return None


def effort_vs_result(df15, n: int = 10) -> dict:
    """Compare recent range expansion (effort) to net price progress (result).
    High effort + low result => possible absorption / composite-operator
    accumulation or distribution rather than a clean directional move.
    """
    try:
        sub = df15.tail(n)
        total_range = float((sub["High"] - sub["Low"]).sum())
        net_move = float(abs(sub["Close"].iloc[-1] - sub["Close"].iloc[0]))
        if total_range <= 0:
            return {"absorption": False, "efficiency": 0.0}
        efficiency = net_move / total_range
        return {"absorption": efficiency < 0.25, "efficiency": round(efficiency, 2)}
    except Exception:  # noqa: BLE001
        return {"absorption": False, "efficiency": 0.0}


def read(df15, direction, atr_val, htf_df=None):
    event = spring_or_upthrust(df15, direction)
    sosw = sign_of_strength_weakness(df15, direction, atr_val)
    evr = effort_vs_result(df15)
    phase_df = htf_df if htf_df is not None else df15
    phase = rg.classify(phase_df).get("phase", "unknown")

    lines = [f"phase: {phase}"]
    if event:
        lines.append(f"{event['event'].upper()} at {event['level']} "
                     f"({event['bars_ago']} bars ago) — classic reversal signature")
    if sosw:
        lines.append(f"{sosw}: momentum candle confirms {direction} away from the range")
    if evr["absorption"]:
        lines.append(f"absorption warning: effort/result {evr['efficiency']} — "
                     "wide range, little net progress (possible composite-operator activity)")
    agree_count = sum([bool(event), bool(sosw)]) - (1 if evr["absorption"] else 0)
    return {"phase": phase, "event": event, "sos_sow": sosw,
            "absorption": evr["absorption"], "efficiency": evr["efficiency"],
            "agree_count": agree_count, "lines": lines}
