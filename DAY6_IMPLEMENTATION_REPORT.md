# Day 6 Implementation Report — Confidence Engine (Calibrated Decision Quality)

Full design detail: `CONFIDENCE_ENGINE_SPECIFICATION.md`. Research:
`RESEARCH_CONFIDENCE_ENGINE.md`.

## New files

- `engine/confidence_engine.py` — `ConfidenceAssessment` dataclass, `assess()`
  (main entry point), `classify_tier()`, and the internal
  `_evidence_quality()`/`_market_quality()`/`_uncertainty_indicators()`/
  `_rationale()` helpers. Consumes `sig`, `mkt_regime`, `cr`,
  `portfolio_verdict`, `guard`, `news_state`, `session`, `risk_locked` —
  all already-computed upstream objects, never re-fetched.
- `engine/confidence_history.py` — append-only JSONL log of every
  assessment, mirroring `regime_history.py`/`confluence_history.py`'s
  exact pattern. `record()`, `tail()`, `all_rows()`, `find_by_ref()`.
- `engine/confidence_calibration.py` — `join_trades_with_confidence()`,
  `reliability()`, `brier()`, `calibrated_probability_for()`,
  `recommend_recalibration()`, `rolling_evaluation()`, `report()`. Mirrors
  the pre-existing `calibration.py`'s methodology rather than inventing a
  new one.
- `tests/test_confidence_engine.py` (28 tests), `tests/test_confidence_history.py`
  (10 tests), `tests/test_confidence_calibration.py` (21 tests),
  `tests/test_journal_confidence.py` (7 tests),
  `tests/test_alert_signals_confidence.py` (10 tests) — 76 total.
- `CONFIDENCE_ENGINE_SPECIFICATION.md`, `RESEARCH_CONFIDENCE_ENGINE.md`.

## Modified files

- `engine/journal.py` — added `make_ref(symbol, when)` (extracted from the
  existing inline `id` construction so callers can compute the identical
  string ahead of time) and two new `Trade` fields, `confluence_ref`/
  `confidence_ref` (both default `""`). `log_signal()` gained matching
  optional keyword parameters.
