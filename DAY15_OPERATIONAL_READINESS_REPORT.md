# Day 15 — Operational Readiness Report

Covers mandate Objective 5. Answers each question directly, with the
evidence behind each answer and what — if anything — still blocks it.

## Can the platform scan automatically?

**Yes, mechanically — confirmed directly, not assumed.** Fetched the
repo's live GitHub Actions run history (public repo, no auth needed):
`entry-scan.yml` has run 48 times, on its `*/15 * * * *` schedule, most
recently today (2026-08-05, run started 11:14 UTC, ~1h43m before this
check), each completing in ~1m-1m23s and reporting **Status Success**.
The other five workflows (fundamentals-daily, gold-btc-hourly, heartbeat-
watchdog, news-refresh, wti-hourly) show the same pattern — all running
on schedule. The scheduler, secrets access, and GitHub Actions
infrastructure are not the problem.

**But "Success" was misleading.** `alert_signals.py`'s own fail-safe
design means a total market-data-fetch failure never raises — it logs
"ERROR yfinance empty for ..." per symbol and completes normally, so the
workflow step (previously wrapped in `continue-on-error: true` besides)
reports green regardless. Reproduced this exact failure signature
locally this Day (see DAY15_IMPLEMENTATION_REPORT.md Sec.2) when run
without a working data source. Combined with `trades.json`/`pending.
json`/`run_ledger.jsonl` showing zero commits since 2026-07-23/24 despite
~1,000+ "successful" runs since, the leading hypothesis is a sustained
market-data fetch failure (most likely `TWELVEDATA_API_KEY` invalid/
exhausted, falling back to yfinance, which frequently blocks GitHub
Actions' shared IPs) — evidenced but not certain, since step-level logs
require repo sign-in this environment doesn't have. **Fixed this Day**:
a total-outage scan now exits non-zero (visible as a failed run in the
Actions UI) instead of silently succeeding, so this will be directly
observable going forward regardless of which specific cause it turns out
to be.

## Can it generate paper trades?

**Yes, mechanically confirmed** — a controlled local trace (synthetic
price data, real unmodified pipeline code, full details in DAY15_
PIPELINE_TRACE_AND_TRADE_ID_VALIDATION.md) produced a real "ENTRY"
event, a new `trades.json` row, a Paper Broker order, and every
downstream advisory record, in one run. The *code* is not broken.

**Two things currently prevent it from happening for real, independently
of each other:**

1. The market-data fetch issue above — the primary blocker.
2. **Newly found this Day**: `trades.json` currently contains three
   duplicate, still-open BTCUSD long positions (identical ID
   `BTCUSD-2026-07-17T13:15:00`, opened 2026-07-17, never closed) and
   `pending.json` holds one stale, three-week-old unresolved XAUUSD
   setup. `portfolio_risk.py` counts open positions by direction with
   no ID deduplication, so those three duplicate rows alone occupy 3 of
   the platform's long-side exposure slots (configured max: 2) —
   **any new long-direction trade, on any symbol, is likely to be
   blocked by the portfolio risk gate right now, even after #1 is
   fixed**, until a human reviews and cleans up those specific rows.
   Not auto-fixed this Day: editing the trade journal's historical
   record is a data-correctness decision for the platform owner, not
   something to change unilaterally while fixing an unrelated
   observability bug. **Recommended action**: review those 3 duplicate
   BTCUSD rows and the stale XAUUSD pending setup, and either close/
   remove them or confirm they reflect real, intentional open positions
   before the next live scan.

## Can it persist those trades?

**Yes, for the fields it's always persisted** (`trades.json`, `pending.
json`, `run_ledger.jsonl` — committed by every relevant workflow's
persist step, verified against every workflow file). **No, until this
Day, for almost everything else**: 15 history/audit files that Days
4-14's own logging calls write on every scan (regime, confluence,
confidence, decision-audit, macro, execution, all 4 broker stores, all 3
data-health stores, the experiment registry, correlation cache) were
never in ANY workflow's `git add` list — meaning the entire advisory
research/evidence layer this platform's mandate has spent 11 Days
building has likely never survived a single ephemeral GitHub Actions
runner in production. **Fixed this Day** — see DAY15_GIT_HYGIENE_REPORT.
md Sec.2 and DAY15_IMPLEMENTATION_REPORT.md.

## Can it reconstruct state after restart?

**Yes — this remains the platform's best-evidenced reliability claim.**
`engine.broker`'s `rebuild_from_history()` was benchmarked at 17ms
(`PERFORMANCE_BENCHMARK_REPORT.md` Sec.4, Research & Validation Cycle
#2) and is exercised by Day 13's own dedicated replay-compatibility test
suite. Not re-benchmarked this Day (no code changed in that path) —
cited as still-current evidence, not re-verified from scratch.

## Can it populate the unified evidence chain?

**Yes — confirmed directly this Day, reversing Research & Validation
Cycle #2's headline finding.** The clean-state trace run (DAY15_
PIPELINE_TRACE_AND_TRADE_ID_VALIDATION.md) produced a trade row with all
six `*_ref` fields populated and matching, and independently confirmed
the same ID present across eight separate history stores. Cycle #2 found
these fields completely absent on all 102 real trades and treated it as
an unresolved wiring gap; this Day's evidence says the wiring works —
the real trades simply predate this code path ever successfully firing
in production (the scan loop had already gone quiet before it could).
**Practical implication**: once the market-data issue and the phantom-
position issue are both resolved, the very next real trade should
populate the full chain correctly with no further code changes needed.

## Summary table

| Question | Answer | Blocker(s) remaining |
|---|---|---|
| Scans automatically? | Yes (scheduler/infra confirmed) | Suspected market-data fetch failure (Objective 1) — now observable, not yet confirmed root-caused end-to-end |
| Generates paper trades? | Yes (code confirmed working) | #1 above, plus phantom duplicate positions blocking portfolio risk |
| Persists trades? | Yes (core fields) / now yes (research layer, as of this Day's fix) | None — fixed |
| Reconstructs state after restart? | Yes | None — previously validated, unchanged |
| Populates the unified evidence chain? | Yes (confirmed this Day) | None on the code side — needs #1 and the phantom-position cleanup to see it on a real trade |

## Absence of trades explained by system state, not market conditions

Per the mandate's own success criterion: the 12+ day absence of new
trades is **not** attributable to quiet markets — Gold, WTI, Bitcoin,
and EUR/USD do not go 12 consecutive days without a single qualifying
15-minute setup across 4 symbols under this platform's own historical
trade frequency (102 trades in a comparable prior window). It is
attributable to the two system-level blockers documented above, both
with direct evidence, neither a market-conditions explanation.
