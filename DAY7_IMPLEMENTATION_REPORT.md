# Day 7 Implementation Report — Market Memory Engine & Trade Intelligence System

Full design detail: `MARKET_MEMORY_SPECIFICATION.md`. Research:
`RESEARCH_MARKET_MEMORY.md`.

## New files

- `engine/market_memory.py` — `MemoryRecord` dataclass; `build_memory_record()`/
  `build_memory_records()` (assembly from `trades.json` + history logs via
  the unified ref, with trade-row fallback); `DEFAULT_SIMILARITY_WEIGHTS`,
  `extract_features()`, `query_features_from_live()`, `similarity()`;
  `_look_ahead_safe()` (single choke-point guard); `find_similar()`,
  `MIN_N_FOR_TRUST`/`MIN_N_FOR_CONTEXT`, `memory_quality()`,
  `historical_context()`; `performance_by_strategy_regime()`,
  `performance_by_confluence_profile()`, `performance_by_session()`,
  `risk_adjusted_by_combo()`.
- `tests/test_regime_history_ref.py` (6 tests), `tests/test_market_memory_lookahead.py`
  (8 tests), `tests/test_market_memory.py` (33 tests),
  `tests/test_calibration_comparison.py` (4 tests), plus 5 tests appended
  to `tests/test_confidence_engine.py` — 56 total.
- `MARKET_MEMORY_SPECIFICATION.md`, `RESEARCH_MARKET_MEMORY.md`.

## Modified files

- `engine/regime_history.py` — `record()` gained an optional `ref: str = ""`
  parameter (persisted alongside the existing schema, not a new record
  type) and a new `find_by_ref(ref)` lookup, mirroring Day 6's
  `confluence_history`/`confidence_history` pattern exactly.
- `engine/journal.py` — `Trade` gained a `regime_ref: str = ""` field
  (alongside the existing Day 6 `confluence_ref`/`confidence_ref`);
  `log_signal()` gained a matching optional `regime_ref` parameter.
- `alert_signals.py` — Stage-2 entry now calls
  `rhist.record(sym, "strategic", mkt_regime, ref=trade_ref)` immediately
  after computing `trade_ref`, and passes `regime_ref=trade_ref` into
  `journal.log_signal()`. Added `market_memory as mm` to the import block,
  a new `log_market_memory_context()` function (builds query features,
  calls `historical_context()`, logs to the ledger, never raises), and
  extended `log_confidence_assessment()` with a `memory_context=None`
  parameter forwarded to `confeng.assess()`. Wired at both Stage-1 and
  Stage-2.
- `engine/confidence_engine.py` — `assess()` gained a `memory_context:
  dict | None = None` parameter, consumed only after `overall_confidence`
  is already computed — appends to `supporting_rationale` (sufficient
  sample) or `assumptions` (insufficient sample) only, never the score.
- `engine/confidence_calibration.py` — added
  `raw_vs_composite_comparison(min_n=MIN_N_FOR_CALIBRATION)`, comparing
  the pre-existing raw `calibration.py` against the Day 6 composite over
  the same matched trades; self-gates `active=False` below `min_n=30`.
  Not called from `report()` or any live surface — deliberate, per the
  platform owner's "design now, activate later" decision.
- `engine/dashboard_publish.py` — added `market_memory as mm` to the
  import block; new `memory_payload` computed via
  `mm.query_features_from_live()` + `mm.historical_context()` inside a
  dedicated try/except (fail-safe, `None` on any error). Top-level
  `payload` gained `"market_memory_advisory": memory_payload` as a sibling
  key to `"signal"`, not nested inside it.
- `ARCHITECTURE_SPECIFICATION.md` — new §17.
- `PROJECT_SUMMARY_AND_ROADMAP.md` — new "Day 7" section.

## Explicit decisions made (documented, not silently resolved)

1. **No new database was created.** `MemoryRecord`s are assembled at read
   time from `trades.json` + the three existing `*_history.jsonl` logs.
   This was the direct, load-bearing interpretation of the mandate's
   "reuse existing journals and histories... avoid duplicate storage"
   principle, and of the platform owner's own Day 6 closing preference for
   a single trace ID over a new central store.
