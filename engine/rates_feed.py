"""Day 11 — Rates cluster: interest rates, sovereign bonds, and a market-
implied inflation-expectations proxy.

These three live in one file (rather than three) because they share the
same underlying data family — US Treasury yield/bond-ETF tickers via
yfinance — and the exact same fetch/cache/degrade infrastructure every
other macro feed in this codebase already uses (engine.risk_sentiment,
engine.spread_feed): `_series()` -> compute -> cache to one JSON file with
an `asof`/`generated` stamp -> read with a max-age check -> fail
safely to `None` on any error, never raise.

Three distinct reads:

  * `rates()` — the short-vs-long Treasury yield curve (13-week bill vs
    10-year note, a widely-watched recession-signal spread) and its trend.
    This is the "Interest Rates" provider's primary data source.
  * `bonds()` — long-duration Treasury price trend (TLT, the most liquid
    20+yr Treasury ETF) — a direct read on sovereign bond market direction
    (bond prices UP = yields DOWN = easing bias; bond prices DOWN = yields
    UP = tightening bias). This is the "Sovereign Bond Markets" provider's
    primary data source, and also one leg of the Bonds<->Risk Assets
    cross-asset relationship (paired with engine.risk_sentiment's SPX read).
  * `inflation_expectation_proxy()` — TIP (inflation-protected Treasury
    ETF) vs IEF (nominal 7-10yr Treasury ETF) RELATIVE trend. TIP
    outperforming IEF is the market pricing in HIGHER inflation
    expectations (inflation protection becoming more valuable); IEF
    outperforming TIP is the market pricing in LOWER inflation
    expectations. HONESTY DISCLOSURE: this is a market-implied proxy for
    the DIRECTION of inflation expectations, not a measurement of the CPI/
    PCE print itself — named `_proxy` deliberately, mirroring this
    codebase's `_like`-suffix convention (engine.research_stats) for
    naming something that approximates, but is not identical to, the
    thing it is standing in for. The actual last-known CPI/PCE print (a
    fact, not a market proxy) is a separate, curated field — see
    engine.macro_reference.economic_prints().

Tickers verified live via Yahoo Finance before being added here (2026-08-03,
Day 11), same verification discipline `spread_feed.py` established
(2026-07-28): ^TNX (CBOE 10-Year Treasury Note Yield Index, quoted in
yield-percent*10), ^IRX (13-Week Treasury Bill), TLT, TIP, IEF are all
real, currently-quoted tickers.
"""
from __future__ import annotations

import json
import pathlib
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "rates_cache.json"
TREND_LOOKBACK = 5  # bars (daily) to judge rising/falling/widening/narrowing


def _series(ticker, period="3mo", interval="1d"):
    import yfinance as yf
    df = yf.download(ticker, period=period, interval=interval, progress=False)
    if df is None or df.empty:
        return None
    c = df["Close"].dropna()
    if hasattr(c, "columns"):
        c = c.iloc[:, 0]
    return c


