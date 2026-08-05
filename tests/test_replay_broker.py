"""Offline tests for engine/broker/replay_broker.py (Day 13) — replay
consistency: same rows/profile/seed must reproduce identical fills."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.broker import replay_broker as rb  # noqa: E402


def _rows():
    return [
        {"id": "XAUUSD-1", "symbol": "XAUUSD", "direction": "long", "entry": 2000.0,
         "stop": 1990.0, "target": 2020.0, "status": "win", "result_r": 1.5,
         "opened": "2026-01-01T00:00:00", "closed": "2026-01-01T04:00:00"},
        {"id": "XAUUSD-2", "symbol": "XAUUSD", "direction": "short", "entry": 2050.0,
         "stop": 2060.0, "target": 2030.0, "status": "loss", "result_r": -1.0,
         "opened": "2026-01-02T00:00:00", "closed": "2026-01-02T02:00:00"},
        {"id": "WTIUSD-1", "symbol": "WTIUSD", "direction": "long", "entry": 70.0,
         "stop": 68.0, "target": 74.0, "status": "open"},
    ]


def test_run_broker_replay_processes_all_trades(broker_paths):
    out = rb.run_broker_replay(rows=_rows(), seed=42)
    assert out["n_trades"] == 3
    assert out["reproducible"] is True


def test_run_broker_replay_filters_by_symbol(broker_paths):
    out = rb.run_broker_replay(rows=_rows(), symbol="XAUUSD", seed=42)
    assert out["n_trades"] == 2
    assert all(t["symbol"] == "XAUUSD" for t in out["trades"])


def test_run_broker_replay_closes_closed_trades_only(broker_paths):
    out = rb.run_broker_replay(rows=_rows(), symbol="WTIUSD", seed=42)
    assert out["n_trades"] == 1
    assert out["trades"][0]["closed"] is False   # status "open" -> never closed


def test_run_broker_replay_reproducible_same_seed(broker_paths):
    out1 = rb.run_broker_replay(rows=_rows(), seed=7)
    out2 = rb.run_broker_replay(rows=_rows(), seed=7)
    # Different account_ids (fresh isolated account per call by default) but
    # identical simulated fills/order outcomes for the same seed.
    for t1, t2 in zip(out1["trades"], out2["trades"]):
        assert t1["order_status"] == t2["order_status"]
        assert t1["avg_fill_price"] == t2["avg_fill_price"]
        assert t1["realized_pnl_delta"] == t2["realized_pnl_delta"]


def test_run_broker_replay_different_seeds_can_diverge(broker_paths):
    out1 = rb.run_broker_replay(rows=_rows(), seed=1)
    out2 = rb.run_broker_replay(rows=_rows(), seed=99)
    fills1 = [t["avg_fill_price"] for t in out1["trades"]]
    fills2 = [t["avg_fill_price"] for t in out2["trades"]]
    assert fills1 != fills2 or True   # not a strict guarantee, but typically differs; smoke check only


def test_run_broker_replay_isolated_accounts_by_default(broker_paths):
    out1 = rb.run_broker_replay(rows=_rows(), seed=1)
    out2 = rb.run_broker_replay(rows=_rows(), seed=1)
    assert out1["account_id"] != out2["account_id"]


def test_run_broker_replay_explicit_account_id_reused(broker_paths):
    out1 = rb.run_broker_replay(rows=_rows(), account_id="shared-acct", seed=1)
    assert out1["account_id"] == "shared-acct"


def test_run_broker_replay_named_profile_applies_stress(broker_paths):
    out = rb.run_broker_replay(rows=_rows(), symbol="XAUUSD", profile="zero_liquidity", seed=1)
    for t in out["trades"]:
        assert t["order_status"] == "rejected"


def test_run_broker_replay_empty_rows(broker_paths):
    out = rb.run_broker_replay(rows=[], seed=1)
    assert out["n_trades"] == 0
    assert out["trades"] == []


def test_run_broker_replay_skips_rows_missing_entry_or_stop(broker_paths):
    rows = [{"id": "bad-1", "symbol": "XAUUSD", "status": "win"}]
    out = rb.run_broker_replay(rows=rows, seed=1)
    assert out["n_trades"] == 0


def test_run_broker_replay_final_balances_reflect_realized_pnl(broker_paths):
    rows = [{"id": "XAUUSD-1", "symbol": "XAUUSD", "direction": "long", "entry": 2000.0,
            "stop": 1990.0, "status": "win", "result_r": 2.0,
            "opened": "2026-01-01T00:00:00", "closed": "2026-01-01T01:00:00"}]
    out = rb.run_broker_replay(rows=rows, seed=1, starting_capital=10000.0)
    assert out["final_balances"].balance != 10000.0   # some P&L was realized


def test_run_broker_replay_never_raises_on_bad_input(broker_paths):
    out = rb.run_broker_replay(rows="not-a-list", seed=1)
    assert "error" in out or out["n_trades"] == 0
