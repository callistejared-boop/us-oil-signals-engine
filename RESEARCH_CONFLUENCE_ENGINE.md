# RESEARCH REPORT — Adaptive Confluence Engine & Evidence Independence (Day 5)

Companion to `CONFLUENCE_SPECIFICATION.md`. Follows the same honesty
convention established in `RESEARCH_REGIME_ENGINE.md` (Day 4): where data
are insufficient, this report states that explicitly rather than drawing
unsupported conclusions.

## 1. What the real trade data actually contains today

Queried directly from `trades.json` (2026-08-03):

| Metric | Value |
|---|---|
| Total trade rows | 102 |
| Closed trades | 99 |
| Closed trades with any `regime_trend`/`regime_vol` tag | 10 |
| Closed trades with a populated `confluence_score` | **0** |

**Every closed trade's `confluence_score` field is -1 (unset).** This is
the single most important finding in this report: the Phase 3/4/9
contribution-measurement framework (`measure_contribution()`,
`recommend_weight_adjustments()`, `join_trades_with_confluence()`) is
fully built and fully tested against synthetic data, but **there is
currently zero real historical data to run it on.**

This is expected, not a defect. `confluence_history.jsonl` — the log
`log_confluence_explainability()` writes to — did not exist before today.
It only begins accumulating rows from this point forward, on live/replay
signal reads. The 99 already-closed trades in `trades.json` predate this
logging entirely, so no amount of code correctness can retroactively
populate their confluence detail. This mirrors Day 4's finding almost
exactly (10/99 trades had a regime tag, all sharing one label) — the
platform's evidence-logging depth has been improving day over day, and
each new day's engine is validated going forward, not retroactively.

**What this means concretely**: every `measure_contribution()` call and
every `recommend_weight_adjustments()` entry, if run today, returns
`"insufficient_data"` for all 26 sources, correctly, because `min_n=30`
per bucket cannot be met by zero rows. This is the framework working as
designed — refusing to manufacture a conclusion from absent data — not a
gap in the framework itself.

## 2. What can be assessed today: architecture, not outcomes

In the absence of outcome data, this report answers the mandate's research
questions using code-grounded structural analysis (§2 of
`CONFLUENCE_SPECIFICATION.md`), which is a legitimate and complete way to
answer "is this source rephrasing existing evidence" even before a single
trade outcome is available — the duplication finding here is about
information content, not correlation with P&L.

### 2.1 Sources with the strongest evidence of unique contribution

Every source in the following list draws on a genuinely separate real-world
data feed or a detection mechanism that shares no primitive function with
Layer 1's own confidence computation (13 Primary-classified sources, see
`CONFLUENCE_SPECIFICATION.md` §2):

- **External data feeds** (no possible overlap with price-structure logic):
  `cot_feed.py` (CFTC positioning), `spread_feed.py` (cross-instrument
  spread/basis), `risk_sentiment.py` (VIX/SPX), `correlation.py` (DXY),
  `bias_adjust.py` (news).
- **Independent price-behavior mechanisms**: `price_action.py` (candle
  geometry), `mean_reversion.py` (RSI/Bollinger/VWAP overextension —
  notably the ONLY source with zero positive weight, i.e. it can only
  penalize, never confirm, a genuinely distinct role), `volume_profile.py`
  (value-area/POC), `momentum_divergence.py` (RSI divergence),
  `chart_patterns.py`, `seasonality.py`.
- These are the sources this report has the most confidence recommending
  be RETAINED at full weight once real outcome data exists to confirm it —
  not because outcome data says so yet, but because their information
  content is structurally guaranteed not to be an echo of anything else in
  the engine.

### 2.2 Sources showing significant, code-verified overlap

Three findings, in descending order of mechanical certainty (detailed with
full code citations in `CONFLUENCE_SPECIFICATION.md` §2.1-2.2):

