# Day 5 Validation Report — Adaptive Confluence Engine & Evidence Independence

## 1. Full suite results

```
cd gold-engine && python3 -m pytest -q
........................................................................ [ 16%]
........................................................................ [ 32%]
........................................................................ [ 49%]
........................................................................ [ 65%]
........................................................................ [ 82%]
........................................................................ [ 98%]
.....                                                                    [100%]
437 passed in 10.04s
```

390 baseline (post-Day-4) + 47 new = 437. **Zero failures, zero regressions.**

## 2. New tests, by file

| File | Tests | Covers |
|---|---|---|
| `tests/test_confluence_analysis.py` | 29 | Registry integrity, the hard label-matching regression test, `explain()`, `quality_score()`, `conflict_resolution()`, `measure_contribution()`, `recommend_weight_adjustments()`, `join_trades_with_confluence()` |
| `tests/test_confluence_history.py` | 6 | record/tail/rotation/fail-safety, all via `monkeypatch` on `HISTORY_PATH` |
| `tests/test_confluence_sandbox.py` | 12 | registration, stage progression, strict validation, import-isolation from `confluence.py` |

Isolated run (confluence-only): `47 passed in 2.53s`.

## 3. Regression check

The pre-existing 390 tests (Day 1-4) were re-run unmodified as part of the
full 437-test suite above — no test file from Day 1-4 was edited, and none
failed. `engine/confluence.py` itself has zero code changes, so no
regression surface was introduced there by construction; the new code
exists entirely in three new modules plus one additive function call in
`alert_signals.py`.

## 4. Manual verification

- **`git status --porcelain`** confirms no stray data-file pollution: the
  only untracked files are the intended Day 3/4/5 deliverables (new
  `engine/*.py`, new `tests/test_*.py`, new `*.md` docs); no stray
  `confluence_history.jsonl` or `confluence_sandbox.json` was left in the
  repo root by the test run (both point at `tmp_path` via monkeypatch in
  every test, per the same discipline established after Day 3's
  `correlation_cache.json` pollution incident).
- **`ast.parse()` on `alert_signals.py`** post-edit confirmed the file still
  parses cleanly.
- **Confirmed via direct `trades.json` query** (not assumed) that 99 of 102
  trade rows are closed, 10 carry a regime tag, and **zero** carry a
  populated `confluence_score`:
  ```
  total 102 / closed 99 / tagged 10 / confluence_score populated 0
  ```
  This directly grounds the "insufficient data" conclusion in both this
  report and `RESEARCH_CONFLUENCE_ENGINE.md`, rather than assuming it.
- **`inspect.getsource()` check** (via
  `test_confluence_module_never_imports_sandbox`) confirms
  `engine/confluence.py` contains no reference to `confluence_sandbox` in
  any form (checked both the literal module name and the lowercased word
  "sandbox") — the Phase 8 isolation guarantee is enforced by an automated
  test, not just a design intention.
- **Manually traced `log_confluence_explainability()`'s call sites** in
  `alert_signals.py`: confirmed it is called once at Stage-1 (heads-up,
  unconditional on tier) and once at Stage-2 (entry, inside the existing
  try/except), and that neither call path can affect `cr.score`,
  `cr.final_tier`, or the hard-gate `continue` logic that determines
  whether a signal publishes — the function only reads `cr` and writes to
  `confluence_history.jsonl`/the ledger.

## 5. Final Validation checklist (per the Day 5 mandate)

| Success criterion | Status |
|---|---|
| Documented purpose for every confluence source | Done — `SOURCE_REGISTRY` + `CONFLUENCE_SPECIFICATION.md` §1 |
| Overlap/duplication identified with evidence | Done — 3 named, code-verified findings (§2.1 of the spec) |
| Objective contribution-measurement framework exists | Done, built and tested — `measure_contribution()`/`recommend_weight_adjustments()` |
| Adaptive weighting designed but NOT allowed to alter production automatically | Done — zero write path from analysis code to `confluence.py`, verified structurally |
| More transparent trade explanations | Done — `explain()` + quality score + conflict detection, logged per trade |
| Production stability preserved | Done — 437/437 passing, `confluence.py` unmodified, additive-only integration |
| Tests pass with no regressions | Done — 437 passed, 0 failed |
| Complete documentation | Done — `CONFLUENCE_SPECIFICATION.md`, `RESEARCH_CONFLUENCE_ENGINE.md`, `ARCHITECTURE_SPECIFICATION.md` §15, `PROJECT_SUMMARY_AND_ROADMAP.md` |
| Future changes governed by measurable evidence, not intuition | Done — sandbox pipeline + 30-trade statistical bar before any recommendation is trusted |

## 6. Known limitations carried forward (not defects — documented, scoped)

1. **No real outcome data yet** — every `measure_contribution()` /
   `recommend_weight_adjustments()` call returns `"insufficient_data"` for
   all 26 sources today, because zero closed trades carry a
   `confluence_score`. This is the framework behaving correctly given the
   data that exists, not a code gap. See `RESEARCH_CONFLUENCE_ENGINE.md` §1.
2. **Point-value reconstruction is nominal, not exact**, for sources with
   conditional sub-weights (trend quality, Wyckoff, volume profile, news).
   Documented in three places (module docstring, spec §4/§9, research
   report §2.3); a future `confluence.py` change to persist exact deltas is
   flagged as a backlog item, not implemented (out of scope for "reuse,
   don't restructure").
3. **`regime_vol` is scored but unlabeled** in `confluence.py` (adds points
   with no `agree.append()`/`disagree.append()` call) — `explain()`
   surfaces this explicitly as `unlabeled_sources`, but cannot retroactively
   make it measurable by `measure_contribution()` without a small
   `confluence.py` change, also flagged as backlog.
4. **Quality-score category weights and formula weights are
   domain-reasonable, not statistically fitted** — same disclosure
   convention as Day 4's regime transition-risk weights. Calibration
   candidate once `confluence_history.jsonl` + labeled outcomes accumulate.
