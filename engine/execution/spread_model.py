"""Day 12 — Spread Model.

Estimates the bid/ask spread a market order would realistically have
crossed, as a function of session, volatility, symbol, and news-event
proximity. This platform has no live spread feed (retail brokers rarely
expose historical spread history via API, and none is wired here) — so
this is a DISCLOSED ESTIMATION MODEL built from typical, published
retail-CFD/futures spread ranges, not a live or historical broker feed.
Every value below is labeled as an assumption in `BASE_SPREAD` and
carried through into every function's output so no caller can mistake an
estimate for an observed spread.

Session convention reused, not reinvented: `engine.ict.read()` already
buckets the trading day into London KZ (07-10 UTC) / New York KZ (12-15
UTC) / Asian (00-06 UTC) / off-session, inline in its own function body
(not exposed as an importable helper). `session_for()` below extracts the
identical hour boundaries into one place inside this package so
`spread_model.py`, `slippage_model.py`, and `latency_model.py` share one
definition instead of each re-deriving it.
"""
from __future__ import annotations

from datetime import datetime, timezone

VERSION = "1.0.0"

# --- Disclosed assumption: typical retail spread, in price units, under
# NORMAL liquidity (London/NY session, normal volatility, no news event).
# These are illustrative figures consistent with commonly published retail
# CFD/futures spread ranges for these instruments — NOT a live feed, NOT
# broker-specific, and NOT fitted to this platform's own trade history.
# An operator with real broker spread data should override these via the
# `overrides=` parameter on `estimate()` rather than editing this table,
# so the substitution is visible at the call site, not silently baked in.
BASE_SPREAD = {
    "XAUUSD": 0.35,     # USD per troy ounce
    "WTIUSD": 0.04,     # USD per barrel
    "BTCUSD": 20.0,     # USD per BTC (crypto CFD spreads vary widely by venue)
    "EURUSD": 0.00012,  # ~1.2 pips
}

SESSIONS = ["London KZ", "New York KZ", "Asian", "off-session"]

# Session liquidity multiplier: London/NY overlap sessions are the most
# liquid (tightest spreads); Asian session and off-session hours see
# materially wider spreads under normal retail-broker conditions.
SESSION_MULTIPLIER = {
    "London KZ": 1.0,
    "New York KZ": 1.0,
    "Asian": 1.5,
    "off-session": 1.8,
}

# Volatility multiplier, keyed by ATR percentile (0.0-1.0, from
# engine.regime.atr_percentile() — reused, not recomputed). Wider spreads
# are the market-maker's normal response to elevated realized volatility.
_VOL_BUCKETS = [
    (0.30, 0.90),   # calm market: spreads often tighten slightly
    (0.70, 1.00),   # normal
    (0.90, 1.35),   # elevated volatility
    (1.01, 1.90),   # extreme volatility (percentile can't exceed 1.0; this
                     # bucket is reachable only via the disclosed override path)
]

NEWS_MULTIPLIER = 2.5  # spread expansion during an active news blackout window


def session_for(now=None) -> str:
    """Same UTC hour-bucket convention as engine.ict.read()'s inline
    session calculation (London KZ 07-10, New York KZ 12-15, Asian 00-06,
    else off-session). Never raises — defaults to "off-session" on any
    malformed input."""
    try:
        now = now or datetime.now(timezone.utc)
        hour = now.hour
        if 7 <= hour < 10:
            return "London KZ"
        if 12 <= hour < 15:
            return "New York KZ"
        if 0 <= hour < 6:
            return "Asian"
        return "off-session"
    except Exception:  # noqa: BLE001
        return "off-session"


def _volatility_multiplier(atr_pct) -> float:
    """Piecewise multiplier from an ATR percentile (0.0-1.0). Returns 1.0
    (neutral) on missing/invalid input — never guesses a direction."""
    try:
        if atr_pct is None:
            return 1.0
        p = float(atr_pct)
        if p < 0:
            return 1.0
        for threshold, mult in _VOL_BUCKETS:
            if p <= threshold:
                return mult
        return _VOL_BUCKETS[-1][1]
    except Exception:  # noqa: BLE001
        return 1.0


def estimate(symbol: str, now=None, atr_pct: float | None = None,
            news_blackout: bool = False, session: str | None = None,
            overrides: dict | None = None) -> dict:
    """Estimate the spread a market order would realistically cross right
    now, for `symbol`. Never raises — degrades to the base assumption on
    any bad input. `overrides` lets a caller substitute a real
    broker-observed base spread for `BASE_SPREAD[symbol]` without editing
    this module (see module docstring)."""
    try:
        base_table = dict(BASE_SPREAD)
        if overrides:
            base_table.update(overrides)
        base = base_table.get(symbol)
        if base is None:
            return {
                "symbol": symbol, "base_spread": None, "session": session or "unknown",
                "session_multiplier": 1.0, "volatility_multiplier": 1.0,
                "news_multiplier": 1.0, "estimated_spread": None,
                "assumption": "no base-spread assumption configured for this symbol",
                "is_estimate": True, "source": "engine.execution.spread_model",
            }
        sess = session or session_for(now)
        sess_mult = SESSION_MULTIPLIER.get(sess, SESSION_MULTIPLIER["off-session"])
        vol_mult = _volatility_multiplier(atr_pct)
        news_mult = NEWS_MULTIPLIER if news_blackout else 1.0
        total_mult = sess_mult * vol_mult * news_mult
        estimated = round(base * total_mult, 8)
        return {
            "symbol": symbol,
            "base_spread": base,
            "session": sess,
            "session_multiplier": sess_mult,
            "volatility_multiplier": vol_mult,
            "news_multiplier": news_mult,
            "estimated_spread": estimated,
            "assumption": ("disclosed illustrative base spread, not a live broker feed "
                          "— see BASE_SPREAD in engine/execution/spread_model.py"),
            "is_estimate": True,
            "source": "engine.execution.spread_model",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "symbol": symbol, "base_spread": None, "session": "unknown",
            "session_multiplier": 1.0, "volatility_multiplier": 1.0,
            "news_multiplier": 1.0, "estimated_spread": None,
            "assumption": f"estimate error: {exc}", "is_estimate": True,
            "source": "engine.execution.spread_model",
        }