1. **Session-timing triplicate** — `structure.in_killzone()`'s boolean is
   scored three times: inside Layer 1's own confidence (+8), directly in
   `confluence.py` (+4), and again inside `session_model.py`'s Judas-Swing
   read (+4/−4). This is the highest-confidence finding in this report —
   it is a literal shared function call, not an inference.
2. **Wyckoff/sweep duplicate** — `wyckoff.py`'s own docstring
   self-describes as "mostly a translation + confirmation layer." Its
   Spring/Upthrust detection calls the identical
   `ict_confluence.liquidity_sweep()` function Layer 1 already scores.
3. **ICC as the weakest sibling of a three-way cluster** —
   `elliott_wave.py`, `chart_patterns.py`, and `icc.py` all read from
   `structure.find_swings()`; `icc.py`'s own docstring positions it as a
   reduced-rigor subset of Elliott Wave logic (roughly wave 1-2-3 only).

**Recommendation for these three, pending real data**: register each as a
sandbox research question (not remove outright — removal without outcome
evidence would itself be an opinion-based decision, which the mandate
explicitly prohibits in the other direction too). Once ≥30 trades exist
with both the source's agree/disagree label AND an outcome, run
`measure_contribution()` on `session_timing` vs. `layer1_ict`-only,
`wyckoff` vs. a Layer-1-sweep-only baseline, and `icc` vs.
`elliott_wave`+`chart_pattern` to test whether the redundant copy adds
measurable expectancy beyond what the primary source already captures.
This is a testable hypothesis, not a foregone conclusion — a duplicate
mechanism CAN still add value if it fires on a slightly different subset
of cases; the current finding is "same information source," not "proven
worthless."

### 2.3 Sources requiring additional validation before any confidence in classification

- **`regime_vol`** — invisible in `agree`/`disagree` (no `.append()` call
  in `confluence.py`), so it cannot even be measured by
  `measure_contribution()` in its current form without a small
  `confluence.py` change to label it. Flagged, not fixed, per "reuse,
  don't restructure" — a candidate for a future minimal `confluence.py`
  patch, tracked as a backlog item below.
- **`bias_adjust` (news)** — its exact point delta isn't persisted on
  `ConfluenceRead` at all; `explain()`/`measure_contribution()` currently
  use a nominal HIGH-strength approximation. Contribution measurement for
  this source specifically will be less precise than for others until
  fixed.
- **Weak-provenance cluster** (`balanced_range.py`, `session_model.py`,
  `icc.py`) — self-disclosed lack of a genuine named source document. This
  doesn't make them wrong, but it does mean their rules were built from
  general domain knowledge rather than a specific verified reference,
  which is a different (lower) evidentiary bar than the platform's other
  modules were held to. Recommend explicit outcome-data validation before
  treating them as equally trustworthy as the Primary-classified sources.

## 3. Feature importance methodology (Phase 9) — designed, not yet run

`measure_contribution(source_key, labeled_trades, min_n=30)` computes, per
source: expectancy when the source agreed, expectancy when it disagreed,
expectancy when it was silent, and a `sufficient` flag requiring ≥30
closed trades in the relevant bucket (matching `RISK_RULES.md`'s existing
30-trade statistical bar and `calibration.py`'s `min_n=8` precedent for a
higher, more conservative threshold given confluence's larger source
count and multiple-comparisons risk).

`recommend_weight_adjustments()` layers a decision rule on top:
`"increase"` if agree-expectancy is meaningfully better than baseline with
sufficient sample, `"decrease_or_retire"` if agree/disagree show no
meaningful separation (the direct operational test for "is this source
rephrasing existing evidence" — a source whose agreement doesn't change
expected outcomes contributes nothing incremental regardless of its
theoretical independence classification), `"retain"` for adequate
separation without a strong enough edge to warrant a weight change, and
`"insufficient_data"` whenever `min_n` isn't met — which is every source,
today.

This is intentionally the SMALLEST possible statistical claim the
framework makes: it does not attempt PCA, mutual information, or any
model-based feature-importance technique that would require far more than
30 samples per source to be reliable. Once real data volume increases,
a natural escalation path exists (see §5) — but starting simple and
provably-not-overfit is the correct choice at the current data volume of
zero.

