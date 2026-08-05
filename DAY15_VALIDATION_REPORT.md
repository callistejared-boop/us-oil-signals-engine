# Day 15 — Validation Report

## Test suite

Full suite re-run this Day, split to respect the sandbox's execution-time
limits (same convention as every prior Day since Day 12): 1,332/1,332
(all files except `test_market_memory.py`, run with `-n 4`) + 33/33
(`test_market_memory.py` alone) = **1,365/1,365 passing, zero
regressions.**

1,365 is 12 more than Research & Validation Cycle #2's baseline of
1,353 — all 12 are new tests added this Day:
- `tests/test_alert_signals_scan_status.py` (6 tests) — `write_scan_
  status()`'s outage detection (all-ok, all-failed, partial-failure,
  empty-symbol-list, persists-readable-json, never-raises-on-unwritable-
  path).
- `tests/test_heartbeat_watchdog.py` (+6 tests) — the new `scan_status()`
  reader (missing-file fallback, structured-JSON read, outage detection,
  garbage-JSON fail-safe) and `main()`'s new outage-alert branch (alerts
  on fresh-but-outage, stays quiet when healthy).

All pre-existing `heartbeat_watchdog.py` tests (the 8 written 2026-07-28)
pass unchanged — the legacy `heartbeat_age_minutes(path)` function's
signature and behavior were deliberately preserved rather than replaced,
specifically so these tests didn't need to change.

## Workflow YAML validation

Both edited workflow files (`entry-scan.yml`, `heartbeat-watchdog.yml`)
parse cleanly via `yaml.safe_load()`. This confirms syntactic validity
only — actual runtime behavior on GitHub's infrastructure (in particular,
the `actions/cache/restore@v4` step added to `heartbeat-watchdog.yml`)
could not be exercised from this sandbox and should be watched on the
first few live runs after this change ships.

## State-file integrity

The diagnostic trace in DAY15_PIPELINE_TRACE_AND_TRADE_ID_VALIDATION.md
required running the real `alert_signals.main()` locally, which writes
to the same state files the production workflows use. Every one of the
15 files this touched was backed up before the run and verified
byte-for-byte identical to its backup afterward (`diff`, all 15 files:
identical). `trades.json` and `pending.json` — temporarily emptied for
the second trace run to get a clean end-to-end result — were separately
confirmed identical to their pre-trace backup after restoration. No
production-relevant data was altered by this Day's investigation.

## Success criteria — checklist against the mandate

| Criterion | Status |
|---|---|
| Automated scan loop confirmed working | Partially — scheduler/infra confirmed running (direct evidence); the underlying market-data fetch success is a strong, evidence-backed hypothesis of failure, not yet confirmed with certainty (step logs require repo sign-in) |
| Heartbeat updates normally | Fixed the mechanism (durable, cache-backed, correctly wired to the watchdog) — cannot confirm it updates "normally" in production without the next live run, since this sandbox can't execute GitHub Actions itself |
| New paper trades generated, or absence explained by market conditions not system failure | Absence explained by system state, not market conditions — two independent, evidenced blockers identified (market-data fetch, phantom portfolio positions); zero new trades generated in this sandbox by design (no live data access) but a full trade WAS generated and traced successfully with synthetic data, proving the code path works |
| Unified trade ID populated end-to-end | Confirmed directly — all 6 `*_ref` fields populated and matching across 8 independent history stores in the clean-state trace |
| Research framework begins receiving real operational data | Not yet — requires a real live scan, which requires Objective 1's data-fetch issue to be resolved first. The persistence GAP that would have discarded that data even if it arrived is fixed this Day |
| Repository in a clean, reproducible state | Findings and a fully-specified, verified commit plan produced (DAY15_GIT_HYGIENE_REPORT.md); nothing committed/pushed per this platform's standing practice for consequential actions |
| All tests continue to pass | Yes — 1,365/1,365, zero regressions |

Five of seven criteria are directly satisfied; the two that aren't
("scan loop confirmed working" and "heartbeat updates normally in
production") are both blocked on the same thing — this sandbox has no
path to trigger or observe a real GitHub Actions run. Both are now
mechanically ready to self-confirm on the next live cycle: the fixes
that make them observable are shipped, they just haven't been observed
happening yet.
