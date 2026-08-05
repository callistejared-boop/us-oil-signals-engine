"""Offline tests for engine/broker/account.py (Day 13)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.broker.account import AccountRegistry, DEFAULT_STARTING_CAPITAL, DEFAULT_LEVERAGE  # noqa: E402


def test_get_or_create_uses_defaults():
    reg = AccountRegistry()
    acct = reg.get_or_create("a1")
    assert acct.starting_capital == DEFAULT_STARTING_CAPITAL
    assert acct.balance == DEFAULT_STARTING_CAPITAL
    assert acct.leverage == DEFAULT_LEVERAGE


def test_get_or_create_respects_overrides():
    reg = AccountRegistry()
    acct = reg.get_or_create("a1", starting_capital=5000.0, leverage=10.0, risk_pct=0.02)
    assert acct.starting_capital == 5000.0
    assert acct.leverage == 10.0
    assert acct.risk_pct == 0.02


def test_get_or_create_idempotent_same_account():
    reg = AccountRegistry()
    a = reg.get_or_create("a1", starting_capital=1234.0)
    b = reg.get_or_create("a1", starting_capital=9999.0)   # second call's overrides ignored
    assert a is b
    assert b.starting_capital == 1234.0


def test_get_returns_none_for_unknown():
    reg = AccountRegistry()
    assert reg.get("nope") is None


def test_apply_realized_pnl_updates_balance():
    reg = AccountRegistry()
    reg.get_or_create("a1", starting_capital=10000.0)
    reg.apply_realized_pnl("a1", 150.0, fee=5.0)
    acct = reg.get("a1")
    assert abs(acct.balance - 10145.0) < 1e-6


def test_reserve_and_release_margin():
    reg = AccountRegistry()
    reg.get_or_create("a1")
    reg.reserve_margin("a1", 500.0)
    assert reg.get("a1").margin_used == 500.0
    reg.release_margin("a1", 200.0)
    assert reg.get("a1").margin_used == 300.0


def test_release_margin_never_goes_negative():
    reg = AccountRegistry()
    reg.get_or_create("a1")
    reg.release_margin("a1", 100.0)
    assert reg.get("a1").margin_used == 0.0


def test_snapshot_computes_equity_and_buying_power():
    reg = AccountRegistry()
    reg.get_or_create("a1", starting_capital=10000.0, leverage=10.0)
    reg.reserve_margin("a1", 1000.0)
    snap = reg.snapshot("a1", unrealized_pnl_total=50.0, open_position_count=1)
    assert snap.balance == 10000.0
    assert snap.equity == 10050.0
    assert snap.margin_used == 1000.0
    assert abs(snap.buying_power - (10050.0 * 10.0 - 1000.0)) < 1e-6
    assert snap.open_position_count == 1


def test_position_size_uses_1pct_risk_convention():
    reg = AccountRegistry()
    reg.get_or_create("a1", starting_capital=10000.0, risk_pct=0.01)
    # XAUUSD mult=100 (engine.markets.MARKETS) -> risk=$100, dist=10 -> lots = 100/(10*100)=0.1
    lots = reg.position_size("a1", 2000.0, 1990.0, "XAUUSD")
    assert abs(lots - 0.1) < 1e-9


def test_position_size_zero_when_entry_equals_stop():
    reg = AccountRegistry()
    reg.get_or_create("a1")
    assert reg.position_size("a1", 2000.0, 2000.0, "XAUUSD") == 0.0


def test_position_size_scales_with_current_balance_not_starting_capital():
    reg = AccountRegistry()
    reg.get_or_create("a1", starting_capital=10000.0, risk_pct=0.01)
    reg.apply_realized_pnl("a1", 10000.0)   # balance now 20000
    lots = reg.position_size("a1", 2000.0, 1990.0, "XAUUSD")
    assert abs(lots - 0.2) < 1e-9   # doubled balance -> doubled size


def test_record_equity_point_persists(broker_paths):
    reg = AccountRegistry()
    reg.get_or_create("a1", starting_capital=10000.0)
    row = reg.record_equity_point("a1", unrealized_pnl_total=25.0, open_position_count=1)
    assert row["equity"] == 10025.0
    curve = broker_paths.account_equity_curve("a1")
    assert len(curve) == 1


def test_reset_clears_one_account_only():
    reg = AccountRegistry()
    reg.get_or_create("a1")
    reg.get_or_create("a2")
    reg.reset("a1")
    assert reg.get("a1") is None
    assert reg.get("a2") is not None


def test_rebuild_from_history_derives_balance_from_positions(broker_paths):
    from engine.broker.position_engine import ENGINE as pos_engine

    reg = AccountRegistry()
    reg.get_or_create("a1", starting_capital=10000.0, leverage=20.0)
    pos_engine.reset("a1")
    # on_fill(account_id, symbol, side, leg, price, quantity, fee, execution_cost, ref=...)
    pos_engine.on_fill("a1", "XAUUSD", "buy", "entry", 2000.0, 0.1, 1.0, 0.0, ref="r1")
    pos_engine.on_fill("a1", "XAUUSD", "sell", "exit", 2020.0, 0.1, 1.0, 0.0, ref="r1")   # +$200 realized, $2 fees total

    acct = reg.rebuild_from_history("a1")
    assert abs(acct.balance - (10000.0 + 200.0 - 2.0)) < 1e-6   # realized minus fees
    assert acct.margin_used == 0.0   # position is closed -> no margin held


def test_rebuild_from_history_never_raises():
    reg = AccountRegistry()
    acct = reg.rebuild_from_history("brand-new-account")
    assert acct.account_id == "brand-new-account"
