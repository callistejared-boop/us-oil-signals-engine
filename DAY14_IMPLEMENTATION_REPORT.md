# Day 14 Implementation Report — Data Quality & Feed Health Monitoring Framework

Full specifications: `DATA_HEALTH_SPECIFICATION.md`,
`FEED_REGISTRY_SPECIFICATION.md`, `OPERATIONAL_GUIDE.md`.

## New files

- `engine/data_health/__init__.py` — package docstring, governing
  principle (observe/validate/classify/report/recommend, never fetch,
  never gate), naming disambiguation against the pre-existing
  `engine/freshness.py`.
- `engine/data_health/registry.py` — `FeedSpec` dataclass +
  `register()`/`get()`/`all_feeds()`/`dependents_of()`/
  `dependency_chain()`/`validate_registry()`. 18 default feed
  registrations covering every real data source this platform has.
- `engine/data_health/freshness.py` — 5-state (Fresh/Aging/Stale/
  Expired/Unknown) classifier, `age_minutes_from_mtime`/
  `age_minutes_from_json_field`/`age_minutes_from_observation`,
  `record_observation()`/`last_observation()` (the one place in the
  package that records anything about a live call, and only as an
  observation of a call made elsewhere).
- `engine/data_health/completeness.py` — `check_dict()`/
  `check_dataframe()`, 4-tier severity (none/minor/major/critical),
  `worst_severity()` reducer.
- `engine/data_health/consistency.py` — `check_ohlc()`,
  `check_duplicate_timestamps()`, `check_conflicting_sources()`,
  `check_symbol_metadata()`.
- `engine/data_health/anomaly.py` — `check_frozen_price()`,
  `check_price_jump()` (z-score), `check_timeline_gaps()`. Explicitly
  disclosed as operational statistics, not predictive modeling.
- `engine/data_health/provider_status.py` — `classify()` (4-state
  Operational/Degraded/Partial/Unavailable + confidence + recommended
  action), `apply_dependency_cascade()`, `affected_subsystems()`.
- `engine/data_health/heartbeat.py` — reuses `heartbeat_watchdog.
  heartbeat_age_minutes()` directly. `current_status()` (read-only) /
  `record_beat()` (persists) split. Tracks scheduler execution,
  dashboard-publish age, journal-persistence age, plus caller-supplied
  processing latency / queue depth.
- `engine/data_health/health_report.py` — `build_report()`: assembles
  every module's output into one report (overall status, per-provider
  detail, dependency map, degraded-or-worse list, registry validation,
  heartbeat, recent history).
- `engine/data_health/feed_monitor.py` — the coordinator:
  `run_health_check(persist=True|False)`, `dashboard_snapshot()`,
  `history_tail()`. Failure-philosophy event persistence
  (`data_health_history.jsonl`: run_summary/provider_issue/recovery).
- `tests/test_data_health_registry.py`,
  `tests/test_data_health_freshness.py`,
  `tests/test_data_health_completeness.py`,
  `tests/test_data_health_consistency.py`,
  `tests/test_data_health_anomaly.py`,
  `tests/test_data_health_provider_status.py`,
  `tests/test_data_health_health_report.py`,
  `tests/test_data_health_heartbeat.py`,
  `tests/test_data_health_feed_monitor.py`,
  `tests/test_alert_signals_data_health.py` — 10 new test files, 144
  tests.
- `DATA_HEALTH_SPECIFICATION.md`, `FEED_REGISTRY_SPECIFICATION.md`,
  `OPERATIONAL_GUIDE.md` — full documentation set.

## Modified files

- `alert_signals.py` — added `from engine.data_health import
  feed_monitor as dh_monitor, freshness as dh_freshness` import; added
  `time` import (for scan-duration timing); added `_scan_start =
  time.monotonic()` at the top of `main()`; added a `record_observation`
  call for the `news_calendar` feed immediately after the pre-existing
  `news_state = news_guard.evaluate()` line; added
  `log_data_health(settings, elapsed_seconds, symbol_count)` (called once
  per scan, after the per-symbol loop completes, immediately before the
  `alert_heartbeat.txt` write) and appended its one-line summary
  (`data health: <status> (<counts>)`) to the same `log` list the
  heartbeat file already carries.
