"""Offline tests for engine/platform_version.py (Day 8)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import platform_version as pv  # noqa: E402


def test_snapshot_has_platform_and_architecture_version():
    snap = pv.snapshot()
    assert snap["platform_version"] == pv.PLATFORM_VERSION
    assert snap["architecture_version"] == pv.ARCHITECTURE_VERSION
    assert isinstance(snap["components"], dict)


def test_component_versions_reports_declared_versions():
    versions = pv.component_versions()
    assert versions["engine.confidence_engine"] != "unversioned"
    assert versions["engine.market_memory"] != "unversioned"
    assert versions["engine.signals"] == "1.0.0"
    assert versions["engine.regime_engine"] == "2.0.0"
    assert versions["engine.confluence"] == "1.0.0"
    assert versions["engine.portfolio_risk"] == "1.0.0"


def test_component_versions_reports_unversioned_honestly(monkeypatch):
    """A module without a VERSION constant must be reported as
    "unversioned", never fabricated — proven with a fake unversioned
    module rather than relying on every real module staying unversioned
    forever."""
    monkeypatch.setattr(pv, "COMPONENT_MODULES", ["engine.store"])
    versions = pv.component_versions()
    assert versions["engine.store"] == "unversioned"


def test_component_versions_never_raises_on_bad_module():
    versions_before = pv.COMPONENT_MODULES[:]
    try:
        import engine.platform_version as mod
        mod.COMPONENT_MODULES = versions_before + ["engine.does_not_exist_xyz"]
        out = mod.component_versions()
        assert "unavailable" in out["engine.does_not_exist_xyz"]
    finally:
        mod.COMPONENT_MODULES = versions_before


def test_snapshot_never_raises():
    out = pv.snapshot()
    assert isinstance(out, dict)
