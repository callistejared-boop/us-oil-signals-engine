# Day 11 Implementation Report — Institutional Macro Intelligence Engine

Full specification: `MACRO_ENGINE_SPECIFICATION.md`. Research assumptions
and validation plan: `RESEARCH_MACRO_ENGINE.md`.

## New files

- `engine/rates_feed.py` — live Treasury yields (`^TNX`/`^IRX`), curve
  slope/shape, TLT (sovereign-bond proxy), TIP/IEF inflation-expectations
  proxy. Same fetch + JSON-cache + fail-safe pattern already established
  by `risk_sentiment.py`/`spread_feed.py`.
- `engine/macro_reference.py` — operator-curated reference data (central
  bank stances, geopolitical flags, economic prints), mirroring
  `eia_feed.py`'s "requires operator input, safe not-configured default"
  precedent. Ships with `"example": True` placeholder entries, honestly
  reported as `not_configured` rather than fabricated.
- `engine/macro_calendar.py` — classifies the existing `news_guard` event
  feed into central_bank/inflation/employment/growth/housing/energy/
  sentiment/other categories with timing buckets; no second event fetch.
- `engine/macro_cross_asset.py` — the 11 named cross-asset relationships,
  represented qualitatively (sign/trend reasoning over a documented
  textbook basis), consistent with how `correlation.py`/`spread_feed.py`
  already represent their own cross-asset reads.
- `engine/macro_providers.py` — the single abstraction layer. Ten mandate
  providers plus two supplementary wrappers (`seasonality`,
  `calendar_summary`), all returning the standardized shape (`facts`,
  `interpretation`, `freshness`, `source_availability`, `uncertainty`,
  `source`).
- `engine/macro_regime.py` — descriptive classifier (8 non-mutually-
  exclusive labels), carrying the two explicitly-distinct fields
  `macro_confidence` and `evidence_quality`.
- `engine/macro_history.py` — immutable, append-only, normalized macro
  assessment log, mirroring `regime_history.py`'s established pattern.
- `engine/macro_engine.py` — top-level orchestrator (`assess()`,
  `explain()`, `record_assessment()`, `last_assessment()`,
  `find_assessment_by_ref()`); performs no calculations of its own.
- `MACRO_ENGINE_SPECIFICATION.md`, `RESEARCH_MACRO_ENGINE.md` — full
  specification and research note.
- 10 new test files (158 tests total — see Testing section below).

## Modified files

- `alert_signals.py` — added `macro_engine as macro` import;
  `log_macro_context(sym, direction, ref)` (new function, called once per
  Stage-2 entry, mirrors `log_market_memory_context()`'s existing
  placement and fail-safe posture); `build_entry()` gained a `macro=None`
  parameter and an optional informational `macro:` line, following the
  same pattern as the existing `confidence:` line; the Stage-2 entry flow
  now passes `macro_ref=trade_ref` to `journal.log_signal()`.
