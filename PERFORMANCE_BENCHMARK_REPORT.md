# Performance Benchmark Report

Research & Validation Cycle #2. All numbers below were measured directly
this cycle (single-machine, sandboxed environment — absolute values will
differ on the platform owner's actual deployment target; relative
comparisons and scaling trends are the reliable part of this report).
Every recommendation is qualified by whether evidence actually supports
it, per the mandate's own instruction. Where a mandate-requested
benchmark was NOT measured this cycle, that gap is stated directly
rather than estimated.

## 1. Startup time

`alert_signals.py` cold import: **7.146s**, profiled via `python3 -X
importtime`. Dominated by `pandas` (~4.29s cumulative of the 7.146s,
~60%). This is a one-time cost per scheduled run, not a per-symbol or
per-scan cost.

`engine/dashboard_publish.py` cold import: **0.480s** — no pandas
dependency in its import chain, ~15x faster to start.

**Assessment**: not recommended for optimization. GitHub Actions'
`entry-scan.yml` runs on a `*/15min` cadence with (presumably, per the
workflow file) a much larger execution budget than 7 seconds — there is
no evidence this cost causes missed scans or timeouts. Optimizing it
(e.g., lazy-importing pandas only where used) would be speculative
complexity against no measured problem, which the mandate explicitly
cautions against ("avoid adding complexity unless it delivers
measurable value"). **Recommendation: no action, revisit only if a
scan-timeout or missed-cadence problem is ever actually observed.**

## 2. Scan performance

**Not directly benchmarked this cycle.** What was measured is import
cost (Sec.1) and individual subsystem costs (Sec.4-5) — not a full,
realistic end-to-end scan cycle including live network calls to price/
news/macro providers, since this review is explicitly prohibited from
making live network calls or altering production behavior. This is a
disclosed gap: real scan-cycle latency (the number that would actually
matter for the `*/15min` cadence and for the Scalping Engine's
latency-sensitivity concerns) can only be measured by instrumenting a
real, live scan run — recommended as a monitoring addition (log
`elapsed` from `alert_signals.py`'s own `_scan_start` timer, already
present in the code since Day 14, to a persistent metric) rather than
a one-off benchmark here.

## 3. JSONL scalability (ledger append cost)

Measured append latency at increasing existing-file sizes, using the
same `_rotate()`-per-append pattern this codebase uses across `engine/
ledger.py` and 5+ other history modules (see `ARCHITECTURE_AND_TEST_
SUITE_REVIEW.md` Sec.2.4 and `TECHNICAL_DEBT_REGISTER.md` Item 10):

| Existing records | Cost per append |
|---|---|
| 500 | 0.082ms |
| 2,000 | 0.220ms |

A ~2.7x slowdown as the file grows 4x, consistent with an O(n)
per-append cost (the append function re-reads the full file to check
against `MAX_LINES` on every write). **At today's actual data volumes
(102 total live trades, per `RESEARCH_VALIDATION_CYCLE_2_REPORT.md`
Sec.0) this is entirely immaterial — sub-millisecond regardless.** At
the `MAX_LINES` cap most of these modules use (5,000-20,000 lines) it
remains fast in absolute terms (low single-digit milliseconds).
**Recommendation: no urgent action; consolidate into a shared,
smarter-rotation helper opportunistically (Technical Debt Register Item
10), not as dedicated performance work** — there is no evidence this
is currently a bottleneck.

## 4. Broker reconstruction

`engine.broker` (Day 13 abstraction layer) `rebuild_from_history()`:
**0.017s (17ms)** to reconstruct full broker state from history. This
is the platform's fastest-measured subsystem and matches the
Operational Reliability finding in `RESEARCH_VALIDATION_CYCLE_2_
REPORT.md` Sec.5.4 that restart/reconstruction reliability is the
platform's best-evidenced reliability claim — now with a concrete
number behind it. **Recommendation: no action; this is not a
bottleneck.**

100 simulated Paper Broker order cycles: **2.045s total, 20.45ms per
cycle**. Not yet benchmarked against a realistic concurrent-order
scenario (Technical Debt Register Item 4 — the position model isn't
yet built for that), so this number describes today's sequential,
symbol-aggregate usage pattern only, not the concurrency scenario the
Strategy Framework / Scalping Engine designs anticipate.

## 5. Dashboard generation

Per-symbol `dashboard_publish.py` payload cost, broken down by
subsystem snapshot call:

| Subsystem | Cost |
|---|---|
| `engine.broker` / Paper Broker `dashboard_snapshot()` | 0.0383s |
| Data Health `feed_monitor.dashboard_snapshot()` | 0.2255s |
| **Combined, both subsystems** | **~0.264s** |

Data Health dominates this pair — consistent with `run_health_check()`
(persist=False path) doing real freshness/completeness/consistency/
anomaly checks across the full feed registry on every call, once per
symbol, in `dashboard_publish.py`'s per-symbol loop. **This is the one
concrete, evidence-backed optimization opportunity this cycle
found**: `dashboard_snapshot()` is symbol-agnostic (confirmed in Day
14's own test `test_build_payload_data_health_is_symbol_agnostic`) —
it computes the same platform-wide health report regardless of which
symbol is being published, yet is currently called fresh once per
symbol in the publish loop. **Recommendation: cache one `dashboard_
snapshot()` result per publish run and reuse it across all symbols in
that run, rather than recomputing per-symbol.** With 4 symbols
(XAUUSD/WTIUSD/BTCUSD/EURUSD), this would cut Data Health's
contribution to total publish time by roughly 75% (4 calls -> 1 call)
with zero behavior change, since the result is already
symbol-independent. This is a real, low-risk, evidence-backed
optimization — the strongest one in this report.

## 6. Memory usage

Peak RSS observed during the benchmark run (100 broker cycles + JSONL
scaling test + data health checks, combined in one process): **76.5MB**.
No evidence of unbounded growth or a leak pattern across the measured
operations — flat within the observed range. **Recommendation: no
action; not a concern at measured scale.**

## 7. Replay performance

**Not benchmarked this cycle** — disclosed gap, not measured. Day 9's
walk-forward/replay tooling exists and is tested for correctness, but
its own performance characteristics (time to replay N historical bars)
were not separately profiled in this cycle's time budget. Recommended
as a follow-up benchmark before any Version 2.2 work that depends on
frequent replay runs (e.g., validating a new Scalping Profile against
historical data).

## 8. Summary — findings supported by evidence vs. gaps

| Area | Status |
|---|---|
| Startup time | Measured. No action recommended (pandas cost, no observed problem it causes). |
| Scan performance (real, end-to-end) | **Not measured** — recommend live instrumentation, not a synthetic benchmark. |
| JSONL scalability | Measured, trend confirmed (O(n)-per-append). No urgent action; opportunistic consolidation recommended. |
| Broker reconstruction | Measured. Fast (17ms). No action needed. |
| Dashboard generation | Measured. **One concrete optimization identified and recommended** (cache Data Health snapshot across symbols in one publish run). |
| Memory usage | Measured. Flat, no concern. |
| Replay performance | **Not measured** — recommended as a follow-up before Scalping/multi-strategy validation work begins. |

Per the mandate's own instruction to recommend optimizations only where
evidence supports them: **this cycle found exactly one concrete,
low-risk, high-confidence optimization** (Sec.5's dashboard snapshot
caching) and two measurement gaps worth closing before Version 2.2 work
proceeds (scan performance, replay performance) — everything else
measured shows no evidence of a current problem worth solving.