2. **The unified trade ID extension to `regime_history` reuses the exact
   same string `journal.make_ref()` already produces for `Trade.id`.**
   `trade.id == regime_ref == confluence_ref == confidence_ref` by
   construction for every trade logged from today forward — the ASCII
   diagram the platform owner sketched (Trade ID branching to Regime/
   Confluence/Confidence/Risk/Portfolio/Journal/Telegram/Dashboard/Outcome)
   is implemented for the three subsystems it names that persist history
   logs today; **Risk Assessment, Portfolio Assessment, Telegram Alert,
   and Dashboard Entry were NOT given their own ref-tagged storage** this
   Day — documented explicitly in `MARKET_MEMORY_SPECIFICATION.md` §2.2 as
   scope not yet closed, not silently dropped.
3. **`_look_ahead_safe()` is a single, shared choke point**, not a check
   duplicated across `find_similar()`/`historical_context()`/analytics
   functions — every one of them routes through it. A candidate is usable
   only if `status` is a terminal outcome AND `closed` is STRICTLY before
   `as_of` (not before-or-equal), closing the exact-boundary edge case
   explicitly, with a dedicated test (`test_lookahead.py`) for each
   condition independently plus a combined 50-future-vs-5-past scenario.
4. **`memory_context` is consumed by `confidence_engine.assess()` only
   after `overall_confidence` is finalized** — proven, not just
   documented, by `test_memory_context_never_changes_overall_confidence`,
   which builds three assessments from identical inputs with different
   `memory_context` values and asserts byte-identical scores/tiers. This
   is the same "prove it structurally" pattern used for the no-`allow`/
   `reject`-field test in Day 6.
5. **Similarity weights are disclosed engineering judgment, not fitted** —
   same convention as every prior day's weighting scheme (Day 4 transition
   risk, Day 5 confluence quality, Day 6 confidence composite). No claim
   is made that these seven dimensions are optimal; `RESEARCH_MARKET_MEMORY.md`
   §3 states this explicitly.
6. **`raw_vs_composite_comparison()` was built exactly as scoped by the
   platform owner's own words** ("design now... keep it inactive until
   enough live observations exist") — self-gated at `min_n=30`, and
   structurally confirmed NOT wired into `report()`
   (`test_not_wired_into_any_live_report_yet` asserts this via
   `inspect.getsource`).
7. **`dashboard_publish.py`'s `market_memory_advisory` is a sibling key to
   `signal`, not nested inside it** — mirrors the mandate's explicit
   instruction that advisory dashboards be "clearly separated from live
   trade recommendations," made structural rather than just visual.
8. **The legacy id-format data-quality finding was documented, not
   silently absorbed.** Some pre-Day-6 `trades.json` rows use an id
   without the symbol prefix (predating the `f"{symbol}-{...}"`
   convention). This does not break anything — all `*_ref` fields are
   empty on those rows regardless of `id` format — but is disclosed in
   `MARKET_MEMORY_SPECIFICATION.md` §2.2 per this session's "state
   findings honestly" discipline.

## What was explicitly NOT touched

- ICT/SMC origination (`signals.py`) — unchanged.
- The Market Regime Engine's classification logic (`regime_engine.py`) —
  unchanged; only its history log gained an optional `ref` field.
- MAST confluence scoring, hard gates, and checklist (`confluence.py`) —
  unchanged.
- The Portfolio Risk Engine (`portfolio_risk.py`) — unchanged.
- The Confidence Engine's `overall_confidence` composite formula
  (`confidence_engine.py`'s scoring math) — unchanged; `memory_context`
  only appends text, verified structurally (decision #4 above).
- `hourly_briefing.py` — not modified, matching Day 5/6's identical
  precedent for the same file.
- No production behavior changed: no signal that would have published
  before Day 7 is now rejected, delayed, held, or resized differently.
  Market Memory is read-only, advisory, and additive to Telegram/dashboard
  text and a new ledger entry type only.
