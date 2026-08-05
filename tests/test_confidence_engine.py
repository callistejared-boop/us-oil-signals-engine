"""Offline tests for engine/confidence_engine.py (Day 6).

Uses lightweight fakes (SimpleNamespace / plain dicts) for `sig`, `cr`,
`mkt_regime`, `portfolio_verdict`, `guard`, `news_state` rather than driving
the full live pipeline — same approach Day 3/4/5 already used for testing
gate/analysis functions in isolation from data-fetching concerns.
"""
import pathlib
import sys
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import confidence_engine as ce  # noqa: E402


def _sig(confidence=75, symbol="XAUUSD", direction="long"):
    return SimpleNamespace(confidence=confidence, symbol=symbol, direction=direction)


def _cr(score=80, agree=None, disagree=None, layers=None, direction="long"):
    return SimpleNamespace(
        symbol="XAUUSD", direction=direction, score=score,
        agree=agree or ["price action", "COT positioning"],
        disagree=disagree or [],
        layers=layers or {"macro": {"aligned": True}, "trend": {"continuation_ok": True}},
    )


def _regime(confidence=70, quality_score=70, tags=None, per_tf=None, error=None):
    d = {
        "confidence": confidence, "quality_score": quality_score,
        "tags": tags or [], "evidence": ["daily uptrend intact"],
        "conflicting_evidence": [], "transition_label": "stable",
        "per_tf": per_tf or {"1d": {"sufficient": True}, "4h": {"sufficient": True}},
    }
    if error:
        d["error"] = error
    return d


def _portfolio(allow=True, would_block=False, reason="portfolio checks clear"):
    return {"allow": allow, "would_block": would_block, "category": None,
           "reason": reason, "detail": {"portfolio_heat": 0.2}}


# --- decision tiers -----------------------------------------------------------

def test_classify_tier_default_boundaries():
    assert ce.classify_tier(90) == "Exceptional Confidence"
    assert ce.classify_tier(85) == "Exceptional Confidence"
    assert ce.classify_tier(84) == "High Confidence"
    assert ce.classify_tier(70) == "High Confidence"
    assert ce.classify_tier(69) == "Moderate Confidence"
    assert ce.classify_tier(55) == "Moderate Confidence"
    assert ce.classify_tier(54) == "Low Confidence"
    assert ce.classify_tier(40) == "Low Confidence"
    assert ce.classify_tier(39) == ce.RESEARCH_ONLY
    assert ce.classify_tier(0) == ce.RESEARCH_ONLY


def test_classify_tier_never_raises_on_garbage():
    assert ce.classify_tier(None) == ce.RESEARCH_ONLY
    assert ce.classify_tier(-50) == ce.RESEARCH_ONLY
    assert ce.classify_tier(500) == "Exceptional Confidence"  # clamped to 100


def test_classify_tier_respects_settings_override():
    settings = SimpleNamespace(confidence_tier_exceptional=95, confidence_tier_high=80,
                               confidence_tier_moderate=60, confidence_tier_low=45)
    assert ce.classify_tier(90, settings=settings) == "High Confidence"  # would be Exceptional by default


# --- assess() basic behavior --------------------------------------------------

def test_assess_returns_valid_object_with_full_context():
    a = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr(),
                  portfolio_verdict=_portfolio(), guard={"action": "allow", "penalty": 0},
                  news_state={}, session="London KZ", risk_locked=False)
    assert isinstance(a, ce.ConfidenceAssessment)
    assert a.symbol == "XAUUSD" and a.direction == "long"
    assert 0 <= a.overall_confidence <= 100
    assert a.tier in [t[2] for t in ce.DEFAULT_TIERS] + [ce.RESEARCH_ONLY]
    assert a.version["confidence_engine"] == ce.VERSION


def test_assess_never_raises_on_all_none():
    a = ce.assess("XAUUSD", "long")
    assert isinstance(a, ce.ConfidenceAssessment)
    assert a.overall_confidence == 0
    assert a.tier == ce.RESEARCH_ONLY


def test_assess_never_raises_on_garbage_input():
    a = ce.assess("XAUUSD", "long", sig="not a signal", mkt_regime="not a dict",
                  cr=12345, portfolio_verdict=[], guard="oops", news_state=None)
    assert isinstance(a, ce.ConfidenceAssessment)


