"""Offline tests for engine/research_dashboard.py (Day 9)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import research_dashboard as rd    # noqa: E402
from engine import experiment_registry as er    # noqa: E402


def _hyp():
    return er.Hypothesis(
        objective="obj", theoretical_rationale="rationale", expected_benefit="benefit",
        implementation_scope="scope", measurable_success_criteria=["x"], rollback_criteria=["y"])


def test_payload_has_required_top_level_keys():
    out = rd.build_research_payload()
    for key in ("advisory_only", "note", "lifecycle_stages", "terminal_stages",
               "stage_criteria", "active_experiments", "completed_experiments",
               "rejected_experiments", "edge_decay_check", "evidence_tier_reference"):
        assert key in out


def test_payload_is_advisory_only():
    out = rd.build_research_payload()
    assert out["advisory_only"] is True
    assert "separate" in out["note"].lower()


def test_payload_reflects_registry_state(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "HISTORY_PATH", tmp_path / "exp.jsonl")
    a = er.propose("in-progress", _hyp())["experiment_id"]
    b = er.propose("shipped", _hyp())["experiment_id"]
    c = er.propose("failed", _hyp())["experiment_id"]
    er.transition(b, "ongoing_monitoring", decision="promoted")
    er.transition(c, "rejected", decision="rejected")

    out = rd.build_research_payload()
    active_ids = [e["experiment_id"] for e in out["active_experiments"]]
    completed_ids = [e["experiment_id"] for e in out["completed_experiments"]]
    rejected_ids = [e["experiment_id"] for e in out["rejected_experiments"]]
    assert a in active_ids
    assert b in completed_ids
    assert c in rejected_ids


def test_experiment_summary_includes_objective():
    out = {"experiment_id": "x", "title": "t", "hypothesis": {"objective": "test obj"},
          "current_stage": "idea", "decision": "", "n_records": 1, "last_updated": "ts"}
    summary = rd._experiment_summary(out)
    assert summary["objective"] == "test obj"


def test_payload_never_raises_when_registry_unavailable(monkeypatch):
    def boom():
        raise RuntimeError("registry unavailable")
    monkeypatch.setattr(er, "active_experiments", boom)
    out = rd.build_research_payload()
    assert out["active_experiments"] == []
    assert "active" in out["errors"]


def test_evidence_tier_reference_matches_evidence_tiers_module():
    from engine import evidence_tiers as et
    out = rd.build_research_payload()
    assert len(out["evidence_tier_reference"]) == len(et.TIERS)


def test_lifecycle_stages_exposed_for_dashboard():
    out = rd.build_research_payload()
    assert out["lifecycle_stages"] == er.LIFECYCLE_STAGES


# --------------------------------------------------------------------------
# V2.2 Priority 5 extension: qualification_diagnostics
# --------------------------------------------------------------------------

def test_payload_includes_qualification_diagnostics():
    out = rd.build_research_payload()
    assert "qualification_diagnostics" in out
    assert out["qualification_diagnostics"]["advisory_only"] is True


def test_payload_never_raises_when_qualification_diagnostics_breaks(monkeypatch):
    from engine import qualification_diagnostics as qd
    monkeypatch.setattr(qd, "summary", lambda **k: (_ for _ in ()).throw(RuntimeError("boom")))
    out = rd.build_research_payload()   # must not raise
    assert "error" in out["qualification_diagnostics"]
