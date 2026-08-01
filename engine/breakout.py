"""Breakout analysis — compression, session/day/week highs-lows, and the
real-breakout vs false-breakout vs liquidity-grab distinction.

Ties directly into ICT liquidity concepts: a break of a prior high/low that
immediately reverses is treated as a liquidity grab (see ict_confluence's
sweep detector for the entry-timeframe version); this module works on the
higher-level "is the level itself real support/resistance" question and
classifies today's/this-week's reaction to it.
"""
from __future__ import annotations

import pandas as pd

from .structure import atr as _atr

SQUEEZE_ATR_PCTL = 0.30   # ATR percentile below this = compression
TIGHT_RANGE_MULT = 1.5    # last N bars' range <= this x ATR = compression


def compression(df: pd.DataFrame, n: int = 12) -> dict:
    """Detect consolidation / range compression (pre-breakout coiling)."""
    try:
        a = _atr(df)
        cur_atr = float(a.iloc[-1])
        sub = df.tail(n)
        rng = float(sub["High"].max() - sub["Low"].min())
        window = a.tail(100).dropna()
        pctl = float((window <= cur_atr).mean()) if len(window) else 0.5
        is_compressed = (pctl <= SQUEEZE_ATR_PCTL) or \
            (cur_atr > 0 and rng <= TIGHT_RANGE_MULT * cur_atr)
        return {"compressed": is_compressed, "atr_pctl": round(pctl, 2),
                "range": round(rng, 4)}
    except Exception:  # noqa: BLE001
        return {"compressed": False, "atr_pctl": 0.5, "range": 0.0}


def prior_levels(df: pd.DataFrame, now: pd.Timestamp) -> dict:
    """Session/day/week high-low reference levels as of `now` (no lookahead)."""
    try:
        hist = df[df.index < now]
        if hist.empty:
            return {}
        today = now.normalize()
        day = hist[hist.index >= today]
        prior_day = hist[hist.index < today]
        week_start = now - pd.Timedelta(days=now.weekday())
        week = hist[hist.index >= week_start.normalize()]
        out = {}
        if len(prior_day):
            out["prior_day_high"] = float(prior_day["High"].max())
            out["prior_day_low"] = float(prior_day["Low"].min())
        if len(day):
            out["session_high"] = float(day["High"].max())
            out["session_low"] = float(day["Low"].min())
        if len(week):
            out["week_high"] = float(week["High"].max())
            out["week_low"] = float(week["Low"].min())
        return out
    except Exception:  # noqa: BLE001
        return {}


def classify_break(df: pd.DataFrame, level: float, direction: str,
                    lookback: int = 6) -> str:
    """After price trades through `level`, classify the reaction:
    'real'         — closed through and held (no reclaim back).
    'false'        — closed through then reclaimed back (liquidity grab).
    'untested'     — hasn't traded through the level yet.
    """
    try:
        sub = df.tail(lookback)
        broke = False
        for _, r in sub.iterrows():
            c = float(r["Close"])
            if direction == "long":
                if c > level:
                    broke = True
                elif broke and c < level:
                    return "false"
            else:
                if c < level:
                    broke = True
                elif broke and c > level:
                    return "false"
        return "real" if broke else "untested"
    except Exception:  # noqa: BLE001
        return "untested"


def read(df: pd.DataFrame, direction: str):
    now = df.index[-1]
    comp = compression(df)
    levels = prior_levels(df, now)
    key = levels.get("week_high") if direction == "long" else levels.get("week_low")
    verdict = classify_break(df, key, direction) if key is not None else "untested"
    lines = [f"compression: {'yes' if comp['compressed'] else 'no'} "
             f"(ATR percentile {comp['atr_pctl']:.0%})"]
    for k, v in levels.items():
        lines.append(f"{k.replace('_', ' ')}: {v}")
    if key is not None:
        lines.append(f"reaction to weekly {'high' if direction=='long' else 'low'} "
                     f"({key}): {verdict}")
    return {"compressed": comp["compressed"], "atr_pctl": comp["atr_pctl"],
            "levels": levels, "break_verdict": verdict, "lines": lines}