- `engine/dashboard_publish.py` — added `from engine.data_health import
  feed_monitor as dhfm` import; added a `"data_health"` payload key
  (`_safe_note(lambda: dhfm.dashboard_snapshot(), "Data Health")`) next
  to `"paper_trading"` in `build_payload()`; added a
  `dashboard_publish_heartbeat.json` write (`published_at` +
  `symbols_published`) to `main()`, only when at least one symbol
  actually published.
- `tests/conftest.py` — added `data_health_paths` fixture (isolates
  every file path this package touches) and `registry_sandbox` fixture
  (snapshots/restores the module-level feed registry), alongside Day
  13's `broker_paths`.
- `tests/test_dashboard_publish.py` — 5 new tests appended for the
  `"data_health"` payload key and the publish-heartbeat write (existing
  18 tests unchanged).
- `ARCHITECTURE_SPECIFICATION.md` — new §24.
- `PROJECT_SUMMARY_AND_ROADMAP.md` — new "Day 14" section.
- `TESTING_GUIDE.md` — new Day 14 addendum section.

**No other file was touched.** `engine/confluence.py`,
`engine/confidence_engine.py`, `engine/bias_adjust.py`,
`engine/risk_guard.py`, `engine/signals.py`, `engine/portfolio_risk.py`,
`engine/regime_engine.py`, and every prior Day's gating/scoring module
are byte-for-byte unchanged from the end of Day 13 — grep-verified (see
Validation Report).

## Explicit decisions made (documented, not silently resolved)

1. **Read vs. write separation in the coordinator
   (`run_health_check(persist=True|False)`).** NOT in the original
   design — added mid-Day after direct testing showed the obvious naive
   design (one function that always both computes AND persists a
   research record) would inflate `data_health_history.jsonl` and
   `data_health_heartbeat_history.jsonl` every time `dashboard_publish.py`
   rendered a symbol's page (which happens multiple times per scan,
   once per configured symbol) — a dashboard read is not a scan. See
   the Bug section below.
2. **Quality checks (completeness/consistency/anomaly) only run against
   feeds this package can cheaply inspect on disk.** Market-data
   pickles get the full treatment (OHLC validity, duplicate timestamps,
   frozen-price/jump/gap detection); JSON-cache-backed macro/
   infrastructure feeds get a generic non-empty-payload check, not
   per-field schema validation for each individual feed's internal
   shape — disclosed as a backlog item in the specification, not
   silently assumed complete.
3. **REFERENCE (curated) and COMPUTED (pure calculation) feeds are
   treated as always-current for the health-status floor**, distinct
   from their freshness *label* which still reports "reference_data"/
   "computed" rather than a fabricated "fresh" — an operator reading
   the report sees the real distinction even though the status
   classifier doesn't penalize either kind for lacking a decay clock.
