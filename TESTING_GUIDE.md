# Testing Guide: Broker Abstraction Layer (Day 13)

## Running the Day 13 suite

```bash
python -m pytest -q tests/test_broker_contract.py tests/test_broker_order_state.py \
  tests/test_broker_events.py tests/test_broker_history.py \
  tests/test_broker_position_engine.py tests/test_broker_account.py \
  tests/test_paper_broker.py tests/test_replay_broker.py \
  tests/test_research_bridge.py tests/test_journal_broker.py \
  tests/test_alert_signals_broker.py tests/test_dashboard_publish.py
```

For the FULL platform regression suite, see the batching convention in
DAY13_VALIDATION_REPORT.md (the same `pytest -n 4` + file-splitting
workaround every prior Day's validation report documents).

## The `broker_paths` fixture (`tests/conftest.py`)

This is the first `conftest.py` in this codebase's test suite. Every
prior Day's file-backed history module had exactly one JSONL path to
monkeypatch; `broker_history.py` has four
(`ORDERS_PATH`/`FILLS_PATH`/`EVENTS_PATH`/`ACCOUNTS_PATH`), and a dozen
Day 13 test files need all four patched identically. Rather than
inlining that four-line block a dozen times, one shared fixture does it:

```python
def test_something(broker_paths):
    # broker_paths IS the broker_history module, with all 4 paths
    # already pointed at an isolated tmp_path, and both singletons
    # (position_engine.ENGINE, account.REGISTRY) already reset.
    ...
```

Any test that touches `PaperBroker`, `replay_broker`, `research_bridge`,
or `broker_history` directly should take `broker_paths` as a fixture
argument — this guarantees test isolation (no leaking state between
tests via the shared singletons or a shared on-disk file).

## Test file map

| File | Tests | Covers |
|---|---|---|
| `tests/test_broker_contract.py` | 11 | Enums, dataclass shapes, frozen-ness, ABC-ness |
| `tests/test_broker_order_state.py` | 11 | Every valid/invalid transition, immutability |
| `tests/test_broker_events.py` | 7 | Event taxonomy, emit/tail/for_ref, fail-safe persistence |
| `tests/test_broker_history.py` | 17 | All 4 JSONL stores, rotation, cross-store joins |
| `tests/test_broker_position_engine.py` | 18 | open/increase/reduce/close/flip math, margin, rebuild |
| `tests/test_broker_account.py` | 15 | Balances, margin, position sizing, rebuild |
| `tests/test_paper_broker.py` | 38 | The full `BrokerInterface` implementation — see below |
| `tests/test_replay_broker.py` | 12 | Reproducibility, isolation, profile-driven stress |
| `tests/test_research_bridge.py` | 6 | Evidence-source separation |
| `tests/test_journal_broker.py` | 5 | `broker_ref` field, unified-ID invariant |
| `tests/test_alert_signals_broker.py` | 12 | `alert_signals.py`'s integration points, mocked broker |
| `tests/test_dashboard_publish.py` (+3 new) | 3 | `paper_trading` payload key |
| **Total new** | **155** | |

## `test_paper_broker.py`'s scenario coverage (mapped to the mandate's testing list)

| Mandate item | Test(s) |
|---|---|
| Unit tests | Every `test_submit_*`/`test_close_*` etc. |
| Integration tests | `test_get_execution_reports_returns_merged_feed`, close+reconciliation tests |
| Concurrent order scenarios | `test_concurrent_orders_across_symbols_isolated`, `test_concurrent_orders_different_accounts_never_bleed` |
| Partial fills | `test_partial_fill_reduces_filled_quantity_and_status` |
| Cancellations | `test_cancel_working_order`, `test_cancel_terminal_order_is_noop`, `test_cancel_unknown_order_returns_none` |
| Rejected orders | `test_submit_order_rejects_*` (3 variants) |
| Account reconciliation | `test_account_reconciliation_matches_after_process_restart` |
| Replay consistency | `tests/test_replay_broker.py::test_run_broker_replay_reproducible_same_seed` |
| Recovery from simulated failures | `test_failure_injection_*` (4 variants) + `test_market_stress_*` (3 variants) + `test_failure_injection_recovery_retry_with_same_client_id_after_condition_clears` |

## Adding a new test

1. If it touches `broker_history`/`PaperBroker`/`replay_broker`/
   `research_bridge`, take `broker_paths` as a fixture argument.
2. Follow the existing "never raises" testing pattern: for any new
   fail-safe code path, assert the DEGRADED return value, don't assert
   `pytest.raises(...)` unless you're specifically testing
   `order_state.InvalidTransition` (the one exception this package
   intentionally lets propagate, by design — see `order_state.py`'s
   docstring).
3. Use `SimpleNamespace` to stub a fake `PaperBroker`/`Order` in
   `alert_signals.py`-level tests (see `test_alert_signals_broker.py`)
   rather than constructing a real `PaperBroker` — keeps those tests
   fast and focused on the integration glue, not the broker's own
   internal logic (which `test_paper_broker.py` already covers).

---

# Testing Guide addendum: Data Quality & Feed Health Monitoring (Day 14)

## Running the Day 14 suite

```bash
python -m pytest -q tests/test_data_health_registry.py \
  tests/test_data_health_freshness.py tests/test_data_health_completeness.py \
  tests/test_data_health_consistency.py tests/test_data_health_anomaly.py \
  tests/test_data_health_provider_status.py tests/test_data_health_health_report.py \
  tests/test_data_health_heartbeat.py tests/test_data_health_feed_monitor.py \
  tests/test_alert_signals_data_health.py tests/test_dashboard_publish.py
```

## The `data_health_paths` and `registry_sandbox` fixtures (`tests/conftest.py`)

Two new fixtures, added alongside Day 13's `broker_paths`:

- **`data_health_paths(tmp_path, monkeypatch)`** — isolates every file
  path this package touches (`freshness.ROOT`/`OBSERVATIONS_PATH`,
  `heartbeat.HEARTBEAT_HISTORY`/`DASHBOARD_PUBLISH_HEARTBEAT`,
  `feed_monitor.ROOT`/`DATA_HEALTH_HISTORY`) to a tmp_path. Required by
  any test that calls `freshness.age_minutes_from_*`,
  `heartbeat.record_beat`/`current_status`, or `feed_monitor.
  run_health_check`/`dashboard_snapshot` — omitting it will read/write
  the REAL repo root's cache and history files (this was found and
  fixed once already during this Day's own testing — see the
  Implementation Report's "Bug found" section).
- **`registry_sandbox()`** — snapshots and restores
  `engine.data_health.registry`'s module-level registry dict, so a test
  that registers a custom/fake `FeedSpec` (for dependency-cascade or
  validation testing) never leaks into a later test. Call
  `registry_sandbox.reset()` first if the test wants a clean registry
  rather than the real 18-feed default.

## `feed_monitor.py`'s scenario coverage (mapped to the mandate's testing list)

| Mandate item | Test(s) |
|---|---|
| Missing feeds | `test_run_health_check_missing_feed_reports_unavailable_or_degraded_never_crashes` |
| Delayed feeds | `test_run_health_check_delayed_feed_reports_worse_than_fresh` |
| Malformed data | `test_run_health_check_malformed_market_cache_reports_critical` |
| Duplicate updates | `test_run_health_check_duplicate_timestamps_detected` |
| Frozen prices | `test_run_health_check_frozen_price_detected` |
| Dependency failures | `test_run_health_check_dependency_failure_cascades`, `test_apply_dependency_cascade_*` (provider_status) |
| Restart recovery | `test_run_health_check_recovery_detected_across_two_runs` (re-derives previous status from persisted history, not in-process memory) |
| Registry validation | `test_validate_registry_*` (5 variants: hidden dependency, missing provider/purpose, circular dependency) |
| Regression testing | Full-suite batched run, 1,353/1,353 — see `DAY14_VALIDATION_REPORT.md` |

## Adding a new test

1. If it touches any `engine.data_health` module that does file I/O,
   take `data_health_paths` as a fixture argument.
2. If it registers a custom `FeedSpec`, take `registry_sandbox` and call
   `registry_sandbox.reset()` first if you want a clean slate rather
   than the real default registry.
3. Follow the same "never raises" pattern as every other Day: assert
   the degraded/fallback return shape, not `pytest.raises(...)` — every
   public function in this package is fail-safe by design.
4. Remember the `persist` split in `feed_monitor.run_health_check()`:
   a test asserting something got WRITTEN to `data_health_history.jsonl`
   or `data_health_heartbeat_history.jsonl` needs `persist=True`
   (the default); a test asserting a dashboard read does NOT pollute
   history should call `dashboard_snapshot()` (which is `persist=False`)
   and assert the file does not exist.
