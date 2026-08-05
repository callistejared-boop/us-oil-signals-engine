"""Day 11 — Macro Intelligence Engine: standardized provider layer.

THE single abstraction layer for all macro data on this platform. Every
one of the ten providers the Day 11 mandate names is a function here, and
every one returns the SAME standardized shape:

    {
      "provider": "interest_rates",     # stable machine-readable name
      "symbol": "XAUUSD" or None,       # None for market-wide providers
      "facts": {...},                   # structured data points — FACTS
      "interpretation": "...",          # human-readable reading of the facts
      "freshness": {"updated": iso|None, "age_minutes": float|None,
                    "state": "fresh"|"stale"|"reference_data"|"computed"|"missing"},
      "source_availability": "available"|"unavailable"|"not_configured",
      "uncertainty": "low"|"medium"|"high"|"unknown",
      "source": "engine.xxx",           # which underlying module this came from
    }

DOWNSTREAM RULE (Day 11, explicit): no other macro module
(`macro_regime.py`, `macro_engine.py`, or any future consumer) imports
`rates_feed`, `macro_reference`, `macro_calendar`, `risk_sentiment`,
`correlation`, `correlation_dynamic`, `spread_feed`, `seasonality`,
`cot_feed`, `eia_feed`, `fundamentals_feed`, or `macro_cross_asset`
DIRECTLY. Everything flows through the ten functions in this file. This
is the stable interface the rest of Version 2 builds against — the
underlying feed modules can change internally without any downstream
macro consumer needing to change.

REUSE, NOT DUPLICATION: every fact below is read from an EXISTING module
(seven of the eleven underlying sources predate Day 11 entirely) or from
the three small Day 11 feed modules (`rates_feed.py`, `macro_reference.py`,
`macro_calendar.py`) built specifically because no existing module covered
that data. Nothing in this file re-fetches or re-derives anything a
provider function below could instead call into.

NOT A SCORING ENGINE: every `interpretation` field is a plain-language
reading of the facts, and `uncertainty` is a disclosed qualitative tier —
never a fitted number, never a point contribution to any score. That
discipline belongs to `confluence.py`; this file explicitly does not
replicate it.
"""
from __future__ import annotations

from datetime import datetime, timezone

VERSION = "1.0.0"

PROVIDERS = [
    "interest_rates", "central_bank_policy", "inflation", "employment",
    "energy_fundamentals", "currency_markets", "sovereign_bonds",
    "volatility", "geopolitical", "cross_asset",
]

# Per-underlying-module max-age, mirrored from each module's own
# `read_cached`/`load_feed` default (not re-invented here) — used only to
# label freshness for the CALLER, never to gate or refuse a read.
_MAX_AGE_HOURS = {
    "rates_feed": 20, "risk_sentiment": 20, "spread_feed": 20,
    "correlation": 48, "cot_feed": 24 * 10, "eia_feed": 24 * 8,
    "fundamentals_feed": 24 * 3,
}


def _now():
    return datetime.now(timezone.utc)


def _freshness_from_iso(updated_iso, module: str) -> dict:
    """Standard freshness block from a `generated`/`asof`-style ISO
    timestamp already produced by the underlying module. Never raises."""
    if not updated_iso:
        return {"updated": None, "age_minutes": None, "state": "missing"}
    try:
        gen = datetime.fromisoformat(updated_iso)
        if gen.tzinfo is None:
            gen = gen.replace(tzinfo=timezone.utc)
        age_min = (_now() - gen).total_seconds() / 60.0
        max_age_h = _MAX_AGE_HOURS.get(module, 24)
        state = "fresh" if age_min <= max_age_h * 60 else "stale"
        return {"updated": updated_iso, "age_minutes": round(age_min, 1), "state": state}
    except Exception:  # noqa: BLE001
        return {"updated": updated_iso, "age_minutes": None, "state": "stale"}


