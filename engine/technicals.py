"""Classical technical-analysis layer that complements the ICT/structure
engine. Every indicator is standard and computed lookahead-safe (uses only
closed bars). Returns numeric values plus a bull/bear vote used in the
hourly briefing.

Indicators: EMA(50/200) trend, RSI(14), MACD(12,26,9), ATR(14),
Bollinger %B(20,2), rolling VWAP(20).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .structure import atr


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    roll_up = up.ewm(alpha=1 / n, adjust=False).mean()
    roll_down = down.ewm(alpha=1 / n, adjust=False).mean()
    rs = roll_up / roll_down.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def bollinger_pctb(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.Series:
    mid = close.rolling(n).mean()
    sd = close.rolling(n).std(ddof=0)
    upper, lower = mid + k * sd, mid - k * sd
    width = (upper - lower).replace(0, np.nan)
    return ((close - lower) / width).clip(0, 1)


def rolling_vwap(df: pd.DataFrame, n: int = 20) -> pd.Series:
    tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
    pv = (tp * df["Volume"]).rolling(n).sum()
    vv = df["Volume"].rolling(n).sum().replace(0, np.nan)
    # fall back to typical-price MA if volume is missing/zero
    vwap = pv / vv
    return vwap.fillna(tp.rolling(n).mean())


@dataclass
class Technicals:
    price: float
    ema50: float
    ema200: float
    trend: str            # "bull" | "bear" | "mixed"
    rsi: float
    macd_hist: float
    macd_state: str       # "bullish" | "bearish"
    atr: float
    pct_b: float
    vwap: float
    bull_votes: int
    bear_votes: int
    lines: list = field(default_factory=list)

    @property
    def bias(self) -> str:
        if self.bull_votes - self.bear_votes >= 2:
            return "bullish"
        if self.bear_votes - self.bull_votes >= 2:
            return "bearish"
        return "neutral"


def compute(df: pd.DataFrame) -> Technicals:
    close = df["Close"]
    price = float(close.iloc[-1])
    e50 = float(ema(close, 50).iloc[-1])
    e200 = float(ema(close, 200).iloc[-1]) if len(close) >= 200 else float(ema(close, 100).iloc[-1])
    r = float(rsi(close).iloc[-1])
    _, _, hist = macd(close)
    mh = float(hist.iloc[-1])
    a = float(atr(df).iloc[-1])
    pb = float(bollinger_pctb(close).iloc[-1])
    vw = float(rolling_vwap(df).iloc[-1])

    bull = bear = 0
    lines = []

    if price > e50 > e200:
        trend, bull = "bull", bull + 1
    elif price < e50 < e200:
        trend, bear = "bear", bear + 1
    else:
        trend = "mixed"
    lines.append(f"EMA trend: {trend} (px {price:.2f} / 50 {e50:.2f} / 200 {e200:.2f})")

    if r >= 55:
        bull += 1
    elif r <= 45:
        bear += 1
    lines.append(f"RSI(14): {r:.1f} " + ("(bullish)" if r >= 55 else "(bearish)" if r <= 45 else "(neutral)"))

    if mh > 0:
        bull += 1
        macd_state = "bullish"
    else:
        bear += 1
        macd_state = "bearish"
    lines.append(f"MACD hist: {mh:+.2f} ({macd_state})")

    if price > vw:
        bull += 1
    else:
        bear += 1
    lines.append(f"VWAP(20): {vw:.2f} — price {'above' if price > vw else 'below'}")

    zone = "overbought" if pb >= 0.8 else "oversold" if pb <= 0.2 else "mid-band"
    lines.append(f"Bollinger %B: {pb:.2f} ({zone})")
    lines.append(f"ATR(14): {a:.2f}  (volatility gauge)")

    return Technicals(price, e50, e200, trend, r, mh, macd_state, a, pb, vw,
                      bull, bear, lines)
