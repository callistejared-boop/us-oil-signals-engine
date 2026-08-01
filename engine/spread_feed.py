"""Cross-instrument spread/basis layer — asset-appropriate leading
indicators that aren't visible in price action alone.

Multi-symbol (2026-07-28): this used to be Brent-WTI/crack only (oil is the
one instrument these two specific spreads apply to), and every symbol was
silently being scored against oil's spread data via a confluence.py bug
(fixed alongside this). These are NOT drop-in reuses of the same math —
each asset gets a genuinely different, asset-appropriate substitute:

  * WTIUSD - Brent-WTI spread (regional imbalance) + RBOB crack spread
    (refiner demand pull), as before.
  * XAUUSD - gold/silver ratio (GC=F / SI=F). A RISING ratio means gold is
    outperforming silver - read as safe-haven/defensive demand specific to
    gold rather than broad precious-metals or industrial-metal strength
    (silver has meaningful industrial demand, gold doesn't). A FALLING
    ratio means silver catching up / broad precious-metals or industrial
    risk-on strength - a headwind for a gold-specific long thesis. This is
    a standard, widely-watched institutional ratio, not an invented metric.
  * BTCUSD - CME Bitcoin futures basis (BTC=F front-month minus BTC-USD
    spot). A WIDENING basis (futures trading at a premium to spot, i.e.
    contango) signals bullish positioning / demand to be long via futures;
    a NARROWING or negative basis (backwardation) signals bearish
    positioning or stress. Standard futures-basis read, same shape as the
    Brent-WTI spread just applied to BTC's own futures/spot pair.

Tickers verified live via Yahoo Finance before being added here (2026-07-28):
GC=F, SI=F, BTC=F, BTC-USD are all real, currently-quoted tickers.

Fetched via yfinance, fail-safe throughout: any fetch/format issue -> None,
degrades cleanly. Cached per-symbol in one JSON file (mirrors
engine/cot_feed.py's pattern) so a bad run for one symbol never blanks out
another's cached read.
"""
from __future__ import annotations

import json
import pathlib
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "spread_cache.json"
TREND_LOOKBACK = 5   # bars (daily) to judge widening/narrowing

_LABELS = {
    "WTIUSD": "Brent-WTI/crack spreads",
    "XAUUSD": "gold/silver ratio",
    "BTCUSD": "BTC futures basis",
}


def label(symbol: str = "WTIUSD") -> str:
    return _LABELS.get(symbol, "cross-instrument spread")


def _series(ticker, period="30d", interval="1d"):
    import yfinance as yf
    df = yf.download(ticker, period=period, interval=interval, progress=False)
    if df is None or df.empty:
        return None
    c = df["Close"].dropna()
    if hasattr(c, "columns"):
        c = c.iloc[:, 0]
    return c


def _trend(series):
    if series is None or len(series) < TREND_LOOKBACK + 1:
        return "flat"
    recent = float(series.iloc[-1])
    prior = float(series.iloc[-TREND_LOOKBACK - 1])
    if recent > prior * 1.01:
        return "widening"
    if recent < prior * 0.99:
        return "narrowing"
    return "flat"


def _refresh_wti():
    wti = _series("CL=F")
    brent = _series("BZ=F")
    rbob = _series("RB=F")
    if wti is None or brent is None:
        return None
    wti_px, brent_px = float(wti.iloc[-1]), float(brent.iloc[-1])
    bw_spread = brent_px - wti_px
    bw_series = (brent - wti).dropna() if len(brent) == len(wti) else None
    out = {
        "symbol": "WTIUSD",
        "wti": round(wti_px, 2), "brent": round(brent_px, 2),
        "brent_wti_spread": round(bw_spread, 2),
        "brent_wti_trend": _trend(bw_series) if bw_series is not None else "flat",
    }
    if rbob is not None and len(rbob) > 0:
        rbob_px = float(rbob.iloc[-1])
        crack = rbob_px * 42.0 - wti_px   # $/gal -> $/bbl (42 gal/bbl)
        crack_series = None
        if len(rbob) == len(wti):
            crack_series = (rbob * 42.0 - wti).dropna()
        out.update({"rbob": round(rbob_px, 3), "crack_spread": round(crack, 2),
                   "crack_trend": _trend(crack_series) if crack_series is not None
                                 else "flat"})
    return out


def _refresh_gold():
    gold = _series("GC=F")
    silver = _series("SI=F")
    if gold is None or silver is None or len(silver) == 0:
        return None
    gold_px, silver_px = float(gold.iloc[-1]), float(silver.iloc[-1])
    if silver_px == 0:
        return None
    ratio = gold_px / silver_px
    ratio_series = (gold / silver).dropna() if len(gold) == len(silver) else None
    return {
        "symbol": "XAUUSD",
        "gold": round(gold_px, 2), "silver": round(silver_px, 3),
        "gold_silver_ratio": round(ratio, 2),
        "ratio_trend": _trend(ratio_series) if ratio_series is not None else "flat",
    }


def _refresh_btc():
    fut = _series("BTC=F")
    spot = _series("BTC-USD")
    if fut is None or spot is None or len(spot) == 0:
        return None
    fut_px, spot_px = float(fut.iloc[-1]), float(spot.iloc[-1])
    basis = fut_px - spot_px
    basis_series = (fut - spot).dropna() if len(fut) == len(spot) else None
    return {
        "symbol": "BTCUSD",
        "btc_future": round(fut_px, 2), "btc_spot": round(spot_px, 2),
        "btc_basis": round(basis, 2),
        "basis_trend": _trend(basis_series) if basis_series is not None else "flat",
    }


