"""Market-structure primitives: swings, trend/BOS/CHoCH, FVGs, ATR,
premium/discount. All functions are lookahead-safe: a swing formed at
bar i needs K later bars to confirm, so its *effective* time is i+K.
Backtests and live scans therefore see identical information.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

SWING_K = 2  # fractal width: bar must exceed K neighbours each side


@dataclass
class Swing:
    idx: int            # bar index of the extreme
    confirmed_idx: int  # bar index when the swing became known (idx + K)
    price: float
    kind: str           # "H" or "L"
    strength: str | None = None  # "strong" | "weak" | None (set by classify_swing_strength)


def find_swings(high: np.ndarray, low: np.ndarray, k: int = SWING_K) -> list[Swing]:
    """Fractal swing highs/lows. O(n·k)."""
    swings: list[Swing] = []
    n = len(high)
    for i in range(k, n - k):
        win_h = high[i - k: i + k + 1]
        win_l = low[i - k: i + k + 1]
        if high[i] == win_h.max() and (win_h.argmax() == k):
            swings.append(Swing(i, i + k, float(high[i]), "H"))
        if low[i] == win_l.min() and (win_l.argmin() == k):
            swings.append(Swing(i, i + k, float(low[i]), "L"))
    swings.sort(key=lambda s: (s.idx, s.kind))
    return swings


@dataclass
class StructureState:
    trend: str                  # "bull" | "bear" | "range"
    last_high: float | None     # most recent confirmed swing high
    last_low: float | None      # most recent confirmed swing low
    last_event: str             # "BOS_up" | "BOS_down" | "CHoCH_up" | "CHoCH_down" | ""
    last_event_idx: int


def structure_series(df: pd.DataFrame, k: int = SWING_K) -> pd.DataFrame:
    """Walk bars in order; emit per-bar trend and structural events.

    BOS  = close breaks the last swing extreme *with* the trend.
    CHoCH = close breaks the last swing extreme *against* the trend
            (first sign of reversal).
    """
    high, low, close = df["High"].values, df["Low"].values, df["Close"].values
    n = len(df)
    swings = find_swings(high, low, k)
    by_confirm: dict[int, list[Swing]] = {}
    for s in swings:
        by_confirm.setdefault(s.confirmed_idx, []).append(s)

    trend = "range"
    last_h: float | None = None
    last_l: float | None = None
    trends = np.empty(n, dtype=object)
    events = np.empty(n, dtype=object)
    lh = np.full(n, np.nan)
    ll = np.full(n, np.nan)

    for i in range(n):
        # 1. register swings that become confirmed at this bar
        for s in by_confirm.get(i, []):
            if s.kind == "H":
                last_h = s.price
            else:
                last_l = s.price
        event = ""
        # 2. check for structural breaks on close
        if last_h is not None and close[i] > last_h:
            event = "BOS_up" if trend == "bull" else "CHoCH_up"
            trend = "bull"
            last_h = None  # consumed: wait for next swing high
        elif last_l is not None and close[i] < last_l:
            event = "BOS_down" if trend == "bear" else "CHoCH_down"
            trend = "bear"
            last_l = None
        trends[i] = trend
        events[i] = event
        lh[i] = last_h if last_h is not None else np.nan
        ll[i] = last_l if last_l is not None else np.nan

    return pd.DataFrame({"trend": trends, "event": events,
                         "swing_high": lh, "swing_low": ll}, index=df.index)


@dataclass
class FVG:
    created_idx: int
    top: float
    bottom: float
    kind: str           # "bull" | "bear"
    filled_idx: int | None = None

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2.0


def find_fvgs(df: pd.DataFrame) -> list[FVG]:
    """3-candle Fair Value Gaps.

    Bullish: low[i] > high[i-2]  → gap (high[i-2] .. low[i]).
    Bearish: high[i] < low[i-2]  → gap (high[i] .. low[i-2]).
    A gap is 'filled' once a later bar trades fully through its far edge.
    """
    high, low = df["High"].values, df["Low"].values
    out: list[FVG] = []
    for i in range(2, len(df)):
        if low[i] > high[i - 2]:
            out.append(FVG(i, float(low[i]), float(high[i - 2]), "bull"))
        elif high[i] < low[i - 2]:
            out.append(FVG(i, float(low[i - 2]), float(high[i]), "bear"))
    # mark fills
    for gap in out:
        seg_low = low[gap.created_idx + 1:]
        seg_high = high[gap.created_idx + 1:]
        if gap.kind == "bull":
            hit = np.where(seg_low <= gap.bottom)[0]
        else:
            hit = np.where(seg_high >= gap.top)[0]
        if hit.size:
            gap.filled_idx = gap.created_idx + 1 + int(hit[0])
    return out


def unfilled_fvgs(fvgs: list[FVG], at_idx: int, kind: str) -> list[FVG]:
    """FVGs of `kind` that exist and are still unfilled as of bar `at_idx`."""
    return [g for g in fvgs
            if g.kind == kind and g.created_idx <= at_idx
            and (g.filled_idx is None or g.filled_idx > at_idx)]


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def range_position(price: float, range_high: float, range_low: float) -> float:
    """0.0 = at range low (deep discount), 1.0 = at range high (premium)."""
    if range_high <= range_low:
        return 0.5
    return (price - range_low) / (range_high - range_low)


def dealing_range(df: pd.DataFrame, k: int = SWING_K,
                  lookback: int = 200) -> tuple[float, float]:
    """Most recent confirmed major swing high/low within `lookback` bars."""
    sub = df.tail(lookback)
    swings = find_swings(sub["High"].values, sub["Low"].values, k)
    highs = [s.price for s in swings if s.kind == "H"]
    lows = [s.price for s in swings if s.kind == "L"]
    hi = max(highs) if highs else float(sub["High"].max())
    lo = min(lows) if lows else float(sub["Low"].min())
    return hi, lo


def classify_swing_strength(df: pd.DataFrame, swings: list[Swing], atr_val: float,
                            reaction_bars: int = 5, reaction_mult: float = 1.5) -> list[Swing]:
    """Pragmatic proxy for the ICT "strong vs. weak" high/low concept: a
    swing is STRONG if price displaced hard AWAY from it afterward (real
    buying/selling defended the level -> less likely to be easily swept), and
    WEAK if there was no strong reaction (the level is undefended -> a
    higher-probability liquidity target/draw). Measures the size of the move
    away from the swing over the following `reaction_bars` bars, normalized
    by ATR. This is domain knowledge standard to ICT/SMC teaching, not a rule
    extracted from a specific source document — labelled as such wherever
    it's surfaced to the user."""
    from dataclasses import replace
    high, low = df["High"].values, df["Low"].values
    n = len(df)
    out = []
    for s in swings:
        start = s.confirmed_idx
        end = min(start + reaction_bars, n)
        if start >= n or end <= start or atr_val <= 0:
            out.append(s)
            continue
        if s.kind == "H":
            move = s.price - float(low[start:end].min())
        else:
            move = float(high[start:end].max()) - s.price
        strength = "strong" if move >= reaction_mult * atr_val else "weak"
        out.append(replace(s, strength=strength))
    return out


def in_killzone(ts: pd.Timestamp) -> bool:
    """London (07–10 UTC) and New York (12–15 UTC) kill zones."""
    return ts.hour in (7, 8, 9, 12, 13, 14)
