"""Integration tests: engine/execution/execution_report.py's `style`
parameter (V2.2 Priority 1 Item 3) - confirms build_trade_execution_
report() attaches an execution_profile_evaluation when style is given,
stays byte-for-byte backward compatible (None) when it isn't, and that
engine.config's new execution_style setting round-trips.
"""
import pathlib
import random
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.execution import execution_report as er  # noqa: E402
from engine import config  # noqa: E402

TS = pd.Timestamp("2026-08-03 08:00:00")


def test_style_none_by_default_no_evaluation_attached():
    rep = er.build_trade_execution_report("XAUUSD", "long", 2350.0, stop_price=2340.0,
                                          signal_ts=TS, rng=random.Random(1))
    assert rep["execution_profile_evaluation"] is None


def test_style_given_attaches_evaluation():
    rep = er.build_trade_execution_report("XAUUSD", "long", 2350.0, stop_price=2340.0,
                                          signal_ts=TS, rng=random.Random(1), style="scalping")
    ev = rep["execution_profile_evaluation"]
    assert ev is not None
    assert ev["style"] == "scalping"
    assert "checks" in ev


def test_style_does_not_change_existing_fields():
    rng_seed = 7
    rep_no_style = er.build_trade_execution_report(
        "XAUUSD", "long", 2350.0, stop_price=2340.0, signal_ts=TS, rng=random.Random(rng_seed))
    rep_with_style = er.build_trade_execution_report(
        "XAUUSD", "long", 2350.0, stop_price=2340.0, signal_ts=TS, rng=random.Random(rng_seed),
        style="day")
    # Same seed -> identical simulated fill; only the new key should differ.
    for key in rep_no_style:
        if key == "execution_profile_evaluation":
            continue
        assert rep_no_style[key] == rep_with_style[key], f"field {key} diverged"


def test_style_swing_more_tolerant_than_scalping_same_fill():
    rng_seed = 3
    scalp_ev = er.build_trade_execution_report(
        "XAUUSD", "long", 2350.0, stop_price=2340.0, signal_ts=TS, rng=random.Random(rng_seed),
        style="scalping")["execution_profile_evaluation"]
    swing_ev = er.build_trade_execution_report(
        "XAUUSD", "long", 2350.0, stop_price=2340.0, signal_ts=TS, rng=random.Random(rng_seed),
        style="swing")["execution_profile_evaluation"]
    # Same underlying fill (same seed) — swing's looser tolerances must
    # never be MORE likely to fail than scalping's tighter ones for any
    # single dimension.
    for dim in scalp_ev["checks"]:
        if scalp_ev["checks"][dim]["within_tolerance"]:
            assert swing_ev["checks"][dim]["within_tolerance"], (
                f"{dim} passed scalping but failed swing — tolerances inverted")


def test_config_execution_style_default_is_day():
    s = config.Settings()
    assert s.execution_style == "day"


def test_config_execution_style_overridable_via_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("EXECUTION_STYLE=scalping\n")
    s = config.load(env)
    assert s.execution_style == "scalping"
