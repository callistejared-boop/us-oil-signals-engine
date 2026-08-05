import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.data_health import provider_status as ps  # noqa: E402
from engine.data_health import freshness as fr  # noqa: E402
from engine.data_health import completeness as comp  # noqa: E402


def test_classify_all_healthy_is_operational():
    result = ps.classify("f1", freshness_state=fr.FRESH)
    assert result["status"] == ps.OPERATIONAL
    assert result["confidence"] == "high"
    assert result["reasons"] == []


def test_classify_aging_freshness_is_degraded():
    result = ps.classify("f1", freshness_state=fr.AGING)
    assert result["status"] == ps.DEGRADED


def test_classify_stale_freshness_is_partial():
    result = ps.classify("f1", freshness_state=fr.STALE)
    assert result["status"] == ps.PARTIAL


def test_classify_expired_freshness_is_unavailable():
    result = ps.classify("f1", freshness_state=fr.EXPIRED)
    assert result["status"] == ps.UNAVAILABLE


def test_classify_unknown_freshness_is_degraded_low_confidence():
    result = ps.classify("f1", freshness_state=fr.UNKNOWN)
    assert result["status"] == ps.DEGRADED
    assert result["confidence"] == "low"


def test_classify_not_configured_is_unavailable():
    result = ps.classify("f1", freshness_state=fr.FRESH, configured=False)
    assert result["status"] == ps.UNAVAILABLE
    assert any("not configured" in r for r in result["reasons"])


def test_classify_worst_of_multiple_checks_wins():
    result = ps.classify("f1", freshness_state=fr.FRESH,
                          completeness_severity=comp.MINOR,
                          consistency_severity=comp.CRITICAL,
                          anomaly_severity=comp.NONE_)
    assert result["status"] == ps.UNAVAILABLE


def test_classify_critical_completeness_alone_is_unavailable():
    result = ps.classify("f1", freshness_state=fr.FRESH, completeness_severity=comp.CRITICAL)
    assert result["status"] == ps.UNAVAILABLE


def test_classify_recommended_action_present_for_every_status():
    for state in (fr.FRESH, fr.AGING, fr.STALE, fr.EXPIRED):
        result = ps.classify("f1", freshness_state=state)
        assert result["recommended_action"]


def test_classify_never_raises():
    # deliberately pass a garbage freshness_state
    result = ps.classify("f1", freshness_state="not_a_real_state")
    assert result["status"] in (ps.OPERATIONAL, ps.DEGRADED, ps.PARTIAL, ps.UNAVAILABLE)


def test_apply_dependency_cascade_degrades_dependent(registry_sandbox):
    from engine.data_health.registry import FeedSpec
    registry_sandbox.register(FeedSpec(feed_id="upstream", provider="p", purpose="x", category="macro"))
    registry_sandbox.register(FeedSpec(feed_id="downstream", provider="p", purpose="x", category="macro",
                                        dependency_ids=("upstream",)))
    statuses = {
        "upstream": ps.classify("upstream", freshness_state=fr.EXPIRED),
        "downstream": ps.classify("downstream", freshness_state=fr.FRESH),
    }
    assert statuses["downstream"]["status"] == ps.OPERATIONAL  # before cascade
    cascaded = ps.apply_dependency_cascade(statuses)
    assert cascaded["downstream"]["status"] == ps.UNAVAILABLE  # after cascade
    assert any("cascaded from dependency" in r for r in cascaded["downstream"]["reasons"])


def test_apply_dependency_cascade_never_downgrades_healthy_dependency(registry_sandbox):
    from engine.data_health.registry import FeedSpec
    registry_sandbox.register(FeedSpec(feed_id="upstream2", provider="p", purpose="x", category="macro"))
    registry_sandbox.register(FeedSpec(feed_id="downstream2", provider="p", purpose="x", category="macro",
                                        dependency_ids=("upstream2",)))
    statuses = {
        "upstream2": ps.classify("upstream2", freshness_state=fr.FRESH),
        "downstream2": ps.classify("downstream2", freshness_state=fr.EXPIRED),
    }
    cascaded = ps.apply_dependency_cascade(statuses)
    # downstream2's own worse status should not be improved by a healthy upstream
    assert cascaded["downstream2"]["status"] == ps.UNAVAILABLE


def test_apply_dependency_cascade_never_raises_on_missing_dep():
    statuses = {"lonely": ps.classify("lonely", freshness_state=fr.FRESH)}
    cascaded = ps.apply_dependency_cascade(statuses)
    assert cascaded["lonely"]["status"] == ps.OPERATIONAL


def test_affected_subsystems_real_registry():
    affected = ps.affected_subsystems("news_calendar")
    assert "macro_calendar" in affected


def test_affected_subsystems_transitive(registry_sandbox):
    from engine.data_health.registry import FeedSpec
    registry_sandbox.register(FeedSpec(feed_id="root", provider="p", purpose="x", category="macro"))
    registry_sandbox.register(FeedSpec(feed_id="mid", provider="p", purpose="x", category="macro",
                                        dependency_ids=("root",)))
    registry_sandbox.register(FeedSpec(feed_id="leaf", provider="p", purpose="x", category="macro",
                                        dependency_ids=("mid",)))
    affected = ps.affected_subsystems("root")
    assert "mid" in affected and "leaf" in affected


def test_affected_subsystems_empty_for_leaf_feed():
    affected = ps.affected_subsystems("scan_loop_heartbeat")
    assert affected == ()
