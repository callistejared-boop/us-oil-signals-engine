# Architecture & Test Suite Review — Research & Validation Cycle #2

Recommendations only. No code was changed as part of this document.
Builds on and reconciles against the original Day 1-2 audit
(`audit_05_testing_and_debt.md`, 311 tests / 58 engine modules at the
time) — every claim below either re-confirms, updates, or supersedes a
finding from that document with a fresh command run against the current
repo (88 engine modules, 23 root scripts, 1,353 tests).

## 1. What has genuinely improved since the original audit

Worth stating plainly, not just cataloguing new problems:

- **The `hourly_briefing.py` risk-guard bypass — the original audit's
  single most serious finding — has been fixed.** Re-confirmed this
  cycle: `hourly_briefing.py` now imports and calls `risk_guard.
  evaluate(sym)` directly, with its own docstring stating it runs "the
  SAME risk_guard + portfolio_risk path" as `alert_signals.py`. This is
  a genuine, verified resolution of the platform's most important
  historical technical-debt item.
- **Every subsequent Day (3-14) has shipped its own dedicated
  specification, validation report, and closing readiness report** —
  a documentation discipline the original audit's "clean module
  docstrings, but debt isn't tracked with markers" finding did not
  anticipate. Technical debt IS now tracked, explicitly, in every Day's
  own "Known limitations" / "Remaining risks" sections — just not
  consolidated into one register until this cycle (Sec. 5, this gap is
  addressed here).
- **Zero bare `except:` and zero un-reasoned `except Exception: pass`
  have been introduced across 30 new engine modules and ~40 new test
  files** (Days 3-14) — the project-wide fail-safe convention held.

## 2. What has NOT changed / is newly found

### 2.1 `4_SEND_SIGNAL_NOW.bat` still calls the (now-safer, but still
separate) `hourly_briefing.py` path

Re-confirmed this cycle. Lower severity than the original finding (the
bypass itself is fixed), but the platform still has two live entry
points (`alert_signals.py`, tested, 1,353-test-suite-covered;
`hourly_briefing.py`, zero direct test coverage per the original audit,
not re-verified this cycle) reachable from the main interactive menu.
**Recommendation, carried forward**: either retire `hourly_briefing.py`
and repoint the `.bat` menu, or give it the same test coverage
`alert_signals.py` has. Not urgent given the risk-guard fix, but still
a real duplication of the platform's most safety-critical code path.

### 2.2 Duplicate `class Trade` in `engine/backtest.py` and `engine/journal.py`

Re-confirmed unchanged. Still worth a one-time audit to confirm the two
representations haven't drifted to mean subtly different things — not
done as part of this review (recommendations only).

### 2.3 Caching-helper duplication has grown, not shrunk

