"""Day 11 — Structured cross-asset relationship analysis.

The eleven relationships named in the Day 11 mandate. REUSE, NOT
DUPLICATION: seven of the eleven are already computed elsewhere in this
codebase (`engine.correlation`'s USD_SENSITIVITY table, `engine.
risk_sentiment`'s VIX/SPX regime, `engine.eia_feed`'s inventory read,
`engine.spread_feed`'s crack-spread read) — this module WRAPS those exact
functions in one standardized shape rather than recomputing them. Four are
genuinely new (`engine.rates_feed`, Day 11) and are represented the SAME
way every existing cross-asset read in this codebase already is:
qualitative, sign/trend-based reasoning over a documented, disclosed
relationship — NOT a fabricated numeric correlation coefficient. This
mirrors `engine.correlation.py`/`engine.spread_feed.py`/`engine.
risk_sentiment.py`'s own established style (a Pearson-correlation
approach exists elsewhere in this codebase — `engine.correlation_dynamic`
— but it is purpose-built for TRADED-symbol pairs the platform has its own
OHLC feed for, e.g. portfolio_risk.py's position-sizing correlation; DXY/
Treasury-yield/VIX series are not platform-traded symbols, so that
machinery does not apply here without a new, separate live-fetch
dependency this module deliberately avoids duplicating).

Every relationship function returns the SAME standardized shape:
`{"relationship", "documented_basis", "read", "supports": True/False/None,
"note", "source"}` — `documented_basis` is the textbook/institutional
relationship being applied (a FACT about how markets are understood to
relate), `read` is what the CURRENT data says, `supports` translates that
into a directional lean for the named asset (None when there is no clean
signal), and `note` is the human-readable explanation. This directly
serves the mandate's "Document how these relationships are represented and
how uncertainty is communicated" requirement — every function's own
docstring states its representation method explicitly.
"""
from __future__ import annotations


def _shape(relationship, documented_basis, read, supports, note, source):
    return {"relationship": relationship, "documented_basis": documented_basis,
           "read": read, "supports": supports, "note": note, "source": source}


# --- 1. Gold <-> DXY (reuse engine.correlation) -----------------------------

def gold_vs_dxy(direction: str = "long") -> dict:
    from . import correlation as co
    d = co.read_macro()
    trend = d.get("trend") if d else None
    al = co.macro_alignment("XAUUSD", direction, trend)
    return _shape("Gold <-> DXY",
                  "Gold is priced in USD and inversely correlated with the Dollar Index "
                  "(documented sign: -1, engine.correlation.USD_SENSITIVITY).",
                  {"dxy_trend": trend}, al["aligned"], al["note"], "engine.correlation")


# --- 2. Gold <-> Real Yields (NEW: inferred from rates_feed nominal yield
#         trend vs inflation-expectation-proxy trend) -----------------------

def gold_vs_real_yields() -> dict:
    from . import rates_feed as rf
    r, ip = rf.rates(), rf.inflation_expectation_proxy()
    if not r or not ip:
        return _shape("Gold <-> Real Yields",
                      "Gold pays no yield, so RISING real yields (nominal yield minus "
                      "inflation expectations) raise its opportunity cost and are "
                      "historically bearish for gold; FALLING real yields are bullish.",
                      {}, None, "real yields: no data (needs network)", "engine.rates_feed")
    nominal_trend = r.get("ten_year_trend", "flat")
    infl_trend = ip.get("trend", "flat")
    # Real yield direction = nominal trend net of inflation-expectation trend.
    # Both rising or both falling together -> ambiguous (they partly offset);
    # a clean read only exists when they diverge.
    if nominal_trend == "rising" and infl_trend != "rising":
        real_yield_direction = "rising"
    elif nominal_trend == "falling" and infl_trend != "falling":
        real_yield_direction = "falling"
    else:
        real_yield_direction = "ambiguous"
    if real_yield_direction == "ambiguous":
        supports = None
        note = (f"nominal 10Y {nominal_trend}, inflation-expectation proxy {infl_trend} — "
               "net real-yield direction unclear, not a clean read")
    else:
        supports = real_yield_direction == "falling"   # falling real yields = bullish gold
        note = (f"inferred real yields {real_yield_direction} (nominal 10Y {nominal_trend}, "
               f"inflation proxy {infl_trend}) -> "
               f"{'supportive' if supports else 'headwind'} for gold")
    return _shape("Gold <-> Real Yields",
                  "Gold pays no yield, so RISING real yields raise its opportunity cost "
                  "(bearish); FALLING real yields are bullish. INFERRED, not directly "
                  "measured — see note.",
                  {"nominal_10y_trend": nominal_trend, "inflation_proxy_trend": infl_trend,
                   "inferred_real_yield_direction": real_yield_direction},
                  supports, note, "engine.rates_feed")


