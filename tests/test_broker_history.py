"""Offline tests for engine/broker/broker_history.py (Day 13)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.broker import broker_history as bh  # noqa: E402
from engine.broker import order_state as ost  # noqa: E402
from engine.broker.contract import Fill, AccountSnapshot  # noqa: E402


def _order():
    return ost.new_order("c1", "acct1", "XAUUSD", "buy", "market", 2000.0, 0.1, ref="ref1")


def test_record_order_transition_and_read_back(broker_paths):
    o = _order()
    bh.record_order_transition(o, reason="created")
    rows = bh.orders_for(o.order_id)
    assert len(rows) == 1
    assert rows[0]["status"] == "created"


def test_orders_for_reconstructs_full_transition_history(broker_paths):
    o = _order()
    bh.record_order_transition(o)
    o = ost.transition(o, ost.OrderStatus.ACCEPTED)
    bh.record_order_transition(o)
    o = ost.transition(o, ost.OrderStatus.WORKING)
    bh.record_order_transition(o)
    rows = bh.orders_for(o.order_id)
    assert [r["status"] for r in rows] == ["created", "accepted", "working"]


def test_latest_order_row_returns_most_recent(broker_paths):
    o = _order()
    bh.record_order_transition(o)
    o = ost.transition(o, ost.OrderStatus.ACCEPTED)
    bh.record_order_transition(o)
    latest = bh.latest_order_row(o.order_id)
    assert latest["status"] == "accepted"


def test_find_order_by_client_id_matches_created_row_only(broker_paths):
    o = _order()
    bh.record_order_transition(o)
    o2 = ost.transition(o, ost.OrderStatus.ACCEPTED)
    bh.record_order_transition(o2)
    found = bh.find_order_by_client_id("acct1", "c1")
    assert found is not None
    assert found["status"] == "created"
    assert found["order_id"] == o.order_id


def test_find_order_by_client_id_scoped_to_account(broker_paths):
    o = _order()
    bh.record_order_transition(o)
    assert bh.find_order_by_client_id("other-acct", "c1") is None


def test_find_order_by_client_id_empty_string_returns_none(broker_paths):
    assert bh.find_order_by_client_id("acct1", "") is None


def _fill(order_id="ord-1", leg="entry", account_id="acct1", symbol="XAUUSD"):
    return Fill(fill_id="fill-1", order_id=order_id, account_id=account_id, symbol=symbol,
               side="buy", leg=leg, price=2000.0, quantity=0.1, fee=0.0,
               execution_cost=0.05, is_partial=False, ts="2026-01-01T00:00:00+00:00")


def test_record_fill_and_fills_for_order(broker_paths):
    bh.record_fill(_fill())
    rows = bh.fills_for_order("ord-1")
    assert len(rows) == 1
    assert rows[0]["price"] == 2000.0


def test_fills_tail_filters_by_symbol_and_account(broker_paths):
    bh.record_fill(_fill(order_id="o1", symbol="XAUUSD"))
    bh.record_fill(_fill(order_id="o2", symbol="WTIUSD"))
    rows = bh.fills_tail(n=10, account_id="acct1", symbol="XAUUSD")
    assert len(rows) == 1
    assert rows[0]["symbol"] == "XAUUSD"


def test_all_fills_and_all_orders_no_limit(broker_paths):
    for i in range(5):
        bh.record_fill(_fill(order_id=f"o{i}"))
    assert len(bh.all_fills("acct1")) == 5


def test_exit_fill_refs_for_symbol_joins_through_orders(broker_paths):
    o = ost.new_order("c1", "acct1", "XAUUSD", "sell", "market", 2010.0, 0.1, ref="trade-ref-1")
    bh.record_order_transition(o)
    bh.record_fill(_fill(order_id=o.order_id, leg="exit"))
    refs = bh.exit_fill_refs_for_symbol("XAUUSD", account_id="acct1")
    assert refs == {"trade-ref-1"}


def test_exit_fill_refs_ignores_entry_leg_fills(broker_paths):
    o = ost.new_order("c1", "acct1", "XAUUSD", "buy", "market", 2000.0, 0.1, ref="trade-ref-2")
    bh.record_order_transition(o)
    bh.record_fill(_fill(order_id=o.order_id, leg="entry"))
    refs = bh.exit_fill_refs_for_symbol("XAUUSD", account_id="acct1")
    assert refs == set()


def test_record_event_and_events_tail(broker_paths):
    bh.record_event("fill", "acct1", "XAUUSD", {"x": 1}, ref="r1")
    rows = bh.events_tail(n=5, account_id="acct1")
    assert len(rows) == 1
    assert rows[0]["payload"]["x"] == 1


def test_events_for_ref(broker_paths):
    bh.record_event("fill", "acct1", "XAUUSD", {}, ref="r1")
    bh.record_event("cancellation", "acct1", "XAUUSD", {}, ref="r2")
    assert len(bh.events_for_ref("r1")) == 1


def test_record_account_snapshot_and_equity_curve(broker_paths):
    snap = AccountSnapshot(account_id="acct1", currency="USD", starting_capital=10000.0,
                           balance=10050.0, equity=10060.0, margin_used=100.0,
                           buying_power=299000.0, leverage=30.0, open_position_count=1,
                           as_of="2026-01-01T00:00:00+00:00")
    bh.record_account_snapshot(snap)
    curve = bh.account_equity_curve("acct1")
    assert len(curve) == 1
    assert curve[0]["equity"] == 10060.0


def test_execution_reports_merges_orders_and_fills_time_ordered(broker_paths):
    o = _order()
    bh.record_order_transition(o)
    bh.record_fill(_fill(order_id=o.order_id))
    merged = bh.execution_reports("acct1", n=10)
    kinds = {r["kind"] for r in merged}
    assert kinds == {"order", "fill"}


def test_read_all_never_raises_on_missing_file(broker_paths):
    assert bh._read_all(bh.ORDERS_PATH) == []


def test_rotation_keeps_only_max_lines(broker_paths, monkeypatch):
    monkeypatch.setattr(bh, "MAX_LINES", 3)
    for i in range(6):
        bh.record_order_transition(_order())
    lines = bh.ORDERS_PATH.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
