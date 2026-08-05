# MARKET REGIME SPECIFICATION — Gold/US Oil High Probability Platform

**Day 4 deliverable.** Covers `engine/regime_engine.py` (the new Market
Regime Engine) and `engine/regime_history.py` (its historical store),
implemented 2026-08-03. Companion to `ARCHITECTURE_SPECIFICATION.md` (Day 1
audit), `RISK_SPECIFICATION.md` (Day 3), and `RESEARCH_REGIME_ENGINE.md`
(the Day 4 research output and statistical validation plan).

---

## 1. What this is, and what it is not

The Regime Engine classifies the current market environment. It does not
originate, score, size, or approve trades — it produces structured context
that `signals.py` (origination), `confluence.py` (MAST scoring),
`risk_guard.py`/`portfolio_risk.py` (risk), and the operator (via logged
explainability) can read. By default it does not change what publishes;
`Settings.regime_filter_mode` defaults to `"advisory"` (log-only). See §7 for
why, and `RESEARCH_REGIME_ENGINE.md` for the plan to change that with
evidence.

Nothing in `signals.py`, `confluence.py`, `structure.py`, `ict.py`, or
`range_guard.py` was modified. The existing single-timeframe
`engine/regime.classify()` call inside `alert_signals.py::_guard_for()`
(which feeds `range_guard.py`) is untouched — it is a different, already-
tested input to a different, already-tested gate. The new engine is
additive.

## 2. Reuse inventory (what was NOT reimplemented)

| Need | Reused from | Not reimplemented |
|---|---|---|
| Per-timeframe trend classification (Kaufman Efficiency Ratio) | `engine.regime.classify()` / `efficiency_ratio()` | Trend/ER math |
| Per-timeframe volatility level (ATR percentile) | `engine.regime.atr_percentile()` | ATR math |
| Resampling 15m -> 1h/4h/1d/1w | `engine.data_loader.resample()` | Timeframe aggregation |
| Dealing range / range position | `engine.structure.dealing_range()`, `range_position()` | Swing-high/low range math |
| BOS/CHoCH structural events | `engine.structure.structure_series()` (read via `engine.ict.last_event()` where already computed) | Structure-break detection |
| Session / kill-zone context | `engine.ict.read()`'s `session` field / `engine.structure.in_killzone()` | Session-hour tables |
| News-calendar state | `engine.news_guard.evaluate()` | News blackout/calendar logic |
| Cross-asset correlation | `engine.correlation_dynamic.get_correlation()` (Day 3) | Correlation math |
| History persistence pattern | `engine.ledger.py`'s append/rotate/tail JSONL pattern, mirrored in `engine.regime_history` | A new persistence mechanism |