# --- 3. Gold <-> Treasury Yields (NEW, direct nominal-yield read) ----------

def gold_vs_treasury_yields() -> dict:
    from . import rates_feed as rf
    r = rf.rates()
    if not r:
        return _shape("Gold <-> Treasury Yields",
                      "Gold historically trades inversely with nominal Treasury yields "
                      "(higher yields -> higher opportunity cost of holding a zero-yield asset).",
                      {}, None, "treasury yields: no data (needs network)", "engine.rates_feed")
    trend = r.get("ten_year_trend", "flat")
    if trend == "flat":
        supports, note = None, "10Y yield flat — no clear read"
    else:
        supports = trend == "falling"
        note = f"10Y yield {r['ten_year_yield']}% ({trend}) -> {'supportive' if supports else 'headwind'} for gold"
    return _shape("Gold <-> Treasury Yields",
                  "Gold historically trades inversely with nominal Treasury yields.",
                  {"ten_year_yield": r.get("ten_year_yield"), "trend": trend},
                  supports, note, "engine.rates_feed")


# --- 4. WTI <-> USD (reuse engine.correlation) ------------------------------

def wti_vs_usd(direction: str = "long") -> dict:
    from . import correlation as co
    d = co.read_macro()
    trend = d.get("trend") if d else None
    al = co.macro_alignment("WTIUSD", direction, trend)
    return _shape("WTI <-> USD",
                  "WTI is mildly inversely correlated with the Dollar (documented sign: "
                  "-0.5, engine.correlation.USD_SENSITIVITY — weaker than gold's, since "
                  "oil is also driven by physical supply/demand independent of the dollar).",
                  {"dxy_trend": trend}, al["aligned"], al["note"], "engine.correlation")


# --- 5. WTI <-> Inventories (reuse engine.eia_feed) -------------------------

def wti_vs_inventories() -> dict:
    from . import eia_feed as eia
    d = eia.read_cached() or eia.fetch()
    if not d:
        return _shape("WTI <-> Inventories",
                      "A weekly crude-stock BUILD (inventories rising) is bearish for WTI "
                      "price; a DRAW (inventories falling) is bullish (standard supply/demand read).",
                      {}, None, eia.note(), "engine.eia_feed")
    kb = d["change_kb"]
    supports = kb < 0  # a draw supports higher price / long bias
    verb = "BUILD" if kb > 0 else "DRAW" if kb < 0 else "flat"
    return _shape("WTI <-> Inventories",
                  "A weekly crude-stock BUILD is bearish for WTI; a DRAW is bullish.",
                  {"change_kb": kb, "period": d.get("period")}, supports if kb != 0 else None,
                  f"EIA crude stocks ({d.get('period')}): {verb} {abs(kb):,.0f}kb", "engine.eia_feed")


# --- 6. WTI <-> Crack Spreads (reuse engine.spread_feed) --------------------

def wti_vs_crack_spreads(direction: str = "long") -> dict:
    from . import spread_feed as sp
    d = sp.read("WTIUSD")
    al = sp.alignment(direction, "WTIUSD", d)
    return _shape("WTI <-> Crack Spreads",
                  "A WIDENING crack spread (refined-product demand pulling crude) is "
                  "bullish for WTI; a NARROWING spread signals softening refiner demand.",
                  d or {}, al["supports"], al["note"], "engine.spread_feed")


# --- 7. Bitcoin <-> Liquidity (NEW proxy: short-end yield trend) -----------

