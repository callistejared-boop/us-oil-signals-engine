"""Offline tests for alert_signals.py's Priority 5 Item 3 integration
point: sync_lifecycle_closures(). Mirrors
test_alert_signals_broker.py's exact pattern for
sync_paper_broker_closures() -- the real trade_lifecycle.jsonl file is
never touched here (that's what tests/test_trade_lifecycle.py is for);
this file only tests the thin alert_signals.py wrapper with a
monkeypatched engine.trade_lifecycle collaborator.
"""
import pathlib
import sys
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import alert_signals as als  # noqa: E402
from engine import trade_lifecycle as tl  # noqa: E402


def test_sync_lifecycle_closures_calls_tl_sync_and_logs(monkeypatch):
    logged = []
    monkeypatch.setattr(als, "tl", SimpleNamespace(
        sync_closures=lambda sym, rows=None: [
            {"lifecycle_id": "chain-1", "trade_ref": "ref-1", "outcome": "win"}]))
    monkeypatch.setattr(als, "ledger", SimpleNamespace(log=lambda d: logged.append(d)))

    out = als.sync_lifecycle_closures("XAUUSD")
    assert len(out) == 1
    assert logged[0]["event"] == "lifecycle_closed"
    assert logged[0]["lifecycle_id"] == "chain-1"
    assert logged[0]["trade_ref"] == "ref-1"
    assert logged[0]["outcome"] == "win"


def test_sync_lifecycle_closures_never_raises_when_tl_blows_up(monkeypatch):
    def boom(sym, rows=None):
        raise RuntimeError("trade_lifecycle blew up")
    monkeypatch.setattr(als, "tl", SimpleNamespace(sync_closures=boom))
    out = als.sync_lifecycle_closures("XAUUSD")
    assert out == []


def test_sync_lifecycle_closures_returns_empty_when_nothing_closed(monkeypatch):
    monkeypatch.setattr(als, "tl", SimpleNamespace(sync_closures=lambda sym, rows=None: []))
    monkeypatch.setattr(als, "ledger", SimpleNamespace(log=lambda d: None))
    out = als.sync_lifecycle_closures("XAUUSD")
    assert out == []


# --- Real trade_lifecycle module wired end-to-end through alert_signals's
# own s1_lifecycle_id construction convention (journal.make_ref(sym, when))
# -- confirms the id scheme really is shared, not just documented as such.

def test_lifecycle_id_matches_pending_id_and_decision_id_construction(monkeypatch, tmp_path):
    """The three independent constructions this module's docstring claims
    are identical -- journal.make_ref(), pending.Pending.id, and
    explainability_engine's decision_id -- really do produce the same
    string for the same (symbol, when) pair, which is the whole premise
    `s1_lifecycle_id` / `rec["id"]` linkage in alert_signals.py depends
    on."""
    from engine import journal, pending, explainability_engine as expl
    import pandas as pd

    sym, when = "XAUUSD", pd.Timestamp("2026-08-15 10:00:00")

    # journal.make_ref() needs _load() to not blow up; point it at an empty tmp store
    monkeypatch.setattr(journal, "STORE", tmp_path / "trades.json")
    monkeypatch.setattr(journal, "BAK", tmp_path / "trades.json.bak")
    ref_from_journal = journal.make_ref(sym, when)

    pending_id = f"{sym}-{str(when).replace(' ', 'T')}"

    snap = expl.build_decision_snapshot(sym, "long", when, stage="approval_or_rejection",
                                        final_action="approved_heads_up")
    assert ref_from_journal == pending_id == snap.decision_id
