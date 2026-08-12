# Opportunity Ranking — Specification

**Module:** `engine/opportunity_ranking.py`
**V2.2 Priority 3, Item 1** (genuine new build per `PHASE0_FORENSIC_AUDIT.md` Section P)

## 1. The gap this closes

`PHASE0_FORENSIC_AUDIT.md`: *"Opportunity Ranking across symbols — no
code found anywhere (`opportunity_rank`, `rank_opportunit*` — zero hits).
Genuine gap; every symbol is evaluated independently today."*

Confirmed directly in `alert_signals.py::main()`: `for sym in
markets.symbols(s):` evaluates each symbol through the full gate sequence
(regime → origination → confluence → portfolio risk) and publishes its
heads-up immediately, in loop order, the moment it clears every gate. If
three symbols all clear in the same scan cycle, all three publish in
sequence with no sense of which is actually the strongest opportunity
right now.

## 2. What this is

A standalone, pure-function ranking module: hand it a batch of same-cycle
candidates that already passed every existing gate, get back an ordered
list with a transparent composite score.

```python
candidates = [opportunity_ranking.candidate_from_alert_signals_context(...), ...]
ranked = opportunity_ranking.rank_opportunities(candidates)
# ranked[0] is the single best opportunity in this scan cycle
```

## 3. What this is NOT

Not a new gate. Not a filter. Not a publish-suppression mechanism. Every
candidate handed to this module has already been judged tradeable by the
existing gates — this module only orders already-approved candidates by
quality, it does not decide approve/reject.

Not wired into `alert_signals.py`'s actual publish behavior in this
landing — same posture as `decision_gate.py` and `kill_switch.py`.
Deciding whether/how ranking should affect what a person actually
receives (e.g. "only alert on the top-ranked symbol per cycle", "tag
lower-ranked alerts as secondary") is a real behavioral change to what
gets sent, and needs explicit sign-off rather than being folded silently
into an additive architecture landing.

## 4. Scoring

```
composite_score = 0.6 * primary_confidence + 0.25 * confluence_score + 0.15 * regime_quality
```

| Component | Source | Range |
|---|---|---|
| `primary_confidence` | `assessment.calibrated_probability * 100` if `assessment.is_calibrated`, else `assessment.overall_confidence` | 0–100 |
| `confluence_score` | `cr.score` (Day 5 MAST composite) | 0–100 |
| `regime_quality` | `mkt_regime["quality_score"]` (Day 4) | 0–100 |

`confidence_engine.py`'s `overall_confidence` was chosen as the primary,
highest-weighted signal rather than inventing new scoring logic: it
already exists specifically to answer "how good is this opportunity", and
its own sub-scores (`evidence_quality`, `evidence_diversity`,
`market_quality`, `regime_confidence`, `confluence_quality`) already fold
in confluence and regime internally. The 0.6 weight is not double-counting
`confluence_score`/`regime_quality` — those two are included at lower
weight specifically as secondary, less-aggregated signals for cases where
confidence diverges from raw confluence or regime quality.

`calibrated_probability` is preferred over `overall_confidence` whenever
`is_calibrated` is `True`: a real, outcome-backed number (from
`confidence_calibration.py`) is strictly better evidence than the
uncalibrated proxy once enough trade history exists to compute one.

Portfolio risk headroom (`risk_budget_remaining_pct`) is carried through
on every `RankedOpportunity` for visibility but deliberately excluded from
the score: every candidate here already passed
`portfolio_risk.evaluate()`'s pass/fail gate, so headroom answers "how
much room is left", not "how good is this trade" — conflating the two
would blur the gate/quality separation `decision_gate.py` already
established (gates decide allow/deny; this module ranks quality among
already-allowed candidates).

## 5. Determinism

Tie-break order: `composite_score` descending, then `confluence_score`
descending (the second-highest-weighted signal), then `symbol` ascending
(alphabetical) as a final deterministic fallback. Ranking never depends on
input list order or dict/set iteration order — verified by a dedicated
test (`test_rank_opportunities_deterministic_regardless_of_input_order`).

## 6. Failure behavior

Every field is defensively clamped to `[0, 100]` (mirroring `grade.py`'s
own `score = max(0, min(100, ...))` pattern) and `None`/missing inputs
degrade to `0`/`None` rather than raising —
`candidate_from_alert_signals_context()` accepts `assessment=None`,
`cr=None`, `mkt_regime=None`, `pr_verdict=None` and still returns a valid
(zero-scored) candidate, matching the fail-open posture used throughout
this codebase's advisory modules.

## 7. Adapter function

`candidate_from_alert_signals_context(symbol, direction, *, assessment,
cr, mkt_regime, pr_verdict=None, session=None, grade_letter=None)` builds
an `OpportunityCandidate` directly from the objects `alert_signals.py`
already holds in scope at heads-up time (`ConfidenceAssessment`,
confluence `ConfluenceRead`, `mkt_regime` dict, `portfolio_risk` verdict
dict) — so that wiring this module in later, if/when that's decided, is a
one-line call at each heads-up site rather than a re-derivation of these
fields.

## 8. Test coverage

`tests/test_opportunity_ranking.py`, 16 tests: `score_opportunity` (5 —
uncalibrated default, calibrated preference, `is_calibrated=False` guard
against stale `calibrated_probability`, clamping, `None`-safety),
`rank_opportunities` (8 — empty input, ordering, two tie-break scenarios,
order-independence, candidate-count preservation, field passthrough,
single-candidate case), and `candidate_from_alert_signals_context` (3 —
full inputs, missing-optional-inputs, end-to-end adapter-to-ranking with
no mocking).