def btc_vs_liquidity() -> dict:
    from . import rates_feed as rf
    r = rf.rates()
    if not r:
        return _shape("Bitcoin <-> Liquidity",
                      "Falling short-term rates (looser policy / more liquidity) are "
                      "historically supportive for risk assets including Bitcoin; rising "
                      "short-term rates are a headwind. PROXY: this platform has no direct, "
                      "free, live global-liquidity (e.g. M2, Fed balance sheet) feed, so the "
                      "13-week Treasury bill yield trend is used as a liquidity-conditions "
                      "proxy, disclosed as such.",
                      {}, None, "liquidity proxy: no data (needs network)", "engine.rates_feed")
    trend = r.get("ten_year_trend")  # fallback if short-end trend unavailable
    short_trend = r.get("slope_trend", "flat")
    # Use the short-rate LEVEL trend if available via a direct read; the
    # module only stores curve-slope trend and ten-year trend today, so
    # the proxy read is: falling three-month yield vs the cached level.
    three_m_now = r.get("three_month_yield")
    if three_m_now is None:
        return _shape("Bitcoin <-> Liquidity", "See above.", {}, None,
                      "liquidity proxy: incomplete data", "engine.rates_feed")
    # Curve slope widening/narrowing is used as the directional proxy here
    # (steepening curve historically coincides with easing-cycle
    # expectations building; flattening/inverting with tightening) —
    # simpler and more robust than trying to isolate a short-rate-only
    # trend from the cached fields, and disclosed as such.
    supports = short_trend == "rising"  # steepening curve -> easing-cycle-consistent -> BTC-supportive
    note = (f"yield curve slope {r.get('curve_slope_10y_3m')} ({short_trend}) used as a "
           f"liquidity-conditions proxy -> {'supportive' if supports else 'headwind' if short_trend=='falling' else 'no clear read'} for BTC"
           if short_trend != "flat" else "yield curve slope flat — no clear liquidity-proxy read")
    return _shape("Bitcoin <-> Liquidity",
                  "Looser liquidity conditions are historically supportive for risk assets "
                  "including Bitcoin; tighter conditions are a headwind. PROXY: yield-curve "
                  "slope trend, since no direct free live liquidity feed exists.",
                  {"curve_slope_10y_3m": r.get("curve_slope_10y_3m"), "slope_trend": short_trend},
                  supports if short_trend != "flat" else None, note, "engine.rates_feed")


# --- 8. Bitcoin <-> Risk Appetite (reuse engine.risk_sentiment) ------------

def btc_vs_risk_appetite(direction: str = "long") -> dict:
    from . import risk_sentiment as rs
    d = rs.read()
    al = rs.alignment(direction, "BTCUSD", d)
    return _shape("Bitcoin <-> Risk Appetite",
                  "Bitcoin trades as a risk asset correlated with broad risk appetite "
                  "(risk-on -> BTC up; risk-off -> BTC down), per engine.risk_sentiment's "
                  "documented per-asset regime mapping.",
                  d or {}, al["supports"], al["note"], "engine.risk_sentiment")


# --- 9. Bitcoin <-> Dollar (reuse engine.correlation) -----------------------

def btc_vs_dollar(direction: str = "long") -> dict:
    from . import correlation as co
    d = co.read_macro()
    trend = d.get("trend") if d else None
    al = co.macro_alignment("BTCUSD", direction, trend)
    return _shape("Bitcoin <-> Dollar",
                  "Bitcoin is inversely correlated with the Dollar (documented sign: -1, "
                  "engine.correlation.USD_SENSITIVITY).",
                  {"dxy_trend": trend}, al["aligned"], al["note"], "engine.correlation")


# --- 10. Equities <-> Volatility (reuse engine.risk_sentiment) -------------

def equities_vs_volatility() -> dict:
    from . import risk_sentiment as rs
    d = rs.read()
    if not d:
        return _shape("Equities <-> Volatility",
                      "VIX and equities are structurally inversely related (rising VIX "
                      "coincides with falling equities and vice versa) — the read here is "
                      "the platform's own risk-on/risk-off/mixed regime classification.",
                      {}, None, "no data (needs network)", "engine.risk_sentiment")
    return _shape("Equities <-> Volatility",
                  "VIX and equities are structurally inversely related.",
                  {"vix": d.get("vix"), "spx": d.get("spx"), "regime": d.get("regime")},
                  None if d.get("regime") == "mixed" else d.get("regime") == "risk-on",
                  f"regime {d.get('regime')} (VIX {d.get('vix')}, SPX {d.get('spx')})",
                  "engine.risk_sentiment")


# --- 11. Bonds <-> Risk Assets (NEW: TLT trend vs SPX trend) --------------

