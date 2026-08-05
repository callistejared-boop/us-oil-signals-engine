# Research & Statistical Validation Framework — Specification (Day 9)

Covers the mandate's Research Specification, Validation Specification,
Developer Guide, and Testing Guide requirements in one document, following
this project's established convention of one comprehensive spec per Day
(see `CONFIDENCE_ENGINE_SPECIFICATION.md`, `MARKET_MEMORY_SPECIFICATION.md`,
`EXPLAINABILITY_SPECIFICATION.md` for precedent).

## 1. Primary objective and governing principle

This framework governs research. **It does not change production trading
behavior.** No function in any Day 9 module can hold, approve, reject,
resize, or otherwise alter a live signal — there is no code path from
`engine/experiment_registry.py`, `engine/research_stats.py`,
`engine/evidence_tiers.py`, `engine/edge_decay_monitor.py`,
`engine/paper_trading_review.py`, or `engine/research_dashboard.py` into
`alert_signals.py`'s publication decisions. This is verified structurally,
not just documented: `alert_signals.py` was NOT modified this Day (see
Sec.12).

No future feature should be accepted because it is interesting, popular,
or theoretically appealing — every feature must earn its place through
reproducible evidence, measured performance, and disciplined validation
(the mandate's own governing principle, repeated here because it is the
organizing idea behind every section below).

## 2. Research lifecycle

Eleven stages plus two terminal states, implemented as
`engine.experiment_registry.LIFECYCLE_STAGES`/`TERMINAL_STAGES`:

```
idea -> research_proposal -> technical_design ->
implementation_research_branch -> historical_testing ->
walk_forward_testing -> paper_trading -> performance_review ->
production_recommendation -> controlled_release -> ongoing_monitoring
                                                  (terminal: rejected, rolled_back —
                                                   reachable from any stage)
```

Every stage has documented entry/exit criteria
(`experiment_registry.STAGE_CRITERIA`) — descriptive guidance surfaced to
researchers (and the research dashboard), NOT programmatically enforced.
This is a deliberate choice: the mandate's governing principle is that
this framework governs research, not production, and heavy-handed
programmatic gating of a RESEARCH workflow would itself be a form of
production-like rigidity this framework is meant to avoid. A human
(the platform owner, or a future designated reviewer) makes every
promotion decision; the registry records it.

## 3. Hypothesis template

`engine.experiment_registry.Hypothesis` — verbatim per the mandate:
`objective`, `theoretical_rationale`, `expected_benefit`,
`implementation_scope`, `dependencies`, `risks`,
`measurable_success_criteria`, `rollback_criteria`.

`is_complete()` requires every narrative field non-empty AND at least one
measurable success criterion AND one rollback criterion — a hypothesis
with no falsifiable success/rollback condition is not a hypothesis in any
useful sense, so this is the one thing the template DOES check
structurally. An incomplete hypothesis can still be recorded
(`propose()` never refuses to write) — it is flagged `"complete": False`,
not hidden, matching this codebase's "disclose, don't hide" convention.

## 4. Backtest quality review

Reviewing `engine/backtest.py` and `engine/montecarlo.py` (existing,
UNCHANGED this Day — per the mandate: "Identify areas for future
improvement without changing validated behavior unless justified"; no
justification for a behavior change was found or acted on):

| Dimension | Current behavior | Assessment |
|---|---|---|
| **Entry model** | Limit order at the setup level; fill only on a later bar's wick touching that price (`sig.entry`), pessimistic touch fill | Reasonable and conservative — does not assume a better-than-achievable fill |
| **Trade management** | Stop to break-even after +1R, bank 50% at +2R, runner to target; stop wins ties on a bar that touches both stop and target | Matches the live journal's identical management rule (`engine/journal.py::_manage`) — backtest and live are apples-to-apples |
| **Transaction costs** | Flat `SPREAD_USD = 0.30` subtracted from the R result of every trade (`res -= SPREAD_USD / ru`) | A single flat number, not session- or volatility-conditioned. Real spread widens around news/session transitions — this is a known simplification, not silently assumed away (now explicitly logged here) |
| **Slippage** | Not modeled beyond the spread constant — fills assume the exact quoted entry price is achieved once the level is touched | A real limitation: in fast markets a limit order can be skipped entirely (price gaps through the level) rather than filled at it. Not modeled. |
| **Survivorship** | Not applicable in the traditional sense (no basket of instruments where some get delisted) — but the backtest depends entirely on the depth of the local CSV feed for each symbol, which is finite and itself a form of "what data we have" bias | Disclosed limitation, not previously stated this explicitly anywhere in the codebase |
| **Look-ahead protection** | `signals.analyze()` is called on `data.iloc[i-WINDOW:i+1]` (bars up to and including the signal bar `i`); the fill search then only scans bars `j > i` (`range(i + 1, ...)`); trade management (`manage_exit`) only reads bars strictly after the fill bar. Traced directly — no look-ahead found. | Sound. This is the same "only information available up to and including the decision bar" discipline Day 7's `_look_ahead_safe()` formalized for Market Memory — `backtest.py` already followed it, just without a name for the pattern |
| **Reproducibility** | Fully deterministic — no randomness anywhere in `backtest.py`/`walkforward.py`/`calibration.py`. `montecarlo.py`'s bootstrap uses a fixed `seed=42` default, so even the stochastic Monte Carlo overlay is reproducible run-to-run | Sound |

