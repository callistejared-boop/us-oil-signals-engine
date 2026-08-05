"""Day 13 — shared pytest fixtures.

The first `conftest.py` in this codebase's test suite. Every prior Day's
file-backed history module (`macro_history.py`, `execution_history.py`,
etc.) has exactly ONE JSONL path to monkeypatch, so each test file just
did it inline (`monkeypatch.setattr(mod, "HISTORY_PATH", tmp_path / ...)`).
`engine/broker/broker_history.py` has FOUR (`ORDERS_PATH`/`FILLS_PATH`/
`EVENTS_PATH`/`ACCOUNTS_PATH`), and roughly a dozen Day 13 test files need
all four patched identically — inlining that four-line block a dozen
times would be pure duplication with no offsetting clarity benefit, so
this one shared fixture replaces it. Every other Day's inline-patching
convention is otherwise unchanged; this is additive, not a rewrite.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


@pytest.fixture
def broker_paths(tmp_path, monkeypatch):
    """Monkeypatches every `engine.broker.broker_history` JSONL path to an
    isolated tmp_path, and resets the two in-memory singletons
    (`position_engine.ENGINE`, `account.REGISTRY`) so tests never leak
    state into each other. Returns the `broker_history` module for
    convenience. Also clears `alert_signals._BROKER_CACHE` so a test that
    imports `alert_signals` doesn't reuse a `PaperBroker` built against a
    different tmp_path from an earlier test."""
    from engine.broker import broker_history as bh
    from engine.broker import position_engine as pos_mod
    from engine.broker import account as acct_mod

    monkeypatch.setattr(bh, "ORDERS_PATH", tmp_path / "broker_orders.jsonl")
    monkeypatch.setattr(bh, "FILLS_PATH", tmp_path / "broker_fills.jsonl")
    monkeypatch.setattr(bh, "EVENTS_PATH", tmp_path / "broker_events.jsonl")
    monkeypatch.setattr(bh, "ACCOUNTS_PATH", tmp_path / "broker_accounts.jsonl")
    pos_mod.ENGINE.reset()
    acct_mod.REGISTRY.reset()
    try:
        import alert_signals as als
        als._BROKER_CACHE.clear()
    except Exception:  # noqa: BLE001
        pass
    return bh


@pytest.fixture
def data_health_paths(tmp_path, monkeypatch):
    """Day 14 — isolates every `engine.data_health` file path to a tmp_path
    so tests never read/write the real repo root's cache files or history
    logs. `freshness.ROOT`/`feed_monitor.ROOT` are re-read on every call
    (not baked into a precomputed path at import time), so patching the
    module attribute is sufficient for those; the two module-level history
    paths computed once at import time (`heartbeat.HEARTBEAT_HISTORY`,
    `heartbeat.DASHBOARD_PUBLISH_HEARTBEAT`, `feed_monitor.DATA_HEALTH_HISTORY`)
    are patched directly."""
    from engine.data_health import freshness as fr, heartbeat as hb, feed_monitor as fm

    monkeypatch.setattr(fr, "ROOT", tmp_path)
    monkeypatch.setattr(fr, "OBSERVATIONS_PATH", tmp_path / "data_health_observations.jsonl")
    monkeypatch.setattr(hb, "HEARTBEAT_HISTORY", tmp_path / "data_health_heartbeat_history.jsonl")
    monkeypatch.setattr(hb, "DASHBOARD_PUBLISH_HEARTBEAT", tmp_path / "dashboard_publish_heartbeat.json")
    monkeypatch.setattr(fm, "ROOT", tmp_path)
    monkeypatch.setattr(fm, "DATA_HEALTH_HISTORY", tmp_path / "data_health_history.jsonl")
    return {"freshness": fr, "heartbeat": hb, "feed_monitor": fm, "tmp_path": tmp_path}


@pytest.fixture
def registry_sandbox():
    """Snapshots `engine.data_health.registry`'s module-level registry dict
    before a test and restores it afterward, so a test that registers a
    custom/fake FeedSpec (for dependency-cascade or validation testing)
    never leaks that registration into a later test."""
    from engine.data_health import registry as reg
    original = dict(reg._REGISTRY)
    yield reg
    reg._REGISTRY.clear()
    reg._REGISTRY.update(original)
