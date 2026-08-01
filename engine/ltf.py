"""Lower-timeframe (1m / 5m) confirmation.

Extends the read down to the 1-minute chart so entries are timed on the
finest structure. Fetched live from yfinance; if the feed is unavailable it
fails SAFE (returns {}), and the engine simply proceeds on 15m+ — it never
crashes the signal pipeline on a lower-timeframe hiccup.
"""
from __future__ import annotations

import pandas as pd

from . import structure as st


def _fetch(interval: str, period: str):
    import yfinance as yf
    df = yf.download("GC=F", period=period, interval=interval,
                     progress=False, auto_adjust=True)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[["Open", "High", "Low", "Close", "Volume"]].astype(float)


def confirm(direction: str) -> dict:
    """Return {'5m':trend,'1m':trend,'aligned':bool,'fvg':(lo,hi)|None}.
    Empty dict on any failure (fail-safe)."""
    out: dict = {}
    try:
        specs = {"5m": ("5m", "30d"), "1m": ("1m", "5d")}
        frames = {}
        for tf, (iv, pr) in specs.items():
            d = _fetch(iv, pr)
            if d is not None and len(d) >= 60:
                frames[tf] = d
                out[tf] = str(st.structure_series(d.tail(300))["trend"].iloc[-1])
        if not out:
            return {}
        # aligned = no lower timeframe directly opposes the trade
        opp = "bear" if direction == "long" else "bull"
        out["aligned"] = all(v != opp for k, v in out.items() if k in ("5m", "1m"))
        # nearest unfilled LTF FVG in trade direction (from 5m)
        if "5m" in frames:
            kind = "bull" if direction == "long" else "bear"
            tail = frames["5m"].tail(120)
            gaps = st.unfilled_fvgs(st.find_fvgs(tail), len(tail) - 1, kind)
            if gaps:
                px = float(frames["5m"]["Close"].iloc[-1])
                g = min(gaps, key=lambda x: abs(px - x.mid))
                out["fvg"] = (round(g.bottom, 2), round(g.top, 2))
    except Exception:  # noqa: BLE001
        return {}
    return out


def line(direction: str, info: dict) -> str:
    if not info:
        return "LTF (1m/5m): unavailable — proceeding on 15m+"
    parts = []
    for tf in ("5m", "1m"):
        if tf in info:
            parts.append(f"{tf}={info[tf]}")
    flag = "aligned ✓" if info.get("aligned") else "NOT aligned ✗"
    fvg = f" · 5m FVG {info['fvg'][0]}-{info['fvg'][1]}" if info.get("fvg") else ""
    return f"LTF entry ({' '.join(parts)}): {flag}{fvg}"
