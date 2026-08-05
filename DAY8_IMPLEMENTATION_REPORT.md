# Day 8 Implementation Report — Explainability Engine & Decision Audit System

Full design detail: `EXPLAINABILITY_SPECIFICATION.md`. Research:
`RESEARCH_EXPLAINABILITY.md`.

## New files

- `engine/platform_version.py` — `PLATFORM_VERSION`, `ARCHITECTURE_VERSION`,
  `COMPONENT_MODULES`, `component_versions()`, `snapshot()`. Single source
  of truth for version/configuration traceability.
- `engine/explainability_engine.py` — `DecisionSnapshot` dataclass;
  `DECISION_STAGES`; the rejection-category vocabulary (`WEAK_EVIDENCE`,
  `INSUFFICIENT_HISTORICAL_CONTEXT`, `RISK_LOCK`, `NEWS_BLACKOUT`, plus
  `engine.portfolio_risk`'s existing ten reused directly);
  `CONFIG_FIELDS`/`config_snapshot()`; `build_decision_snapshot()`;
  `build_audit_graph()`; `DATA_LINEAGE_MAP`/`lineage_for_snapshot()`;
  `explain_approval()`/`explain_rejection()`/the two
  `_hypothetical_*` helpers/`_limitations()`; `post_trade_review()`/
  `_review_recommendations()`; `replay()`.
- `engine/decision_audit_history.py` — `record()`, `record_correction()`,
  `tail()`, `all_rows()`, `find_by_ref()`, `find_by_trade_ref()`,
  `history_for_ref()`. No update/delete function of any kind.
- `tests/test_platform_version.py` (5 tests), `tests/test_decision_audit_history.py`
  (15 tests), `tests/test_explainability_engine.py` (19 tests),
  `tests/test_replay.py` (5 tests), `tests/test_post_trade_review.py`
  (7 tests) — 51 total.
- `EXPLAINABILITY_SPECIFICATION.md`, `RESEARCH_EXPLAINABILITY.md`.

## Modified files

- `engine/signals.py`, `engine/regime_engine.py`, `engine/confluence.py`,
  `engine/portfolio_risk.py` — each gained a retroactive `VERSION`
  constant (`"1.0.0"` for signals/confluence/portfolio_risk, `"2.0.0"` for
  regime_engine matching its own "V2" docstring label). Purely additive
  module-level metadata; zero logic touched.
- `alert_signals.py` — added `explainability_engine as expl,
  decision_audit_history as dah` to the import block. New
  `log_decision_snapshot()` helper (builds + persists one
  `DecisionSnapshot`, fail-safe, mirrors every other `log_*` helper's
  posture). Called at seven points: Stage-2 risk-lock hold, Stage-2
  portfolio hold, Stage-2 approved entry, Stage-1 regime-blocked, Stage-1
  confluence-held, Stage-1 portfolio-held, Stage-1 approved heads-up —
  every call site reuses already-computed variables (`mkt_regime`, `cr`,
  `e_pr`/`pr_verdict`, `e_assessment`/`assessment`), zero new fetches.
- `engine/dashboard_publish.py` — added `decision_audit_history as dah,
  explainability_engine as expl` to the import block. New
  `decision_audit_payload` computed via `dah.tail(5, symbol=symbol)` +
  `expl.build_audit_graph()`/`explain_approval()`/`explain_rejection()`
  per row, inside a dedicated fail-safe try/except. Top-level `payload`
  gained `"decision_audit": decision_audit_payload` as a sibling key to
  `"signal"`/`"market_memory_advisory"`.
- `ARCHITECTURE_SPECIFICATION.md` — new §18.
- `PROJECT_SUMMARY_AND_ROADMAP.md` — new "Day 8" section.

## Explicit decisions made (documented, not silently resolved)

1. **`decision_id` and `trade_ref` are deliberately two different fields.**
   Every decision — approved, heads-up, or rejected — gets a `decision_id`
   (same `journal.make_ref()` format). `trade_ref` stays the narrower
   Day 6/7 concept: non-empty only for a decision that IS a Stage-2 fill.
   Conflating them would have meant either fabricating a fake `trade_ref`
   for rejections (dishonest) or leaving rejections without any unique
   identifier at all (failing the mandate's "unified identifiers connect
   all stages of the decision lifecycle" for the rejected path
   specifically). See `EXPLAINABILITY_SPECIFICATION.md` Sec.2.1.
2. **No new duplicate database.** `DecisionSnapshot` stores ref pointers
   into the three existing history logs plus a small denormalized
   summary — the SAME trade-off `engine/journal.py`'s `Trade` dataclass
   already makes (Day 1-2 precedent). The genuinely new fields are ones
   nothing else captures: `final_action`, `rejection`, `platform_version`,
   `config`. See `EXPLAINABILITY_SPECIFICATION.md` Sec.3.
3. **Immutability is a structural property, not a documented promise.**
   `decision_audit_history.py` exposes no update/delete/overwrite function
   — `test_no_mutator_besides_record_exists` proves this by inspecting the
   module's own function names, the same "prove it structurally" pattern
   used for Day 6's no-`allow`/`reject`-field test and Day 7's
   `_look_ahead_safe()` choke-point test.
4. **Corrections are new rows, never edits** — `record_correction()`
   appends `{record_type: "correction", corrects_ref: <decision_id>}`;
   `history_for_ref()` returns the original plus every correction in
   write order. Directly implements the mandate's own words: "Corrections
   should be stored as subsequent records, not by altering history."
5. **`replay()` is proven deterministic, not just designed to be.**
   `test_replay_approved_decision_is_deterministic`/
   `test_replay_rejected_decision_is_deterministic` compare
   `json.dumps(..., sort_keys=True)` output across two calls for
   byte-identical equality — the literal meaning of "historical
   explanations must remain reproducible," verified rather than assumed.
6. **`post_trade_review()` is explicitly labeled a heuristic, not a causal
   model** — every output includes a `heuristic_disclosure` string. This
   was a deliberate choice to avoid the report implying a stronger claim
   ("this uncertainty indicator caused this loss") than one data point can
   support — same statistical-honesty discipline as every prior Day's
   `MIN_N_FOR_TRUST` gating, applied to a per-trade review instead of an
   aggregate.
7. **Two account-level gates are explicitly NOT snapshotted**: the news
   blackout check and the pre-origination `risk_guard` lock both run
   before any specific candidate direction/opportunity exists (before
   `signals.analyze()` has even run), so there is no real "decision about
   a setup" to snapshot yet. Recording a `DecisionSnapshot` with an
   empty/fabricated direction would misrepresent what the object means.
   Both remain single-line ledger events only, exactly as before Day 8 —
   see `EXPLAINABILITY_SPECIFICATION.md` Sec.9.1.
8. **Four modules retroactively assigned `VERSION="1.0.0"`/`"2.0.0"`
   rather than every module in the codebase.** Scoped to the six modules
   that matter to a trading decision's explainability
   (`COMPONENT_MODULES`) — same "smallest evidence set" discipline as
   every prior Day's deliberately-scoped weighting/feature list. The rest
   report `"unversioned"` honestly via `component_versions()`, never a
   fabricated number.
9. **`dashboard_publish.py`'s `decision_audit` payload key is a sibling of
   `signal`, not nested inside it** — mirrors Day 7's identical structural
   choice for `market_memory_advisory`, per the mandate's own instruction
   that advisory dashboards be "clearly separated from live trade
   recommendations."

## What was explicitly NOT touched

- ICT/SMC origination logic (`signals.py`'s `analyze()`) — unchanged; only
  gained a `VERSION` constant.
- Market Regime Engine classification logic (`regime_engine.py`'s
  `classify()`) — unchanged; only gained a `VERSION` constant.
- MAST confluence scoring, hard gates, checklist (`confluence.py`'s
  `analyze()`) — unchanged; only gained a `VERSION` constant.
- Portfolio Risk Engine's evaluation logic (`portfolio_risk.py`'s
  `evaluate()`) — unchanged; only gained a `VERSION` constant.
- The Confidence Engine's composite formula (`confidence_engine.py`) —
  untouched this Day (Day 6/7 already established `memory_context`'s
  score-independence; Day 8 reuses `ConfidenceAssessment`'s already-final
  fields, never re-derives them).
- `hourly_briefing.py` — not modified, matching Day 5/6/7's identical
  precedent for the same file.
- No production behavior changed: no signal that would have published
  before Day 8 is now rejected, delayed, held, or resized differently.
  Every `log_decision_snapshot()` call site is fail-safe and runs strictly
  after the real gate/approval decision has already been made.
