# Day 10 Implementation Report — Edge Investigation & Performance Recovery

Full analytical detail: `PERFORMANCE_INVESTIGATION_0001.md`.

## New files

- `engine/edge_investigation.py` — the analytical code behind Experiment
  #0001: `holding_time_stats()`, `stop_target_stats()`,
  `verify_core_metrics()`, `data_quality_review()`,
  `_settlement_rule_family()`, `restate_win_to_current_methodology()`,
  `restated_comparison()`, `segment_performance()`,
  `variance_permutation_test()`, `feature_contribution_check()`,
  `full_investigation_report()`.
- `tests/test_edge_investigation.py` — 29 tests, all offline (explicit
  `rows=` fixtures, nothing touches the real `trades.json`).
- `PERFORMANCE_INVESTIGATION_0001.md` — the full investigation write-up.

## Modified files

- `experiment_registry.jsonl` — 4 new records (this file's first-ever
  entries): `propose()` for Experiment #0001 with a complete `Hypothesis`,
  a `historical_testing` transition (verification + data-quality
  evidence), a `performance_review` transition (segment/root-cause/
  variance/feature-contribution evidence, `decision="research_further"`),
  and one typo-only correction transition (new row per the registry's
  own immutability convention — see `experiment_registry.py`'s module
  docstring — never an edit).
- `ARCHITECTURE_SPECIFICATION.md` — new §20.
- `PROJECT_SUMMARY_AND_ROADMAP.md` — new "Day 10" section, plus the
  platform owner's requested permanent process rule (every 10
  implementation days, one dedicated Research & Validation day before new
  production capability) recorded as standing project policy.

**No other file was touched.** In particular, `trades.json`,
`alert_signals.py`, `engine/journal.py`, `engine/dashboard_publish.py`, and
every Day 1-9 engine module are byte-for-byte unchanged from the end of
Day 9 — the structural proof behind this Day's "no production change"
success criterion.

## Explicit decisions made (documented, not silently resolved)

1. **`edge_investigation.py` is entirely read-only against `trades.json`**,
   using the exact same access pattern `engine.edge_decay_monitor` already
   established (`store.load_array(journal.STORE)`). No new write path to
   the journal was created, and none was needed — this is an investigation,
   not a correction.
2. **The settlement-methodology drift is quantified via a `restated`
   comparison, not by editing `trades.json`.** Actually rewriting the
   historical R-multiples in the live journal was considered and rejected
   for this experiment: it would be a real, consequential data change that
   deserves its own explicit decision and its own experiment-registry
   entry, not something that happens as a side effect of an investigation
   whose stated job is to determine causes, not apply fixes. Flagged as a
   Day 10+ backlog item instead (see `PERFORMANCE_INVESTIGATION_0001.md`
   Sec.8).
3. **Two of the eight named root-cause hypotheses (Regime Shift, Risk
   Controls) were left EXPLICITLY marked "inconclusive — data gap"**
   rather than forced to a verdict. `regime_trend`/`regime_vol`/
   `guard_action` are populated on too few trades (0% in the prior window
   for all three) to responsibly test either hypothesis from trade-level
   tags. Reporting "inconclusive" honestly was judged more valuable than
   a false-precision verdict — consistent with this codebase's disclosure
   culture (Day 6's `probability_label`, Day 9's `sharpe_like` naming).
4. **The statistical-variance permutation test uses the METHODOLOGY-
   RESTATED pool**, not the as-stored data. Using as-stored data would let
   the settlement-methodology drift (item 2 above) leak into the variance
   test and inflate how "anomalous" the recent window looks for a reason
   unrelated to statistical variance itself. Restating first isolates the
   two questions properly.
5. **The permutation test's result is reported with an explicit post-hoc-
   selection caveat**, not just a bare p-value. The recent window was
   examined specifically because Day 9's monitor already flagged it as
   anomalous — presenting the p-value without that caveat would overstate
   how decisive the test is. This mirrors this codebase's standing
   "disclose, don't overclaim" convention (Day 9's `sharpe_like` naming,
   Day 7's `data_completeness` fields).
6. **Confluence Profile and Strategy Mix segmentation were not attempted**
   — not silently skipped, but explicitly reported as data-completeness
   gaps in `segment_performance()`'s own `note` field
   (`confluence_score` is unpopulated on effectively every trade; the
   platform runs one production strategy at a time by design, so "mix"
   cannot be observed as a trade-level dimension under current
   instrumentation).
7. **Experiment #0001 is progressed to `performance_review`, not further**
   — not `production_recommendation`/`controlled_release`, since nothing
   here proposes a production change to approve, and not a terminal state
   (`rejected`/`rolled_back`), since the investigation's own conclusion is
   "research further," not "stop" or "done." `performance_review`'s own
   stage-exit criterion ("a documented promotion decision with explicit
   rationale exists") is satisfied by the `decision="research_further"`
   field on the final transition record.
8. **The counterfactual analysis for advisory-on/off is reported as a
   degenerate null result, not an unrun analysis.** Since
   `feature_contribution_check()` shows 0% ref-linkage between these
   trades and any Day 6/7/8 advisory output, there is no configuration
   under which the recorded outcomes could differ — this was worth stating
   explicitly rather than leaving the counterfactual section blank.

## What was explicitly NOT touched

- `trades.json`, `alert_signals.py`, `engine/journal.py`,
  `engine/dashboard_publish.py` — zero changes.
- Every Day 1-9 engine module — zero changes.
- No threshold, config value, or trading behavior changed as a result of
  this investigation — the Day 10 mandate's hard success criterion.
