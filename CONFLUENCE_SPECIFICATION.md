# CONFLUENCE SPECIFICATION — Adaptive Confluence Engine (Day 5)

Covers `engine/confluence_analysis.py`, `engine/confluence_history.py`, and
`engine/confluence_sandbox.py` (all new, 2026-08-03). Companion to
`ARCHITECTURE_SPECIFICATION.md` (Day 1 audit, which first flagged the ~45%
echo finding this document investigates), `RISK_SPECIFICATION.md` (Day 3),
`MARKET_REGIME_SPECIFICATION.md` (Day 4), and
`RESEARCH_CONFLUENCE_ENGINE.md` (the Day 5 research output).

**`engine/confluence.py` was not modified.** Every scored source, every
weight, every hard gate, and the checklist are exactly as they were before
Day 5. This document is an analysis layer read from `confluence.py`'s
output, not a replacement for it — per the Day 5 mandate: "the goal is not
to replace MAST."

---

## 1. Phase 1 — Complete confluence inventory

MAST scores 26 confirmation sources on top of Layer 1's own 45%-weighted
confidence (27 inputs total). For each, `engine/confluence_analysis.py`'s
`SOURCE_REGISTRY` documents: purpose, nominal point weights (positive/
negative), the informational-independence category (Phase 2, §2 below), and
named overlaps with other sources — all derived directly from reading
`confluence.py`'s scoring code and every confirmation module's own
docstring, not from assumption.

| Source | Module | Nominal weight | Category | Shares mechanism/data with |
|---|---|---|---|---|
| Layer 1 ICT/SMC confidence | `signals.py` | 45% of confidence (≤42.75 pts) | *(anchor)* | — |
| Price action | `price_action.py` | +8 / −5 | Primary | candlestick (sibling) |
| Trend (HTF stack + ADX) | `trend_quality.py` | +10 / −6 | Derived | Layer 1 |
| Breakout quality | `breakout.py` | +6 / −6 | Supporting | Layer 1 |
| Mean reversion | `mean_reversion.py` | 0 / −10 | Primary | — |
| Wyckoff | `wyckoff.py` | +8 / −5 | **Duplicate** | Layer 1 |
| Volume profile | `volume_profile.py` | +5 / −3 | Primary | — |
| Macro (USD) | `correlation.py` | +6 / −6 | Primary | — |
| News | `bias_adjust.py` | +6 / −6 | Primary | — |
| Session/kill-zone timing | `structure.in_killzone` | +4 / 0 | **Duplicate** | Layer 1, session_model |
| Regime volatility | `regime.py` | +3 / 0 | Supporting | — (unlabeled — see §2.3) |
| COT positioning | `cot_feed.py` | +5 / −5 | Primary | — |
| Spread/basis | `spread_feed.py` | +4 / −4 | Primary | — |
| Seasonality | `seasonality.py` | +3 / −2 | Primary | — |
| Cross-asset risk sentiment | `risk_sentiment.py` | +4 / −4 | Primary | — |
| RSI divergence | `momentum_divergence.py` | +5 / −6 | Primary | — |
| Pivot level confluence | `pivots.py` | +4 / −3 | Supporting | Layer 1 |
| Candlestick pattern | `candlestick_patterns.py` | +4 / −4 | Supporting | price_action (sibling) |
| Breaker/mitigation block | `breaker_blocks.py` | +5 / −4 | Derived | Layer 1 |
| Fibonacci confluence | `fibonacci.py` | +4 / 0 | Derived | Layer 1 (OTE) |
| Chart pattern | `chart_patterns.py` | +5 / −4 | Primary | — |
| Liquidity strength | `liquidity_strength.py` | +4 / −3 | Supporting | — |
| BPR / consequent encroachment | `balanced_range.py` | +3 / 0 | Derived | Layer 1 |
| Fibonacci ABC expansion | `fibonacci.py` (`alignment_abc`) | +3 / 0 | Primary | fibonacci (sibling) |
| Session model (Judas Swing) | `session_model.py` | +4 / −4 | Supporting | Layer 1, session_timing |
| Elliott Wave | `elliott_wave.py` | +3 / −3 | Primary | icc, chart_pattern (sibling) |
| ICC | `icc.py` | +3 / −3 | **Legacy** | elliott_wave, chart_pattern |

