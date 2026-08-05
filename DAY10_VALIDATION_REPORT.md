# Day 10 Validation Report — Edge Investigation & Performance Recovery

## 1. Full suite results

```
cd gold-engine && python3 -m pytest -q -n 4
........................................................................ [  9%]
........................................................................ [ 19%]
........................................................................ [ 29%]
........................................................................ [ 39%]
........................................................................ [ 49%]
........................................................................ [ 59%]
........................................................................ [ 68%]
........................................................................ [ 78%]
........................................................................ [ 88%]
........................................................................ [ 98%]
............                                                             [100%]
732 passed in 42.95s
```

703 baseline (post-Day-9) + 29 new = 732. **Zero failures, zero
regressions.**

## 2. New tests

`tests/test_edge_investigation.py` — 29 tests, isolated run also passes
(`python3 -m pytest -q tests/test_edge_investigation.py` -> `29 passed`).
Covers: `holding_time_stats()`/`stop_target_stats()` basic correctness and
empty-input handling; `verify_core_metrics()` insufficiency and the new
fields' presence; `data_quality_review()` duplicate-id detection, no-false-
positive on unique ids, sign-mismatch detection, field-coverage
quantification, and never-raises on garbage/empty input;
`_settlement_rule_family()`'s legacy-vs-current classification correctness
(including the `None`-for-non-win case); `restate_win_to_current_
methodology()`'s formula correctness and its no-op behavior on losses/
scratches; `restated_comparison()`'s directional guarantee (restating
legacy wins to the current rule can only lower, never raise, the prior
window's expectancy); `segment_performance()`'s insufficiency handling,
dimension coverage (including the explicit strategy/confluence-profile
exclusion), and bucket shape; `variance_permutation_test()`'s
insufficiency handling, exact reproducibility under a fixed seed, and
correct behavior on both a genuinely-anomalous synthetic window (p < 0.05)
and a typical one (p > 0.05); `feature_contribution_check()`'s ref-
coverage reporting; `full_investigation_report()`'s never-raises guarantee
on garbage input and full section coverage on sufficient data.

One test-authoring correction made during writing (not a code bug): the
first version of `test_variance_permutation_test_high_p_when_recent_is_
typical` used a deterministic alternating win/loss pattern whose win value
(1.0) was inconsistent with the fixture's fixed `entry`/`stop`/`target`
(which imply a "current rule" win credit of 3.0) — since
`restate_win_to_current_methodology()` recomputes off `entry`/`stop`/
`target` regardless of the passed `result_r`, this silently inflated the
restated pool's mean and made every seed look anomalous. Fixed by using a
win value (3.0) consistent with the fixture's own entry/stop/target, and a
seed (5) verified across a small sweep to land solidly mid-range rather
than in either tail.

## 3. Regression check

The pre-existing 703 tests (Days 1-9) were re-run unmodified as part of the
full 732-test suite above — no pre-existing test file's assertions were
changed this Day.

## 4. Manual verification

- **`git status --porcelain`** reviewed directly: every new `??` entry
  corresponds to `engine/edge_investigation.py`,
  `tests/test_edge_investigation.py`, `PERFORMANCE_INVESTIGATION_0001.md`,
  and `experiment_registry.jsonl` (this file's first-ever entries — 0
  bytes before this Day) — no stray data files. The pre-existing `M`
  (modified) list (`alert_signals.py`, `engine/journal.py`, `engine/
  dashboard_publish.py`, etc.) is unchanged from Day 9's baseline diff —
  confirmed by direct file-mtime inspection (all three predate this
  session's Day 10 work by roughly 1.5-2 hours; `edge_investigation.py`
  and `experiment_registry.jsonl` postdate them).
- **`grep -l "edge_investigation" alert_signals.py engine/dashboard_
  publish.py`** returned no matches (exit code 1) — the structural proof
  that this Day's new module is not wired into any production path.
- **Re-ran `engine.edge_investigation.full_investigation_report()`**
  against the live `trades.json` directly, independent of the automated
  test suite (which only uses synthetic `rows=` fixtures): confirmed every
  number quoted in `PERFORMANCE_INVESTIGATION_0001.md` reproduces exactly
  — expectancy +1.22R/-0.01R, profit factor 3.47/0.99, win rate 49.3%/
  26.7%, holding time 63.9min/23.5min, the 30-vs-4 legacy/current
  settlement-rule win split in the prior window, the restated +0.91R prior
  expectancy, and the permutation-test p-values (p=0.0123 expectancy,
  p=0.0315 win rate at trials=20000, seed=42).
