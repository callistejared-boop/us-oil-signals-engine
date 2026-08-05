"""Day 8 — Explainability Engine & Decision Audit System.

This module does NOT generate trades and cannot influence whether one
publishes. It records, reconstructs, and explains every decision the
platform already made — the literal framing of the Day 8 mandate: "This
system does not generate trades. It records, reconstructs, and explains
every decision the platform makes."

Everything here is a pure downstream synthesis layer, same posture as
`confidence_engine.py` (Day 6) and `market_memory.py` (Day 7): every
function takes already-computed upstream objects as parameters and never
re-fetches, re-derives, or re-scores anything. See
EXPLAINABILITY_SPECIFICATION.md for the full design narrative.

WHAT'S NEW vs. what's REUSED (storage-design discipline, per the mandate's
"avoid duplicated storage" principle):
  - REUSED, verbatim: regime/confluence/confidence summaries and ref
    pointers (Day 4-7's own history logs), the ConfidenceAssessment's
    already-normalized `portfolio_status`/`risk_status`/rationale/
    uncertainty/assumptions fields (Day 6), the market-memory
    `historical_context()` summary (Day 7), the unified trade ID
    (`journal.make_ref()`), and `engine.portfolio_risk`'s existing ten-item
    rejection-category vocabulary (Day 3).
  - NEW: `DecisionSnapshot` — a small, denormalized, IMMUTABLE record
    capturing what none of the above stores at all: the platform/config/
    version state active AT THE MOMENT of the decision, the final action
    (approved/rejected/heads-up), and — for the first time in this
    codebase — a persisted, structured record of REJECTED opportunities
    (nothing before Day 8 kept any durable record of a held/rejected
    signal beyond a single-line ledger event).
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import platform_version as pv          # noqa: E402
from engine import portfolio_risk as pr            # noqa: E402
from engine import regime_history as rh            # noqa: E402
from engine import confluence_history as cfh       # noqa: E402
from engine import confidence_history as cfdh      # noqa: E402
from engine import decision_audit_history as dah   # noqa: E402
from engine import journal                          # noqa: E402
from engine import store                            # noqa: E402

VERSION = "1.0.0"
SCHEMA_VERSION = 1

# --- Decision timeline (per the Day 8 mandate's own diagram) ---------------
# Every DecisionSnapshot records which of these stages it reached
# (`stage_reached`) — not every decision passes through every stage (a
# rejection stops the timeline early; a heads-up stops before Execution).
DECISION_STAGES = [
    "market_data_received",
    "market_regime_assessment",
    "ict_smc_origination",
    "confluence_assessment",
    "portfolio_risk",
    "confidence_assessment",
    "market_memory",
    "approval_or_rejection",
    "publication",
    "execution",
    "trade_outcome",
    "post_trade_review",
    "calibration",
]

# --- Rejection vocabulary ---------------------------------------------------
# Reused directly from engine.portfolio_risk (Day 3's canonical ten-category
# list), not re-declared — plus two categories that vocabulary explicitly
# left for other modules to use (Sec. header there says "listed for
# completeness"). WEAK_EVIDENCE covers a MAST confluence hold; Market Memory
# is advisory-only (Day 7) and never itself blocks a trade, so
# INSUFFICIENT_HISTORICAL_CONTEXT is listed per the mandate's own example
# list but is NOT, today, ever the recorded CAUSE of a rejection — disclosed
# explicitly here rather than silently omitted or falsely implemented.
WEAK_EVIDENCE = "weak_evidence"
INSUFFICIENT_HISTORICAL_CONTEXT = "insufficient_historical_context"   # never the cause today — see above
RISK_LOCK = "risk_lock"                                               # risk_guard.py daily-loss lock
NEWS_BLACKOUT = "news_blackout"

REJECTION_CATEGORIES = {
    pr.RISK_BUDGET_EXCEEDED, pr.CORRELATION_TOO_HIGH, pr.PORTFOLIO_EXPOSURE_EXCEEDED,
    pr.MARKET_REGIME_UNSUITABLE, pr.CONFIDENCE_BELOW_THRESHOLD, pr.SESSION_RESTRICTION,
    pr.DRAWDOWN_PROTECTION, pr.LIQUIDITY_CONDITIONS, pr.TRADE_FREQUENCY_CONTROL,
    pr.DUPLICATE_OPPORTUNITY, WEAK_EVIDENCE, INSUFFICIENT_HISTORICAL_CONTEXT,
    RISK_LOCK, NEWS_BLACKOUT,
}

# --- Configuration traceability ---------------------------------------------
# The decision-relevant subset of Settings — thresholds, modes, and feature
# flags that could plausibly change what decision the platform reaches.
# Deliberately excludes credentials/connection settings (telegram tokens,
# API keys, Supabase secrets) — those affect DELIVERY, not the decision
# itself, and have no place in a record meant to be reviewed/shared.
CONFIG_FIELDS = [
    "paper_mode", "max_daily_loss_r", "max_open_per_symbol", "confluence_min_score",
    "portfolio_equity", "portfolio_risk_mode", "portfolio_max_risk_pct",
    "portfolio_day_stop_r", "portfolio_max_drawdown_r", "portfolio_max_directional",
    "correlation_high_threshold", "correlation_window_days",
    "regime_filter_mode", "regime_min_quality_for_block", "regime_strategy",
    "confidence_tier_low", "confidence_tier_moderate", "confidence_tier_high",
    "confidence_tier_exceptional",
]


def config_snapshot(settings=None) -> dict:
    """The decision-relevant configuration state, frozen at the moment of
    the decision. Never raises; missing fields are reported as `None`
    rather than silently skipped, so a reviewer can see exactly what wasn't
    available rather than inferring an empty dict means "nothing to show.\""""
    out = {}
    for f in CONFIG_FIELDS:
        try:
            out[f] = getattr(settings, f, None) if settings is not None else None
        except Exception:  # noqa: BLE001
            out[f] = None
    return out


