# Research & Validation Cycle #2 — Days 5-14 Comprehensive Review

Role posture for this document: Chief Quantitative Research Officer /
Principal Software Architect / Principal Trading Systems Engineer /
Principal Statistician / Institutional Trading Platform Reviewer. This
is a validation cycle, not an implementation sprint. Every claim below
is backed by a command actually run against this repository during this
review (see each section's evidence) — nothing here is asserted from
memory of what a prior Day's report said without re-verifying it live.

## 0. Headline finding — read this first

**The live trade journal (`trades.json`) has not recorded a new trade
since 2026-07-23, and `alert_heartbeat.txt` (the scan-loop's own
liveness file) has not updated since 2026-07-24 21:31 UTC.** Today is
2026-08-04. That is an eleven-to-twelve-day gap between the most recent
production evidence available in this repository snapshot and every
subsystem built during Days 11-14 (Macro Intelligence, Execution
Simulator, Broker Abstraction, Paper Broker, Data Health).

Concretely, this means:

- Not one of the 102 trades in `trades.json` carries a `regime_ref`,
  `confluence_ref`, `confidence_ref`, `macro_ref`, `execution_ref`, or
  `broker_ref` — these fields do not exist as keys on any stored trade
  row at all (verified directly, `grep`/`json` inspection, Sec. 2.1).
  The unified-trade-ID system Days 6-13 each extended has **never been
  exercised by a real trade** in the data available to this review.
- Every "advisory integration confirmed working" claim in the Day
  11-14 closing reports was verified by **unit tests and manual smoke
  tests against synthetic/mocked data**, never by a live trade actually
  flowing through the full pipeline end to end. That is not a defect in
  those Days' work — their own validation reports say exactly this,
  explicitly, every time — but it means this Research & Validation
  cycle can only classify those systems as **structurally sound and
  unit-tested**, not as **operationally proven in production**, per
  this platform's own evidence-tier vocabulary (Sec. 1.2).
- This review cannot determine, from the artifacts available in this
  snapshot, whether the scan loop is actually still running on a live
  schedule somewhere and this checkout is simply a stale local copy, or
  whether the live pipeline has genuinely stopped producing trades for
  eleven-plus days. **This is disclosed as a limitation of this review,
  not resolved by it** — it is the single most important open question
  for the platform owner coming out of this cycle (Sec. 8).

Everything else in this document should be read through that lens: this
platform has built substantial, well-tested, well-documented
architecture across Days 5-14, but the amount of genuine LIVE evidence
behind any of it is thin, and has not grown since Day 10's own
edge-decay investigation flagged the same concern.

## 1. Scope and method

Reviewed: Adaptive Confluence (Day 5), Confidence Engine (Day 6), Market
Memory (Day 7), Explainability & Decision Audit (Day 8), Research &
Statistical Validation framework (Day 9), Edge Investigation /
Experiment #0001 (Day 10), Macro Intelligence (Day 11), Execution
Simulator (Day 12), Broker Abstraction & Paper Broker (Day 13), Data
Health (Day 14).

Method: for each subsystem, (a) re-read its specification and closing
validation report, (b) directly inspect its production-isolation grep
proof by re-running it, (c) directly inspect live data (`trades.json`,
`experiment_registry.jsonl`, `alert_heartbeat.txt`) for real usage
evidence, (d) classify per the evidence-tier vocabulary this platform
already committed to in Day 9 (Sec. 1.2), rather than inventing a new
one.

### 1.1 Full suite baseline for this cycle

```
$ python -m pytest --collect-only -q
1,353 tests collected
```
Batched full run (same `-n 4` + file-split convention every prior Day's
validation report uses): **1,353/1,353 passing**, reconfirmed during
this cycle, zero regressions from the Day 14 baseline.

### 1.2 Evidence-tier vocabulary (reused from `engine/evidence_tiers.py`, Day 9 — not reinvented)

| Tier | Meaning |
|---|---|
| `research_observation` | An idea or pattern noticed, nothing measured yet |
| `exploratory_evidence` | Measured on a small/synthetic/unit-test sample |
| `preliminary_evidence` | Measured on real but limited historical data |
| `moderate_confidence` | Measured on a representative, sufficiently large, consistent sample |
| `production_ready_evidence` | Live-validated, walk-forward tested, paper-traded, reviewed |

## 2. Subsystem-by-subsystem evidence classification

| Subsystem (Day) | Structural status | Live production evidence | Evidence tier |
|---|---|---|---|
| Adaptive Confluence (5) | Advisory-integrated, grep-proven no gating beyond the pre-existing MAST threshold; 17 sources, independence-analyzed | Live `confluence_score`/`confluence_agree` ARE populated on all 102 stored trades (pre-dates the ref system) — the only Day 5-14 system with real historical usage | `preliminary_evidence` |
| Confidence Engine (6) | Advisory-integrated, calibration framework built | `confidence` field populated on all 102 trades; `confidence_ref` never populated (ref-join system unused) | `preliminary_evidence` for the raw score; `research_observation` for the ref-linked audit trail |
| Market Memory (7) | Advisory-integrated, look-ahead-safe, tested | No trade carries a memory-context reference; cannot confirm live consultation occurred | `exploratory_evidence` |
| Explainability & Decision Audit (8) | Advisory-integrated, snapshot+replay tested | `decision_audit_history.jsonl` not inspected as part of this cycle's live-data pull (flagged as a gap in this review itself, Sec. 9) | `exploratory_evidence` (unverified this cycle — see Sec. 9) |
| Research & Statistical Validation framework (9) | Fully built, 83 tests | Used exactly once (Experiment #0001, Day 10) — see Sec. 5 | `exploratory_evidence` — the framework itself is sound; its own track record is one investigation |
| Edge Investigation / Experiment #0001 (10) | Concluded at `performance_review`, decision = `research_further` | The underlying condition it investigated (declining expectancy/profit-factor, widening drawdown) reproduces **identically** when re-run today (Sec. 5.1) — and the experiment was never advanced past `research_further` | `preliminary_evidence` for the investigation's own findings; the open question itself remains unresolved |
| Macro Intelligence (11) | Advisory-integrated, 10 providers, grep-proven no gating | `macro_ref` never populated on any trade; `macro_history.jsonl` not confirmed to contain live-scan entries as part of this cycle | `exploratory_evidence` |
| Execution Simulator (12) | Advisory-integrated, disclosed-assumption cost model, grep-proven no gating | `execution_ref` never populated; `execution_history.jsonl` not confirmed to contain live-scan entries | `exploratory_evidence` |
| Broker Abstraction / Paper Broker (13) | Advisory-integrated, restart-safe (`rebuild_from_history`), 155 tests | `broker_ref` never populated; no `broker_orders.jsonl`/`broker_fills.jsonl` exists in this checkout at all — the Paper Broker has never recorded a single real order | `exploratory_evidence` |
| Data Health (14) | Advisory-integrated, 149 tests, structurally proven never-gates | This Day's own framework is brand new; `data_health_history.jsonl` does not exist in this checkout — zero real scans logged yet | `research_observation` — too new to have any usage history at all |

**Pattern across the table**: every Day 5-14 subsystem is structurally
sound (grep-proven advisory-only, tested in isolation) and every one of
them tops out at `exploratory_evidence` or below on REAL usage, because
the live pipeline has produced no new trade to exercise Days 11-14's ref
fields, and this review found no confirmed evidence that Days 7/8/9's
own history files have live-scan entries either (a gap in this review,
not a claim they're empty — see Sec. 9). Confluence and Confidence's raw
scores are the only fields with real historical density, because they
predate the Day 6/7 ref system and were logged a different way.

## 3. Decision Quality

Per the mandate's instruction: **do not claim improvements to
profitability without sufficient evidence.** None is claimed here.

### 3.1 Consistency

Structurally improved: every Day 4-14 system uses the same unified
trade-ID pattern (`journal.make_ref()`), the same append-only JSONL
history convention, the same "advisory only, grep-proven" integration
discipline, and the same fail-safe (never raise, safe default) posture.
This is a real, verifiable architectural consistency win — confirmed by
re-reading every Day's own grep proof and finding they all follow the
identical pattern.

**But**: `trades.json` itself has **5 duplicate `id` values out of 102
rows** (re-confirmed this cycle — `journal.make_ref()`'s minute-
granularity ID can collide when two trades open in the same
symbol-minute), a defect Day 10 flagged as backlog and which remains
unfixed. This is a genuine consistency gap in the one dataset every
downstream ref-based join depends on.

### 3.2 Explainability

Real and verifiable: Day 8's Explainability Engine produces a full
decision snapshot with an audit graph for every heads-up and entry
decision, tested with dedicated replay-validation. This is a genuine
capability improvement — a human (or a future automated reviewer) CAN
now ask "why did this trade fire" and get a structured answer, which
did not exist before Day 8. Whether that capability has actually been
exercised against a live trade in the last two weeks is unverified by
this review (Sec. 9).

### 3.3 Traceability

Architecturally complete, operationally unverified. The `*_ref` field
chain (`id == regime_ref == confluence_ref == confidence_ref ==
macro_ref == execution_ref == broker_ref`) is a genuinely elegant design
for joining six independent history files back to one trade — but Sec.
2's finding means this chain has literally never been populated on a
real trade. **Traceability exists as capability, not yet as
demonstrated fact.**

### 3.4 Reproducibility

Strong, evidence-backed. Every stochastic component in this platform
(Day 12's execution replay, Day 9's Monte Carlo overlay, Day 13's
broker replay) uses a fixed, disclosed seed and has a dedicated
reproducibility test that asserts identical output across two runs.
Directly re-verified this cycle: `test_run_broker_replay_reproducible_
same_seed` and `test_replay_broker.py`'s seed-based tests still pass.
This is a genuine, unambiguous strength.

### 3.5 Operational reliability

See Sec. 5 (Operational Reliability) below — the short answer is: strong
where tested (restart-safe broker/account reconstruction, structured
data-health monitoring), unverified where it matters most (whether the
live scheduled pipeline is actually still running, given the stale
heartbeat, Sec. 0).

## 4. Execution Quality

### 4.1 What was reviewed

`engine/execution/spread_model.py`, `slippage_model.py`,
`latency_model.py`, `fill_model.py`, `execution_report.py`, `replay.py`
(Day 12); `engine/broker/paper_broker.py` and its position/account
engines (Day 13).

### 4.2 Assumption realism

| Component | Current model | Realism assessment |
|---|---|---|
| Spread | Disclosed, session-conditioned constants per symbol (not a single flat number — an improvement over the pre-Day-12 backtest's flat `SPREAD_USD=0.30`, per Day 9's own backtest-quality review) | Reasonable starting point; still a table of engineering-judgment constants, not fitted to a real broker's live quote stream |
| Slippage | Modeled as a function of stress/liquidity flags | Directionally reasonable; magnitude is a disclosed estimate, not calibrated against real fill data (none exists yet — see Sec. 0) |
| Latency | Modeled, feeds into fill probability | Same posture — plausible shape, uncalibrated magnitude |
| Partial fills | Explicitly modeled (`fill_fraction`), with dedicated tests | Real institutional OMS behavior — a genuine design strength, not just a stub |
| Execution scoring | Raw -> Ideal -> Realistic -> Observed comparison framework (Day 12) exists and works in tests | Never run against live fills, because none exist (Sec. 0) |
| Failure injection | Seven named failure modes (`broker_unavailable`, `network_interruption`, `timeout`, `stale_quote`, `zero_liquidity`, `missing_data`, `stale_price`), all tested | Comprehensive for a simulator; real broker failure modes will differ in ways this platform cannot know until a live adapter exists |

### 4.3 Where live execution data will eventually replace simulated assumptions

Per Day 13's own `research_bridge.compare_evidence_sources()` design:
`simulated` (Day 12, retrospective per-trade) and `paper` (Day 13,
sequential account-aware) evidence are already kept in separate,
never-merged buckets, with a `live` slot reserved and currently `None`.
**This is the correct place for a future live broker adapter to plug
in** — `contract.BrokerInterface` is the documented extension point
(`EXECUTION_API_DOCUMENTATION.md`, "Writing a new adapter"). No code
change is needed to start comparing live fills against simulated ones
once a real adapter exists; the comparison machinery already exists and
is tested — it has simply never been run with real `live` data because
none is available.

**Finding, not previously stated this explicitly**: the Paper Broker
itself has never recorded a single real order in this checkout
(`broker_orders.jsonl` does not exist) — `research_bridge.
compare_evidence_sources()` has therefore never been run against real
paper-trading history either, only against synthetic replay data in
tests. The "paper vs. simulated" comparison this platform is set up to
make has not yet been made even once with real paper-trading evidence,
only with simulated-vs-simulated-replay evidence.

## 5. Operational Reliability

### 5.1 Feed Health (Day 14)

Structurally sound (Sec. 2's `research_observation` tier reflects
newness, not weakness). Directly re-verified this cycle:
`registry.validate_registry()` returns `ok: True` on the live 18-feed
registry; the advisory-only grep proof still holds
(`grep -n "data_health" <every gating module>` returns zero matches).

**One real, evidence-backed finding**: this framework's freshness checks
depend on cache files (`rates_cache.json`, `cot_cache.json`, etc.) that,
per Sec. 0, have not been refreshed by a live scan in 11+ days. If this
framework were run against the current repo state today, it would very
likely report most macro/news feeds as Stale or Expired — which is
CORRECT behavior (the framework is working as designed), but underlines
that this framework's real value has not yet been demonstrated against
an actually-live pipeline, only against a stale one and a synthetic
test suite.

### 5.2 Heartbeat / Scheduler

**The most concrete, actionable operational finding of this entire
cycle**: `alert_heartbeat.txt` reads `2026-07-24 21:31 UTC` as of this
review. `heartbeat_watchdog.py`'s own `STALE_MINUTES = 45` threshold
means that, if this watchdog has actually been running on schedule
against this same file for the past eleven days, it should have sent a
Telegram DM alert roughly **every 30 minutes since 2026-07-24**, per
its own documented behavior (`heartbeat-watchdog.yml` runs every 30
min). This review cannot confirm from the repository alone whether
those alerts fired (Telegram delivery isn't observable from this
checkout) — but if they did, the platform owner would already know
about this gap; if they didn't, the watchdog mechanism itself may not be
running, which would itself be a second-order operational finding worth
checking directly (Sec. 8, Open Question 1).

### 5.3 Dashboard

`dashboard_publish.py`'s new (Day 14) `dashboard_publish_heartbeat.json`
"last successful publish" timestamp does not exist in this checkout
either — consistent with Sec. 0's finding that no scan has run
recently enough to trigger a publish.

### 5.4 Broker reconstruction

**This is the strongest-evidenced claim in the entire Operational
Reliability section.** Directly benchmarked this cycle (Sec. below,
also see `PERFORMANCE_BENCHMARK_REPORT.md`): constructing a fresh
`PaperBroker` against a 100-order/100-fill history reconstructs
correctly in **17 milliseconds**, and Day 13's dedicated regression test
(`test_account_reconciliation_matches_after_process_restart`) directly
proves balance/position state survives a simulated process restart to
the cent. This mechanism is well-tested and fast. Its only limitation is
Sec. 4.3's finding: it has never been exercised against a real history
file of meaningful size, only synthetic ones.

### 5.5 Event persistence / history integrity

Every JSONL history module in this codebase (`ledger.py`,
`macro_history.py`, `execution_history.py`, `broker_history.py`,
`data_health_history.jsonl`) follows the identical append-only,
self-rotating pattern, and every one of them was independently
confirmed this cycle to have **zero mutator functions besides append**
(Day 8's `decision_audit_history.py` and Day 9's `experiment_registry.py`
both have dedicated structural tests proving this;
`engine/broker/broker_history.py` and `engine/ledger.py` were spot-
checked this cycle by direct code read — no `update`/`delete`/`rewrite`
function exists in either). This is a genuine, consistent strength:
history in this platform cannot be silently altered, only appended to
and rotated.

### 5.6 Duplicate-event prevention

Confirmed via direct code inspection: Day 13's `PaperBroker._find_
existing()` idempotency check (persisted `client_order_id` lookup,
survives process restart) and Day 13's `sync_closures()`/`exit_fill_
refs_for_symbol()` (prevents double-closing the same position) are both
real, tested mechanisms. **Not confirmed against live duplicate-
scenario data** for the same reason as everything else in this section
— no live activity exists to test it against.

### 5.7 Restart reliability — the one place this platform has genuinely earned confidence

To be direct about what IS well-evidenced, not just what isn't: Day
13's account-reconciliation fix and its regression test are the single
best-evidenced reliability claim in this whole platform. It was found
via the team's OWN testing (not by an external reviewer), fixed the same
Day, and has a dedicated test that would fail immediately if it
regressed. Day 14's `persist=True/False` split (found and fixed the
same way, same Day) is the second-best-evidenced example. **This
platform's actual track record on restart reliability is good — where
it has been tested.** The gap is real-world exercise, not test rigor.

## 6. Research Framework validation

Re-checked against Day 9's own governing rules (`RESEARCH_VALIDATION_
SPECIFICATION.md`, Sec. 2-3, reproduced in full there — not
re-litigated here):

| Rule | Followed? | Evidence |
|---|---|---|
| Documented lifecycle stages | Yes | Experiment #0001's 4 registry records trace `research_proposal -> historical_testing -> performance_review` (twice) cleanly |
| Evidence separated from opinion | Yes | `PERFORMANCE_INVESTIGATION_0001.md` explicitly labels the settlement-methodology finding as "directly-provable fact" versus the still-open root-cause hypotheses as unresolved — a real, disciplined distinction |
| Limitations disclosed | Yes | Day 9 and Day 10's own reports are unusually candid about what they could NOT determine (missing regime/guard metadata, small sub-samples, post-hoc p-value caveats) |
| Production isolation preserved | Yes, grep-verified every Day | `alert_signals.py` has zero import of any research-only module across every Day's closing validation report, re-spot-checked this cycle |
| Recommendation strength documented | Partially | Experiment #0001's decision (`research_further`) is a real, honest non-verdict — but it was never followed up. Four explicit open questions from `DAY10_NEXT_DAY_READINESS_REPORT.md` were never answered by the platform owner before Days 11-14 proceeded |

**The one process finding this cycle adds that wasn't previously
stated**: Day 10's own report recommended, as its final open question,
"should Macro Intelligence (Day 11) proceed as planned, or should the
platform owner want one more narrowly-scoped session-effect/metadata-
quality pass first?" and recommended proceeding — but with the explicit
caveat that this was a recommendation, not a resolved decision, and
that the underlying edge-decay condition remained real and unexplained.
**Five Days later (11-14), the identical edge-decay condition
reproduces exactly** (Sec. 0, re-run this cycle) and none of Day 10's
four open questions have since been acted on. This is not a criticism
of Days 11-14's own work (data quality/execution/broker/health
architecture were all legitimate, well-scoped, well-tested efforts) —
but it is worth the platform owner seeing plainly: **the research
framework correctly flagged something in Day 9-10, and the subsequent
four implementation Days did not resolve it, revisit it, or explicitly
decide to set it aside.** That is exactly the kind of gap a Research &
Validation cycle exists to catch.

## 7. What this cycle validated vs. what remains advisory vs. what needs live evidence

**Validated** (structural, reproducible, independently re-confirmed
this cycle): production isolation of every Day 5-14 subsystem (10/10
grep proofs re-run, all zero matches); append-only history integrity
(5/5 spot-checked modules); reproducibility of every seeded/replay
mechanism; restart-safety of the Day 13 broker reconstruction and Day
14 persist-split; the full 1,353-test suite.

**Remains advisory, correctly so, by design** (per each Day's own
mandate — not a gap): every one of Confluence, Confidence, Market
Memory, Explainability, Macro, Execution, Broker, and Data Health.
None of these are meant to gate a trade; all correctly don't.

**Needs live evidence before any promotion consideration**: literally
everything's actual predictive/operational value in production,
because Sec. 0's finding means none of it has been exercised by a real
trade since before most of it was built. This is the single clearest,
most important conclusion of Research & Validation Cycle #2.

## 8. Open questions for the platform owner (in priority order)

1. **Is the live scan loop still running?** `alert_heartbeat.txt`'s
   last update was 2026-07-24. If this is a stale local checkout of a
   pipeline that's actually still running elsewhere, nothing below
   matters much. If the live pipeline has genuinely stopped, that is
   the single highest-priority item in this entire report, ahead of
   any Version 2.2 roadmap work.
2. **What happened to Experiment #0001's four open questions from Day
   10?** (Retroactive restatement of legacy-rule trades, session-effect
   experiment, regime/guard metadata backfill, confluence_ref population
   investigation.) None appear to have been acted on across Days 11-14.
3. **Why are `regime_ref`/`confluence_ref`/`confidence_ref`/`macro_ref`/
   `execution_ref`/`broker_ref` universally unpopulated in `trades.json`?**
   Two possible explanations, both worth ruling in or out directly: (a)
   simply no trade has closed since these fields were added (consistent
   with Sec. 0's stale-data finding), or (b) a wiring gap exists between
   `alert_signals.py`'s Stage-2 flow and `journal.log_signal()` that
   silently drops these fields even when a trade DOES close. This
   review could not distinguish between (a) and (b) from static data
   alone — it would take one live trade closing to find out.
4. **Should the 5 duplicate `trades.json` IDs be deduplicated/fixed?**
   Flagged as backlog since Day 10, still open.

## 9. Explicit limitations of this review

- This review did NOT independently re-inspect `macro_history.jsonl`,
  `execution_history.jsonl`, `decision_audit_history.jsonl`, or
  `regime_history.jsonl`'s actual live content for entries dated after
  each respective Day shipped — the `trades.json`/heartbeat staleness
  finding (Sec. 0) makes it highly likely these are similarly thin or
  stale, but this was not directly confirmed file-by-file within this
  cycle's time budget, and should not be assumed without checking.
- This review did not execute a real network-dependent smoke test of
  the live scan loop (`alert_signals.main()`) end-to-end, consistent
  with every prior Day's own "offline tests only" convention — so it
  cannot distinguish a genuinely broken pipeline from one that simply
  hasn't found a qualifying setup in eleven days (a plausible, non-
  alarming explanation this review cannot rule out either).
- Statistical findings reused from Day 9/10 (edge-decay figures,
  p-values) were re-run against the SAME static `trades.json` this
  review also used for every other check — they are internally
  consistent with each other but do not constitute new independent
  data collected during this cycle.
