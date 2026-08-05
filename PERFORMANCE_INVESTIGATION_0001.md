# Performance Investigation — Experiment #0001

**Title:** Observed Edge Deterioration Investigation
**Experiment ID:** `0001-observed-edge-deterioration-investigation`
**Registered in:** `experiment_registry.jsonl` (4 records: proposal,
`historical_testing`, `performance_review`, and one typo-only correction —
query via `engine.experiment_registry.history()`)
**Code:** `engine/edge_investigation.py` (tested: `tests/test_edge_investigation.py`, 29 tests)
**Governing principle:** determine WHY performance changed, not whether to
change it. **No production file was modified as a result of this
investigation.** Every number below is reproducible by calling
`engine.edge_investigation.full_investigation_report()` against the live
`trades.json`.

---

## 0. What triggered this investigation

Day 9's `edge_decay_monitor.check()`, run against the live `trades.json`,
flagged: expectancy +1.22R (prior 69 trades) -> -0.01R (recent 30 trades),
profit factor 3.47 -> 0.99, max drawdown -5.0R -> -12.0R, and inconsistent
sign across the recent window's own sub-segments. Per the framework's
governing principle, this was reported and NOT acted on. This experiment is
that investigation.

---

## 1. Verify the data (independent recalculation)

Re-run via `engine.edge_investigation.verify_core_metrics()`, which calls
`engine.research_stats.full_report()` (Day 9, reused not reimplemented) plus
two metrics not previously in this platform's statistics vocabulary:

| Metric | Prior (n=69) | Recent (n=30) |
|---|---|---|
| Expectancy | +1.22R | **-0.01R** |
| Profit factor | 3.47 | **0.99** |
| Win rate | 49.3% | **26.7%** |
| Max drawdown | -5.0R | **-12.0R** |
| Avg holding time | 63.9 min | **23.5 min** (2.7x faster) |
| Avg stop size (% of entry) | 0.12% | 0.12% (unchanged) |
| Avg target size (% of entry) | 0.45% | 0.41% (roughly unchanged) |
| Avg planned R:R | 3.70 | 3.64 (roughly unchanged) |
| Avg confidence at entry | 82.1 | 76.7 |

This reproduces the Day 9 finding exactly — not a one-off artifact. Two new
observations beyond Day 9's own report: **win rate collapsed** (49.3% ->
26.7%) far more than trade construction changed (stop/target/R:R sizing is
essentially unchanged), and **holding time collapsed** (trades are resolving
2.7x faster), both of which point toward the trades themselves behaving
differently, not just being sized or managed differently.

---

## 2. Data quality review

Via `engine.edge_investigation.data_quality_review()`, against all 102 rows
(99 closed, 3 still open):

- **No sign mismatches, no `closed`-before-`opened` rows, no closed trade
  missing a `closed` timestamp.** Every recorded loss is exactly `-1.0R`
  (100% internally consistent) in both windows.
- **5 duplicate `id` groups, 12 rows affected.** `journal.make_ref()` keys
  on `f"{symbol}-{timestamp}"` at minute granularity; when the same symbol
  produces more than one distinct signal (different entry/stop/target) in
  the same minute-bar, the `id`s collide even though `journal.is_open()`'s
  dedup check does not block them (a different entry price bypasses it).
  **This is a reference-integrity issue, not a P&L issue** — each row's own
  `result_r` is independently correct — but it does mean any future lookup
  keyed purely by `id`/`*_ref` (e.g. `decision_audit_history.find_by_ref`)
  can be ambiguous for these 12 rows. Flagged for the backlog, not fixed
  here (out of this investigation's scope; see Sec.7).
- **Metadata completeness is genuinely uneven across the dataset**
  (quantified, not just noted): `regime_trend`/`regime_vol` are 0%
  populated on the entire prior window and only ~33% on the recent window;
  `guard_action` is 0% populated in prior, 10% in recent; `confluence_score`
  and `confluence_ref`/`confidence_ref`/`regime_ref` are **0% populated on
  all 102 rows**. This is a schema-evolution artifact (these fields were
  added by later Days) and a genuine limitation on what this investigation
  can conclude from trade-level tags alone — see Sec.4 (Regime Shift,
  Risk Controls, Strategy Mix, Confluence Profile).

### 2.1 The most significant data-quality finding: a settlement-methodology change

Every WIN's `result_r` was cross-checked against what it *should* be given
the trade's stored `entry`/`stop`/`target` under the CURRENT settlement rule
(`engine/journal.py::_manage()`: breakeven after +1R, bank 50% at +2R,
runner to target — which always credits `1 + 0.5*finalR` for any win that
reaches target, or exactly `1.0R` if stopped at breakeven after touching
+2R without reaching target).

**30 of the prior window's 34 wins (88%) do not match this formula at all —
their `result_r` equals the full planned R-multiple (`finalR`) directly, a
simpler "full target or bust" rule with no partial banking.** Every one of
the recent window's 8 wins (100%) matches the current, more conservative
rule. The legacy-rule pattern last appears at `2026-07-09 07:30:00`; the
current-rule pattern first appears at `2026-07-12 21:15:00` — i.e. the
settlement methodology changed **mid-way through the prior window itself**,
and was never retroactively reapplied to earlier trades.

**This is directly reconstructable from stored data — no external price
feed needed** (see `engine.edge_investigation._settlement_rule_family()`).

**Quantified impact** (`engine.edge_investigation.restated_comparison()`):
restating every prior-window win to the current rule's formula (holding
losses/scratches unchanged, since they are identical under both rules):

