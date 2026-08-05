# Day 15 — Git Repository Health Audit

Covers mandate Objective 4. Nothing was committed or pushed as part of
this audit — findings and a recommended commit plan only, per this
platform's standing practice of treating commit/push as consequential
actions the platform owner directs. Staging (`git add`, fully reversible
via `git reset`, never pushes anything) was exercised during this audit
to verify the plan below is mechanically correct, then reset back to a
clean, unstaged working tree before finishing.

## 1. Current state

`git status --porcelain` at the start of this Day: 23 modified files, 185
untracked files, 209 total. `git log` shows only 2 real commits
(`514b032` Initial commit, `25aba7a` Update generated dashboard artifacts,
both 2026-08-01) plus 4 automated `fundamentals-daily` state commits made
by the bot since — meaning **essentially all of Days 3-14's work (every
new engine module, every test file, every specification and Day-closing
report, R&V Cycle #2's eight documents) has been sitting uncommitted in
the working tree since it was written.** This predates Day 15 and wasn't
caused by anything this Day did — it's a genuine, real gap this audit
exists to close.

## 2. The biggest finding: two categories of file were never wired into any workflow's commit step

Direct audit of every `git add` line across all 6 workflow files (cross-
referenced against every `.jsonl`/`.json` file the engine actually
writes) found 15 files that `alert_signals.py`'s own logging calls
create on every scan, but that no workflow ever adds to git — meaning
they've been silently discarded on every single ephemeral GitHub Actions
runner, independent of the market-data issue (Objective 1) or the
phantom-position issue (see DAY15_PIPELINE_TRACE_AND_TRADE_ID_
VALIDATION.md): `regime_history.jsonl`, `confluence_history.jsonl`,
`confidence_history.jsonl`, `decision_audit.jsonl`, `macro_history.
jsonl`, `execution_history.jsonl`, `broker_orders.jsonl`, `broker_fills.
jsonl`, `broker_events.jsonl`, `broker_accounts.jsonl`, `data_health_
history.jsonl`, `data_health_heartbeat_history.jsonl`, `data_health_
observations.jsonl`, `experiment_registry.jsonl`, `correlation_cache.
json`. **This is fixed as of this Day** — `entry-scan.yml`'s persist step
now adds all 15 (see DAY15_IMPLEMENTATION_REPORT.md). This finding
belongs in this report because it IS a git-hygiene issue at its root:
"generated artifacts not accidentally versioned" cuts both ways — these
weren't being *accidentally* versioned, they were being *accidentally
un-versioned* despite being exactly the kind of durable research state
that should survive.

Their CURRENT on-disk content, however, is local sandbox test output
(from this and prior Days' development work), not real production data.
**Recommendation: do not commit these 15 files' present content.** Once
the workflow fix above ships and a real scan runs, the first genuine
commit will seed them correctly. Committing today's synthetic/test
content would permanently mix fabricated data into what should be a
clean evidence trail.

## 3. .gitignore — audited, one gap found and not yet fixed

Checked every currently-untracked file against `.gitignore` and against
each workflow's own `git add` list (Sec.2's method, applied to the
non-history files too). Result: `.gitignore` correctly excludes
`__pycache__/`, `.pytest_cache/`, `.cache/`, `.env`, `*.json.bak`,
`*.json.tmp`, `*_result.txt`, `*.log`, and several named scratch files
(`hb_check.txt`, `last_briefing.txt`, `task_audit_output.txt`,
`unregister_output.txt`, `alert_heartbeat.txt`) — verified via `git
status --ignored` that a full set of local scratch/debug files from
Days 3-14 sessions (`battery_result.txt`, `live_result.txt`, `overview_
result.txt`, five `sched*_result.txt` files, `verify_result.txt`, `wti_
hourly.log`, `trades.json.bak`) are all correctly caught by these
existing patterns. No gap found there.

**One real gap**: `.gitignore` has no rule for `correlation_cache.json`,
`data_health_*.jsonl`, or `experiment_registry.jsonl` specifically — they
were simply never committed AND never explicitly ignored, an ambiguous
state this Day's workflow fix resolves by making them intentionally
tracked (Sec.2), not by ignoring them. No `.gitignore` change is needed
as a result — noted here only so the ambiguity itself is documented as
resolved, one way, rather than left open.

## 4. Recommended commit structure

Files fall into clean, largely Day-shaped groups already, since this
platform's own convention has been one cohesive unit of work per Day.
Recommended sequence (oldest first, matching how the work actually
happened) — each `git add` list below was verified this Day via actual
staging + `git diff --cached --stat`, then unstaged again:

