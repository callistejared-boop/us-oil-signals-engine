# Version 2.2 Roadmap

Research & Validation Cycle #2 closing deliverable. Built from measured
findings across this cycle's documents — `RESEARCH_VALIDATION_CYCLE_2_
REPORT.md`, `ARCHITECTURE_AND_TEST_SUITE_REVIEW.md`, `TECHNICAL_DEBT_
REGISTER.md`, `PERFORMANCE_BENCHMARK_REPORT.md`, and the three
forward-design documents (`STRATEGY_FRAMEWORK_SPECIFICATION.md`,
`SCALPING_ENGINE_DESIGN.md`, `STRATEGY_RESEARCH_FRAMEWORK.md`) — not
assumptions. Sequenced per the mandate's own priority order: (1)
execution realism, (2) statistical confidence, (3) operational
reliability, (4) research quality, (5) maintainability. This is a
recommended sequence for the platform owner to accept, adjust, or
reject — not a commitment to build.

## Before any of the below: resolve the P0 findings

Every priority tier in this roadmap assumes the platform's live
feedback loop is trustworthy. This cycle found direct evidence it may
not currently be (`TECHNICAL_DEBT_REGISTER.md` Items 1-3):
`alert_heartbeat.txt` stale 11+ days, `trades.json`'s last trade
2026-07-23, and the unified trade-ID `*_ref` chain completely
unpopulated on all 102 live trades. **Recommendation: before scheduling
any Version 2.2 feature work, confirm (a) whether the scheduled scan
workflow is intentionally paused or has silently failed, and (b) trace
one real trade through the full `*_ref` chain and fix the join.**
Everything below produces stronger evidence faster once this is
resolved, and produces misleading evidence if built on top of it
unresolved.

## Priority 1 — Execution realism

1. **Extend Paper Broker's position model from symbol-aggregate to
   per-trade or per-(symbol, strategy) granularity**
   (`TECHNICAL_DEBT_REGISTER.md` Item 4, `STRATEGY_FRAMEWORK_
   SPECIFICATION.md` Sec.7, `SCALPING_ENGINE_DESIGN.md` Sec.7). This is
   the single highest-leverage execution-realism item: it's a
   prerequisite for the Scalping Engine, for any multi-strategy
   concurrent paper-trading, and for trustworthy per-strategy execution
   quality metrics (`STRATEGY_RESEARCH_FRAMEWORK.md` Sec.3). Building
   the Scalping Engine or multi-strategy support before this lands
   would produce paper-trading evidence that looks cleaner than it is.
2. **Instrument real, end-to-end scan-cycle latency** (`PERFORMANCE_
   BENCHMARK_REPORT.md` Sec.2). Currently a measurement gap, not a
   known problem — but execution realism claims (spread/slippage/
   latency modeling) are only as credible as the platform's
   understanding of its OWN latency profile end-to-end, not just
   individual subsystem costs.
3. **Validate the Execution Simulator's assumptions against the
   Scalping Profile's tighter tolerances specifically**
   (`SCALPING_ENGINE_DESIGN.md` Sec.6), once Item 1 and the Strategy
   Framework schema (Priority 2, Item 4) both exist — a scalping
   strategy's edge is far more sensitive to spread/slippage assumptions
   than swing's, per this cycle's own design analysis.

## Priority 2 — Statistical confidence

4. **Land the `Trade.strategy` schema change**
   (`STRATEGY_FRAMEWORK_SPECIFICATION.md` Sec.2-3, sequencing in Sec.9)
   together with the `origination_method` rename
   (`STRATEGY_RESEARCH_FRAMEWORK.md` Sec.6, `TECHNICAL_DEBT_REGISTER.md`
   Item 8) in the same implementation Day, so the naming collision never
   ships. This is the prerequisite for literally everything in the
   Strategy Research Framework (Sec.3-5) — no per-strategy statistic can
   be computed until trades carry a strategy tag.
5. **Add `avg_holding_time_minutes()` to `research_stats.py`**
   (`STRATEGY_RESEARCH_FRAMEWORK.md` Sec.4) — small, mechanical, and
   already motivated by a real Day 10 finding (holding-time collapse
   from 63.9min to 23.5min was informative during that edge-decay
   investigation).
6. **Set realistic sample-size expectations before promoting any new
   strategy** — per `STRATEGY_RESEARCH_FRAMEWORK.md` Sec.5/7, `MIN_N_
   FOR_TRUST = 30` applies PER strategy once tagging exists, and today's
   102-trade dataset (all pre-dating this design) offers zero
   retroactively-taggable history for a new Scalping strategy. Any new
   strategy starts from n=0. This isn't an action item so much as a
   planning constraint the roadmap needs to carry forward honestly:
   **do not expect strong per-strategy evidence quickly** — budget
   real calendar time for sample accumulation once Item 4 lands.
7. **Fix the `journal.make_ref()` duplicate-ID generator and add the
   missing regression test** (`TECHNICAL_DEBT_REGISTER.md` Item 3) —
   a prerequisite for trustworthy per-trade statistics of any kind,
   strategy-tagged or not.

## Priority 3 — Operational reliability

8. **Diagnose and resolve the stalled live scan loop** (see "Before any
   of the below," Item 1 above — repeated here because it is also,
   correctly, an operational-reliability item, not just a blocking
   precondition).
9. **Wire the unified `*_ref` chain end-to-end for at least one real
   trade** (P0 Item 2) — validates Days 6-13's join design against
   reality for the first time.
10. **Cache one Data Health `dashboard_snapshot()` per publish run
    instead of recomputing per-symbol** (`PERFORMANCE_BENCHMARK_
    REPORT.md` Sec.5) — the one concrete, evidence-backed, low-risk
    optimization this cycle found. Cuts Data Health's contribution to
    dashboard publish time by roughly 75% with zero behavior change.
11. **Give the Scalping Engine's `latency_gate.py` a real feed-health
    dependency check** (`SCALPING_ENGINE_DESIGN.md` Sec.2) once the
    engine itself is scheduled — Data Health's registry already exposes
    everything needed; this is pure integration, not new detection
    logic.

## Priority 4 — Research quality

12. **Retire or resolve Day 10's 4 open questions**
    (`DAY10_NEXT_DAY_READINESS_REPORT.md`) — this cycle's own Research
    Framework validation (`RESEARCH_VALIDATION_CYCLE_2_REPORT.md` Sec.6)
    found "recommendation strength documented" only "Partially" true
    specifically because these were never acted on. Closing them (even
    if the answer is "still open, here's why") keeps the Research
    Framework's own governing rules honest.
13. **Benchmark real replay performance** (`PERFORMANCE_BENCHMARK_
    REPORT.md` Sec.7) before relying heavily on replay-based validation
    for new Strategy Profiles — a measurement gap, not a known problem,
    but worth closing before Priority 2's per-strategy validation work
    leans on it.
14. **Design the `strategy_profile_history.jsonl` versioning ledger**
    (`STRATEGY_FRAMEWORK_SPECIFICATION.md` Sec.6) alongside Item 4 —
    keeps the same lifecycle-and-evidence discipline Day 9 established
    applied to strategy profiles from day one, rather than retrofitted
    later.

## Priority 5 — Maintainability

15. **Consolidate the caching-helper pattern into `engine/feed_
    cache.py`** (`TECHNICAL_DEBT_REGISTER.md` Item 5) — 6 modules, low
    risk, opportunistic.
16. **Consolidate the JSONL append/rotate pattern into `engine/jsonl_
    store.py`** (`TECHNICAL_DEBT_REGISTER.md` Item 10) — bundle with
    Priority 1 Item 1's Paper Broker rework, since Paper Broker's
    history store is one of the six affected modules.
17. **Resolve the `4_SEND_SIGNAL_NOW.bat` / `hourly_briefing.py` dual
    entry point** (`TECHNICAL_DEBT_REGISTER.md` Items 6, 15) — either
    retire the path or give it test coverage matching `alert_signals.
    py`'s.
18. **Audit the duplicate `Trade` class** (`TECHNICAL_DEBT_REGISTER.md`
    Item 7), the dashboard-script helper duplication (Item 13), and
    re-locate the `journal.py` silent-except block (Item 14) — all three
    need a fresh look before scheduling, not immediate action.
19. **Mark the two slow `test_market_memory.py` tests `@pytest.mark.
    slow`** and mock Paper Broker/Data Health in the three slow
    `test_dashboard_publish.py` parametrized tests
    (`ARCHITECTURE_AND_TEST_SUITE_REVIEW.md` Sec.3.2) — improves local
    developer iteration speed, zero coverage loss.
20. **Seed the one flaky `test_paper_broker.py` stress test**
    (`TECHNICAL_DEBT_REGISTER.md` Item 9) — removes an intermittent
    false-failure signal from CI.

## What this roadmap deliberately does NOT include

- No production promotion recommendation for any subsystem — every
  item above is either a fix, a measurement, or a design landing;
  none claims readiness for live capital.
- No new signal-origination logic, no new ML model, no changes to
  Confluence's 17 sources or Confidence's calibration — consistent with
  every design document this cycle produced.
- No committed dates or Day numbers — sequencing is by dependency and
  priority tier, not calendar, since this cycle's own top finding (the
  live loop's uncertain state) makes calendar commitments premature.
