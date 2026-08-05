# RESEARCH REPORT — Confidence Engine Calibration (Day 6)

Companion to `CONFIDENCE_ENGINE_SPECIFICATION.md`. Follows the same honesty
convention `RESEARCH_REGIME_ENGINE.md` (Day 4) and `RESEARCH_CONFLUENCE_ENGINE.md`
(Day 5) established: where data are insufficient, this report states that
explicitly rather than drawing unsupported conclusions.

## 1. What the real data actually contains today

Queried directly from `trades.json` and the filesystem (2026-08-03, same
day the Confidence Engine went live):

| Metric | Value |
|---|---|
| Total trade rows | 102 |
| Closed trades | 99 |
| Closed trades with a populated `confluence_score` | 0 (unchanged from Day 5) |
| Trade rows with a `confluence_ref`/`confidence_ref` | 0 |
| `confidence_history.jsonl` | does not exist yet |

**Every single `ConfidenceAssessment` this engine will ever produce starts
from zero historical calibration data, by construction.** `confidence_history.jsonl`
is created fresh the first time `alert_signals.py` runs after this
deployment; `confidence_calibration.calibrated_probability_for()` will
correctly return `(None, False, 0)` for every bucket until real trades
close and get matched. This is not a defect — it is the calibration
framework refusing to manufacture a probability from data that doesn't
exist yet, exactly as designed.

**Practical consequence**: `is_calibrated` will be `False` on literally
every `ConfidenceAssessment` produced for some time. `probability_label`
will read *"internal decision-quality estimate — NOT a statistically
calibrated probability"* on every Telegram message and dashboard payload
until enough matched, closed, confidence-tagged trades accumulate — see
§3 for how long that is likely to take at current trade frequency.

## 2. What can be assessed today: architecture, not calibration accuracy

In the complete absence of outcome data, this report can speak to the
DESIGN of the calibration framework and the composite formula's internal
consistency, but not to whether `overall_confidence` is actually a good
predictor of anything yet. Two things ARE verifiable today without
outcome data:

### 2.1 The formula does not reproduce the Layer-1 double-counting problem

Day 5's audit found ~45% of MAST's confluence score effectively echoes
Layer 1's own confidence through other layers. The Confidence Engine's
`base_evidence` term uses `cr.score` (which already embeds Layer 1 at 45%
weight) OR `sig.confidence` directly, NEVER both summed — verified by
`test_overall_confidence_never_double_counts_layer1_via_addition`. This is
a structural guarantee, checkable today, independent of any trade outcome.

### 2.2 The sub-scores respond to their intended signals directionally

Unit tests confirm each sub-score/penalty moves in the expected direction
in isolation: higher `confluence_quality` (more independent agreement, not
just more agreement) raises `overall_confidence`; a portfolio
`would_block` verdict, a range-guard penalty, and an active risk lock all
reduce it; stale data and `Illiquid`/`News-Driven` regime tags reduce
`market_quality`; missing evidence sources reduce `evidence_quality`. This
confirms the formula is INTERNALLY CONSISTENT with its documented design —
it does not confirm the formula's weights are the RIGHT weights for
predicting real outcomes, which only calibration against closed trades can
show.

## 3. Timeline expectation for real calibration

At `MIN_N_FOR_CALIBRATION=30` per bucket (five buckets total — see
`CONFIDENCE_ENGINE_SPECIFICATION.md` §8.1) and the platform's observed
historical trade rate (99 closed trades since inception, across four
symbols), reaching a trustworthy sample in even the single most common
bucket is realistically a matter of months of continued live/forward-test
operation, not days — the same conclusion Day 4 and Day 5 both reached
independently for their own calibration questions. This report does not
project a specific date, because trade frequency depends on live market
conditions this platform cannot control or predict.

## 4. Calibration methodology (for when data exists)

`confidence_calibration.py` mirrors the pre-existing, already-in-production
`calibration.py` (which has calibrated Layer 1's raw `sig.confidence`
since before Day 3) rather than inventing a new approach:

- **Reliability table**: for each of five `overall_confidence` buckets
  (`<40`, `40-54`, `55-69`, `70-84`, `85-100`), the empirical win rate
  among real matched trades, compared to the bucket's midpoint as the
  "predicted" rate.
- **Brier score**: `mean((confidence/100 - outcome)^2)` across all matched
  trades — 0 is perfect, 0.25 is a coin flip, matching `calibration.py`'s
  existing interpretation guide.