| # | Commit message | Contents |
|---|---|---|
| 1 | `Day 3: Portfolio risk gate + correlation engine` | `engine/portfolio_risk.py`, `engine/correlation_dynamic.py`, `DAY3_*.md`, related tests |
| 2 | `Day 4: Market Regime Engine` | `engine/regime_engine.py`, `engine/regime_history.py`, `DAY4_*.md`, related tests |
| 3 | `Day 5: Confluence contribution + adaptive weighting` | `engine/confluence_analysis.py`, `engine/confluence_history.py`, `engine/confluence_sandbox.py`, `DAY5_*.md`, `CONFLUENCE_SPECIFICATION.md`, related tests |
| 4 | `Day 6: Confidence Engine` | `engine/confidence_engine.py`, `engine/confidence_history.py`, `engine/confidence_calibration.py`, `DAY6_*.md`, `CONFIDENCE_ENGINE_SPECIFICATION.md`, related tests |
| 5 | `Day 7: Market Memory + unified trade ID` | `engine/market_memory.py`, `DAY7_*.md`, `MARKET_MEMORY_SPECIFICATION.md`, related tests |
| 6 | `Day 8: Explainability & Decision Audit` | `engine/explainability_engine.py`, `engine/decision_audit_history.py`, `engine/post_trade_review.py`, `DAY8_*.md`, `EXPLAINABILITY_SPECIFICATION.md`, related tests |
| 7 | `Day 9: Research & Validation Framework` | `engine/research_stats.py`, `engine/evidence_tiers.py`, `engine/experiment_registry.py`, `engine/edge_decay_monitor.py`, `engine/edge_investigation.py`, `engine/research_dashboard.py`, `DAY9_*.md`, `RESEARCH_VALIDATION_SPECIFICATION.md`, related tests |
| 8 | `Day 10: Experiment #0001 investigation` | `PERFORMANCE_INVESTIGATION_0001.md`, `DAY10_*.md`, related tests |
| 9 | `Day 11: Macro Intelligence Engine` | `engine/macro_*.py`, `engine/rates_feed.py`, `DAY11_*.md`, `MACRO_ENGINE_SPECIFICATION.md`, related tests |
| 10 | `Day 12: Execution Simulator` | `engine/execution/`, `DAY12_*.md`, `EXECUTION_SIMULATOR_SPECIFICATION.md`, related tests |
| 11 | `Day 13: Broker Abstraction Layer + Paper Broker` | `engine/broker/`, `DAY13_*.md`, `BROKER_ABSTRACTION_SPECIFICATION.md`, `PAPER_BROKER_SPECIFICATION.md`, `EXECUTION_API_DOCUMENTATION.md`, related tests |
| 12 | `Day 14: Data Quality & Feed Health Monitoring` | `engine/data_health/`, `DAY14_*.md`, `DATA_HEALTH_SPECIFICATION.md`, `FEED_REGISTRY_SPECIFICATION.md`, `OPERATIONAL_GUIDE.md`, related tests |
| 13 | `Research & Validation Cycle #2` | `RESEARCH_VALIDATION_CYCLE_2_*.md`, `STRATEGY_*.md`, `SCALPING_ENGINE_DESIGN.md`, `ARCHITECTURE_AND_TEST_SUITE_REVIEW.md`, `TECHNICAL_DEBT_REGISTER.md`, `PERFORMANCE_BENCHMARK_REPORT.md`, `VERSION_2.2_ROADMAP.md` |
| 14 | `Day 15: Operational recovery — heartbeat + evidence-persistence fixes` | `alert_signals.py`, `heartbeat_watchdog.py`, `.github/workflows/entry-scan.yml`, `.github/workflows/heartbeat-watchdog.yml`, `tests/test_alert_signals_scan_status.py`, `tests/test_heartbeat_watchdog.py`, `DAY15_*.md` |
| 15 | `Cross-cutting fixes and doc updates` | `hourly_briefing.py` (risk_guard wiring, resolved before this cycle), `command_center.html`, `news_bias.html`, `4_SEND_SIGNAL_NOW.bat`, `START_HERE.bat`, `run_hourly_silent.bat`, `README.md`, `PROJECT_SUMMARY_AND_ROADMAP.md`, `PLATFORM_MASTER_SUMMARY.md`, `TESTING_GUIDE.md`, `DEVELOPER_GUIDE.md`, `audit_05_testing_and_debt.md` — files that don't cleanly attribute to one Day |

Verified today that groups 1-12 and 15 correctly separate along file
boundaries with no overlap (each `engine/`, test, and doc file maps to
exactly one Day) — the exact `git add` argument lists were exercised
directly and are ready to run, not just estimated.

**Not recommended for this pass**: committing `fundamentals.json`,
`news_state.json`, or `run_ledger.jsonl` in their current form — their
"modified" status reflects incidental local-sandbox test-run drift, not
meaningful work. Recommend `git checkout -- fundamentals.json news_state.
json run_ledger.jsonl` to discard that drift and let the real workflows
resync them on the next live run, rather than folding sandbox-test noise
into permanent history.

## 5. What this audit did NOT do

Did not run `git commit` or `git push`. Committing 227 files across 15
commits and pushing them to a public GitHub repository is a bigger,
less-reversible action than the fixes elsewhere in this Day, and this
platform's standing practice treats that class of action as the platform
owner's to direct. The plan above is fully specified and mechanically
verified (every file list was staged and checked this Day) — ready to
execute in one sitting whenever given the go-ahead, either by the
platform owner directly or by asking this assistant to run it.