Full purpose/inputs/outputs/dependencies/assumptions text for each source
lives in `SOURCE_REGISTRY[key]["note"]` in `engine/confluence_analysis.py`
— reproduced narratively in §2 below rather than duplicated verbatim here.

### 1.1 Dependency map

```
Layer 1 (signals.py)
  reads: structure.py (swings, BOS/CHoCH, structure_trend+EMA21/55 fallback),
         ict_confluence.py (sweep, displacement, OTE, order block),
         technicals.ema, structure.in_killzone
        |
        v
MAST confluence.py (Layer 2) — reads Layer 1's Signal object directly (sig.confidence,
  sig.entry/stop/target, sig.direction), plus:
  |
  +-- price_action.py -------- (own candle math, no shared primitives)
  +-- trend_quality.py ------- technicals.ema, technicals.macd
  +-- breakout.py ------------ structure.atr
  +-- mean_reversion.py ------ technicals.rsi/bollinger_pctb/rolling_vwap, structure.atr
  +-- wyckoff.py ------------- ict_confluence.liquidity_sweep [SAME FN Layer 1 uses],
  |                            price_action.momentum_candle, regime.classify
  +-- volume_profile.py ------ (own binning math, no shared primitives)
  +-- correlation.py --------- (own DXY fetch/cache)
  +-- bias_adjust.py --------- fundamentals_feed.py (live news feed)
  +-- cot_feed.py ------------ CFTC public API (own fetch/cache)
  +-- spread_feed.py --------- yfinance (own fetch/cache)
  +-- seasonality.py --------- (calendar table, no data dependency)
  +-- risk_sentiment.py ------ yfinance VIX/SPX (own fetch/cache)
  +-- momentum_divergence.py - technicals.rsi, own swing-pivot detection
  +-- pivots.py --------------- own prior-period OHLC math
  +-- candlestick_patterns.py - own candle math (parallel to price_action.py)
  +-- breaker_blocks.py ------ structure.find_fvgs, structure.find_swings [SHARED]
  +-- fibonacci.py ------------ structure swing highs/lows [SHARED]
  +-- chart_patterns.py ------ structure.find_swings [SHARED]
  +-- liquidity_strength.py -- structure.classify_swing_strength [SHARED, not used by Layer 1's confidence]
  +-- balanced_range.py ------ structure.find_fvgs [SHARED]
  +-- session_model.py ------- structure.in_killzone's session-hour convention [SHARED]
  +-- elliott_wave.py -------- structure.find_swings [SHARED]
  +-- icc.py ------------------ structure.find_swings [SHARED]
  +-- regime.py --------------- (used directly for the vol +3/+2 score, AND
                                 indirectly inside wyckoff.py's phase field)
```

`structure.py` is the single most load-bearing shared dependency: 8 of the
26 confirmation sources call one of its functions, and Layer 1 itself is
built on it. This is expected and healthy (one well-tested swing/FVG/ATR
library, not eight reimplementations) — the independence concern in §2 is
about which sources score the SAME underlying event as something already
counted, not about sharing utility code.

## 2. Phase 2 — Independence analysis

Every source is classified using confluence.py's actual scoring code and
each module's own docstring as ground truth (not intuition):

- **Primary Evidence** — genuinely independent data or mechanism, not
  derived from Layer 1's inputs; a real, orthogonal information axis.
- **Supporting Evidence** — different mechanism/data than Layer 1, but
  measures a correlated underlying phenomenon.
- **Derived Evidence** — built substantially from Layer 1's own primitives,
  repackaged with real but partial incremental value.
