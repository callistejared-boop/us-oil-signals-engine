"""Market-regime detection — trend/range + volatility expansion/contraction.

Institutional context: ICT/SMC setups behave very differently in a trend vs a
range, and in high vs low volatility. This classifies the current regime so the
engine (and you) can weight setups accordingly, and so every read is explainable.

Method (transparent, no black box):
- Kaufman Efficiency Ratio (ER) = net move / total path over a lookback.
  High ER => directional/trending; low ER => choppy/ranging.
- ATR percentile over a lookback => volatility expansion vs contraction.
- A coarse Wyckoff-style phase from trend direction + range position.
Pure function of price; fully testable; degrades to 'unknown' on thin data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TREND_ER = 0.35          # ER at/above this => trending
EXP_PCT, CON_PCT = 0.70, 0.30


def efficiency_ratio(closes, n: int = 20) -> float:
    c = np.asarray(closes, dtype=float)
    if len(c) < n + 1:
        return 0.0
    seg = c[-(n + 1):]
    net = abs(seg[-1] - seg[0])
    path = np.abs(np.diff(seg)).sum()
    return float(net / path) if path > 0 else 0.0


def atr_percentile(df: pd.DataFrame, period: int = 14, lookback: int = 100) -> float:
    h, l, c = df["High"].astype(float), df["Low"].astype(float), df["Close"].astype(float)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().dropna()
    if len(atr) < 5:
        return 0.5
    window = atr.tail(lookback)
    cur = atr.iloc[-1]
    return float((window <= cur).mean())


def classify(df: pd.DataFrame, er_len: int = 20) -> dict:
    if df is None or len(df) < er_len + 2:
        return {"er": 0.0, "trend": "unknown", "atr_pct": 0.5, "vol": "unknown",
                "phase": "unknown", "label": "unknown"}
    er = efficiency_ratio(df["Close"].values, er_len)
    trend = "trend" if er >= TREND_ER else "range"
    atr_pct = atr_percentile(df)
    vol = "expansion" if atr_pct >= EXP_PCT else "contraction" if atr_pct <= CON_PCT else "normal"
    price = float(df["Close"].iloc[-1])
    hi = float(df["High"].tail(60).max())
    lo = float(df["Low"].tail(60).min())
    pos = (price - lo) / (hi - lo) if hi > lo else 0.5
    up = float(df["Close"].iloc[-1]) >= float(df["Close"].tail(er_len).mean())
    if trend == "trend":
        phase = "markup (uptrend)" if up else "markdown (downtrend)"
    else:
        phase = ("accumulation (range low)" if pos <= 0.4 else
                 "distribution (range high)" if pos >= 0.6 else "consolidation (mid-range)")
    label = f"{trend.upper()} / {vol} ({phase})"
    return {"er": round(er, 2), "trend": trend, "atr_pct": round(atr_pct, 2),
            "vol": vol, "phase": phase, "label": label}