**What this review changed**: nothing in `backtest.py` itself. What it
produced: the table above (new, was previously implicit/undocumented),
and the explicit backlog items in Sec.14 for slippage/variable-spread
modeling as candidate FUTURE experiments — which, per this framework's
own governing principle, would need their own hypothesis and pass through
the lifecycle in Sec.2 like any other proposed change, not be silently
added.

## 5. Walk-forward methodology

`engine/walkforward.py` (existing, Day 1-2) already implements an
EXPANDING-window out-of-sample methodology comparing three probability
models (raw confidence, base-rate, empirically-calibrated) by rolling
Brier score. This Day adds `expanding_window_series()` — a GENERALIZATION
of the same look-ahead-safe iteration to any metric function, so a future
experiment's own metric (not just probability calibration) can reuse
proven, tested walk-forward plumbing rather than reimplementing it.

**Rolling windows**: EXPANDING by default (train set = every closed trade
strictly before trade `i`, growing as `i` increases) — matching the
existing `rolling_brier()`'s own shape, not a new methodology. An explicit
`window_size=N` parameter switches to a TRUE fixed-size rolling window
(train set = the last `N` trades before `i`) for a future experiment that
specifically wants recency-weighting; this is disclosed as an available
option, not the default, because the existing calibration methodology
(Sec above) has always used expanding windows and changing the default
would silently change validated behavior.

**Evaluation metrics**: caller-supplied (`metric_fn`) — for the existing
probability-calibration use case, Brier score; for a future strategy
experiment, any `engine.research_stats` metric (Sec.7) or a custom
function.

**Recalibration policy**: implicit and continuous — `calibrated_model()`
(existing) recomputes `calibration.calibrated_map()` fresh from the
CURRENT training window on every step, so the "calibration" is always
as of that point in time, not a stale snapshot. No separate recalibration
schedule exists or is needed given this.

**Reporting standards**: `walkforward.report()` (existing, text summary)
for the probability-comparison use case; `expanding_window_series()`
returns a structured list (`{"i", "opened", "value"}` per step) for
programmatic consumption by, e.g., `edge_decay_monitor.py` (Sec.9) or a
future experiment's own reporting.

## 6. Paper trading framework

`engine/paper_trading_review.py` — reuses Day 8's
`explainability_engine.post_trade_review()` verbatim for
`expected_outcome`/`realized_outcome`/`deviations`, and adds:

- `proposed_vs_executed`: confirms an approved-entry `DecisionSnapshot`
  actually has a matching `trade_ref` in the journal (execution
  confirmed) — flags `matches: False` if not, rather than assuming
  benign.
- `operational_issues`: a best-effort scan of the last 200 ledger events
  for this symbol for anything error-shaped.

**Disclosed limitation, not silently worked around**: this platform does
NOT currently persist a direct reference linking a Stage-1 heads-up
decision to the Stage-2 entry it may (or may not) have triggered — Day 6/7
unified the trade ID for FILLED trades only. `proposed_vs_executed()`
reports `matches: None` with an explicit note for heads-up decisions
rather than attempting a fragile timestamp/price heuristic match. The
natural fix — extending Day 8's `DecisionSnapshot` with a
`heads_up_decision_id` field, threaded through `pending.json` the same way
`trade_ref` is threaded through Stage-1/Stage-2 today — is flagged as a
Day 10+ backlog item (Sec.14), following this platform's established
"extend an existing ref pattern" precedent (regime/confluence/confidence
refs, Day 6/7) rather than inventing something new this Day.

