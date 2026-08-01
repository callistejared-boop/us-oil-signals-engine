"""Data loading and resampling.

Historical: semicolon-separated CSV (Date;Open;High;Low;Close;Volume).
Live: TwelveData (free API key) with yfinance fallback — used on the
user's own machine where network access is unrestricted.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

# Resample rules per timeframe label
TIMEFRAMES = {
    "15m": "15min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
    "1w": "W-MON",
}

OHLC_AGG = {
    "Open": "first",
    "High": "max",
    "Low": "min",
    "Close": "last",
    "Volume": "sum",
}


def load_csv(path: str | Path) -> pd.DataFrame:
    """Load 15m OHLCV history. Auto-detects ';' or ',' separator."""
    with open(path) as f:
        sep = ";" if ";" in f.readline() else ","
    df = pd.read_csv(path, sep=sep)
    date_col = df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col], format="mixed")
    df = df.set_index(date_col).sort_index()
    df.columns = [c.strip().capitalize() for c in df.columns]
    df = df[~df.index.duplicated(keep="last")]
    return df[["Open", "High", "Low", "Close", "Volume"]].astype(float)


def resample(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Resample 15m bars up to a higher timeframe."""
    rule = TIMEFRAMES[tf]
    out = df.resample(rule, label="left", closed="left").agg(OHLC_AGG)
    return out.dropna(subset=["Open"])


def fetch_live_twelvedata(api_key: str, symbol: str = "XAU/USD",
                          interval: str = "15min", bars: int = 5000) -> pd.DataFrame:
    """Fetch recent 15m bars from TwelveData (free tier: 800 credits/day)."""
    import requests

    url = "https://api.twelvedata.com/time_series"
    params = {"symbol": symbol, "interval": interval,
              "outputsize": min(bars, 5000), "apikey": api_key,
              "order": "ASC"}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    payload = r.json()
    if "values" not in payload:
        raise RuntimeError(f"TwelveData error: {payload.get('message', payload)}")
    df = pd.DataFrame(payload["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()
    df = df.rename(columns={"open": "Open", "high": "High",
                            "low": "Low", "close": "Close"})
    for c in ("Open", "High", "Low", "Close"):
        df[c] = df[c].astype(float)
    df["Volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
    return df[["Open", "High", "Low", "Close", "Volume"]]


def fetch_live_yfinance(bars: int = 3000) -> pd.DataFrame:
    """Fallback: gold futures (GC=F) 15m bars via Yahoo Finance."""
    import yfinance as yf

    df = yf.download("GC=F", period="60d", interval="15m",
                     progress=False, auto_adjust=True)
    if df.empty:
        raise RuntimeError("yfinance returned no data for GC=F")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[["Open", "High", "Low", "Close", "Volume"]].tail(bars)


def fetch_live(settings) -> pd.DataFrame:
    """Try TwelveData first (real XAU/USD spot), fall back to yfinance."""
    key = getattr(settings, "twelvedata_api_key", "") or os.environ.get(
        "TWELVEDATA_API_KEY", "")
    if key:
        try:
            return fetch_live_twelvedata(key)
        except Exception as exc:  # noqa: BLE001
            print(f"[data] TwelveData failed ({exc}); falling back to yfinance")
    return fetch_live_yfinance()
