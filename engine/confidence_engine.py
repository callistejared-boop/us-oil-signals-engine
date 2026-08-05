"""Day 6 — Confidence Engine (calibrated decision quality).

Converts the platform's already-validated evidence into a single,
structured, explainable confidence assessment. This module does NOT
originate trades, does NOT re-score ICT/SMC structure, does NOT
re-implement the Market Regime Engine (Day 4) or the Adaptive Confluence
Engine (Day 5), and does NOT duplicate the Portfolio Risk Engine (Day 3).
It is a pure downstream synthesis layer: every function here takes
already-computed upstream objects as parameters and never re-fetches or
re-derives what those engines already produced.

IMPORTANT — what "confidence" means here: `overall_confidence` is an
internal decision-quality estimate assembled from disclosed, non-statistically
-fitted weights (documented inline below), exactly like Day 4's transition-risk
weights and Day 5's quality-score weights before them. It is NOT a
probability of winning unless `confidence_calibration.py` has enough real
outcome data to say otherwise (see that module's `min_n` gate). Every
ConfidenceAssessment carries an explicit `probability_label` stating which
case applies, so nothing downstream can mistake a decision-quality score for
a calibrated probability.

Inputs consumed (produced elsewhere, never recomputed here):
  - sig                 : engine.signals.Signal (Layer 1 ICT/SMC origination)
  - mkt_regime           : dict from engine.regime_engine.classify() (Day 4)
  - cr                   : engine.confluence.ConfluenceRead or None (Day 5's
                            engine.confluence.analyze() output)
  - portfolio_verdict     : dict from engine.portfolio_risk.evaluate() (Day 3)
  - guard                : dict from engine.range_guard.evaluate()
  - news_state            : dict from engine.news_guard.evaluate()
  - session               : str, e.g. r["session"] from engine.ict.read()
  - risk_locked           : bool, from engine.risk_guard.evaluate()['locked']
  - data_stale            : bool, optional (dashboard/resilient-fetch contexts)

Everything above already exists in the live pipeline before this module is
called (alert_signals.py computes all of it per scan); this module adds zero
new external fetches.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import confluence_analysis as cfa  # noqa: E402

VERSION = "1.0.0"
SCHEMA_VERSION = 1

# (floor_field_name, tier_label) — checked high to low. Floors are read from
# Settings at call time (see config.py's Day 6 block) rather than
# hard-coded, so an operator can retune bands without a code change; these
# are the documented engineering defaults used when no override is supplied.
DEFAULT_TIERS = [
    ("confidence_tier_exceptional", 85, "Exceptional Confidence"),
    ("confidence_tier_high", 70, "High Confidence"),
    ("confidence_tier_moderate", 55, "Moderate Confidence"),
    ("confidence_tier_low", 40, "Low Confidence"),
]
RESEARCH_ONLY = "Research Only"

TOTAL_CONFLUENCE_SOURCES = 26  # excludes the layer1_ict anchor — see confluence_analysis.SOURCE_REGISTRY


@dataclass
class ConfidenceAssessment:
    """Standardized confidence object. Every field is documented below —
    see CONFIDENCE_ENGINE_SPECIFICATION.md Sec.2 for the authoritative field
    reference (this docstring is the code-level summary)."""

    # --- identity -----------------------------------------------------------
    symbol: str
    direction: str
    timestamp: str                     # ISO8601 UTC, when this assessment was made
    version: dict                      # {"confidence_engine": VERSION, "schema": SCHEMA_VERSION}

    # --- headline -------------------------------------------------------------
    overall_confidence: int            # 0-100 composite decision-quality estimate
    tier: str                          # one of the five decision tiers (see DEFAULT_TIERS)
    probability_label: str             # explicit statement of what overall_confidence is/isn't
    calibrated_probability: float | None   # None until confidence_calibration.py has enough data
    is_calibrated: bool                # True only when calibrated_probability came from real outcomes

    # --- sub-scores (each independently meaningful, not just headline inputs) -
    evidence_quality: int              # 0-100: coverage/completeness of available evidence sources
    evidence_diversity: int            # 0-100: category diversity of agreeing confluence sources (Day 5, scaled)
    market_quality: int                # 0-100: session timing + data freshness + regime stability
    regime_confidence: int             # 0-100: Day 4 Market Regime Engine's own confidence in its read
    confluence_quality: int            # 0-100: Day 5 independence-weighted confluence quality score

    # --- upstream status passthroughs (summaries, not new judgments) ----------
    portfolio_status: dict             # {allow, would_block, category, reason, heat}
    risk_status: dict                  # {guard_action, guard_penalty, risk_locked, macro_headwind}

    # --- explainability ---------------------------------------------------
    uncertainty_indicators: list = field(default_factory=list)
    supporting_rationale: list = field(default_factory=list)
    conflicting_rationale: list = field(default_factory=list)
    highest_impact_evidence: str | None = None
    lowest_impact_evidence: str | None = None
    assumptions: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    def summary_line(self) -> str:
        cal = (f"calibrated ~{self.calibrated_probability*100:.0f}%"
               if self.is_calibrated and self.calibrated_probability is not None
               else "uncalibrated estimate")
        return (f"{self.symbol} {self.direction} — {self.tier} "
                f"({self.overall_confidence}/100, {cal})")


def _tiers_from_settings(settings=None) -> list:
    """Resolve tier boundaries from Settings, falling back to DEFAULT_TIERS'
    literal floors if settings is None or a field is missing. Never raises."""
    if settings is None:
        return [(label, floor) for _, floor, label in DEFAULT_TIERS]
    out = []
    for attr, default_floor, label in DEFAULT_TIERS:
        try:
            floor = int(getattr(settings, attr, default_floor) or default_floor)
        except Exception:  # noqa: BLE001
            floor = default_floor
        out.append((label, floor))
    return out


def classify_tier(overall_confidence: int, settings=None) -> str:
    """Map a 0-100 score onto a decision tier. Never presents false
    numerical precision — callers should show the tier label, not just the
    raw number, in any user-facing context (mandate: "avoid false numerical
    precision")."""
    tiers = _tiers_from_settings(settings)
    score = max(0, min(100, int(overall_confidence or 0)))
    for label, floor in tiers:
        if score >= floor:
            return label
    return RESEARCH_ONLY


def _evidence_quality(cr, mkt_regime: dict, news_state: dict) -> int:
    """Coverage/completeness of the evidence AVAILABLE to this assessment —
    distinct from confluence_quality (Day 5's independence-WEIGHTED
    agreement score). A read where every sensor reported something (even a
    disagreement) has higher evidence_quality than one where several
    upstream reads errored or returned empty, regardless of what the
    evidence said. Never raises; degrades to 0 on total failure."""
    try:
        components = []

        # 1. Confluence source coverage: what fraction of the 26 registered
        #    sources actually produced a non-neutral read this pass.
        if cr is not None:
            touched = len(getattr(cr, "agree", []) or []) + len(getattr(cr, "disagree", []) or [])
            components.append(min(1.0, touched / TOTAL_CONFLUENCE_SOURCES))
        else:
            components.append(0.0)

        # 2. Regime per-timeframe data sufficiency (Day 4's own `sufficient`
        #    flag per timeframe — reused directly, not recomputed).
        per_tf = (mkt_regime or {}).get("per_tf", {}) or {}
        if per_tf:
            suff = sum(1 for v in per_tf.values() if v.get("sufficient"))
            components.append(suff / len(per_tf))
        else:
            components.append(0.0)

        # 3. External service health: did regime/news report a degraded
        #    state? (mkt_regime carries an "error" key only on its
        #    fail-safe path; news_state carries a non-empty "note" only when
        #    the calendar feed itself is unavailable.)
        healthy = 1.0
        if (mkt_regime or {}).get("error"):
            healthy -= 0.5
        if (news_state or {}).get("note"):
            healthy -= 0.25
        if cr is None:
            healthy -= 0.25
        components.append(max(0.0, healthy))

        return round(100 * (sum(components) / len(components)))
    except Exception:  # noqa: BLE001
        return 0


def _market_quality(mkt_regime: dict, session: str | None, data_stale: bool) -> int:
    """Is the CURRENT market environment good-quality for acting on a
    signal — independent of whether the signal itself is good. Session
    timing, data freshness, and regime stability (not direction) are the
    three inputs; none of this duplicates confluence.py's own session
    kill-zone SCORE (+4, see Day 5 observability fix) — this measures
    environment quality for the confidence write-up, not a confluence point."""
    try:
        components = []

        # Session alignment: kill-zone windows have historically deeper
        # liquidity/tighter spreads on this platform's instruments.
        session = session or ""
        components.append(1.0 if "KZ" in session else 0.6 if session == "Asian" else 0.4)

        # Data freshness: a stale (cached) feed is a real quality reduction,
        # regardless of what the cached data says.
        components.append(0.4 if data_stale else 1.0)

        # Regime stability proxy: Day 4's own tags flag genuinely degraded
        # conditions (Illiquid, News-Driven) — reused directly, not
        # reclassified here.
        tags = set((mkt_regime or {}).get("tags", []) or [])
        if "Illiquid" in tags or "News-Driven" in tags:
            components.append(0.3)
        elif "High Volatility" in tags:
            components.append(0.7)
        else:
            components.append(1.0)

        return round(100 * (sum(components) / len(components)))
    except Exception:  # noqa: BLE001
        return 50


def _uncertainty_indicators(cr, mkt_regime: dict, news_state: dict,
                            portfolio_verdict: dict, evidence_quality: int,
                            calibration_sufficient: bool) -> list:
    """Explicit, named uncertainty flags — never silently folded into the
    score. Per the mandate: "Uncertainty should reduce trust in the
    assessment without necessarily rejecting the trade." Nothing here
    blocks anything; it is read-only annotation."""
    out = []
    try:
        if not calibration_sufficient:
            out.append("insufficient historical data for a calibrated probability")
        if cr is not None:
            conflicts = cfa.conflict_resolution(cr)
            if conflicts:
                out.append(f"conflicting evidence ({len(conflicts)} pattern(s) detected)")
        else:
            out.append("confluence engine unavailable for this read")
        if evidence_quality < 60:
            out.append("incomplete market data (evidence coverage below 60%)")
        if (mkt_regime or {}).get("error"):
            out.append("degraded regime-engine service (failed safe to Unknown)")
        if (news_state or {}).get("note"):
            out.append(f"degraded news/calendar service ({news_state['note']})")
        if cr is not None:
            macro_layer = (getattr(cr, "layers", {}) or {}).get("macro", {}) or {}
            if macro_layer.get("aligned") is None:
                out.append("missing macro input (USD correlation unavailable)")
        detail = (portfolio_verdict or {}).get("detail", {}) or {}
        if detail.get("correlation"):
            out.append(f"unstable/elevated correlation vs open position "
                       f"({detail['correlation'].get('against', '?')})")
        tr_label = (mkt_regime or {}).get("transition_label", "")
        if tr_label in ("elevated", "high"):
            out.append(f"regime in transition (risk: {tr_label})")
    except Exception:  # noqa: BLE001
        out.append("uncertainty assessment itself encountered an error — treat this read cautiously")
    return out


def _rationale(cr, mkt_regime: dict, portfolio_verdict: dict) -> tuple:
    """Builds (supporting, conflicting) rationale lists, plus the single
    highest/lowest-impact evidence label when available (reuses Day 5's
    explain(), does not recompute impact ranking)."""
    supporting, conflicting = [], []
    highest, lowest = None, None
    try:
        if cr is not None:
            ex = cfa.explain(cr)
            if ex.get("highest_impact"):
                highest = ex["highest_impact"].get("label")
                supporting.append(f"strongest confirming evidence: {highest}")
            if ex.get("lowest_impact") and ex["lowest_impact"].get("direction") == "disagree":
                lowest = ex["lowest_impact"].get("label")
            supporting.extend(f"confluence: {a}" for a in (cr.agree or [])[:5])
            conflicting.extend(f"confluence: {d}" for d in (cr.disagree or [])[:5])
        evidence = (mkt_regime or {}).get("evidence", []) or []
        supporting.extend(f"regime: {e}" for e in evidence[:3])
        conflicts = (mkt_regime or {}).get("conflicting_evidence", []) or []
        conflicting.extend(f"regime: {c}" for c in conflicts[:3])
        if portfolio_verdict is not None:
            if portfolio_verdict.get("allow") and not portfolio_verdict.get("would_block"):
                supporting.append("portfolio risk checks clear")
            elif portfolio_verdict.get("would_block"):
                conflicting.append(f"portfolio risk: {portfolio_verdict.get('reason', '')}")
    except Exception:  # noqa: BLE001
        pass
    return supporting, conflicting, highest, lowest


def assess(symbol: str, direction: str, sig=None, mkt_regime: dict | None = None,
          cr=None, portfolio_verdict: dict | None = None, guard: dict | None = None,
          news_state: dict | None = None, session: str | None = None,
          risk_locked: bool = False, data_stale: bool = False,
          settings=None, memory_context: dict | None = None) -> ConfidenceAssessment:
    """Main entry point. Assembles a ConfidenceAssessment from already-
    computed upstream objects. Every parameter is optional so this can be
    called with a partial context (e.g. no confluence read yet) and still
    degrade gracefully rather than raising — matching this platform's
    fail-safe convention throughout Day 3-5. Never raises.

    `memory_context` (Day 7, optional): a `market_memory.historical_context()`
    result. Per the Day 7 mandate ("Before a trade reaches the Confidence
    Engine, the platform should determine... historical context"), this is
    consumed here ONLY as an additional rationale/assumption line —
    `overall_confidence`'s formula (see below) does not read this
    parameter at all, so passing it can change what a `ConfidenceAssessment`
    SAYS but never what it SCORES. See
    `test_memory_context_never_changes_overall_confidence`."""
    try:
        mkt_regime = mkt_regime or {}
        guard = guard or {}
        news_state = news_state or {}
        portfolio_verdict = portfolio_verdict or {}

        base_evidence = float(cr.score) if cr is not None else float(getattr(sig, "confidence", 0) or 0)
        confluence_quality = cfa.quality_score(cr)["score"] if cr is not None else 0
        evidence_diversity = round(100 * cfa.quality_score(cr)["diversity"]) if cr is not None else 0
        regime_confidence = int(mkt_regime.get("confidence", 0) or 0)
        regime_quality = int(mkt_regime.get("quality_score", 0) or 0)
        evidence_quality = _evidence_quality(cr, mkt_regime, news_state)
        market_quality = _market_quality(mkt_regime, session, data_stale)

        # --- overall_confidence composition (disclosed, not statistically
        # fitted — see module docstring). base_evidence already embeds Layer
        # 1's own confidence (either directly, or at 45% weight inside
        # cr.score), so it is NOT added again here — that would reproduce
        # exactly the double-counting Day 5's audit flagged in MAST itself.
        # quality_modifier discounts base_evidence when the confirming
        # evidence is mostly Duplicate/Derived/Legacy (low independence);
        # regime_modifier is a SMALL modifier (regime remains advisory-only
        # per Day 4 — no forward-test evidence yet that it should swing
        # confidence hard); guard/portfolio penalties are subtracted as
        # absolute points, reusing values those engines already computed.
        quality_modifier = 0.70 + 0.30 * (confluence_quality / 100.0)
        regime_modifier = 0.85 + 0.15 * (regime_quality / 100.0)
        guard_penalty = abs(int(guard.get("penalty", 0) or 0))
        portfolio_penalty = 10 if portfolio_verdict.get("would_block") else 0
        risk_lock_penalty = 15 if risk_locked else 0

        overall = base_evidence * quality_modifier * regime_modifier
        overall -= (guard_penalty + portfolio_penalty + risk_lock_penalty)
        overall_confidence = max(0, min(100, round(overall)))

        tier = classify_tier(overall_confidence, settings=settings)

        # --- calibration (see confidence_calibration.py) ----------------------
        try:
            from engine import confidence_calibration as cc
            calibrated_prob, is_cal, n = cc.calibrated_probability_for(overall_confidence)
        except Exception:  # noqa: BLE001
            calibrated_prob, is_cal, n = None, False, 0

        if is_cal and calibrated_prob is not None:
            probability_label = (f"calibrated against {n} historical trades in this "
                                 f"confidence bucket")
        else:
            probability_label = ("internal decision-quality estimate — NOT a statistically "
                                 "calibrated probability (insufficient historical data)")

        supporting, conflicting, highest, lowest = _rationale(cr, mkt_regime, portfolio_verdict)
        uncertainty = _uncertainty_indicators(cr, mkt_regime, news_state, portfolio_verdict,
                                              evidence_quality, is_cal)

        assumptions = [
            "overall_confidence uses disclosed, engineering-judgment weights, not "
            "weights fitted to historical outcomes (see CONFIDENCE_ENGINE_SPECIFICATION.md)",
            "base evidence already embeds Layer 1 ICT/SMC confidence — see "
            "RESEARCH_CONFLUENCE_ENGINE.md for the known ~45% overlap this implies",
        ]
        if not is_cal:
            assumptions.append("calibrated_probability is None: fewer than the required "
                               "minimum historical trades exist in this confidence bucket")

        # --- Day 7: Market Memory context — informational only, never
        # scored. See this function's docstring and
        # MARKET_MEMORY_SPECIFICATION.md Sec.7 "Integration."
        if memory_context is not None:
            try:
                if memory_context.get("sufficient_sample"):
                    agg = memory_context.get("aggregate") or {}
                    supporting.append(
                        f"market memory: {memory_context.get('comparable_count')} comparable "
                        f"historical situation(s), {agg.get('win_rate', 0)*100:.0f}% win rate "
                        f"(not used in overall_confidence's score)")
                else:
                    assumptions.append(
                        f"market memory found only {memory_context.get('comparable_count', 0)} "
                        "comparable historical situation(s) — too few for historical context "
                        "to inform this assessment")
            except Exception:  # noqa: BLE001
                pass

        portfolio_status = {
            "allow": portfolio_verdict.get("allow"),
            "would_block": portfolio_verdict.get("would_block"),
            "category": portfolio_verdict.get("category"),
            "reason": portfolio_verdict.get("reason"),
            "heat": (portfolio_verdict.get("detail", {}) or {}).get("portfolio_heat"),
        }
        risk_status = {
            "guard_action": guard.get("action"),
            "guard_penalty": guard.get("penalty", 0),
            "risk_locked": bool(risk_locked),
            "macro_headwind": bool(guard.get("macro_headwind")),
        }

        return ConfidenceAssessment(
            symbol=symbol, direction=direction,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            version={"confidence_engine": VERSION, "schema": SCHEMA_VERSION},
            overall_confidence=overall_confidence, tier=tier,
            probability_label=probability_label,
            calibrated_probability=calibrated_prob, is_calibrated=is_cal,
            evidence_quality=evidence_quality, evidence_diversity=evidence_diversity,
            market_quality=market_quality, regime_confidence=regime_confidence,
            confluence_quality=confluence_quality,
            portfolio_status=portfolio_status, risk_status=risk_status,
            uncertainty_indicators=uncertainty, supporting_rationale=supporting,
            conflicting_rationale=conflicting, highest_impact_evidence=highest,
            lowest_impact_evidence=lowest, assumptions=assumptions,
        )
    except Exception as exc:  # noqa: BLE001
        # Total failure path — still returns a valid, clearly-labeled object
        # rather than raising or returning None, so a caller that always
        # expects a ConfidenceAssessment never crashes.
        return ConfidenceAssessment(
            symbol=symbol, direction=direction,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            version={"confidence_engine": VERSION, "schema": SCHEMA_VERSION},
            overall_confidence=0, tier=RESEARCH_ONLY,
            probability_label="assessment failed — treat as no-confidence pending investigation",
            calibrated_probability=None, is_calibrated=False,
            evidence_quality=0, evidence_diversity=0, market_quality=0,
            regime_confidence=0, confluence_quality=0,
            portfolio_status={}, risk_status={},
            uncertainty_indicators=[f"confidence engine error: {exc}"],
            supporting_rationale=[], conflicting_rationale=[],
            assumptions=["this assessment failed internally — see uncertainty_indicators"],
        )
