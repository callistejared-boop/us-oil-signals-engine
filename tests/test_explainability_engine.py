"""Offline tests for engine/explainability_engine.py (Day 8). Covers
DecisionSnapshot assembly, config/version traceability, the audit graph,
data lineage, explain_approval()/explain_rejection(), and graceful
degradation on missing/garbage data.
"""
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import explainability_engine as ee   # noqa: E402
from engine import confluence as cf              # noqa: E402
from engine import confidence_engine as ce        # noqa: E402
from engine import portfolio_risk as pr           # noqa: E402


def _cr(score=80, final_tier="confirmed", agree=None, disagree=None):
    return cf.ConfluenceRead(
        symbol="XAUUSD", direction="long", base_tier="confirmed", final_tier=final_tier,
        score=score, agree=agree or ["price action", "trend"], disagree=disagree or [])


def _assessment(overall_confidence=75, tier="High Confidence"):
    return ce.ConfidenceAssessment(
        symbol="XAUUSD", direction="long", timestamp="2026-08-03T10:00:00",
        version={"confidence_engine": ce.VERSION, "schema": ce.SCHEMA_VERSION},
        overall_confidence=overall_confidence, tier=tier,
        probability_label="internal decision-quality estimate", calibrated_probability=None,
        is_calibrated=False, evidence_quality=70, evidence_diversity=60,
        market_quality=75, regime_confidence=65, confluence_quality=70,
        portfolio_status={"allow": True, "would_block": False, "category": None, "reason": None, "heat": 1.2},
        risk_status={"guard_action": "allow", "guard_penalty": 0, "risk_locked": False, "macro_headwind": False},
        uncertainty_indicators=["incomplete market data (evidence coverage below 60%)"],
        supporting_rationale=["confluence: price action"],
        conflicting_rationale=["confluence: momentum divergence"],
        highest_impact_evidence="price action", lowest_impact_evidence="momentum divergence",
        assumptions=["disclosed, non-fitted weights"],
    )


# --- config_snapshot ----------------------------------------------------------

def test_config_snapshot_none_settings_returns_all_none():
    out = ee.config_snapshot(None)
    assert set(out.keys()) == set(ee.CONFIG_FIELDS)
    assert all(v is None for v in out.values())


def test_config_snapshot_reads_real_fields():
    class S:
        confluence_min_score = 70
        regime_filter_mode = "advisory"
    out = ee.config_snapshot(S())
    assert out["confluence_min_score"] == 70
    assert out["regime_filter_mode"] == "advisory"
    assert out["portfolio_equity"] is None   # not set on the fake Settings -> None, not fabricated


def test_config_snapshot_never_raises_on_garbage():
    out = ee.config_snapshot(object())
    assert isinstance(out, dict)


# --- build_decision_snapshot ---------------------------------------------------

def test_build_snapshot_approved_entry_full_context():
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="approval_or_rejection",
        final_action="approved_entry",
        mkt_regime={"primary": "trend", "confidence": 70, "quality_score": 65, "transition_label": "low"},
        regime_ref="XAUUSD-2026-08-03T10:00:00",
        cr=_cr(), confluence_ref="XAUUSD-2026-08-03T10:00:00",
        confidence_assessment=_assessment(), confidence_ref="XAUUSD-2026-08-03T10:00:00",
        memory_context={"comparable_count": 12, "sufficient_sample": True,
                        "quality": {"confidence_label": "sparse"}, "aggregate": {"win_rate": 0.5}},
        trade_ref="XAUUSD-2026-08-03T10:00:00")
    assert snap.decision_id == "XAUUSD-2026-08-03T10:00:00"
    assert snap.trade_ref == "XAUUSD-2026-08-03T10:00:00"
    assert snap.final_action == "approved_entry"
    assert snap.regime_summary["primary"] == "trend"
    assert snap.confluence_summary["score"] == 80
    assert snap.confidence_summary["overall_confidence"] == 75
    assert snap.portfolio_state["allow"] is True
    assert snap.risk_assessment["guard_action"] == "allow"
    assert snap.historical_context_summary["comparable_count"] == 12
    assert snap.advisory_messages["supporting_rationale"]
    assert snap.supporting_evidence["highest_impact_evidence"] == "price action"
    assert snap.rejection is None
    assert snap.platform_version["platform_version"]
    assert snap.version["schema"] == ee.SCHEMA_VERSION


def test_build_snapshot_rejected_minimal_context():
    snap = ee.build_decision_snapshot(
        "WTIUSD", "short", "2026-08-03 11:00:00", stage="confluence_assessment",
        final_action="rejected",
        rejection={"category": ee.WEAK_EVIDENCE, "reason": "score 55 below min 70"})
    assert snap.final_action == "rejected"
    assert snap.rejection["category"] == ee.WEAK_EVIDENCE
    assert snap.confluence_summary["score"] is None   # no cr supplied -> honestly None, not fabricated
    assert snap.confidence_summary == {}               # never assessed


def test_build_snapshot_never_raises_on_garbage_inputs():
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", object(), stage="unknown_stage", final_action="approved_entry",
        mkt_regime="not-a-dict", cr="not-a-cr", confidence_assessment="not-an-assessment",
        memory_context="not-a-dict", settings="not-settings")
    assert snap.decision_id   # still produced something, never raised
    assert isinstance(snap.as_dict(), dict)


def test_decision_id_distinct_from_trade_ref_for_heads_up():
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 09:00:00", stage="approval_or_rejection",
        final_action="approved_heads_up")
    assert snap.decision_id == "XAUUSD-2026-08-03T09:00:00"
    assert snap.trade_ref == ""   # heads-up never became a fill


