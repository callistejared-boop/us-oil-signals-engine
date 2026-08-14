"""Offline tests for engine/promotion_gate.py (V2.2 Priority 5, Item 1).

Same fixture pattern as tests/test_experiment_registry.py: HISTORY_PATH is
monkeypatched onto experiment_registry (promotion_gate has no HISTORY_PATH
of its own -- it only reads via experiment_registry's own functions).
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import experiment_registry as er  # noqa: E402
from engine import promotion_gate as pg        # noqa: E402


def _complete_hypothesis(**overrides):
    defaults = dict(
        objective="Test whether X improves Y",
        theoretical_rationale="Because Z was observed",
        expected_benefit="Higher expectancy",
        implementation_scope="New optional module, advisory only",
        dependencies=["some_module"],
        risks=["overfitting"],
        measurable_success_criteria=["OOS expectancy improves by >0.1R with n>=30"],
        rollback_criteria=["no improvement after 60 OOS trades"],
    )
    defaults.update(overrides)
    return er.Hypothesis(**defaults)


def _walk_full_path(monkeypatch, eid, *, evidence=True):
    """Advance an experiment through every required stage in order, with
    evidence recorded at paper_trading/performance_review."""
    for stage in ("technical_design", "implementation_research_branch",
                 "historical_testing", "walk_forward_testing"):
        er.transition(eid, stage)
    er.transition(eid, "paper_trading",
                 evidence={"n": 40, "effective_tier": "moderate_confidence"} if evidence else None)
    er.transition(eid, "performance_review",
                 evidence={"n": 40, "effective_tier": "moderate_confidence"} if evidence else None)


# --------------------------------------------------------------------------
# found / not-found
# --------------------------------------------------------------------------

def test_missing_experiment_returns_found_false():
    out = pg.evaluate("does-not-exist")
    assert out["found"] is False


# --------------------------------------------------------------------------
# legitimate promotion
# --------------------------------------------------------------------------

def test_full_legitimate_path_is_eligible_and_not_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    eid = er.propose("clean-path", _complete_hypothesis())["experiment_id"]
    _walk_full_path(monkeypatch, eid)
    er.transition(eid, "production_recommendation", decision="promoted")

    out = pg.evaluate(eid)
    assert out["missing_required_stages"] == []
    assert out["hypothesis_complete"] is True
    assert out["evidence_recorded_at_paper_trading"] is True
    assert out["evidence_recorded_at_performance_review"] is True
    assert out["eligible_for_production"] is True
    assert out["premature_promotion"] is False
    assert out["blocking_reasons"] == []


def test_legitimate_promotion_never_appears_in_audit_all(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    eid = er.propose("clean-path-2", _complete_hypothesis())["experiment_id"]
    _walk_full_path(monkeypatch, eid)
    er.transition(eid, "controlled_release", decision="promoted")

    flagged_ids = [f["experiment_id"] for f in pg.audit_all()]
    assert eid not in flagged_ids


# --------------------------------------------------------------------------
# premature / illegitimate promotion
# --------------------------------------------------------------------------

def test_skipped_stages_flagged_as_missing_and_premature(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    eid = er.propose("shortcut", _complete_hypothesis())["experiment_id"]
    er.transition(eid, "production_recommendation", decision="promoted")

    out = pg.evaluate(eid)
    assert "technical_design" in out["missing_required_stages"]
    assert "paper_trading" in out["missing_required_stages"]
    assert out["eligible_for_production"] is False
    assert out["premature_promotion"] is True
    assert any("missing required stage" in r for r in out["blocking_reasons"])


def test_incomplete_hypothesis_blocks_eligibility(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    eid = er.propose("bad-hypothesis", _complete_hypothesis(rollback_criteria=[]))["experiment_id"]
    _walk_full_path(monkeypatch, eid)
    er.transition(eid, "production_recommendation", decision="promoted")

    out = pg.evaluate(eid)
    assert out["hypothesis_complete"] is False
    assert out["eligible_for_production"] is False
    assert out["premature_promotion"] is True
    assert any("incomplete" in r for r in out["blocking_reasons"])


def test_missing_evidence_at_paper_trading_blocks_eligibility(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    eid = er.propose("no-evidence", _complete_hypothesis())["experiment_id"]
    _walk_full_path(monkeypatch, eid, evidence=False)
    er.transition(eid, "production_recommendation", decision="promoted")

    out = pg.evaluate(eid)
    assert out["evidence_recorded_at_paper_trading"] is False
    assert out["eligible_for_production"] is False
    assert any("paper_trading" in r for r in out["blocking_reasons"])


def test_invalid_stage_record_disclosed(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    eid = er.propose("garbage-stage", _complete_hypothesis())["experiment_id"]
    er.transition(eid, "not_a_real_stage")

    out = pg.evaluate(eid)
    assert len(out["invalid_stage_records"]) == 1
    assert any("invalid" in r for r in out["blocking_reasons"])


def test_audit_all_surfaces_premature_promotion(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    good = er.propose("good", _complete_hypothesis())["experiment_id"]
    _walk_full_path(monkeypatch, good)
    er.transition(good, "production_recommendation", decision="promoted")

    bad = er.propose("bad", _complete_hypothesis())["experiment_id"]
    er.transition(bad, "controlled_release", decision="promoted")

    flagged_ids = [f["experiment_id"] for f in pg.audit_all()]
    assert bad in flagged_ids
    assert good not in flagged_ids


# --------------------------------------------------------------------------
# stages that are NOT yet promoted are never flagged, however incomplete
# --------------------------------------------------------------------------

def test_experiment_still_in_early_research_is_not_flagged_premature(tmp_path, monkeypatch):
    """An experiment sitting at `historical_testing` is, definitionally,
    not yet promoted -- missing later stages is expected, not a
    violation. `premature_promotion` only fires once the CURRENT stage
    claims to be production_recommendation/controlled_release/
    ongoing_monitoring."""
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    eid = er.propose("still-researching", _complete_hypothesis())["experiment_id"]
    er.transition(eid, "technical_design")
    er.transition(eid, "historical_testing")

    out = pg.evaluate(eid)
    assert out["missing_required_stages"] != []   # incomplete, as expected mid-research
    assert out["premature_promotion"] is False     # but NOT flagged -- not promoted yet


def test_idea_only_stage_not_required_for_eligibility(tmp_path, monkeypatch):
    """propose() can be called directly without a prior log_idea() --
    'idea' is documented as the lightest-weight OPTIONAL entry point, so
    its absence must not itself block eligibility."""
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    eid = er.propose("no-idea-stage", _complete_hypothesis())["experiment_id"]
    _walk_full_path(monkeypatch, eid)
    er.transition(eid, "production_recommendation", decision="promoted")

    out = pg.evaluate(eid)
    assert "idea" not in out["required_before_promotion"]
    assert out["eligible_for_production"] is True


# --------------------------------------------------------------------------
# this module must never gain write/blocking power over the registry
# --------------------------------------------------------------------------

def test_promotion_gate_never_blocks_experiment_registry_writes(tmp_path, monkeypatch):
    """Structural proof that evaluating a premature promotion does not
    (and cannot) prevent experiment_registry.transition() from writing
    it -- per RESEARCH_VALIDATION_SPECIFICATION.md Sec.2's explicit
    design choice, this module observes and discloses, it does not gate
    the append-only record."""
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    eid = er.propose("still-writes", _complete_hypothesis())["experiment_id"]
    pg.evaluate(eid)  # flags it as radically incomplete
    rec = er.transition(eid, "production_recommendation", decision="promoted")
    assert rec["stage"] == "production_recommendation"
    assert er.current_state(eid)["current_stage"] == "production_recommendation"


def test_summary_never_raises_and_reports_healthy_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "nope.jsonl")
    out = pg.summary()
    assert out["experiments_evaluated"] == 0
    assert out["flagged_premature_promotions"] == []
    assert out["healthy"] is True


def test_summary_reports_unhealthy_when_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    eid = er.propose("bad-again", _complete_hypothesis())["experiment_id"]
    er.transition(eid, "ongoing_monitoring", decision="promoted")

    out = pg.summary()
    assert out["healthy"] is False
    assert out["experiments_evaluated"] == 1
    assert len(out["flagged_premature_promotions"]) == 1
