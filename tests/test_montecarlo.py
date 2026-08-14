"""Offline tests for engine/montecarlo.py (V2.2 Priority 4 Item 1: extend
the existing 51-line bootstrap with a "recovery time" metric --
PHASE0_FORENSIC_AUDIT.md Section P was explicit that percentiles,
drawdown percentiles, and probability-of-ruin were already present and
did NOT need rebuilding; recovery time was the one genuinely missing
piece against the spec's stated requirements, so that's the only new
surface area here.
"""
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import montecarlo as mc  # noqa: E402


# --------------------------------------------------------------------------
# pre-existing behavior (regression guard -- unchanged logic, must still hold)
# --------------------------------------------------------------------------

def test_too_few_trades_returns_note_not_simulation():
    out = mc.simulate([1.0, -1.0, 2.0])
    assert "note" in out
    assert "paths" not in out


def test_simulate_returns_all_original_keys():
    rs = [1, -1, 2, -1, 1, 1, -2, 1, 1, -1, 2, 1]
    out = mc.simulate(rs, n_paths=200, seed=7)
    for key in ("paths", "trades_per_path", "total_r_p5", "total_r_p25",
                "total_r_p50", "total_r_p75", "total_r_p95", "prob_negative",
                "max_dd_p50", "max_dd_p95", "prob_ruin", "ruin_threshold_r"):
        assert key in out


def test_deterministic_with_fixed_seed():
    rs = [1, -1, 2, -1, 1, 1, -2, 1, 1, -1, 2, 1]
    out1 = mc.simulate(rs, n_paths=300, seed=42)
    out2 = mc.simulate(rs, n_paths=300, seed=42)
    assert out1 == out2


def test_percentiles_are_monotonic():
    rs = [1, -1, 2, -1, 1, 1, -2, 1, 1, -1, 2, 1] * 3
    out = mc.simulate(rs, n_paths=500, seed=3)
    assert out["total_r_p5"] <= out["total_r_p25"] <= out["total_r_p50"]
    assert out["total_r_p50"] <= out["total_r_p75"] <= out["total_r_p95"]


def test_all_positive_series_has_zero_ruin_probability():
    rs = [1.0] * 20
    out = mc.simulate(rs, n_paths=200, seed=1)
    assert out["prob_ruin"] == 0.0
    assert out["prob_negative"] == 0.0


def test_ruin_threshold_reflected_in_output():
    rs = [1, -1, 2, -1, 1, 1, -2, 1, 1, -1, 2, 1]
    out = mc.simulate(rs, n_paths=100, seed=5, ruin_r=-3.5)
    assert out["ruin_threshold_r"] == -3.5


# --------------------------------------------------------------------------
# new: recovery time metric
# --------------------------------------------------------------------------

def test_recovery_keys_present_in_output():
    rs = [1, -1, 2, -1, 1, 1, -2, 1, 1, -1, 2, 1] * 3
    out = mc.simulate(rs, n_paths=300, seed=11)
    assert "prob_never_recovered" in out
    assert "recovery_trades_p50" in out
    assert "recovery_trades_p95" in out


def test_all_winners_series_has_no_drawdown_recovery_needed():
    """An all-positive series never draws down, so every path's
    recovery time is 0 -- meaning there's nothing to accumulate into
    the recovery_trades distribution, and prob_never_recovered is 0."""
    rs = [1.0] * 20
    out = mc.simulate(rs, n_paths=200, seed=2)
    assert out["prob_never_recovered"] == 0.0
    # No actual drawdowns occurred, so no non-zero recovery samples exist.
    assert out["recovery_trades_p50"] is None
    assert out["recovery_trades_p95"] is None


def test_series_with_real_drawdown_produces_positive_recovery_time():
    rs = ([1, 1, 1, -1, -1, -1, -1, 2, 2, 2, 1, 1, -2, -2, 3, 1, 1, 1, -1, 1]
          * 4)
    out = mc.simulate(rs, n_paths=500, seed=9)
    assert out["recovery_trades_p50"] is not None
    assert out["recovery_trades_p50"] > 0
    assert out["recovery_trades_p95"] >= out["recovery_trades_p50"]


def test_prob_never_recovered_is_between_zero_and_one():
    rs = [1, -1, 2, -1, 1, 1, -2, 1, 1, -1, 2, 1] * 3
    out = mc.simulate(rs, n_paths=400, seed=13)
    assert 0.0 <= out["prob_never_recovered"] <= 1.0


def test_monotonically_declining_series_never_recovers():
    """A path that only ever loses can't recover from its own drawdown
    within the simulated window -- every path should be censored."""
    rs = [-1.0] * 15
    out = mc.simulate(rs, n_paths=100, seed=4)
    assert out["prob_never_recovered"] == 1.0
    assert out["recovery_trades_p50"] is None


# --------------------------------------------------------------------------
# _recovery_trades helper -- direct unit coverage
# --------------------------------------------------------------------------

def test_recovery_trades_helper_zero_when_no_drawdown():
    eq = np.array([1.0, 2.0, 3.0, 4.0])
    assert mc._recovery_trades(eq) == 0.0


def test_recovery_trades_helper_measures_peak_to_recovery():
    # peak at index 1 (value 2), trough at index 3 (value 0), recovers
    # to >= 2 at index 5 (value 2) -> 5 - 1 = 4 trades to recover.
    eq = np.array([1.0, 2.0, 1.0, 0.0, 1.0, 2.0])
    assert mc._recovery_trades(eq) == 4.0


def test_recovery_trades_helper_none_when_never_recovers():
    eq = np.array([1.0, 2.0, 1.0, 0.0, -1.0])
    assert mc._recovery_trades(eq) is None
