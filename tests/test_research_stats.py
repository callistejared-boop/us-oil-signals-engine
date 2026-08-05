"""Offline tests for engine/research_stats.py (Day 9)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import research_stats as rs  # noqa: E402


def _rows(rs_list):
    return [{"result_r": r} for r in rs_list]


# --- input normalization -------------------------------------------------------

def test_accepts_plain_float_list():
    out = rs.expectancy([1.0, -1.0, 2.0])
    assert out["value"] == 0.667


def test_accepts_dict_rows():
    out = rs.expectancy(_rows([1.0, -1.0, 2.0]))
    assert out["value"] == 0.667


def test_accepts_objects_with_result_r():
    class T:
        def __init__(self, r):
            self.result_r = r
    out = rs.expectancy([T(1.0), T(-1.0)])
    assert out["value"] == 0.0


def test_skips_unparseable_entries_without_raising():
    # "garbage"/None have no `.result_r` -> skipped; a dict always defaults
    # `result_r` to 0 via `.get(..., 0)`, so it's kept as 0.0, not skipped.
    out = rs.expectancy([1.0, "garbage", None, {"no_result_r": True}])
    assert out["n"] == 2


# --- expectancy / win_rate / avg_r ----------------------------------------------

def test_expectancy_empty():
    out = rs.expectancy([])
    assert out["value"] is None and out["sufficient"] is False


def test_expectancy_sufficiency_flag():
    small = rs.expectancy([1.0] * 10)
    large = rs.expectancy([1.0] * 35)
    assert small["sufficient"] is False
    assert large["sufficient"] is True


def test_avg_r_multiple_is_expectancy_alias():
    data = [1.0, -1.0, 0.5, 2.0]
    assert rs.avg_r_multiple(data) == rs.expectancy(data)


def test_win_rate_basic():
    out = rs.win_rate([1.0, 1.0, -1.0, -1.0])
    assert out["value"] == 0.5


# --- profit factor --------------------------------------------------------------

def test_profit_factor_basic():
    out = rs.profit_factor([2.0, 2.0, -1.0, -1.0])
    assert out["value"] == 2.0   # gross wins 4.0 / gross losses 2.0


def test_profit_factor_undefined_with_no_losses():
    out = rs.profit_factor([1.0, 2.0, 3.0])
    assert out["value"] is None
    assert "undefined" in out["note"]


def test_profit_factor_insufficient_below_10_losses():
    data = [1.0] * 40 + [-1.0] * 3
    out = rs.profit_factor(data)
    assert out["sufficient"] is False
    assert out["n_losses"] == 3


# --- drawdown --------------------------------------------------------------------

def test_max_drawdown_basic():
    # +1, +1, -3, +1 -> peak 2, trough -1 -> dd = 3
    out = rs.max_drawdown([1.0, 1.0, -3.0, 1.0])
    assert out["value"] == -3.0


def test_max_drawdown_empty():
    assert rs.max_drawdown([])["value"] is None


# --- sharpe / sortino ------------------------------------------------------------

def test_sharpe_like_needs_at_least_two():
    assert rs.sharpe_like([1.0])["value"] is None


def test_sharpe_like_zero_variance():
    out = rs.sharpe_like([1.0, 1.0, 1.0])
    assert out["value"] is None
    assert "zero variance" in out["note"]


def test_sortino_like_needs_losses():
    out = rs.sortino_like([1.0, 2.0, 3.0])
    assert out["value"] is None
    assert "losing trades" in out["note"]


def test_sortino_like_basic():
    data = [1.0] * 20 + [-1.0] * 12
    out = rs.sortino_like(data)
    assert out["value"] is not None


# --- calmar / recovery factor ----------------------------------------------------

def test_calmar_like_undefined_with_no_drawdown():
    out = rs.calmar_like([1.0, 1.0, 1.0])
    assert out["value"] is None


def test_calmar_like_basic():
    data = [2.0, 2.0, -1.0]
    out = rs.calmar_like(data)
    assert out["value"] == 3.0   # total 3.0 / dd 1.0


def test_recovery_factor_matches_calmar_like():
    data = [2.0, -1.0, 2.0, -1.0]
    assert rs.recovery_factor(data) == rs.calmar_like(data)


# --- stability over time ----------------------------------------------------------

def test_stability_over_time_insufficient_trades():
    out = rs.stability_over_time([1.0, 1.0])
    assert out["sufficient"] is False


def test_stability_over_time_consistent_sign():
    data = [1.0] * 40
    out = rs.stability_over_time(data)
    assert out["consistent_sign"] is True


def test_stability_over_time_inconsistent_sign():
    data = [1.0] * 20 + [-1.0] * 20
    out = rs.stability_over_time(data)
    assert out["consistent_sign"] is False


# --- full_report -------------------------------------------------------------------

def test_full_report_has_every_metric():
    data = [1.0, -1.0, 2.0, -0.5] * 15
    out = rs.full_report(data)
    for key in ("expectancy", "profit_factor", "win_rate", "avg_r_multiple",
               "max_drawdown", "sharpe_like", "sortino_like", "calmar_like",
               "recovery_factor", "stability_over_time"):
        assert key in out


def test_full_report_never_raises_on_garbage():
    out = rs.full_report("not-a-list")
    assert isinstance(out, dict)


def test_full_report_empty_input():
    out = rs.full_report([])
    assert out["n"] == 0