# --- audit graph ----------------------------------------------------------------

def test_audit_graph_approved_all_nodes_completed():
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="approval_or_rejection",
        final_action="approved_entry")
    g = ee.build_audit_graph(snap.as_dict())
    assert len(g["nodes"]) == len(ee.DECISION_STAGES)
    reached = ee.DECISION_STAGES.index("approval_or_rejection")
    assert g["nodes"][reached]["status"] == "completed"
    assert g["nodes"][reached + 1]["status"] == "not_reached"
    assert len(g["edges"]) == reached


def test_audit_graph_rejected_has_terminal_rejection_edge():
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="confluence_assessment",
        final_action="rejected", rejection={"category": ee.WEAK_EVIDENCE, "reason": "score too low"})
    g = ee.build_audit_graph(snap.as_dict())
    reached = ee.DECISION_STAGES.index("confluence_assessment")
    assert g["nodes"][reached]["status"] == "rejected"
    assert g["nodes"][reached + 1]["status"] == "not_reached"
    last_edge = g["edges"][-1]
    assert last_edge["to"] == "rejected"
    assert "weak_evidence" in last_edge["reason"]


def test_audit_graph_never_raises_on_garbage():
    g = ee.build_audit_graph({"stage": "does_not_exist", "final_action": "rejected"})
    assert isinstance(g, dict)
    assert "nodes" in g


# --- data lineage -----------------------------------------------------------------

def test_lineage_map_covers_the_mandates_diagram():
    stages = {x["stage"] for x in ee.DATA_LINEAGE_MAP}
    for expected in ("market_data", "confluence_assessment", "confidence_assessment",
                     "journal", "dashboard", "research"):
        assert expected in stages


def test_lineage_for_snapshot_reflects_present_fields():
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="approval_or_rejection",
        final_action="approved_entry", cr=_cr(), trade_ref="XAUUSD-2026-08-03T10:00:00")
    out = ee.lineage_for_snapshot(snap.as_dict())
    assert out["present_for_this_decision"]["confluence_assessment"] is True
    assert out["present_for_this_decision"]["journal"] is True


def test_lineage_never_raises_on_garbage():
    out = ee.lineage_for_snapshot("not-a-dict")
    assert "map" in out


# --- explain_approval / explain_rejection ---------------------------------------

def test_explain_approval_answers_every_required_question():
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="approval_or_rejection",
        final_action="approved_entry", cr=_cr(), confidence_assessment=_assessment(),
        memory_context={"comparable_count": 40, "sufficient_sample": True,
                        "quality": {"confidence_label": "moderate"}, "aggregate": {"win_rate": 0.55}})
    ex = ee.explain_approval(snap.as_dict())
    required = ("why_considered", "why_approved", "most_contributing_evidence",
               "least_contributing_evidence", "conflicting_evidence", "assumptions",
               "uncertainty", "what_would_have_caused_rejection", "historical_context",
               "limitations")
    for key in required:
        assert key in ex
    assert ex["most_contributing_evidence"] == "price action"
    assert ex["least_contributing_evidence"] == "momentum divergence"
    assert ex["historical_context"]["comparable_count"] == 40


def test_explain_rejection_answers_every_required_question():
    snap = ee.build_decision_snapshot(
        "XAUUSD", "short", "2026-08-03 10:00:00", stage="portfolio_risk",
        final_action="rejected",
        rejection={"category": pr.CORRELATION_TOO_HIGH, "reason": "0.8 correlation vs open XAUUSD"})
    ex = ee.explain_rejection(snap.as_dict())
    required = ("rejection_category", "rejection_reason", "stage_reached",
               "evidence_at_rejection", "what_would_have_allowed_it", "historical_context",
               "assumptions", "limitations")
    for key in required:
        assert key in ex
    assert ex["rejection_category"] == pr.CORRELATION_TOO_HIGH
    assert ex["stage_reached"] == "portfolio_risk"
    assert "correlation" in ex["what_would_have_allowed_it"][0].lower()


def test_explain_approval_never_raises_on_garbage():
    ex = ee.explain_approval({"decision_id": None})
    assert "decision_id" in ex


def test_explain_rejection_never_raises_on_garbage():
    ex = ee.explain_rejection({"decision_id": None})
    assert "decision_id" in ex


def test_explain_rejection_risk_lock_requirement():
    snap = ee.build_decision_snapshot(
        "XAUUSD", "long", "2026-08-03 10:00:00", stage="market_regime_assessment",
        final_action="rejected", rejection={"category": ee.RISK_LOCK, "reason": "daily loss -2R"})
    ex = ee.explain_rejection(snap.as_dict())
    assert "reset" in ex["what_would_have_allowed_it"][0].lower()


# --- performance -------------------------------------------------------------------

def test_large_history_graph_and_explain_performance():
    """Guard against an accidental O(n^2)/O(n^3) regression, not a strict
    contract — same framing as market_memory's 2000-record benchmark."""
    rows = [ee.build_decision_snapshot(
        "XAUUSD", "long", f"2026-08-03 10:{i % 60:02d}:00", stage="approval_or_rejection",
        final_action="approved_entry", cr=_cr(), confidence_assessment=_assessment()).as_dict()
        for i in range(500)]
    start = time.time()
    for row in rows:
        ee.build_audit_graph(row)
        ee.explain_approval(row)
    elapsed = time.time() - start
    assert elapsed < 5.0
