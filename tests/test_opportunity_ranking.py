"""Offline tests for engine/opportunity_ranking.py (V2.2 Priority 3:
Opportunity Ranking -- genuine new build, no prior code to extend).

No mocking needed for most of these: score_opportunity()/rank_opportunities()
are pure functions over OpportunityCandidate dataclasses, so tests construct
candidates directly rather than monkeypatching upstream modules."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import opportunity_ranking as opr  # noqa: E402


def _cand(symbol="XAUUSD", direction="long", overall_confidence=70, confluence_score=75,
         regime_quality=60, calibrated_probability=None, is_calibrated=False,
         risk_budget_remaining_pct=None, session=None, grade_letter=None):
    return opr.OpportunityCandidate(
        symbol=symbol, direction=direction, overall_confidence=overall_confidence,
        confluence_score=confluence_score, regime_quality=regime_quality,
        calibrated_probability=calibrated_probability, is_calibrated=is_calibrated,
        risk_budget_remaining_pct=risk_budget_remaining_pct, session=session,
        grade_letter=grade_letter)


# --------------------------------------------------------------------------
# score_opportunity
# --------------------------------------------------------------------------

def test_score_opportunity_uses_overall_confidence_when_not_calibrated():
    c = _cand(overall_confidence=80, confluence_score=70, regime_quality=60,
             is_calibrated=False, calibrated_probability=0.99)
    composite, primary, source = opr.score_opportunity(c)
    assert source == "overall_confidence"
    assert primary == 80.0
    # 0.6*80 + 0.25*70 + 0.15*60 = 48 + 17.5 + 9 = 74.5
    assert composite == 74.5


def test_score_opportunity_prefers_calibrated_probability_when_available():
    c = _cand(overall_confidence=80, confluence_score=70, regime_quality=60,
             is_calibrated=True, calibrated_probability=0.65)
    composite, primary, source = opr.score_opportunity(c)
    assert source == "calibrated_probability"
    assert primary == 65.0
    # 0.6*65 + 0.25*70 + 0.15*60 = 39 + 17.5 + 9 = 65.5
    assert composite == 65.5


def test_score_opportunity_ignores_calibrated_probability_if_is_calibrated_false():
    """A stale/leftover calibrated_probability value must not be used if
    is_calibrated is False -- matches confidence_engine.py's own contract
    that calibrated_probability is None until confidence_calibration.py has
    enough data, and is_calibrated is the authoritative flag."""
    c = _cand(overall_confidence=55, is_calibrated=False, calibrated_probability=0.9)
    _, primary, source = opr.score_opportunity(c)
    assert source == "overall_confidence"
    assert primary == 55.0


def test_score_opportunity_clamps_out_of_range_inputs():
    c = _cand(overall_confidence=150, confluence_score=-10, regime_quality=200)
    composite, primary, _ = opr.score_opportunity(c)
    assert primary == 100.0  # clamped
    assert 0 <= composite <= 100


def test_score_opportunity_never_raises_on_none_fields():
    c = opr.OpportunityCandidate(symbol="X", direction="long", overall_confidence=None,
                                 confluence_score=None, regime_quality=None)
    composite, primary, source = opr.score_opportunity(c)
    assert composite == 0.0
    assert primary == 0.0


# --------------------------------------------------------------------------
# rank_opportunities
# --------------------------------------------------------------------------

def test_rank_opportunities_empty_input():
    assert opr.rank_opportunities([]) == []
    assert opr.rank_opportunities(None) == []


def test_rank_opportunities_orders_best_first():
    low = _cand(symbol="WTIUSD", overall_confidence=40, confluence_score=50, regime_quality=40)
    high = _cand(symbol="XAUUSD", overall_confidence=90, confluence_score=85, regime_quality=80)
    mid = _cand(symbol="BTCUSD", overall_confidence=65, confluence_score=65, regime_quality=60)
    ranked = opr.rank_opportunities([low, high, mid])
    assert [r.symbol for r in ranked] == ["XAUUSD", "BTCUSD", "WTIUSD"]
    assert [r.rank for r in ranked] == [1, 2, 3]
    assert ranked[0].composite_score > ranked[1].composite_score > ranked[2].composite_score


def test_rank_opportunities_tie_break_by_confluence_score():
    """Equal composite_score (deliberately constructed so confluence_score
    and regime_quality trade off to the same total) should break the tie
    by confluence_score descending -- confluence is the second-highest
    weighted signal, ahead of regime_quality."""
    a = _cand(symbol="AAA", overall_confidence=70, confluence_score=80, regime_quality=10)
    b = _cand(symbol="BBB", overall_confidence=70, confluence_score=50, regime_quality=60)
    # a: 0.6*70 + 0.25*80 + 0.15*10 = 42 + 20 + 1.5  = 63.5
    # b: 0.6*70 + 0.25*50 + 0.15*60 = 42 + 12.5 + 9   = 63.5  (tied composite)
    composite_a, _, _ = opr.score_opportunity(a)
    composite_b, _, _ = opr.score_opportunity(b)
    assert composite_a == composite_b == 63.5
    ranked = opr.rank_opportunities([b, a])
    assert ranked[0].symbol == "AAA"  # higher confluence_score wins the tie


def test_rank_opportunities_tie_break_by_symbol_when_fully_tied():
    a = _cand(symbol="ZZZ", overall_confidence=70, confluence_score=70, regime_quality=70)
    b = _cand(symbol="AAA", overall_confidence=70, confluence_score=70, regime_quality=70)
    ranked = opr.rank_opportunities([a, b])
    assert ranked[0].composite_score == ranked[1].composite_score
    assert [r.symbol for r in ranked] == ["AAA", "ZZZ"]  # alphabetical tie-break


def test_rank_opportunities_deterministic_regardless_of_input_order():
    a = _cand(symbol="AAA", overall_confidence=70, confluence_score=70, regime_quality=70)
    b = _cand(symbol="ZZZ", overall_confidence=70, confluence_score=70, regime_quality=70)
    order1 = [r.symbol for r in opr.rank_opportunities([a, b])]
    order2 = [r.symbol for r in opr.rank_opportunities([b, a])]
    assert order1 == order2 == ["AAA", "ZZZ"]


def test_rank_opportunities_preserves_all_input_candidates():
    cands = [_cand(symbol=s) for s in ("XAUUSD", "WTIUSD", "BTCUSD")]
    ranked = opr.rank_opportunities(cands)
    assert len(ranked) == 3
    assert {r.symbol for r in ranked} == {"XAUUSD", "WTIUSD", "BTCUSD"}


def test_rank_opportunities_carries_through_risk_budget_and_session_unmodified():
    c = _cand(symbol="XAUUSD", risk_budget_remaining_pct=1.25, session="London",
              grade_letter="A")
    ranked = opr.rank_opportunities([c])
    assert ranked[0].risk_budget_remaining_pct == 1.25
    assert ranked[0].session == "London"
    assert ranked[0].grade_letter == "A"


def test_rank_opportunities_single_candidate_ranks_first():
    ranked = opr.rank_opportunities([_cand()])
    assert len(ranked) == 1
    assert ranked[0].rank == 1


# --------------------------------------------------------------------------
# candidate_from_alert_signals_context -- adapter over real upstream shapes
# --------------------------------------------------------------------------

class _FakeAssessment:
    def __init__(self, overall_confidence=72, calibrated_probability=None, is_calibrated=False):
        self.overall_confidence = overall_confidence
        self.calibrated_probability = calibrated_probability
        self.is_calibrated = is_calibrated


class _FakeConfluenceRead:
    def __init__(self, score=68):
        self.score = score


def test_candidate_from_alert_signals_context_full_inputs():
    assessment = _FakeAssessment(overall_confidence=72, calibrated_probability=0.7,
                                 is_calibrated=True)
    cr = _FakeConfluenceRead(score=68)
    mkt_regime = {"quality_score": 55}
    pr_verdict = {"detail": {"risk_budget_remaining_pct": 3.4}}
    c = opr.candidate_from_alert_signals_context(
        "XAUUSD", "long", assessment=assessment, cr=cr, mkt_regime=mkt_regime,
        pr_verdict=pr_verdict, session="NY", grade_letter="A+")
    assert c.symbol == "XAUUSD"
    assert c.overall_confidence == 72
    assert c.calibrated_probability == 0.7
    assert c.is_calibrated is True
    assert c.confluence_score == 68
    assert c.regime_quality == 55
    assert c.risk_budget_remaining_pct == 3.4
    assert c.session == "NY"
    assert c.grade_letter == "A+"


def test_candidate_from_alert_signals_context_missing_optional_inputs():
    """assessment=None, cr=None, pr_verdict=None (all legitimate at various
    pipeline stages) must degrade to safe defaults, not raise."""
    c = opr.candidate_from_alert_signals_context(
        "WTIUSD", "short", assessment=None, cr=None, mkt_regime=None, pr_verdict=None)
    assert c.overall_confidence == 0
    assert c.confluence_score == 0
    assert c.regime_quality == 0
    assert c.risk_budget_remaining_pct is None
    assert c.is_calibrated is False


def test_candidate_from_alert_signals_context_feeds_into_ranking_end_to_end():
    """No mocking: builds real OpportunityCandidate objects via the adapter
    from fake-but-realistically-shaped upstream objects, then ranks them --
    confirms the adapter's output is actually consumable by
    rank_opportunities() without any glue code."""
    strong = opr.candidate_from_alert_signals_context(
        "XAUUSD", "long", assessment=_FakeAssessment(overall_confidence=88),
        cr=_FakeConfluenceRead(score=90), mkt_regime={"quality_score": 85})
    weak = opr.candidate_from_alert_signals_context(
        "WTIUSD", "short", assessment=_FakeAssessment(overall_confidence=45),
        cr=_FakeConfluenceRead(score=50), mkt_regime={"quality_score": 40})
    ranked = opr.rank_opportunities([weak, strong])
    assert ranked[0].symbol == "XAUUSD"
    assert ranked[0].rank == 1
    assert ranked[1].symbol == "WTIUSD"
