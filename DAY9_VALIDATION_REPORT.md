# Day 9 Validation Report — Research & Statistical Validation Framework

## 1. Full suite results

```
cd gold-engine && python3 -m pytest -q
........................................................................ [ 20%]
........................................................................ [ 30%]
........................................................................ [ 40%]
........................................................................ [ 51%]
........................................................................ [ 61%]
........................................................................ [ 71%]
........................................................................ [ 81%]
........................................................................ [ 92%]
.......................................................                  [100%]
703 passed in 40.87s
```

620 baseline (post-Day-8) + 83 new = 703. **Zero failures, zero
regressions.**

## 2. New tests, by file

| File | Tests | Covers |
|---|---|---|
| `tests/test_research_stats.py` | 26 | input normalization (float list, dict rows, objects, garbage), every metric's basic correctness, sufficiency-flag boundaries, undefined/edge cases (zero losses for profit factor, zero variance for sharpe_like, no losses for sortino_like, no drawdown for calmar_like), `recovery_factor`≡`calmar_like`, stability-over-time consistent/inconsistent sign, `full_report()` completeness and garbage-input safety |
| `tests/test_evidence_tiers.py` | 10 | tier-boundary correctness, provisional-when-unassessed caveats, downgrade-on-non-representative, downgrade-on-inconsistent, double-downgrade floor, small-n-cannot-be-upgraded-by-good-context, garbage-input safety |
| `tests/test_experiment_registry.py` | 19 | `Hypothesis.is_complete()` boundary conditions, `log_idea()`/`propose()` (including incomplete-hypothesis disclosure), `transition()` (including invalid-stage disclosure), `current_state()` reconstruction, terminal-state detection, active/completed/rejected partition, permanent queryability of rejected experiments, immutability (never-mutated-in-place + structural no-mutator-function proof), lifecycle-stage/criteria completeness |
| `tests/test_walkforward_expanding_window.py` | 5 | basic shape, look-ahead-safety proof (train set never includes current/future trade), `window_size` rolling behavior, per-step error isolation, below-min_train empty result |
| `tests/test_edge_decay_monitor.py` | 8 | insufficient-data handling, sufficient recent-vs-prior comparison, decline flagging, no-flags-when-stable, garbage/empty-input safety, regime-conditioned pointer (not duplicate), every flag's recommendation text |
| `tests/test_paper_trading_review.py` | 8 | not-found handling, rejected/heads-up/approved-entry decision types, missing-trade_ref disclosure, trade_ref-based lookup, empty operational issues, garbage-input safety |
| `tests/test_research_dashboard.py` | 7 | required top-level keys, advisory-only framing, registry-state reflection, experiment-summary extraction, error isolation per section, evidence-tier/lifecycle-stage cross-references |

Isolated run (Day 9 files only): `83 passed`.

## 3. Regression check

The pre-existing 620 tests (Day 1-8) were re-run unmodified as part of the
full 703-test suite above — no pre-existing test file's assertions were
changed this Day. `engine/walkforward.py`'s existing tests
(`test_walkforward.py`, 3 tests) pass unmodified alongside the new
`test_walkforward_expanding_window.py` file, confirming the additive
change to that module broke nothing.

## 4. Manual verification

- **`git status --porcelain`** reviewed directly: all `??` entries for
  this Day correspond to the seven new modules and seven new test files
  plus `RESEARCH_VALIDATION_SPECIFICATION.md`/the three `DAY9_*.md`
  artifacts; no stray data files.
- **`ast.parse()` on every new/modified Python file** (`engine/
  research_stats.py`, `engine/evidence_tiers.py`,
  `engine/experiment_registry.py`, `engine/edge_decay_monitor.py`,
  `engine/paper_trading_review.py`, `engine/research_dashboard.py`,
  `engine/walkforward.py`) confirmed all parse cleanly.
