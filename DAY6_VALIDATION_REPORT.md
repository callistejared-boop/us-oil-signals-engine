# Day 6 Validation Report — Confidence Engine (Calibrated Decision Quality)

## 1. Full suite results

```
cd gold-engine && python3 -m pytest -q
........................................................................ [ 14%]
........................................................................ [ 28%]
........................................................................ [ 42%]
........................................................................ [ 56%]
........................................................................ [ 70%]
........................................................................ [ 84%]
........................................................................ [ 98%]
.........                                                                [100%]
513 passed in 10.48s
```

437 baseline (post-Day-5) + 76 new = 513. **Zero failures, zero
regressions.**

## 2. New tests, by file

| File | Tests | Covers |
|---|---|---|
| `tests/test_confidence_engine.py` | 28 | `classify_tier()` boundaries/overrides, `assess()` basic/degraded/garbage-input behavior, sub-score composition (confluence quality, portfolio block, guard penalty, risk lock, no-double-counting), market/evidence quality, the full uncertainty-indicator checklist, explainability/rationale, `as_dict()`/`summary_line()` |
| `tests/test_confidence_history.py` | 10 | record/tail/rotation/fail-safety, dict-vs-object input, `find_by_ref()`, immutability of previously-written rows |
| `tests/test_confidence_calibration.py` | 21 | ref-preferred join with timestamp fallback, the T/space normalization regression guard, reliability/Brier computation, `calibrated_probability_for()`'s min_n gate, `recommend_recalibration()`'s bias flagging and advisory-only guarantee, rolling evaluation, report formatting |
| `tests/test_journal_confidence.py` | 7 | `make_ref()` format, `Trade` schema fields, `log_signal()` ref storage, backward-compatible reads of pre-Day-6 rows, `confluence_history.record()`'s new `ref` parameter |
| `tests/test_alert_signals_confidence.py` | 10 | `log_confidence_assessment()`'s record/log/fail-safe behavior, `log_confluence_explainability()`'s `ref` passthrough, the Telegram confidence line in both `build_entry()`/`build_prealert()` |

Isolated run (Day 6 files only): `76 passed in 3.21s`.

## 3. Regression check

The pre-existing 437 tests (Day 1-5) were re-run unmodified as part of the
full 513-test suite above. One test file was edited
(`tests/test_confluence_analysis.py`): the label-matching regression test
gained two new labels (`"regime volatility (expansion)"` / `"(normal)"`)
and one test was renamed/repurposed
(`test_explain_flags_regime_vol_as_unlabeled` →
`test_explain_regime_vol_no_longer_unlabeled`) to assert the Day 6 fix's
actual behavior instead of the Day 5 gap it closes — net test count in
that file unchanged, both edits are direct, intended consequences of the
approved `confluence.py` observability fixes, not incidental breakage.
No other pre-existing test file was modified.

## 4. Manual verification

- **`git status --porcelain`** confirms no stray data-file pollution: only
  the intended new/modified files appear; no stray `confidence_history.jsonl`
  was left in the repo root (every test points `HISTORY_PATH` at `tmp_path`
  via monkeypatch, same discipline as every prior day).
- **`ast.parse()` on every modified/new Python file** (`alert_signals.py`,
  `engine/journal.py`, `engine/confluence.py`, `engine/confluence_analysis.py`,
  `engine/confidence_engine.py`, `engine/confidence_history.py`,
  `engine/confidence_calibration.py`, `engine/dashboard_publish.py`,
  `engine/config.py`) confirmed all parse cleanly.
- **Re-queried `trades.json` directly** (not assumed) immediately before
  writing this report: 102 total rows, 99 closed, 0 with a populated
  `confluence_score`, 0 with a `confluence_ref`/`confidence_ref` set, and
  `confidence_history.jsonl` does not exist in the repo yet — all four
  facts underpin `RESEARCH_CONFIDENCE_ENGINE.md`'s central finding and were
  independently re-verified, not carried over from memory.
