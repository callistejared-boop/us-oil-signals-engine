"""Tests for engine/execution/execution_profile.py (V2.2 Priority 1
Item 3). Covers profile_for() lookup/fallback/overrides, and evaluate()
across each of the five evaluated dimensions (latency, spread multiplier,
slippage-as-cost_r, partial fill, liquidity shock) plus the deliberately
unevaluated sixth field (maximum_trade_duration_minutes).
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.execution import execution_profile as ep  # noqa: E402


def _report(latency_ms=1000.0, estimated_spread=0.10, base_spread=0.10,
           cost_r=0.01, filled=True, fill_fraction=1.0, partial_fill=False,
           liquidity_shock=False):
    return {
        "entry_filled": filled,
        "cost_r": cost_r,
        "entry_detail": {
            "latency": {"total_latency_ms": latency_ms},
            "spread": {"estimated_spread": estimated_spread, "base_spread": base_spread},
            "fill_fraction": fill_fraction,
            "partial_fill": partial_fill,
            "slippage": {"liquidity_shock": liquidity_shock},
        },
    }


def test_profile_for_known_style():
    prof = ep.profile_for("scalping")
    assert prof["style"] == "scalping"
    assert prof["acceptable_latency_ms"] == 3000.0


def test_profile_for_unknown_style_falls_back_to_default():
    prof = ep.profile_for("nonexistent_style")
    assert prof["style"] == ep.DEFAULT_STYLE
    assert prof["style_requested"] == "nonexistent_style"


def test_profile_for_overrides_shallow_merge():
    prof = ep.profile_for("day", overrides={"acceptable_latency_ms": 999.0})
    assert prof["acceptable_latency_ms"] == 999.0
    assert prof["acceptable_spread_multiplier"] == ep.PROFILES["day"]["acceptable_spread_multiplier"]


def test_overrides_do_not_mutate_profiles_table():
    ep.profile_for("day", overrides={"acceptable_latency_ms": 1.0})
    assert ep.PROFILES["day"]["acceptable_latency_ms"] == 15000.0


def test_evaluate_all_within_tolerance_for_swing_clean_fill():
    report = _report(latency_ms=45000.0, estimated_spread=0.30, base_spread=0.15,
                     cost_r=0.10)
    result = ep.evaluate(report, style="swing")
    assert result["all_within_tolerance"] is True
    assert all(c["within_tolerance"] for c in result["checks"].values())


def test_evaluate_latency_breach_for_scalping():
    report = _report(latency_ms=36000.0)   # far above scalping's 3000ms
    result = ep.evaluate(report, style="scalping")
    assert result["checks"]["latency"]["within_tolerance"] is False
    assert result["all_within_tolerance"] is False


def test_evaluate_spread_multiplier_computed_and_checked():
    report = _report(estimated_spread=0.36, base_spread=0.30)  # 1.2x
    result = ep.evaluate(report, style="scalping")   # scalping tolerates up to 1.2x
    assert abs(result["checks"]["spread"]["actual"] - 1.2) < 1e-9
    assert result["checks"]["spread"]["within_tolerance"] is True


def test_evaluate_spread_breach_above_multiplier():
    report = _report(estimated_spread=0.50, base_spread=0.30)  # ~1.667x
    result = ep.evaluate(report, style="scalping")
    assert result["checks"]["spread"]["within_tolerance"] is False


def test_evaluate_slippage_uses_absolute_cost_r():
    report = _report(cost_r=-0.05)  # sign shouldn't matter
    result = ep.evaluate(report, style="day")
    assert result["checks"]["slippage"]["actual"] == 0.05
    assert result["checks"]["slippage"]["within_tolerance"] is True  # 0.05 <= 0.08


def test_evaluate_partial_fill_intolerant_style_fails_on_any_partial():
    report = _report(partial_fill=True, fill_fraction=0.9)
    result = ep.evaluate(report, style="scalping")  # scalping: acceptable_partial_fill=False
    assert result["checks"]["partial_fill"]["within_tolerance"] is False


def test_evaluate_partial_fill_tolerant_style_passes_above_min_fraction():
    report = _report(partial_fill=True, fill_fraction=0.9)
    result = ep.evaluate(report, style="swing")  # swing: min_fill_fraction=0.5
    assert result["checks"]["partial_fill"]["within_tolerance"] is True


def test_evaluate_no_partial_fill_always_passes_that_check():
    report = _report(partial_fill=False, fill_fraction=1.0)
    result = ep.evaluate(report, style="scalping")
    assert result["checks"]["partial_fill"]["within_tolerance"] is True


def test_evaluate_liquidity_shock_breach_for_intolerant_style():
    report = _report(liquidity_shock=True)
    result = ep.evaluate(report, style="day")  # day: acceptable_liquidity_shock=False
    assert result["checks"]["liquidity_shock"]["within_tolerance"] is False


def test_evaluate_liquidity_shock_tolerated_by_swing():
    report = _report(liquidity_shock=True)
    result = ep.evaluate(report, style="swing")  # swing: acceptable_liquidity_shock=True
    assert result["checks"]["liquidity_shock"]["within_tolerance"] is True


def test_evaluate_unfilled_entry_is_never_within_tolerance():
    report = _report(filled=False)
    result = ep.evaluate(report, style="swing")
    assert result["entry_filled"] is False
    assert result["all_within_tolerance"] is False


def test_evaluate_maximum_trade_duration_is_informational_not_checked():
    report = _report()
    result = ep.evaluate(report, style="scalping")
    assert result["maximum_trade_duration_minutes"] == 30
    assert "maximum_trade_duration" not in result["checks"]


def test_evaluate_missing_spread_data_marks_check_not_within_tolerance():
    report = _report()
    report["entry_detail"]["spread"] = {"estimated_spread": None, "base_spread": None}
    result = ep.evaluate(report, style="day")
    assert result["checks"]["spread"]["actual"] is None
    assert result["checks"]["spread"]["within_tolerance"] is False


def test_evaluate_never_raises_on_malformed_report():
    result = ep.evaluate({"entry_detail": "not-a-dict"}, style="day")
    assert result["all_within_tolerance"] is False
    assert result["is_estimate"] is True


def test_evaluate_default_style_is_day():
    report = _report()
    result = ep.evaluate(report)
    assert result["style"] == "day"
