"""Trend-following layer — EMA stack, ADX, MACD maturity.

Answers: is there a real, tradeable trend here, is it still young enough to
continue, or is it exhausted? Feeds the confluence engine; never trades alone.
Continuation (pullback) entries are only endorsed when the higher-timeframe
EMA stack agrees with the trade direction.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .technicals import ema, macd


def ema_stack(df: pd.DataFrame):
    """20/50/100/200 EMA alignment. Returns (direction, strength 0-4)."""
    try:
        c = df["Close"]
        e20 = float(ema(c, 20).iloc[-1])
        e50 = float(ema(c, 50).iloc[-1])
        e100 = float(ema(c, 100).iloc[-1]) if len(c) >= 100 else e50
        e200 = float(ema(c, 200).iloc[-1]) if len(c) >= 200 else e100
        px = float(c.iloc[-1])
        vals = [px, e20, e50, e100, e200]
        if all(vals[i] > vals[i + 1] for i in range(len(vals) - 1)):
            return "bull", 4
        if all(vals[i] < vals[i + 1] for i in range(len(vals) - 1)):
            return "bear", 4
        # partial alignment: count consecutive agreeing gaps from price down
        up = sum(1 for i in range(len(vals) - 1) if vals[i] > vals[i + 1])
        down = sum(1 for i in range(len(vals) - 1) if vals[i] < vals[i + 1])
        if up >= 3:
            return "bull", up
        if down >= 3:
            return "bear", down
        return "mixed", 0
    except Exception:  # noqa: BLE001
        return "mixed", 0


def adx(df: pd.DataFrame, n: int = 14) -> float:
    """Average Directional Index — trend strength (not direction)."""
    try:
        h, l, c = df["High"].astype(float), df["Low"].astype(float), df["Close"].astype(float)
        up_move = h.diff()
        down_move = -l.diff()
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        atr_n = tr.ewm(alpha=1 / n, adjust=False).mean()
        plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr_n.replace(0, np.nan)
        minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr_n.replace(0, np.nan)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        out = dx.ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
        return float(out) if pd.notna(out) else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def maturity(df: pd.DataFrame, direction: str, lookback: int = 40) -> str:
    """Trend-age heuristic via MACD histogram slope: 'young' (accelerating),
    'mature' (steady), or 'exhausted' (histogram fading vs trend direction).
    """
    try:
        c = df["Close"]
        _, _, hist = macd(c)
        h = hist.tail(lookback)
        if len(h) < 6:
            return "young"
        recent = float(h.tail(3).mean())
        prior = float(h.iloc[-6:-3].mean())
        if direction == "long":
            if recent > prior and recent > 0:
                return "young"
            if recent < 0:
                return "exhausted"
            return "mature"
        else:
            if recent < prior and recent < 0:
                return "young"
            if recent > 0:
                return "exhausted"
            return "mature"
    except Exception:  # noqa: BLE001
        return "mature"


def read(df15: pd.DataFrame, df_htf: pd.DataFrame, direction: str):
    """Full trend-quality read for the confluence engine.
    df15: execution timeframe (for ADX/maturity on entry TF).
    df_htf: higher timeframe (for stack alignment gating continuation).
    """
    stack_dir, stack_n = ema_stack(df_htf)
    adx_val = adx(df15)
    mat = maturity(df15, direction)
    trend_strength = "strong" if adx_val >= 25 else "weak" if adx_val < 15 else "developing"
    htf_agrees = (stack_dir == direction) or \
        (stack_dir == "bull" and direction == "long") or \
        (stack_dir == "bear" and direction == "short")
    continuation_ok = htf_agrees and mat != "exhausted" and adx_val >= 15
    lines = [
        f"EMA stack (HTF): {stack_dir} ({stack_n}/4 aligned)",
        f"ADX(14): {adx_val:.1f} ({trend_strength} trend)",
        f"trend maturity: {mat}",
        f"continuation eligible: {'yes' if continuation_ok else 'no'}",
    ]
    return {"stack_dir": stack_dir, "stack_n": stack_n, "adx": round(adx_val, 1),
            "trend_strength": trend_strength, "maturity": mat,
            "htf_agrees": htf_agrees, "continuation_ok": continuation_ok,
            "lines": lines}