# --- The DecisionSnapshot object --------------------------------------------

@dataclass
class DecisionSnapshot:
    """Standardized, immutable decision record — one per opportunity the
    platform evaluated, whether it was ultimately approved, published as a
    heads-up, or rejected. See EXPLAINABILITY_SPECIFICATION.md Sec.2 for the
    authoritative field reference (this docstring is the code-level
    summary)."""

    # --- identity ------------------------------------------------------------
    decision_id: str            # unique per decision — f"{symbol}-{decision_ts}" (journal.make_ref format)
    trade_ref: str              # == Trade.id/regime_ref/confluence_ref/confidence_ref IFF this decision
                                 # became an actual Stage-2 fill; "" otherwise (heads-up or rejection)
    symbol: str
    direction: str
    created: str                # ISO8601 UTC, when this snapshot was captured
    stage: str                  # which DECISION_STAGES entry this decision reached
    final_action: str           # "approved_entry" | "approved_heads_up" | "rejected"
    version: dict                # {"explainability_engine": VERSION, "schema": SCHEMA_VERSION}

    # --- version & configuration traceability --------------------------------
    platform_version: dict       # engine.platform_version.snapshot()
    config: dict                 # config_snapshot()

    # --- upstream summaries (denormalized + ref pointer, see module docstring) -
    regime_summary: dict         # {primary, confidence, quality_score, transition_label, ref}
    confluence_summary: dict     # {score, final_tier, agree_count, disagree_count, ref}
    confidence_summary: dict     # {overall_confidence, tier, is_calibrated, ref} or {} if never assessed
    portfolio_state: dict        # reused ConfidenceAssessment.portfolio_status (or raw verdict summary)
    risk_assessment: dict        # reused ConfidenceAssessment.risk_status (or raw guard/lock summary)
    historical_context_summary: dict   # market_memory.historical_context() summary, or {}

    # --- explainability (reused from ConfidenceAssessment where available) ---
    advisory_messages: dict = field(default_factory=dict)   # {supporting, conflicting, uncertainty, assumptions}
    supporting_evidence: dict = field(default_factory=dict)  # {highest_impact, lowest_impact}
    rejection: dict | None = None    # {category, reason} or None

    def as_dict(self) -> dict:
        return asdict(self)


def _regime_summary(mkt_regime: dict | None, ref: str = "") -> dict:
    mkt_regime = mkt_regime or {}
    return {
        "primary": mkt_regime.get("primary"),
        "confidence": mkt_regime.get("confidence"),
        "quality_score": mkt_regime.get("quality_score"),
        "transition_label": mkt_regime.get("transition_label"),
        "ref": ref or "",
    }


