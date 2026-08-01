"""Volume profile / market-profile layer — POC, Value Area High/Low.

Honesty note baked into the code, not just the docs: WTIUSD here is fed from
a CFD/spot-style feed (see engine/markets.py). Retail CFD "volume" is tick
count, not real traded volume — it's directionally useful but not the same
instrument institutions use for true auction-theory volume profile (CME
futures volume). This module uses whatever Volume column is present and
FLAGS the result as approximate (`approx=True`) whenever volume looks
degenerate (all-zero, all-equal, or missing), so nothing downstream treats a
tick-count profile as if it were verified exchange volume.

Method: bin Close prices across the lookback window, weight each bar's
volume into its price bin, find the Point of Control (highest-volume bin)
and expand outward until 70% of total volume is captured (Value Area).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _volume_is_reliable(vol: pd.Series) -> bool:
    v = vol.dropna()
    if v.empty or float(v.sum()) <= 0:
        return False
    return v.nunique() > 3   # a real feed varies; a placeholder column doesn't


def profile(df: pd.DataFrame, lookback: int = 200, bins: int = 40) -> dict:
    try:
        sub = df.tail(lookback)
        if len(sub) < 20:
            return {"poc": None, "vah": None, "val": None, "approx": True,
                    "reliable": False}
        reliable = _volume_is_reliable(sub["Volume"])
        weights = sub["Volume"].astype(float).values if reliable else \
            np.ones(len(sub))
        lo, hi = float(sub["Low"].min()), float(sub["High"].max())
        if hi <= lo:
            return {"poc": None, "vah": None, "val": None, "approx": True,
                    "reliable": reliable}
        edges = np.linspace(lo, hi, bins + 1)
        typical = ((sub["High"] + sub["Low"] + sub["Close"]) / 3.0).values
        idx = np.clip(np.digitize(typical, edges) - 1, 0, bins - 1)
        vol_by_bin = np.zeros(bins)
        for i, w in zip(idx, weights):
            vol_by_bin[i] += w
        total = vol_by_bin.sum()
        if total <= 0:
            return {"poc": None, "vah": None, "val": None, "approx": True,
                    "reliable": reliable}
        poc_i = int(np.argmax(vol_by_bin))
        centers = (edges[:-1] + edges[1:]) / 2.0
        poc = float(centers[poc_i])
        # expand value area outward from POC until >=70% of volume captured
        lo_i = hi_i = poc_i
        captured = vol_by_bin[poc_i]
        target = 0.70 * total
        while captured < target and (lo_i > 0 or hi_i < bins - 1):
            left = vol_by_bin[lo_i - 1] if lo_i > 0 else -1
            right = vol_by_bin[hi_i + 1] if hi_i < bins - 1 else -1
            if right >= left:
                hi_i += 1
                captured += vol_by_bin[hi_i]
            else:
                lo_i -= 1
                captured += vol_by_bin[lo_i]
        vah, val = float(centers[hi_i]), float(centers[lo_i])
        return {"poc": round(poc, 4), "vah": round(vah, 4), "val": round(val, 4),
                "approx": not reliable, "reliable": reliable}
    except Exception:  # noqa: BLE001
        return {"poc": None, "vah": None, "val": None, "approx": True,
                "reliable": False}


def react(price: float, prof: dict, atr_val: float) -> str:
    """Classify current price vs the value area: 'above_va' / 'in_va' /
    'below_va' / 'at_poc' — the auction-theory read (acceptance/rejection)."""
    try:
        if prof.get("vah") is None:
            return "unknown"
        if atr_val and abs(price - prof["poc"]) <= 0.15 * atr_val:
            return "at_poc"
        if price > prof["vah"]:
            return "above_va"
        if price < prof["val"]:
            return "below_va"
        return "in_va"
    except Exception:  # noqa: BLE001
        return "unknown"


def read(df: pd.DataFrame, atr_val: float = None):
    prof = profile(df)
    price = float(df["Close"].iloc[-1])
    loc = react(price, prof, atr_val or 0)
    lines = []
    if prof["poc"] is not None:
        tag = " (approx — unreliable volume feed)" if prof["approx"] else ""
        lines.append(f"POC {prof['poc']} | VAH {prof['vah']} | VAL {prof['val']}{tag}")
        lines.append(f"price vs value area: {loc.replace('_', ' ')}")
    else:
        lines.append("volume profile unavailable (insufficient data)")
    return {**prof, "location": loc, "lines": lines}
