# Day 15 — Pipeline Execution Trace & Unified Trade-ID Validation

Covers mandate Objectives 2 ("End-to-end pipeline validation") and 3
("Trade-ID validation") together, since one controlled local run produced
evidence for both.

## Method and why

The sandbox this work runs in cannot reach live market-data providers
(yfinance/TwelveData calls fail with a proxy 403 — a sandbox network
restriction, not a platform bug; see DAY15_IMPLEMENTATION_REPORT.md
Sec.2). To still produce a real, evidence-based execution trace against
the *actual, unmodified* pipeline code (not a reimplementation of it), a
throwaway diagnostic script (`_day15_trace.py`, deleted after use, never
committed) monkeypatched only `engine.markets.fetch` — swapping the live
HTTP call for a synthetic 500-bar OHLCV DataFrame — and `alert_signals.
_send` — suppressing the outbound Telegram call — then called the real,
unmodified `alert_signals.main()`. Every other line of every engine
module ran exactly as it does in production, driven by the CI/CD schedule.

Every state file this touched (`trades.json`, `pending.json`,
`run_ledger.jsonl`, and 9 history/broker files) was backed up before the
run and restored/removed byte-for-byte afterward — verified via `diff`
against the backup for every file, all identical. No production-relevant
state changed as a result of this investigation.

## Run 1 — against the repo's real (unmodified) trades.json / pending.json

This run is itself a finding, not just a rehearsal. Result:

```
XAUUSD: setup voided | XAUUSD: entry HELD (portfolio) — 4 simultaneous
long positions across the portfolio would exceed the configured max of 2.
| XAUUSD: no setup | data health: degraded
```

Investigating why a single-symbol scan produced a portfolio-cap rejection
led directly to a second, independent, previously-undocumented finding
(see "Critical finding" below): the repo's real `trades.json` currently
contains **three duplicate, still-open BTCUSD long positions**, all
sharing the identical ID `BTCUSD-2026-07-17T13:15:00`, opened 2026-07-17
and never closed. `engine/portfolio_risk.py::directional_exposure()`
counts open rows by direction with no deduplication by ID — so those
three duplicate rows alone count as 3 simultaneous long positions before
any new candidate is even evaluated, meaning **any new long-direction
trade, on any symbol, is currently likely to be blocked by the portfolio
exposure gate** even once the market-data issue (Objective 1) is fixed.

