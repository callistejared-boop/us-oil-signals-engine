"""Offline tests for engine/trade_lifecycle.py (Priority 5 Item 3). All
persistence tests point HISTORY_PATH at a tmp_path file via monkeypatch so
nothing touches the real repo's trade_lifecycle.jsonl -- mirrors
test_decision_audit_history.py's exact fixture pattern.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import trade_lifecycle as tl  # noqa: E402


# --------------------------------------------------------------------------
# Pure state machine (no persistence involved)
# --------------------------------------------------------------------------

def test_new_lifecycle_starts_detected():
    rec = tl.new_lifecycle("XAUUSD-2026-08-15T10:00:00", "XAUUSD", "long")
    assert rec.stage == tl.Stage.DETECTED
    assert len(rec.history) == 1
    assert rec.history[0]["stage"] == tl.Stage.DETECTED
    assert rec.decision_id == "XAUUSD-2026-08-15T10:00:00"


def test_new_lifecycle_accepts_explicit_decision_id():
    rec = tl.new_lifecycle("chain-1", "XAUUSD", "long", decision_id="other-id")
    assert rec.decision_id == "other-id"


def test_transition_is_pure_returns_new_object():
    rec = tl.new_lifecycle("chain-1", "XAUUSD", "long")
    rec2 = tl.transition(rec, tl.Stage.QUALIFIED)
    assert rec.stage == tl.Stage.DETECTED  # original untouched
    assert rec2.stage == tl.Stage.QUALIFIED
    assert rec is not rec2


def test_transition_appends_to_history_not_replaces():
    rec = tl.new_lifecycle("chain-1", "XAUUSD", "long")
    rec = tl.transition(rec, tl.Stage.QUALIFIED, reason="passed confluence")
    rec = tl.transition(rec, tl.Stage.PENDING, reason="watching")
    assert [h["stage"] for h in rec.history] == [
        tl.Stage.DETECTED, tl.Stage.QUALIFIED, tl.Stage.PENDING]
    assert rec.history[-1]["reason"] == "watching"


def test_transition_can_set_extra_fields_atomically():
    rec = tl.new_lifecycle("chain-1", "XAUUSD", "long")
    rec = tl.transition(rec, tl.Stage.QUALIFIED)
    rec = tl.transition(rec, tl.Stage.PENDING)
    rec = tl.transition(rec, tl.Stage.ENTERED, trade_ref="XAUUSD-2026-08-15T10:05:00")
    assert rec.trade_ref == "XAUUSD-2026-08-15T10:05:00"
    assert rec.stage == tl.Stage.ENTERED


def test_full_happy_path_chain_detected_to_learned():
    rec = tl.new_lifecycle("chain-1", "XAUUSD", "long")
    rec = tl.transition(rec, tl.Stage.QUALIFIED)
    rec = tl.transition(rec, tl.Stage.PENDING)
    rec = tl.transition(rec, tl.Stage.ENTERED, trade_ref="ref-1")
    rec = tl.transition(rec, tl.Stage.MANAGING)
    rec = tl.transition(rec, tl.Stage.CLOSED, outcome="win", result_r=1.5)
    rec = tl.transition(rec, tl.Stage.LEARNED)
    assert rec.stage == tl.Stage.LEARNED
    assert rec.outcome == "win"
    assert rec.result_r == 1.5
    assert len(rec.history) == 7


def test_direct_entered_path_without_pending_is_valid():
    """QUALIFIED -> ENTERED directly is in the graph (future-proofing for
    a hypothetical direct-fill strategy) even though today's
    alert_signals.py wiring always routes through PENDING first."""
    rec = tl.new_lifecycle("chain-1", "XAUUSD", "long")
    rec = tl.transition(rec, tl.Stage.QUALIFIED)
    rec = tl.transition(rec, tl.Stage.ENTERED, trade_ref="ref-1")
    assert rec.stage == tl.Stage.ENTERED


def test_rejected_reachable_from_detected_qualified_and_pending():
    for stages_before in ([], [tl.Stage.QUALIFIED], [tl.Stage.QUALIFIED, tl.Stage.PENDING]):
        rec = tl.new_lifecycle("chain-1", "XAUUSD", "long")
        for st in stages_before:
            rec = tl.transition(rec, st)
        rec = tl.transition(rec, tl.Stage.REJECTED)
        assert rec.stage == tl.Stage.REJECTED


def test_voided_only_reachable_from_pending():
    rec = tl.new_lifecycle("chain-1", "XAUUSD", "long")
    rec = tl.transition(rec, tl.Stage.QUALIFIED)
    rec = tl.transition(rec, tl.Stage.PENDING)
    rec = tl.transition(rec, tl.Stage.VOIDED)
    assert rec.stage == tl.Stage.VOIDED


def test_invalid_transition_raises():
    rec = tl.new_lifecycle("chain-1", "XAUUSD", "long")
    try:
        tl.transition(rec, tl.Stage.ENTERED)  # DETECTED -> ENTERED is not valid
        assert False, "expected InvalidTransition"
    except tl.InvalidTransition:
        pass


def test_terminal_stages_have_no_outgoing_transitions_except_closed_to_learned():
    for stage in tl.Stage.TERMINAL:
        allowed = tl.VALID_TRANSITIONS[stage]
        if stage == tl.Stage.CLOSED:
            assert allowed == {tl.Stage.LEARNED}
        else:
            assert allowed == set(), f"{stage} should have no outgoing transitions"


def test_is_terminal():
    for stage in (tl.Stage.REJECTED, tl.Stage.VOIDED, tl.Stage.CLOSED, tl.Stage.LEARNED):
        assert tl.is_terminal(stage)
    for stage in (tl.Stage.DETECTED, tl.Stage.QUALIFIED, tl.Stage.PENDING,
                  tl.Stage.ENTERED, tl.Stage.MANAGING):
        assert not tl.is_terminal(stage)


def test_can_transition_matches_valid_transitions_graph():
    for frm, tos in tl.VALID_TRANSITIONS.items():
        for to in tl.Stage.ALL:
            expected = to in tos
            assert tl.can_transition(frm, to) == expected


def test_every_non_terminal_stage_can_eventually_reach_a_terminal_stage():
    """Structural sanity check: no stage is a dead end that isn't terminal."""
    for stage in tl.Stage.ALL:
        if tl.is_terminal(stage):
            continue
        seen, stack = set(), [stage]
        reached_terminal = False
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            if tl.is_terminal(cur):
                reached_terminal = True
                break
            stack.extend(tl.VALID_TRANSITIONS.get(cur, set()))
        assert reached_terminal, f"{stage} cannot reach any terminal stage"


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------

