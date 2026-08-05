# Day 9 Implementation Report — Research & Statistical Validation Framework

Full design detail: `RESEARCH_VALIDATION_SPECIFICATION.md`.

## New files

- `engine/research_stats.py` — `expectancy()`, `profit_factor()`,
  `win_rate()`, `avg_r_multiple()`, `max_drawdown()`, `sharpe_like()`,
  `sortino_like()`, `calmar_like()`, `recovery_factor()`,
  `stability_over_time()`, `full_report()`. Every metric a pure function
  of an R-multiple list.
- `engine/evidence_tiers.py` — `TIERS`, `evidence_tier()`, `assess()`.
  Five-tier, non-rigid sample-size policy.
- `engine/experiment_registry.py` — `LIFECYCLE_STAGES`, `TERMINAL_STAGES`,
  `STAGE_CRITERIA`, `Hypothesis` dataclass, `log_idea()`, `propose()`,
  `transition()`, `history()`, `current_state()`, `all_experiment_ids()`,
  `active_experiments()`, `completed_experiments()`,
  `rejected_experiments()`, `tail()`, `all_rows()`.
- `engine/edge_decay_monitor.py` — `recent_vs_prior()`, `check()`.
- `engine/paper_trading_review.py` — `evaluate()`, plus internal
  `_proposed_vs_executed()`/`_operational_issues()`.
- `engine/research_dashboard.py` — `build_research_payload()`.
- `tests/test_research_stats.py` (26 tests), `tests/test_evidence_tiers.py`
  (10 tests), `tests/test_experiment_registry.py` (19 tests),
  `tests/test_walkforward_expanding_window.py` (5 tests),
  `tests/test_edge_decay_monitor.py` (8 tests),
  `tests/test_paper_trading_review.py` (8 tests),
  `tests/test_research_dashboard.py` (7 tests) — 83 total.
- `RESEARCH_VALIDATION_SPECIFICATION.md`.

## Modified files

- `engine/walkforward.py` — added `expanding_window_series(metric_fn,
  closed=None, min_train=30, window_size=None)`, appended after every
  existing function. Nothing in the file's original 92 lines (raw_model/
  base_model/calibrated_model/rolling_brier/compare/report) changed.
- `ARCHITECTURE_SPECIFICATION.md` — new §19.
- `PROJECT_SUMMARY_AND_ROADMAP.md` — new "Day 9" section.

**No other file was touched.** In particular, `alert_signals.py`,
`engine/dashboard_publish.py`, `engine/confidence_engine.py`,
`engine/portfolio_risk.py`, `engine/regime_engine.py`,
`engine/confluence.py`, `engine/explainability_engine.py`, and
`engine/decision_audit_history.py` are all byte-for-byte unchanged from
the end of Day 8 — the structural proof behind this framework's "does not
change production trading behavior" claim.

## Explicit decisions made (documented, not silently resolved)

1. **`walkforward.py` was extended additively, not replaced.** The
   mandate asked for a "standardized walk-forward methodology"; the
   platform already had one (Day 1-2's expanding-window Brier comparison).
   Rather than build a second, competing implementation,
   `expanding_window_series()` generalizes the SAME look-ahead-safe
   iteration to any metric function — reuse over duplication, per this
   codebase's standing discipline.
2. **`research_stats.py` deliberately does NOT modify
   `backtest.py::summarize()`**, which already computes some of the same
   numbers inline. `backtest.py`'s validated behavior is untouched per the
   mandate's own "changing behavior... unless justified" instruction — no
   justification was found. `research_stats.py` is a separate, richer,
   reusable layer any future research branch can call regardless of
   whether its data came from `backtest.py`, `trades.json`, or its own log.
3. **`sharpe_like`/`sortino_like`/`calmar_like` are named with an explicit
   `_like` suffix**, not `sharpe`/`sortino`/`calmar` — because this
   platform has no clean time-annualization basis for an event-driven,
   multi-symbol trade sequence. Naming them as if they were the standard,
   cross-system-comparable ratios would be a false-precision claim this
   codebase's disclosure culture explicitly avoids elsewhere (e.g.
   Day 6's `probability_label`, Day 7's `MemoryRecord` completeness
   fields).
4. **`evidence_tiers.assess()` can downgrade but never upgrade** a
   size-only tier. This was a deliberate asymmetry: the mandate says
   "avoid rigid numerical thresholds where statistical context matters,"
   which could be read as "let good context compensate for a small
   sample" — that reading was rejected, because no amount of
   representativeness can make an 8-trade sample statistically
   trustworthy. Context can only ever make a large sample WORSE than its
   size alone would suggest, never better.
5. **`active_experiments()` excludes `ongoing_monitoring`** even though
   that stage is not in `TERMINAL_STAGES` (monitoring has no defined exit
   — see `STAGE_CRITERIA`). This was caught and fixed during testing
   (`test_active_completed_rejected_partition` initially failed because an
   experiment in `ongoing_monitoring` appeared in both `active_
   experiments()` and `completed_experiments()`) — resolved by making
   "active" mean "still progressing through the pre-monitoring lifecycle,"
   distinct from `current_state()`'s own stricter `is_terminal` field,
   which a caller wanting the terminal-only distinction can still use
   directly.
6. **`paper_trading_review.py` does not attempt a heuristic heads-up-to-
   entry match.** A nearest-timestamp/price heuristic was considered and
   rejected in favor of explicitly reporting `matches: None` with a note —
   this codebase's Day 4/5 precedent (nearest-timestamp joins later
   replaced by Day 6 direct refs) shows that approximate joins get
   replaced by exact ones over time; inventing a NEW approximate join for
   a brand-new gap, when the exact-ref pattern is already proven three
   times over (regime/confluence/confidence), was judged worse than
   disclosing the gap and flagging the direct-ref extension as a Day 10+
   backlog item.
7. **`research_dashboard.py` is never imported by any production file.**
   Verified directly (grepped `alert_signals.py`/`dashboard_publish.py`
   for `research_dashboard` — zero matches) rather than merely documented,
   giving the "keep research clearly separated from production" mandate
   requirement a structural guarantee, not just an intention.
8. **The real edge-decay finding (Sec.9.1 of the spec) was reported, not
   acted on.** Running `edge_decay_monitor.check()` against the live
   `trades.json` surfaced four real flags. Per the mandate's own governing
   principle, this framework recommends investigation and nothing more —
   no threshold, config value, or production file was changed as a result.

## What was explicitly NOT touched

- `alert_signals.py`, `engine/dashboard_publish.py` — zero changes.
- Every Day 3-8 engine module (`portfolio_risk.py`, `regime_engine.py`,
  `confluence.py`, `confidence_engine.py`, `market_memory.py`,
  `explainability_engine.py`, `decision_audit_history.py`,
  `platform_version.py`) — zero changes.
- `engine/backtest.py`, `engine/montecarlo.py`, `engine/calibration.py`,
  `engine/confidence_calibration.py` — reviewed in depth (see
  `RESEARCH_VALIDATION_SPECIFICATION.md` Sec.4) but not modified; no
  justification for a behavior change was found.
- `engine/walkforward.py`'s pre-existing functions — additive-only change.
- No production behavior changed: this is the first Day where that
  statement is true of the ENTIRE Day's work, not just the new module —
  every prior Day added at least one integration touch-point into
  `alert_signals.py`/`dashboard_publish.py`; Day 9 adds none, by design.