This IS, per the mandate, "the primary bridge between research and
production": any future experiment reaching the `paper_trading` lifecycle
stage should call `paper_trading_review.evaluate()` on its own decisions
to build the evidence base for its `performance_review` stage.

## 7. Statistical framework

`engine/research_stats.py` — ten standardized metrics, every one a pure
function of an R-multiple list (or trades.json-shaped dicts). Summary
table (full why-it-matters/when-misleading/min-sample text lives in each
function's own docstring — not duplicated here to avoid drift):

| Metric | Formula | Honesty disclosure |
|---|---|---|
| `expectancy` / `avg_r_multiple` | mean(R) | — |
| `profit_factor` | gross wins / gross losses | reports `None` (not `inf`) when there are zero losses |
| `win_rate` | wins / n | always read alongside expectancy/profit_factor, never alone |
| `max_drawdown` | deepest peak-to-trough decline, in realized sequence order | one realized path — see `montecarlo.simulate()` for a resampled DISTRIBUTION |
| `sharpe_like` | mean(R) / stdev(R) | explicitly NOT annualized — named `_like` specifically so it is never confused with a standard, cross-system-comparable Sharpe ratio |
| `sortino_like` | mean(R) / downside-stdev(R) | same annualization disclosure as `sharpe_like` |
| `calmar_like` / `recovery_factor` | total(R) / abs(max drawdown) | explicitly NOT time-annualized (no clean per-symbol annualization basis exists yet in this event-driven, multi-symbol platform); both names report the identical number since the two conventional metrics differ only in whether the numerator is annualized |
| `stability_over_time` | per-segment expectancy across N equal chunks of the sample, in order | a WITHIN-sample check, explicitly distinguished from `walkforward`'s OUT-of-sample check |

Every function returns `{"value", "n", "sufficient", ...}` — `sufficient`
is `n >= MIN_N_FOR_TRUST` (30, reused from Day 5/6/7's established bar),
never hidden, never silently omitted.

## 8. Sample size / evidence policy

`engine/evidence_tiers.py` implements the mandate's own five-tier list
verbatim (`research_observation` -> `exploratory_evidence` ->
`preliminary_evidence` -> `moderate_confidence` -> `production_ready_
evidence`), with the explicit "avoid rigid numerical thresholds" mandate
requirement satisfied by `assess()`: sample size alone gives a
`size_only_tier`, but `representative` (does the sample span multiple
market regimes/sessions, or one narrow period) and `consistent_sign`
(does `research_stats.stability_over_time()` show the effect holding
across sub-segments) can each DOWNGRADE the effective tier regardless of
`n` — a large sample that is unrepresentative or inconsistent is
explicitly worth LESS than the same `n` with neither problem. Good context
can never UPGRADE past the size-only tier — sample size is a genuine
floor, not something good context can substitute for.

## 9. Edge decay monitoring

`engine/edge_decay_monitor.py::check()` compares the most recent 30 closed
trades against everything before them (`RECENT_WINDOW =
research_stats.MIN_N_FOR_TRUST`), flagging declining expectancy, declining
profit factor, increasing drawdown, and within-recent-window
inconsistency. **Every flag's `recommendation` field is the literal string
"investigate — do not change production automatically"** — this is
enforced by convention in the one function that generates flags, and
confirmed by a dedicated test
(`test_flags_are_descriptive_never_prescriptive_of_a_production_change`)
that every flag says so, not just some.

Regime-conditioned decay (the mandate's "changing market regimes" item) is
explicitly NOT reimplemented here — `check()`'s own output points callers
at `engine.market_memory.performance_by_strategy_regime()` (Day 7, already
regime-aware) rather than duplicating that logic.

### 9.1 A real, current finding — reported, not acted on

Running `edge_decay_monitor.check()` against the actual live
`trades.json` (2026-08-03, at the time this document was written) flags
FOUR conditions:

- **Declining expectancy**: +1.22R (prior 69 trades) -> -0.01R (most
  recent 30).
- **Declining profit factor**: 3.47 -> 0.99.
- **Increasing drawdown**: -5.0R (prior) -> -12.0R (recent).
- **Reduced within-window consistency**: the 30 most recent trades'
  own sub-segments do not agree in sign.

**This is reported here exactly as the framework is designed to report
it: as something worth investigating, not as a verdict, and NOT acted on
by this Day's work.** No threshold was changed, no strategy was paused,
no config was touched as a result of this finding — per the framework's
own governing principle. See `DAY9_NEXT_DAY_READINESS_REPORT.md` for this
flagged as an explicit open item for the platform owner's attention.

## 10. Experiment registry

`engine/experiment_registry.py` persists to `experiment_registry.jsonl`,
mirroring `decision_audit_history.py`'s (Day 8) exact immutability
pattern: `record()`/`propose()`/`log_idea()`/`transition()` only ever
APPEND; there is no update/delete function of any kind
(`test_no_mutator_besides_record_writes` proves this structurally, same
technique as Day 8's equivalent test). An experiment's current stage is
always DERIVED by reading its full history and taking the latest record —
never stored redundantly, so there is no risk of a "current state" view
drifting from the append-only log of how it got there.

`active_experiments()` excludes both terminal stages AND
`ongoing_monitoring` (an experiment being monitored in production is no
longer "in research," even though monitoring has no defined exit stage);
`completed_experiments()` is exactly `ongoing_monitoring`;
`rejected_experiments()` is both terminal stages — kept permanently
queryable, per the mandate: "Failed experiments are valuable knowledge and
should remain documented."

## 11. Research dashboard

`engine/research_dashboard.py::build_research_payload()` — a symbol-
agnostic, standalone JSON payload (never called from
`dashboard_publish.py` or `alert_signals.py`) showing active/completed/
rejected experiments, the lifecycle stage reference, the edge-decay check,
and the evidence-tier reference table. Consistent with this codebase's
existing "dashboard = a JSON payload function" precedent — no HTML is
rendered by this repo for the production dashboard either (`webapp/`,
outside this repo, does that).

## 12. Production isolation — what was NOT touched

`alert_signals.py`, `engine/dashboard_publish.py`, `engine/confidence_
engine.py`, `engine/portfolio_risk.py`, `engine/regime_engine.py`,
`engine/confluence.py`, `engine/explainability_engine.py`,
`engine/decision_audit_history.py` — **none of these were modified this
Day.** Every Day 9 module is new and additive; the only pre-existing file
touched was `engine/walkforward.py`, and only by ADDING
`expanding_window_series()` after its existing functions — nothing in the
file's original 92 lines changed. This is the structural proof behind
Sec.1's claim that this framework cannot change production behavior: there
is no import of any Day 9 module anywhere in the live scan path.

## 13. Testing

83 new tests across seven files: `test_research_stats.py` (26),
`test_evidence_tiers.py` (10), `test_experiment_registry.py` (19),
`test_walkforward_expanding_window.py` (5), `test_edge_decay_monitor.py`
(8), `test_paper_trading_review.py` (8), `test_research_dashboard.py`
(7). Covers unit correctness for every metric (including edge cases: zero
losses, zero variance, insufficient samples), registry immutability
(structural), reproducibility (deterministic given the same input), and
graceful degradation on garbage/missing data. See
`DAY9_VALIDATION_REPORT.md` for the full breakdown and regression results.

## 14. Known limitations and backlog

1. **Slippage and variable/session-conditioned spread are not modeled** in
   `backtest.py` (Sec.4) — flagged as a candidate FUTURE EXPERIMENT (must
   pass through this Day's own lifecycle, not be silently added).
2. **No direct ref links a Stage-1 heads-up decision to its Stage-2 entry**
   (Sec.6) — `paper_trading_review.py`'s `proposed_vs_executed` reports
   `matches: None` for heads-up decisions rather than guessing.
3. **`experiment_registry.jsonl` contains zero real experiments today** —
   this framework is ready; no research has been logged through it yet
   (this Day's own backtest-quality review and the edge-decay finding in
   Sec.9.1 were NOT run through the registry, since neither proposes a
   production change — they are documentation and monitoring output, not
   experiments).
4. **The edge-decay finding in Sec.9.1 is unresolved** — explicitly an
   open item for Day 10+, not fixed this Day.
5. **`sharpe_like`/`sortino_like`/`calmar_like` are per-trade, not
   time-annualized** — disclosed by name and docstring, not a defect to
   fix without first establishing a clean time-annualization basis for an
   event-driven, multi-symbol platform (itself a candidate future
   experiment).
