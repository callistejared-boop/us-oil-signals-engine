"""Offline tests for engine/macro_providers.py (Day 11) — the single
abstraction layer. Every test monkeypatches the underlying feed
modules directly (never the real network) and asserts on the
STANDARDIZED shape every provider must return: facts/interpretation/
freshness/source_availability/uncertainty/source.
"""
import pathlib
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import macro_providers as mp  # noqa: E402
from engine import rates_feed as rf        # noqa: E402
from engine import macro_reference as mref  # noqa: E402
from engine import correlation as co       # noqa: E402
from engine import risk_sentiment as rs    # noqa: E402

REQUIRED_KEYS = {"provider", "symbol", "facts", "interpretation", "freshness",
                 "source_availability", "uncertainty", "source"}


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def test_freshness_from_iso_fresh_within_window():
    ts = _now_iso()
    out = mp._freshness_from_iso(ts, "rates_feed")
    assert out["state"] == "fresh"


def test_freshness_from_iso_stale_outside_window():
    ts = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat(timespec="seconds")
    out = mp._freshness_from_iso(ts, "rates_feed")
    assert out["state"] == "stale"


def test_freshness_from_iso_missing_when_none():
    out = mp._freshness_from_iso(None, "rates_feed")
    assert out["state"] == "missing"


def test_freshness_reference_not_configured():
    out = mp._freshness_reference(None, configured=False)
    assert out["state"] == "missing"


def test_freshness_reference_configured():
    out = mp._freshness_reference(_now_iso(), configured=True)
    assert out["state"] == "reference_data"


def test_freshness_computed_is_always_computed():
    out = mp._freshness_computed()
    assert out["state"] == "computed"


def test_interest_rates_shape_when_no_data(monkeypatch):
    monkeypatch.setattr(rf, "rates", lambda **kw: None)
    out = mp.interest_rates()
    assert REQUIRED_KEYS <= set(out.keys())
    assert out["provider"] == "interest_rates"
    assert out["source_availability"] == "unavailable"
    assert out["freshness"]["state"] == "missing"


def test_interest_rates_shape_when_data_present(monkeypatch):
    monkeypatch.setattr(rf, "rates", lambda **kw: {
        "ten_year_yield": 4.3, "three_month_yield": 4.9, "curve_slope_10y_3m": -0.6,
        "curve_shape": "inverted", "ten_year_trend": "falling", "slope_trend": "flat",
        "generated": _now_iso()})
    out = mp.interest_rates()
    assert out["source_availability"] == "available"
    assert out["freshness"]["state"] == "fresh"
    assert "inverted" in out["interpretation"]


def test_central_bank_policy_not_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(mref, "REFERENCE_PATH", tmp_path / "missing.json")
    out = mp.central_bank_policy()
    assert out["source_availability"] == "not_configured"
    assert out["freshness"]["state"] == "missing"


def test_central_bank_policy_configured(tmp_path, monkeypatch):
    import json
    data = {"central_banks": {"Federal Reserve": {
        "stance": "restrictive", "expected_direction": "hold", "uncertainty": "medium",
        "next_scheduled_event": "", "updated": _now_iso(), "source": "x", "example": False}}}
    f = tmp_path / "macro_reference.json"
    f.write_text(json.dumps(data))
    monkeypatch.setattr(mref, "REFERENCE_PATH", f)
    out = mp.central_bank_policy("Federal Reserve")
    assert out["source_availability"] == "available"
    assert out["freshness"]["state"] == "reference_data"


def test_energy_fundamentals_not_applicable_for_non_wti():
    out = mp.energy_fundamentals("XAUUSD")
    assert out["source_availability"] == "not_configured"
    assert "not applicable" in out["interpretation"]


def test_currency_markets_shape(monkeypatch):
    monkeypatch.setattr(co, "read_macro", lambda: {"trend": "up", "price": 105.0,
                                                    "generated": _now_iso()})
    out = mp.currency_markets()
    assert out["source_availability"] == "available"
    assert "DXY" in out["interpretation"]


def test_volatility_shape(monkeypatch):
    monkeypatch.setattr(rs, "read", lambda: {"vix": 18.0, "spx": 5000.0, "regime": "risk-on",
                                             "generated": _now_iso()})
    out = mp.volatility()
    assert out["source_availability"] == "available"
    assert out["uncertainty"] == "low"