def _confluence_summary(cr, ref: str = "") -> dict:
    if cr is None:
        return {"score": None, "final_tier": None, "agree_count": 0, "disagree_count": 0, "ref": ref or ""}
    try:
        return {
            "score": getattr(cr, "score", None),
            "final_tier": getattr(cr, "final_tier", None),
            "agree_count": len(getattr(cr, "agree", []) or []),
            "disagree_count": len(getattr(cr, "disagree", []) or []),
            "ref": ref or "",
        }
    except Exception:  # noqa: BLE001
        return {"score": None, "final_tier": None, "agree_count": 0, "disagree_count": 0, "ref": ref or ""}


def _confidence_summary(assessment, ref: str = "") -> dict:
    if assessment is None:
        return {}
    try:
        d = assessment.as_dict() if hasattr(assessment, "as_dict") else dict(assessment)
        return {
            "overall_confidence": d.get("overall_confidence"),
            "tier": d.get("tier"),
            "is_calibrated": d.get("is_calibrated"),
            "ref": ref or "",
        }
    except Exception:  # noqa: BLE001
        return {}


def _memory_summary(memory_context: dict | None) -> dict:
    if not memory_context:
        return {}
    try:
        return {
            "comparable_count": memory_context.get("comparable_count"),
            "sufficient_sample": memory_context.get("sufficient_sample"),
            "confidence_label": (memory_context.get("quality") or {}).get("confidence_label"),
            "aggregate": memory_context.get("aggregate"),
        }
    except Exception:  # noqa: BLE001
        return {}


def build_decision_snapshot(
    symbol: str, direction: str, when, stage: str, final_action: str, *,
    mkt_regime: dict | None = None, regime_ref: str = "",
    cr=None, confluence_ref: str = "",
    confidence_assessment=None, confidence_ref: str = "",
    memory_context: dict | None = None,
    trade_ref: str = "", rejection: dict | None = None,
    settings=None,
) -> DecisionSnapshot:
    """Assemble one DecisionSnapshot from already-computed upstream objects.
    Never raises — a total failure still returns a valid, clearly-labeled
    object rather than raising or returning None, matching
    confidence_engine.assess()'s Day 6 precedent exactly.

    `when`: the pd.Timestamp/str this decision was evaluated at — used to
    build `decision_id` via `journal.make_ref()`, the SAME format
    (`f"{symbol}-{timestamp}"`) `Trade.id` uses. `decision_id` is assigned
    to EVERY decision (approved, heads-up, or rejected) — `trade_ref` is
    only non-empty for decisions that correspond 1:1 to an actual Stage-2
    fill. See module docstring for why these are deliberately two different
    fields, not aliases of each other."""
    try:
        decision_id = journal.make_ref(symbol, when)
    except Exception:  # noqa: BLE001
        decision_id = f"{symbol}-unknown"

    try:
        portfolio_state, risk_assessment, advisory_messages, supporting_evidence = {}, {}, {}, {}
        if confidence_assessment is not None:
            try:
                d = (confidence_assessment.as_dict()
                     if hasattr(confidence_assessment, "as_dict") else dict(confidence_assessment))
                portfolio_state = d.get("portfolio_status") or {}
                risk_assessment = d.get("risk_status") or {}
                advisory_messages = {
                    "supporting_rationale": d.get("supporting_rationale", []),
                    "conflicting_rationale": d.get("conflicting_rationale", []),
                    "uncertainty_indicators": d.get("uncertainty_indicators", []),
                    "assumptions": d.get("assumptions", []),
                }
                supporting_evidence = {
                    "highest_impact_evidence": d.get("highest_impact_evidence"),
                    "lowest_impact_evidence": d.get("lowest_impact_evidence"),
                }
            except Exception:  # noqa: BLE001
                pass

        return DecisionSnapshot(
            decision_id=decision_id, trade_ref=trade_ref or "",
            symbol=symbol, direction=direction,
            created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            stage=stage, final_action=final_action,
            version={"explainability_engine": VERSION, "schema": SCHEMA_VERSION},
            platform_version=pv.snapshot(), config=config_snapshot(settings),
            regime_summary=_regime_summary(mkt_regime, regime_ref),
            confluence_summary=_confluence_summary(cr, confluence_ref),
            confidence_summary=_confidence_summary(confidence_assessment, confidence_ref),
            portfolio_state=portfolio_state, risk_assessment=risk_assessment,
            historical_context_summary=_memory_summary(memory_context),
            advisory_messages=advisory_messages, supporting_evidence=supporting_evidence,
            rejection=dict(rejection) if rejection else None,
        )
    except Exception as exc:  # noqa: BLE001
        return DecisionSnapshot(
            decision_id=decision_id, trade_ref=trade_ref or "",
            symbol=symbol, direction=direction,
            created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            stage=stage, final_action="error",
            version={"explainability_engine": VERSION, "schema": SCHEMA_VERSION},
            platform_version={}, config={},
            regime_summary={}, confluence_summary={}, confidence_summary={},
            portfolio_state={}, risk_assessment={}, historical_context_summary={},
            advisory_messages={}, supporting_evidence={},
            rejection={"category": "internal_error", "reason": f"snapshot build error: {exc}"},
        )


