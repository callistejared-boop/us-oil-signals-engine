import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.data_health import registry as reg  # noqa: E402


def test_default_registry_populated_at_import():
    ids = reg.feed_ids()
    assert len(ids) >= 15
    assert "market_data:XAUUSD" in ids
    assert "rates_feed" in ids
    assert "scan_loop_heartbeat" in ids
    assert "dashboard_publish" in ids


def test_get_returns_none_for_unknown_feed():
    assert reg.get("does_not_exist") is None


def test_validate_registry_ok_on_default_registry():
    result = reg.validate_registry()
    assert result["ok"] is True
    assert result["errors"] == []
    assert result["feed_count"] == len(reg.feed_ids())


def test_validate_registry_catches_hidden_dependency(registry_sandbox):
    from engine.data_health.registry import FeedSpec
    registry_sandbox.register(FeedSpec(
        feed_id="fake_feed", provider="p", purpose="purpose",
        category="macro", dependency_ids=("not_registered_anywhere",),
    ))
    result = registry_sandbox.validate_registry()
    assert result["ok"] is False
    assert any("not_registered_anywhere" in e for e in result["errors"])


def test_validate_registry_catches_missing_provider_or_purpose(registry_sandbox):
    from engine.data_health.registry import FeedSpec
    registry_sandbox.register(FeedSpec(feed_id="bad_feed", provider="", purpose="", category="macro"))
    result = registry_sandbox.validate_registry()
    assert result["ok"] is False
    assert any("bad_feed" in e for e in result["errors"])


def test_validate_registry_detects_circular_dependency(registry_sandbox):
    from engine.data_health.registry import FeedSpec
    registry_sandbox.register(FeedSpec(feed_id="a", provider="p", purpose="x", category="macro",
                                        dependency_ids=("b",)))
    registry_sandbox.register(FeedSpec(feed_id="b", provider="p", purpose="x", category="macro",
                                        dependency_ids=("a",)))
    result = registry_sandbox.validate_registry()
    assert result["ok"] is False
    assert any("circular" in e for e in result["errors"])


def test_dependents_of_finds_direct_dependents():
    dependents = reg.dependents_of("news_calendar")
    assert "macro_calendar" in dependents


def test_dependency_chain_transitive(registry_sandbox):
    from engine.data_health.registry import FeedSpec
    registry_sandbox.register(FeedSpec(feed_id="x1", provider="p", purpose="x", category="macro"))
    registry_sandbox.register(FeedSpec(feed_id="x2", provider="p", purpose="x", category="macro",
                                        dependency_ids=("x1",)))
    registry_sandbox.register(FeedSpec(feed_id="x3", provider="p", purpose="x", category="macro",
                                        dependency_ids=("x2",)))
    chain = registry_sandbox.dependency_chain("x3")
    assert "x2" in chain and "x1" in chain


def test_dependency_chain_cycle_safe(registry_sandbox):
    from engine.data_health.registry import FeedSpec
    registry_sandbox.register(FeedSpec(feed_id="c1", provider="p", purpose="x", category="macro",
                                        dependency_ids=("c2",)))
    registry_sandbox.register(FeedSpec(feed_id="c2", provider="p", purpose="x", category="macro",
                                        dependency_ids=("c1",)))
    # must terminate, not infinite-loop
    chain = registry_sandbox.dependency_chain("c1")
    assert "c2" in chain


def test_register_never_raises_on_bad_input():
    # register() should not raise even if given garbage
    reg.register(None)  # type: ignore[arg-type]


def test_configured_check_eia_feed_reflects_settings():
    class FakeSettings:
        eia_api_key = ""
    assert reg._configured("eia_feed", FakeSettings()) is False

    class FakeSettingsConfigured:
        eia_api_key = "abc123"
    assert reg._configured("eia_feed", FakeSettingsConfigured()) is True


def test_configured_check_returns_none_when_not_applicable():
    class FakeSettings:
        pass
    assert reg._configured("rates_feed", FakeSettings()) is None


def test_configured_check_never_raises_on_bad_settings():
    # object() has no eia_api_key attribute; getattr(..., "") defaults to
    # "" rather than raising, so this correctly reports "not configured"
    # (False), not an unknown (None) — the check itself never raises.
    assert reg._configured("eia_feed", object()) is False


def test_every_feed_has_provider_and_purpose():
    for spec in reg.all_feeds():
        assert spec.provider, f"{spec.feed_id} missing provider"
        assert spec.purpose, f"{spec.feed_id} missing purpose"


def test_market_data_feeds_registered_for_every_symbol():
    from engine.markets import MARKETS
    for symbol in MARKETS:
        assert reg.get(f"market_data:{symbol}") is not None