| | As stored | Restated to current methodology |
|---|---|---|
| Prior expectancy | +1.22R | **+0.91R** |
| Prior profit factor | 3.47 | **2.85** |
| Prior max drawdown | -5.0R | -5.0R (unaffected — drawdown driven by losses, not the win formula) |

**Conclusion: implementation drift explains roughly 25-30% of the apparent
expectancy gap (the drop from +1.22R to +0.91R against a recent value of
-0.01R), but not the majority of it.** Even under a fully consistent,
current-methodology comparison, the prior window remains solidly profitable
(+0.91R, PF 2.85) against a recent window that is flat-to-losing (-0.01R,
PF 0.99). The methodology change is real and should be corrected as its own
follow-up item (see Sec.7), but it is not, by itself, a sufficient
explanation for the deterioration.

---

## 3. Sample adequacy

Via `engine.evidence_tiers.assess()` (Day 9, reused) on the recent 30-trade
window, with `representative=False` (the window spans a single narrow
~9-day calendar period with uneven symbol/session/day-of-week composition —
see Sec.5) and `consistent_sign` read from
`research_stats.stability_over_time()`:

- **Size-only tier: `moderate_confidence`** (n=30 clears this platform's own
  30-trade statistical-trust floor, and nothing more).
- **Effective tier after downgrade: `preliminary_evidence`** — "a pattern is
  visible; still easily explained by chance or a narrow period." The
  downgrade triggers on BOTH representativeness and within-sample
  consistency, per `evidence_tiers.py`'s deliberate downgrade-only design
  (Day 9): no amount of the window "clearing 30 trades" can compensate for
  it being narrow and internally inconsistent.

**Read this plainly: the recent window is exactly this platform's own
minimum trust floor, not comfortably above it, and per this platform's own
policy should be treated as preliminary, not conclusive, evidence of
anything — including a genuine edge change.**

---