- **Confirmed zero production-path references to any Day 9 module** —
  `grep -l` for `research_dashboard|experiment_registry|
  edge_decay_monitor|paper_trading_review|evidence_tiers|research_stats`
  against `alert_signals.py` and `engine/dashboard_publish.py` returned no
  matches. This is the structural proof behind
  `DAY9_IMPLEMENTATION_REPORT.md`'s "zero production files touched"
  claim, not just an assertion.
- **Re-ran `edge_decay_monitor.check()` against the live `trades.json`**
  directly, independent of the automated test suite (which only uses
  synthetic `rows=` fixtures): confirmed the four flags quoted in
  `RESEARCH_VALIDATION_SPECIFICATION.md` Sec.9.1 reproduce exactly
  (expectancy +1.22R -> -0.01R, profit factor 3.47 -> 0.99, drawdown
  -5.0R -> -12.0R, inconsistent recent sub-segments) — not a one-off
  fluke of the first run.
- **Confirmed `experiment_registry.py` exposes no mutator function** by
  direct inspection of its function list (`log_idea`, `propose`,
  `transition`, `history`, `current_state`, `all_experiment_ids`,
  `active_experiments`, `completed_experiments`, `rejected_experiments`,
  `tail`, `all_rows`, plus three private write/read helpers) — none named
  update/delete/overwrite/edit/modify/remove/patch.
- **Traced `expanding_window_series()`'s look-ahead safety manually**:
  confirmed the train set passed to `metric_fn` at step `i` is exactly
  `seq[:i]` (or `seq[i-window_size:i]`), never including `seq[i]` itself
  — same conclusion the dedicated test
  (`test_expanding_window_never_includes_current_or_future_trade`)
  reaches automatically.

## 5. Final Validation checklist (per the Day 9 mandate)

| Success criterion | Status |
|---|---|
| A permanent research workflow exists | Done — `experiment_registry.py`'s eleven-stage lifecycle, persisted immutably |
| Every future feature requires a documented hypothesis | Done — `Hypothesis` template with `is_complete()` check (recorded, not enforced — this framework governs research, not production) |
| Promotion from research to production follows a defined process | Done — `STAGE_CRITERIA` documents entry/exit criteria for every stage through `controlled_release` |
| Statistical evaluation is standardized | Done — `research_stats.py`'s ten metrics, shared vocabulary for backtest/paper-trading/experiment evaluation alike |
| Experiments are reproducible and traceable | Done — every metric is a pure function of its input; the registry's append-only history makes every experiment's full trail traceable |
| Production remains isolated from research | Done — zero production files modified this Day; verified by direct grep, not just documented |
| Documentation is complete | Done — `RESEARCH_VALIDATION_SPECIFICATION.md` (Research Spec, Validation Spec, Developer/Testing Guide sections all folded in), `ARCHITECTURE_SPECIFICATION.md` §19, `PROJECT_SUMMARY_AND_ROADMAP.md` |
| Automated tests pass with zero regressions | Done — 703/703 passing |

## 6. Known limitations carried forward (not defects — documented, scoped)

1. **`experiment_registry.jsonl` contains zero real experiments today** —
   the framework is ready; nothing has been run through it yet, honestly
   because this Day's own work (a documentation review and a monitoring
   run) doesn't itself propose a production change.
2. **The real edge-decay finding (Sec.9.1 of the spec) is unresolved** —
   explicitly flagged for the platform owner, not investigated or fixed
   this Day; see `DAY9_NEXT_DAY_READINESS_REPORT.md`.
3. **No direct ref links a Stage-1 heads-up to its Stage-2 entry** —
   `paper_trading_review.py` discloses this rather than guessing; flagged
   as a Day 10+ backlog item.
4. **Slippage and variable/session-conditioned spread are not modeled** in
   the existing `backtest.py` — documented as a finding of this Day's
   backtest-quality review, not fixed (would itself need to pass through
   this new framework as a proposed change).
5. **`sharpe_like`/`sortino_like`/`calmar_like` are per-trade, not
   time-annualized** — disclosed by naming convention and docstring.