def test_geopolitical_no_flags_no_acute_signal(tmp_path, monkeypatch):
    from engine import fundamentals_feed as ff
    monkeypatch.setattr(mref, "REFERENCE_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(ff, "load_feed", lambda symbol="WTIUSD", **kw: None)
    out = mp.geopolitical("WTIUSD")
    assert out["source_availability"] == "not_configured"
    assert out["facts"]["acute_news_signal_active"] is False


def test_geopolitical_acute_signal_active(monkeypatch):
    from engine import fundamentals_feed as ff
    monkeypatch.setattr(mref, "REFERENCE_PATH", pathlib.Path("/nonexistent/path.json"))
    monkeypatch.setattr(ff, "load_feed", lambda symbol="WTIUSD", **kw: {
        "signal": "BUY", "strength": "HIGH", "why": "supply shock headline"})
    out = mp.geopolitical("WTIUSD")
    assert out["facts"]["acute_news_signal_active"] is True
    assert out["source_availability"] == "available"


def test_get_provider_unknown_name_degrades_safely():
    out = mp.get_provider("not_a_real_provider")
    assert out["source_availability"] == "unavailable"
    assert "unknown provider" in out["interpretation"]


def test_get_provider_dispatches_correctly(monkeypatch):
    monkeypatch.setattr(rs, "read", lambda: None)
    out = mp.get_provider("volatility")
    assert out["provider"] == "volatility"


def test_get_all_returns_every_provider_with_standard_shape(monkeypatch):
    # Patch every underlying module so this stays fast/offline.
    monkeypatch.setattr(rf, "rates", lambda **kw: None)
    monkeypatch.setattr(rf, "bonds", lambda **kw: None)
    monkeypatch.setattr(rf, "inflation_expectation_proxy", lambda **kw: None)
    monkeypatch.setattr(co, "read_macro", lambda: None)
    monkeypatch.setattr(rs, "read", lambda: None)
    from engine import eia_feed as eia, spread_feed as sp, cot_feed as cot, fundamentals_feed as ff
    monkeypatch.setattr(eia, "read_cached", lambda **kw: None)
    monkeypatch.setattr(eia, "fetch", lambda **kw: None)
    monkeypatch.setattr(sp, "read", lambda symbol="WTIUSD", **kw: None)
    monkeypatch.setattr(cot, "read", lambda symbol="WTIUSD", **kw: None)
    monkeypatch.setattr(ff, "load_feed", lambda symbol="WTIUSD", **kw: None)
    monkeypatch.setattr(mref, "REFERENCE_PATH", pathlib.Path("/nonexistent/path.json"))
    monkeypatch.setattr(mp, "_traded_pair_context", lambda symbol: {})

    out = mp.get_all("WTIUSD")
    assert set(out.keys()) == set(mp.PROVIDERS)
    for name, payload in out.items():
        assert REQUIRED_KEYS <= set(payload.keys()), f"{name} missing required keys"


def test_get_all_never_raises_when_a_provider_errors(monkeypatch):
    def boom(**kw):
        raise RuntimeError("provider blew up")
    monkeypatch.setattr(rf, "rates", boom)
    out = mp.get_all("XAUUSD")
    assert out["interest_rates"]["source_availability"] == "unavailable"
    # every other provider still returned a dict, not an exception
    assert set(out.keys()) == set(mp.PROVIDERS)


def test_seasonality_wraps_engine_seasonality():
    out = mp.seasonality("WTIUSD")
    assert out["provider"] == "seasonality"
    assert out["source"] == "engine.seasonality"
    assert "lean" in out["facts"]


def test_calendar_summary_never_raises_on_fetch_failure(monkeypatch):
    from engine import macro_calendar as mcal

    def boom():
        raise RuntimeError("fetch failed")
    monkeypatch.setattr(mcal, "_fetch_raw", boom)
    out = mp.calendar_summary()
    assert out["provider"] == "economic_calendar"
    assert isinstance(out["interpretation"], str)


def test_cross_asset_shape(monkeypatch):
    from engine import macro_cross_asset as mxa
    monkeypatch.setattr(mxa, "for_symbol", lambda symbol, direction="long": {
        "gold_vs_dxy": {"relationship": "Gold <-> DXY", "supports": True, "note": "x"}})
    # _traded_pair_context does its own live correlation_dynamic lookup —
    # stub it out so this test doesn't depend on network/cache state.
    monkeypatch.setattr(mp, "_traded_pair_context", lambda symbol: {})
    out = mp.cross_asset("XAUUSD", "long")
    assert out["source_availability"] == "available"
    assert "1/1" in out["interpretation"]


def test_traded_pair_context_never_raises_on_error(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("no settings available")
    monkeypatch.setattr("engine.config.load", boom)
    assert mp._traded_pair_context("XAUUSD") == {}