- `engine/confluence.py` — two small, additive, approved observability
  fixes (see "Explicit decisions" #5 below): `regime_vol` is now labeled
  in `agree`/`disagree`; `ConfluenceRead` gained a `news_delta: int = 0`
  field, set from the already-computed `bias_adjust.adjustment()` value.
  No score, weight, or gate changed.
- `engine/confluence_analysis.py` — `LABEL_PATTERNS` gained a `regime_vol`
  entry; `explain()`'s hard-coded `unlabeled_sources: ["regime_vol"]` now
  reflects the fix (always `[]`); `_source_points()` uses the real
  `cr.news_delta` for the `"news"` source instead of a nominal
  approximation; `join_trades_with_confluence()` now prefers a direct
  `Trade.confluence_ref` match before falling back to its original
  nearest-timestamp join.
- `alert_signals.py` — added `confidence_engine as confeng, confidence_history
  as cfdh` to the engine import block. Added `log_confidence_assessment()`
  (assembles + persists one assessment, fail-safe, mirrors
  `log_confluence_explainability()`'s posture) and extended
  `log_confluence_explainability()` with an optional `ref` parameter.
  Wired at both Stage-1 (heads-up, `ref=""`) and Stage-2 (entry,
  `ref=trade_ref` — computed once via `journal.make_ref()` and reused for
  the confluence log, the confidence log, and the trade row itself).
  `build_entry()`/`build_prealert()` gained an optional `confidence=`
  parameter that adds one line to the Telegram message when present.
- `engine/dashboard_publish.py` — added a read-only `confidence_assessment`
  block to the per-symbol `signal_payload`, computed from a fresh
  `regime_engine.classify()` + `portfolio_risk.evaluate()` call (this
  process cannot share `alert_signals.py`'s in-scan objects — separate OS
  processes) plus the already-computed `sig`/`cread`/`guard`/`rguard`.
  Fail-safe: `confidence_payload = None` on any error, never blocks the
  rest of the payload.
- `engine/config.py` — added the Day 6 `confidence_tier_low/moderate/high/
  exceptional` fields (defaults 40/55/70/85, documented rationale inline).
- `ARCHITECTURE_SPECIFICATION.md` — new §16.
- `PROJECT_SUMMARY_AND_ROADMAP.md` — new "Day 6" section.
- `tests/test_confluence_analysis.py` — updated the label-matching
  regression test to include the two new `regime_vol` labels; replaced
  `test_explain_flags_regime_vol_as_unlabeled` with
  `test_explain_regime_vol_no_longer_unlabeled` (same test count, updated
  to assert the Day 6 behavior instead of the Day 5 gap it closes).

## Explicit decisions made (documented, not silently resolved)

1. **The Confidence Engine has no `allow`/`reject` field and cannot gate a
   trade.** Confirmed structurally (`test_uncertainty_does_not_reject_the_trade`)
   rather than just by convention — this is the literal, load-bearing
   interpretation of "does not create trade ideas... without replacing any
   upstream decision."
2. **`base_evidence` uses `cr.score` OR `sig.confidence`, never both
   summed.** `cr.score` already embeds Layer 1's confidence at 45% weight;
   adding `sig.confidence` again would reproduce, at this new layer,
   exactly the echo problem Day 5's audit found in MAST. Verified by a
   dedicated test.
3. **The composite formula's weights are disclosed engineering judgment,
   not statistically fitted** — same convention as Day 4's transition-risk
   weights and Day 5's quality-score weights. Every `ConfidenceAssessment`
   carries this disclosure in its own `assumptions` field, not just in
   documentation a user might not read.
4. **`is_calibrated` is `False` on every assessment today, by design.**
   `confidence_calibration.calibrated_probability_for()` requires ≥30 real
   matched outcomes per bucket; `confidence_history.jsonl` starts empty at
   this deployment. `probability_label` states this explicitly on every
   single assessment, not just in a report a user might not read.
5. **Two small `confluence.py` touches were made, with explicit go-ahead
   from the platform owner's Day 6 mandate** ("Implement the previously
   approved additive improvements... These additions must increase
   transparency only. They must not change existing scoring behavior.") —
   this was the first `confluence.py` edit since the Day 5 audit
   established "the goal is not to replace MAST," and it was scoped
   exactly to what the mandate pre-approved: labeling `regime_vol` and
   persisting `news_delta`. Neither changes `score`, a gate, or
   `final_tier`; verified by the full regression suite showing zero
   changed outcomes elsewhere.
6. **`journal.py`'s schema gap was closed exactly as scoped** ("Extend the
   trade journal so each trade contains a direct reference to the
   corresponding confluence and confidence records... Maintain backward
   compatibility or provide a documented migration path") — no migration
   script was needed because `journal.py` already reads rows as plain
   dicts with `.get()` defaults throughout; this is documented explicitly
   in `CONFIDENCE_ENGINE_SPECIFICATION.md` §9.1 rather than left implicit.
7. **`dashboard_publish.py` independently calls `regime_engine.classify()`
   and `portfolio_risk.evaluate()`** rather than trying to share state with
   `alert_signals.py`'s scan loop — impossible across separate OS
   processes, and consistent with the "each entry point computes its own
   read" pattern this codebase already used for `regime.classify()` and
   `cf.analyze()` in that same file before Day 6.
8. **Regime history was NOT given a `ref` parameter this Day** — the
   mandate's "Trade Journal Integration" section scoped this to confluence
   and confidence specifically ("previously discussed enhancement"); regime
   remains timestamp-joined, flagged as a Day 7+ backlog item in
   `DAY6_NEXT_DAY_READINESS_REPORT.md` rather than silently left
   inconsistent without comment.

## What was explicitly NOT touched

- ICT/SMC origination (`signals.py`) — unchanged.
- The Market Regime Engine (`regime_engine.py`) — unchanged.
- MAST confluence scoring, hard gates, and checklist (`confluence.py`'s
  `analyze()` core logic) — unchanged; the two additive fixes above touch
  only label text and a new persisted field, never `score` math.
- The Portfolio Risk Engine (`portfolio_risk.py`) — unchanged.
- `hourly_briefing.py` — not modified; it does not call `confluence.analyze()`
  directly, so there is no confluence/confidence read to attach there,
  matching Day 5's identical precedent for the same file.
- No production behavior changed: no signal that would have published
  before Day 6 is now rejected, delayed, held, or resized differently.
