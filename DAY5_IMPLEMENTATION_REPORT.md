# Day 5 Implementation Report — Adaptive Confluence Engine & Evidence Independence

Full design detail: `CONFLUENCE_SPECIFICATION.md`. Research: `RESEARCH_CONFLUENCE_ENGINE.md`.

## New files

- `engine/confluence_analysis.py` — `SOURCE_REGISTRY` (27-entry independence
  classification of all confluence sources), `explain()`, `quality_score()`,
  `conflict_resolution()`, `measure_contribution()`,
  `recommend_weight_adjustments()`, `join_trades_with_confluence()`.
- `engine/confluence_history.py` — append-only JSONL log of every confluence
  read, mirroring `regime_history.py`'s pattern exactly (`record`, `tail`,
  `all_rows`, 20,000-line rotation).
- `engine/confluence_sandbox.py` — JSON-backed governed research pipeline
  (research → historical_testing → walk_forward → paper_trading →
  production_recommendation), zero coupling to `confluence.py`.
- `tests/test_confluence_analysis.py` (32 tests), `tests/test_confluence_history.py`
  (6 tests), `tests/test_confluence_sandbox.py` (12 tests) — 50 total, 47
  distinct new test functions plus 3 module-level `__main__` runners.
- `CONFLUENCE_SPECIFICATION.md`, `RESEARCH_CONFLUENCE_ENGINE.md`.

## Modified files

- `alert_signals.py` — added `confluence_analysis as cfa, confluence_history
  as cfh` to the existing engine import block; added
  `log_confluence_explainability(sym, cr)`, called immediately after every
  successful `cf.analyze(...)` call at both the Stage-1 (heads-up) and
  Stage-2 (entry) confluence-analysis sites, inside the existing try/except
  so a failure here cannot block a signal. Nothing else in the file changed.
- `ARCHITECTURE_SPECIFICATION.md` — new §15 documenting the Day 5 addition.
- `PROJECT_SUMMARY_AND_ROADMAP.md` — new "Day 5" section (test count,
  pointer to new docs, headline finding).

## Explicit decisions made (documented, not silently resolved)

1. **`engine/confluence.py` was not modified.** Every scored source, weight,
   hard gate, and the checklist are byte-identical to before Day 5. The
   mandate's own framing — "the goal is not to replace MAST" — is treated
   literally: Day 5 is an analysis and logging layer that reads
   `ConfluenceRead` objects, not a rewrite of how they're produced.
2. **Independence classification is code-grounded, not opinion-based.**
   Every Duplicate/Legacy label is backed by a specific, quotable shared
   function call or module self-disclosure (see
   `CONFLUENCE_SPECIFICATION.md` §2.1-2.4), directly satisfying the
   mandate's "do not hard-code rankings based on opinion."
3. **Point values in `explain()`/`measure_contribution()` are reconstructed
   nominal approximations, not exact.** `ConfluenceRead` stores source
   NAMES in `agree`/`disagree`, not per-source point deltas; several
   sources (trend quality, Wyckoff, volume profile, news) have conditional
   sub-weights computed inline in `confluence.py` and never persisted.
   Rather than modify `confluence.py` to expose exact deltas (a larger,
   riskier change), a static nominal-weight registry was built and its
   limitation is explicitly documented in three places
   (`confluence_analysis.py`'s docstring, `CONFLUENCE_SPECIFICATION.md` §4
   and §9, `RESEARCH_CONFLUENCE_ENGINE.md` §2.3).
4. **`recommend_weight_adjustments()` never writes to `confluence.py` and
   requires `min_n=30` per bucket before recommending anything other than
   `"insufficient_data"`** — matching `RISK_RULES.md`'s existing 30-trade
   statistical bar. Currently returns `"insufficient_data"` for all 26
   sources because zero closed trades carry a populated `confluence_score`
   (see Validation Report §4 and Research Report §1). This is the intended
   behavior, not a bug: a framework that manufactured a recommendation from
   zero data would violate the mandate's "no source receives permanent
   authority... [but] no hard-coded rankings based on opinion" principle in
   the other direction.
5. **The sandbox's stage-ordering validation is strict (raises on
   skip/unknown-candidate/empty-note), not fail-open.** A silently lenient
   sandbox would defeat its own purpose — the whole point of Phase 8 is that
   a candidate's promotion history is a trustworthy audit trail.
6. **`log_confluence_explainability()` is called regardless of
   `cr.final_tier`** (both at Stage-1 heads-up level and Stage-2 entry
   level), so the historical log captures rejected/lower-tier reads too,
   not just published signals — needed for `measure_contribution()` to
   later compare outcomes across the full distribution of confluence
   quality, not a tier-filtered subset.
7. **Fixed a genuine bug found via testing, not inspection**: the initial
   `join_trades_with_confluence()` compared ISO-format history timestamps
   (`"T"` separator) against `trades.json`'s space-separated `opened` field
   using naive string comparison, which can misorder rows because ASCII
   space sorts before `"T"`. Fixed with a `_norm()` helper that normalizes
   both to the same separator before comparing. Caught by
   `test_join_trades_with_confluence_nearest_timestamp`, not manual review.

## What was explicitly NOT touched

- `engine/confluence.py`'s scoring, hard gates, and checklist — unchanged.
- Every one of the 26 confirmation-source modules — unchanged.
- `hourly_briefing.py` — not modified; Day 5's logging was wired only into
  `alert_signals.py`'s two confluence-analysis call sites, since
  `hourly_briefing.py` does not call `confluence.analyze()` directly (per
  Day 3's execution-path trace).
- `engine/regime_engine.py`, `engine/portfolio_risk.py`, and all Day 3/4
  modules — unchanged; Day 5 reads regime data only via `cr.layers["reg"]`
  the way `confluence.py` already did.
- No production behavior changed: no signal that would have published
  before Day 5 is now rejected, delayed, or resized differently.