4. **Only one real dependency edge exists in the registry today**
   (`macro_calendar` -> `news_calendar`), reflecting Day 11's
   single-abstraction-layer design (no provider function calls another
   provider's underlying feed module). The dependency-cascade machinery
   is fully general and tested against synthetic multi-hop graphs
   (`registry_sandbox`-based tests), ready for more edges as this
   platform's data sourcing grows.
5. **`timeout_threshold_seconds` per feed is a disclosed estimate, not
   live-measured.** This package does no fetching of its own to
   instrument; adding real per-call timing would require touching each
   source module's own fetch function, out of scope for an advisory
   layer whose stated purpose is not to fetch.
6. **`news_calendar` and `fundamentals_feed` are handled differently**
   despite both being "news" category: `fundamentals_feed` writes a real
   cache file (`fundamentals.json`) so it gets a `file_mtime` probe like
   any macro feed; `news_guard`'s calendar has no persisted cache at all
   (a fresh live fetch every call, by design — see `news_guard.py`'s own
   docstring), so it uses the `observed` probe mechanism instead — the
   one place this package records anything about a live call, and only
   as an observation of alert_signals.py's own pre-existing call.

## Bug found and fixed during this Day's own work

**A dashboard page load would have silently inflated the heartbeat and
research history on every render.** While smoke-testing the full
pipeline (running the new Day 14 + Day 13 test suites together), several
pre-existing `test_dashboard_publish.py` tests that call
`build_payload()` without mocking the new `"data_health"` key started
writing REAL files at the repo root (`data_health_history.jsonl`,
`data_health_heartbeat_history.jsonl`) even though those tests use no
Day 14 fixture at all. Root cause: the first draft of
`feed_monitor.dashboard_snapshot()` called the same `run_health_check()`
used by `alert_signals.py`'s once-per-scan check, and that function
unconditionally wrote a heartbeat record and a `run_summary` event on
every call — meaning every dashboard render (called once per symbol,
several times per scan) counted as a "beat," which would have corrupted
the heartbeat history's meaning (it's supposed to answer "how healthy
was each actual scan," not "how many times was the dashboard opened").

Fixed by splitting `heartbeat.py`'s single `record_beat()` into a
read-only `current_status()` (used by both) and a persisting
`record_beat()` (which calls `current_status()` then appends), and
adding a `persist: bool = True` parameter to
`feed_monitor.run_health_check()` — `alert_signals.py`'s
`log_data_health()` uses the default `persist=True`;
`dashboard_snapshot()` explicitly passes `persist=False`. Verified via
`tests/test_data_health_feed_monitor.py::test_dashboard_snapshot_never_
writes_history_or_heartbeat` and
`test_run_health_check_persist_false_report_shape_matches_persist_true`
(same report shape, only persistence differs), plus a repo-cleanliness
re-check confirming no repeat stray files after the full suite reruns.

A second, smaller mistake was caught during the same refactor: the
initial edit renamed one function's body but left its `def` line still
reading `def record_beat(...)`, silently shadowing the intended
`current_status` definition — Python simply kept only the second
definition, so every call to the (nonexistent) `current_status()` from
inside the real `record_beat()` raised a `NameError`, caught by the
function's own `except Exception` and masked as a generic "failed"
error dict. Found immediately by the new tests
(`test_record_beat_persists_and_returns_row`,
`test_tail_returns_recent_records`) failing with a `KeyError` on a field
that should always be present; fixed by renaming the first function's
`def` line to `current_status`.

## Testing

149 new offline tests, zero live-network dependency:

| File | Tests |
|---|---|
| `tests/test_data_health_registry.py` | 15 |
| `tests/test_data_health_freshness.py` | 22 |
| `tests/test_data_health_completeness.py` | 16 |
| `tests/test_data_health_consistency.py` | 19 |
| `tests/test_data_health_anomaly.py` | 14 |
| `tests/test_data_health_provider_status.py` | 16 |
| `tests/test_data_health_health_report.py` | 8 |
| `tests/test_data_health_heartbeat.py` | 13 |
| `tests/test_data_health_feed_monitor.py` | 16 |
| `tests/test_alert_signals_data_health.py` | 5 |
| `tests/test_dashboard_publish.py` (+5 new) | 5 |
| **Total new** | **149** |

## What was explicitly NOT touched

- `engine/confluence.py`, `engine/confidence_engine.py`,
  `engine/bias_adjust.py`, `engine/risk_guard.py`, `engine/signals.py`,
  `engine/portfolio_risk.py`, `engine/regime_engine.py` — zero changes.
- `engine/freshness.py` (the pre-existing day-granularity banner) —
  zero changes; a new, separate, explicitly disambiguated module was
  added instead of modifying or replacing it.
- Every underlying data-source module this Day audits
  (`engine/rates_feed.py`, `engine/risk_sentiment.py`,
  `engine/correlation_dynamic.py`, `engine/cot_feed.py`,
  `engine/eia_feed.py`, `engine/spread_feed.py`,
  `engine/macro_reference.py`, `engine/seasonality.py`,
  `engine/news_guard.py`, `engine/macro_calendar.py`,
  `engine/fundamentals_feed.py`, `engine/markets.py`) — zero changes.
  This package reads their already-written cache files; it does not
  modify how any of them fetch or cache data.
- `heartbeat_watchdog.py` and `.github/workflows/heartbeat-watchdog.yml`
  — zero changes; `heartbeat_age_minutes()` is imported and reused
  exactly as-is, its own Telegram-DM alerting behavior is untouched.
- `trades.json` — zero changes; this package only reads its mtime for
  the `journal_persistence` feed's freshness check.
- No threshold, confidence score, confluence score, macro label, or
  gating decision changed as a result of this Day's work.