# --- Audit graph -------------------------------------------------------------

def build_audit_graph(row: dict) -> dict:
    """Build the decision graph (nodes = DECISION_STAGES up through the
    stage this decision reached; edges = why the platform progressed from
    one to the next) purely from a PERSISTED decision_audit row — no live
    re-fetch, no re-computation. This is what makes `replay()` deterministic
    (see that function): the graph is a pure, structural reshaping of data
    already in the row. Never raises."""
    try:
        reached = row.get("stage", "market_data_received")
        try:
            reached_idx = DECISION_STAGES.index(reached)
        except ValueError:
            reached_idx = 0
        is_rejected = row.get("final_action") == "rejected"
        nodes = []
        for i, name in enumerate(DECISION_STAGES):
            if i < reached_idx:
                status = "completed"
            elif i == reached_idx:
                status = "rejected" if is_rejected else "completed"
            else:
                status = "not_reached"
            nodes.append({"stage": name, "status": status})
        edges = []
        for i in range(min(reached_idx, len(DECISION_STAGES) - 1)):
            edges.append({"from": DECISION_STAGES[i], "to": DECISION_STAGES[i + 1],
                          "reason": "cleared"})
        if is_rejected and reached_idx < len(DECISION_STAGES) - 1:
            rej = row.get("rejection") or {}
            edges.append({"from": DECISION_STAGES[reached_idx], "to": "rejected",
                          "reason": f"{rej.get('category', 'unknown')}: {rej.get('reason', '')}"})
        return {"decision_id": row.get("decision_id"), "nodes": nodes, "edges": edges}
    except Exception as exc:  # noqa: BLE001
        return {"decision_id": row.get("decision_id") if isinstance(row, dict) else None,
               "nodes": [], "edges": [], "error": str(exc)}


# --- Data lineage ------------------------------------------------------------
# A static, documented map of the pipeline's data flow (the mandate's own
# diagram) — NOT recomputed per decision; annotated per decision by
# `lineage_for_snapshot()` below using only fields already on the row.
DATA_LINEAGE_MAP = [
    {"stage": "market_data", "produces": "OHLCV bars (markets.fetch)",
     "consumed_by": ["market_regime_assessment", "ict_smc_origination"]},
    {"stage": "market_regime_assessment", "produces": "mkt_regime dict (regime_engine.classify)",
     "consumed_by": ["confluence_assessment", "confidence_assessment", "market_memory"]},
    {"stage": "ict_smc_origination", "produces": "Signal (signals.analyze)",
     "consumed_by": ["confluence_assessment", "confidence_assessment"]},
    {"stage": "confluence_assessment", "produces": "ConfluenceRead (confluence.analyze)",
     "consumed_by": ["portfolio_risk", "confidence_assessment", "market_memory"]},
    {"stage": "portfolio_risk", "produces": "portfolio verdict (portfolio_risk.evaluate)",
     "consumed_by": ["confidence_assessment", "market_memory"]},
    {"stage": "confidence_assessment", "produces": "ConfidenceAssessment (confidence_engine.assess)",
     "consumed_by": ["approval_or_rejection", "decision_snapshot", "journal", "dashboard"]},
    {"stage": "market_memory", "produces": "historical_context summary (market_memory.historical_context)",
     "consumed_by": ["confidence_assessment", "decision_snapshot", "dashboard"]},
    {"stage": "decision_snapshot", "produces": "DecisionSnapshot (this module)",
     "consumed_by": ["journal", "dashboard", "research"]},
    {"stage": "journal", "produces": "Trade row (journal.log_signal)",
     "consumed_by": ["dashboard", "research", "post_trade_review", "calibration"]},
    {"stage": "dashboard", "produces": "read-only JSON payload (dashboard_publish.build_payload)",
     "consumed_by": []},
    {"stage": "research", "produces": "aggregate reports (market_memory analytics, confidence_calibration)",
     "consumed_by": []},
]


