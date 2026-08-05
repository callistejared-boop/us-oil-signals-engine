"""Offline tests for engine/macro_cross_asset.py (Day 11). Every
relationship function reaches into an underlying module (engine.
correlation, engine.risk_sentiment, engine.eia_feed, engine.spread_feed,
engine.rates_feed) internally, so these tests monkeypatch each underlying
module's own read function directly — the same technique
test_extra_confluence_sources.py already uses for engine.risk_sentiment
(test_risk_sentiment_geopolitical_override_is_oil_only) — rather than
hitting the real network.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import macro_cross_asset as mxa  # noqa: E402
from engine import correlation as co          # noqa: E402
from engine import risk_sentiment as rs       # noqa: E402
from engine import eia_feed as eia            # noqa: E402
from engine import spread_feed as sp          # noqa: E402
from engine import rates_feed as rf           # noqa: E402


def test_gold_vs_dxy_reuses_correlation_macro_alignment(monkeypatch):
    monkeypatch.setattr(co, "read_macro", lambda: {"trend": "up", "price": 105.0})
    out = mxa.gold_vs_dxy("long")
    assert out["relationship"] == "Gold <-> DXY"
    assert out["supports"] is False  # DXY up -> bearish for gold long
    assert out["source"] == "engine.correlation"


def test_gold_vs_dxy_no_data(monkeypatch):
    monkeypatch.setattr(co, "read_macro", lambda: None)
    out = mxa.gold_vs_dxy("long")
    assert out["supports"] is None


def test_wti_vs_usd_uses_wti_sensitivity(monkeypatch):
    monkeypatch.setattr(co, "read_macro", lambda: {"trend": "down", "price": 95.0})
    out = mxa.wti_vs_usd("long")
    assert out["relationship"] == "WTI <-> USD"
    assert out["supports"] is True  # DXY down -> supportive for WTI long


def test_btc_vs_dollar(monkeypatch):
    monkeypatch.setattr(co, "read_macro", lambda: {"trend": "down", "price": 95.0})
    out = mxa.btc_vs_dollar("long")
    assert out["supports"] is True


def test_gold_vs_real_yields_no_data(monkeypatch):
    monkeypatch.setattr(rf, "rates", lambda **kw: None)
    monkeypatch.setattr(rf, "inflation_expectation_proxy", lambda **kw: None)
    out = mxa.gold_vs_real_yields()
    assert out["relationship"] == "Gold <-> Real Yields"
    assert out["supports"] is None


def test_gold_vs_real_yields_rising_nominal_stable_inflation(monkeypatch):
    monkeypatch.setattr(rf, "rates", lambda **kw: {"ten_year_trend": "rising", "ten_year_yield": 4.5})
    monkeypatch.setattr(rf, "inflation_expectation_proxy", lambda **kw: {"trend": "flat"})
    out = mxa.gold_vs_real_yields()
    assert out["read"]["inferred_real_yield_direction"] == "rising"
    assert out["supports"] is False  # rising real yields -> headwind for gold


def test_gold_vs_real_yields_ambiguous_when_both_rise(monkeypatch):
    monkeypatch.setattr(rf, "rates", lambda **kw: {"ten_year_trend": "rising", "ten_year_yield": 4.5})
    monkeypatch.setattr(rf, "inflation_expectation_proxy", lambda **kw: {"trend": "rising"})
    out = mxa.gold_vs_real_yields()
    assert out["supports"] is None
    assert out["read"]["inferred_real_yield_direction"] == "ambiguous"


def test_gold_vs_treasury_yields_falling_supports_gold(monkeypatch):
    monkeypatch.setattr(rf, "rates", lambda **kw: {"ten_year_trend": "falling", "ten_year_yield": 3.8})
    out = mxa.gold_vs_treasury_yields()
    assert out["supports"] is True


def test_wti_vs_inventories_draw_is_bullish(monkeypatch):
    monkeypatch.setattr(eia, "read_cached", lambda **kw: {"change_kb": -3000, "period": "2026-07-29"})
    out = mxa.wti_vs_inventories()
    assert out["supports"] is True


def test_wti_vs_inventories_build_is_bearish(monkeypatch):
    monkeypatch.setattr(eia, "read_cached", lambda **kw: {"change_kb": 2500, "period": "2026-07-29"})
    out = mxa.wti_vs_inventories()
    assert out["supports"] is False


def test_wti_vs_crack_spreads_reuses_spread_feed(monkeypatch):
    d = {"brent_wti_trend": "narrowing", "crack_trend": "widening"}
    monkeypatch.setattr(sp, "read", lambda symbol="WTIUSD": d)
    out = mxa.wti_vs_crack_spreads("long")
    assert out["supports"] is True  # both votes bullish


def test_btc_vs_liquidity_no_data(monkeypatch):
    monkeypatch.setattr(rf, "rates", lambda **kw: None)
    out = mxa.btc_vs_liquidity()
    assert out["relationship"] == "Bitcoin <-> Liquidity"
    assert out["supports"] is None


def test_btc_vs_liquidity_steepening_curve_supports_btc(monkeypatch):
    monkeypatch.setattr(rf, "rates", lambda **kw: {
        "three_month_yield": 4.0, "curve_slope_10y_3m": 0.5, "slope_trend": "rising"})
    out = mxa.btc_vs_liquidity()
    assert out["supports"] is True


def test_btc_vs_risk_appetite_reuses_risk_sentiment(monkeypatch):
    monkeypatch.setattr(rs, "read", lambda: {"regime": "risk-on", "vix": 12.0, "spx": 5000.0})
    out = mxa.btc_vs_risk_appetite("long")
    assert out["supports"] is True


def test_equities_vs_volatility_risk_off(monkeypatch):
    monkeypatch.setattr(rs, "read", lambda: {"regime": "risk-off", "vix": 30.0, "spx": 4800.0})
    out = mxa.equities_vs_volatility()
    assert out["supports"] is False


def test_equities_vs_volatility_mixed_is_none(monkeypatch):
    monkeypatch.setattr(rs, "read", lambda: {"regime": "mixed", "vix": 18.0, "spx": 4900.0})
    out = mxa.equities_vs_volatility()
    assert out["supports"] is None


def test_bonds_vs_risk_assets_classic_flight_to_quality(monkeypatch):
    monkeypatch.setattr(rf, "bonds", lambda **kw: {"trend": "rising"})
    monkeypatch.setattr(rs, "read", lambda: {"regime": "risk-off"})
    out = mxa.bonds_vs_risk_assets()
    assert out["supports"] is True
    assert "flight-to-quality" in out["note"]


def test_bonds_vs_risk_assets_unusual_combination_flagged(monkeypatch):
    monkeypatch.setattr(rf, "bonds", lambda **kw: {"trend": "rising"})
    monkeypatch.setattr(rs, "read", lambda: {"regime": "risk-on"})
    out = mxa.bonds_vs_risk_assets()
    assert out["supports"] is False
    assert "UNUSUAL" in out["note"]


def _patch_all_underlying_to_none(monkeypatch):
    monkeypatch.setattr(co, "read_macro", lambda: None)
    monkeypatch.setattr(rs, "read", lambda: None)
    monkeypatch.setattr(eia, "read_cached", lambda **kw: None)
    monkeypatch.setattr(eia, "fetch", lambda **kw: None)
    monkeypatch.setattr(sp, "read", lambda symbol="WTIUSD", **kw: None)
    monkeypatch.setattr(rf, "rates", lambda **kw: None)
    monkeypatch.setattr(rf, "bonds", lambda **kw: None)
    monkeypatch.setattr(rf, "inflation_expectation_proxy", lambda **kw: None)


def test_for_symbol_returns_relevant_relationships_only(monkeypatch):
    _patch_all_underlying_to_none(monkeypatch)
    names = set(mxa._RELEVANT_BY_SYMBOL["XAUUSD"])
    out = mxa.for_symbol("XAUUSD")
    assert set(out.keys()) == names


def test_for_symbol_never_raises_on_underlying_error(monkeypatch):
    _patch_all_underlying_to_none(monkeypatch)

    def boom():
        raise RuntimeError("boom")
    monkeypatch.setattr(rs, "read", boom)
    out = mxa.for_symbol("BTCUSD")
    assert "btc_vs_risk_appetite" in out
    assert "error" in out["btc_vs_risk_appetite"]


def test_all_relationships_have_documented_basis_and_source(monkeypatch):
    """Every relationship function's own output must disclose its
    representation method and source — the mandate's explicit
    'document how these relationships are represented' requirement.
    All underlying reads monkeypatched to None/empty so this stays
    offline and fast regardless of which relationships have live data."""
    monkeypatch.setattr(co, "read_macro", lambda: None)
    monkeypatch.setattr(rs, "read", lambda: None)
    monkeypatch.setattr(eia, "read_cached", lambda **kw: None)
    monkeypatch.setattr(eia, "fetch", lambda **kw: None)
    monkeypatch.setattr(sp, "read", lambda symbol="WTIUSD", **kw: None)
    monkeypatch.setattr(rf, "rates", lambda **kw: None)
    monkeypatch.setattr(rf, "bonds", lambda **kw: None)
    monkeypatch.setattr(rf, "inflation_expectation_proxy", lambda **kw: None)
    for name in mxa.ALL_RELATIONSHIPS:
        fn = mxa._FUNCS[name]
        import inspect
        out = fn("long") if "direction" in inspect.signature(fn).parameters else fn()
        assert out.get("documented_basis")
        assert out.get("source")
