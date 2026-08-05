# CONFIDENCE ENGINE SPECIFICATION — Calibrated Decision Quality (Day 6)

Covers `engine/confidence_engine.py`, `engine/confidence_history.py`, and
`engine/confidence_calibration.py` (all new, 2026-08-03). Companion to
`RISK_SPECIFICATION.md` (Day 3), `MARKET_REGIME_SPECIFICATION.md` (Day 4),
`CONFLUENCE_SPECIFICATION.md` (Day 5), and `RESEARCH_CONFIDENCE_ENGINE.md`
(this day's research output).

**No ICT/SMC origination logic, Regime Engine logic, or Confluence Engine
logic was modified.** Two small, disclosed, additive exceptions inside
`engine/confluence.py` are documented in Sec.6 below (Observability
Enhancements) — neither changes a score or a gate.

## 1. Primary objective

The Confidence Engine does not create trade ideas. It runs LAST, after
origination, regime classification, confluence confirmation, and risk/
portfolio validation have all already happened, and produces a single
structured, explainable synthesis of how much decision-quality that
already-validated evidence represents. It cannot hold, downgrade, or
reject a trade — it has no `allow`/`reject` field at all (see
`ConfidenceAssessment`'s field list, Sec.2). Its only two effects on the
live system are: (1) an extra line in the Telegram message and dashboard
payload, and (2) a new row in `confidence_history.jsonl`.

## 2. The ConfidenceAssessment object

Every field, as implemented in `engine/confidence_engine.py`:

| Field | Type | Meaning |
|---|---|---|
| `symbol`, `direction` | str | Identity |
| `timestamp` | str (ISO8601 UTC) | When this assessment was made |
| `version` | dict | `{"confidence_engine": "1.0.0", "schema": 1}` |
| `overall_confidence` | int 0-100 | The headline composite score — see Sec.3 |
| `tier` | str | One of five decision tiers — see Sec.4 |
| `probability_label` | str | Explicit statement of what `overall_confidence` is/isn't (see Sec.5) |
| `calibrated_probability` | float or None | Empirical win rate for this score's bucket, only when enough real data exists |
| `is_calibrated` | bool | True only when `calibrated_probability` came from real matched outcomes |
| `evidence_quality` | int 0-100 | Coverage/completeness of available evidence — see Sec.3.2 |
| `evidence_diversity` | int 0-100 | Category diversity of agreeing confluence sources (Day 5's `quality_score()["diversity"]`, reused, scaled to 0-100) |
| `market_quality` | int 0-100 | Session timing + data freshness + regime stability — see Sec.3.3 |
| `regime_confidence` | int 0-100 | Day 4 Market Regime Engine's own `confidence` field, reused directly |
| `confluence_quality` | int 0-100 | Day 5's independence-weighted `quality_score()["score"]`, reused directly |
| `portfolio_status` | dict | `{allow, would_block, category, reason, heat}` — summary of Day 3's `portfolio_risk.evaluate()` |
| `risk_status` | dict | `{guard_action, guard_penalty, risk_locked, macro_headwind}` — summary of `range_guard`/`risk_guard` |
| `uncertainty_indicators` | list[str] | Named, explicit uncertainty flags — see Sec.7 |
| `supporting_rationale` | list[str] | What agrees, pulled from already-computed upstream evidence |
| `conflicting_rationale` | list[str] | What disagrees, likewise |
| `highest_impact_evidence` / `lowest_impact_evidence` | str or None | Reuses Day 5's `explain()` ranking, not recomputed |
| `assumptions` | list[str] | What could invalidate this specific assessment |

`ConfidenceAssessment.as_dict()` and `.summary_line()` are the two public
convenience methods (used by `confidence_history.record()` and by the
Telegram/dashboard integration respectively).

## 3. overall_confidence composition

`assess()` never re-fetches or re-derives upstream data — every input is a
parameter, already computed once by the caller (`alert_signals.py` computes
`sig`, `mkt_regime`, `cr`, `portfolio_verdict`, `guard`, `news_state` once
per scan already, before this module is ever called).

### 3.1 The formula

```
base_evidence      = cr.score if cr is not None else sig.confidence
quality_modifier    = 0.70 + 0.30 * (confluence_quality / 100)
regime_modifier      = 0.85 + 0.15 * (regime_quality_score / 100)
guard_penalty        = abs(guard.penalty)
portfolio_penalty     = 10 if portfolio_verdict.would_block else 0
risk_lock_penalty      = 15 if risk_locked else 0

overall_confidence = clamp(0, 100, round(
    base_evidence * quality_modifier * regime_modifier
    - guard_penalty - portfolio_penalty - risk_lock_penalty
))
```

**Disclosed, not statistically fitted** — these weights are engineering
judgment, exactly like Day 4's transition-risk weights and Day 5's
quality-score formula weights before them. `assumptions` on every
`ConfidenceAssessment` says so explicitly, and `RESEARCH_CONFIDENCE_ENGINE.md`
documents the calibration plan that would let real data validate or revise
them.

### 3.2 Why base_evidence is EITHER cr.score OR sig.confidence, never both

`cr.score` (Day 5's MAST confluence score) already embeds Layer 1's own
`sig.confidence` at 45% weight (`ict_pts = sig.confidence * 0.45`,
`confluence.py`). Adding `sig.confidence` again on top of `cr.score` would
reproduce, at the Confidence Engine layer, exactly the "Layer 1 confidence
echoed through other layers" problem the Day 1 audit found and Day 5
investigated. `base_evidence` uses `cr.score` whenever a confluence read
exists (the normal case) and only falls back to `sig.confidence` directly
when `cr` is `None` (confluence engine unavailable) — this is a design
decision `test_overall_confidence_never_double_counts_layer1_via_addition`
verifies directly.

### 3.3 evidence_quality — distinct from confluence_quality

`confluence_quality` (Day 5's own metric) measures how INDEPENDENT the
agreeing evidence is. `evidence_quality` is a different question: how much
of the AVAILABLE evidence actually reported something this pass, regardless
of what it said. It averages three components: confluence source coverage
(`touched / 26`), regime per-timeframe data sufficiency (Day 4's own
`sufficient` flag, reused), and external-service health (did regime/news/
confluence report a degraded state). A read where five sources fired and
twenty-one stayed silent has lower `evidence_quality` than one where
twenty sources fired, even if the twenty that fired were mostly Duplicate/
Derived (that redundancy concern is `confluence_quality`'s job, not this
field's).

### 3.4 market_quality — environment quality, not signal quality

Averages session kill-zone alignment (`"KZ" in session`), data freshness
(`data_stale` flag, relevant in dashboard/resilient-fetch contexts), and
Day 4's own regime tags (`Illiquid`/`News-Driven`/`High Volatility` reduce
this score). This deliberately does NOT duplicate `confluence.py`'s own
+4 session-timing confluence point (see Sec.6) — that scores whether the
CONFLUENCE read should count kill-zone timing as confirming evidence;
`market_quality` scores whether the CURRENT environment is good-quality for
acting on anything at all, independent of direction.

## 4. Decision tiers

| Tier | Default floor | Rationale |
|---|---|---|
| Exceptional Confidence | 85 | New intermediate band, roughly mirrors grade.py's A+ spacing |
| High Confidence | 70 | Matches `signals.PUBLISH_THRESHOLD` / `confluence_min_score`'s default — the platform's existing "confirmed/tradeable" bar |
| Moderate Confidence | 55 | Matches `signals.WATCH_THRESHOLD` — the existing "worth watching" bar |
| Low Confidence | 40 | New intermediate band |
| Research Only | < 40 | Below any existing actionable threshold |

Boundaries are configurable via `config.py`'s `confidence_tier_*` fields
(Sec.9), read fresh on every `classify_tier()` call — an operator can retune
without a code change. `classify_tier()` never returns a raw number to a
caller without a label attached; every consumer (Telegram, dashboard) shows
the tier name alongside the score specifically to avoid presenting false
numerical precision (mandate: "avoid presenting false numerical
precision").

## 5. Confidence vs. probability — the calibration boundary

`overall_confidence` is NEVER shown or treated as a probability of winning
unless `confidence_calibration.py` has verified enough real matched
outcomes exist for its bucket. `probability_label` states which case
applies on every single assessment:

- **Uncalibrated (the only case possible on Day 6 itself — see
  `RESEARCH_CONFIDENCE_ENGINE.md`):** *"internal decision-quality estimate
  — NOT a statistically calibrated probability (insufficient historical
  data)"*. `calibrated_probability` is `None`.
- **Calibrated (once real data accumulates):** *"calibrated against N
  historical trades in this confidence bucket"*. `calibrated_probability`
  is the empirical win rate for that bucket.

This is enforced by `confidence_calibration.calibrated_probability_for()`,
which `assess()` calls on every invocation — see Sec.8.

## 6. Observability enhancements (approved, additive-only)

Two small changes to `engine/confluence.py`, both purely additive
(confirmed by the full regression suite — no score or gate changed):

1. **`regime_vol` is now labeled.** Previously `confluence.py` added its
   +3 (expansion) / +2 (normal) points directly to `score` with no
   `agree.append()` call at all — Day 5's `explain()` had to hard-code
   `"regime_vol"` into `unlabeled_sources` because it was structurally
   invisible. `confluence.py` now calls `agree.append("regime volatility
   (expansion)")` / `("normal")` alongside the same, unchanged point
   addition. `confluence_analysis.py`'s `LABEL_PATTERNS`, `explain()`, and
   the regression label-matching test were all updated to match.
2. **The exact news point delta is now persisted.** `ConfluenceRead` gained
   a `news_delta: int = 0` field, set to `bias_adjust.adjustment()`'s
   already-computed return value (previously computed, added to `score`,
   and then discarded — never stored anywhere on the object).
   `confluence_analysis._source_points()` now uses this real value for the
   `"news"` source instead of a nominal approximation, closing one of the
   two precision gaps `RESEARCH_CONFLUENCE_ENGINE.md` flagged as backlog.

## 7. Uncertainty engine

`uncertainty_indicators` is a list of named strings, never a score
modifier by itself (the score-level penalties in Sec.3.1 are separate and
explicit) — per the mandate: "Uncertainty should reduce trust in the
assessment without necessarily rejecting the trade." Checks performed,
each independently:

insufficient historical data for calibration; conflicting evidence
(Day 5's `conflict_resolution()` found a pattern); confluence engine
unavailable; incomplete market data (`evidence_quality < 60`); degraded
regime-engine service; degraded news/calendar service; missing macro
input (`cr.layers["macro"]["aligned"] is None`); unstable/elevated
correlation vs. an open position (Day 3's portfolio detail); regime in
transition (Day 4's `transition_label`).

`test_uncertainty_does_not_reject_the_trade` confirms structurally that
`ConfidenceAssessment` has no `allow`/`reject` field — uncertainty can only
ever inform, never gate.

## 8. Calibration framework (`engine/confidence_calibration.py`)

Mirrors the pre-existing `engine/calibration.py` (which calibrates Layer
1's raw `sig.confidence` and has been in production since before Day 3)
rather than inventing a new methodology: same bucket/reliability/Brier-
score approach. A separate module, not an extension, because it calibrates
a different number (the Day 6 composite) against a different data source
(`confidence_history.jsonl` joined to `trades.json`, not `trades.json`'s
`confidence` field directly).

- `join_trades_with_confidence()` — prefers the direct `ref` match
  (Sec.9); falls back to the nearest-preceding-timestamp join Day 4/5
  established for trades logged before `ref` existed.
- `reliability()` / `brier()` — per-bucket realized win rate vs. predicted,
  and the overall Brier score.
- `calibrated_probability_for(overall_confidence)` — the single function
  `assess()` calls; returns `(None, False, n)` below `MIN_N_FOR_CALIBRATION`
  (30 — see Sec.8.1), `(realized_rate, True, n)` above it.
- `recommend_recalibration()` — flags systematic over/under-confidence per
  bucket where `n >= min_n`. **Never recalibrates automatically** — mirrors
  Day 5's `recommend_weight_adjustments()`: advisory only, any actual
  change to `confidence_engine.py`'s weights remains a deliberate,
  human-reviewed code edit.
- `rolling_evaluation(window_trades=50)` — calibration over only the most
  recent N matched trades, for drift detection over time rather than only
  against the ever-growing full history.

### 8.1 Why MIN_N=30, not calibration.py's MIN_N=8

`overall_confidence` is a compound metric (five sub-scores combined via
disclosed, not statistically fitted, weights). A higher trust bar before
treating its buckets as reliable is deliberate — same reasoning Day 5 used
for `MIN_N_FOR_CONTRIBUTION=30` instead of reusing `calibration.py`'s
`min_n=8`: more moving parts warrants more evidence before trusting a
systematic-bias finding.

## 9. Trade journal integration — stable references

Previously (Day 4/5), confluence and regime history could only be joined
to a closed trade by nearest-preceding timestamp — an approximation,
documented as such in both `RESEARCH_REGIME_ENGINE.md` and
`RESEARCH_CONFLUENCE_ENGINE.md`. Day 6 closes this gap for confluence and
confidence data (regime remains timestamp-joined; see Sec.11 backlog):

- `journal.make_ref(symbol, when)` returns `f"{symbol}-{timestamp}"` — the
  EXACT same format `Trade.id` already used internally, now extracted as
  its own function.
- `alert_signals.py` computes this string ONCE per Stage-2 entry (before
  calling `cf.analyze()`), and passes it through to
  `confluence_history.record(..., ref=trade_ref)`,
  `confidence_history.record(assessment, ref=trade_ref)`, and
  `journal.log_signal(..., confluence_ref=trade_ref,
  confidence_ref=trade_ref)`. The result: `trade.id == trade.confluence_ref
  == trade.confidence_ref` for every trade logged from Day 6 onward.
- `Trade` gained two new fields, both defaulting to `""`:
  `confluence_ref`, `confidence_ref`.
- `confluence_analysis.join_trades_with_confluence()` and
  `confidence_calibration.join_trades_with_confidence()` both now try the
  direct `ref` match FIRST, falling back to the original nearest-timestamp
  join only when `ref` is empty or unmatched (pre-Day-6 trades, or a
  Stage-1 heads-up read that never became a filled trade).

### 9.1 Backward compatibility

No migration script was written, and none was needed: `journal.py` reads
`trades.json` rows as plain dicts (never reconstructs a `Trade()` from
disk), so a pre-Day-6 row simply lacks the two new keys — every reader
uses `.get("confluence_ref", "")`, the same pattern every prior field
addition (`news_signal`, `regime_trend`, `confluence_score`, ...) already
established. `test_backward_compatible_read_of_pre_day6_rows` confirms
this directly against a synthetic legacy row with the keys deliberately
absent.

## 10. Integration points

```
Market Data -> Regime Engine (Day 4) -> ICT/SMC Origination -> MAST Confluence (Day 5)
    -> Risk Guard -> Portfolio Risk (Day 3) -> [Day 6: Confidence Engine] -> Publication
                                                        |
                                                        v
                                          confidence_history.jsonl (Day 6)
                                          Telegram confidence line
                                          dashboard_publish.py confidence_assessment block
                                          Trade.confidence_ref (Day 6)
```

Called at both Stage-1 (heads-up, `ref=""`, no trade yet) and Stage-2
(entry, `ref=trade_ref`) in `alert_signals.py`, and read-only in
`dashboard_publish.py`'s per-symbol payload build (that process
independently calls `regime_engine.classify()` and `portfolio_risk.evaluate()`
once, the same "each entry point computes its own read" pattern Day 4/5
already established — not a new duplication). `hourly_briefing.py` was
NOT touched, matching Day 5's precedent: it does not call
`confluence.analyze()` directly, so there is no confluence/confidence read
to attach in that file either.

## 11. Known limitations (documented, not silently assumed)

1. **No real calibration data exists yet** — `is_calibrated` is `False` on
   every assessment made today; see `RESEARCH_CONFIDENCE_ENGINE.md` §1.
2. **The composite formula's weights (Sec.3.1) are engineering judgment,
   not statistically fitted** — same disclosure convention as Day 4/5's
   own formula weights. `recommend_recalibration()` is the designed path
   to revising them once data exists, never automatic.
3. **Regime data is still timestamp-joined, not ref-joined** —
   `regime_history.py` was not extended with a `ref` parameter this Day
   (only confluence/confidence were, per the mandate's explicit "Trade
   Journal Integration" scope); flagged as a natural Day 7+ follow-up in
   `DAY6_NEXT_DAY_READINESS_REPORT.md`.
4. **`dashboard_publish.py`'s confidence block calls a fresh
   `regime_engine.classify()` and `portfolio_risk.evaluate()`** rather than
   reusing `alert_signals.py`'s in-scan objects — unavoidable, since these
   are separate OS processes with no shared memory; consistent with every
   other cross-process duplication already present in this codebase (e.g.
   `dashboard_publish.py` already independently calls `regime.classify()`
   and `cf.analyze()` today).