- **Manually traced the Stage-2 ENTRY integration** in `alert_signals.py`:
  confirmed `trade_ref` is computed once via `journal.make_ref()`, passed
  identically to `log_confluence_explainability(..., ref=trade_ref)`,
  `log_confidence_assessment(..., ref=trade_ref)`, and
  `journal.log_signal(..., confluence_ref=trade_ref, confidence_ref=trade_ref)`
  — so `trade.id == trade.confluence_ref == trade.confidence_ref` holds by
  construction for every future entry, not just in the isolated unit test.
- **Confirmed `ConfidenceAssessment` has no `allow`/`reject` field** by
  direct inspection of the dataclass definition and via
  `test_uncertainty_does_not_reject_the_trade` — the mandate's "without
  replacing any upstream decision" requirement is a structural property of
  the object, not just a documented intention.
- **Confirmed the two `confluence.py` observability fixes changed no
  score**: read the diff directly — both changes add an `agree.append()`
  call or a new dataclass field alongside an unchanged `score +=`
  statement; the full regression suite (437 pre-existing tests, all still
  passing) is independent confirmation that no downstream behavior
  (grading, gating, publication) shifted.

## 5. Final Validation checklist (per the Day 6 mandate)

| Success criterion | Status |
|---|---|
| A centralized Confidence Engine exists | Done — `engine/confidence_engine.py` |
| Reuses existing system outputs rather than duplicating logic | Done — every input to `assess()` is a parameter, never re-fetched; verified no double-counting of Layer 1 |
| Confidence assessments are transparent and explainable | Done — `explain`-style rationale, uncertainty indicators, highest/lowest-impact evidence, assumptions, all on every assessment |
| Confidence history is persisted for future calibration | Done — `confidence_history.jsonl`, immutable append-only, `find_by_ref()` |
| Trade journal contains direct references to confluence and confidence data | Done — `Trade.confluence_ref`/`confidence_ref`, exact-match join preferred over timestamp fallback |
| Approved observability enhancements implemented without changing production scoring | Done — `regime_vol` labeling + exact `news_delta` persistence, zero score/gate changes, confirmed by full regression suite |
| Confidence clearly distinguished from statistically validated probability | Done — `is_calibrated`/`calibrated_probability`/`probability_label` on every assessment; `False`/`None`/explicit-uncalibrated-text today, by design |
| All automated tests pass with zero regressions | Done — 513/513 passing |
| Documentation is complete | Done — `CONFIDENCE_ENGINE_SPECIFICATION.md`, `RESEARCH_CONFIDENCE_ENGINE.md`, `ARCHITECTURE_SPECIFICATION.md` §16, `PROJECT_SUMMARY_AND_ROADMAP.md` |
| A calibration plan is established for future live-data validation | Done — `confidence_calibration.py`'s full reliability/Brier/recalibration/rolling-evaluation framework, gated at n≥30, documented rollout in the research report |

## 6. Known limitations carried forward (not defects — documented, scoped)

1. **Zero real calibration data exists yet** — `is_calibrated=False` on
   every assessment made today, by design; this is the framework working
   correctly given the data that exists, not a code gap. See
   `RESEARCH_CONFIDENCE_ENGINE.md` §1.
2. **The composite formula's weights are engineering judgment, not
   statistically fitted** — disclosed on every single `ConfidenceAssessment`
   via its own `assumptions` field, plus documented in the spec and
   research report; `recommend_recalibration()` is the designed (never
   automatic) path to revising them once data exists.
3. **Regime history is still timestamp-joined, not ref-joined** — the Day 6
   mandate's "Trade Journal Integration" section scoped the direct-reference
   work to confluence and confidence specifically; regime was left
   unchanged and is flagged as a Day 7+ backlog item, not silently
   inconsistent without comment.
4. **`dashboard_publish.py`'s confidence block independently recomputes
   regime/portfolio reads** rather than sharing state with
   `alert_signals.py`'s scan — unavoidable across separate OS processes,
   consistent with this file's pre-existing pattern for `regime.classify()`
   and `cf.analyze()`.
5. **`base_evidence`'s five-term composite formula cannot be independently
   validated term-by-term at current trade volumes** — only the aggregate
   score's bucket-level calibration is realistically checkable in the near
   term; see `RESEARCH_CONFIDENCE_ENGINE.md` §6 for the full statistical
   caveat.