def lineage_for_snapshot(row: dict) -> dict:
    """Annotate DATA_LINEAGE_MAP with which stages actually produced data
    for THIS decision (using only the row's own recorded ref/summary
    fields — no new fetch). Never raises."""
    try:
        present = {
            "market_data": True,
            "market_regime_assessment": bool((row.get("regime_summary") or {}).get("primary")),
            "ict_smc_origination": True,
            "confluence_assessment": (row.get("confluence_summary") or {}).get("score") is not None,
            "portfolio_risk": bool(row.get("portfolio_state")),
            "confidence_assessment": bool(row.get("confidence_summary")),
            "market_memory": bool(row.get("historical_context_summary")),
            "decision_snapshot": True,
            "journal": bool(row.get("trade_ref")),
            "dashboard": None,   # not determinable from a stored row — disclosed, not guessed
            "research": None,
        }
        return {"map": DATA_LINEAGE_MAP, "present_for_this_decision": present}
    except Exception as exc:  # noqa: BLE001
        return {"map": DATA_LINEAGE_MAP, "present_for_this_decision": {}, "error": str(exc)}


# --- Explanation reports -----------------------------------------------------

def explain_approval(row: dict) -> dict:
    """Structured explanation for an approved (entry or heads-up) decision.
    Operates purely on a PERSISTED row (dict) — the same shape whether
    called live right after build_decision_snapshot() or later via
    replay() — so the answer is identical either way. Never raises."""
    try:
        adv = row.get("advisory_messages") or {}
        conf = row.get("confidence_summary") or {}
        mem = row.get("historical_context_summary") or {}
        return {
            "decision_id": row.get("decision_id"),
            "why_considered": (
                f"ICT/SMC origination (Layer 1) identified a {row.get('direction', '?')} setup in "
                f"{row.get('symbol', '?')}; MAST confluence scored "
                f"{(row.get('confluence_summary') or {}).get('score', 'n/a')}/100."),
            "why_approved": (
                f"Cleared every upstream gate through '{row.get('stage')}' with final action "
                f"'{row.get('final_action')}'" +
                (f"; confidence tier {conf.get('tier')} ({conf.get('overall_confidence')}/100)."
                 if conf else ".")),
            "most_contributing_evidence": (row.get("supporting_evidence") or {}).get("highest_impact_evidence"),
            "least_contributing_evidence": (row.get("supporting_evidence") or {}).get("lowest_impact_evidence"),
            "conflicting_evidence": adv.get("conflicting_rationale", []),
            "assumptions": adv.get("assumptions", []),
            "uncertainty": adv.get("uncertainty_indicators", []),
            "what_would_have_caused_rejection": _hypothetical_rejection_causes(row),
            "historical_context": mem if mem else {"note": "no market-memory context recorded for this decision"},
            "limitations": _limitations(row),
        }
    except Exception as exc:  # noqa: BLE001
        return {"decision_id": row.get("decision_id") if isinstance(row, dict) else None,
               "error": f"explain_approval error: {exc}"}


def explain_rejection(row: dict) -> dict:
    """Structured explanation for a rejected decision. Same replay-safe,
    persisted-row-only contract as explain_approval(). Never raises."""
    try:
        rej = row.get("rejection") or {}
        adv = row.get("advisory_messages") or {}
        mem = row.get("historical_context_summary") or {}
        return {
            "decision_id": row.get("decision_id"),
            "rejection_category": rej.get("category", "unknown"),
            "rejection_reason": rej.get("reason", ""),
            "stage_reached": row.get("stage"),
            "evidence_at_rejection": {
                "regime": row.get("regime_summary"), "confluence": row.get("confluence_summary"),
                "portfolio_state": row.get("portfolio_state"), "risk_assessment": row.get("risk_assessment"),
            },
            "what_would_have_allowed_it": _hypothetical_approval_requirements(row),
            "historical_context": mem if mem else {"note": "no market-memory context recorded for this decision"},
            "assumptions": adv.get("assumptions", []),
            "limitations": _limitations(row),
        }
    except Exception as exc:  # noqa: BLE001
        return {"decision_id": row.get("decision_id") if isinstance(row, dict) else None,
               "error": f"explain_rejection error: {exc}"}