- **Duplicate Evidence** — scores the literal same underlying
  computation/boolean something else already scored.
- **Legacy Evidence** — present for completeness; weak provenance and/or
  smallest incremental value among a cluster of siblings measuring the same
  thing.

**Category counts** (`confluence_analysis.registry_summary()`):

| Category | Count |
|---|---|
| Primary | 13 |
| Supporting | 6 |
| Derived | 4 |
| Duplicate | 2 |
| Legacy | 1 |

**13 of 26 (50%) are genuinely independent (Primary).** This is a more
favorable picture than "45% is an echo" might suggest in isolation — most
of MAST's breadth IS real, orthogonal evidence (external data feeds:
macro, news, COT, spreads, seasonality, risk sentiment; genuinely new
mechanisms: candle geometry, oscillator shape, multi-swing pattern
recognition, volume profile). The problem is concentrated in a specific,
identifiable minority, detailed next.

### 2.1 The three concrete "echo" findings

**Finding 1 — the direct 45% weight.** `ict_pts = sig.confidence * 0.45` is
not itself wrong (Layer 1's read genuinely matters and confluence is
supposed to confirm it), but it means every OTHER source that correlates
with Layer 1's own inputs (structure trend, sweep, session timing) is
double-counting evidence already embedded in that 45%.

**Finding 2 — the session-timing triplicate**
(`confluence_analysis.SESSION_TIMING_TRIPLICATE`). THE single clearest,
most mechanically verifiable overlap in the engine: `structure.in_killzone()`
is called and scored **three separate times** under three different names:

1. Inside Layer 1's own `sig.confidence` (+8, `signals.py` line ~183-185).
2. Directly inside `confluence.analyze()` itself (+4, `in_kz` variable,
   labeled `"session/kill-zone timing"`).
3. Indirectly inside `session_model.py`'s Judas-Swing logic, which uses
   "the same session-hour convention already established elsewhere in the
   engine" per its own docstring (+4/−4, labeled
   `"session model (Judas Swing...)"`).

The same boolean (are we in the 07:00-10:00 or 12:00-15:00 UTC window)
contributes to the score under three names. `session_model.py`'s Judas-Swing
directional NARRATIVE is a genuinely distinct claim from a pure timing
bonus (worth Supporting Evidence on its own), but the underlying timing
FACT has by that point already been counted twice.

**Finding 3 — Wyckoff's Spring/Upthrust echo.** `wyckoff.py`'s own
docstring: *"mostly a translation + confirmation layer rather than new
detection logic."* Its Spring/Upthrust event detection calls
`ict_confluence.liquidity_sweep()` — the exact same function Layer 1
already used for its own +12 sweep bonus. Whenever Layer 1's sweep bonus
fired, Wyckoff's dominant scoring component (`event`) is very likely to
fire too, for the same underlying reason. This is the module most honestly
self-described as duplicative anywhere in the codebase.

### 2.2 Sibling-cluster overlaps (not Layer-1 echoes, but real redundancy)

Independent of Layer 1, some confirmation sources substantially overlap
with EACH OTHER:

- **Multi-swing geometry cluster**: `elliott_wave.py`, `chart_patterns.py`,
  and `icc.py` all detect patterns from the same `structure.find_swings()`
  output at different rule-complexity levels. `icc.py`'s own docstring
  positions itself as "closer to just wave 1-2-3" of Elliott Wave's full
  test — the least rigorous of the three, and the one most likely to be
  fully subsumed by the other two. This is why `icc` is classified Legacy.
- **Candle-geometry cluster**: `price_action.py` and
  `candlestick_patterns.py` both read candle shape (pin bars/engulfing
  overlap conceptually with the broader pattern library). Neither echoes
  Layer 1, but they likely echo each other.
