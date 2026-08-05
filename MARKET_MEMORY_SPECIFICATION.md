# MARKET MEMORY SPECIFICATION — Institutional Memory & Trade Intelligence (Day 7)

Covers `engine/market_memory.py` (new), the Day 7 extension of
`engine/regime_history.py` (`ref` parameter), the `regime_ref` field on
`engine/journal.py`'s `Trade`, and the `raw_vs_composite_comparison()`
addendum to `engine/confidence_calibration.py`. Companion to
`RISK_SPECIFICATION.md` (Day 3), `MARKET_REGIME_SPECIFICATION.md` (Day 4),
`CONFLUENCE_SPECIFICATION.md` (Day 5), `CONFIDENCE_ENGINE_SPECIFICATION.md`
(Day 6), and `RESEARCH_MARKET_MEMORY.md` (this day's research output).

**The Market Memory Engine does not generate trades.** It answers, for a
candidate situation: "have we seen a materially similar situation before,
and what were the historical outcomes?" — purely advisory, and structurally
incapable of influencing any production decision (no field on any of its
return types feeds into `confidence_engine.py`'s score formula; see Sec.7).

## 1. Primary objective

Before a trade reaches the Confidence Engine, the platform now assembles
historical context for the situation and attaches it — as TEXT ONLY, never
as a score input — to that trade's `ConfidenceAssessment`. This closes the
final gap in the platform's decision architecture that Day 6's mandate
previewed: origination, regime, confluence, risk/portfolio, and confidence
all existed; nothing previously asked "has this happened before."

## 2. Unified Trade ID — reference architecture

Every trade now carries ONE identifier — `journal.make_ref(symbol, when)`,
the exact string `Trade.id` has always used (`f"{symbol}-{timestamp}"`) —
threaded through every subsystem that produces a record about that trade:

```
Trade ID  (journal.make_ref(symbol, when) == Trade.id)
    │
    ├── regime_history.jsonl     row.ref  (Day 7 — NEW)
    ├── confluence_history.jsonl row.ref  (Day 6)
    ├── confidence_history.jsonl row.ref  (Day 6)
    ├── Trade.regime_ref          (Day 7 — NEW)
    ├── Trade.confluence_ref      (Day 6)
    ├── Trade.confidence_ref      (Day 6)
    └── MemoryRecord.trade_id     (Day 7 — the assembler, see Sec.3)
```

`alert_signals.py` computes `trade_ref` ONCE per Stage-2 entry (before any
of the confluence/regime/confidence calls) and passes the identical string
to all three history `record()` calls and to `journal.log_signal()` — so
`trade.id == trade.regime_ref == trade.confluence_ref == trade.confidence_ref`
by construction, not by convention that could drift. `find_by_ref()` exists
identically on all three history modules (`regime_history`,
`confluence_history`, `confidence_history`).

### 2.1 What was NOT unified

- **Telegram alerts and dashboard entries** are not separately logged with
  a trade ID — they are rendered FROM an already-ref-tagged
  `ConfidenceAssessment`/`ConfluenceRead` at send time, so there is no
  separate persisted "alert record" to link; the mandate's diagram lists
  them as consumers of the trade ID, which they are (via the objects they
  render), not as new storage keyed by it.
- **`portfolio_risk.evaluate()`'s verdict** is not separately persisted at
  all (Day 3 never added a `portfolio_history.jsonl`) — its summary is only
  recoverable via `confidence_history`'s `portfolio_status` sub-object
  (Day 6), which IS ref-keyed. A dedicated `portfolio_history.jsonl` with
  its own `ref` field is flagged as a natural future extension in
  `DAY7_NEXT_DAY_READINESS_REPORT.md`, not built this Day (no existing
  storage to reuse — would be new, not a mirror of an existing pattern).
- **Pre-Day-6/7 trades** have empty `*_ref` fields by definition — they
  predate the fields entirely. `MemoryRecord` assembly falls back to each
  trade row's own already-persisted summary fields for these (Sec.3.2).

### 2.2 A pre-existing data-quality finding (not a Day 7 bug)

Querying `trades.json` directly during this Day's work surfaced that the
platform's VERY EARLIEST trade rows use an id format without the symbol
prefix at all (e.g. `"2026-07-07T13:15:00"`, not
`"XAUUSD-2026-07-07T13:15:00"`) — the `f"{symbol}-{...}"` convention
`journal.make_ref()` now formalizes was not always followed. This has zero
functional impact on Day 6/7 (every `*_ref` field on those old rows is
already `""`, so nothing tries to match against the legacy id format), but
is disclosed here for anyone reasoning about `id` uniqueness across the
platform's full history.

## 3. The MemoryRecord object

`engine/market_memory.py`'s `MemoryRecord` dataclass — every field:

| Field | Meaning |
|---|---|
| `trade_id` | The unified trade ID (`Trade.id`) |
| `symbol`, `direction` | Identity |
| `opened`, `closed`, `status`, `result_r` | Straight from the journal |
| `regime` | `{primary, confidence, quality_score, transition_label, source}` if `regime_ref` resolved via `regime_history.find_by_ref()`; else `{trend, vol, source: "trade_row"}` from the trade's own `regime_trend`/`regime_vol` fields (pre-Day-7 fallback) |
| `strategy` | `config.regime_strategy` at assembly time — one production strategy platform-wide today (Day 4's own documented reality), not stored per-trade |
| `confluence_summary` | `{score, final_tier, agree, disagree, quality_score, source}` if `confluence_ref` resolved; else `{score, agree_count, source: "trade_row"}` from `Trade.confluence_score`/`confluence_agree` |
| `confidence_assessment` | `{overall_confidence, tier, is_calibrated, source}` if `confidence_ref` resolved; else `{}` (no equivalent field existed on `Trade` before Day 6) |
| `risk_profile` | `{guard_action, guard_penalty, guard_headwind}` — always from the trade row |
| `portfolio_context` | Recovered from the confidence assessment's `portfolio_status` sub-object (Day 6) when available; `{}` otherwise — see Sec.6 limitation |
| `session` | Derived from `opened`'s hour using `ict.py`'s exact session-window convention — NOT separately stored (see Sec.5) |
| `news_context` | `{signal, strength, delta}` — already on `Trade` since before Day 6 |
| `outcome` | `{status, result_r, closed}` — a convenience duplicate of fields above, for callers that want one "outcome" object |
| `post_trade_review` | `{}` today — placeholder; no post-trade review subsystem exists yet (Sec.6) |
| `data_completeness` | `{regime, confluence, confidence} -> "matched"\|"trade_row_only"\|"missing"` — the explainability/quality input every other function reads |
| `version` | `{"market_memory": "1.0.0", "schema": 1}` |

### 3.1 `build_memory_record(trade_row)` / `build_memory_records()`

`build_memory_record()` assembles ONE record from a `trades.json` row
(optionally accepting pre-fetched history rows to avoid redundant lookups
in bulk contexts). `build_memory_records()` bulk-assembles every trade,
sorted by `opened` ascending — the ordering every look-ahead-sensitive
function in this module relies on. Both never raise; a total failure
returns a `MemoryRecord` with `status="error"` and the exception recorded
in `data_completeness`, never `None` and never a propagated exception.

### 3.2 Storage design — no new duplicate database

Per the mandate's explicit "reuse existing journals and histories... avoid
duplicate storage... avoid redundant databases": **there is no
`market_memory.jsonl` or equivalent.** Every `MemoryRecord` is assembled
ON DEMAND, at read time, by joining `trades.json` (`engine.store.load_array`)
with `regime_history.jsonl`/`confluence_history.jsonl`/`confidence_history.jsonl`
via the unified trade ID (Sec.2). This is a deliberate trade-off:

- **Pro**: zero new persistent state to keep consistent, zero migration
  risk, zero "which store is authoritative" ambiguity — the journal and
  the three history logs remain the single sources of truth they already
  were.
- **Con**: assembling all `MemoryRecord`s is an O(n) pass over `trades.json`
  plus up to 3×n lookups into the history logs (each currently O(m) linear
  scans — see `find_by_ref()`'s own docstring, which already flags this).
  At current data volume (102 trades, history logs in the low hundreds of
  rows) this is fast (`tests/test_market_memory.py`'s 2,000-record
  synthetic benchmark completes in well under a second); it is NOT
  designed to scale to tens of thousands of trades without an index — see
  `DAY7_NEXT_DAY_READINESS_REPORT.md` for the flagged future optimization.

### 3.3 Retention and archival

No new retention policy is introduced — `MemoryRecord`s are ephemeral
(computed, used, discarded), so there is nothing to retain beyond what
`regime_history.py`/`confluence_history.py`/`confidence_history.py` already
govern (each caps at `MAX_LINES=20000` with oldest-first rotation,
established Day 4/5/6). `trades.json` itself has no rotation — it is the
platform's permanent trade ledger, unchanged by Day 7.

## 4. Similarity framework

`extract_features(rec)` reduces a `MemoryRecord` to a seven-dimension
comparison vector; `query_features_from_live(...)` produces the identical
shape directly from a live candidate's already-computed objects (so a
not-yet-executed trade can be compared against history without needing a
`MemoryRecord` of itself first). Dimensions and rationale:

| Dimension | Source | Why included |
|---|---|---|
| `regime_primary` | Day 4's regime classification | The single highest-level "what kind of market is this" signal |
| `confluence_profile` | Day 5's independence-CATEGORY set among agreeing sources (not raw labels) | Compares evidence STRUCTURE, not exact source overlap — two trades rarely share the identical agree list, but often share the identical category mix |
| `session` | Derived from `opened`'s hour | Liquidity/spread conditions vary meaningfully by session on this platform's instruments |
| `volatility` | Regime engine's `vol_trend` (live) / trade row's `regime_vol` (historical fallback) | Expansion/contraction context materially changes expected trade behavior |
| `macro_alignment` | Whether "macro (USD)" appears in agree/disagree | A binary but genuinely independent (Primary-classified, Day 5) signal |
| `portfolio_state` | Bucketed `portfolio_status.heat` (low/medium/high) | Was the platform's overall risk posture crowded or clear at the time |
| `direction` | long/short | Long and short setups can have structurally different edge on the same instrument |

`similarity(features_a, features_b, weights=None)` — a 0.0-1.0 score.
**Weights are disclosed, engineering-judgment defaults
(`DEFAULT_SIMILARITY_WEIGHTS`), not statistically fitted** — same
convention as every prior day's formula weights. A dimension contributes
its weight ONLY when both sides have a known value; `confluence_profile`
uses Jaccard overlap (partial credit for partial category overlap), every
other dimension is exact-match-or-zero. The function and its weights are
config-parameter-driven (a `weights` dict can be supplied per call),
satisfying the mandate's "should remain configurable and extensible."

## 5. Session derivation — no new stored field

Session is NOT a new `Trade` field. It is computed from the already-
persisted `opened` timestamp's hour, using `ict.py`'s EXACT session-window
boundaries (`_session_from_hour()`, deliberately mirroring, not
reinventing, that convention). This is a direct instance of the storage
design principle in Sec.3.2: information derivable from existing data does
not need new storage.

## 6. Known limitations (documented, not silently assumed)

1. **`portfolio_context` is only as complete as `confidence_ref` resolves**
   — there is no dedicated portfolio history log (see Sec.2.1). A trade
   with a `confidence_ref` but where the confidence assessment itself
   predates full portfolio-status persistence would show `{}` here.
2. **`post_trade_review` is always `{}`** — no structured post-trade-review
   subsystem exists in this codebase yet (`self_review.html` exists as a
   static page but is not a queryable data source `market_memory.py` reads
   from). This field is a documented placeholder for a future integration,
   not a bug.
3. **Volatility taxonomies don't perfectly match between the live query
   side and the historical fallback side** — `query_features_from_live()`
   reads `mkt_regime.get("vol_trend")` (Day 4's `"expansion"/"contraction"/
   "stable"/"unknown"` vocabulary), while `extract_features()`'s
   trade-row fallback reads `regime.get("vol")` (the older `regime.py`
   vocabulary: `"expansion"/"contraction"/"normal"`). These overlap on the
   two most decision-relevant values (`expansion`/`contraction`) but not
   on the "no visible trend" case (`"stable"` vs `"normal"`) — a real,
   disclosed imprecision, not silently assumed to be identical.
4. **No new database means no index** — `find_by_ref()` is an O(n) scan of
   its history log; acceptable today (Sec.3.2), a documented future
   optimization otherwise.
5. **The similarity weights are not statistically fitted** — see Sec.4.

## 7. Integration — advisory-only, and how that's enforced structurally

`historical_context()`'s result is passed to `confidence_engine.assess()`
as the new, optional `memory_context` parameter. Inside `assess()`, this
parameter is read ONLY after `overall_confidence` has already been
computed and can only append to `supporting_rationale`/`assumptions` —
`test_memory_context_never_changes_overall_confidence` verifies this by
comparing three assessments (no memory context, insufficient-sample
context, rich-sample context) built from identical upstream inputs and
asserting `overall_confidence`/`tier` are byte-identical across all three.

`alert_signals.py` calls `log_market_memory_context()` at both Stage-1 and
Stage-2, purely for logging + the informational pass-through above — it
cannot hold, delay, or modify any signal. `dashboard_publish.py` surfaces
the same `historical_context()` result as its own top-level
`market_memory_advisory` payload key, DELIBERATELY separate from
`signal_payload` (the mandate: "Keep these clearly separated from live
trade recommendations") — never nested inside the trade recommendation
object.

### 7.1 Performance analytics

`performance_by_strategy_regime()`, `performance_by_confluence_profile()`,
`performance_by_session()`, `risk_adjusted_by_combo()` operate over the
FULL assembled history (not one query's top-K matches) and answer the
mandate's named research questions. Every bucket reports `n` and
`sufficient` (gated at `MIN_N_FOR_TRUST=30`, matching Day 5/6's
established bar) — a bucket below the bar is still RETURNED (transparency)
but with `risk_adjusted=None` where applicable, never silently hidden or
treated as if it were trustworthy.

## 8. Calibration-comparison addendum (platform owner's explicit decision)

Per the owner's Day 7 kickoff message: *"Build a raw-vs-composite
calibration view — yes, but not yet. Design the architecture now; keep it
inactive until enough live observations exist."*
`confidence_calibration.raw_vs_composite_comparison()` IS that
architecture: it compares the pre-existing `calibration.py` (raw Layer-1
confidence) against the Day 6 composite over the same matched trades, but
returns `{"active": False, "reason": "..."}` below
`MIN_N_FOR_CALIBRATION=30` matched trades — and, per the owner's
"not yet" instruction, it is NOT called from `report()` or any dashboard/
Telegram surface today (`test_not_wired_into_any_live_report_yet` confirms
this structurally). See `RESEARCH_MARKET_MEMORY.md` Sec.5 for the
activation trigger.