The original audit found `_load_cache`/`read_cached`/`refresh`/`note`
duplicated across `cot_feed.py`, `eia_feed.py`, `risk_sentiment.py`,
`spread_feed.py`. Day 14's own Phase 1 audit (`DATA_HEALTH_
SPECIFICATION.md`, `FEED_REGISTRY_SPECIFICATION.md`) independently
re-confirmed this exact same pattern this cycle, plus found it ALSO in
`correlation_dynamic.py` and `rates_feed.py` — **six modules now**, each
independently implementing "fetch external feed, cache to
`{name}_cache.json`, fall back to stale cache on error." A shared
`engine/feed_cache.py` helper (`read_cached(path, max_age_hours)` /
`write_cached(path, payload)`) would collapse six near-identical
implementations into one, tested once. **This is now a stronger
recommendation than it was at the original audit**, given the pattern
has grown rather than been addressed, and Day 14's registry now has
programmatic visibility into exactly which six modules would benefit
(`registry.py`'s `probe_kind="file_mtime"` entries for
`rates_feed`/`risk_sentiment`/`correlation_dynamic`/`cot_feed`/
`eia_feed`/`spread_feed` are precisely this list).

### 2.4 NEW finding this cycle: the append-only JSONL pattern is reimplemented independently at least six times, and it has a real, measured performance cost

Every history module in this codebase (`engine/ledger.py`,
`engine/macro_history.py`, `engine/execution/execution_history.py`,
`engine/broker/broker_history.py` (four stores), `engine/decision_
audit_history.py`, `engine/experiment_registry.py`, `engine/data_
health/heartbeat.py`/`feed_monitor.py`) independently implements the
identical pattern: append one JSON line, then read the ENTIRE file back
into memory to check whether it exceeds `MAX_LINES` and needs rotating
— on every single write, not periodically.

**This was directly benchmarked this cycle** (`PERFORMANCE_BENCHMARK_
REPORT.md` Sec. 3): append cost grows with file size — 0.082ms/append
at 500 existing lines vs. 0.220ms/append at 2,000 existing lines, a
~2.7x slowdown purely from the file having grown, consistent with an
O(n) rotation-check cost paid on every append (making N appends
cumulatively O(n²), not O(n)). At today's trade volumes (102 trades
total, per `RESEARCH_VALIDATION_CYCLE_2_REPORT.md` Sec. 0) this is
immaterial. At `MAX_LINES` scale (most of these modules cap at
5,000-20,000 lines) it remains fast in absolute terms (low
milliseconds), so this is **not an urgent fix** — but it is a real,
now-measured architectural inefficiency, reimplemented independently
six-plus times instead of once, and worth consolidating into one
shared `engine/jsonl_store.py` helper (`append(path, rec, max_lines)`)
the next time any of these modules is touched, rather than as its own
dedicated effort.

### 2.5 Dashboard-script duplication — unchanged, not re-verified this cycle

The original audit's finding (`equity_svg`, `pct`, `pf_fmt`,
`session_of`, `conf_bucket` duplicated across `command_center.py`,
`performance_dashboard.py`, `self_review.py`, `weekly_audit.py`) was
not re-inspected this cycle (out of scope given time budget — flagged
as a gap in this review, not a claim it's resolved).

### 2.6 The "strategy" naming collision this cycle's own design work discovered

New finding, not from the original audit: `engine.market_memory.
performance_by_strategy_regime()`'s existing "strategy" parameter means
`config.regime_strategy` (an origination-method label like
"ict_smc_mast"), which will collide with `STRATEGY_FRAMEWORK_
SPECIFICATION.md`'s proposed `Trade.strategy` (swing/day/scalp) if both
are implemented without a rename. See `STRATEGY_RESEARCH_FRAMEWORK.md`
Sec. 6 for the recommended fix (rename to `origination_method`,
mechanical, no behavior change).

## 3. Test suite review

### 3.1 Suite size and health

1,353 tests (up from 311 at the original audit), 1,353/1,353 passing,
re-confirmed this cycle via the same `-n 4` + file-split batching
convention every Day's validation report has used since the bash tool's
45-second timeout first became a constraint (Day 12+).

### 3.2 Slow tests — directly measured this cycle

```
$ pytest -q --durations=8 tests/test_market_memory.py
17.72s  test_large_history_performance_analytics_completes
17.62s  test_large_history_find_similar_completes_and_is_correct
 0.93s  test_historical_context_never_raises_on_garbage