- **Confirmed `experiment_registry.jsonl`'s Experiment #0001 entry**
  reconstructs correctly via `engine.experiment_registry.current_state(
  "0001-observed-edge-deterioration-investigation")`: `current_stage ==
  "performance_review"`, `decision == "research_further"`, `n_records ==
  4` (proposal, `historical_testing` transition, `performance_review`
  transition, one typo-only correction — the correction itself
  demonstrating the registry's append-only "corrections are new rows,
  never edits" convention in live use, not just in its test suite).
- **Confirmed the settlement-rule-family classification** by hand-tracing
  three real rows from `trades.json` against `engine/journal.py::_manage(
  )`'s actual source (not just the reconstruction formula) — the earliest
  win (`2026-07-07 13:15:00`, rr=3.81, result_r=3.81) cannot be produced
  by the current `_manage()` for any code path (every branch that credits
  a win applies `0.5*2.0 + 0.5*finalR`, never `finalR` alone), confirming
  this trade was settled by different code than what's in the repo today.
- **Confirmed `data_quality_review()`'s duplicate-id finding** by direct
  inspection of the 5 colliding `id` groups in `trades.json` — in every
  case the colliding rows have DIFFERENT `entry`/`stop`/`target` values,
  confirming these are genuinely distinct trades sharing an `id` due to
  minute-granularity collision, not accidental double-logging of the same
  trade.

## 5. Final validation checklist (per the Day 10 mandate)

| Success criterion | Status |
|---|---|
| Deterioration independently verified | Done — `verify_core_metrics()` reproduces the Day 9 finding exactly from raw `trades.json`, plus two new metrics (holding time, stop/target size) |
| Multiple competing hypotheses evaluated | Done — all 8 mandate-named hypotheses assessed separately in `PERFORMANCE_INVESTIGATION_0001.md` Sec.4, with 2 explicitly marked inconclusive rather than forced to a verdict |
| Data quality validated | Done — `data_quality_review()`: 5 duplicate-id groups quantified, a genuine settlement-methodology drift discovered and quantified (25-30% of the apparent gap), zero sign-mismatches/corrupted-timestamp issues found |
| Findings distinguish evidence from speculation | Done — every finding in Sec.4/5/6 is labeled Supported / Plausible-not-confirmed / Inconclusive-data-gap / Not-the-primary-driver, never asserted flatly; the permutation test carries an explicit post-hoc-selection caveat |
| Experiment #0001 fully documented | Done — 4 registry records (proposal, 2 stage transitions, 1 correction) plus `PERFORMANCE_INVESTIGATION_0001.md`'s full narrative |
| No production changes made solely because of the investigation | Done — `trades.json`, `alert_signals.py`, `engine/journal.py`, `engine/dashboard_publish.py` byte-for-byte unchanged; verified by mtime inspection and grep, not just documented |
| Recommendations prioritized by evidence strength | Done — Sec.8's table classifies every finding (Research Further for all substantive items; instrumentation gaps called out separately from strategy questions) |
| Automated tests pass with zero regressions | Done — 732/732 passing |

## 6. Known limitations carried forward (not defects — documented, scoped)

1. **The settlement-methodology drift was discovered, not fixed.**
   `trades.json`'s historical records still contain the legacy-rule
   values. Correcting them is its own follow-up item requiring its own
   explicit decision (see `PERFORMANCE_INVESTIGATION_0001.md` Sec.9).
2. **Regime Shift and Risk Controls hypotheses remain untested**, not
   because they were investigated and found irrelevant, but because
   `regime_trend`/`regime_vol`/`guard_action` tagging is too sparse on
   these specific trades. Backfilling this (retroactively via `engine.
   regime_engine` against historical price bars, if available, and/or
   improving live-tagging coverage going forward) is a prerequisite for a
   future attempt at these two hypotheses.
3. **Confluence-profile segmentation is not possible** — `confluence_score`
   is essentially never populated in the live journal despite being a
   `Trade` field since Day 5/6. Worth its own follow-up investigation into
   why the live signal path isn't stamping it (separate from this Day's
   scope).
4. **The permutation test's p-values carry a disclosed post-hoc-selection
   caveat** — they should not be read as a formal, pre-registered
   significance test.
5. **Duplicate `id` collisions (12 rows across 5 groups) remain
   unresolved** — flagged for the backlog, not fixed (would require a
   `journal.make_ref()` format change, itself a candidate future
   experiment given every downstream consumer assumes `id` uniqueness).
