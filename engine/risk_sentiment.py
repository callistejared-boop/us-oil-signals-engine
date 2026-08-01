"""Cross-asset risk sentiment (VIX / S&P 500) — a signal source outside the
traded market entirely.

Multi-symbol (2026-07-28): the VIX/SPX regime read itself is market-wide
and symbol-agnostic, but what that regime MEANS for direction is genuinely
different per asset — this was a real gap when gold/Bitcoin were turned on
(oil's interpretation was being silently reused for both, which is wrong
for gold specifically):

  * WTIUSD (growth-linked/cyclical): normally trades WITH risk sentiment
    (risk-on -> oil up; risk-off -> oil down). EXCEPT during an active
    geopolitical/supply-shock narrative, where oil can decouple and rally
    on risk-off as a war-premium asset — handled by the existing news-based
    override below.
  * XAUUSD (safe haven): trades the OPPOSITE way from oil. Risk-off is
    normally BULLISH for gold (flight to safety), risk-on is bearish
    (capital rotates to equities). No geopolitical-decoupling override is
    needed here — risk-off already supports gold directly, it doesn't need
    an exception to stop penalizing it.
  * BTCUSD (risk asset, correlates with tech/Nasdaq since institutional
    adoption): trades WITH risk sentiment like oil's normal regime (risk-on
    -> BTC up), but for a different reason (liquidity/risk appetite, not
    growth-linked physical demand) — so it does NOT get oil's geopolitical
    supply-shock override, which is a story about physical commodity flows
    that doesn't apply to Bitcoin.

Fetched via yfinance (^VIX, ^GSPC), fail-safe throughout.
"""
from __future__ import annotations

import json
import pathlib
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "risk_sentiment_cache.json"


def _series(ticker, period="15d", interval="1d"):
    import yfinance as yf
    df = yf.download(ticker, period=period, interval=interval, progress=False)
    if df is None or df.empty:
        return None
    c = df["Close"].dropna()
    if hasattr(c, "columns"):
        c = c.iloc[:, 0]
    return c


def refresh():
    try:
        vix = _series("^VIX")
        spx = _series("^GSPC")
        if vix is None or spx is None or len(vix) < 6 or len(spx) < 6:
            return None
        vix_now, vix_prior = float(vix.iloc[-1]), float(vix.iloc[-6])
        spx_now, spx_prior = float(spx.iloc[-1]), float(spx.iloc[-6])
        vix_rising = vix_now > vix_prior * 1.03
        vix_falling = vix_now < vix_prior * 0.97
        spx_rising = spx_now > spx_prior * 1.005
        spx_falling = spx_now < spx_prior * 0.995
        if vix_falling and spx_rising:
            regime = "risk-on"
        elif vix_rising and spx_falling:
            regime = "risk-off"
        else:
            regime = "mixed"
        out = {"vix": round(vix_now, 2), "spx": round(spx_now, 2), "regime": regime,
              "asof": date.today().isoformat(),
              "generated": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        try:
            CACHE_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        return out
    except Exception:  # noqa: BLE001
        return None


def read_cached(max_age_hours: int = 20):
    try:
        d = json.loads(CACHE_PATH.read_text())
        gen = datetime.fromisoformat(d["generated"])
        if (datetime.now(timezone.utc) - gen).total_seconds() > max_age_hours * 3600:
            return None
        return d
    except Exception:  # noqa: BLE001
        return None


def read(refresh_if_missing=True):
    d = read_cached()
    if d is None and refresh_if_missing:
        d = refresh()
    return d


# Which regime is normally BULLISH for each symbol — this is the one true
# per-asset fact this module needs to get right. Unknown symbols default to
# the oil-style "risk-on" mapping (the more common case: growth-linked /
# risk-asset), which is the safer default than silently defaulting to gold's
# inverted one.
_BULLISH_REGIME = {
    "WTIUSD": "risk-on",   # growth-linked/cyclical — normally moves WITH risk sentiment
    "XAUUSD": "risk-off",  # safe haven — normally moves OPPOSITE risk sentiment
    "BTCUSD": "risk-on",   # risk asset (correlates with tech/Nasdaq) — moves WITH risk sentiment
}
# Only oil has a documented geopolitical supply-shock decoupling story (a war
# premium that can make it rally on risk-off). Gold's own inverted mapping
# already treats risk-off as supportive, so it needs no override; Bitcoin
# has no comparable physical-supply-shock narrative.
_GEOPOLITICAL_OVERRIDE_SYMBOLS = {"WTIUSD"}


def _geopolitical_override_active(symbol="WTIUSD"):
    """True if a HIGH-strength geopolitical/supply narrative is live - in
    which case risk-off should NOT count against oil longs."""
    try:
        from . import bias_adjust as ba
        v = ba.news_view(symbol)
        return bool(v and v.get("signal") == "BUY" and v.get("strength") == "HIGH")
    except Exception:  # noqa: BLE001
        return False


def alignment(direction: str, symbol="WTIUSD", d=None):
    d = d if d is not None else read()
    if not d:
        return {"supports": None, "note": "risk sentiment: no data (needs network)"}
    regime = d["regime"]
    if regime == "mixed":
        return {"supports": None, "note": "risk sentiment: mixed, no clear regime"}
    if (regime == "risk-off" and symbol in _GEOPOLITICAL_OVERRIDE_SYMBOLS
            and _geopolitical_override_active(symbol)):
        return {"supports": None,
                "note": f"risk sentiment: {regime} (VIX {d['vix']}) but geopolitical "
                        "supply-shock override active — decoupled, not penalized"}
    bullish_regime = _BULLISH_REGIME.get(symbol, "risk-on")
    up_normally = regime == bullish_regime
    supports = up_normally if direction == "long" else not up_normally
    return {"supports": supports,
            "note": f"risk sentiment: {regime} (VIX {d['vix']}, SPX {d['spx']})"}


def note(symbol: str = "WTIUSD"):
    d = read()
    if not d:
        return "Risk sentiment: unavailable (no network this run)"
    return f"Risk sentiment ({symbol}): {d['regime']} (VIX {d['vix']}, SPX {d['spx']})"


if __name__ == "__main__":
    for sym in _BULLISH_REGIME:
        print(note(sym))