def _hypothetical_rejection_causes(row: dict) -> list:
    """What WOULD have caused this approved decision to be rejected instead
    — a plain-language readout of the same thresholds `config_snapshot()`
    already recorded, not a re-run of any gate. Descriptive, not a
    counterfactual simulation."""
    out = []
    try:
        cfg = row.get("config") or {}
        cs = row.get("confluence_summary") or {}
        if cs.get("score") is not None and cfg.get("confluence_min_score") is not None:
            out.append(f"MAST confluence score below {cfg['confluence_min_score']} "
                       f"(scored {cs['score']})")
        if cfg.get("regime_filter_mode") == "block":
            out.append(f"regime quality_score below {cfg.get('regime_min_quality_for_block')} "
                       "(regime_filter_mode=block)")
        out.append("a portfolio risk violation (see engine.portfolio_risk's ten-category "
                   "vocabulary) under portfolio_risk_mode="
                   f"{cfg.get('portfolio_risk_mode', '?')}")
        out.append("an active daily-loss risk lock for this symbol")
    except Exception:  # noqa: BLE001
        pass
    return out


def _hypothetical_approval_requirements(row: dict) -> list:
    """Inverse of the above: what this specific rejection's category
    implies would need to be true for a future, otherwise-similar
    opportunity to clear. Plain-language readout, not a simulation."""
    rej = row.get("rejection") or {}
    cat = rej.get("category", "")
    cfg = row.get("config") or {}
    mapping = {
        WEAK_EVIDENCE: f"MAST confluence score at/above {cfg.get('confluence_min_score', '?')}",
        pr.MARKET_REGIME_UNSUITABLE: f"regime quality_score at/above {cfg.get('regime_min_quality_for_block', '?')}",
        pr.RISK_BUDGET_EXCEEDED: "portfolio risk usage back under the configured budget",
        pr.CORRELATION_TOO_HIGH: f"correlation vs. open positions below {cfg.get('correlation_high_threshold', '?')}",
        pr.PORTFOLIO_EXPOSURE_EXCEEDED: "reduced same-direction/portfolio exposure",
        pr.DRAWDOWN_PROTECTION: "trailing drawdown back under the configured cap",
        RISK_LOCK: "the daily-loss lock for this symbol to reset (new trading day)",
        NEWS_BLACKOUT: "the news blackout window to end",
    }
    return [mapping.get(cat, "the specific condition in `rejection_reason` above to no longer hold")]


def _limitations(row: dict) -> list:
    out = []
    try:
        if not row.get("confidence_summary"):
            out.append("no Confidence Engine assessment was recorded for this decision")
        if not row.get("historical_context_summary"):
            out.append("no Market Memory historical context was recorded for this decision")
        cfg = row.get("config") or {}
        if not cfg or all(v is None for v in cfg.values()):
            out.append("configuration snapshot is empty — settings were unavailable when this "
                       "decision was captured")
    except Exception:  # noqa: BLE001
        out.append("limitations assessment itself encountered an error")
    return out


# --- Post-trade review --------------------------------------------------------