## 4. Root cause analysis — all 8 hypotheses, evaluated separately

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| 1 | **Market Conditions changed** | Plausible, not confirmed | Avg holding time collapsed 63.9min -> 23.5min (2.7x faster resolution) — consistent with faster/choppier price action. Cannot be fully confirmed via regime tags (see #2). |
| 2 | **Regime Shift** | **Inconclusive — data gap** | `regime_trend`/`regime_vol` are 0% populated on all 69 prior trades, ~33% on recent. Cannot test whether the regime distribution changed from trade-level tags alone. Not "ruled out" — untestable with current instrumentation. |
| 3 | **Session Effects** | **Supported** | Asian session (largest recent sample, n=9): 50.0% win-rate/+1.106R -> 11.1%/-0.556R. London KZ (n=7 recent): 50.0%/+1.5R -> 14.3%/-0.176R. Off-session held up comparatively (46.7%->38.5%, stayed positive). A real, concentrated pattern. |
| 4 | **Symbol Effects** | Not the primary driver | Decline is broad-based across all 4 symbols (XAUUSD, BTCUSD, WTIUSD, EURUSD) — not concentrated in one. XAUUSD (the flagship symbol) shows the steepest reversal (+1.536R -> -0.714R) and merits separate attention, but every symbol declined. |
| 5 | **Strategy Mix** | Not applicable under current instrumentation | `engine.market_memory` confirms one production strategy platform-wide at a time (`config.regime_strategy`) — a trade-level "mix" literally cannot shift under current instrumentation. |
| 6 | **Risk Controls** | **Inconclusive — data gap** | `guard_action` is 0% populated in the prior window; 90% unknown in the recent window (only 3 of 30 tagged, all "downgrade," all losses). Sample far too small and one-sided to conclude new safeguards altered trade selection at any measurable scale. |
| 7 | **Execution Quality** | **Confirmed, partial explanation** | The settlement-methodology drift documented in Sec.2.1 is real, quantified, and reproducible. Explains ~25-30% of the apparent expectancy gap, not the majority. |
| 8 | **Statistical Variance** | Unlikely to be the sole explanation, not ruled out | See Sec.6 — permutation test gives P(expectancy this low by chance) ≈ 1.2%, P(win rate this low by chance) ≈ 3.2%, with a disclosed post-hoc selection caveat. |

**Two of eight hypotheses (Regime Shift, Risk Controls) cannot be
responsibly evaluated with current data — this is itself a finding**, not a
gap this report papers over. See Sec.7.

---

## 5. Segment performance

Via `engine.edge_investigation.segment_performance()`. Full detail
reproducible from the function; headline patterns:

- **By session:** Asian and London KZ sessions concentrate the decline (see
  Sec.4 #3); off-session trades held up comparatively better.
- **By day of week:** the prior window is heavily concentrated on Wednesday
  (38 of 69 trades, 55%, expectancy +1.635R) — a striking concentration
  worth noting on its own. Recent Wednesdays flip to -0.444R (n=9, 11.1% win
  rate). The mechanism (e.g. a recurring Wednesday economic-data catalyst
  the strategy may be tuned around) is speculative and NOT concluded here —
  flagged as a candidate for future research, not a finding.
- **By confidence tier:** only Exceptional (>=85) and High (70-84) tiers
  were ever taken (confluence gating means lower tiers never reach
  execution). The **Exceptional tier collapsed from 45.5% win rate
  (n=33, +1.217R) to 0.0% (n=5, -0.6R)** — small n alone, but directionally
  consistent with every other signal in this report. High tier: 52.8% ->
  32.0% win rate.
- **By symbol, regime, guard_action:** see Sec.4 items #2, #4, #6 above.
- **Confluence profile: not segmentable.** `confluence_score` is
  unpopulated (-1) on effectively every trade — documented as a data gap,
  not a finding that confluence composition is stable.

---

## 6. Statistical variance — permutation test

Via `engine.edge_investigation.variance_permutation_test()`: the full
99-trade closed population (methodology-RESTATED per Sec.2.1, so the test
is not contaminated by the settlement-rule drift) is treated as a fixed
pool; 20,000 random 30-trade draws without replacement are compared against
the actual observed recent-window expectancy and win rate.

- **P(random 30-draw expectancy <= observed -0.01R) = 0.0123**
- **P(random 30-draw win rate <= observed 26.7%) = 0.0315**

**Disclosed limitation, read before trusting this:** the recent window was
not chosen blindly — it was examined specifically *because* it already
looked anomalous (exactly how Day 9's `edge_decay_monitor` surfaced it).
This post-hoc selection biases the p-values downward relative to a truly
pre-registered test. Treat this as **informative, not confirmatory**: a
~1-3% chance-alone probability makes pure statistical variance an unlikely
sole explanation, but it does not rule it out, especially stacked against
Sec.3's finding that this sample sits at, not above, this platform's own
trust floor.

---

## 7. Feature contribution (Day 6/7/8 advisory systems)

Via `engine.edge_investigation.feature_contribution_check()`:
`confluence_ref`/`confidence_ref`/`regime_ref` — the ONLY mechanism by which
a Day 6/7/8 advisory system's own output could later be joined back to a
specific trade — are **0% populated on all 102 trades**. Combined with
every prior Day's own structural proof (direct grep) that these systems
never write to `alert_signals.py`'s trade-selection/sizing path, **there is
no mechanism by which the Confidence Engine, Market Memory, or
Explainability Engine could have contributed to this deterioration** —
advisory-only status holds for this sample by construction, not merely by
design. This is an observation, not a causal claim about whether these
systems would help if wired in.

### 7.1 Counterfactual analysis

The mandate asks for advisory-on vs. advisory-off, filter-on vs.
filter-off, and alternate risk-configuration comparisons where feasible.
For THIS sample, the advisory-on/off counterfactual is **degenerate, not
merely "not run"**: since zero ref-linkage exists between these trades and
any Day 6/7/8 advisory output (Sec.7 above), there is no configuration
under which the recorded outcomes could have differed — the advisory
systems were never in the loop for any of these 99 trades regardless of any
setting. This is reported as a genuine null result. A risk-configuration or
session-filter counterfactual (e.g. "what if Asian-session trades had been
filtered out") was considered but requires re-simulating against historical
price bars this investigation does not have loaded — flagged as a Day 10+
backlog item (a natural `historical_testing`-stage follow-up for a future,
narrower experiment specifically proposing a session filter), not attempted
here to avoid overclaiming a result this data cannot support.

---

## 8. Recommendations (classified, none defaulting to production)

| Finding | Classification | Rationale |
|---|---|---|
| Settlement-methodology drift (legacy vs. current R-crediting rule) | **Research Further** (fix-scoped) | Real, quantified, reproducible. Should become its own small, well-scoped follow-up experiment: retroactively restate `trades.json`'s historical wins for reporting purposes (NOT a production trading-behavior change — a data-hygiene correction), so all future prior-vs-recent comparisons are apples-to-apples. |
| Session effects (Asian/London degradation) | **Research Further** | Concrete, concentrated, but drawn from n=7-9 per session in the recent window — too small to act on directly. A dedicated experiment testing a session-aware filter, run through `historical_testing` -> `walk_forward_testing` -> `paper_trading` before any production consideration, is the appropriate next step. |
| Regime Shift, Risk Controls hypotheses | **Research Further** (instrumentation, not strategy) | Cannot be evaluated without better data. Recommend backfilling `regime_trend`/`regime_vol`/`guard_action` tagging coverage going forward (and, if feasible, retroactively via `engine.regime_engine` against historical price bars) before attempting this analysis again. |
| Confluence-profile / confluence_ref data gap | **Research Further** (instrumentation) | `confluence_score` essentially never populated in the live journal despite being a `Trade` field since Day 5/6. Worth a dedicated look at why the live signal path isn't stamping it. |
| Duplicate `id` collisions (12 rows / 5 groups) | **Research Further** (instrumentation) | Reference-integrity issue for any future ref-based lookup. Candidate fix: extend `journal.make_ref()` to include a sub-minute disambiguator, or accept multiple rows per `id` explicitly in all downstream joins. |
| Overall verdict on "has the platform's edge genuinely decayed?" | **Research Further — NOT Monitor, NOT Reject, NOT a graduation to Paper Trading or Production Evaluation** | The deterioration is real and only ~25-30% explained by measurement artifact. A majority remains unexplained. Two of eight hypotheses are untestable with current data (not ruled out). The statistical-variance test makes chance-alone unlikely (p≈0.01-0.03) but is subject to a disclosed post-hoc caveat, and the sample sits at, not above, this platform's statistical-trust floor. This is exactly the profile of "worth continued, focused investigation," not "safe to ignore" and not "confirmed edge decay requiring a strategy change." |

**No recommendation above proposes moving anything directly into
production.** Every item is scoped as its own future `idea` /
`research_proposal` in the experiment registry, to be evaluated on its own
merits through the full lifecycle — this experiment's job was to
investigate, not to fix.

---

## 9. What this experiment explicitly did NOT do

- Did not change any threshold, config value, or trading behavior.
- Did not modify `trades.json`, `alert_signals.py`, `engine/journal.py`,
  or any other production file.
- Did not conclude that genuine edge decay is confirmed OR ruled out — the
  evidence is mixed and partial, and this report says so plainly rather
  than forcing a verdict the data doesn't support.
- Did not attempt to retroactively fix the settlement-methodology drift in
  the live `trades.json` — restatement here is for ANALYSIS only (see
  `restate_win_to_current_methodology()`'s docstring); actually correcting
  the stored historical records is its own follow-up item (Sec.8), requiring
  its own explicit decision, not something to slip in silently as a side
  effect of an investigation.