def _trend(series, up_pct=1.0, down_pct=1.0):
    """Generic rising/falling/flat trend over TREND_LOOKBACK bars. `up_pct`/
    `down_pct` are the percent-move thresholds (in percentage points of the
    series' own scale) — kept as parameters, not hardcoded twice, so
    `rates()` (yield POINTS, small numbers) and `bonds()`/inflation proxy
    (price ratios, larger numbers) can each pass a threshold appropriate to
    their own scale rather than sharing one that's wrong for one of them."""
    if series is None or len(series) < TREND_LOOKBACK + 1:
        return "flat"
    recent = float(series.iloc[-1])
    prior = float(series.iloc[-TREND_LOOKBACK - 1])
    if prior == 0:
        return "flat"
    pct_move = (recent - prior) / abs(prior) * 100.0
    if pct_move > up_pct:
        return "rising"
    if pct_move < -down_pct:
        return "falling"
    return "flat"


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _save(key: str, payload: dict) -> None:
    payload = dict(payload)
    payload["asof"] = date.today().isoformat()
    payload["generated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        cache = _load_cache()
        cache[key] = payload
        CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _read_cached(key: str, max_age_hours: int = 20):
    try:
        d = _load_cache().get(key)
        if d is None:
            return None
        gen = datetime.fromisoformat(d["generated"])
        if (datetime.now(timezone.utc) - gen).total_seconds() > max_age_hours * 3600:
            return None
        return d
    except Exception:  # noqa: BLE001
        return None


# --- Interest rates ---------------------------------------------------------

def _refresh_rates():
    ten_y = _series("^TNX")
    three_m = _series("^IRX")
    if ten_y is None or three_m is None or len(ten_y) == 0 or len(three_m) == 0:
        return None
    ten_now = float(ten_y.iloc[-1]) / 10.0    # ^TNX quotes yield*10
    short_now = float(three_m.iloc[-1]) / 10.0
    slope = round(ten_now - short_now, 3)
    slope_series = None
    if len(ten_y) == len(three_m):
        slope_series = ((ten_y - three_m) / 10.0).dropna()
    out = {
        "ten_year_yield": round(ten_now, 3), "three_month_yield": round(short_now, 3),
        "curve_slope_10y_3m": slope,
        "curve_shape": "inverted" if slope < 0 else "normal",
        "ten_year_trend": _trend(ten_y / 10.0, up_pct=1.5, down_pct=1.5),
        "slope_trend": _trend(slope_series, up_pct=3.0, down_pct=3.0) if slope_series is not None else "flat",
    }
    return out


def refresh_rates():
    try:
        out = _refresh_rates()
    except Exception:  # noqa: BLE001
        out = None
    if out is None:
        return None
    _save("rates", out)
    return out


def rates(refresh_if_missing=True, max_age_hours: int = 20):
    d = _read_cached("rates", max_age_hours)
    if d is None and refresh_if_missing:
        d = refresh_rates()
    return d


# --- Sovereign bonds (long-duration Treasury price trend, TLT) -------------

def _refresh_bonds():
    tlt = _series("TLT")
    if tlt is None or len(tlt) == 0:
        return None
    px = float(tlt.iloc[-1])
    return {
        "instrument": "TLT (20+yr Treasury ETF)", "price": round(px, 2),
        "trend": _trend(tlt, up_pct=1.0, down_pct=1.0),
        "note": "TLT price UP = long yields DOWN = easing-consistent bond-market bias; "
               "TLT price DOWN = long yields UP = tightening-consistent bond-market bias",
    }


def refresh_bonds():
    try:
        out = _refresh_bonds()
    except Exception:  # noqa: BLE001
        out = None
    if out is None:
        return None
    _save("bonds", out)
    return out


def bonds(refresh_if_missing=True, max_age_hours: int = 20):
    d = _read_cached("bonds", max_age_hours)
    if d is None and refresh_if_missing:
        d = refresh_bonds()
    return d


# --- Inflation-expectations proxy (TIP vs IEF relative trend) -------------

def _refresh_inflation_proxy():
    tip = _series("TIP")
    ief = _series("IEF")
    if tip is None or ief is None or len(tip) == 0 or len(ief) == 0:
        return None
    if len(tip) != len(ief):
        n = min(len(tip), len(ief))
        tip, ief = tip.tail(n), ief.tail(n)
    ratio = tip / ief
    ratio = ratio.dropna()
    if ratio.empty:
        return None
    trend = _trend(ratio, up_pct=0.3, down_pct=0.3)
    direction = ("rising" if trend == "rising" else
                "falling" if trend == "falling" else "flat")
    return {
        "tip_ief_ratio": round(float(ratio.iloc[-1]), 4),
        "trend": trend,
        "interpretation": (
            f"TIP/IEF {direction} -> market-implied inflation expectations "
            f"{'RISING' if direction == 'rising' else 'FALLING' if direction == 'falling' else 'roughly stable'} "
            "(proxy, not the CPI/PCE print itself)"
        ),
    }


def refresh_inflation_proxy():
    try:
        out = _refresh_inflation_proxy()
    except Exception:  # noqa: BLE001
        out = None
    if out is None:
        return None
    _save("inflation_proxy", out)
    return out


def inflation_expectation_proxy(refresh_if_missing=True, max_age_hours: int = 20):
    d = _read_cached("inflation_proxy", max_age_hours)
    if d is None and refresh_if_missing:
        d = refresh_inflation_proxy()
    return d


def note() -> str:
    r, b, i = rates(), bonds(), inflation_expectation_proxy()
    parts = []
    parts.append(f"10Y {r['ten_year_yield']}% / 3M {r['three_month_yield']}% "
                 f"(slope {r['curve_slope_10y_3m']:+.2f}, {r['curve_shape']})"
                 if r else "rates: unavailable (no network this run)")
    parts.append(f"TLT {b['price']} ({b['trend']})" if b else "bonds: unavailable")
    parts.append(i["interpretation"] if i else "inflation proxy: unavailable")
    return " | ".join(parts)


if __name__ == "__main__":
    print(note())
