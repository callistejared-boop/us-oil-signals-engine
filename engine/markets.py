"""Multi-instrument support — Gold, Forex, Crypto.

The analysis engine (structure, ICT, technicals, signals) is instrument
agnostic; this module supplies per-symbol data feeds and position sizing.
Every fetch is isolated so one failing market can never break the others.

Resilience note: `fetch()` tries TwelveData then yfinance and RAISES if both
fail — that's correct for anything that can originate or size a trade
(signals.py, confluence.py): standing aside on a data outage is the safe
default, not a bug. `fetch_resilient()` wraps the same two live sources but
adds a third, local fallback — the last successfully fetched bars for that
symbol, cached to disk — so read-only/display consumers (the dashboard) can
keep showing real (if stale) numbers through an outage instead of going
blank. It never silently masks the outage: the returned DataFrame carries
`.attrs["stale"]` and `.attrs["stale_since"]` so callers can show a banner.
"""
from __future__ import annotations

import pathlib
import time

import pandas as pd

CACHE_DIR = pathlib.Path(__file__).resolve().parent.parent / ".cache"

# friendly -> yfinance ticker, TwelveData symbol, USD P/L per 1.0 lot per
# 1.0 unit of price move, display label, price decimals
MARKETS = {
    "XAUUSD": {"yf": "GC=F",     "td": "XAU/USD", "mult": 100.0,    "label": "Gold",      "dp": 2},
    "EURUSD": {"yf": "EURUSD=X", "td": "EUR/USD", "mult": 100000.0, "label": "Euro",      "dp": 5},
    "BTCUSD": {"yf": "BTC-USD",  "td": "BTC/USD", "mult": 1.0,      "label": "Bitcoin",   "dp": 1},
    "WTIUSD": {"yf": "CL=F",     "td": "WTI/USD", "mult": 100.0,    "label": "US Oil", "dp": 2},
}
DEFAULT_SYMBOLS = ["XAUUSD", "EURUSD", "BTCUSD", "WTIUSD"]


def symbols(settings) -> list:
    raw = (getattr(settings, "symbols", "") or "").upper()
    lst = [s.strip() for s in raw.split(",") if s.strip()]
    picked = [s for s in lst if s in MARKETS]
    return picked or DEFAULT_SYMBOLS


def dp(symbol: str) -> int:
    return MARKETS.get(symbol, {}).get("dp", 2)


def name(symbol: str) -> str:
    """User-facing display name for a symbol (e.g. 'US Oil'). Falls back to the
    raw key so alerts never show a blank. Change the label above to rebrand."""
    return MARKETS.get(symbol, {}).get("label", symbol)


def channel_for(symbol: str, settings) -> str:
    """The Telegram channel this symbol posts to (its own if configured,
    else the default channel)."""
    per = getattr(settings, "symbol_channels", {}) or {}
    return per.get(symbol.upper(), "") or getattr(settings, "telegram_channel", "")


def _yf(symbol: str, bars: int = 3000) -> pd.DataFrame:
    import yfinance as yf
    tk = MARKETS[symbol]["yf"]
    df = yf.download(tk, period="60d", interval="15m",
                     progress=False, auto_adjust=True)
    if df is None or df.empty:
        raise RuntimeError(f"yfinance empty for {tk}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[["Open", "High", "Low", "Close", "Volume"]].astype(float).tail(bars)


def fetch(symbol: str, settings, bars: int = 3000) -> pd.DataFrame:
    """Live 15m bars for one symbol. TwelveData (exact spot) if a key is
    set, else yfinance. Raises on failure so callers can skip that symbol."""
    symbol = symbol.upper()
    key = getattr(settings, "twelvedata_api_key", "") or ""
    if key:
        try:
            from .data_loader import fetch_live_twelvedata
            return fetch_live_twelvedata(key, symbol=MARKETS[symbol]["td"])
        except Exception:  # noqa: BLE001
            pass
    return _yf(symbol, bars)


def _cache_path(symbol: str) -> pathlib.Path:
    return CACHE_DIR / f"{symbol.upper()}.pkl"


def _cache_write(symbol: str, df: pd.DataFrame) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_pickle(_cache_path(symbol))
    except Exception:  # noqa: BLE001
        pass  # caching is best-effort — never let it break a live fetch


def _cache_read(symbol: str):
    """Returns (df, age_seconds) or (None, None) if no cache exists / unreadable."""
    p = _cache_path(symbol)
    if not p.exists():
        return None, None
    try:
        df = pd.read_pickle(p)
        age = time.time() - p.stat().st_mtime
        return df, age
    except Exception:  # noqa: BLE001
        return None, None


def fetch_resilient(symbol: str, settings, bars: int = 3000) -> pd.DataFrame:
    """Same live sources as fetch(), but degrades to the last cached snapshot
    for this symbol instead of raising when both TwelveData and yfinance are
    unreachable (proxy/outage/rate-limit). Intended for read-only display
    paths (the dashboard) — NOT for anything that originates or sizes a
    trade; those should keep calling fetch() and stand aside on failure.

    df.attrs["stale"] is False on a fresh live fetch, True when serving the
    cache. df.attrs["stale_since"] holds the cache age in seconds when stale.
    Raises only if there is neither a live source nor any cache to fall back
    to — i.e. truly nothing to show.
    """
    try:
        df = fetch(symbol, settings, bars)
        df.attrs["stale"] = False
        df.attrs["stale_since"] = 0
        _cache_write(symbol, df)
        return df
    except Exception as live_exc:  # noqa: BLE001
        cached, age = _cache_read(symbol)
        if cached is None:
            raise RuntimeError(
                f"fetch_resilient({symbol}): live fetch failed ({live_exc}) "
                f"and no cached snapshot exists"
            ) from live_exc
        cached = cached.copy()
        cached.attrs["stale"] = True
        cached.attrs["stale_since"] = round(age, 0) if age else 0
        return cached


def sizing_lines(symbol: str, entry: float, stop: float) -> list:
    dist = abs(entry - stop)
    if dist <= 0:
        return []
    mult = MARKETS.get(symbol, {}).get("mult", 100.0)
    out = [f"position sizing ({symbol}; verify contract value with your broker):",
           f"  stop distance: {dist:.{dp(symbol)}f}"]
    for acct in (1000, 5000, 10000):
        risk = acct * 0.01
        lots = risk / (dist * mult)
        out.append(f"  1% of ${acct:,} = ${risk:,.0f}  ->  ~{lots:.3f} lot")
    out.append("  (scale linearly; lot/contract sizes differ per broker)")
    return out
