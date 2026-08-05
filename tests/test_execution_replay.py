"""Offline tests for engine/execution/replay.py (Day 12) — the mandate's
explicit "reproducible historical replay under configurable assumptions"
requirement. All tests pass an explicit `rows=` list (this codebase's
standing offline-testing convention) so nothing here touches the real
trades.json.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.execution import replay as rp  # noqa: E402

ROWS = [
    {"id": "XAUUSD-1", "symbol": "XAUUSD", "direction": "long", "entry": 2350.0,
     "stop": 2340.0, "target": 2380.0, "status": "win", "result_r": 3.0,
     "opened": "2026-07-20 08:00:00"},
    {"id": "XAUUSD-2", "symbol": "XAUUSD", "direction": "short", "entry": 2360.0,
     "stop": 2370.0, "target": 2330.0, "status": "loss", "result_r": -1.0,
     "opened": "2026-07-21 13:00:00"},
    {"id": "WTIUSD-1", "symbol": "WTIUSD", "direction": "long", "entry": 78.0,
     "stop": 77.0, "target": 81.0, "status": "win", "result_r": 2.5,
     "opened": "2026-07-22 02:00:00"},
    {"id": "XAUUSD-3", "symbol": "XAUUSD", "direction": "long", "entry": 2400.0,
     "stop": 2390.0, "target": None, "status": "open", "result_r": 0.0,
     "opened": "2026-07-23 09:00:00"},
]


def test_approx_exit_price_long_win():
    price = rp._approx_exit_price(2350.0, 2340.0, "long", 3.0)
    assert price == 2350.0 + 10.0 * 3.0


def test_approx_exit_price_short_loss():
    price = rp._approx_exit_price(2360.0, 2370.0, "short", -1.0)
    assert price == 2360.0 - 10.0 * -1.0


def test_approx_exit_price_never_raises_on_bad_input():
    assert rp._approx_exit_price("bad", 2340.0, "long", 3.0) == "bad"


def test_run_replay_reproducible_same_seed():
    out1 = rp.run_replay(rows=ROWS, profile="typical", seed=42)
    out2 = rp.run_replay(rows=ROWS, profile="typical", seed=42)
    assert out1["reports"] == out2["reports"]
    assert out1["score_distribution"] == out2["score_distribution"]


def test_run_replay_different_seeds_can_differ():
    out1 = rp.run_replay(rows=ROWS, profile="typical", seed=1)
    out2 = rp.run_replay(rows=ROWS, profile="typical", seed=2)
    # at least one entry price should differ across seeds
    assert any(a["actual_entry"] != b["actual_entry"]
              for a, b in zip(out1["reports"], out2["reports"]))


def test_run_replay_filters_by_symbol():
    out = rp.run_replay(rows=ROWS, symbol="WTIUSD", profile="typical", seed=1)
    assert out["n_trades_replayed"] == 1
    assert all(r["symbol"] == "WTIUSD" for r in out["reports"])


def test_run_replay_skips_open_trades_exit_but_still_simulates_entry():
    out = rp.run_replay(rows=ROWS, symbol="XAUUSD", profile="typical", seed=1)
    open_trade = [r for r in out["reports"] if r["trade_status"] == "open"]
    assert len(open_trade) == 1
    assert open_trade[0]["expected_exit"] is None
    assert open_trade[0]["entry_filled"] is True


def test_run_replay_named_example_wti_london_typical():
    """The mandate's own worked example: WTI, London session, typical
    spread/slippage/latency."""
    out = rp.run_replay(rows=ROWS, symbol="WTIUSD", session="London KZ",
                        profile="typical", seed=42)
    assert out["n_trades_replayed"] == 1
    assert out["profile_assumptions"] == rp.PROFILES["typical"]
    assert out["session_override"] == "London KZ"


def test_run_replay_zero_liquidity_profile_fails_every_trade():
    out = rp.run_replay(rows=ROWS, profile="zero_liquidity", seed=1)
    assert out["score_distribution"]["Failed"] == out["n_trades_replayed"]


def test_run_replay_unknown_profile_falls_back_to_typical():
    out = rp.run_replay(rows=ROWS, profile="not_a_real_profile", seed=1)
    assert out["profile_assumptions"] == rp.PROFILES["typical"]


def test_run_replay_stored_result_r_carried_through():
    out = rp.run_replay(rows=[ROWS[0]], profile="typical", seed=1)
    assert out["reports"][0]["stored_result_r"] == 3.0


def test_run_replay_empty_rows_returns_valid_empty_report():
    out = rp.run_replay(rows=[], profile="typical", seed=1)
    assert out["n_trades_replayed"] == 0
    assert out["reports"] == []
    assert out["reproducible"] is True


def test_run_replay_never_raises_on_malformed_row():
    bad_rows = [{"symbol": "XAUUSD"}]  # missing entry/stop
    out = rp.run_replay(rows=bad_rows, profile="typical", seed=1)
    assert out["n_trades_replayed"] == 0


def test_run_replay_never_raises_on_completely_broken_row():
    bad_rows = [{"entry": "not-a-number", "stop": "also-bad", "symbol": "XAUUSD",
                "direction": "long", "opened": "not-a-date"}]
    out = rp.run_replay(rows=bad_rows, profile="typical", seed=1)
    assert isinstance(out["reports"], list)


def test_run_replay_avg_cost_r_is_mean_of_reported_cost_r():
    out = rp.run_replay(rows=ROWS[:3], profile="typical", seed=1)
    cost_rs = [r["cost_r"] for r in out["reports"] if r.get("cost_r") is not None]
    assert out["avg_cost_r"] == round(sum(cost_rs) / len(cost_rs), 6)


def test_all_profiles_are_valid_and_runnable():
    for name in rp.PROFILES:
        out = rp.run_replay(rows=ROWS[:1], profile=name, seed=1)
        assert out["profile"] == name
        assert out["n_trades_replayed"] == 1