- **Fibonacci cluster**: `fibonacci.py`'s own docstring states the ICT OTE
  zone Layer 1 already scores IS the golden-ratio retracement band "under a
  different name" — its retracement-confluence component substantially
  echoes Layer 1's OTE bonus, while its extension-level and ABC-expansion
  components are genuinely new (hence `fibonacci`: Derived,
  `fibonacci_abc`: Primary — the two components were assessed separately
  despite being computed by the same module).

### 2.3 An invisible source: regime_vol

`confluence.py` scores `regime.classify()`'s volatility read (+3
expansion / +2 normal) by adding directly to `score` with **no
`agree.append()` call at all**. It contributes points but is invisible in
`cr.agree`/`cr.disagree` — a real, previously undocumented explainability
gap. `confluence_analysis.explain()` surfaces this explicitly as
`"unlabeled_sources": ["regime_vol"]` on every trade read, satisfying the
Day 5 mandate's "missing evidence" requirement in the most literal possible
sense: this is evidence MAST itself doesn't tell you it used.

### 2.4 Weak-provenance cluster (a separate, orthogonal finding)

Three modules (`balanced_range.py`, `session_model.py`, `icc.py`) each
independently disclose in their own docstrings that their named source
document ("Smart Money 200-Page Master Guide") turned out to be templated
boilerplate with no unique operational rule, and were reimplemented from
general domain knowledge instead. This is a documentation-provenance
finding, not an independence-of-mechanism finding — assessed separately in
`confluence_analysis.WEAK_PROVENANCE_SOURCES` — but worth flagging as its
own pattern: three of the newest-added modules share this caveat.

## 3. Phase 3/4/9 — Contribution measurement and adaptive weighting

Framework is fully built (`confluence_analysis.measure_contribution()`,
`recommend_weight_adjustments()`, `join_trades_with_confluence()`) but
**currently returns "insufficient_data" for every one of the 26 sources**,
because `trades.json` has zero closed trades with a populated
`confluence_score` field. See `RESEARCH_CONFLUENCE_ENGINE.md` §1 for the
full, honest accounting of what data exists and what doesn't, and §2-3 for
the measurement methodology and minimum sample sizes required before any
weight-adjustment recommendation is trusted.

**No weight in `confluence.py` was changed.** `recommend_weight_adjustments()`
produces advisory output only; it has no write access to `confluence.py`
and nothing in the live path reads its recommendations automatically. This
satisfies the mandate's explicit requirement: *"Adaptive weighting is
designed but not allowed to alter production automatically."*

## 4. Phase 5 — Explainable Confluence

`confluence_analysis.explain(cr)` returns, for one confluence read:

```python
{
    "positive": [...],       # sources that agreed, ranked by reconstructed impact
    "negative": [...],       # sources that disagreed, ranked by reconstructed impact
    "neutral": [...],        # sources that produced no signal ("missing evidence")
    "highest_impact": {...}, # single largest-magnitude contributor (either direction)
    "lowest_impact": {...},
    "conflicting_evidence": [...],  # sources sharing a mechanism that landed on opposite sides
    "missing_evidence": [...],      # alias of `neutral` — both terms appear in the mandate
    "unlabeled_sources": ["regime_vol"],  # see §2.3
    "rationale": "...",      # one human-readable paragraph
}
```

**Point values are reconstructed, not authoritative** — `ConfluenceRead`
stores source NAMES in `agree`/`disagree`, not exact point deltas
(several sources have conditional sub-weights; `confluence.py` adds
straight to `score` inline). `explain()` uses `SOURCE_REGISTRY`'s
documented nominal weight (the value used in the module's most common
branch) rather than modifying `confluence.py` to expose exact deltas — the
module docstring states this precisely, and `RESEARCH_CONFLUENCE_ENGINE.md`
names the specific sources where nominal and actual can diverge (trend
quality's three-way split, Wyckoff's capped sum, volume profile's
approx-data discount, and news — whose exact delta isn't stored on
`ConfluenceRead` at all, a distinct small gap also flagged there).

