# Day 15 — Operational Recovery & Production Pipeline Validation
## Implementation Report

Unlike Days 3-14 and Research & Validation Cycle #2, this Day's mandate
explicitly called for restoring the evidence pipeline rather than adding
new strategy logic — the work below is diagnostic and corrective, not
new features. Companion documents: DAY15_PIPELINE_TRACE_AND_TRADE_ID_
VALIDATION.md (Objectives 2-3), DAY15_GIT_HYGIENE_REPORT.md (Objective
4), DAY15_OPERATIONAL_READINESS_REPORT.md (Objective 5), DAY15_
VALIDATION_REPORT.md (test/regression evidence), DAY15_NEXT_DAY_
READINESS_REPORT.md (what's next).

## 1. Diagnosis — why the heartbeat hasn't updated in 11+ days

Investigated with real evidence, not assumption, in this order:

1. **Confirmed the scheduler and infrastructure are not the problem.**
   Fetched the repo's live GitHub Actions run history directly (public
   repo). All 6 workflows are running on their configured cron
   schedules, `entry-scan.yml` most recently today, every run reporting
   "Status Success."
2. **Found the actual root cause of the observability gap**: `alert_
   heartbeat.txt` — the file `heartbeat_watchdog.py` was designed to
   read — is (correctly) `.gitignore`d, and `entry-scan.yml`'s persist
   step never added it even if it weren't. `heartbeat-watchdog.yml` runs
   on its own fresh `actions/checkout@v4` every 30 minutes, so it could
   never see a file that only ever existed on a different, already-
   destroyed ephemeral runner. `heartbeat_watchdog.py`'s own "no file ->
   not launched yet, don't alert" fail-safe design meant this looked
   like "healthy, nothing to check" indefinitely, rather than raising
   any signal.
3. **Reproduced the likely reason the scans themselves aren't producing
   trades.** Ran `alert_signals.py` locally (sandbox network egress to
   Yahoo/TwelveData is blocked here, simulating a total data-fetch
   failure) and got the exact log signature — "ERROR yfinance empty for
   ..." per symbol — with the script completing normally (exit 0, no
   crash). Cross-referenced against git history: `trades.json`/`pending.
   json`/`run_ledger.jsonl` show zero commits since 2026-07-23/24 despite
   ~1,000+ "successful" workflow runs since, while a *different* workflow
   (`fundamentals-daily.yml`, using a different data source/secret) has
   committed successfully every day through today — isolating the
   suspect to the market-data fetch path specifically (most plausibly
   `TWELVEDATA_API_KEY`, with the yfinance fallback also failing — a
   well-known behavior for GitHub Actions' shared IP ranges against
   Yahoo Finance). **Not confirmed with certainty** — GitHub hides
   step-level logs from unauthenticated viewers, so the exact secret/API
   state inside the real runs couldn't be inspected directly. This
   remains the leading, evidence-backed hypothesis, not a proven fact,
   and is stated as such throughout these Day 15 documents.

## 2. Code changes

### `alert_signals.py`
- Added per-symbol fetch-outcome tracking (`scan_symbol_status`) —
  distinguishes "this symbol's data fetch failed" from any other,
  unrelated downstream exception.
- Added `write_scan_status()` — writes a small, structured record to
  `.cache/heartbeat_status.json` every scan: timestamp, per-symbol
  outcome, and a `total_data_outage` flag. `.cache/` is the SAME
  directory `entry-scan.yml` already round-trips across ephemeral
  runners via `actions/cache` (previously only for market-data caching)
  — this rides an existing, already-working mechanism rather than
  inventing a new one. Never raises internally (same fail-safe
  discipline as the rest of the file).
- `main()` now raises once, at the very end (after the dashboard-publish
  attempt), if `total_data_outage` is true — making a total outage show
  up as a failed GitHub Actions run instead of a silently-successful one.
  Partial failures (one symbol down, others fine) are unaffected — that
  graceful degradation was already correct and is unchanged.

### `heartbeat_watchdog.py`
- New primary check (`scan_status()`): reads `.cache/heartbeat_status.
  json` first, falls back to the legacy `alert_heartbeat.txt` for local/
  manual runs. The original `heartbeat_age_minutes(path)` function is
  kept, unchanged in behavior, specifically so it and the tests that
  already exercised it directly continue to work exactly as before.
