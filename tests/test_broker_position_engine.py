"""Offline tests for engine/broker/position_engine.py (Day 13)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.broker.position_engine import PositionEngine  # noqa: E402


def test_first_fill_opens_position():
    pe = PositionEngine()
    r = pe.on_fill("a1", "XAUUSD", "buy", "entry", 2000.0, 0.1, 0.0, 0.05, ref="ref1")
    assert r["action"] == "opened"
    snap = pe.snapshot("a1", "XAUUSD")
    assert snap.direction == "long"
    assert snap.quantity == 0.1
    assert snap.avg_entry == 2000.0
    assert snap.open_refs == ("ref1",)


def test_same_direction_add_weighted_average():
    # Both fills share ref="r1" - this is one trade being added to (e.g.
    # a scale-in), which must still weighted-average within that one
    # position. Two DIFFERENT refs on the same symbol are a separate
    # scenario covered by test_different_refs_same_symbol_tracked_separately
    # below - as of V2.2 Priority 1 Item 1 they are never blended.
    pe = PositionEngine()
    pe.on_fill("a1", "XAUUSD", "buy", "entry", 2000.0, 0.1, 0.0, 0.0, ref="r1")
    r = pe.on_fill("a1", "XAUUSD", "buy", "entry", 2010.0, 0.1, 0.0, 0.0, ref="r1")
    assert r["action"] == "increased"
    snap = pe.snapshot("a1", "XAUUSD", ref="r1")
    assert snap.quantity == 0.2
    assert abs(snap.avg_entry - 2005.0) < 1e-9
    assert snap.open_refs == ("r1",)


def test_opposite_direction_reduces_and_realizes_pnl():
    pe = PositionEngine()
    pe.on_fill("a1", "XAUUSD", "buy", "entry", 2000.0, 0.2, 0.0, 0.0, ref="r1")
    r = pe.on_fill("a1", "XAUUSD", "sell", "exit", 2010.0, 0.1, 0.0, 0.0, ref="r1")
    assert r["action"] == "reduced"
    snap = pe.snapshot("a1", "XAUUSD")
    assert snap.quantity == 0.1
    assert snap.direction == "long"
    assert abs(snap.realized_pnl - (10.0 * 0.1 * 100.0)) < 1e-6   # XAUUSD mult=100


def test_full_close_flattens_position():
    pe = PositionEngine()
    pe.on_fill("a1", "XAUUSD", "buy", "entry", 2000.0, 0.1, 0.0, 0.0, ref="r1")
    r = pe.on_fill("a1", "XAUUSD", "sell", "exit", 2020.0, 0.1, 0.0, 0.0, ref="r1")
    assert r["action"] == "closed"
    snap = pe.snapshot("a1", "XAUUSD")
    assert snap.direction == "flat"
    assert snap.quantity == 0.0
    assert abs(snap.realized_pnl - (20.0 * 0.1 * 100.0)) < 1e-6
    assert snap.open_refs == ()


def test_flip_when_opposite_fill_overshoots_quantity():
    # Same ref throughout - one trade whose position flips direction
    # (e.g. a reversal order on the same ticket), not two independent
    # trades. See the note on test_same_direction_add_weighted_average.
    pe = PositionEngine()
    pe.on_fill("a1", "XAUUSD", "buy", "entry", 2000.0, 0.1, 0.0, 0.0, ref="r1")
    r = pe.on_fill("a1", "XAUUSD", "sell", "entry", 2000.0, 0.3, 0.0, 0.0, ref="r1")
    assert r["action"] == "flipped"
    snap = pe.snapshot("a1", "XAUUSD", ref="r1")
    assert snap.direction == "short"
    assert abs(snap.quantity - 0.2) < 1e-9


def test_different_refs_same_symbol_tracked_separately():
    """V2.2 Priority 1 Item 1: the core behavioral change. Two
    independently-managed trades on the same symbol (different refs)
    must never blend into one weighted-average lot - each gets its own
    position, keyed by (account_id, symbol, ref)."""
    pe = PositionEngine()
    pe.on_fill("a1", "XAUUSD", "buy", "entry", 2000.0, 0.1, 0.0, 0.0, ref="r1")
    r = pe.on_fill("a1", "XAUUSD", "buy", "entry", 2010.0, 0.1, 0.0, 0.0, ref="r2")
    assert r["action"] == "opened"   # a brand new position for r2, not an add to r1
    snap_r1 = pe.snapshot("a1", "XAUUSD", ref="r1")
    snap_r2 = pe.snapshot("a1", "XAUUSD", ref="r2")
    assert snap_r1.quantity == 0.1 and snap_r1.avg_entry == 2000.0
    assert snap_r2.quantity == 0.1 and snap_r2.avg_entry == 2010.0
    open_refs = {p.ref for p in pe.open_positions("a1", "XAUUSD")}
    assert open_refs == {"r1", "r2"}


def test_snapshot_without_ref_returns_blended_aggregate_across_refs():
    """snapshot(account_id, symbol) with no ref still returns the old
    symbol-wide aggregate view, computed on demand across every open
    ref - preserved for callers that want total symbol exposure."""
    pe = PositionEngine()
    pe.on_fill("a1", "XAUUSD", "buy", "entry", 2000.0, 0.1, 0.0, 0.0, ref="r1")
    pe.on_fill("a1", "XAUUSD", "buy", "entry", 2010.0, 0.1, 0.0, 0.0, ref="r2")
    agg = pe.snapshot("a1", "XAUUSD")
    assert agg.direction == "long"
    assert agg.quantity == 0.2
    assert abs(agg.avg_entry - 2005.0) < 1e-9
    assert set(agg.open_refs) == {"r1", "r2"}
    assert agg.ref == ""   # empty ref marks this as the blended aggregate, not one trade


def test_realized_pnl_accumulates_across_multiple_close_cycles():
    pe = PositionEngine()
    pe.on_fill("a1", "XAUUSD", "buy", "entry", 2000.0, 0.1, 0.0, 0.0, ref="r1")
    pe.on_fill("a1", "XAUUSD", "sell", "exit", 2010.0, 0.1, 0.0, 0.0, ref="r1")   # +100
    pe.on_fill("a1", "XAUUSD", "buy", "entry", 2000.0, 0.1, 0.0, 0.0, ref="r2")
    pe.on_fill("a1", "XAUUSD", "sell", "exit", 2005.0, 0.1, 0.0, 0.0, ref="r2")   # +50
    snap = pe.snapshot("a1", "XAUUSD")
    assert abs(snap.realized_pnl - 150.0) < 1e-6


def test_fees_and_execution_costs_accumulate():
    pe = PositionEngine()
    pe.on_fill("a1", "XAUUSD", "buy", "entry", 2000.0, 0.1, 1.0, 5.0, ref="r1")
    snap = pe.snapshot("a1", "XAUUSD")
    assert snap.fees_paid == 1.0
    assert snap.execution_costs == 5.0


def test_unrealized_pnl_long_and_short():
    pe = PositionEngine()
    pe.on_fill("a1", "XAUUSD", "buy", "entry", 2000.0, 0.1, 0.0, 0.0, ref="r1")
    assert pe.unrealized_pnl("a1", "XAUUSD", 2010.0) > 0
    pe2 = PositionEngine()
    pe2.on_fill("a1", "XAUUSD", "sell", "entry", 2000.0, 0.1, 0.0, 0.0, ref="r1")
    assert pe2.unrealized_pnl("a1", "XAUUSD", 2010.0) < 0


def test_unrealized_pnl_none_for_unknown_position():
    pe = PositionEngine()
    assert pe.unrealized_pnl("a1", "XAUUSD", 2000.0) is None


def test_unrealized_pnl_zero_for_flat_position():
    pe = PositionEngine()
    pe.on_fill("a1", "XAUUSD", "buy", "entry", 2000.0, 0.1, 0.0, 0.0, ref="r1")
    pe.on_fill("a1", "XAUUSD", "sell", "exit", 2000.0, 0.1, 0.0, 0.0, ref="r1")
    assert pe.unrealized_pnl("a1", "XAUUSD", 2050.0) == 0.0


def test_margin_required_formula():
    pe = PositionEngine()
    margin = pe.margin_required("XAUUSD", 2000.0, 0.1, 20.0)
    assert abs(margin - (0.1 * 2000.0 * 100.0 / 20.0)) < 1e-6


def test_margin_required_infinite_when_zero_leverage():
    pe = PositionEngine()
    assert pe.margin_required("XAUUSD", 2000.0, 0.1, 0.0) == float("inf")


def test_open_positions_excludes_flat():
    pe = PositionEngine()
    pe.on_fill("a1", "XAUUSD", "buy", "entry", 2000.0, 0.1, 0.0, 0.0, ref="r1")
    pe.on_fill("a1", "WTIUSD", "buy", "entry", 70.0, 1.0, 0.0, 0.0, ref="r2")
    pe.on_fill("a1", "WTIUSD", "sell", "exit", 70.0, 1.0, 0.0, 0.0, ref="r2")   # closes WTI
    open_syms = {p.symbol for p in pe.open_positions("a1")}
    assert open_syms == {"XAUUSD"}


def test_reset_clears_one_account_not_others():
    pe = PositionEngine()
    pe.on_fill("a1", "XAUUSD", "buy", "entry", 2000.0, 0.1, 0.0, 0.0, ref="r1")
    pe.on_fill("a2", "XAUUSD", "buy", "entry", 2000.0, 0.1, 0.0, 0.0, ref="r1")
    pe.reset("a1")
    assert pe.snapshot("a1", "XAUUSD").direction == "flat"
    assert pe.snapshot("a2", "XAUUSD").direction == "long"


def test_two_symbols_same_account_are_isolated():
    pe = PositionEngine()
    pe.on_fill("a1", "XAUUSD", "buy", "entry", 2000.0, 0.1, 0.0, 0.0, ref="r1")
    pe.on_fill("a1", "WTIUSD", "sell", "entry", 70.0, 1.0, 0.0, 0.0, ref="r2")
    xau = pe.snapshot("a1", "XAUUSD")
    wti = pe.snapshot("a1", "WTIUSD")
    assert xau.direction == "long"
    assert wti.direction == "short"


def test_on_fill_never_raises_returns_error_action():
    pe = PositionEngine()
    # quantity=None -> `cur_signed + signed_qty` raises TypeError internally;
    # on_fill() must catch it and degrade to an error action, never propagate.
    r = pe.on_fill("a1", "XAUUSD", "buy", "entry", 2000.0, None, 0.0, 0.0)
    assert r["action"] == "error"


def test_rebuild_from_history_reconstructs_state(broker_paths):
    from engine.broker import broker_history as bh
    from engine.broker.contract import Fill
    from engine.broker import order_state as ost
    from engine.broker.position_engine import ENGINE

    o1 = ost.new_order("c1", "acct-x", "XAUUSD", "buy", "market", 2000.0, 0.1, ref="ref1")
    bh.record_order_transition(o1)
    bh.record_fill(Fill(fill_id="f1", order_id=o1.order_id, account_id="acct-x", symbol="XAUUSD",
                        side="buy", leg="entry", price=2000.0, quantity=0.1, fee=0.0,
                        execution_cost=0.05, is_partial=False, ts="2026-01-01T00:00:00+00:00"))
    o2 = ost.new_order("c2", "acct-x", "XAUUSD", "sell", "market", 2010.0, 0.1, ref="ref1")
    bh.record_order_transition(o2)
    bh.record_fill(Fill(fill_id="f2", order_id=o2.order_id, account_id="acct-x", symbol="XAUUSD",
                        side="sell", leg="exit", price=2010.0, quantity=0.1, fee=0.0,
                        execution_cost=0.05, is_partial=False, ts="2026-01-01T01:00:00+00:00"))

    ENGINE.reset()
    ENGINE.rebuild_from_history("acct-x")
    snap = ENGINE.snapshot("acct-x", "XAUUSD")
    assert snap.direction == "flat"
    assert abs(snap.realized_pnl - (10.0 * 0.1 * 100.0)) < 1e-6


def test_rebuild_from_history_never_raises_on_missing_files(broker_paths):
    from engine.broker.position_engine import ENGINE
    ENGINE.reset()
    ENGINE.rebuild_from_history("no-such-account")   # no files exist yet
    snap = ENGINE.snapshot("no-such-account", "XAUUSD")
    assert snap.direction == "flat"