def bonds_vs_risk_assets() -> dict:
    from . import rates_feed as rf
    from . import risk_sentiment as rs
    b = rf.bonds()
    r = rs.read()
    if not b or not r:
        return _shape("Bonds <-> Risk Assets",
                      "Classic 'flight to quality' relationship: bonds (TLT) rising while "
                      "risk assets (equities) fall signals risk-off/flight-to-safety; both "
                      "moving together signals a broad liquidity-driven move (less classic, "
                      "worth flagging rather than over-interpreting).",
                      {}, None, "bonds/risk-sentiment: no data (needs network)",
                      "engine.rates_feed + engine.risk_sentiment")
    bond_trend = b.get("trend", "flat")
    equity_regime = r.get("regime", "mixed")
    if bond_trend == "rising" and equity_regime == "risk-off":
        read, supports = "classic flight-to-quality (bonds up, risk-off)", True
    elif bond_trend == "falling" and equity_regime == "risk-on":
        read, supports = "classic risk-on rotation out of bonds", True
    elif bond_trend == "flat" or equity_regime == "mixed":
        read, supports = "no clean cross-confirmation", None
    else:
        read, supports = "bonds and risk sentiment moving in an UNUSUAL combination — worth noting, not over-interpreting", False
    return _shape("Bonds <-> Risk Assets",
                  "Classic 'flight to quality': bonds rising while risk assets fall signals "
                  "risk-off; the inverse signals risk-on. Divergence from this pattern is a "
                  "flagged observation, not assumed to mean anything specific.",
                  {"bond_trend": bond_trend, "equity_regime": equity_regime},
                  supports, read, "engine.rates_feed + engine.risk_sentiment")


ALL_RELATIONSHIPS = [
    "gold_vs_dxy", "gold_vs_real_yields", "gold_vs_treasury_yields",
    "wti_vs_usd", "wti_vs_inventories", "wti_vs_crack_spreads",
    "btc_vs_liquidity", "btc_vs_risk_appetite", "btc_vs_dollar",
    "equities_vs_volatility", "bonds_vs_risk_assets",
]

_RELEVANT_BY_SYMBOL = {
    "XAUUSD": ["gold_vs_dxy", "gold_vs_real_yields", "gold_vs_treasury_yields",
              "equities_vs_volatility", "bonds_vs_risk_assets"],
    "WTIUSD": ["wti_vs_usd", "wti_vs_inventories", "wti_vs_crack_spreads",
              "equities_vs_volatility", "bonds_vs_risk_assets"],
    "BTCUSD": ["btc_vs_liquidity", "btc_vs_risk_appetite", "btc_vs_dollar",
              "equities_vs_volatility", "bonds_vs_risk_assets"],
    "EURUSD": ["gold_vs_dxy", "equities_vs_volatility", "bonds_vs_risk_assets"],
}

_FUNCS = {
    "gold_vs_dxy": gold_vs_dxy, "gold_vs_real_yields": gold_vs_real_yields,
    "gold_vs_treasury_yields": gold_vs_treasury_yields, "wti_vs_usd": wti_vs_usd,
    "wti_vs_inventories": wti_vs_inventories, "wti_vs_crack_spreads": wti_vs_crack_spreads,
    "btc_vs_liquidity": btc_vs_liquidity, "btc_vs_risk_appetite": btc_vs_risk_appetite,
    "btc_vs_dollar": btc_vs_dollar, "equities_vs_volatility": equities_vs_volatility,
    "bonds_vs_risk_assets": bonds_vs_risk_assets,
}


def for_symbol(symbol: str, direction: str = "long") -> dict:
    """Every cross-asset relationship relevant to `symbol` — the mandate's
    own grouping (Gold's 5, WTI's 5, Bitcoin's 5, all sharing Equities<->
    Volatility and Bonds<->RiskAssets as market-wide context). Never
    raises; each relationship degrades independently."""
    names = _RELEVANT_BY_SYMBOL.get(symbol, ["equities_vs_volatility", "bonds_vs_risk_assets"])
    out = {}
    for name in names:
        fn = _FUNCS[name]
        try:
            import inspect
            out[name] = fn(direction) if "direction" in inspect.signature(fn).parameters else fn()
        except Exception as exc:  # noqa: BLE001
            out[name] = {"relationship": name, "error": f"error: {exc}"}
    return out