- `main()` now alerts (one Telegram DM, same quiet-by-default discipline
  as before) on two distinct conditions: legacy staleness (unchanged),
  and a NEW condition — a fresh-but-`total_data_outage` scan, which
  would otherwise look "healthy" by staleness alone while producing
  nothing usable.
- Docstrings corrected — they previously claimed `alert_heartbeat.txt`
  "is committed by entry-scan.yml every ~15 min," which was never true;
  now describe the actual, working mechanism.

### `.github/workflows/entry-scan.yml`
- Removed `continue-on-error: true` from the scan step — a total-outage
  exception (above) now surfaces as a failed step/job. The persist step
  (`if: always()`) still runs regardless, so partial state is never lost.
- Persist step now also commits 15 files that were being written every
  run and silently discarded (see Sec.3) — `regime_history.jsonl`,
  `confluence_history.jsonl`, `confidence_history.jsonl`, `decision_
  audit.jsonl`, `macro_history.jsonl`, `execution_history.jsonl`,
  `broker_orders.jsonl`, `broker_fills.jsonl`, `broker_events.jsonl`,
  `broker_accounts.jsonl`, `data_health_history.jsonl`, `data_health_
  heartbeat_history.jsonl`, `data_health_observations.jsonl`,
  `experiment_registry.jsonl`, `correlation_cache.json`.

### `.github/workflows/heartbeat-watchdog.yml`
- Added a cache-restore step (`actions/cache/restore@v4`, same key
  prefix as `entry-scan.yml`'s cache) so this workflow can actually see
  the status file the scan job wrote. Deliberately restore-only — this
  workflow never writes state, so it must never save a cache entry
  itself (would create noise/races against the scan job's own cache).

## 3. The second, larger finding — the evidence layer was never persisted at all

Independent of the heartbeat/observability fix and independent of the
market-data question: a direct audit of every workflow's `git add` list
against every file `alert_signals.py`'s logging calls actually write
found 15 files (listed above) that no workflow has EVER committed. Since
`entry-scan.yml` is the job that calls all of Days 4-14's history-writing
functions, this means the platform's entire advisory research/audit
trail — regime history, confluence explainability, confidence
calibration history, macro context, execution reports, every Paper
Broker store, every decision-audit snapshot, all of Data Health's own
history, the experiment registry — has very likely never survived a
single ephemeral GitHub Actions runner in production, regardless of
whether trades were flowing. Fixed as part of the same workflow edit
above. Full detail in DAY15_GIT_HYGIENE_REPORT.md Sec.2.

## 4. Trade-ID chain — validated, not repaired

A controlled local trace (synthetic price data driving the real,
unmodified pipeline code — full methodology and results in DAY15_
PIPELINE_TRACE_AND_TRADE_ID_VALIDATION.md) produced a trade with all six
`*_ref` fields populated and matching across eight independent history
stores. **No code changes were needed here** — the wiring already works.
This revises Research & Validation Cycle #2's headline finding (which
found the fields entirely absent on all 102 real trades and treated it
as a broken join): the more likely explanation is that the ref-
population code was finished after the scan loop had already stopped
producing usable trades, so it has simply never fired on a real one yet.

## 5. A third finding, surfaced but deliberately not auto-fixed

The same trace investigation found `trades.json` currently holds three
duplicate, still-open BTCUSD long positions (identical ID, opened
2026-07-17, never closed) which alone occupy 3 of the platform's 2-slot
long-side portfolio exposure cap — meaning new long trades are likely to
be blocked by `portfolio_risk.py` even once the market-data issue is
fixed. This was NOT corrected as part of this Day: editing the trade
journal's historical record is a data-correctness decision for the
platform owner, not something to change unilaterally while fixing an
unrelated pipeline-observability bug. See DAY15_OPERATIONAL_READINESS_
REPORT.md for the specific recommended action.

## 6. What this Day did NOT do

- Did not modify `trades.json` or `pending.json`'s real content (Sec.5).
- Did not commit or push anything to the real git history (DAY15_GIT_
  HYGIENE_REPORT.md Sec.5) — staging was exercised and verified, then
  reset to a clean working tree.
- Did not add any Strategy Framework / Scalping Engine code — per the
  mandate's own framing, that's Day 16-17's work, gated on this Day's
  operational fixes actually landing in production first.
- Did not modify `engine/confluence.py`'s behavior to fix the "confluence
  did not complete" observation from the trace — logged as a disclosed
  limitation of the synthetic trace data, not a confirmed platform
  defect (DAY15_PIPELINE_TRACE_AND_TRADE_ID_VALIDATION.md).
