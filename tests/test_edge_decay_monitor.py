"""Offline tests for engine/edge_decay_monitor.py (Day 9). All tests pass
an explicit `rows=` list so nothing touches the real trades.json.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import edge_decay_monitor as edm  # noqa: E402


def _mk(i, r, symbol="XAUUSD"):
    return {"opened": f"2026-01-{1 + i // 1000:02d} {i//60 % 24:02d}:{i%60:02d}:00",
           "status": "win" if r > 0 else "loss" if r < 0 else "scratch",
           "result_r": r, "symbol": symbol}


def test_recent_vs_prior_insufficient_data():
    out = edm.recent_vs_prior(rows=[_mk(i, 1.0) for i in range(10)])
    assert out["sufficient"] is False


def test_recent_vs_prior_sufficient_when_enough_trades():
    rows = [_mk(i, 1.0 if i % 2 == 0 else -1.0) for i in range(70)]
    out = edm.recent_vs_prior(rows=rows, recent_n=30)
    assert out["sufficient"] is True
    assert out["recent_n"] == 30
    assert out["prior_n"] == 40


def test_check_flags_declining_expectancy():
    # prior 40 trades all winners (+1R), recent 30 trades mostly losers
    prior = [_mk(i, 1.0) for i in range(40)]
    recent = [_mk(40 + i, 1.0 if i % 5 == 0 else -1.0) for i in range(30)]
    out = edm.check(rows=prior + recent)
    types = [f["type"] for f in out["flags"]]
    assert "declining_expectancy" in types
    for f in out["flags"]:
        assert "do not change production" in f["recommendation"]


def test_check_no_flags_when_stable():
    rows = [_mk(i, 1.0 if i % 2 == 0 else -1.0) for i in range(70)]
    out = edm.check(rows=rows)
    # stable alternating win/loss across the whole series -> no decline flags
    assert out["n_flags"] == 0 or all(f["type"] != "declining_expectancy" for f in out["flags"])


def test_check_never_raises_on_garbage():
    out = edm.check(rows="not-a-list")
    assert isinstance(out, dict)
    assert "flags" in out


def test_check_never_raises_on_empty():
    out = edm.check(rows=[])
    assert out["comparison"]["sufficient"] is False
    assert out["flags"] == []


def test_check_includes_regime_conditioned_pointer_not_duplicate():
    """Per the mandate's 'changing market regimes' item — the monitor
    points to market_memory's existing regime-conditioned analytics rather
    than reimplementing them."""
    out = edm.check(rows=[])
    assert "market_memory" in out["note"]


def test_flags_are_descriptive_never_prescriptive_of_a_production_change():
    prior = [_mk(i, 2.0) for i in range(40)]
    recent = [_mk(40 + i, -1.0) for i in range(30)]
    out = edm.check(rows=prior + recent)
    assert out["n_flags"] > 0
    for f in out["flags"]:
        assert "investigate" in f["recommendation"]
