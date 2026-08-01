"""Classical floor-trader pivot points — daily and weekly.

Gap this closes: every level the engine currently trades off (OTE, FVG,
order blocks, swing highs/lows, value area) comes from ICT/SMC or volume
profile. None of it is the specific set of prior-period-derived levels a
large slice of the participants on the other side of every trade (CTAs,
prop desks, and plenty of ICT traders themselves) are also watching. Pivot
confluence doesn't predict direction — it flags when an entry, stop, or
target lines up with a level that independently-informed order flow is
also likely to react to, which is exactly what "confluence" is supposed to
mean.

Standard floor-trader formula from the prior period's OHLC:
  P  = (H + L + C) / 3
  R1 = 2P - L      S1 = 2P - H
  R2 = P + (H - L) S2 = P - (H - L)
  R3 = H + 2*(P-L) S3 = L - 2*(H-P)

Computed from the prior completed daily bar and prior completed weekly bar.
Fail-safe throughout: any computation issue -> neutral read, never raises.
"""
from __future__ import annotations

import pandas as pd

from .data_loader import resample

PROXIMITY_ATR_MULT = 0.35   # how close a price must be to count as "at" a pivot level


def _floor_pivots(o: float, h: float, l: float, c: float) -> dict:
    p = (h + l + c) / 3.0
    r1, s1 = 2 * p - l, 2 * p - h
    r2, s2 = p + (h - l), p - (h - l)
    r3, s3 = h + 2 * (p - l), l - 2 * (h - p)
    return {"P": p, "R1": r1, "R2": r2, "R3": r3, "S1": s1, "S2": s2, "S3": s3}


def compute(df15: pd.DataFrame) -> dict:
    """Prior-day and prior-week pivot sets from the execution-timeframe df."""
    out = {"daily": None, "weekly": None}
    try:
        d1 = resample(df15, "1d")
        if len(d1) >= 2:
            prior = d1.iloc[-2]   # last *completed* daily bar
            out["daily"] = _floor_pivots(float(prior.Open), float(prior.High),
                                         float(prior.Low), float(prior.Close))
    except Exception:  # noqa: BLE001
        pass
    try:
        w1 = resample(df15, "1w")
        if len(w1) >= 2:
            prior = w1.iloc[-2]
            out["weekly"] = _floor_pivots(float(prior.Open), float(prior.High),
                                          float(prior.Low), float(prior.Close))
    except Exception:  # noqa: BLE001
        pass
    return out


def _nearest(levels: dict, price: float):
    if not levels:
        return None, None
    name = min(levels, key=lambda k: abs(levels[k] - price))
    return name, levels[name]


def alignment(df15: pd.DataFrame, direction: str, entry: float, atr_val: float) -> dict:
    """Does the entry sit at/near a pivot level in a direction-consistent
    way? Longs get credit resting on/above a support pivot (P/S1-3); shorts
    get credit resting on/below a resistance pivot (P/R1-3). Soft signal ->
    {supports: True/False/None, note}."""
    try:
        piv = compute(df15)
        tol = max(atr_val, 1e-6) * PROXIMITY_ATR_MULT
        hits = []
        for label, levels in (("daily", piv["daily"]), ("weekly", piv["weekly"])):
            if not levels:
                continue
            name, val = _nearest(levels, entry)
            if name is None or abs(val - entry) > tol:
                continue
            is_support = name.startswith("S") or name == "P"
            is_resistance = name.startswith("R") or name == "P"
            if direction == "long" and is_support:
                hits.append((True, f"{label} {name} {val:.2f} (support, {abs(entry-val):.2f} away)"))
            elif direction == "short" and is_resistance:
                hits.append((True, f"{label} {name} {val:.2f} (resistance, {abs(entry-val):.2f} away)"))
            else:
                # sitting at a level that argues the other way is a mild warning
                hits.append((False, f"{label} {name} {val:.2f} works against {direction} here"))
        if not hits:
            return {"supports": None, "note": "pivots: entry not near a daily/weekly pivot level"}
        supports = any(h[0] for h in hits)
        note = "pivots: " + "; ".join(h[1] for h in hits)
        return {"supports": supports, "note": note}
    except Exception:  # noqa: BLE001
        return {"supports": None, "note": "pivots: unavailable"}


def lines(df15: pd.DataFrame) -> list:
    piv = compute(df15)
    out = []
    for label, levels in (("Daily", piv["daily"]), ("Weekly", piv["weekly"])):
        if not levels:
            out.append(f"{label} pivots: unavailable")
            continue
        out.append(f"{label} pivots: P {levels['P']:.2f} | "
                   f"R1 {levels['R1']:.2f} R2 {levels['R2']:.2f} | "
                   f"S1 {levels['S1']:.2f} S2 {levels['S2']:.2f}")
    return out
