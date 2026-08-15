"""Offline tests for engine/qualification_diagnostics.py (V2.2 Priority 5
extension — triggered by a live diagnostic finding zero approvals in 9+
tracked days). Monkeypatches each upstream module's own read function
rather than touching real repo files, mirroring test_research_dashboard.py
and test_why_not.py's fixture style.
"""
import pathlib
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import qualification_diagnostics as qd   # noqa: E402
from engine import kill_switch                        # noqa: E402


def _iso(dt):
    return dt.isoformat(timespec="seconds")


def _row(final_action, stage=None, category=None, score=None, when=None):
    when = when or datetime.now(timezone.utc)
    r = {"final_action": final_action, "recorded": _iso(when)}
    if stage:
        r["stage"] = stage
    if category:
        r["rejection"] = {"category": category}
    if score is not None:
        r["confluence_summary"] = {"score": score}
    return r


# --------------------------------------------------------------------------
# rejection_summary
# --------------------------------------------------------------------------

def test_rejection_summary_counts_final_actions_and_stages(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [
        _row("rejected", stage="confluence_assessment", category="weak_evidence", score=66, when=now),
        _row("rejected", stage="confluence_assessment", category="weak_evidence", score=60, when=now),
        _row("rejected", stage="portfolio_risk", category="drawdown_protection", when=now),
        _row("approved_heads_up", when=now),
    ]
    monkeypatch.setattr(qd.dah, "all_rows", lambda: rows)
    out = qd.rejection_summary(days=14)
    assert out["decisions_in_window"] == 4
    assert out["final_action_counts"]["rejected"] == 3
    assert out["final_action_counts"]["approved_heads_up"] == 1
    assert out["rejection_stage_counts"]["confluence_assessment"] == 2
    assert out["rejection_category_counts"]["weak_evidence"] == 2
    assert out["confluence_score_distribution"]["n"] == 2
    assert out["confluence_score_distribution"]["near_threshold_60_to_70"] == 2


def test_rejection_summary_excludes_rows_outside_window(monkeypatch):
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=30)
    rows = [_row("rejected", stage="confluence_assessment", score=50, when=old),
           _row("rejected", stage="confluence_assessment", score=50, when=now)]
    monkeypatch.setattr(qd.dah, "all_rows", lambda: rows)
    out = qd.rejection_summary(days=14)
    assert out["decisions_in_window"] == 1


def test_rejection_summary_handles_empty_history(monkeypatch):
    monkeypatch.setattr(qd.dah, "all_rows", lambda: [])
    out = qd.rejection_summary(days=14)
    assert out["decisions_in_window"] == 0
    assert out["confluence_score_distribution"] is None


def test_rejection_summary_never_raises(monkeypatch):
    monkeypatch.setattr(qd.dah, "all_rows", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    out = qd.rejection_summary(days=14)
    assert "error" in out


# --------------------------------------------------------------------------
# disagree_frequency
# --------------------------------------------------------------------------

def test_disagree_frequency_counts_and_ranks(monkeypatch):
    rows = [
        {"event": "confluence_held", "disagree": ["liquidity strength", "COT positioning"]},
        {"event": "confluence_held", "disagree": ["liquidity strength"]},
        {"event": "regime", "symbol": "XAUUSD"},   # non-matching event, must be ignored
    ]
    monkeypatch.setattr(qd.ledger, "tail", lambda n: rows)
    out = qd.disagree_frequency(top=5)
    assert out["confluence_held_events"] == 2
    assert out["top_disagreeing_checks"][0] == ("liquidity strength", 2)


def test_disagree_frequency_never_raises(monkeypatch):
    monkeypatch.setattr(qd.ledger, "tail", lambda n: (_ for _ in ()).throw(RuntimeError("boom")))
    out = qd.disagree_frequency()
    assert "error" in out


# --------------------------------------------------------------------------
# current_regime_snapshot
# --------------------------------------------------------------------------

def test_current_regime_snapshot_reads_last_for_per_symbol(monkeypatch):
    def fake_last_for(symbol, timeframe="strategic"):
        if symbol == "XAUUSD":
            return {"primary": "Distribution", "quality_score": 53, "confidence": 37,
                   "ts": "2026-08-15T23:21:11+00:00"}
        return None

    monkeypatch.setattr(qd.rh, "last_for", fake_last_for)
    out = qd.current_regime_snapshot(symbols=["XAUUSD", "BTCUSD"])
    assert out["XAUUSD"]["primary"] == "Distribution"
    assert out["XAUUSD"]["quality_score"] == 53
    assert out["BTCUSD"] is None


def test_current_regime_snapshot_never_raises_per_symbol(monkeypatch):
    def boom(symbol, timeframe="strategic"):
        raise RuntimeError("feed down")

    monkeypatch.setattr(qd.rh, "last_for", boom)
    out = qd.current_regime_snapshot(symbols=["XAUUSD"])
    assert "error" in out["XAUUSD"]


# --------------------------------------------------------------------------
# summary
# --------------------------------------------------------------------------

def test_summary_assembles_every_section(monkeypatch):
    monkeypatch.setattr(qd.dah, "all_rows", lambda: [])
    monkeypatch.setattr(qd.ledger, "tail", lambda n: [])
    monkeypatch.setattr(qd.rh, "last_for", lambda symbol, timeframe="strategic": None)
    monkeypatch.setattr(qd.kill_switch, "current_stand_downs",
                        lambda **k: [kill_switch.StandDownStatus(
                            name="drawdown_protection", engaged=False, scope="portfolio",
                            reason="", category=None, source="test", detail={})])

    out = qd.summary(days=14, symbols=["XAUUSD"])
    assert out["advisory_only"] is True
    assert "rejection_summary" in out
    assert "disagree_frequency" in out
    assert "current_regime" in out
    assert out["current_stand_downs"][0]["name"] == "drawdown_protection"


def test_summary_never_raises_even_if_kill_switch_breaks(monkeypatch):
    monkeypatch.setattr(qd.dah, "all_rows", lambda: [])
    monkeypatch.setattr(qd.ledger, "tail", lambda n: [])
    monkeypatch.setattr(qd.rh, "last_for", lambda symbol, timeframe="strategic": None)
    monkeypatch.setattr(qd.kill_switch, "current_stand_downs",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("boom")))

    out = qd.summary(days=14, symbols=["XAUUSD"])   # must not raise
    assert out["current_stand_downs"][0]["error"]
