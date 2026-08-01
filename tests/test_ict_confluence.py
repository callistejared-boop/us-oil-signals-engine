"""Offline tests for the new ICT confluences (sweep/displacement/OTE/OB)."""
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import ict_confluence as icf  # noqa: E402
from engine import structure as st        # noqa: E402


def _df(rows):
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"])
    df["Volume"] = 0.0
    df.index = pd.date_range("2026-07-01", periods=len(df), freq="15min")
    return df


def _base(n=100, price=80.0, amp=0.5):
    """Gently oscillating series with a clear swing low near the middle."""
    rows = []
    for i in range(n):
        c = price + amp * np.sin(i / 6)
        rows.append([c, c + 0.15, c - 0.15, c + 0.02])
    return rows


def test_sweep_detects_stop_hunt_long():
    rows = _base(100)
    # bar 95 dives BELOW every prior low then closes back inside: stop hunt
    lo = min(r[2] for r in rows[:84]) - 0.5
    rows[95] = [80.0, 80.2, lo, 80.1]
    ok, lvl, ago = icf.liquidity_sweep(_df(rows), "long", lookback=96, recent=16)
    assert ok and lvl is not None and ago is not None


def test_sweep_ignores_clean_breakdown():
    rows = _base(100)
    lo = min(r[2] for r in rows[:84]) - 0.5
    rows[95] = [80.0, 80.0, lo, lo + 0.01]   # closes BELOW the level: breakdown, not sweep
    # close must be back above the swept level to count
    ok, _, _ = icf.liquidity_sweep(_df(rows), "long", lookback=96, recent=16)
    # the dive bar closed under all prior lows -> no reclaim -> no sweep
    assert not ok


def test_sweep_short_mirror():
    rows = _base(100)
    hi = max(r[1] for r in rows[:84]) + 0.5
    rows[95] = [80.0, hi, 79.9, 79.95]        # spike above, close back under
    ok, _, _ = icf.liquidity_sweep(_df(rows), "short", lookback=96, recent=16)
    assert ok


def test_displacement_requires_impulse():
    # weak drift gap: tiny middle candle -> reject
    weak = _df([[80, 80.1, 79.9, 80.05], [80.05, 80.15, 80.0, 80.1],
                [80.3, 80.5, 80.25, 80.45]])
    gaps = st.find_fvgs(weak)
    assert gaps and not icf.displacement(weak, gaps[0], atr15=0.2)
    # impulse gap: big-bodied middle candle -> accept
    strong = _df([[80, 80.1, 79.9, 80.05], [80.05, 80.9, 80.0, 80.85],
                  [80.95, 81.3, 80.92, 81.2]])
    gaps2 = st.find_fvgs(strong)
    assert gaps2 and icf.displacement(strong, gaps2[0], atr15=0.2)


def test_ote_textbook_zones():
    # range 70..80 (R=10): long OTE = 72.1..73.8 ; short OTE = 76.2..77.9
    assert icf.in_ote(73.0, 80, 70, "long")
    assert not icf.in_ote(76.5, 80, 70, "long")
    assert icf.in_ote(77.0, 80, 70, "short")
    assert not icf.in_ote(72.0, 80, 70, "short")
    assert not icf.in_ote(73.0, 70, 80, "long")  # inverted range -> False


def test_failsafe():
    assert icf.liquidity_sweep(None, "long") == (False, None, None)
    assert icf.displacement(None, None, None) is False
    assert icf.ob_confluence(None, "long", 1, 0) is False


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok ", fn.__name__)
    print(f"\n{len(fns)}/{len(fns)} ict-confluence tests passed")
