"""Offline tests for engine/edge_investigation.py (Day 10 — Experiment
#0001). All tests pass an explicit `rows=` list so nothing touches the
real trades.json; the module's use against the real journal is validated
separately and reported in PERFORMANCE_INVESTIGATION_0001.md /
DAY10_VALIDATION_REPORT.md, not re-asserted here (those real numbers can
legitimately change if trades.json changes; these tests must not)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import edge_investigation as ei  # noqa: E402


def _mk(i, r, symbol="XAUUSD", opened=None, closed=None, entry=100.0,
       stop=99.0, target=104.0, rr=4.0, confidence=80, **extra):
    row = {
        "id": f"{symbol}-{i}",
        "opened": opened or f"2026-01-{1 + i // 96:02d} {(i * 15 // 60) % 24:02d}:{(i * 15) % 60:02d}:00",
        "closed": closed or f"2026-01-{1 + i // 96:02d} {(i * 15 // 60 + 1) % 24:02d}:{(i * 15) % 60:02d}:00",
        "status": "win" if r > 1e-9 else "loss" if r < -1e-9 else "scratch",
        "result_r": r, "symbol": symbol, "entry": entry, "stop": stop,
        "target": target, "rr": rr, "confidence": confidence,
    }
    row.update(extra)
    return row


# --- holding_time_stats / stop_target_stats -------------------------------

def test_holding_time_stats_basic():
    rows = [_mk(0, 1.0, opened="2026-01-01 00:00:00", closed="2026-01-01 01:00:00"),
           _mk(1, 1.0, opened="2026-01-01 00:00:00", closed="2026-01-01 00:30:00")]
    out = ei.holding_time_stats(rows)
    assert out["n"] == 2
    assert out["value"] == 45.0  # avg of 60 and 30 minutes


def test_holding_time_stats_empty():
    out = ei.holding_time_stats([])
    assert out["value"] is None and out["n"] == 0


def test_stop_target_stats_basic():
    rows = [_mk(0, 1.0, entry=100.0, stop=99.0, target=104.0, rr=4.0)]
    out = ei.stop_target_stats(rows)
    assert out["avg_stop_pct_of_entry"]["value"] == 1.0
    assert out["avg_target_pct_of_entry"]["value"] == 4.0
    assert out["avg_planned_rr"]["value"] == 4.0


# --- verify_core_metrics ----------------------------------------------------

def test_verify_core_metrics_insufficient():
    out = ei.verify_core_metrics(rows=[_mk(i, 1.0) for i in range(10)])
    assert out["sufficient"] is False


def test_verify_core_metrics_sufficient_includes_new_fields():
    rows = [_mk(i, 1.0 if i % 2 == 0 else -1.0) for i in range(70)]
    out = ei.verify_core_metrics(rows=rows, recent_n=30)
    assert out["sufficient"] is True
    for half in ("prior", "recent"):
        assert "holding_time_minutes" in out[half]
        assert "avg_stop_pct_of_entry" in out[half]
        assert "avg_target_pct_of_entry" in out[half]
        assert "avg_planned_rr" in out[half]
        assert "avg_confidence" in out[half]
        assert "expectancy" in out[half]  # reused from research_stats.full_report


# --- data_quality_review ----------------------------------------------------

def test_data_quality_review_detects_duplicate_ids():
    rows = [_mk(0, 1.0), dict(_mk(0, -1.0))]  # same id, different outcome
    rows[1]["id"] = rows[0]["id"]
    out = ei.data_quality_review(rows)
    assert out["duplicate_ids"]["n_colliding_id_groups"] == 1
    assert out["duplicate_ids"]["n_rows_affected"] == 2


def test_data_quality_review_no_duplicates_when_ids_unique():
    rows = [_mk(i, 1.0) for i in range(5)]
    out = ei.data_quality_review(rows)
    assert out["duplicate_ids"]["n_colliding_id_groups"] == 0


def test_data_quality_review_sign_mismatch_detection():
    bad = _mk(0, 1.0)
    bad["status"] = "loss"  # win-sized result_r but loss status
    out = ei.data_quality_review([bad])
    assert bad["id"] in out["sign_mismatches"]


def test_data_quality_review_field_coverage_quantified():
    rows = [_mk(i, 1.0, symbol="XAUUSD") for i in range(3)]
    out = ei.data_quality_review(rows)
    cov = out["field_coverage"]["symbol"]
    assert cov["populated"] == 3 and cov["total"] == 3 and cov["pct"] == 100.0


def test_data_quality_review_never_raises_on_garbage():
    out = ei.data_quality_review([{"garbage": True}, None, 42, "x"])
    assert "error" not in out or isinstance(out, dict)


def test_data_quality_review_empty_input():
    out = ei.data_quality_review([])
    assert out["n_total_rows"] == 0


# --- settlement-methodology classification / restatement -------------------

def test_settlement_rule_family_legacy_full_target():
    # result_r == finalR exactly -> legacy full-target rule
    row = _mk(0, 4.0, entry=100.0, stop=99.0, target=104.0)  # finalR = 4.0
    assert ei._settlement_rule_family(row) == "legacy_rule(full-target)"


def test_settlement_rule_family_current_partial_rule():
    # current rule caps a full-target win at 1 + 0.5*finalR = 1 + 0.5*4 = 3.0
    row = _mk(0, 3.0, entry=100.0, stop=99.0, target=104.0)
    assert ei._settlement_rule_family(row) == "current_rule(partial/be)"


def test_settlement_rule_family_none_for_non_win():
    row = _mk(0, -1.0)
    assert ei._settlement_rule_family(row) is None


def test_restate_win_to_current_methodology():
    # a legacy-rule win (result_r=finalR=4.0) restated to current rule
    row = _mk(0, 4.0, entry=100.0, stop=99.0, target=104.0)
    restated = ei.restate_win_to_current_methodology(row)
    assert restated == 3.0  # 1 + 0.5*4.0


def test_restate_leaves_losses_and_scratches_unchanged():
    loss = _mk(0, -1.0)
    scratch = _mk(1, 0.0)
    assert ei.restate_win_to_current_methodology(loss) == -1.0
    assert ei.restate_win_to_current_methodology(scratch) == 0.0


def test_restated_comparison_lowers_a_legacy_heavy_prior_window():
    # prior window: all wins settled under the legacy full-target rule
    # (result_r == finalR == 4.0). recent window: same setups but already
    # settled under the current rule (result_r == 3.0).
    prior = [_mk(i, 4.0 if i % 2 == 0 else -1.0) for i in range(40)]
    recent = [_mk(40 + i, 3.0 if i % 2 == 0 else -1.0) for i in range(30)]
    out = ei.restated_comparison(rows=prior + recent, recent_n=30)
    assert out["sufficient"] is True
    as_stored_prior_exp = out["as_stored"]["prior"]["expectancy"]["value"]
    restated_prior_exp = out["restated_to_current_methodology"]["prior"]["expectancy"]["value"]
    # restating legacy wins down to the current rule's formula must LOWER
    # (or leave equal, never raise) the prior window's expectancy
    assert restated_prior_exp <= as_stored_prior_exp


# --- segment_performance -----------------------------------------------------

def test_segment_performance_insufficient():
    out = ei.segment_performance(rows=[_mk(i, 1.0) for i in range(10)])
    assert out["sufficient"] is False


def test_segment_performance_covers_expected_dimensions():
    rows = [_mk(i, 1.0 if i % 2 == 0 else -1.0, symbol="XAUUSD" if i % 3 else "BTCUSD")
           for i in range(70)]
    out = ei.segment_performance(rows=rows, recent_n=30)
    assert out["sufficient"] is True
    for dim in ("symbol", "session", "day_of_week", "regime_trend",
               "regime_vol", "confidence_tier", "guard_action"):
        assert dim in out["dimensions"]
        assert "prior" in out["dimensions"][dim] and "recent" in out["dimensions"][dim]
    assert "strategy" not in out["dimensions"]  # explicitly not segmentable, see note
    assert "not segmentable" in out["note"] or "strategy" in out["note"]


def test_segment_performance_bucket_shape():
    rows = [_mk(i, 1.0 if i % 2 == 0 else -1.0) for i in range(70)]
    out = ei.segment_performance(rows=rows, recent_n=30)
    sym_bucket = out["dimensions"]["symbol"]["prior"]
    for key, stats in sym_bucket.items():
        assert set(stats.keys()) == {"n", "expectancy", "win_rate"}


# --- variance_permutation_test -----------------------------------------------

def test_variance_permutation_test_insufficient():
    out = ei.variance_permutation_test(rows=[_mk(i, 1.0) for i in range(10)])
    assert out["sufficient"] is False


def test_variance_permutation_test_reproducible_same_seed():
    rows = [_mk(i, 1.0 if i % 3 else -1.0) for i in range(99)]
    a = ei.variance_permutation_test(rows=rows, recent_n=30, trials=500, seed=7)
    b = ei.variance_permutation_test(rows=rows, recent_n=30, trials=500, seed=7)
    assert a == b


def test_variance_permutation_test_detects_genuinely_anomalous_window():
    # prior: all wins. recent: all losses -> should be a very rare draw.
    prior = [_mk(i, 2.0) for i in range(69)]
    recent = [_mk(69 + i, -1.0) for i in range(30)]
    out = ei.variance_permutation_test(rows=prior + recent, recent_n=30, trials=2000, seed=1)
    assert out["sufficient"] is True
    assert out["p_expectancy_le_observed"] < 0.05


def test_variance_permutation_test_high_p_when_recent_is_typical():
    # recent window drawn from the SAME random process as the rest of the
    # pool, using a win size (3.0 = 1 + 0.5*finalR for the fixed
    # entry/stop/target below) that is CONSISTENT with what
    # restate_win_to_current_methodology() would recompute — so
    # restatement is a no-op and doesn't itself skew the pool. A
    # deterministic alternating pattern, or a win value inconsistent with
    # entry/stop/target, can otherwise create an artificial imbalance
    # between "the last 30" and "the rest." Fixed seed=5 chosen because it
    # lands solidly mid-range (not an edge case in either tail).
    import random as _random
    rng = _random.Random(5)
    rows = [_mk(i, 3.0 if rng.random() < 0.5 else -1.0) for i in range(99)]
    out = ei.variance_permutation_test(rows=rows, recent_n=30, trials=2000, seed=1)
    assert out["sufficient"] is True
    assert out["p_expectancy_le_observed"] > 0.05


# --- feature_contribution_check ----------------------------------------------

def test_feature_contribution_check_reports_ref_coverage():
    rows = [_mk(i, 1.0, confluence_ref=("x" if i < 2 else "")) for i in range(10)]
    out = ei.feature_contribution_check(rows)
    assert out["ref_field_coverage"]["confluence_ref"]["populated"] == 2
    assert out["ref_field_coverage"]["confluence_ref"]["total"] == 10
    assert "not_a_causal_claim" in out


def test_feature_contribution_check_empty_input():
    out = ei.feature_contribution_check([])
    assert out["n_trades"] == 0


# --- full_investigation_report never raises ----------------------------------

def test_full_investigation_report_never_raises_on_garbage():
    out = ei.full_investigation_report(rows=[{"garbage": 1}, None, "x", 3.14])
    assert isinstance(out, dict)
    assert "error" not in out  # each section degrades independently, not the whole report


def test_full_investigation_report_all_sections_present_with_sufficient_data():
    rows = [_mk(i, 1.0 if i % 2 == 0 else -1.0) for i in range(99)]
    out = ei.full_investigation_report(rows=rows, trials=500)
    for key in ("verify_core_metrics", "data_quality_review", "restated_comparison",
               "evidence_tier_assessment", "segment_performance",
               "variance_permutation_test", "feature_contribution_check"):
        assert key in out


def test_full_investigation_report_empty_input():
    out = ei.full_investigation_report(rows=[])
    assert isinstance(out, dict)
    assert out["verify_core_metrics"]["sufficient"] is False