## 5. Phase 6 — Confluence Quality Score

Separate from `cr.score` (confluence.py's own confidence number).
`confluence_analysis.quality_score(cr)`:

```
score = 100 * (0.35*diversity + 0.35*independent_agreement
              + 0.15*cross_tf_consistency + 0.15*(1 - conflict_penalty))
```

- **diversity**: fraction of the four non-anchor categories
  (primary/supporting/derived/duplicate/legacy minus the always-absent
  anchor) represented among AGREEING sources. Five agreeing Duplicate
  sources score lower on this axis than one Primary + one Supporting + one
  Derived agreeing — rewarding breadth of evidence TYPE, not count.
- **independent_agreement**: agreeing sources weighted by category
  (`primary=1.0, supporting=0.8, derived=0.4, duplicate=0.1, legacy=0.3`)
  before averaging — this is the mechanism that directly answers "a high
  score should indicate strong, diverse confirmation, not simply more
  confirmations," per the Day 5 mandate's own Phase 6 wording.
- **cross_tf_consistency**: reuses `confluence.py`'s own already-computed
  `trend_quality` read (`continuation_ok`/`htf_agrees`) rather than
  inventing a new timeframe check.
- **conflict_penalty**: fraction of touched sources that disagreed.

Tested directly: `tests/test_confluence_analysis.py::
test_quality_score_rewards_diverse_independent_agreement` constructs two
reads with the SAME COUNT of agreeing sources — five Duplicate/Derived vs.
five Primary/Supporting — and asserts the diverse-independent set scores
higher, verifying the design goal empirically rather than just by
construction.

## 6. Phase 7 — Conflict resolution

`confluence_analysis.conflict_resolution(cr)` detects the mandate's own
named examples from already-computed `cr.layers` data (no new
calculations, no change to `cr.score`/`cr.final_tier`):

| Pattern | Trigger | Recommendation |
|---|---|---|
| `strong_ict_weak_macro` | `cr.score >= 80` and macro alignment is `False` | Treat as a lower-conviction version of a high-score setup; not a hard gate. |
| `strong_structure_poor_liquidity` | `base_tier == "confirmed"` and liquidity strength disagreed | Structural read is real; target distance may be optimistic — caution on target, not direction. |
| `bullish_technicals_high_impact_news` | HIGH-strength news signal present and `cr.score >= 70` | `news_guard.py`'s blackout hard-gate is unchanged; this surfaces the remaining case where strong news exists but hasn't triggered a full blackout. |
| `buying_above_value` | Long entry above volume-profile value area with `cr.score >= 70` | Not a rejection; flags one genuinely independent (Primary Evidence) source disagreeing with an otherwise strong read. |

Purely descriptive/logged — every pattern's `recommendation` is text for
the trader/operator, never a code path that changes what publishes.

## 7. Phase 8 — Research Sandbox

`engine/confluence_sandbox.py` implements the mandate's required pipeline
as a JSON-backed governance registry:

```
research -> historical_testing -> walk_forward -> paper_trading -> production_recommendation
```

`advance_stage()` enforces one-stage-at-a-time progression (raises
`ValueError` on any attempt to skip a stage) and requires a non-empty
evidence note on every transition, so the registry itself is the audit
trail proving a candidate was validated before it mattered.

**The load-bearing guarantee**: `engine/confluence.py` has zero import of,
or reference to, `confluence_sandbox` — verified directly by
`tests/test_confluence_sandbox.py::test_confluence_module_never_imports_sandbox`,
which inspects `confluence.py`'s actual source text. A candidate reaching
`"production_recommendation"` status has exactly zero runtime effect;
promoting it into `confluence.py`'s real scored source list remains a
separate, deliberate, human-reviewed code change — the same review any
existing source went through when it was added.

## 8. Phase 10 — Integration

### 8.1 Interfaces

```python
# engine/confluence_analysis.py
SOURCE_REGISTRY: dict            # 27 entries, see §1
registry_summary() -> dict       # category counts
explain(cr) -> dict              # Phase 5
quality_score(cr) -> dict        # Phase 6
conflict_resolution(cr) -> list  # Phase 7
measure_contribution(source_key, labeled_trades, min_n=30) -> dict     # Phase 3/9
recommend_weight_adjustments(labeled_trades, min_n=30) -> list          # Phase 4
join_trades_with_confluence(trades_rows, history_rows) -> list          # Phase 3/9

# engine/confluence_history.py
record(symbol, direction, cr_score, cr_final_tier, agree, disagree, quality, conflicts) -> dict
tail(n=20, symbol=None) -> list
all_rows() -> list

# engine/confluence_sandbox.py
register_candidate(name, description, hypothesis="") -> dict
advance_stage(name, new_stage, evidence_note) -> dict   # raises ValueError on invalid transition
get_candidate(name) -> dict | None
list_candidates(stage=None) -> list
is_production_ready(name) -> bool

# alert_signals.py
log_confluence_explainability(sym, cr) -> None   # calls quality_score + conflict_resolution
                                                  # + confluence_history.record(), fail-safe
```

### 8.2 Pipeline position

```
Market Regime Engine (Day 4)
        |
        v
ICT/SMC Origination (signals.analyze — UNCHANGED)
        |
        v
MAST Confluence (confluence.analyze — UNCHANGED: score, hard gates, checklist all as before)
        |
        v
[Day 5: log_confluence_explainability() — reads cr, computes explain()/
 quality_score()/conflict_resolution(), records to confluence_history.jsonl
 + the ledger. Runs on EVERY confluence read, both alert stages, regardless
 of final_tier — purely additive, changes nothing about what publishes.]
        |
        v
Risk Engine (risk_guard — UNCHANGED, Day 3)
        |
        v
Portfolio Risk (portfolio_risk — UNCHANGED, Day 3)
        |
        v
Trade Approval / Publication
```

### 8.3 Forward interfaces (Confidence Engine / Market Memory, future)

Per the mandate's Phase 10 request to integrate cleanly with future
systems: `quality_score()`'s output (a 0-100 score independent of
`cr.score`) and `explain()`'s structured breakdown are designed to be
directly consumable by a future Day 6 Confidence Engine (a calibrated
probability estimate would naturally want BOTH the raw confidence number
AND a measure of evidence quality/independence as inputs, not just the
former) and by a future Market Memory system (`confluence_history.jsonl`
is already the append-only event log such a system would read from,
following the exact same pattern `regime_history.jsonl` established in
Day 4). No code in either future system exists yet — this is a documented
design compatibility, not a built integration.

## 9. Known limitations (documented, not silently assumed)

1. **Point-value reconstruction is nominal, not exact**, for sources with
   conditional sub-weights (trend quality, Wyckoff, volume profile) — see
   §4. `RESEARCH_CONFLUENCE_ENGINE.md` names the specific affected sources.
2. **News's exact point delta isn't stored on `ConfluenceRead` at all**
   (a `confluence.py` architecture gap, not a Day 5 introduction) — worked
   around via the nominal HIGH-strength value; a genuinely more accurate fix
   would require a small `confluence.py` change to persist
   `ba.adjustment()`'s return value, deferred as out of scope for "reuse,
   don't restructure."
3. **No historical data exists yet to run Phase 3/4/9's measurement
   framework for real** — see `RESEARCH_CONFLUENCE_ENGINE.md` §1 for the
   full honest accounting.
4. **`quality_score()`'s category weights (1.0/0.8/0.4/0.1/0.3) and the
   0.35/0.35/0.15/0.15 formula weights are domain-reasonable, not
   statistically fitted** — same disclosure convention as Day 4's
   transition-risk weights and `structure.classify_swing_strength()`'s own
   precedent. Calibration candidate once `confluence_history.jsonl` +
   labeled outcomes accumulate.
