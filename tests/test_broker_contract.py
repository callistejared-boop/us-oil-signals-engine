"""Offline tests for engine/broker/contract.py (Day 13)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from engine.broker import contract as ct  # noqa: E402


def test_order_side_values():
    assert ct.OrderSide.BUY == "buy"
    assert ct.OrderSide.SELL == "sell"
    assert set(ct.OrderSide.ALL) == {"buy", "sell"}


def test_order_type_values():
    assert set(ct.OrderType.ALL) == {"market", "limit", "stop"}


def test_time_in_force_values():
    assert set(ct.TimeInForce.ALL) == {"gtc", "ioc", "day"}


def test_order_request_defaults():
    req = ct.OrderRequest(client_order_id="c1", account_id="a1", symbol="XAUUSD",
                          side=ct.OrderSide.BUY, order_type=ct.OrderType.MARKET,
                          intended_price=2000.0)
    assert req.quantity is None
    assert req.time_in_force == ct.TimeInForce.GTC
    assert req.ref == ""
    assert req.simulate_failure is None


def test_order_request_is_frozen():
    req = ct.OrderRequest(client_order_id="c1", account_id="a1", symbol="XAUUSD",
                          side=ct.OrderSide.BUY, order_type=ct.OrderType.MARKET,
                          intended_price=2000.0)
    with pytest.raises(Exception):
        req.symbol = "WTIUSD"


def test_fill_is_frozen_and_estimate_flagged():
    fill = ct.Fill(fill_id="f1", order_id="o1", account_id="a1", symbol="XAUUSD",
                   side="buy", leg="entry", price=2000.0, quantity=0.1, fee=0.0,
                   execution_cost=0.05, is_partial=False, ts="2026-01-01T00:00:00")
    assert fill.is_estimate is True
    assert fill.source == "engine.broker.paper_broker"
    with pytest.raises(Exception):
        fill.price = 2001.0


def test_position_snapshot_default_open_refs_empty():
    snap = ct.PositionSnapshot(account_id="a1", symbol="XAUUSD", direction="flat",
                               quantity=0.0, avg_entry=None, realized_pnl=0.0,
                               unrealized_pnl=0.0, fees_paid=0.0, execution_costs=0.0,
                               risk_utilization=None)
    assert snap.open_refs == ()


def test_account_snapshot_shape():
    snap = ct.AccountSnapshot(account_id="a1", currency="USD", starting_capital=10000.0,
                              balance=10000.0, equity=10000.0, margin_used=0.0,
                              buying_power=300000.0, leverage=30.0, open_position_count=0)
    assert snap.currency == "USD"
    assert snap.open_position_count == 0


def test_now_iso_returns_iso_string_with_timezone():
    ts = ct.now_iso()
    assert "T" in ts
    assert ts.endswith("+00:00")


def test_broker_interface_is_abstract():
    with pytest.raises(TypeError):
        ct.BrokerInterface()


def test_contract_version_declared():
    assert ct.CONTRACT_VERSION == "1.0.0"
    assert ct.BrokerInterface.contract_version == ct.CONTRACT_VERSION