def _freshness_reference(updated_iso, configured: bool) -> dict:
    """Freshness block for curated reference data (central bank stance,
    geopolitical flags, economic prints) — never "fresh"/"stale" against a
    live-fetch clock; it is either configured (state="reference_data",
    however old) or not (state="missing")."""
    if not configured:
        return {"updated": None, "age_minutes": None, "state": "missing"}
    age_min = None
    if updated_iso:
        try:
            gen = datetime.fromisoformat(updated_iso)
            if gen.tzinfo is None:
                gen = gen.replace(tzinfo=timezone.utc)
            age_min = round((_now() - gen).total_seconds() / 60.0, 1)
        except Exception:  # noqa: BLE001
            age_min = None
    return {"updated": updated_iso or None, "age_minutes": age_min, "state": "reference_data"}


def _freshness_computed() -> dict:
    """For providers that are a pure function of the current date/time
    (seasonality) or a synchronous live fetch with no separate cache clock
    (the economic calendar) — always "computed"/"fresh" as of this call,
    never stale in the sense the other states mean."""
    return {"updated": _now().isoformat(timespec="seconds"), "age_minutes": 0.0, "state": "computed"}


def _shape(provider, symbol, facts, interpretation, freshness,
          source_availability, uncertainty, source) -> dict:
    return {
        "provider": provider, "symbol": symbol, "facts": facts,
        "interpretation": interpretation, "freshness": freshness,
        "source_availability": source_availability, "uncertainty": uncertainty,
        "source": source,
    }


# --- 1. Interest Rates -------------------------------------------------------

def interest_rates() -> dict:
    """Treasury yield curve (10Y/3M) and its trend. Source: `rates_feed`."""
    try:
        from . import rates_feed as rf
        d = rf.rates()
        if not d:
            return _shape("interest_rates", None, {}, "no data (needs network)",
                          {"updated": None, "age_minutes": None, "state": "missing"},
                          "unavailable", "unknown", "engine.rates_feed")
        interp = (f"10Y {d['ten_year_yield']}% / 3M {d['three_month_yield']}% "
                 f"(curve {d['curve_shape']}, slope {d['curve_slope_10y_3m']:+.2f}, "
                 f"{d['slope_trend']})")
        uncertainty = "low" if d["ten_year_trend"] != "flat" else "medium"
        return _shape("interest_rates", None, d, interp,
                      _freshness_from_iso(d.get("generated"), "rates_feed"),
                      "available", uncertainty, "engine.rates_feed")
    except Exception as exc:  # noqa: BLE001
        return _shape("interest_rates", None, {}, f"error: {exc}",
                      {"updated": None, "age_minutes": None, "state": "missing"},
                      "unavailable", "unknown", "engine.rates_feed")


# --- 2. Central Bank Policy --------------------------------------------------

def central_bank_policy(bank: str = None) -> dict:
    """Curated policy stance for one bank (or all five if `bank` is None).
    Source: `macro_reference` (operator-curated; see that module's
    docstring for why this is not a live fetch)."""
    try:
        from . import macro_reference as mref
        if bank:
            d = mref.central_bank_stance(bank)
            stances = {bank: d}
        else:
            stances = mref.all_central_bank_stances()
        any_configured = any(v.get("configured") for v in stances.values())
        lines = [f"{b}: {v.get('stance','unknown')} (expected: {v.get('expected_direction','unknown')})"
                for b, v in stances.items()]
        interp = "; ".join(lines) if any_configured else \
            "not configured — see MACRO_ENGINE_SPECIFICATION.md Sec.4 for how an operator populates this"
        latest_update = max((v.get("updated") or "" for v in stances.values()), default="")
        return _shape("central_bank_policy", None, stances, interp,
                      _freshness_reference(latest_update or None, any_configured),
                      "available" if any_configured else "not_configured",
                      "high" if not any_configured else "medium", "engine.macro_reference")
    except Exception as exc:  # noqa: BLE001
        return _shape("central_bank_policy", None, {}, f"error: {exc}",
                      {"updated": None, "age_minutes": None, "state": "missing"},
                      "unavailable", "unknown", "engine.macro_reference")


