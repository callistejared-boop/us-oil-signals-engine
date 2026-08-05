"""Offline tests for alert_signals.apply_regime_gate() (Day 4 Phase 6
integration point). Extracted as its own pure function so it's testable
without driving alert_signals.main() (live fetch, Telegram, journal I/O),
mirroring the same pattern used for hourly_briefing.apply_risk_gate() in
Day 3.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import alert_signals as als  # noqa: E402


def _regime(quality=75, primary="Strong Bull Trend", compat="preferred"):
    return {"quality_score": quality, "primary": primary, "compatibility": compat}


def test_advisory_mode_never_blocks_regardless_of_quality():
    blocked, note = als.apply_regime_gate(_regime(quality=0), "advisory", 30)
    assert blocked is False and note == ""


def test_block_mode_allows_when_quality_at_or_above_threshold():
    blocked, note = als.apply_regime_gate(_regime(quality=30), "block", 30)
    assert blocked is False


def test_block_mode_blocks_when_quality_below_threshold():
    blocked, note = als.apply_regime_gate(_regime(quality=10, primary="Range"), "block", 30)
    assert blocked is True
    assert "10" in note and "30" in note and "Range" in note


def test_unknown_mode_string_treated_as_non_blocking():
    blocked, note = als.apply_regime_gate(_regime(quality=0), "not_a_real_mode", 30)
    assert blocked is False


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)