The Regime Engine's own new code is exactly: the multi-timeframe hierarchy
(§3), the finer taxonomy mapping (§4), the volatility-**trend** derivative
(§4.1, distinct from `regime.py`'s static level), transition-risk estimation
(§5), the strategy compatibility matrix (§6), and the quality score (§6.2).

## 3. Multi-timeframe hierarchy — not a vote

Five timeframes are classified independently (`1w, 1d, 4h, 1h, 15m`), each
via one call to the existing `regime.classify()`. They are then combined
with an explicit hierarchy, not a vote:

- **Strategic** (`1w`, falling back to `1d` when the weekly series has fewer
  than 22 resampled bars — realistically almost always, given the ~60-day
  fetch window the live data sources provide; see §8 known limitation)
  anchors the **primary regime label**. Nothing below it can override that
  label.
- **Tactical** (`4h`, `1h`) and **Execution** (`15m`) timeframes never
  change the primary label. They can only: (a) add to `confidence` when
  they agree with the strategic trend, (b) subtract from `confidence` and
  populate `conflicting_evidence` when they disagree, and (c) contribute to
  `transition_risk` (persistent bottom-up disagreement is one of three
  inputs to the transition-risk heuristic — see §5).

This directly implements the Day 4 mandate's explicit instruction to "avoid
simple voting systems" and "develop a hierarchy where higher timeframes
establish strategic context while lower timeframes refine tactical
conditions."

### 3.1 Confidence — fully explainable, not a black box

```
base = strategic_TF.efficiency_ratio * 100        # ER is already a natural 0-1 confidence measure
for each sufficient tactical/execution TF:
    if agrees with strategic trend: +2 * TF_weight
    if disagrees:                  -2 * TF_weight
confidence = clip(base + sum(adjustments), 0, 100)
```

`TF_weight` = `{1w:5, 1d:4, 4h:3, 1h:2, 15m:1}`. Every term of this sum is
returned in the result's `evidence`/`conflicting_evidence` lists as a
human-readable string (e.g. `"4h agrees (trend) -> +6"`), so the number is
always traceable to its inputs.

## 4. Regime taxonomy and mapping

The strategic TF's `regime.classify()` output (`trend`, `phase`, `er`) maps
onto the Day 4 taxonomy as follows:

| `regime.classify()` output | Mapped primary label |
|---|---|
| `trend=="trend"`, `er >= 0.55`, phase contains "uptrend"/"markup" | **Strong Bull Trend** |
| `trend=="trend"`, `er < 0.55`, phase contains "uptrend"/"markup" | **Weak Bull Trend** |
| `trend=="trend"`, `er >= 0.55`, phase contains "downtrend"/"markdown" | **Strong Bear Trend** |
| `trend=="trend"`, `er < 0.55`, phase contains "downtrend"/"markdown" | **Weak Bear Trend** |
| `trend=="range"`, phase contains "distribution" | **Distribution** |
| `trend=="range"`, phase contains "accumulation" | **Accumulation** |
| `trend=="range"`, otherwise (mid-range/consolidation) | **Range** |
| insufficient data | **Unknown** |

`0.55` (`STRONG_ER`) is a new, separate threshold from `regime.py`'s own
`TREND_ER=0.35` (which only distinguishes trend-vs-range) — it further
splits the "trend" bucket into Strong/Weak. Not statistically fitted; a
domain-reasonable midpoint above the trend/range boundary, labeled here as
such (same disclosure convention `structure.classify_swing_strength()`
already uses in this codebase). Candidate for calibration once
`regime_history.jsonl` accumulates enough data — see
`RESEARCH_REGIME_ENGINE.md`.

### 4.1 Volatility: level vs. trend, and the remaining taxonomy tags

`regime.py`'s `atr_percentile()` gives the current volatility **level**
(0-1 percentile). The Regime Engine additionally computes `_vol_trend()`:
the same `atr_percentile()` call run twice — once on the full series, once
with the most recent 10 bars removed — and compares them. This is a genuine
new capability (`regime.py` has no derivative/trend-of-volatility signal),
built from the exact same function called twice, not new ATR math.

Remaining taxonomy items are tags (a result can carry zero or more, they are
not mutually exclusive with the primary label):

| Tag | Condition |
|---|---|
| **High Volatility** | volatility trend is `"expansion"` AND current ATR percentile ≥ 0.85 |
| **Low Volatility** | volatility trend is `"contraction"` AND current ATR percentile ≤ 0.15 |
| **Expansion** | strategic TF trending AND volatility trend is `"expansion"` |
| **Contraction** | strategic TF ranging AND volatility trend is `"contraction"` |
| **Illiquid** | session is off-peak (`ict.read()`'s session field, when passed in) AND both strategic and 15m ATR percentile ≤ 0.15 |
| **News-Driven** | `news_guard.evaluate()` reports an active blackout OR a high-impact event within 30 minutes |

## 5. Transition framework

Markets do not switch regimes instantly, so `transition_risk` (0.0-1.0,
labeled low/medium/high) estimates how likely the CURRENT classification is
to change soon, rather than assuming stability. Three deterministic,
domain-labeled contributing factors (not a fitted probability — see below):

1. **Tactical/strategic disagreement.** The fraction of tactical-TF weight
   that disagrees with the strategic trend, scaled by 0.4. Persistent
   bottom-up divergence is a classic early sign of a strategic-level regime
   change.
2. **Volatility expanding while still range-bound** (+0.30 flat). This is
   the mandate's own worked example: "Contraction → Breakout." Rising
   volatility inside a still-ranging strategic structure is the textbook
   precursor to a breakout.
3. **Price near a dealing-range extreme** (position ≥0.85 or ≤0.15, +0.20
   flat). Proximity to resting liquidity that, if swept, commonly triggers
   the CHoCH that starts a new trend.

```
transition_risk = min(1.0, 0.4*disagree_fraction + 0.3*[expansion during range] + 0.2*[near range extreme])
label = "high" if >=0.6 else "medium" if >=0.3 else "low"
```

**Explicit limitation, stated plainly:** these three weights (0.4/0.3/0.2)
and their trigger thresholds are domain-reasonable heuristics chosen for
directional correctness (each factor genuinely should raise transition
risk), NOT a statistically fitted transition-probability model. Fitting a
real model requires a labeled dataset of actual regime changes, which is
exactly what `engine/regime_history.py` starts accumulating as of Day 4 —
see `RESEARCH_REGIME_ENGINE.md` for the calibration plan once enough
history exists.

### 5.1 Documented qualitative transition pathways

The mandate's own worked examples, and how this engine's outputs would
surface each one starting:

| Pathway | Early signal in this engine's output |
|---|---|
| Trending → Distribution | Strategic trend still "trend"/Bull, but tactical TFs start showing "range" with phase "distribution" -> rising `conflicting_evidence`, rising `transition_risk` |
| Distribution → Bear Trend | Primary label is "Distribution"; `transition_risk` elevated by proximity to range highs |
| Range → Expansion | Volatility trend flips to "expansion" while strategic trend is still "range" -> `Contraction`/pre-breakout tag, `transition_risk` factor 2 fires |
| Expansion → Trend | Volatility trend "expansion" persists and strategic ER climbs past 0.35 (regime.py's own trend threshold) -> primary label flips from Range/Accumulation/Distribution to a Trend label |
| Contraction → Breakout | Volatility trend "contraction" for a sustained period (visible in `regime_history.jsonl`'s duration field) followed by a flip to "expansion" |

## 6. Strategy compatibility matrix

The platform has exactly **one** production trade-origination strategy
today (`ict_smc_mast`: `signals.py` ICT/SMC origination + `confluence.py`
MAST scoring). `STRATEGY_COMPATIBILITY` in `regime_engine.py` is a
dict-of-dicts keyed by strategy name specifically so a second strategy is a
new dictionary entry, not an architectural change (Day 4's own "support
future expansion without architectural redesign" principle).

| Tier | Regimes | Why |
|---|---|---|
| Preferred | Strong Bull Trend, Strong Bear Trend | Clean structural breaks and displacement (which creates the FVGs this strategy enters on) are most reliable in strong trends. |
| Acceptable | Weak Bull Trend, Weak Bear Trend, Distribution, Accumulation | Weak trends still trend, just choppier. Distribution/Accumulation are the classic ICT liquidity-sweep-then-reversal setup — this strategy is explicitly designed to catch it. |
| Discouraged | Range | Choppy, low-ER conditions produce more false BOS signals. Not prohibited: MAST confluence and `range_guard.py` already provide signal-level filtering for choppy conditions — this matrix is descriptive context, not a new enforcement mechanism (avoiding duplicated logic, per the mandate). |
| Prohibited | Unknown | No evidence basis to act on at all. |

### 6.1 Quality score

```
base = {preferred: 80, acceptable: 60, discouraged: 35, prohibited: 10, unrated: 50}[compatibility]
confidence_adjustment = (confidence - 50) * 0.3        # range: -15 to +15
transition_risk_adjustment = -transition_risk * 20      # range: -20 to 0
quality_score = clip(base + confidence_adjustment + transition_risk_adjustment, 0, 100)
```

Every term is returned in `quality_detail` so the score is traceable, same
transparency standard as `confidence`. Like `STRONG_ER` and the
transition-risk weights, the base-per-tier numbers (80/60/35/10) are
domain-reasonable, not statistically fitted — flagged here rather than
silently presented as validated.

## 7. Integration — advisory by default, and why

`Settings.regime_filter_mode` defaults to `"advisory"`: the engine runs on
every scan, is logged to `regime_history.jsonl` and the ledger
(`{"event": "regime", ...}`), but never blocks publication.
`"block"` mode is fully implemented (`alert_signals.apply_regime_gate()`,
independently unit-tested) and suppresses a **new Stage-1 origination**
(never an already-published Stage-2 fill — publishing a HEADS-UP and then
retroactively blocking its own ENTRY would be a worse, more confusing user
experience than either publishing cleanly or not announcing at all) when
`quality_score < regime_min_quality_for_block` (default `30`).

This mirrors the exact evidence-first pattern already established twice in
this codebase: `range_guard.py`'s `SUPPRESS_MODE=False` ("we do not yet have
out-of-sample proof that guard-flagged trades lose... flip only after the
evidence is in") and Day 3's `portfolio_risk_mode`. Day 4's own mandate is
explicit on this point too: *"A regime filter should only remain in
production if it demonstrates an improvement in metrics such as expectancy,
drawdown, profit factor, or risk-adjusted returns."* No such evidence exists
yet — `regime_history.jsonl` did not exist before this Day 4 change — so
shipping `"block"` as the default would be exactly the "complexity without
measurable benefit" the mandate warns against. See
`RESEARCH_REGIME_ENGINE.md` §3 for the concrete plan to gather that
evidence and the promotion criteria.

### 7.1 Post-integration pipeline

```
Market Data (markets.fetch)
        |
        v
Market Regime Engine (regime_engine.classify) --------> regime_history.jsonl
        |                                                (every scan, every symbol)
        v
ICT/SMC Origination (signals.analyze)  <- UNCHANGED
        |
        v
[Day 4 advisory/block gate: apply_regime_gate() - only if mode="block"]
        |
        v
MAST Confluence (confluence.analyze)   <- UNCHANGED
        |
        v
Risk Engine (risk_guard.evaluate)      <- UNCHANGED (Day 3)
        |
        v
Portfolio Risk (portfolio_risk.evaluate) <- UNCHANGED (Day 3)
        |
        v
Trade Approval / Publication (_send)
        |
        v
Journal (journal.log_signal)           <- UNCHANGED: still receives the
        |                                  original single-TF regime.classify()
        v                                  snapshot via _guard_for(), not this
Dashboard                                  engine's output (see §8)
```

### 7.2 Interfaces

```python
# engine/regime_engine.py
classify(df15, symbol, strategy="ict_smc_mast", session_label=None,
        news_state=None) -> dict
    # {symbol, generated, primary, confidence, evidence, conflicting_evidence,
    #  transition_risk, transition_label, transition_factors,
    #  expected_behavior, quality_score, quality_detail, strategy,
    #  compatibility, tags, per_tf, vol_trend, range_pos, trend, vol}
line(result) -> str

# engine/regime_history.py
record(symbol, timeframe, result) -> dict   # appends + returns the written record
last_for(symbol, timeframe="strategic") -> dict | None
tail(n=20, symbol=None) -> list
transitions(symbol=None, n=50) -> list

# alert_signals.py
apply_regime_gate(mkt_regime, mode, min_quality) -> (blocked: bool, note: str)
```

## 8. Known limitations (documented, not silently assumed)

1. **Weekly timeframe is usually "insufficient."** The live data sources
   this platform uses (`markets.fetch`/`fetch_resilient`, both ultimately
   bounded by yfinance's `period="60d"` 15-minute-bar window) provide
   roughly 8-9 weekly bars, below the `MIN_BARS=22` threshold needed for
   `regime.classify()` to trust a weekly efficiency ratio. The engine
   degrades gracefully to `1d` as the strategic anchor (§3), which is
   correct fail-safe behavior, but means the "Weekly establishes the
   longest-horizon context" part of the mandate's suggested MTF structure is
   not fully realized with the platform's current data window. Fixing this
   would require a longer-history data source for the weekly resample
   specifically — flagged as a Day 5+ candidate in
   `DAY4_NEXT_DAY_READINESS_REPORT.md`.
2. **`journal.py`'s `Trade.regime_trend`/`regime_vol` fields still receive
   the OLD single-timeframe `regime.classify()` snapshot**, not this
   engine's output. This was a deliberate, conservative choice — see
   Implementation Report decision log — to avoid changing the shape/meaning
   of an already-shipped, already-tested journal field. The NEW,
   richer multi-timeframe classification is recorded separately in
   `regime_history.jsonl`, fully additive.
3. **`session_label` is not threaded into the Day 4 `classify()` call
   inside `alert_signals.py`/`hourly_briefing.py`** (it defaults to `None`).
   Computing it would require an extra `ict.read(df)` call per scan before
   it's otherwise needed; the Illiquid tag still fires on ATR percentile
   alone without it, just slightly more conservatively. Low-cost future
   improvement, not a correctness bug.
4. **Transition-risk weights and quality-score base values are domain
   heuristics, not fitted.** Stated plainly in §5/§6.1 rather than presented
   as validated. `RESEARCH_REGIME_ENGINE.md` documents the calibration path.

## 9. Failure handling

| Failure | Behavior |
|---|---|
| A single timeframe's resample/classify fails (bad data, insufficient bars, arbitrary exception) | `_classify_tf()` catches it locally, returns that ONE timeframe as `"unknown"`/`sufficient=False`. The other four timeframes are unaffected. |
| The strategic timeframe itself is unusable | `classify()` falls back 1w → 1d automatically; if even 1d is insufficient, primary resolves to `"Unknown"` with `confidence=0`, `compatibility="prohibited"`, `quality_score=0` — a fully-formed, safe result, not an exception. |
| Volatility-trend computation fails | `_vol_trend()` returns `"unknown"`; tags derived from it (Expansion/Contraction/High/Low Volatility) simply don't fire. |
| Range-position computation fails | Caught locally; `range_pos=None`, and the transition-risk factor that depends on it (§5, factor 3) does not contribute. |
| News-guard/session data unavailable | `news_state`/`session_label` default to `None`; the News-Driven/Illiquid tags simply don't fire — never an exception. |
| The entire `classify()` call fails for an unanticipated reason | Top-level `try/except` (belt-and-suspenders beyond the per-piece handling above) returns the same fully-formed "Unknown" shape with the exception text in `error`. |
| `regime_history.record()`'s disk write fails (unwritable path, disk full, etc.) | Caught and swallowed, mirroring `ledger.py`'s "a logging error must never disrupt trading logic" — the function still returns the record that WOULD have been written, so callers relying on the return value (transition detection, etc.) are unaffected within that single call. |
| The whole regime step fails inside `alert_signals.py`'s per-symbol loop | Already covered by that loop's own pre-existing outer `try/except` (unchanged) — a regime-engine failure degrades that one symbol's scan to an `ERROR` log line, exactly like any other per-symbol failure already does, and the loop continues to the next symbol. |

**Retry policy:** none. Every classification is a fast, local (already-
fetched-data) computation with no external call of its own (correlation/news
lookups it reads are themselves already-cached, already-fail-open reads) —
there is nothing transient to retry. **Degraded mode:** `"Unknown"` with
`confidence=0` IS the degraded mode; it is a safe, valid, fully-typed result,
not a special case callers must handle separately. **Safe mode:** since
default `regime_filter_mode="advisory"`, a degraded classification never
blocks anything by construction — it's simply recorded as low-quality
context. **Notification:** every classification (degraded or not) is logged
to the ledger (`{"event": "regime", ...}`) and `regime_history.jsonl`, so a
sustained run of `"Unknown"` results is visible in existing operator
tooling without any new alerting mechanism.

## 10. Testing summary

See `DAY4_VALIDATION_REPORT.md` for full results. New test files:
`tests/test_regime_engine.py` (28 tests: core classification, MTF hierarchy,
explainability, compatibility matrix, quality score, volatility trend, tags,
multi-symbol parametrized, rapid-regime-change edge case, fail-safety on
`None`/malformed/tiny input), `tests/test_regime_history.py` (10 tests:
record/read, transition detection, symbol isolation, rotation, fail-safety
on unwritable path), `tests/test_alert_signals_regime_gate.py` (4 tests:
advisory/block mode behavior).
