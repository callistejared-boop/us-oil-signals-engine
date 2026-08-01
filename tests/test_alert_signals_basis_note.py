"""Regression test for the 2026-07-31 fix to alert_signals.build_entry().

Before this fix, build_entry() quoted a module-level BASIS_NOTE constant
hardcoded to "levels from WTI futures (CL=F)" for every symbol — so a live
Telegram ENTRY alert for a gold or Bitcoin trade told the reader to check
the wrong futures contract's price. symbol_meta.py already carries the
correct per-symbol basis note (used by dashboard_publish.py and
wti_note.py); this test locks in that alert_signals.py now uses the same
source of truth instead of its own stale, oil-only copy.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import alert_signals as als  # noqa: E402
from engine import symbol_meta as sm  # noqa: E402


def _rec(symbol, direction="long"):
    return {"symbol": symbol, "direction": direction, "entry": 100.0,
            "stop": 99.0, "target": 103.0, "rr": 3.0, "invalidation": "n/a"}


def test_entry_note_uses_gold_basis_for_xauusd():
    text = als.build_entry(_rec("XAUUSD"), lt=None)
    assert sm.basis_note("XAUUSD") in text
    assert "WTI futures" not in text
    assert "CL=F" not in text


def test_entry_note_uses_btc_basis_for_btcusd():
    text = als.build_entry(_rec("BTCUSD"), lt=None)
    assert sm.basis_note("BTCUSD") in text
    assert "WTI futures" not in text
    assert "CL=F" not in text


def test_entry_note_still_uses_wti_basis_for_wtiusd():
    text = als.build_entry(_rec("WTIUSD"), lt=None)
    assert sm.basis_note("WTIUSD") in text
    assert "CL=F" in text  # WTI's own basis note legitimately mentions CL=F


def test_no_module_level_basis_note_constant_left_behind():
    """The old hardcoded constant should be gone entirely, not just unused."""
    assert not hasattr(als, "BASIS_NOTE")


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)
