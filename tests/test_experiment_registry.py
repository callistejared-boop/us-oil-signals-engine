"""Offline tests for engine/experiment_registry.py (Day 9). All tests point
HISTORY_PATH at a tmp_path file via monkeypatch so nothing touches the real
repo's experiment_registry.jsonl — mirrors decision_audit_history.py's
(Day 8) exact fixture pattern.
"""
import inspect
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import experiment_registry as er  # noqa: E402


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


# --- Hypothesis template -----------------------------------------------------

def test_hypothesis_is_complete_when_all_fields_present():
    assert _complete_hypothesis().is_complete() is True


def test_hypothesis_incomplete_without_success_criteria():
    h = _complete_hypothesis(measurable_success_criteria=[])
    assert h.is_complete() is False


def test_hypothesis_incomplete_without_rollback_criteria():
    h = _complete_hypothesis(rollback_criteria=[])
    assert h.is_complete() is False


def test_hypothesis_incomplete_with_blank_objective():
    h = _complete_hypothesis(objective="   ")
    assert h.is_complete() is False


def test_hypothesis_as_dict_has_all_template_fields():
    d = _complete_hypothesis().as_dict()
    for field in ("objective", "theoretical_rationale", "expected_benefit",
                 "implementation_scope", "dependencies", "risks",
                 "measurable_success_criteria", "rollback_criteria"):
        assert field in d


# --- log_idea / propose -------------------------------------------------------

def test_log_idea_creates_idea_stage_record(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    rec = er.log_idea("maybe try X", note="just a thought")
    assert rec["stage"] == "idea"
    state = er.current_state(rec["experiment_id"])
    assert state["current_stage"] == "idea"


def test_propose_records_complete_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    rec = er.propose("title", _complete_hypothesis())
    assert rec["complete"] is True
    assert rec["stage"] == "research_proposal"


def test_propose_incomplete_hypothesis_still_recorded(tmp_path, monkeypatch):
    """Incomplete proposals are recorded, not rejected — disclosed, not
    hidden."""
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    rec = er.propose("title", _complete_hypothesis(risks=[]))
    assert rec["complete"] is True   # risks isn't required for completeness
    rec2 = er.propose("title2", _complete_hypothesis(rollback_criteria=[]))
    assert rec2["complete"] is False   # but this IS recorded despite being incomplete


# --- transitions / current_state ----------------------------------------------

def test_transition_and_current_state(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    rec = er.propose("title", _complete_hypothesis())
    eid = rec["experiment_id"]
    er.transition(eid, "technical_design", notes="designed")
    er.transition(eid, "historical_testing", evidence={"expectancy": 0.2})
    state = er.current_state(eid)
    assert state["current_stage"] == "historical_testing"
    assert state["n_records"] == 3
    assert state["is_terminal"] is False


def test_transition_invalid_stage_flagged_not_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    rec = er.propose("title", _complete_hypothesis())
    out = er.transition(rec["experiment_id"], "not_a_real_stage")
    assert out["valid_stage"] is False
    # still written — never silently rejected
    assert er.current_state(rec["experiment_id"])["current_stage"] == "not_a_real_stage"


def test_current_state_missing_experiment_returns_none():
    assert er.current_state("does-not-exist") is None


def test_terminal_state_detection(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    rec = er.propose("title", _complete_hypothesis())
    eid = rec["experiment_id"]
    er.transition(eid, "rejected", decision="rejected", rationale="not representative")
    state = er.current_state(eid)
    assert state["is_terminal"] is True
    assert state["decision"] == "rejected"


# --- registry-level queries -----------------------------------------------------

def test_active_completed_rejected_partition(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    a = er.propose("active-one", _complete_hypothesis())["experiment_id"]
    b = er.propose("completed-one", _complete_hypothesis())["experiment_id"]
    c = er.propose("rejected-one", _complete_hypothesis())["experiment_id"]
    er.transition(a, "technical_design")
    er.transition(b, "ongoing_monitoring", decision="promoted")
    er.transition(c, "rejected", decision="rejected")

    active_ids = [s["experiment_id"] for s in er.active_experiments()]
    completed_ids = [s["experiment_id"] for s in er.completed_experiments()]
    rejected_ids = [s["experiment_id"] for s in er.rejected_experiments()]

    assert a in active_ids and b not in active_ids and c not in active_ids
    assert b in completed_ids
    assert c in rejected_ids


def test_rejected_experiments_remain_permanently_queryable(tmp_path, monkeypatch):
    """Mandate: 'Failed experiments are valuable knowledge and should
    remain documented.'"""
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    eid = er.propose("doomed", _complete_hypothesis())["experiment_id"]
    er.transition(eid, "walk_forward_testing")
    er.transition(eid, "rejected", decision="rejected", rationale="OOS Brier worse than base rate")
    hist = er.history(eid)
    assert len(hist) == 3
    assert hist[-1]["rationale"] == "OOS Brier worse than base rate"


def test_history_never_mutated_in_place(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    eid = er.propose("x", _complete_hypothesis())["experiment_id"]
    before = (tmp_path / "exp.jsonl").read_text()
    er.transition(eid, "technical_design")
    after = (tmp_path / "exp.jsonl").read_text()
    assert after.startswith(before)


def test_no_mutator_besides_record_writes():
    """Structural proof of immutability, same discipline as Day 8's
    decision_audit_history.py."""
    names = [n for n, obj in inspect.getmembers(er) if inspect.isfunction(obj)]
    forbidden = {"update", "delete", "overwrite", "edit", "modify", "remove", "patch"}
    for n in names:
        lname = n.lower()
        assert not any(f in lname for f in forbidden), f"unexpected mutator-like function: {n}"


def test_lifecycle_stages_match_mandate_order():
    assert er.LIFECYCLE_STAGES == [
        "idea", "research_proposal", "technical_design",
        "implementation_research_branch", "historical_testing",
        "walk_forward_testing", "paper_trading", "performance_review",
        "production_recommendation", "controlled_release", "ongoing_monitoring",
    ]


def test_every_lifecycle_stage_has_criteria():
    for stage in er.LIFECYCLE_STAGES:
        assert stage in er.STAGE_CRITERIA
        assert "entry" in er.STAGE_CRITERIA[stage]
        assert "exit" in er.STAGE_CRITERIA[stage]


def test_all_rows_and_tail_never_raise_on_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "nope.jsonl")
    assert er.all_rows() == []
    assert er.tail(5) == []