## 4. Adaptive weighting rollout roadmap

Staged, matching the sandbox pipeline in `CONFLUENCE_SPECIFICATION.md` §7:

1. **Now — data accumulation.** `log_confluence_explainability()` is live
   at both alert stages. Every future signal read now writes a full
   agree/disagree/quality/conflict record to `confluence_history.jsonl`.
   No action needed beyond time passing and trades closing.
2. **Close the confluence_score gap.** `journal.py`'s `Trade` dataclass
   should be extended to persist `confluence_score` and (ideally) a
   pointer/timestamp linking a trade to its originating
   `confluence_history.jsonl` row, the same way Day 4 flagged the
   equivalent regime-linkage gap. Currently `join_trades_with_confluence()`
   works around this via nearest-timestamp join, which is a reasonable
   stopgap but a direct foreign key would be strictly better. Backlog item
   for Day 6+, not blocking Day 5's completion.
3. **n≥30 threshold reached, per source.** Only once real trades accumulate
   with both a source label and a closed outcome does
   `measure_contribution()` produce a non-`"insufficient_data"` result.
   Given the current closed-trade rate (99 trades since inception),
   reaching n=30 for even the highest-frequency sources is a matter of
   weeks to months of live operation, not days.
4. **Sandbox validation for the three flagged overlaps.** Register
   `session_timing`, `wyckoff_sweep_overlap`, and `icc_vs_elliott` as
   sandbox candidates (Phase 8) and progress them through
   research → historical_testing → walk_forward → paper_trading before any
   weight change reaches `confluence.py`.
5. **Human-reviewed promotion.** Even at `production_recommendation`
   stage, `confluence_sandbox.py` has zero code-level authority over
   `confluence.py` (verified by the dedicated import-isolation test). Any
   actual weight change remains a deliberate, reviewed code edit — the
   same bar every existing source was held to when originally added.

## 5. Recommendations for future research

- **Extend `journal.py`'s `Trade` schema** to persist `confluence_score`
  and a direct link to the originating `confluence_history.jsonl` record
  (removes the nearest-timestamp-join approximation entirely).
- **Give `regime_vol` an explicit agree/disagree label** in `confluence.py`
  so it becomes measurable — currently the one source contributing points
  invisibly.
- **Persist `bias_adjust`'s exact computed delta** on `ConfluenceRead`
  rather than reconstructing a nominal approximation.
- **Once n≥30 is reached for several sources**, consider a proper
  feature-importance pass (e.g., permutation importance across the
  reconstructed per-trade point vectors) as a second, more powerful stage
  beyond the current agree/disagree expectancy split — but only after the
  simple version has been running long enough to build confidence in the
  underlying data quality.
- **Revisit the "45% echo" framing itself once data exists**: this
  report's structural analysis found the true picture is more nuanced than
  a flat 45% — roughly half of MAST's sources are genuinely independent,
  and the overlap is concentrated in three specific, named mechanisms
  (session timing, Wyckoff/sweep, ICC/Elliott/chart-pattern cluster)
  rather than diffused across the whole engine. Confirming or revising
  this picture with real outcome data is the highest-value next research
  step for the Confluence Engine specifically.

## 6. Explicit statement on insufficient data

Per the mandate's own instruction: **where data are insufficient, this
report states that explicitly rather than drawing unsupported
conclusions.** No claim in this report about which sources improve or
harm expectancy should be read as outcome-validated — none are, because
zero closed trades carry a `confluence_score`. Every claim in §2 is a
structural/architectural finding (same function, same underlying
computation, self-disclosed provenance gap), independently true regardless
of trade outcomes, and clearly distinguished in this report from the
Phase 3/4/9 outcome-based measurement, which has no real data yet and
whose framework's only currently-correct output is `"insufficient_data"`
for all 26 sources.