# --- 3. Inflation -------------------------------------------------------------

def inflation() -> dict:
    """TWO evidence sources, kept explicitly distinct per Day 10's own
    lesson about not conflating different kinds of evidence: (a) a
    market-IMPLIED proxy (TIP/IEF relative trend, live, `rates_feed`) and
    (b) the curated last-known CPI print (a fact, `macro_reference`).
    Never conflates the two into one number."""
    try:
        from . import rates_feed as rf
        from . import macro_reference as mref
        proxy = rf.inflation_expectation_proxy()
        cpi = mref.economic_print("CPI")
        facts = {"market_implied_proxy": proxy, "last_cpi_print": cpi}
        parts = []
        parts.append(proxy["interpretation"] if proxy else "market-implied proxy: no data (needs network)")
        parts.append(f"last CPI print: {cpi.get('last_value')} ({cpi.get('period','')})"
                     if cpi.get("configured") else "last CPI print: not configured")
        avail = "available" if (proxy or cpi.get("configured")) else "unavailable"
        fresh = _freshness_from_iso(proxy.get("generated"), "rates_feed") if proxy else \
            {"updated": None, "age_minutes": None, "state": "missing"}
        return _shape("inflation", None, facts, " | ".join(parts), fresh, avail,
                      "medium" if proxy else "unknown", "engine.rates_feed + engine.macro_reference")
    except Exception as exc:  # noqa: BLE001
        return _shape("inflation", None, {}, f"error: {exc}",
                      {"updated": None, "age_minutes": None, "state": "missing"},
                      "unavailable", "unknown", "engine.rates_feed + engine.macro_reference")


# --- 4. Employment ------------------------------------------------------------

def employment() -> dict:
    """Employment has no clean continuous daily series (NFP is monthly,
    event-driven) — represented via (a) the curated last-known prints
    (`macro_reference`) and (b) the next scheduled employment-category
    calendar event (`macro_calendar`), NOT a fabricated numeric series."""
    try:
        from . import macro_reference as mref
        from . import macro_calendar as mcal
        nfp = mref.economic_print("NFP")
        unemp = mref.economic_print("unemployment_rate")
        nxt = mcal.next_event(category="employment")
        facts = {"last_nfp": nfp, "last_unemployment_rate": unemp, "next_event": nxt}
        parts = []
        parts.append(f"last NFP: {nfp.get('last_value')} ({nfp.get('period','')})"
                     if nfp.get("configured") else "last NFP: not configured")
        parts.append(f"next employment event: {nxt['title']} in {nxt['minutes_until']}min"
                     if nxt else "no upcoming employment event found this week")
        configured = nfp.get("configured") or unemp.get("configured")
        return _shape("employment", None, facts, " | ".join(parts),
                      _freshness_reference(nfp.get("updated"), configured),
                      "available" if (configured or nxt) else "not_configured",
                      "high", "engine.macro_reference + engine.macro_calendar")
    except Exception as exc:  # noqa: BLE001
        return _shape("employment", None, {}, f"error: {exc}",
                      {"updated": None, "age_minutes": None, "state": "missing"},
                      "unavailable", "unknown", "engine.macro_reference + engine.macro_calendar")


# --- 5. Energy Fundamentals ---------------------------------------------------