def test_assess_uses_sig_confidence_when_no_confluence_read():
    a = ce.assess("XAUUSD", "long", sig=_sig(confidence=90), mkt_regime=_regime(), cr=None)
    # base_evidence falls back to sig.confidence (90) when cr is None
    assert a.overall_confidence > 0
    assert a.confluence_quality == 0   # no confluence read -> 0, not fabricated


def test_assess_is_not_calibrated_by_default():
    """No real historical data exists yet (Day 6 just went live) — every
    assessment must honestly report is_calibrated=False and explain why in
    probability_label, never silently present overall_confidence as a
    probability."""
    a = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr())
    assert a.is_calibrated is False
    assert a.calibrated_probability is None
    assert "not a statistically calibrated probability" in a.probability_label.lower()


# --- sub-score composition ----------------------------------------------------

def test_higher_confluence_quality_raises_overall_confidence():
    strong = _cr(score=85, agree=["price action", "COT positioning", "seasonality",
                                   "cross-asset risk sentiment", "chart pattern"])
    weak = _cr(score=85, agree=["Wyckoff (Spring)", "session/kill-zone timing"])  # duplicate-heavy
    a_strong = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=strong)
    a_weak = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=weak)
    assert a_strong.confluence_quality >= a_weak.confluence_quality
    assert a_strong.overall_confidence >= a_weak.overall_confidence


def test_would_block_portfolio_reduces_overall_confidence():
    ok = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr(),
                   portfolio_verdict=_portfolio(would_block=False))
    blocked = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr(),
                        portfolio_verdict=_portfolio(would_block=True))
    assert blocked.overall_confidence < ok.overall_confidence
    assert blocked.portfolio_status["would_block"] is True


def test_guard_penalty_reduces_overall_confidence():
    no_penalty = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr(),
                           guard={"action": "allow", "penalty": 0})
    penalized = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr(),
                          guard={"action": "downgrade", "penalty": -15})
    assert penalized.overall_confidence < no_penalty.overall_confidence
    assert penalized.risk_status["guard_penalty"] == -15


def test_risk_locked_reduces_overall_confidence():
    unlocked = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr(),
                         risk_locked=False)
    locked = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr(),
                       risk_locked=True)
    assert locked.overall_confidence < unlocked.overall_confidence
    assert locked.risk_status["risk_locked"] is True


def test_overall_confidence_never_double_counts_layer1_via_addition():
    """base_evidence uses EITHER cr.score (which already embeds Layer 1 at
    45% weight) OR sig.confidence directly — never both added together,
    which would reproduce the exact echo the Day 5 audit flagged."""
    sig = _sig(confidence=95)
    cr = _cr(score=60)  # a low confluence score despite high Layer-1 confidence
    a = ce.assess("XAUUSD", "long", sig=sig, mkt_regime=_regime(), cr=cr)
    # overall must be grounded in cr.score (60), not sig.confidence (95) --
    # so it should land well below what a 95-based calc would produce
    assert a.overall_confidence < 90


# --- market_quality / evidence_quality -----------------------------------------

def test_market_quality_penalizes_stale_data():
    fresh = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr(),
                      session="London KZ", data_stale=False)
    stale = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr(),
                      session="London KZ", data_stale=True)
    assert stale.market_quality < fresh.market_quality


def test_market_quality_penalizes_illiquid_tag():
    normal = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(tags=[]), cr=_cr())
    illiquid = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(tags=["Illiquid"]), cr=_cr())
    assert illiquid.market_quality < normal.market_quality


def test_evidence_quality_reflects_confluence_coverage():
    full = _cr(agree=["price action", "COT positioning", "seasonality", "chart pattern",
                      "cross-asset risk sentiment", "RSI divergence"], disagree=[])
    empty = _cr(agree=[], disagree=[])
    a_full = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=full)
    a_empty = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=empty)
    assert a_full.evidence_quality >= a_empty.evidence_quality


def test_evidence_quality_penalizes_missing_confluence_read():
    with_cr = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr())
    without_cr = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=None)
    assert without_cr.evidence_quality < with_cr.evidence_quality


# --- uncertainty engine ---------------------------------------------------------