- **Bias flagging**: `recommend_recalibration()` flags a bucket as
  systematically over- or under-confident only once it has `n >= 30` real
  outcomes AND the realized-vs-predicted gap exceeds 15 percentage points
  — both thresholds chosen to avoid a false "recalibrate" signal from
  noise in a small sample.

## 5. Confidence drift detection

`rolling_evaluation(window_trades=50)` computes the same reliability/Brier
metrics restricted to only the most recent N matched trades (sorted by
trade open time), rather than the ever-growing full history. This lets an
operator ask "has the engine's calibration quality changed recently"
separately from "is the engine calibrated overall" — a full-history metric
can look fine on average while masking a recent regression (e.g. after a
market regime shift, or after an upstream module change). No drift has
been observed or could be observed yet — zero matched trades exist. This
is a designed CAPABILITY, not yet a finding.

## 6. Statistical assumptions and limitations

- **The five confidence buckets are fixed, not adaptively sized.** With
  very little data, a bucket with genuinely 35% real win rate and one with
  55% could both show as "insufficient_data" for a long time if trades
  cluster unevenly across buckets (e.g. if the engine rarely produces
  Low-Confidence reads because upstream gates already filtered most weak
  setups out before reaching this stage). This is a reasonable design
  trade-off (fixed buckets are simpler to reason about and match the
  platform's existing tier language) but worth flagging as a real
  limitation once real data starts arriving unevenly.
- **The Brier score treats every trade as an independent observation.**
  Trades from the same session, symbol, or correlated market conditions
  are not independent in reality; this is a standard simplification shared
  with `calibration.py`'s existing methodology, not a new assumption
  introduced by this report.
- **`overall_confidence`'s composite formula (Sec.3.1 of the spec) has
  five weighted terms; with only ~100 total historical trades platform-wide
  (across ALL prior days, not just Day 6), there will not be enough data
  for a long time to independently validate all five weights (quality_modifier,
  regime_modifier, guard_penalty, portfolio_penalty, risk_lock_penalty)
  separately — only the AGGREGATE score's calibration can realistically be
  checked with the sample sizes this platform will see in the near term.**
  A proper decomposition (e.g., "is the regime_modifier term specifically
  well-calibrated") would need substantially more data than a bucket-level
  Brier score requires, and is out of scope until trade volume grows well
  beyond current levels.

## 7. Future research recommendations

- Once `confidence_history.jsonl` and `trades.json`'s `confidence_ref`
  linkage accumulate real matched trades, run `confidence_calibration.report()`
  and compare it against `calibration.py`'s existing report for the SAME
  closed trades — do the two calibration exercises (raw Layer 1 confidence
  vs. the Day 6 composite) diverge, and if so, does the composite's
  calibration improve on the raw one? This is the single most direct test
  of whether the Confidence Engine adds value over what already existed.
- Extend `regime_history.py` with a `ref` parameter (mirroring
  `confluence_history.py`'s Day 6 addition) so regime data can also be
  directly joined rather than timestamp-approximated — see
  `DAY6_NEXT_DAY_READINESS_REPORT.md` backlog.
- Once decomposition-level data volume exists (see §6), consider whether
  `quality_modifier`/`regime_modifier`'s specific curve shapes (currently
  linear in `confluence_quality`/`regime_quality_score`) are the right
  functional form, or whether a fitted (e.g. logistic) relationship
  between confluence/regime quality and realized win rate would calibrate
  better — this cannot be answered without real data and should not be
  guessed at now.
- Consider whether `evidence_quality` (coverage) and `confluence_quality`
  (independence-weighted agreement) should be combined into a single term
  in the composite formula, or kept separate as they are now — both are
  currently informational-only in the headline score's SUB-fields but do
  not independently enter the `overall_confidence` formula in Sec.3.1
  beyond confluence_quality's role in quality_modifier. This is a design
  question for a future day once real calibration data can show whether
  coverage independently predicts outcomes beyond what confluence_quality
  already captures.

## 8. Explicit statement on insufficient data

Per the mandate's own instruction: **where data are insufficient, this
report states that explicitly rather than drawing unsupported
conclusions.** Nothing in this report should be read as evidence that
`overall_confidence` is, or is not, a good predictor of trade outcomes.
The calibration framework exists, is fully tested against synthetic data,
and is wired into the live pipeline starting today — its only honest
output right now is "not enough data yet," on every bucket, for every
symbol. That will remain true until real closed trades accumulate with a
`confidence_ref` linkage, which starts happening from this deployment
forward.
