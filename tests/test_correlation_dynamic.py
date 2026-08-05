"""Offline tests for engine/correlation_dynamic.py (Day 3 Phase 4).

All tests exercise pure math and disk-cache logic only — no network calls,
so this suite runs fast and deterministically even with no internet access
(matching the pattern the rest of this test suite already uses for
engine.correlation's macro.json cache).
"""
import json
import math
import pathlib
import sys
from datetime import date, datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import correlation_dynamic as cd  # noqa: E402


def test_identity_pair_short_circuits():
    r = cd.get_correlation("XAUUSD", "XAUUSD")
    assert r["corr"] == 1.0 and r["sample"] == "trivial" and r["source"] == "identity"


def test_pearson_perfect_positive():
    a = [0.01, 0.02, -0.01, 0.03, -0.02]
    b = [x * 2 for x in a]
    assert abs(cd._pearson(a, b) - 1.0) < 1e-9


def test_pearson_perfect_negative():
    a = [0.01, 0.02, -0.01, 0.03, -0.02]
    b = [-x for x in a]
    assert abs(cd._pearson(a, b) + 1.0) < 1e-9


def test_pearson_needs_at_least_three_points():
    assert cd._pearson([0.01], [0.02]) is None
    assert cd._pearson([0.01, 0.02], [0.02, 0.01]) is None


def test_pearson_degenerate_zero_variance_returns_none():
    assert cd._pearson([0.01, 0.01, 0.01], [0.02, 0.03, 0.01]) is None


def test_log_returns_matches_hand_calc():
    closes = [100, 110, 99]
    r = cd._log_returns(closes)
    assert len(r) == 2
    assert abs(r[0] - math.log(110 / 100)) < 1e-9
    assert abs(r[1] - math.log(99 / 110)) < 1e-9


def test_log_returns_skips_non_positive():
    closes = [100, 0, 105]
    r = cd._log_returns(closes)
    assert len(r) == 0   # neither pair has two positive closes in a row


def test_static_fallback_same_sign_is_positive():
    # XAUUSD and EURUSD are both -1 in USD_SENSITIVITY -> same sign -> +0.4
    assert cd._static_fallback("XAUUSD", "EURUSD") == 0.4


def test_static_fallback_unknown_symbol_is_neutral():
    assert cd._static_fallback("XAUUSD", "NOT_A_SYMBOL") == 0.0
    assert cd._static_fallback("NOT_A_SYMBOL", "NOT_A_SYMBOL_2") == 0.0


def test_get_correlation_reads_fresh_cache(tmp_path, monkeypatch):
    payload = {
        "asof": date.today().isoformat(),
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_days": 60,
        "matrix": {"XAUUSD|BTCUSD": {"corr": 0.55, "n": 40, "sample": "ok",
                                     "method": "rolling_pearson"}},
    }
    cache_file = tmp_path / "correlation_cache.json"
    cache_file.write_text(json.dumps(payload))
    monkeypatch.setattr(cd, "CACHE_PATH", cache_file)
    r = cd.get_correlation("XAUUSD", "BTCUSD")
    assert r["corr"] == 0.55
    assert r["source"] == "cache"


def test_get_correlation_reverse_key(tmp_path, monkeypatch):
    payload = {
        "asof": date.today().isoformat(),
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_days": 60,
        "matrix": {"BTCUSD|XAUUSD": {"corr": -0.3, "n": 25, "sample": "ok",
                                     "method": "rolling_pearson"}},
    }
    cache_file = tmp_path / "correlation_cache.json"
    cache_file.write_text(json.dumps(payload))
    monkeypatch.setattr(cd, "CACHE_PATH", cache_file)
    r = cd.get_correlation("XAUUSD", "BTCUSD")
    assert r["corr"] == -0.3
    assert r["source"] == "cache"


def test_read_cache_rejects_stale_entry(tmp_path, monkeypatch):
    old = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat(timespec="seconds")
    payload = {"asof": "2020-01-01", "generated": old, "window_days": 60, "matrix": {}}
    cache_file = tmp_path / "correlation_cache.json"
    cache_file.write_text(json.dumps(payload))
    monkeypatch.setattr(cd, "CACHE_PATH", cache_file)
    assert cd.read_cache(max_age_hours=24) is None


def test_read_cache_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(cd, "CACHE_PATH", tmp_path / "does_not_exist.json")
    assert cd.read_cache() is None


def test_compute_pair_never_raises_when_data_unavailable(monkeypatch):
    # Force the live-data path to fail (simulating an outage) without ever
    # touching the network — must degrade to the static fallback, never
    # throw, since this runs directly inside the live publish path.
    from engine import markets as mk

    def _boom(symbol, settings, bars=3000):
        raise RuntimeError("simulated outage - no live source, no cache")
    monkeypatch.setattr(mk, "fetch_resilient", _boom)

    class _BadSettings:
        pass
    result = cd.compute_pair("XAUUSD", "EURUSD", _BadSettings(), window_days=60)
    assert result["method"] == "static_fallback"
    assert isinstance(result["corr"], float)


def test_line_formats_thin_sample_tag():
    out = cd.line("XAUUSD", "BTCUSD", {"corr": 0.42, "sample": "insufficient"})
    assert "thin sample" in out


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)
