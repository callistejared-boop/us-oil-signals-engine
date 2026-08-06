"""Tests for engine/strategy_registry.py (V2.2 — Strategy Registry).
Covers strategy_for() lookup/fallback and execution_style_for()'s
three-step resolution order (registry entry -> settings.execution_style
-> hardcoded "day" default), plus fail-safe behavior on malformed input.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import strategy_registry as sr  # noqa: E402
from engine import config  # noqa: E402


def test_strategy_for_known_id():
    entry = sr.strategy_for("ict_smc_mast")
    assert entry["strategy_id"] == "ict_smc_mast"
    assert entry["style"] == "day"
    assert entry["strategy_id_requested"] == "ict_smc_mast"


def test_strategy_for_unknown_id_falls_back_to_default():
    entry = sr.strategy_for("nonexistent_strategy")
    assert entry["strategy_id"] == sr.DEFAULT_STRATEGY_ID
    assert entry["strategy_id_requested"] == "nonexistent_strategy"


def test_strategy_for_none_falls_back_to_default():
    entry = sr.strategy_for(None)
    assert entry["strategy_id"] == sr.DEFAULT_STRATEGY_ID
    assert entry["strategy_id_requested"] is None


def test_execution_style_for_known_strategy_uses_registry_style():
    s = config.Settings()
    s.execution_style = "scalping"  # should be ignored: known id wins
    assert sr.execution_style_for("ict_smc_mast", settings=s) == "day"


def test_execution_style_for_unknown_strategy_falls_back_to_settings():
    s = config.Settings()
    s.execution_style = "swing"
    assert sr.execution_style_for("some_future_strategy", settings=s) == "swing"


def test_execution_style_for_no_strategy_id_falls_back_to_settings():
    s = config.Settings()
    s.execution_style = "scalping"
    assert sr.execution_style_for(None, settings=s) == "scalping"


def test_execution_style_for_no_strategy_id_no_settings_defaults_to_day():
    assert sr.execution_style_for(None, settings=None) == "day"


def test_execution_style_for_unknown_strategy_no_settings_defaults_to_day():
    assert sr.execution_style_for("unknown", settings=None) == "day"


def test_execution_style_for_settings_missing_execution_style_attr():
    class Empty:
        pass
    assert sr.execution_style_for(None, settings=Empty()) == "day"


def test_execution_style_for_never_raises_on_malformed_settings():
    assert sr.execution_style_for(None, settings=object()) == "day"


def test_strategy_for_never_mutates_strategies_table():
    entry = sr.strategy_for("ict_smc_mast")
    entry["style"] = "mutated"
    assert sr.STRATEGIES["ict_smc_mast"]["style"] == "day"


def test_config_execution_style_still_the_documented_default():
    # Regression guard: strategy_registry's fallback chain assumes
    # config.Settings().execution_style defaults to "day" (V2.2 Item 3).
    assert config.Settings().execution_style == "day"
