"""Offline tests for engine/evidence_tiers.py (Day 9)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import evidence_tiers as et  # noqa: E402


def test_tiers_ordered_ascending_by_floor():
    floors = [f for _, f, _ in et.TIERS]
    assert floors == sorted(floors)


def test_evidence_tier_boundaries():
    assert et.evidence_tier(0) == "research_observation"
    assert et.evidence_tier(4) == "research_observation"
    assert et.evidence_tier(5) == "exploratory_evidence"
    assert et.evidence_tier(14) == "exploratory_evidence"
    assert et.evidence_tier(15) == "preliminary_evidence"
    assert et.evidence_tier(29) == "preliminary_evidence"
    assert et.evidence_tier(30) == "moderate_confidence"
    assert et.evidence_tier(99) == "moderate_confidence"
    assert et.evidence_tier(100) == "production_ready_evidence"
    assert et.evidence_tier(10_000) == "production_ready_evidence"


def test_assess_no_context_is_provisional():
    out = et.assess(50)
    assert out["size_only_tier"] == "moderate_confidence"
    assert out["effective_tier"] == "moderate_confidence"
    assert out["downgraded"] is False
    assert len(out["caveats"]) == 2   # representativeness + consistency both unassessed


def test_assess_full_context_no_caveats():
    out = et.assess(50, representative=True, consistent_sign=True)
    assert out["caveats"] == []
    assert out["downgraded"] is False


def test_assess_downgraded_when_not_representative():
    out = et.assess(150, representative=False, consistent_sign=True)
    assert out["size_only_tier"] == "production_ready_evidence"
    assert out["effective_tier"] == "preliminary_evidence"
    assert out["downgraded"] is True


def test_assess_downgraded_when_not_consistent():
    out = et.assess(150, representative=True, consistent_sign=False)
    assert out["effective_tier"] == "preliminary_evidence"
    assert out["downgraded"] is True


def test_assess_double_downgrade_still_floors_at_preliminary():
    """Large n with BOTH failures shouldn't drop below preliminary — a
    non-representative, inconsistent sample is still worth SOMETHING
    (an exploratory flag), not zero."""
    out = et.assess(150, representative=False, consistent_sign=False)
    assert out["effective_tier"] == "preliminary_evidence"


def test_assess_small_n_cannot_be_upgraded_by_good_context():
    """Sample size is a genuine floor — good representativeness/
    consistency cannot promote a tiny sample past its size-only tier."""
    out = et.assess(3, representative=True, consistent_sign=True)
    assert out["effective_tier"] == "research_observation"
    assert out["downgraded"] is False


def test_assess_never_raises_on_garbage():
    out = et.assess("not-a-number")
    assert isinstance(out, dict)
    assert "effective_tier" in out


def test_assess_includes_notes():
    out = et.assess(10, notes="from paper trading batch #3")
    assert out["notes"] == "from paper trading batch #3"
