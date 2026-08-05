import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.data_health import health_report as hr  # noqa: E402
from engine.data_health import provider_status as ps  # noqa: E402
from engine.data_health.registry import FeedSpec  # noqa: E402


def test_build_report_all_operational(registry_sandbox):
    registry_sandbox.reset()
    registry_sandbox.register(FeedSpec(feed_id="f1", provider="p", purpose="x", category="macro"))
    statuses = {"f1": ps.classify("f1", freshness_state="fresh")}
    report = hr.build_report(statuses, {"ok": True, "errors": []})
    assert report["overall_status"] == "operational"
    assert report["counts"]["operational"] == 1
    assert report["total_feeds"] == 1


def test_build_report_degraded_overall_when_any_issue(registry_sandbox):
    registry_sandbox.reset()
    registry_sandbox.register(FeedSpec(feed_id="f1", provider="p", purpose="x", category="macro"))
    registry_sandbox.register(FeedSpec(feed_id="f2", provider="p", purpose="x", category="macro"))
    statuses = {
        "f1": ps.classify("f1", freshness_state="fresh"),
        "f2": ps.classify("f2", freshness_state="stale"),
    }
    report = hr.build_report(statuses, {"ok": True, "errors": []})
    assert report["overall_status"] == "degraded"
    assert len(report["degraded_or_worse"]) == 1


def test_build_report_unavailable_overall_when_majority_down(registry_sandbox):
    registry_sandbox.reset()
    registry_sandbox.register(FeedSpec(feed_id="f1", provider="p", purpose="x", category="macro"))
    registry_sandbox.register(FeedSpec(feed_id="f2", provider="p", purpose="x", category="macro"))
    registry_sandbox.register(FeedSpec(feed_id="f3", provider="p", purpose="x", category="macro"))
    statuses = {
        "f1": ps.classify("f1", freshness_state="expired"),
        "f2": ps.classify("f2", freshness_state="expired"),
        "f3": ps.classify("f3", freshness_state="fresh"),
    }
    report = hr.build_report(statuses, {"ok": True, "errors": []})
    assert report["overall_status"] == "unavailable"


def test_build_report_empty_statuses_is_unavailable():
    report = hr.build_report({}, {"ok": True, "errors": []})
    assert report["overall_status"] == "unavailable"
    assert report["total_feeds"] == 0


def test_build_report_dependency_map_present(registry_sandbox):
    registry_sandbox.reset()
    registry_sandbox.register(FeedSpec(feed_id="root", provider="p", purpose="x", category="macro"))
    registry_sandbox.register(FeedSpec(feed_id="child", provider="p", purpose="x", category="macro",
                                        dependency_ids=("root",)))
    statuses = {
        "root": ps.classify("root", freshness_state="fresh"),
        "child": ps.classify("child", freshness_state="fresh"),
    }
    report = hr.build_report(statuses, {"ok": True, "errors": []})
    assert report["dependency_map"]["child"]["depends_on"] == ["root"]
    assert "child" in report["dependency_map"]["root"]["dependents"]


def test_build_report_never_raises_on_missing_spec():
    # a status entry for a feed_id that isn't in the registry at all
    statuses = {"ghost_feed": ps.classify("ghost_feed", freshness_state="fresh")}
    report = hr.build_report(statuses, {"ok": True, "errors": []})
    assert report["total_feeds"] == 1
    assert report["providers"][0]["feed_id"] == "ghost_feed"
    assert report["providers"][0]["provider"] is None


def test_build_report_includes_heartbeat_and_history():
    report = hr.build_report({}, {"ok": True, "errors": []},
                              heartbeat_record={"note": "x"}, recent_history=[{"a": 1}])
    assert report["heartbeat"] == {"note": "x"}
    assert report["recent_history"] == [{"a": 1}]


def test_build_report_note_mentions_advisory_only():
    report = hr.build_report({}, {"ok": True, "errors": []})
    assert "Advisory only" in report["note"]