...
33 passed in 38.84s
```

**These two tests alone consume 91% of `test_market_memory.py`'s total
runtime, and this one file alone accounts for roughly a quarter of the
entire suite's wall-clock time** (38.84s of a full-suite run that
otherwise batches into 6 groups of 6-35s each). Both are legitimately
named performance/stress tests (large synthetic history, correctness +
completion-time assertions) — not slow by accident, slow by design.
**Recommendation**: mark both `@pytest.mark.slow` (a new marker, not
currently used anywhere in this suite — confirmed via `grep -rn
"pytest.mark" tests/` finding no existing marker convention to build
on) and exclude by default from the fast local-development loop
(`pytest -m "not slow"`), while keeping them in the full CI/validation
run every Day's closing report already does. This would speed up
day-to-day test iteration without losing any coverage.

```
$ pytest -q --durations=8 tests/test_dashboard_publish.py (subset)
6.30s  test_signal_basis_note_matches_symbol[BTCUSD]
5.93s  test_signal_basis_note_matches_symbol[XAUUSD]
2.25s  test_signal_basis_note_matches_symbol[WTIUSD]
```

These three parametrized tests predate Day 13/14's `paper_trading`/
`data_health` payload keys and do not mock either
`pbroker.dashboard_snapshot()` or `dhfm.dashboard_snapshot()` — each
real (unmocked) `build_payload()` call now pays the real cost of both
(a fresh `PaperBroker` construction plus a full `run_health_check()`,
~40ms + ~230ms per `PERFORMANCE_BENCHMARK_REPORT.md` Sec. 4, on top of
whatever else `build_payload()` already does). **Recommendation**: any
existing `test_dashboard_publish.py` test that constructs a real
`build_payload()` call without asserting on `paper_trading`/
`data_health` specifically should mock both, the same way the
dedicated `paper_trading`/`data_health` tests already do — this would
likely cut several seconds off this file's runtime with zero coverage
loss, since the slow tests aren't testing either of those two keys.

### 3.3 Flaky tests

One identified and directly reproduced this cycle (also documented in
`DAY14_VALIDATION_REPORT.md` Sec. 1):
`tests/test_paper_broker.py::test_market_stress_stale_price_still_
fills_with_wider_cost` failed once under `pytest -n 4` parallel
execution, passed 5/5 times in isolation, and passed on an immediate
parallel re-run. Consistent with Day 12's `fill_model`'s use of
unseeded `random` for this specific stress condition interacting with
`pytest-xdist` worker-process RNG state. **Recommendation**: give this
one stress-condition test (and any other `fill_model` test using
unseeded randomness for a probabilistic assertion, not yet audited
individually) an explicit seed, the same discipline every OTHER
stochastic test in this codebase already follows (Day 12's replay
tests, Day 13's broker replay tests, Day 9's Monte Carlo tests all use
fixed seeds) — this looks like the one place that discipline wasn't
applied, not a new problem to design around.

### 3.4 Duplicate coverage

Not exhaustively re-audited this cycle (311-test baseline's own
coverage map, Sec. 2 of the original audit, is 1,042 tests out of date
now) — flagged as a gap. One pattern worth naming: `engine.confluence`
has at least four dedicated "confluence survives layer offline"
resilience tests scattered across `test_candlestick_patterns.py`,
`test_gap2_modules.py`, `test_gap3_modules.py`, and others (visible in
this cycle's own `--durations` output, Sec. 3.2) — each testing the
identical "confluence degrades gracefully when one source errors"
property against a different individual source. This is arguably NOT
true duplication (each asserts a different source's specific failure
mode) but is worth a maintainer's eye to confirm the pattern is
intentional (one property, many sources) rather than accidental
copy-paste drift.

### 3.5 Missing edge cases

One concrete, evidence-backed gap found this cycle: no test in the
suite currently exercises `journal.make_ref()`'s minute-granularity
ID collision directly — the 5 duplicate IDs found in live `trades.json`
this cycle (`RESEARCH_VALIDATION_CYCLE_2_REPORT.md` Sec. 3.1) represent
a real, reproducible defect with no regression test guarding it. This
was flagged as backlog since Day 10 (`DAY10_NEXT_DAY_READINESS_
REPORT.md`) and remains both unfixed and untested.

## 4. Naming and structural consistency — reconciled

The original audit's core finding ("`engine/` = pure testable domain
logic, root scripts = I/O glue, with one repeated violation in the
dashboard-script cluster") still holds structurally for every module
added in Days 3-14 — every new `engine/` module added since (30 of
them) has a module docstring, is offline-testable, and has zero
network/Telegram side effects, confirmed by the same "no live-network
dependency" claim every Day's own validation report makes and this
cycle re-confirmed via the full suite's clean run with no network
mocking required.

## 5. This cycle's contribution: consolidating scattered debt into one register

Every prior Day's own "Known limitations"/"Remaining risks" section
already discloses that Day's own debt — nothing was hidden. What was
missing was ONE place a maintainer could scan across all of it at once,
prioritized. See `TECHNICAL_DEBT_REGISTER.md`, a new artifact this
cycle produces specifically to close that gap — every item in it traces
back to either this document, the original audit, or a specific prior
Day's own disclosed limitation, none invented fresh.
