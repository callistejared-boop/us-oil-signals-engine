"""Offline tests for engine/confluence_sandbox.py (Day 5 Phase 8). All tests
point REGISTRY_PATH at a tmp_path file via monkeypatch so nothing touches
the real repo's confluence_sandbox.json.
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import confluence_sandbox as sb  # noqa: E402


def test_register_candidate_starts_at_research(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "REGISTRY_PATH", tmp_path / "sandbox.json")
    rec = sb.register_candidate("order_flow_imbalance", "Tick-level order flow imbalance")
    assert rec["stage"] == "research"
    assert rec["name"] == "order_flow_imbalance"


def test_register_candidate_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "REGISTRY_PATH", tmp_path / "sandbox.json")
    sb.register_candidate("x", "desc 1")
    sb.advance_stage("x", "historical_testing", "backtest looks promising")
    rec2 = sb.register_candidate("x", "desc 2 - should be ignored")
    assert rec2["stage"] == "historical_testing"   # progress preserved
    assert rec2["description"] == "desc 1"          # not overwritten


def test_advance_stage_one_at_a_time(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "REGISTRY_PATH", tmp_path / "sandbox.json")
    sb.register_candidate("x", "desc")
    rec = sb.advance_stage("x", "historical_testing", "n=50 backtest, positive expectancy")
    assert rec["stage"] == "historical_testing"
    assert len(rec["history"]) == 2


def test_advance_stage_rejects_skipping_stages(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "REGISTRY_PATH", tmp_path / "sandbox.json")
    sb.register_candidate("x", "desc")
    with pytest.raises(ValueError):
        sb.advance_stage("x", "production_recommendation", "skipping straight to prod")


def test_advance_stage_rejects_unknown_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "REGISTRY_PATH", tmp_path / "sandbox.json")
    with pytest.raises(ValueError):
        sb.advance_stage("never_registered", "historical_testing", "note")


def test_advance_stage_requires_evidence_note(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "REGISTRY_PATH", tmp_path / "sandbox.json")
    sb.register_candidate("x", "desc")
    with pytest.raises(ValueError):
        sb.advance_stage("x", "historical_testing", "")


def test_full_pipeline_progression(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "REGISTRY_PATH", tmp_path / "sandbox.json")
    sb.register_candidate("x", "desc")
    sb.advance_stage("x", "historical_testing", "note1")
    sb.advance_stage("x", "walk_forward", "note2")
    sb.advance_stage("x", "paper_trading", "note3")
    rec = sb.advance_stage("x", "production_recommendation", "note4 - 30+ paper trades, positive")
    assert rec["stage"] == "production_recommendation"
    assert sb.is_production_ready("x") is True
    assert len(rec["history"]) == 5   # register + 4 advances


def test_is_production_ready_false_for_earlier_stages(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "REGISTRY_PATH", tmp_path / "sandbox.json")
    sb.register_candidate("x", "desc")
    assert sb.is_production_ready("x") is False


def test_is_production_ready_false_for_unknown_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "REGISTRY_PATH", tmp_path / "sandbox.json")
    assert sb.is_production_ready("nope") is False


def test_list_candidates_filters_by_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "REGISTRY_PATH", tmp_path / "sandbox.json")
    sb.register_candidate("a", "desc")
    sb.register_candidate("b", "desc")
    sb.advance_stage("b", "historical_testing", "note")
    research_only = sb.list_candidates(stage="research")
    assert [c["name"] for c in research_only] == ["a"]


def test_get_candidate_returns_none_for_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "REGISTRY_PATH", tmp_path / "sandbox.json")
    assert sb.get_candidate("nope") is None


def test_confluence_module_never_imports_sandbox():
    """The core Phase 8 guarantee: engine/confluence.py has zero dependency
    on the sandbox registry, so nothing registered here can ever influence
    a live score no matter what stage it reaches."""
    import inspect
    from engine import confluence as cf
    src = inspect.getsource(cf)
    assert "confluence_sandbox" not in src
    assert "sandbox" not in src.lower()


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)
