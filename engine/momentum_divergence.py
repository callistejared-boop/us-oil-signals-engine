"""Momentum (RSI) divergence layer — a genuinely new confirmation source,
not a re-weighting of anything already in the engine.

Gap this closes: technicals.py/mean_reversion.py already use RSI's absolute
LEVEL (overbought/oversold), but nothing in the engine checked RSI's SHAPE
against price's shape. Classic regular divergence — price prints a new
extreme while the oscillator fails to confirm it — is one of the most
widely used institutional exhaustion signals precisely because it catches
the moment participation is quietly drying up even though price is still
pushing. This module detects it directly from swing pivots, independent of
mean_reversion's extension score.

Only regular (reversal-warning) divergence is detected — bearish divergence
at swing highs, bullish divergence at swing lows. Hidden (continuation)
divergence is deliberately out of scope: it's a weaker, more ambiguous
signal and would add noise without a clear net benefit.

Fail-safe throughout: any computation issue -> neutral read, never raises.
"""
from __future__ import annotations

import pandas as pd

from .technicals import rsi

LOOKBACK = 120     # bars of the execution timeframe to scan for swings
PIVOT_WING = 3     # bars on each side that must be lower/higher to count as a swing


def _pivots(series: pd.Series, wing: int = PIVOT_WING, kind: str = "high"):
    """Return index positions of local swing highs/lows in `series`."""
    out = []
    vals = series.values
    n = len(vals)
    for i in range(wing, n - wing):
        window = vals[i - wing:i + wing + 1]
        center = vals[i]
        if kind == "high" and center == window.max() and \
           (window == center).sum() == 1:
            out.append(i)
        elif kind == "low" and center == window.min() and \
             (window == center).sum() == 1:
            out.append(i)
    return out


def detect(df: pd.DataFrame, lookback: int = LOOKBACK) -> dict:
    """Scan the last `lookback` bars for the most recent regular divergence
    at swing highs (bearish) and swing lows (bullish)."""
    try:
        sub = df.tail(lookback)
        if len(sub) < 30:
            return {"bearish_div": False, "bullish_div": False,
                    "note": "momentum divergence: insufficient bars", "lines": []}
        close = sub["Close"]
        r = rsi(close)

        lines = []
        bearish_div = bullish_div = False

        hi_idx = _pivots(sub["High"], kind="high")
        if len(hi_idx) >= 2:
            i1, i2 = hi_idx[-2], hi_idx[-1]           # older, newer swing high
            price_hh = sub["High"].iloc[i2] > sub["High"].iloc[i1]
            rsi_lower = r.iloc[i2] < r.iloc[i1]
            if price_hh and rsi_lower:
                bearish_div = True
                lines.append(
                    f"bearish RSI divergence: price higher-high "
                    f"({sub['High'].iloc[i1]:.2f} -> {sub['High'].iloc[i2]:.2f}) "
                    f"while RSI lower-high ({r.iloc[i1]:.1f} -> {r.iloc[i2]:.1f})")

        lo_idx = _pivots(sub["Low"], kind="low")
        if len(lo_idx) >= 2:
            i1, i2 = lo_idx[-2], lo_idx[-1]
            price_ll = sub["Low"].iloc[i2] < sub["Low"].iloc[i1]
            rsi_higher = r.iloc[i2] > r.iloc[i1]
            if price_ll and rsi_higher:
                bullish_div = True
                lines.append(
                    f"bullish RSI divergence: price lower-low "
                    f"({sub['Low'].iloc[i1]:.2f} -> {sub['Low'].iloc[i2]:.2f}) "
                    f"while RSI higher-low ({r.iloc[i1]:.1f} -> {r.iloc[i2]:.1f})")

        if not lines:
            lines.append("no active regular RSI divergence at recent swings")

        return {"bearish_div": bearish_div, "bullish_div": bullish_div,
                "note": "; ".join(lines), "lines": lines}
    except Exception:  # noqa: BLE001
        return {"bearish_div": False, "bullish_div": False,
                "note": "momentum divergence: unavailable", "lines": []}


def alignment(df: pd.DataFrame, direction: str) -> dict:
    """Does active divergence support or warn against `direction`?
    Soft signal -> {supports: True/False/None, note}."""
    d = detect(df)
    if d["bullish_div"] and not d["bearish_div"]:
        supports = direction == "long"
    elif d["bearish_div"] and not d["bullish_div"]:
        supports = direction == "short"
    else:
        return {"supports": None, "note": d["note"]}
    return {"supports": supports, "note": d["note"]}
