"""Offline tests for engine/rates_feed.py (Day 11). All tests avoid the
network entirely — trend classification is tested as a pure function, and
cache reads are tested via a monkeypatched CACHE_PATH (mirrors
test_extra_confluence_sources.py::test_cot_cache_migrates_old_flat_format's
established pattern), never `refresh_if_missing=True` against the real
network.
"""
import json
import pathlib
import sys
from datetime import datetime, timezone

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import rates_feed as rf  # noqa: E402


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def test_trend_rising():
    s = pd.Series([100.0] * 6 + [103.0])  # last vs 6-back: +3%
    assert rf._trend(s, up_pct=1.0, down_pct=1.0) == "rising"


def test_trend_falling():
    s = pd.Series([100.0] * 6 + [96.0])
    assert rf._trend(s, up_pct=1.0, down_pct=1.0) == "falling"


def test_trend_flat_within_threshold():
    s = pd.Series([100.0] * 6 + [100.3])
    assert rf._trend(s, up_pct=1.0, down_pct=1.0) == "flat"


def test_trend_flat_on_short_series():
    assert rf._trend(pd.Series([100.0, 101.0]), up_pct=1.0, down_pct=1.0) == "flat"


def test_trend_flat_on_none():
    assert rf._trend(None) == "flat"


def test_rates_read_from_cache(tmp_path, monkeypatch):
    cache_file = tmp_path / "rates_cache.json"
    payload = {"rates": {"ten_year_yield": 4.25, "three_month_yield": 4.9,
                         "curve_slope_10y_3m": -0.65, "curve_shape": "inverted",
                         "ten_year_trend": "falling", "slope_trend": "flat",
                         "asof": "2026-08-03", "generated": _now_iso()}}
    cache_file.write_text(json.dumps(payload))
    monkeypatch.setattr(rf, "CACHE_PATH", cache_file)
    d = rf.rates(refresh_if_missing=False)
    assert d is not None
    assert d["curve_shape"] == "inverted"
    assert d["ten_year_yield"] == 4.25


def test_rates_returns_none_when_cache_missing_and_no_refresh(tmp_path, monkeypatch):
    monkeypatch.setattr(rf, "CACHE_PATH", tmp_path / "does_not_exist.json")
    assert rf.rates(refresh_if_missing=False) is None


def test_rates_stale_cache_treated_as_missing(tmp_path, monkeypatch):
    stale_gen = "2020-01-01T00:00:00+00:00"
    payload = {"rates": {"ten_year_yield": 1.0, "three_month_yield": 1.0,
                         "curve_slope_10y_3m": 0.0, "curve_shape": "normal",
                         "ten_year_trend": "flat", "slope_trend": "flat",
                         "asof": "2020-01-01", "generated": stale_gen}}
    cache_file = tmp_path / "rates_cache.json"
    cache_file.write_text(json.dumps(payload))
    monkeypatch.setattr(rf, "CACHE_PATH", cache_file)
    assert rf.rates(refresh_if_missing=False, max_age_hours=20) is None


def test_bonds_read_from_cache(tmp_path, monkeypatch):
    cache_file = tmp_path / "rates_cache.json"
    payload = {"bonds": {"instrument": "TLT (20+yr Treasury ETF)", "price": 92.5,
                         "trend": "rising", "note": "x",
                         "asof": "2026-08-03", "generated": _now_iso()}}
    cache_file.write_text(json.dumps(payload))
    monkeypatch.setattr(rf, "CACHE_PATH", cache_file)
    d = rf.bonds(refresh_if_missing=False)
    assert d is not None and d["trend"] == "rising"


def test_inflation_proxy_read_from_cache(tmp_path, monkeypatch):
    cache_file = tmp_path / "rates_cache.json"
    payload = {"inflation_proxy": {"tip_ief_ratio": 1.05, "trend": "rising",
                                   "interpretation": "TIP/IEF rising -> inflation expectations RISING",
                                   "asof": "2026-08-03", "generated": _now_iso()}}
    cache_file.write_text(json.dumps(payload))
    monkeypatch.setattr(rf, "CACHE_PATH", cache_file)
    d = rf.inflation_expectation_proxy(refresh_if_missing=False)
    assert d is not None and d["trend"] == "rising"
    assert "RISING" in d["interpretation"]


def test_note_never_raises_when_everything_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(rf, "CACHE_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(rf, "refresh_rates", lambda: None)
    monkeypatch.setattr(rf, "refresh_bonds", lambda: None)
    monkeypatch.setattr(rf, "refresh_inflation_proxy", lambda: None)
    out = rf.note()
    assert "unavailable" in out


def test_refresh_rates_handles_fetch_exception(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("network down")
    monkeypatch.setattr(rf, "_series", boom)
    assert rf.refresh_rates() is None


def test_refresh_bonds_handles_fetch_exception(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("network down")
    monkeypatch.setattr(rf, "_series", boom)
    assert rf.refresh_bonds() is None


def test_refresh_inflation_proxy_handles_fetch_exception(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("network down")
    monkeypatch.setattr(rf, "_series", boom)
    assert rf.refresh_inflation_proxy() is None
