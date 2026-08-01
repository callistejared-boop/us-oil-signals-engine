"""Single source of truth for per-symbol display strings.

Introduced 2026-07-28 during the multi-symbol (gold + Bitcoin) rollout so
dashboard_publish.py and wti_note.py stop each hand-rolling their own copy
of "what do we call this symbol / what's its basis note" — a prior version
of dashboard_publish.py had this duplicated inline, which is exactly the
kind of drift the project's "documentation over memory" principle exists
to prevent. Add a new symbol here once, both callers pick it up.
"""
from __future__ import annotations

DISPLAY_NAMES = {
    "WTIUSD": "US Oil (WTI)",
    "XAUUSD": "Gold (XAUUSD)",
    "BTCUSD": "Bitcoin (BTCUSD)",
    "EURUSD": "Euro (EURUSD)",
}

# Short label used in headers/titles ("US OIL - INSTITUTIONAL TRADE NOTE").
SHORT_LABELS = {
    "WTIUSD": "US OIL",
    "XAUUSD": "GOLD",
    "BTCUSD": "BITCOIN",
    "EURUSD": "EUR/USD",
}

# What the Telegram channel-routing status line calls this symbol's channel.
CHANNEL_LABELS = {
    "WTIUSD": "US Oil channel",
    "XAUUSD": "Gold channel",
    "BTCUSD": "Bitcoin channel",
    "EURUSD": "EUR/USD channel",
}

BASIS_NOTES = {
    "WTIUSD": "Levels are WTI futures (CL=F); broker USOIL may differ ~$0.1-0.4 (basis) — "
              "check your platform price before filling.",
    "XAUUSD": "Levels are derived from COMEX gold futures (GC=F) as a spot-price proxy; "
              "broker XAUUSD may differ slightly — check your platform price before filling.",
    "BTCUSD": "Levels are derived from BTC-USD (Yahoo Finance); should track most broker/exchange "
              "feeds closely, but confirm your platform price before filling.",
}
_DEFAULT_BASIS_NOTE = "Confirm your platform price against the source feed before filling."

# Symbol-specific "what would invalidate this read" bullets for the trade
# note's closing risk section. Deliberately short and directional, not a
# forecast — these are the known structural risks to the CURRENT bias, not
# a prediction of what will happen.
RISK_NOTES = {
    "WTIUSD": [
        "Credible US-Iran ceasefire or Hormuz reopening -> premium unwinds fast.",
        "OPEC+ output adds + inventory builds cap upside.",
        "High-impact data (EIA/API inventories, FOMC) -> engine stands aside.",
    ],
    "XAUUSD": [
        "A hawkish Fed surprise or sharply stronger USD/real yields -> premium unwinds fast.",
        "De-escalation of active geopolitical/safe-haven risk removes the bid.",
        "High-impact data (CPI, NFP, FOMC) -> engine stands aside.",
    ],
    "BTCUSD": [
        "A regulatory crackdown or major exchange/ETF outflow shock -> fast unwind.",
        "Broad risk-off in equities/Nasdaq typically drags BTC lower (correlation risk).",
        "High-impact macro data (CPI, FOMC) -> engine stands aside.",
    ],
}
_DEFAULT_RISK_NOTES = ["High-impact macro data releases -> engine stands aside.",
                       "A sharp change in the prevailing higher-timeframe trend voids this read."]


def display_name(symbol: str) -> str:
    return DISPLAY_NAMES.get(symbol, symbol)


def short_label(symbol: str) -> str:
    return SHORT_LABELS.get(symbol, symbol)


def channel_label(symbol: str) -> str:
    return CHANNEL_LABELS.get(symbol, f"{symbol} channel")


def basis_note(symbol: str) -> str:
    return BASIS_NOTES.get(symbol, _DEFAULT_BASIS_NOTE)


def risk_notes(symbol: str) -> list:
    return RISK_NOTES.get(symbol, _DEFAULT_RISK_NOTES)
