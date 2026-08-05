"""Offline tests for engine/broker/order_state.py (Day 13)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from engine.broker import order_state as ost  # noqa: E402
from engine.broker.order_state import OrderStatus  # noqa: E402


def _order():
    return ost.new_order("c1", "acct", "XAUUSD", "buy", "market", 2000.0, 0.1,
                         stop_price=1990.0, ref="ref1")


def test_new_order_starts_created():
    o = _order()
    assert o.status == OrderStatus.CREATED
    assert o.order_id.startswith("ord-")
    assert len(o.history) == 1
    assert o.history[0]["status"] == OrderStatus.CREATED


def test_new_order_has_unique_ids():
    a, b = _order(), _order()
    assert a.order_id != b.order_id


def test_valid_transition_chain():
    o = _order()
    o = ost.transition(o, OrderStatus.ACCEPTED, reason="accepted")
    assert o.status == OrderStatus.ACCEPTED
    o = ost.transition(o, OrderStatus.WORKING, reason="working")
    assert o.status == OrderStatus.WORKING
    o = ost.transition(o, OrderStatus.FILLED, reason="filled", filled_quantity=0.1)
    assert o.status == OrderStatus.FILLED
    assert o.filled_quantity == 0.1
    assert len(o.history) == 4


def test_transition_returns_new_object_not_mutated():
    o = _order()
    o2 = ost.transition(o, OrderStatus.ACCEPTED)
    assert o.status == OrderStatus.CREATED   # original untouched
    assert o2.status == OrderStatus.ACCEPTED
    assert o is not o2


def test_invalid_transition_raises_once_terminal():
    o = _order()
    o = ost.transition(o, OrderStatus.ACCEPTED)
    o = ost.transition(o, OrderStatus.WORKING)
    o = ost.transition(o, OrderStatus.FILLED)
    with pytest.raises(ost.InvalidTransition):
        ost.transition(o, OrderStatus.CANCELLED)


def test_cannot_transition_from_created_to_filled_directly():
    o = _order()
    with pytest.raises(ost.InvalidTransition):
        ost.transition(o, OrderStatus.FILLED)


def test_can_transition_helper():
    assert ost.can_transition(OrderStatus.CREATED, OrderStatus.ACCEPTED) is True
    assert ost.can_transition(OrderStatus.CREATED, OrderStatus.FILLED) is False


def test_is_terminal():
    assert ost.is_terminal(OrderStatus.FILLED) is True
    assert ost.is_terminal(OrderStatus.CANCELLED) is True
    assert ost.is_terminal(OrderStatus.REJECTED) is True
    assert ost.is_terminal(OrderStatus.EXPIRED) is True
    assert ost.is_terminal(OrderStatus.WORKING) is False
    assert ost.is_terminal(OrderStatus.CREATED) is False


def test_rejected_is_terminal_from_created():
    o = _order()
    o = ost.transition(o, OrderStatus.REJECTED, reason="no liquidity", reject_reason="no liquidity")
    assert o.status == OrderStatus.REJECTED
    assert o.reject_reason == "no liquidity"
    with pytest.raises(ost.InvalidTransition):
        ost.transition(o, OrderStatus.WORKING)


def test_partially_filled_can_still_reach_filled_or_cancelled():
    o = _order()
    o = ost.transition(o, OrderStatus.ACCEPTED)
    o = ost.transition(o, OrderStatus.WORKING)
    o = ost.transition(o, OrderStatus.PARTIALLY_FILLED, filled_quantity=0.05)
    assert ost.can_transition(o.status, OrderStatus.FILLED)
    assert ost.can_transition(o.status, OrderStatus.CANCELLED)
    assert ost.can_transition(o.status, OrderStatus.EXPIRED)
    assert not ost.can_transition(o.status, OrderStatus.REJECTED)


def test_all_terminal_statuses_have_no_outgoing_transitions():
    for status in OrderStatus.TERMINAL:
        assert ost.VALID_TRANSITIONS[status] == set()