def energy_fundamentals(symbol: str = "WTIUSD") -> dict:
    """WTI-specific: EIA inventories + Brent-WTI/crack spreads + COT
    positioning + fundamentals-feed news signal, all reused directly. For
    non-WTI symbols, returns a clearly-scoped not-applicable result rather
    than forcing an oil-specific read onto gold/BTC/EUR."""
    if symbol != "WTIUSD":
        return _shape("energy_fundamentals", symbol, {},
                      f"energy fundamentals are WTI-specific; not applicable to {symbol}",
                      _freshness_computed(), "not_configured", "low", "n/a")
    try:
        from . import eia_feed as eia, spread_feed as sp, cot_feed as cot, fundamentals_feed as ff
        inv = eia.read_cached()
        spreads = sp.read("WTIUSD")
        cot_d = cot.read("WTIUSD", refresh_if_missing=False)
        news = ff.load_feed("WTIUSD")
        facts = {"inventories": inv, "spreads": spreads, "cot": cot_d,
                "news_signal": news.get("signal") if news else None}
        parts = [
            eia.note(), sp.note("WTIUSD"),
            (cot.note("WTIUSD") if cot_d else "COT: unavailable"),
        ]
        avail = "available" if any([inv, spreads, cot_d]) else "unavailable"
        fresh = (_freshness_from_iso(spreads.get("generated"), "spread_feed") if spreads
                else _freshness_from_iso(inv.get("asof") + "T00:00:00" if inv else None, "eia_feed"))
        return _shape("energy_fundamentals", "WTIUSD", facts, " | ".join(parts), fresh,
                      avail, "medium", "engine.eia_feed + engine.spread_feed + engine.cot_feed + engine.fundamentals_feed")
    except Exception as exc:  # noqa: BLE001
        return _shape("energy_fundamentals", symbol, {}, f"error: {exc}",
                      {"updated": None, "age_minutes": None, "state": "missing"},
                      "unavailable", "unknown", "engine.eia_feed")


# --- 6. Currency Markets -------------------------------------------------------

def currency_markets() -> dict:
    """DXY trend, reused from `correlation.py` (the platform's existing
    Currency-markets read, previously only exposed as a confluence-score
    input — this is the same data, standardized for the macro layer)."""
    try:
        from . import correlation as co
        d = co.read_macro()
        if not d:
            return _shape("currency_markets", None, {}, "no data (needs network)",
                          {"updated": None, "age_minutes": None, "state": "missing"},
                          "unavailable", "unknown", "engine.correlation")
        interp = f"DXY {d.get('trend')} (price {d.get('price')})"
        return _shape("currency_markets", None, d, interp,
                      _freshness_from_iso(d.get("generated"), "correlation"),
                      "available", "low" if d.get("trend") != "flat" else "medium",
                      "engine.correlation")
    except Exception as exc:  # noqa: BLE001
        return _shape("currency_markets", None, {}, f"error: {exc}",
                      {"updated": None, "age_minutes": None, "state": "missing"},
                      "unavailable", "unknown", "engine.correlation")


# --- 7. Sovereign Bond Markets -------------------------------------------------

def sovereign_bonds() -> dict:
    """Long-duration Treasury (TLT) price trend. Source: `rates_feed`."""
    try:
        from . import rates_feed as rf
        d = rf.bonds()
        if not d:
            return _shape("sovereign_bonds", None, {}, "no data (needs network)",
                          {"updated": None, "age_minutes": None, "state": "missing"},
                          "unavailable", "unknown", "engine.rates_feed")
        interp = f"{d['instrument']} {d['price']} ({d['trend']}) — {d['note']}"
        return _shape("sovereign_bonds", None, d, interp,
                      _freshness_from_iso(d.get("generated"), "rates_feed"),
                      "available", "low" if d["trend"] != "flat" else "medium", "engine.rates_feed")
    except Exception as exc:  # noqa: BLE001
        return _shape("sovereign_bonds", None, {}, f"error: {exc}",
                      {"updated": None, "age_minutes": None, "state": "missing"},
                      "unavailable", "unknown", "engine.rates_feed")


# --- 8. Volatility --------------------------------------------------------------

def volatility() -> dict:
    """VIX/SPX risk regime, reused directly from `risk_sentiment.py`."""
    try:
        from . import risk_sentiment as rs
        d = rs.read()
        if not d:
            return _shape("volatility", None, {}, "no data (needs network)",
                          {"updated": None, "age_minutes": None, "state": "missing"},
                          "unavailable", "unknown", "engine.risk_sentiment")
        interp = f"VIX {d['vix']}, SPX {d['spx']} -> {d['regime']}"
        return _shape("volatility", None, d, interp,
                      _freshness_from_iso(d.get("generated"), "risk_sentiment"),
                      "available", "low" if d["regime"] != "mixed" else "medium",
                      "engine.risk_sentiment")
    except Exception as exc:  # noqa: BLE001
        return _shape("volatility", None, {}, f"error: {exc}",
                      {"updated": None, "age_minutes": None, "state": "missing"},
                      "unavailable", "unknown", "engine.risk_sentiment")