- `engine/journal.py` — added `Trade.macro_ref` (default `""`, after
  `regime_ref`) and a `macro_ref=""` parameter to `log_signal()`,
  extending the platform's unified-ID invariant to `id == regime_ref ==
  confluence_ref == confidence_ref == macro_ref`.
- `engine/dashboard_publish.py` — added `macro_engine as macro` import
  and a `"macro_advisory"` payload key reading `macro.last_assessment(symbol)`
  (the last recorded assessment, never a fresh recompute). **Also fixed a
  bug found during this Day's own testing** — see "Bug found and fixed"
  below.
- `ARCHITECTURE_SPECIFICATION.md` — new §21, including the platform
  owner's requested "Version 2.0 Architecture Complete" milestone
  declaration.
- `PROJECT_SUMMARY_AND_ROADMAP.md` — new "Day 11" section, same milestone
  declaration.
- `tests/test_dashboard_publish.py` — 3 new tests appended for the
  `macro_advisory` payload key (existing 9 tests unchanged).

**No other file was touched.** `engine/confluence.py`,
`engine/confidence_engine.py`, `engine/bias_adjust.py`,
`engine/risk_guard.py`, `engine/signals.py`, and every Day 1-10 gating or
scoring module are byte-for-byte unchanged from the end of Day 10 —
grep-verified (see Validation Report).

## Explicit decisions made (documented, not silently resolved)

1. **`macro_providers.py` is the ONLY module any downstream code imports
   for macro data**, per the platform owner's explicit Phase-1 priority.
   `macro_regime.py` takes a pre-fetched `providers` dict as its argument
   rather than importing any feed module itself — there is nothing in it
   to accidentally bypass the abstraction layer.
2. **Employment has no fabricated continuous series.** NFP is monthly/
   event-driven; interpolating a smooth trend between releases would
   imply information that doesn't exist. The `employment` provider is
   deliberately thinner than the other nine (last print + next scheduled
   release only) rather than inventing a proxy series — same "never
   fabricate" discipline the platform applied to trade-data integrity at
   Day 10.
3. **Inflation carries two explicitly separate facts, never blended**: a
   live market-implied proxy (TIP/IEF ratio trend) and a curated
   last-known CPI print. Blending them into one number was considered and
   rejected — Day 10's own lesson about not conflating distinct evidence
   types applies directly here.
4. **The 11 cross-asset relationships are qualitative, not a live
   Pearson correlation.** Nearly all of them pair a platform-traded
   symbol against an external macro series (not two traded symbols), so
   `correlation_dynamic.get_correlation()` (built for traded-symbol pairs
   at Day 3) doesn't directly apply. Representing each relationship via
   sign/trend reasoning over a documented textbook basis matches how
   `correlation.py`/`spread_feed.py`/`risk_sentiment.py` already
   represent their own cross-asset reads — none of them compute a live
   correlation coefficient either.
5. **`macro_confidence` and `evidence_quality` are simple, disclosed,
   count-based rules — not weighted scores**, per the platform owner's
   explicit prohibition on a third scoring engine. Neither field feeds
   `engine/confidence_engine.py` or `engine/bias_adjust.py` — grep-
   verified zero references in either direction.
6. **`macro_history.py` stores only the normalized assessment, never raw
   `facts`.** The underlying feeds already persist their own raw numbers
   in their own caches (`rates_cache.json`, `spread_cache.json`, etc.) —
   duplicating them in `macro_history.jsonl` would violate the platform's
   standing "reuse existing histories, avoid duplicate storage"
   discipline (Day 7, reaffirmed Day 9).
7. **`log_macro_context()` is called once per Stage-2 entry, not every
   scan** — a deliberate, disclosed difference from the Market Regime
   Engine's routine per-scan capture. Macro context is direction-
   dependent (`macro_cross_asset` needs a `direction` argument), so a
   routine no-trade snapshot would need recomputing anyway once a
   candidate direction exists, and nothing reads a no-trade snapshot
   today.
8. **`dashboard_publish.py` reads the last RECORDED assessment, never a
   fresh live recompute.** A fresh `macro_engine.assess()` call on every
   dashboard page load would add another full round of provider fetches
   (including the yfinance-backed ones) to a page that may be refreshed
   frequently by a human — reading the history file instead costs nothing
   beyond a JSONL tail read.

## Bug found and fixed during this Day's own testing

`engine/dashboard_publish.py`'s `build_payload()` had a pre-existing
local variable named `macro` (`macro = co.read_macro()`, used for the
existing DXY-based range-guard evaluation) inside the exact same function
scope as the new `"macro_advisory"` lambda
(`lambda: macro.last_assessment(symbol)`). Because Python resolves a
closure's free variables at the enclosing function's scope, not
line-by-line, this local assignment shadowed the module-level
`macro_engine` import for the ENTIRE function — any code path reaching
the `macro_advisory` line before first reaching the `macro =
co.read_macro()` line (i.e. whenever `sig` is falsy — no active setup)
raised `UnboundLocalError`. Caught by
`test_build_payload_includes_macro_advisory_from_last_recorded_assessment`
and `test_build_payload_macro_advisory_none_when_no_history_yet`, both of
which failed the first time they were run. Fixed by renaming the local
variable to `dxy_macro`. All 9 pre-existing `test_dashboard_publish.py`
tests (predating this Day's change) still pass — zero collateral
regressions from the fix.

## Testing

158 new offline tests, zero live-network dependency:

| File | Tests |
|---|---|
| `tests/test_rates_feed.py` | 14 |
| `tests/test_macro_reference.py` | 11 |
| `tests/test_macro_calendar.py` | 18 |
| `tests/test_macro_cross_asset.py` | 21 |
| `tests/test_macro_providers.py` | 23 |
| `tests/test_macro_regime.py` | 23 |
| `tests/test_macro_history.py` | 20 |
| `tests/test_macro_engine.py` | 12 |
| `tests/test_journal_macro.py` | 4 |
| `tests/test_alert_signals_macro.py` | 9 |
| `tests/test_dashboard_publish.py` (+3 new) | 3 |
| **Total new** | **158** |

## What was explicitly NOT touched

- `engine/confluence.py`, `engine/confidence_engine.py`,
  `engine/bias_adjust.py`, `engine/risk_guard.py`, `engine/signals.py` —
  zero changes.
- Every Day 1-10 engine module besides the three integration touch
  points listed above — zero changes.
- `trades.json` — zero changes; no macro assessment writes to the trade
  journal itself, only to the new `macro_history.jsonl` (which does not
  exist on disk at the end of this Day — left empty/nonexistent, same
  convention as `experiment_registry.jsonl` at Day 9's close, per the
  standing practice of not seeding production-adjacent files with
  smoke-test data).
- No threshold, confidence score, confluence score, or gating decision
  changed as a result of this Day's work.
