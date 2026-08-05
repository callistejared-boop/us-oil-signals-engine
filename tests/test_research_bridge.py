"""Offline tests for engine/broker/research_bridge.py (Day 13) —
verifies simulated/paper/live evidence sources stay separately labeled
and are never merged into one series."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.broker import research_bridge as rbg  # noqa: E402


def _rows():
    return [
        {"id": "XAUUSD-1", "symbol": "XAUUSD", "direction": "long", "entry": 2000.0,
         "stop": 1990.0, "status": "win", "result_r": 1.5,
         "opened": "2026-01-01T00:00:00", "closed": "2026-01-01T01:00:00"},
        {"id": "XAUUSD-2", "symbol": "XAUUSD", "direction": "short", "entry": 2050.0,
         "stop": 2060.0, "status": "loss", "result_r": -1.0,
         "opened": "2026-01-02T00:00:00", "closed": "2026-01-02T01:00:00"},
    ]


def test_evidence_sources_taxonomy_has_three_entries():
    assert set(rbg.EVIDENCE_SOURCES.keys()) == {"simulated", "paper", "live"}


def test_compare_evidence_sources_returns_all_three_keys(broker_paths):
    out = rbg.compare_evidence_sources(rows=_rows(), seed=1)
    assert "simulated" in out
    assert "paper" in out
    assert "live" in out
    assert out["live"] is None


def test_compare_evidence_sources_each_side_tagged_with_own_source(broker_paths):
    out = rbg.compare_evidence_sources(rows=_rows(), seed=1)
    assert out["simulated"]["evidence_source"] == "simulated"
    assert out["paper"]["evidence_source"] == "paper"


def test_compare_evidence_sources_never_merges_into_single_series(broker_paths):
    out = rbg.compare_evidence_sources(rows=_rows(), seed=1)
    # The two sides must remain structurally distinct dicts, not flattened
    # into one combined R-multiple list.
    assert isinstance(out["simulated"], dict)
    assert isinstance(out["paper"], dict)
    assert "raw_strategy" in out["simulated"]      # simulated-only shape
    assert "trades" in out["paper"]                # paper-only shape
    assert "raw_strategy" not in out["paper"]
    assert "trades" not in out["simulated"]


def test_compare_evidence_sources_degrades_one_side_independently(broker_paths, monkeypatch):
    from engine.execution import comparison as sim_comparison

    def _boom(*a, **k):
        raise RuntimeError("simulated layer broken")

    monkeypatch.setattr(sim_comparison, "compare_layers", _boom)
    out = rbg.compare_evidence_sources(rows=_rows(), seed=1)
    assert "error" in out["simulated"]
    assert "error" not in out["paper"]   # paper side unaffected


def test_compare_evidence_sources_never_raises(broker_paths):
    out = rbg.compare_evidence_sources(rows="not-a-list", seed=1)
    assert "simulated" in out and "paper" in out