def post_trade_review(decision_id_or_trade_ref: str) -> dict:
    """After a trade closes, compare the original DecisionSnapshot's
    reasoning against the actual outcome. This is a LIGHTWEIGHT, disclosed
    heuristic comparison — matching `uncertainty_indicators` and
    `conflicting_rationale` text against the realized win/loss/scratch
    result — not a causal attribution model. Never raises; degrades
    gracefully when the trade hasn't closed yet or no decision row exists.
    Does NOT modify production logic (mandate: "Do not automatically modify
    production logic") — this is a read-only report."""
    try:
        row = (dah.find_by_ref(decision_id_or_trade_ref)
               or dah.find_by_trade_ref(decision_id_or_trade_ref))
        if row is None:
            return {"found": False, "note": "no decision snapshot found for this reference"}
        trade_ref = row.get("trade_ref") or ""
        trade_row = None
        if trade_ref:
            for t in store.load_array(journal.STORE):   # same public reader portfolio_risk.py uses
                if t.get("id") == trade_ref:
                    trade_row = t
                    break
        if trade_row is None:
            return {"found": True, "closed": False,
                   "note": "decision snapshot exists but no matching trade row was found "
                          "(heads-up that never filled, or a rejection) — nothing to review yet",
                   "original_reasoning": explain_approval(row) if row.get("final_action") != "rejected"
                                         else explain_rejection(row)}
        if trade_row.get("status") == "open":
            return {"found": True, "closed": False,
                   "note": "trade is still open — post-trade review is only meaningful once closed"}

        status = trade_row.get("status")
        result_r = trade_row.get("result_r")
        adv = row.get("advisory_messages") or {}
        uncertainty = adv.get("uncertainty_indicators", [])
        conflicting = adv.get("conflicting_rationale", [])
        won = status == "win"
        assumptions_held = [] if won else uncertainty[:]     # heuristic only — see docstring
        assumptions_failed_note = (
            "heuristic only: every recorded uncertainty indicator is listed here for a losing/"
            "scratch trade, not a proven causal link — see EXPLAINABILITY_SPECIFICATION.md Sec.8")
        return {
            "found": True, "closed": True,
            "decision_id": row.get("decision_id"), "trade_ref": trade_ref,
            "original_reasoning": explain_approval(row),
            "actual_outcome": {"status": status, "result_r": result_r, "closed": trade_row.get("closed")},
            "expectation_vs_outcome": (
                f"assessed at confidence tier {(row.get('confidence_summary') or {}).get('tier', 'n/a')}; "
                f"realized {status} ({result_r:+.2f}R)" if isinstance(result_r, (int, float))
                else f"assessed at confidence tier {(row.get('confidence_summary') or {}).get('tier', 'n/a')}; "
                     f"realized {status}"),
            "assumptions_that_may_have_held": [] if not won else uncertainty[:],
            "assumptions_that_may_have_failed": assumptions_held,
            "conflicting_evidence_at_decision_time": conflicting,
            "heuristic_disclosure": assumptions_failed_note,
            "recommendations_for_future_research": _review_recommendations(status, uncertainty, conflicting),
        }
    except Exception as exc:  # noqa: BLE001
        return {"found": False, "error": f"post_trade_review error: {exc}"}


def _review_recommendations(status: str, uncertainty: list, conflicting: list) -> list:
    out = []
    try:
        if status in ("loss", "scratch") and uncertainty:
            out.append("this losing/scratch trade had recorded uncertainty indicators at decision "
                       "time — worth including in any future review of which indicators correlate "
                       "with worse outcomes, once enough closed trades accumulate")
        if status in ("loss", "scratch") and conflicting:
            out.append("conflicting evidence was present at decision time and the trade did not "
                       "win — one data point, not a pattern; revisit once N is large enough for "
                       "market_memory.performance_by_* to say something statistically meaningful")
        if status == "win" and conflicting:
            out.append("this trade won despite recorded conflicting evidence — also just one data "
                       "point, but worth flagging so a future review doesn't only look at losses")
        if not out:
            out.append("no notable pattern from this single trade in isolation — "
                       "recommendations become meaningful in aggregate, not per-trade")
    except Exception:  # noqa: BLE001
        pass
    return out


# --- Replay (reproducibility proof) ------------------------------------------

def replay(decision_id: str) -> dict:
    """Reconstruct the full explanation for a past decision PURELY from
    persisted evidence — no live computation, no re-fetch. Calling this
    twice for the same `decision_id` must return byte-identical output
    (see tests/test_replay.py) — that determinism is the literal meaning of
    "historical explanations must remain reproducible" in the Day 8
    mandate. Never raises."""
    try:
        row = dah.find_by_ref(decision_id)
        if row is None:
            return {"found": False, "decision_id": decision_id,
                    "note": "no decision snapshot found for this decision_id"}
        graph = build_audit_graph(row)
        lineage = lineage_for_snapshot(row)
        explanation = (explain_rejection(row) if row.get("final_action") == "rejected"
                      else explain_approval(row))
        corrections = [r for r in dah.history_for_ref(decision_id) if r.get("record_type") == "correction"]
        return {
            "found": True, "decision_id": decision_id, "snapshot": row,
            "graph": graph, "lineage": lineage, "explanation": explanation,
            "corrections": corrections,
        }
    except Exception as exc:  # noqa: BLE001
        return {"found": False, "decision_id": decision_id, "error": f"replay error: {exc}"}