def test_record_writes_and_latest_for_reads_back(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    rec = tl.new_lifecycle("chain-1", "XAUUSD", "long")
    row = tl.record(rec)
    assert row["lifecycle_id"] == "chain-1"
    assert row["record_type"] == "lifecycle"
    assert "recorded" in row
    out = tl.latest_for("chain-1")
    assert out["stage"] == tl.Stage.DETECTED


def test_latest_for_returns_most_recent_of_several_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    rec = tl.new_lifecycle("chain-1", "XAUUSD", "long")
    tl.record(rec)
    rec = tl.transition(rec, tl.Stage.QUALIFIED)
    tl.record(rec)
    rec = tl.transition(rec, tl.Stage.PENDING)
    tl.record(rec)
    out = tl.latest_for("chain-1")
    assert out["stage"] == tl.Stage.PENDING
    assert len(out["history"]) == 3


def test_latest_for_unknown_id_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    assert tl.latest_for("nonexistent") is None
    assert tl.latest_for("") is None


def test_chain_for_returns_all_rows_in_write_order(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    rec = tl.new_lifecycle("chain-1", "XAUUSD", "long")
    tl.record(rec)
    rec = tl.transition(rec, tl.Stage.QUALIFIED)
    tl.record(rec)
    rec = tl.transition(rec, tl.Stage.REJECTED)
    tl.record(rec)
    chain = tl.chain_for("chain-1")
    assert [r["stage"] for r in chain] == [
        tl.Stage.DETECTED, tl.Stage.QUALIFIED, tl.Stage.REJECTED]


def test_find_by_trade_ref(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    rec = tl.new_lifecycle("chain-1", "XAUUSD", "long")
    rec = tl.transition(rec, tl.Stage.QUALIFIED)
    rec = tl.transition(rec, tl.Stage.PENDING)
    rec = tl.transition(rec, tl.Stage.ENTERED, trade_ref="trade-ref-1")
    tl.record(rec)
    out = tl.find_by_trade_ref("trade-ref-1")
    assert out is not None
    assert out["lifecycle_id"] == "chain-1"
    assert tl.find_by_trade_ref("no-such-ref") is None
    assert tl.find_by_trade_ref("") is None


def test_tail_filters_by_symbol(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    tl.record(tl.new_lifecycle("c1", "XAUUSD", "long"))
    tl.record(tl.new_lifecycle("c2", "BTCUSD", "short"))
    out = tl.tail(10, symbol="XAUUSD")
    assert len(out) == 1
    assert out[0]["symbol"] == "XAUUSD"


def test_rotate_caps_at_max_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    monkeypatch.setattr(tl, "MAX_LINES", 5)
    for i in range(10):
        tl.record(tl.new_lifecycle(f"chain-{i}", "XAUUSD", "long"))
    assert len(tl.all_rows()) == 5
    # newest rows survive
    assert tl.all_rows()[-1]["lifecycle_id"] == "chain-9"


def test_record_never_raises_on_bad_path(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "no" / "such" / "dir" / "f.jsonl")
    row = tl.record(tl.new_lifecycle("chain-1", "XAUUSD", "long"))
    assert row["lifecycle_id"] == "chain-1"  # returns the row even though write failed


# --------------------------------------------------------------------------
# High-level fail-safe helpers
# --------------------------------------------------------------------------

def test_seed_qualified_creates_detected_then_qualified(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    row = tl.seed_qualified("chain-1", "XAUUSD", "long", reason="passed confluence")
    assert row["stage"] == tl.Stage.QUALIFIED
    assert [h["stage"] for h in row["history"]] == [tl.Stage.DETECTED, tl.Stage.QUALIFIED]


def test_seed_rejected_creates_detected_then_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    row = tl.seed_rejected("chain-1", "XAUUSD", "long", reason="failed confluence")
    assert row["stage"] == tl.Stage.REJECTED


def test_mark_pending_after_seed_qualified(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    tl.seed_qualified("chain-1", "XAUUSD", "long")
    row = tl.mark_pending("chain-1", "XAUUSD", "long", reason="watching")
    assert row["stage"] == tl.Stage.PENDING


def test_mark_pending_defensive_when_no_prior_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    row = tl.mark_pending("chain-never-seeded", "XAUUSD", "long")
    assert row["stage"] == tl.Stage.PENDING
    assert [h["stage"] for h in row["history"]] == [
        tl.Stage.DETECTED, tl.Stage.QUALIFIED, tl.Stage.PENDING]


def test_mark_rejected_from_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    tl.seed_qualified("chain-1", "XAUUSD", "long")
    tl.mark_pending("chain-1", "XAUUSD", "long")
    row = tl.mark_rejected("chain-1", reason="risk lock at tap time")
    assert row["stage"] == tl.Stage.REJECTED


def test_mark_rejected_unknown_chain_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    assert tl.mark_rejected("no-such-chain") is None


def test_mark_entered_after_mark_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    tl.seed_qualified("chain-1", "XAUUSD", "long")
    tl.mark_pending("chain-1", "XAUUSD", "long")
    row = tl.mark_entered("chain-1", "trade-ref-1", "XAUUSD", "long", reason="tapped")
    assert row["stage"] == tl.Stage.ENTERED
    assert row["trade_ref"] == "trade-ref-1"


def test_mark_entered_defensive_when_no_prior_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    row = tl.mark_entered("chain-never-seeded", "trade-ref-1", "XAUUSD", "long")
    assert row["stage"] == tl.Stage.ENTERED
    assert row["trade_ref"] == "trade-ref-1"
    assert [h["stage"] for h in row["history"]] == [
        tl.Stage.DETECTED, tl.Stage.QUALIFIED, tl.Stage.PENDING, tl.Stage.ENTERED]


def test_mark_voided(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    tl.seed_qualified("chain-1", "XAUUSD", "long")
    tl.mark_pending("chain-1", "XAUUSD", "long")
    row = tl.mark_voided("chain-1", reason="aged out")
    assert row["stage"] == tl.Stage.VOIDED


def test_mark_voided_unknown_chain_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    assert tl.mark_voided("no-such-chain") is None


def test_close_by_trade_ref(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    tl.seed_qualified("chain-1", "XAUUSD", "long")
    tl.mark_pending("chain-1", "XAUUSD", "long")
    tl.mark_entered("chain-1", "trade-ref-1", "XAUUSD", "long")
    row = tl.close_by_trade_ref("trade-ref-1", outcome="win", result_r=1.5,
                                reason="journal settled")
    assert row["stage"] == tl.Stage.CLOSED
    assert row["outcome"] == "win"
    assert row["result_r"] == 1.5


def test_close_by_trade_ref_unknown_ref_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    assert tl.close_by_trade_ref("no-such-ref", "win", 1.0) is None


# --------------------------------------------------------------------------
# sync_closures() -- the alert_signals.py journal.settle() hook
# --------------------------------------------------------------------------

def _closed_trade_row(id_, symbol="XAUUSD", status="win", result_r=1.5):
    return {"id": id_, "symbol": symbol, "status": status, "result_r": result_r,
           "direction": "long", "entry": 2000.0, "stop": 1990.0, "target": 2020.0}


def test_sync_closures_closes_matching_entered_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    tl.seed_qualified("chain-1", "XAUUSD", "long")
    tl.mark_pending("chain-1", "XAUUSD", "long")
    tl.mark_entered("chain-1", "trade-ref-1", "XAUUSD", "long")
    rows = [_closed_trade_row("trade-ref-1")]
    out = tl.sync_closures("XAUUSD", rows=rows)
    assert len(out) == 1
    assert out[0]["stage"] == tl.Stage.CLOSED
    assert out[0]["outcome"] == "win"


def test_sync_closures_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    tl.seed_qualified("chain-1", "XAUUSD", "long")
    tl.mark_pending("chain-1", "XAUUSD", "long")
    tl.mark_entered("chain-1", "trade-ref-1", "XAUUSD", "long")
    rows = [_closed_trade_row("trade-ref-1")]
    out1 = tl.sync_closures("XAUUSD", rows=rows)
    out2 = tl.sync_closures("XAUUSD", rows=rows)  # second scan of same closed rows
    assert len(out1) == 1
    assert len(out2) == 0  # already closed, skipped


def test_sync_closures_ignores_other_symbols(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    tl.seed_qualified("chain-1", "BTCUSD", "long")
    tl.mark_pending("chain-1", "BTCUSD", "long")
    tl.mark_entered("chain-1", "trade-ref-1", "BTCUSD", "long")
    rows = [_closed_trade_row("trade-ref-1", symbol="BTCUSD")]
    out = tl.sync_closures("XAUUSD", rows=rows)  # wrong symbol requested
    assert out == []


def test_sync_closures_ignores_still_open_trades(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    rows = [{"id": "trade-ref-1", "symbol": "XAUUSD", "status": "open", "result_r": 0.0}]
    out = tl.sync_closures("XAUUSD", rows=rows)
    assert out == []


def test_sync_closures_skips_row_with_no_matching_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    rows = [_closed_trade_row("orphan-trade-ref")]
    out = tl.sync_closures("XAUUSD", rows=rows)
    assert out == []  # no chain has this trade_ref -- nothing to close, no crash


def test_sync_closures_never_raises_on_garbage_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    rows = [{}, {"status": "win"}, {"id": "x", "status": "win", "symbol": "XAUUSD"}, None]
    try:
        out = tl.sync_closures("XAUUSD", rows=[r for r in rows if r is not None])
    except Exception as exc:  # noqa: BLE001
        assert False, f"sync_closures raised: {exc}"
    assert isinstance(out, list)


def test_sync_closures_loads_from_journal_when_rows_omitted(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    from engine import journal as jr
    monkeypatch.setattr(jr, "_load", lambda: [_closed_trade_row("trade-ref-1")])
    tl.seed_qualified("chain-1", "XAUUSD", "long")
    tl.mark_pending("chain-1", "XAUUSD", "long")
    tl.mark_entered("chain-1", "trade-ref-1", "XAUUSD", "long")
    out = tl.sync_closures("XAUUSD")  # rows=None -> pulls from journal._load()
    assert len(out) == 1


# --------------------------------------------------------------------------
# Full end-to-end chain via the persistence layer
# --------------------------------------------------------------------------

def test_end_to_end_detected_through_closed_via_helpers(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    lid = "XAUUSD-2026-08-15T10:00:00"
    tl.seed_qualified(lid, "XAUUSD", "long", reason="score 78 >= 70")
    tl.mark_pending(lid, "XAUUSD", "long", reason="watching for entry at 2000")
    tl.mark_entered(lid, "XAUUSD-2026-08-15T11:30:00", "XAUUSD", "long", reason="tapped")
    tl.close_by_trade_ref("XAUUSD-2026-08-15T11:30:00", "win", 1.5, reason="settled")

    final = tl.latest_for(lid)
    assert final["stage"] == tl.Stage.CLOSED
    assert final["trade_ref"] == "XAUUSD-2026-08-15T11:30:00"
    assert final["outcome"] == "win"
    stages = [h["stage"] for h in final["history"]]
    assert stages == [tl.Stage.DETECTED, tl.Stage.QUALIFIED, tl.Stage.PENDING,
                      tl.Stage.ENTERED, tl.Stage.CLOSED]

    also_by_trade_ref = tl.find_by_trade_ref("XAUUSD-2026-08-15T11:30:00")
    assert also_by_trade_ref["lifecycle_id"] == lid


def test_end_to_end_voided_path(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    lid = "XAUUSD-2026-08-15T10:00:00"
    tl.seed_qualified(lid, "XAUUSD", "long")
    tl.mark_pending(lid, "XAUUSD", "long")
    tl.mark_voided(lid, reason="never tapped within MAX_WAIT_BARS")
    final = tl.latest_for(lid)
    assert final["stage"] == tl.Stage.VOIDED
    assert tl.is_terminal(final["stage"])


# --------------------------------------------------------------------------
# stage_summary() -- dashboard-facing aggregate
# --------------------------------------------------------------------------

def test_stage_summary_counts_latest_stage_per_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    tl.seed_qualified("chain-1", "XAUUSD", "long")
    tl.mark_pending("chain-1", "XAUUSD", "long")
    tl.seed_rejected("chain-2", "XAUUSD", "short")
    tl.seed_qualified("chain-3", "XAUUSD", "long")
    tl.mark_pending("chain-3", "XAUUSD", "long")
    tl.mark_entered("chain-3", "trade-ref-3", "XAUUSD", "long")

    out = tl.stage_summary(days=14)
    assert out["total_chains"] == 3
    assert out["by_stage"][tl.Stage.PENDING] == 1
    assert out["by_stage"][tl.Stage.REJECTED] == 1
    assert out["by_stage"][tl.Stage.ENTERED] == 1
    assert out["advisory_only"] is True


def test_stage_summary_filters_by_symbol(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    tl.seed_qualified("chain-1", "XAUUSD", "long")
    tl.seed_qualified("chain-2", "BTCUSD", "long")
    out = tl.stage_summary(days=14, symbol="XAUUSD")
    assert out["total_chains"] == 1
    assert out["symbol"] == "XAUUSD"


def test_stage_summary_empty_history(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "HISTORY_PATH", tmp_path / "trade_lifecycle.jsonl")
    out = tl.stage_summary(days=14)
    assert out["total_chains"] == 0
    assert out["by_stage"] == {}


def test_stage_summary_never_raises_on_corrupt_history(tmp_path, monkeypatch):
    p = tmp_path / "trade_lifecycle.jsonl"
    p.write_text("not valid json\n", encoding="utf-8")
    monkeypatch.setattr(tl, "HISTORY_PATH", p)
    out = tl.stage_summary(days=14)
    assert out["total_chains"] == 0
