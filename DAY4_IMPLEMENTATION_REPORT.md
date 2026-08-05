# Day 4 Implementation Report — Market Regime Engine

2026-08-03. What changed and why, in the order it was built.

## New files

| File | Purpose |
|---|---|
| `engine/regime_engine.py` | Centralized multi-timeframe Market Regime Engine. Reuses `engine.regime.classify()` (Kaufman ER + ATR percentile) once per timeframe via `data_loader.resample()`, plus `structure.dealing_range/range_position` and `news_guard.evaluate()`. Adds: the 5-timeframe strategic/tactical/execution hierarchy, the finer taxonomy (Strong/Weak Bull/Bear Trend, Range, Distribution, Accumulation + volatility/liquidity/news tags), transition-risk estimation, the strategy compatibility matrix, and the quality score. |
| `engine/regime_history.py` | Append-only JSONL history of every regime classification, mirroring `engine/ledger.py`'s exact append/rotate/tail pattern. Adds transition detection and duration tracking a plain ledger doesn't need. |
| `MARKET_REGIME_SPECIFICATION.md` | Master Day 4 reference: reuse inventory, MTF hierarchy reasoning, taxonomy mapping, transition framework, compatibility matrix, quality score, integration order/interfaces, failure handling, known limitations. |
| `RESEARCH_REGIME_ENGINE.md` | Honest analysis of what the existing `trades.json` data can and can't tell us about regime-conditional performance (only 10/99 closed trades are regime-tagged, all sharing one label), plus the concrete statistical validation plan and promotion criteria for enabling regime-based blocking. |
| `tests/test_regime_engine.py` | 28 offline tests: taxonomy mapping, MTF hierarchy (not simple-voting), confidence/quality-score math, compatibility matrix, tags, multi-symbol, rapid-regime-change edge case, fail-safety. |
| `tests/test_regime_history.py` | 10 offline tests: record/read, transition detection, symbol isolation, rotation, fail-safety on an unwritable path. |
| `tests/test_alert_signals_regime_gate.py` | 4 offline tests for the new `apply_regime_gate()` advisory/block decision function. |

## Modified files

| File | Change | Why |
|---|---|---|
| `engine/config.py` | Added `regime_filter_mode` (default `"advisory"`), `regime_min_quality_for_block` (default `30`), `regime_strategy` (default `"ict_smc_mast"`). | New configuration surface for the Day 4 integration; all three are `.env`/env-var overridable via the `_coerce()` mechanism Day 3 already built. |
| `alert_signals.py` | Added `regime_engine`/`regime_history` imports. Computes `mkt_regime = rgeng.classify(df, sym, ...)` once per symbol per scan (first thing after `journal.settle()`), records it to `regime_history.record()`, logs it to the ledger. Added `apply_regime_gate()` (independently unit-tested) and calls it once, at Stage-1 (HEADS-UP) only, right before the confluence check. | Implements the Day 4 mandate's requested pipeline order (Regime Engine runs before origination/confluence/risk) and its "informational context, don't alter core ICT/SMC logic" constraint — nothing about `signals.analyze()`, `confluence.analyze()`, `risk_guard`, or `portfolio_risk` was touched. |
| `hourly_briefing.py` | Added the same `regime_engine`/`regime_history` imports and a `try/except`-wrapped classify+record call inside `main()`'s loop. No gating added (this script's Day 3 classification as research/informational is unchanged). | Consistent history coverage across both entry points, at zero risk to the already-tested Day 3 `apply_risk_gate()` logic. |
| `ARCHITECTURE_SPECIFICATION.md` | Added §14 noting the Day 4 addition, pointing to `MARKET_REGIME_SPECIFICATION.md`. | Keeps the Day 1 audit's own living document accurate. |
| `PROJECT_SUMMARY_AND_ROADMAP.md` | Added a "Day 4" section, new test count (348 → 390). | Standing project log, consistent with every prior day's entry. |

## Explicit decisions made (documented, not silently resolved)

1. **`regime_filter_mode` defaults to `"advisory"` (non-blocking), not
   `"block"`.** Unlike Day 3 (where the user gave an explicit "must reject"
   instruction), Day 4's mandate explicitly asks for a statistical
   validation plan and states a regime filter should only stay in
   production if it demonstrates a measurable improvement. `RESEARCH_REGIME_ENGINE.md`
   §1 shows the current dataset (10 regime-tagged trades, all one label)
   cannot support that claim yet. Shipping `"block"` today would be exactly
   the "complexity without measurable benefit" the mandate itself warns
   against. `"block"` mode is fully implemented and tested, not merely
   stubbed, so it can be enabled the moment the evidence in
   `RESEARCH_REGIME_ENGINE.md` §3 exists.

2. **Blocking (when enabled) only applies at Stage-1 (HEADS-UP origination),
   never Stage-2 (ENTRY fill).** Suppressing an already-published HEADS-UP's
   subsequent ENTRY would be a more confusing outcome for a human reading
   the channel than either publishing cleanly or not announcing the setup at
   all. This mirrors the reasoning (not the mechanism) behind Day 3's
   decision to gate both stages for portfolio risk — here the asymmetry
   between "new idea" and "already-announced idea" argues for a single
   gate point instead.

3. **`journal.py`'s `Trade.regime_trend`/`regime_vol` fields were left
   receiving the OLD single-timeframe `regime.classify()` snapshot**, not
   the new engine's output. The already-tested `_guard_for()` → `range_guard.py`
   path also keeps using the old single-TF call, completely unchanged. The
   new, richer classification is recorded separately and additively in
   `regime_history.jsonl`. This was the more conservative choice — it means
   Day 4 introduces zero risk of changing an already-shipped field's
   meaning — at the cost of the two data sources not being joined by a
   single ID yet (documented as a Day 5+ schema-extension candidate in
   `RESEARCH_REGIME_ENGINE.md` §4.2).

4. **Weekly timeframe usually falls back to daily as the "strategic"
   anchor.** The live data feeds (`markets.fetch`, bounded by yfinance's
   60-day 15-minute-bar window) provide too few weekly bars to trust. This
   is documented, not hidden — `MARKET_REGIME_SPECIFICATION.md` §8,
   limitation #1 — and the engine degrades to daily gracefully rather than
   forcing a low-confidence weekly read.

5. **`STRONG_ER=0.55`, the transition-risk weights (0.4/0.3/0.2), and the
   quality-score base values (80/60/35/10) are domain-reasonable
   heuristics, explicitly labeled as such**, not statistically fitted
   constants — following the exact disclosure convention
   `structure.classify_swing_strength()` already established in this
   codebase. `RESEARCH_REGIME_ENGINE.md` §3.4 documents the path to
   calibrating them once `regime_history.jsonl` has enough transition
   events.

## What was explicitly NOT touched

- `engine/regime.py`, `engine/structure.py`, `engine/ict.py`,
  `engine/range_guard.py`, `engine/news_guard.py`,
  `engine/correlation_dynamic.py` — zero changes. All read from, none
  modified.
- `signals.py`, `confluence.py` — zero changes, per the mandate's explicit
  "without altering the core ICT/SMC trade-generation logic" constraint.
- `engine/risk_guard.py`, `engine/portfolio_risk.py` (Day 3) — zero changes;
  the Day 4 gate is a new, separate check, not a modification to either.
- `journal.py` — zero changes (see decision #3 above).
- The GitHub Actions workflow (`entry-scan.yml`) — no change needed; it
  already calls `alert_signals.py`, which now includes the new stage
  internally.