Separately, `pending.json` contains one stale, unresolved short setup on
XAUUSD created 2026-07-17 — three weeks old, never tapped or voided (void
requires 96 bars — ~24h — of real scans to elapse against it, which
haven't happened since the scan loop stopped producing usable data).

## Run 2 — against a clean (temporarily emptied, then fully restored) state

To get a trace that reaches every stage in the mandate's diagram rather
than stopping at the portfolio gate, `trades.json` and `pending.json`
were temporarily set to `[]` (backed up first, restored immediately
after — verified identical via `diff`) and the same synthetic scan
re-run once, seeded with one pending long setup whose entry level the
synthetic price data dips through partway in.

Result — every stage up to journal persistence executed and a real trade
row was written:

| Stage (mandate diagram) | Evidence this run |
|---|---|
| Scheduler | Out of scope for a local run — see DAY15_IMPLEMENTATION_REPORT.md Sec.1 for the live-cadence evidence (confirmed running on GitHub's own schedule) |
| Market Data | `markets.fetch(XAUUSD)` called, synthetic 500-bar frame returned |
| Regime | `rgeng.classify()` ran; `regime_history.jsonl` gained 1 row tagged with this trade's ref |
| Pending lifecycle / "ICT Origination" (tap) | `pending.update()` returned an `entry` event for the seeded setup; log line `XAUUSD: ENTRY long @ 2396.33...` |
| Risk guard | `risk_guard.evaluate()` ran and allowed this candidate (`"guard_action": "allow"` in the persisted row) |
| Confluence | `cf.analyze()` was called but did not return a usable result against synthetic-only data (see "Confluence did not complete" below) — degraded to `confluence_score: -1` per the platform's own fail-safe convention, correctly non-blocking |
| Portfolio Risk | `pr.evaluate()` ran and allowed the trade (0 pre-existing open positions in this clean run) |
| Market Memory | `log_market_memory_context()` ran (reached in code order; not independently re-verified this run beyond not raising) |
| Macro | `log_macro_context()` ran; `macro_history.jsonl` gained 1 row tagged with this trade's ref |
| Data Health | ran once at end of scan, reported `degraded` (expected — synthetic run has no real feeds) |
| Execution Simulation | `log_execution_context()` ran; `execution_history.jsonl` gained 1 row tagged with this trade's ref |
| Paper Broker | `log_paper_broker_submission()` ran; `broker_orders.jsonl` and `broker_events.jsonl` each gained rows tagged with this trade's ref (4 lines each — an order plus its lifecycle events) |
| Confidence | `log_confidence_assessment()` ran; `confidence_history.jsonl` gained 1 row tagged with this trade's ref |
| Explainability | `log_decision_snapshot()` ran; `decision_audit.jsonl` gained 1 row tagged with this trade's ref |
| Journal | `journal.log_signal()` ran; a new `trades.json` row was written, `status: "open"` |
| Dashboard | `dashboard_publish.main()` was invoked (its own live-publish HTTP call failed in-sandbox, same network restriction as market data — the function itself ran and degraded gracefully, "pipeline continues") |
| Research Records | `run_ledger.jsonl` gained 4 rows (regime, and this run's other logged events) tagged with this trade's ref |

## Unified trade-ID chain — CONFIRMED populated end-to-end (Objective 3)

The new `trades.json` row from Run 2:

```json
{
  "id": "XAUUSD-2026-08-05T13:15:00",
  ...
  "confluence_ref": "XAUUSD-2026-08-05T13:15:00",
  "confidence_ref": "XAUUSD-2026-08-05T13:15:00",
  "regime_ref": "XAUUSD-2026-08-05T13:15:00",
  "macro_ref": "XAUUSD-2026-08-05T13:15:00",
  "execution_ref": "XAUUSD-2026-08-05T13:15:00",
  "broker_ref": "XAUUSD-2026-08-05T13:15:00"
}
```

All six `*_ref` fields are present and equal to the trade's own `id`, and
that same ID was independently confirmed present in `regime_history.
jsonl`, `confidence_history.jsonl`, `decision_audit.jsonl`, `macro_
history.jsonl`, `execution_history.jsonl`, `broker_orders.jsonl`, `broker_
events.jsonl`, and `run_ledger.jsonl` — eight independent stores, one ID,
zero breaks in the chain.

**This directly revises Research & Validation Cycle #2's headline finding**
(`RESEARCH_VALIDATION_CYCLE_2_REPORT.md` Sec.0), which found these fields
entirely absent as keys on all 102 real trade rows and treated this as an
unresolved wiring gap. The Day 15 trace shows the wiring is NOT broken —
the current code populates every ref correctly, every time, when it runs.
The most likely explanation, reconciling both findings: **the ref-
population code (Days 6-13) was completed after the scan loop had
already stopped producing real trades**, so no live trade has been
written by this code since it was finished. This is a much better
position than "the join is broken" — it means Objective 1's fix (restore
real scans) should be sufficient on its own to start populating this
chain on real trades, with no additional wiring work needed.

## Confluence did not complete in either trace run — disclosed, not fixed

`confluence_history.jsonl` was never created in either run; `cf.analyze()`
produced no usable result (the trade row shows `confluence_score: -1`,
`confluence_agree: 0` — the platform's own sentinel for "no confluence
data available," not a crash). Confluence's 17 confirmation sources
include several (COT positioning, seasonality, cross-asset correlation)
that expect either much deeper real history than a 500-bar synthetic
frame provides, or real external cache files shaped like actual market
data. This is recorded as a **limitation of this synthetic trace, not a
confirmed platform defect** — the code's own fail-safe design caught
whatever went wrong internally and degraded to "no confluence" rather
than blocking or crashing the trade, which is correct, intended behavior.
Confirming confluence's own health specifically would need either a real
live scan (once Objective 1 is resolved) or a dedicated synthetic dataset
shaped to satisfy its specific lookback requirements — out of scope for
this trace, noted as a follow-up if the platform owner wants it verified
independently of a live run.

## What this means for Objective 5 (operational readiness)

Two independent things currently stand between "the scan loop runs" and
"the platform generates new real trades":

1. Market data fetch (Objective 1) — the primary, larger blocker.
2. The phantom duplicate BTCUSD positions + stale XAUUSD pending setup
   found in Run 1 — a secondary blocker that will independently prevent
   new long-direction trades via the portfolio exposure cap, even after
   #1 is fixed, until a human reviews and cleans up those specific rows.
   This was NOT auto-fixed as part of this Day: `trades.json` is the
   platform's trade journal / historical record, and editing or deleting
   rows in it is a data-correctness decision for the platform owner to
   make deliberately, not something to change unilaterally while fixing
   an unrelated observability bug. See DAY15_OPERATIONAL_READINESS_
   REPORT.md for the specific recommended action.