# --- 9. Geopolitical --------------------------------------------------------------

def geopolitical(symbol: str = None) -> dict:
    """TWO evidence sources kept explicit: (a) curated structured flags
    (`macro_reference`) and (b) the existing news-based HIGH-strength
    signal already used by `risk_sentiment`'s oil-specific decoupling
    override — reused here, not recomputed, as a live "is something acute
    happening right now" proxy that complements the curated flags."""
    try:
        from . import macro_reference as mref
        from . import fundamentals_feed as ff
        flags = mref.geopolitical_flags(symbol)
        acute_symbol = symbol or "WTIUSD"
        news = ff.load_feed(acute_symbol)
        acute = bool(news and news.get("signal") in ("BUY", "SELL") and news.get("strength") == "HIGH")
        facts = {"curated_flags": flags, "acute_news_signal_active": acute,
                "acute_news_why": news.get("why") if (acute and news) else ""}
        parts = []
        if flags:
            parts.append("; ".join(f"{f.get('category')}: {f.get('summary')}" for f in flags))
        else:
            parts.append("no curated geopolitical flags configured")
        parts.append(f"acute news-based signal: {'ACTIVE' if acute else 'none'}")
        real_flags = [f for f in flags if not f.get("example")]
        return _shape("geopolitical", symbol, facts, " | ".join(parts),
                      _freshness_computed(),
                      "available" if (real_flags or acute) else "not_configured",
                      "high", "engine.macro_reference + engine.fundamentals_feed")
    except Exception as exc:  # noqa: BLE001
        return _shape("geopolitical", symbol, {}, f"error: {exc}",
                      {"updated": None, "age_minutes": None, "state": "missing"},
                      "unavailable", "unknown", "engine.macro_reference")


# --- 10. Cross-Asset Relationships ------------------------------------------------

def cross_asset(symbol: str, direction: str = "long") -> dict:
    """The eleven named cross-asset relationships, scoped to those
    relevant to `symbol` (see `macro_cross_asset.for_symbol`). Also
    surfaces the platform's own traded-symbol correlation context
    (`correlation_dynamic`) as supplementary — DIFFERENT from the
    macro-external-series relationships above (a traded-pair correlation,
    not a macro-driver relationship), disclosed as such rather than
    conflated with them."""
    try:
        from . import macro_cross_asset as mxa
        rels = mxa.for_symbol(symbol, direction)
        supplementary = _traded_pair_context(symbol)
        facts = {"relationships": rels, "traded_pair_correlation_context": supplementary}
        n_executed = sum(1 for r in rels.values() if "error" not in r)
        n_with_data = sum(1 for r in rels.values() if "error" not in r and r.get("supports") is not None)
        interp = (f"{n_executed}/{len(rels)} relationships evaluated for {symbol} "
                 f"({n_with_data} with a directional read; the rest had no data or no clean "
                 f"signal this run — see each relationship's own 'note')")
        avail = "available" if n_with_data > 0 else "unavailable"
        return _shape("cross_asset", symbol, facts, interp, _freshness_computed(),
                      avail, "medium", "engine.macro_cross_asset + engine.correlation_dynamic")
    except Exception as exc:  # noqa: BLE001
        return _shape("cross_asset", symbol, {}, f"error: {exc}",
                      {"updated": None, "age_minutes": None, "state": "missing"},
                      "unavailable", "unknown", "engine.macro_cross_asset")


