"""Offline tests for engine/execution/comparison.py (Day 12) — the
Raw Strategy -> Ideal Execution -> Realistic Execution -> Observed
Performance four-layer research bridge."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.execution import comparison as cmp  # noqa: E402

ROWS = [
    {"id": "XAUUSD-1", "symbol": "XAUUSD", "direction": "long", "entry": 2350.0,
     "stop": 2340.0, "target": 2380.0, "status": "win", "result_r": 3.0,
     "opened": "2026-07-20 08:00:00"},
    {"id": "XAUUSD-2", "symbol": "XAUUSD", "direction": "short", "entry": 2360.0,
     "stop": 2370.0, "target": 2330.0, "status": "loss", "result_r": -1.0,
     "opened": "2026-07-21 13:00:00"},
    {"id": "WTIUSD-1", "symbol": "WTIUSD", "direction": "long", "entry": 78.0,
     "stop": 77.0, "target": 81.0, "status": "win", "result_r": 2.5,
     "opened": "2026-07-22 02:00:00"},
]


def test_compare_layers_returns_all_four_layers():
    out = cmp.compare_layers(rows=ROWS, profile="typical", seed=1)
    for key in ("raw_strategy", "ideal_execution", "realistic_execution", "observed_performance"):
        assert key in out
        assert out[key]["n"] == 3


def test_ideal_execution_identical_to_raw_strategy():
    out = cmp.compare_layers(rows=ROWS, profile="typical", seed=1)
    assert out["ideal_execution"] == out["raw_strategy"]


def test_observed_performance_identical_to_raw_strategy_today():
    """Honesty check: per this module's own documented disclosure, these
    two are numerically identical today because no live broker exists."""
    out = cmp.compare_layers(rows=ROWS, profile="typical", seed=1)
    assert out["observed_performance"] == out["raw_strategy"]


def test_realistic_execution_expectancy_lower_than_raw_under_stress():
    out = cmp.compare_layers(rows=ROWS, profile="stressed", seed=1)
    raw_exp = out["raw_strategy"]["expectancy"]["value"]
    realistic_exp = out["realistic_execution"]["expectancy"]["value"]
    assert realistic_exp <= raw_exp


def test_execution_drag_expectancy_delta_is_positive_or_zero_under_stress():
    out = cmp.compare_layers(rows=ROWS, profile="stressed", seed=1)
    delta = out["execution_drag"]["expectancy_delta"]
    assert delta is not None
    assert delta >= 0


def test_compare_layers_reproducible_with_same_seed():
    out1 = cmp.compare_layers(rows=ROWS, profile="typical", seed=7)
    out2 = cmp.compare_layers(rows=ROWS, profile="typical", seed=7)
    assert out1 == out2


def test_compare_layers_symbol_filter():
    out = cmp.compare_layers(rows=ROWS, symbol="WTIUSD", profile="typical", seed=1)
    assert out["n_trades"] == 1


def test_compare_layers_empty_rows_returns_valid_empty_layers():
    out = cmp.compare_layers(rows=[], profile="typical", seed=1)
    assert out["n_trades"] == 0
    assert out["raw_strategy"]["n"] == 0


def test_compare_layers_note_discloses_identity_relationship():
    out = cmp.compare_layers(rows=ROWS, profile="typical", seed=1)
    assert "numerically identical today" in out["note"]


def test_compare_layers_never_raises_on_internal_error(monkeypatch):
    from engine.execution import replay as rpmod

    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(rpmod, "run_replay", boom)
    out = cmp.compare_layers(rows=ROWS, profile="typical", seed=1)
    assert "error" in out
    assert out["n_trades"] == 0


def test_delta_helper_returns_none_on_missing_metric():
    assert cmp._delta({}, {}, "expectancy") is None


def test_stored_r_helper_reads_field():
    assert cmp._stored_r({"stored_result_r": 2.5}) == 2.5
    assert cmp._stored_r({}) is None