def test_uncertainty_flags_insufficient_calibration_data():
    a = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr())
    assert any("insufficient historical data" in u for u in a.uncertainty_indicators)


def test_uncertainty_flags_degraded_regime_service():
    a = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(error="feed timeout"), cr=_cr())
    assert any("degraded regime-engine" in u for u in a.uncertainty_indicators)


def test_uncertainty_flags_missing_news_calendar():
    a = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr(),
                  news_state={"note": "calendar unavailable (timeout)"})
    assert any("degraded news/calendar" in u for u in a.uncertainty_indicators)


def test_uncertainty_flags_missing_confluence_engine():
    a = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=None)
    assert any("confluence engine unavailable" in u for u in a.uncertainty_indicators)


def test_uncertainty_flags_missing_macro_input():
    cr = _cr(layers={"macro": {"aligned": None}})
    a = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=cr)
    assert any("missing macro input" in u for u in a.uncertainty_indicators)


def test_uncertainty_flags_elevated_correlation():
    pv = _portfolio()
    pv["detail"]["correlation"] = {"against": "WTIUSD", "corr": 0.82}
    a = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr(), portfolio_verdict=pv)
    assert any("correlation" in u for u in a.uncertainty_indicators)


def test_uncertainty_does_not_reject_the_trade():
    """Per the mandate: uncertainty reduces trust, never rejects. assess()
    has no allow/reject field at all — its presence is confirmation that
    uncertainty is advisory-only by construction."""
    a = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(error="x"), cr=None,
                  news_state={"note": "down"}, risk_locked=True)
    assert not hasattr(a, "allow")
    assert not hasattr(a, "reject")
    assert isinstance(a.overall_confidence, int)  # still produces a usable score


# --- explainability --------------------------------------------------------------

def test_rationale_populated_from_upstream_evidence():
    a = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr())
    assert len(a.supporting_rationale) > 0
    assert any("regime:" in s for s in a.supporting_rationale)


def test_conflicting_rationale_populated_on_portfolio_block():
    a = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr(),
                  portfolio_verdict=_portfolio(would_block=True, reason="correlation too high"))
    assert any("correlation too high" in c for c in a.conflicting_rationale)


def test_assumptions_always_disclose_non_fitted_weights():
    a = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr())
    assert any("not weights fitted to historical outcomes" in x for x in a.assumptions)


# --- Day 7: memory_context integration (informational only) --------------------

def test_memory_context_never_changes_overall_confidence():
    """The core Day 7 integration guarantee: passing memory_context can
    change assumptions/rationale TEXT but never the score itself."""
    without = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr())
    ctx_insufficient = {"sufficient_sample": False, "comparable_count": 2}
    ctx_sufficient = {"sufficient_sample": True, "comparable_count": 40,
                      "aggregate": {"win_rate": 0.9, "n": 40}}
    with_insufficient = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr(),
                                  memory_context=ctx_insufficient)
    with_sufficient = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr(),
                                memory_context=ctx_sufficient)
    assert without.overall_confidence == with_insufficient.overall_confidence == with_sufficient.overall_confidence
    assert without.tier == with_insufficient.tier == with_sufficient.tier


def test_memory_context_sufficient_sample_adds_supporting_rationale():
    ctx = {"sufficient_sample": True, "comparable_count": 40,
          "aggregate": {"win_rate": 0.7, "n": 40}}
    a = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr(), memory_context=ctx)
    assert any("market memory" in s for s in a.supporting_rationale)


def test_memory_context_insufficient_sample_adds_assumption():
    ctx = {"sufficient_sample": False, "comparable_count": 3}
    a = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr(), memory_context=ctx)
    assert any("market memory found only 3" in x for x in a.assumptions)


def test_memory_context_none_by_default():
    a = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr())
    assert not any("market memory" in s for s in a.supporting_rationale)


def test_memory_context_garbage_never_raises():
    a = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr(),
                  memory_context="not a dict")
    assert isinstance(a, ce.ConfidenceAssessment)


def test_as_dict_and_summary_line():
    a = ce.assess("XAUUSD", "long", sig=_sig(), mkt_regime=_regime(), cr=_cr())
    d = a.as_dict()
    assert d["symbol"] == "XAUUSD" and "overall_confidence" in d
    line = a.summary_line()
    assert "XAUUSD" in line and a.tier in line
