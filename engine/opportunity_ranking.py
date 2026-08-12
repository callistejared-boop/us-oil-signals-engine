"""V2.2 Priority 3 — Opportunity Ranking.

Genuine new build per PHASE0_FORENSIC_AUDIT.md Section P: "no code found
anywhere (`opportunity_rank`, `rank_opportunit*` -- zero hits)... every
symbol is evaluated independently today." alert_signals.py's main() loop
(`for sym in markets.symbols(s):`) evaluates and PUBLISHES each symbol's
heads-up independently, in whatever order markets.symbols() returns them,
with no comparison across symbols in the same scan cycle -- if three
symbols all qualify in one cycle, all three publish immediately, in
sequence, with no sense of "which of these three is actually the best
opportunity right now."

This module does not change that publish behavior. Same posture as
decision_gate.py and kill_switch.py: additive-only, standalone, testable.
Call it with a batch of same-cycle candidates that ALREADY passed every
existing gate (regime, confluence, portfolio_risk) and get back an ORDERED
list with a transparent composite score -- not a new gate, not a filter,
not a publish-suppression mechanism. Wiring this into alert_signals.py's
actual publish/suppress behavior is a separate, later, deliberate decision:
it would change what alerts a person actually receives, which needs
explicit sign-off, not something to fold silently into an "additive"
architecture landing.

## Scoring

Reuses confidence_engine.ConfidenceAssessment.overall_confidence as the
primary signal (a 0-100 composite decision-quality estimate) rather than
inventing a new scoring philosophy -- confidence_engine.py already exists
specifically to answer "how good is this opportunity", and rebuilding that
logic here would violate the standing extract/reuse-don't-rewrite
discipline this project runs under.

    composite_score = 0.6 * primary_confidence
                     + 0.25 * confluence_score
                     + 0.15 * regime_quality

  - primary_confidence: assessment.calibrated_probability * 100 when
    assessment.is_calibrated is True (a real, outcome-backed number beats
    the uncalibrated proxy once enough history exists -- see
    confidence_calibration.py), else assessment.overall_confidence.
  - confluence_score: cr.score (0-100, Day 5 MAST composite).
  - regime_quality: mkt_regime["quality_score"] (0-100, Day 4).

Weights are a judgment call, documented rather than hidden: confidence_engine
is already the most complete cross-source composite of the three (Section
"sub-scores" of ConfidenceAssessment shows it already folds in evidence
quality, market quality, and regime confidence internally), so the 0.6
weight on it is not double-counting the other two -- they're included as
secondary, less-aggregated signals for cases where confidence and raw
confluence/regime quality diverge.

Portfolio risk headroom (risk_budget_remaining_pct) is reported per
candidate but deliberately NOT part of the score: every candidate here
already passed portfolio_risk.evaluate()'s pass/fail gate, so headroom
answers "how much room is left", not "how good is this trade" -- conflating
the two would blur the gate/quality separation decision_gate.py already
established (gates decide allow/deny; this module ranks quality among
already-allowed candidates).
"""
from __future__ import annotations

from dataclasses import dataclass

CONFIDENCE_WEIGHT = 0.6
CONFLUENCE_WEIGHT = 0.25
REGIME_QUALITY_WEIGHT = 0.15


@dataclass
class OpportunityCandidate:
    """Input: bundles exactly what alert_signals.py already has in hand at
    heads-up time (right before `_send(...)`) -- nothing new computed."""
    symbol: str
    direction: str
    overall_confidence: int
    confluence_score: int
    regime_quality: int
    calibrated_probability: "float | None" = None
    is_calibrated: bool = False
    risk_budget_remaining_pct: "float | None" = None
    session: "str | None" = None
    grade_letter: "str | None" = None


@dataclass
class RankedOpportunity:
    rank: int
    symbol: str
    direction: str
    composite_score: float
    primary_confidence: float
    confidence_source: str   # "calibrated_probability" | "overall_confidence"
    confluence_score: int
    regime_quality: int
    risk_budget_remaining_pct: "float | None"
    session: "str | None"
    grade_letter: "str | None"


def _primary_confidence(c: OpportunityCandidate):
    if c.is_calibrated and c.calibrated_probability is not None:
        return float(c.calibrated_probability) * 100.0, "calibrated_probability"
    return float(c.overall_confidence or 0), "overall_confidence"


def score_opportunity(c: OpportunityCandidate):
    """Returns (composite_score, primary_confidence, confidence_source).
    Never raises -- every input is clamped to [0,100] defensively, same
    fail-safe posture as grade.py's own score = max(0, min(100, ...))."""
    primary, source = _primary_confidence(c)
    primary = max(0.0, min(100.0, primary))
    confluence = max(0, min(100, int(c.confluence_score or 0)))
    regime_q = max(0, min(100, int(c.regime_quality or 0)))
    composite = (CONFIDENCE_WEIGHT * primary + CONFLUENCE_WEIGHT * confluence
                + REGIME_QUALITY_WEIGHT * regime_q)
    return round(composite, 2), primary, source


def rank_opportunities(candidates) -> list:
    """Ranks a batch of same-cycle candidates, best first. Deterministic
    tie-break: composite_score desc, then confluence_score desc, then
    symbol asc (alphabetical) -- so ties never depend on input order or
    dict/set iteration order. Never raises; [] in, [] out."""
    if not candidates:
        return []
    scored = []
    for c in candidates:
        composite, primary, source = score_opportunity(c)
        scored.append((composite, c.confluence_score, c.symbol, c, primary, source))
    scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
    out = []
    for i, (composite, _cf, _sym, c, primary, source) in enumerate(scored, start=1):
        out.append(RankedOpportunity(
            rank=i, symbol=c.symbol, direction=c.direction, composite_score=composite,
            primary_confidence=round(primary, 2), confidence_source=source,
            confluence_score=c.confluence_score, regime_quality=c.regime_quality,
            risk_budget_remaining_pct=c.risk_budget_remaining_pct, session=c.session,
            grade_letter=c.grade_letter))
    return out


def candidate_from_alert_signals_context(symbol, direction, *, assessment, cr, mkt_regime,
                                         pr_verdict=None, session=None,
                                         grade_letter=None) -> OpportunityCandidate:
    """Convenience adapter: builds an OpportunityCandidate directly from the
    objects alert_signals.py already has in scope at heads-up time
    (ConfidenceAssessment, confluence ConfluenceRead, mkt_regime dict,
    portfolio_risk verdict dict) -- so wiring this in later (if/when that's
    decided) is a one-line call at each heads-up site, not a re-derivation
    of these fields. Never raises: missing/None inputs degrade to safe
    defaults (0 / None), matching every other advisory module's fail-open
    posture in this codebase."""
    overall_confidence = getattr(assessment, "overall_confidence", 0) if assessment else 0
    calibrated_probability = (getattr(assessment, "calibrated_probability", None)
                              if assessment else None)
    is_calibrated = bool(getattr(assessment, "is_calibrated", False)) if assessment else False
    confluence_score = getattr(cr, "score", 0) if cr is not None else 0
    regime_quality = (mkt_regime or {}).get("quality_score", 0)
    risk_budget = None
    if pr_verdict is not None:
        risk_budget = (pr_verdict.get("detail") or {}).get("risk_budget_remaining_pct")
    return OpportunityCandidate(
        symbol=symbol, direction=direction, overall_confidence=overall_confidence,
        confluence_score=confluence_score, regime_quality=regime_quality,
        calibrated_probability=calibrated_probability, is_calibrated=is_calibrated,
        risk_budget_remaining_pct=risk_budget, session=session, grade_letter=grade_letter)