_REFRESHERS = {"WTIUSD": _refresh_wti, "XAUUSD": _refresh_gold, "BTCUSD": _refresh_btc}


def _load_cache() -> dict:
    try:
        data = json.loads(CACHE_PATH.read_text())
    except Exception:  # noqa: BLE001
        return {}
    # Migrate the old single-symbol flat format into the new per-symbol one.
    if "wti" in data and "symbol" not in data:
        return {"WTIUSD": {**data, "symbol": "WTIUSD"}}
    return data


def refresh(symbol: str = "WTIUSD"):
    fn = _REFRESHERS.get(symbol)
    if fn is None:
        return None
    try:
        out = fn()
    except Exception:  # noqa: BLE001
        return None
    if out is None:
        return None
    out["asof"] = date.today().isoformat()
    out["generated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        cache = _load_cache()
        cache[symbol] = out
        CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return out


def read_cached(symbol: str = "WTIUSD", max_age_hours: int = 20):
    try:
        cache = _load_cache()
        d = cache.get(symbol)
        if d is None:
            return None
        gen = datetime.fromisoformat(d["generated"])
        if (datetime.now(timezone.utc) - gen).total_seconds() > max_age_hours * 3600:
            return None
        return d
    except Exception:  # noqa: BLE001
        return None


def read(symbol: str = "WTIUSD", refresh_if_missing=True):
    d = read_cached(symbol)
    if d is None and refresh_if_missing:
        d = refresh(symbol)
    return d


def _alignment_wti(direction, d):
    notes, votes = [], 0
    bw_trend = d.get("brent_wti_trend", "flat")
    if bw_trend == "widening":
        votes -= 1
        notes.append("Brent-WTI premium widening (WTI-specific weakness)")
    elif bw_trend == "narrowing":
        votes += 1
        notes.append("Brent-WTI spread narrowing (WTI relative strength)")
    if "crack_trend" in d:
        ck_trend = d["crack_trend"]
        if ck_trend == "widening":
            votes += 1
            notes.append("crack spread widening (refined-product demand pulling crude)")
        elif ck_trend == "narrowing":
            votes -= 1
            notes.append("crack spread narrowing (refiner demand softening)")
    if votes == 0:
        return {"supports": None, "note": "spreads: " + ("; ".join(notes) or "flat/no clear read")}
    bullish = votes > 0
    return {"supports": bullish if direction == "long" else not bullish,
            "note": "spreads: " + "; ".join(notes)}


def _alignment_gold(direction, d):
    trend = d.get("ratio_trend", "flat")
    if trend == "flat":
        return {"supports": None, "note": "gold/silver ratio: flat, no clear read"}
    # rising ratio = gold-specific strength (defensive demand); falling = broad
    # precious-metals/industrial risk-on strength, a headwind for gold-only longs
    bullish_for_gold = trend == "widening"
    return {"supports": bullish_for_gold if direction == "long" else not bullish_for_gold,
            "note": f"gold/silver ratio {d.get('gold_silver_ratio', '?')} ({trend})"}


def _alignment_btc(direction, d):
    trend = d.get("basis_trend", "flat")
    if trend == "flat":
        return {"supports": None, "note": "BTC futures basis: flat, no clear read"}
    bullish_for_btc = trend == "widening"   # widening premium = bullish futures positioning
    return {"supports": bullish_for_btc if direction == "long" else not bullish_for_btc,
            "note": f"BTC futures basis {d.get('btc_basis', '?'):+.2f} ({trend})"}


_ALIGNERS = {"WTIUSD": _alignment_wti, "XAUUSD": _alignment_gold, "BTCUSD": _alignment_btc}


def alignment(direction: str, symbol: str = "WTIUSD", d=None):
    """Do the spreads/basis support or warn against `direction`? Soft signal
    only — returns {supports: True/False/None, note}."""
    d = d if d is not None else read(symbol)
    if not d:
        return {"supports": None, "note": f"{label(symbol)}: no data (needs network)"}
    fn = _ALIGNERS.get(symbol)
    if fn is None:
        return {"supports": None, "note": f"{label(symbol)}: symbol not supported"}
    return fn(direction, d)


def note(symbol: str = "WTIUSD"):
    d = read(symbol)
    if not d:
        return f"{label(symbol)}: unavailable (no network this run)"
    if symbol == "WTIUSD":
        L = [f"Brent {d['brent']} vs WTI {d['wti']} (spread {d['brent_wti_spread']:+.2f}, "
            f"{d['brent_wti_trend']})"]
        if "crack_spread" in d:
            L.append(f"crack spread ~${d['crack_spread']:.2f}/bbl ({d['crack_trend']})")
        return " | ".join(L)
    if symbol == "XAUUSD":
        return (f"Gold/silver ratio {d['gold_silver_ratio']} (gold {d['gold']}, "
               f"silver {d['silver']}, {d['ratio_trend']})")
    if symbol == "BTCUSD":
        return (f"BTC futures basis {d['btc_basis']:+.2f} (future {d['btc_future']}, "
               f"spot {d['btc_spot']}, {d['basis_trend']})")
    return f"{label(symbol)}: unsupported symbol"


if __name__ == "__main__":
    for sym in _REFRESHERS:
        print(note(sym))