def _traded_pair_context(symbol: str) -> dict:
    """Best-effort, read-only: how correlated is `symbol` with the other
    platform-traded symbols right now (engine.correlation_dynamic, Day 3).
    Never raises; returns {} if settings/data aren't available (e.g. in a
    test or offline context) rather than failing the whole provider."""
    try:
        from . import correlation_dynamic as cd, config, markets
        settings = config.load()
        others = [s for s in markets.symbols(settings) if s != symbol]
        out = {}
        for other in others:
            out[other] = cd.get_correlation(symbol, other, settings=settings)
        return out
    except Exception:  # noqa: BLE001
        return {}


# --- Orchestration helpers ----------------------------------------------------

def get_provider(name: str, symbol: str = None, direction: str = "long") -> dict:
    """Single dynamic entry point — `macro_engine.py` calls this rather
    than importing each of the ten functions above by name, so adding an
    eleventh provider later never requires a change anywhere downstream."""
    try:
        if name == "interest_rates":
            return interest_rates()
        if name == "central_bank_policy":
            return central_bank_policy()
        if name == "inflation":
            return inflation()
        if name == "employment":
            return employment()
        if name == "energy_fundamentals":
            return energy_fundamentals(symbol or "WTIUSD")
        if name == "currency_markets":
            return currency_markets()
        if name == "sovereign_bonds":
            return sovereign_bonds()
        if name == "volatility":
            return volatility()
        if name == "geopolitical":
            return geopolitical(symbol)
        if name == "cross_asset":
            return cross_asset(symbol or "XAUUSD", direction)
        return _shape(name, symbol, {}, f"unknown provider: {name}",
                      {"updated": None, "age_minutes": None, "state": "missing"},
                      "unavailable", "unknown", "n/a")
    except Exception as exc:  # noqa: BLE001
        return _shape(name, symbol, {}, f"error: {exc}",
                      {"updated": None, "age_minutes": None, "state": "missing"},
                      "unavailable", "unknown", "n/a")


def get_all(symbol: str, direction: str = "long") -> dict:
    """Every provider's read for one symbol — the single call
    `macro_engine.py`/`macro_regime.py` actually use. Each provider
    degrades independently; one failing/missing provider never prevents
    the others from being returned. Never raises."""
    out = {}
    for name in PROVIDERS:
        out[name] = get_provider(name, symbol=symbol, direction=direction)
    return out


# --- Seasonality is intentionally NOT one of the ten named providers (it's
# not in the Day 11 mandate's list) but is real, existing, reusable macro
# context — exposed here as a small supplementary function so
# macro_engine.py can include it without reaching into engine.seasonality
# directly, keeping the "everything flows through macro_providers.py" rule
# exceptionless.

def seasonality(symbol: str) -> dict:
    try:
        from . import seasonality as sea
        b = sea.bias(symbol=symbol)
        return _shape("seasonality", symbol, b,
                      f"{b['lean']}: {b['reason']}", _freshness_computed(),
                      "available", "medium" if b["lean"] != "neutral" else "low",
                      "engine.seasonality")
    except Exception as exc:  # noqa: BLE001
        return _shape("seasonality", symbol, {}, f"error: {exc}",
                      {"updated": None, "age_minutes": None, "state": "missing"},
                      "unavailable", "unknown", "engine.seasonality")


def calendar_summary() -> dict:
    """Supplementary, same reasoning as `seasonality()` above — exposes
    `macro_calendar.py` through this file rather than requiring a
    downstream import of it directly."""
    try:
        from . import macro_calendar as mcal
        s = mcal.summary()
        return _shape("economic_calendar", None, s,
                      (f"{s['n_events_this_week']} high-impact USD events this week; "
                      f"next: {s['next_event']['title']} in {s['next_event']['minutes_until']}min"
                      if s.get("next_event") else f"{s['n_events_this_week']} events this week"),
                      _freshness_computed(),
                      "available" if s.get("n_events_this_week") else "unavailable",
                      "medium", "engine.macro_calendar")
    except Exception as exc:  # noqa: BLE001
        return _shape("economic_calendar", None, {}, f"error: {exc}",
                      {"updated": None, "age_minutes": None, "state": "missing"},
                      "unavailable", "unknown", "engine.macro_calendar")
