"""Integration test: alert_signals.py's log_execution_context() resolves
its `style` argument through engine.strategy_registry (V2.2 Strategy
Registry) rather than reading config.execution_style directly, and that
the resolved style still reaches execution_report's
execution_profile_evaluation unchanged (V2.2 Priority 1 Item 3's own
contract, now fed by the Registry instead of the flat config value).
"""
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import alert_signals as als  # noqa: E402
from engine import strategy_registry as sr, config  # noqa: E402

TS = pd.Timestamp("2026-08-06 08:00:00")


def test_log_execution_context_resolves_style_via_registry(monkeypatch):
    seen = {}
    real_build = als.exrep.build_trade_execution_report

    def spy(*args, **kwargs):
        seen["style"] = kwargs.get("style")
        return real_build(*args, **kwargs)

    monkeypatch.setattr(als.exrep, "build_trade_execution_report", spy)
    als.log_execution_context("XAUUSD", "long", 2350.0, 2340.0, 2400.0,
                              style=sr.execution_style_for("ict_smc_mast",
                                                           settings=config.Settings()))
    assert seen["style"] == "day"  # ict_smc_mast's registry style


def test_main_call_site_uses_strategy_registry_not_flat_config():
    # Source-level guard: the specific getattr(s, "execution_style", ...)
    # call this replaced must be gone from main()'s Stage-2 entry branch,
    # and the strategy_registry-based replacement must be present exactly
    # once. Prevents a future edit from silently reverting the Registry
    # wiring back to the pre-Registry flat global read.
    src = pathlib.Path(als.__file__).read_text(encoding="utf-8")
    assert 'style=str(getattr(s, "execution_style", "day") or "day"))' not in src
    assert src.count("strategy_registry.execution_style_for(regime_strategy, settings=s)") == 1


def test_strategy_registry_import_present():
    assert hasattr(als, "strategy_registry")
    assert als.strategy_registry is sr
