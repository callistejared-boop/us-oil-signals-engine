"""Mean-reversion layer — RSI, Bollinger, VWAP, ATR, Stochastic.

This module's job in the confluence engine is almost entirely defensive: it
flags when a market is overextended so the engine does not endorse a fresh
continuation entry into exhaustion, and it never authorizes a reversal trade
against a strong institutional trend without independent confirmation
(a liquidity sweep + CHoCH from ict_confluence/structure, checked by the
caller) — this module only measures extension, it doesn't decide direction.
"""
from __future__ import annotations

import pandas as pd

from .technicals import rsi, bollinger_pctb, rolling_vwap
from .structure import atr as _atr


def stochastic(df: pd.DataFrame, n: int = 14, d: int = 3):
    try:
        low_n = df["Low"].rolling(n).min()
        high_n = df["High"].rolling(n).max()
        span = (high_n - low_n).replace(0, pd.NA)
        k = 100 * (df["Close"] - low_n) / span
        k = k.fillna(50.0)
        d_line = k.rolling(d).mean().fillna(50.0)
        return float(k.iloc[-1]), float(d_line.iloc[-1])
    except Exception:  # noqa: BLE001
        return 50.0, 50.0


def extension_score(df: pd.DataFrame) -> dict:
    """0-100 'how stretched is this market' score, direction-agnostic beyond
    the sign: positive lean = stretched to the upside, negative = downside.
    """
    try:
        close = df["Close"]
        r = float(rsi(close).iloc[-1])
        pb = float(bollinger_pctb(close).iloc[-1])
        vw = float(rolling_vwap(df).iloc[-1])
        px = float(close.iloc[-1])
        a = float(_atr(df).iloc[-1])
        k, _ = stochastic(df)
        vwap_dist_atr = ((px - vw) / a) if a > 0 else 0.0

        up_votes = sum([r >= 70, pb >= 0.85, k >= 80, vwap_dist_atr >= 1.5])
        down_votes = sum([r <= 30, pb <= 0.15, k <= 20, vwap_dist_atr <= -1.5])
        score = max(up_votes, down_votes) * 25
        lean = "upside" if up_votes > down_votes else "downside" if down_votes > up_votes else "none"
        return {"score": score, "lean": lean, "rsi": round(r, 1),
                "pct_b": round(pb, 2), "stoch_k": round(k, 1),
                "vwap_dist_atr": round(vwap_dist_atr, 2)}
    except Exception:  # noqa: BLE001
        return {"score": 0, "lean": "none", "rsi": 50.0, "pct_b": 0.5,
                "stoch_k": 50.0, "vwap_dist_atr": 0.0}


def retracement_targets(swing_high: float, swing_low: float) -> dict:
    """Standard Fib retracement levels for a mean-reversion pullback target."""
    try:
        r = float(swing_high) - float(swing_low)
        if r <= 0:
            return {}
        return {f"{int(p*100)}%": round(swing_high - p * r, 4)
                for p in (0.236, 0.382, 0.5, 0.618, 0.786)}
    except Exception:  # noqa: BLE001
        return {}


def conflicts_with_continuation(ext: dict, direction: str) -> bool:
    """True if chasing a fresh continuation entry here fights an overextended
    tape (e.g., a new long when the market is already 100/100 stretched up).
    """
    if ext.get("score", 0) < 75:
        return False
    lean = ext.get("lean")
    return (direction == "long" and lean == "upside") or \
           (direction == "short" and lean == "downside")


def read(df: pd.DataFrame, direction: str, swing_high=None, swing_low=None):
    ext = extension_score(df)
    conflict = conflicts_with_continuation(ext, direction)
    lines = [f"extension score: {ext['score']}/100 (lean {ext['lean']})",
             f"RSI {ext['rsi']} | Bollinger %B {ext['pct_b']} | "
             f"Stoch %K {ext['stoch_k']} | VWAP dist {ext['vwap_dist_atr']} ATR"]
    if conflict:
        lines.append(f"CONFLICT: market overextended {ext['lean']} — "
                     f"chasing a fresh {direction} here fights exhaustion")
    targets = {}
    if swing_high is not None and swing_low is not None:
        targets = retracement_targets(swing_high, swing_low)
        if targets:
            lines.append("retracement targets: " +
                         ", ".join(f"{k} {v}" for k, v in targets.items()))
    return {"extension": ext, "conflict": conflict, "targets": targets, "lines": lines}
