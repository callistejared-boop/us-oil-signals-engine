"""Offline tests for the fourth pass: Elliott Wave rule-validation
(engine/elliott_wave.py) and ICC -- Indication/Correction/Continuation
(engine/icc.py). Both requested explicitly by the user; neither was taught
with operational specifics by any of the 8 uploaded documents (Elliott
Wave wasn't covered at all; ICC's source document is templated
boilerplate), so both are standard/plain-language implementations, said
plainly in their own module docstrings. All pure OHLC math, no network.
"""
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import elliott_wave as ew   # noqa: E402
from engine import icc                  # noqa: E402


def _bars(n, freq="15min"):
    return pd.date_range("2026-01-01", periods=n, freq=freq)


# ------------------------------------------------------------- Elliott Wave
def _valid_impulse_df():
    """Constructs a clean bullish 5-wave impulse: P0=100 (low), P1=110 (w1),
    P2=104 (w2, > P0), P3=122 (w3, biggest leg), P4=115 (w4, > P1=110, no
    overlap), P5=128 (w5). All rules should pass. A short lead-in above P0
    is prepended so P0 itself registers as a confirmed swing (find_swings
    can never confirm a swing at the very first bar of a series -- it
    needs neighbours on both sides)."""
    pts = [105, 100, 110, 104, 122, 115, 128]
    n = 10 * (len(pts) - 1) + 5
    idx = _bars(n)
    o = np.zeros(n); h = np.zeros(n); l = np.zeros(n); c = np.zeros(n)
    pos = 0
    for i in range(len(pts) - 1):
        start, end = pts[i], pts[i + 1]
        for k in range(10):
            t = (k + 1) / 10
            v = start + (end - start) * t
            o[pos] = v - 0.1 if end > start else v + 0.1
            c[pos] = v
            h[pos] = max(o[pos], c[pos]) + 0.15
            l[pos] = min(o[pos], c[pos]) - 0.15
            pos += 1
    for k in range(5):
        o[pos], c[pos] = pts[-1], pts[-1] - 0.05
        h[pos], l[pos] = pts[-1] + 0.1, pts[-1] - 0.2
        pos += 1
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=idx[:pos])


def test_validate_impulse_accepts_clean_rule_valid_sequence():
    from engine.structure import Swing
    pts = [Swing(0, 0, 100, "L"), Swing(1, 1, 110, "H"), Swing(2, 2, 104, "L"),
           Swing(3, 3, 122, "H"), Swing(4, 4, 115, "L"), Swing(5, 5, 128, "H")]
    out = ew.validate_impulse(pts, "long")
    assert out["valid"] is True
    assert out["failed_rules"] == []


def test_validate_impulse_rejects_wave2_over_retracement():
    from engine.structure import Swing
    # P2 (99) below P0 (100) -> rule 1 violated
    pts = [Swing(0, 0, 100, "L"), Swing(1, 1, 110, "H"), Swing(2, 2, 99, "L"),
           Swing(3, 3, 122, "H"), Swing(4, 4, 115, "L"), Swing(5, 5, 128, "H")]
    out = ew.validate_impulse(pts, "long")
    assert out["valid"] is False
    assert any("rule1" in r for r in out["failed_rules"])


def test_validate_impulse_rejects_wave4_overlap():
    from engine.structure import Swing
    # P4 (108) below P1 (110) -> overlaps wave-1 territory, rule 3 violated
    pts = [Swing(0, 0, 100, "L"), Swing(1, 1, 110, "H"), Swing(2, 2, 104, "L"),
           Swing(3, 3, 122, "H"), Swing(4, 4, 108, "L"), Swing(5, 5, 128, "H")]
    out = ew.validate_impulse(pts, "long")
    assert out["valid"] is False
    assert any("rule3" in r for r in out["failed_rules"])


def test_validate_impulse_rejects_wave3_shortest():
    from engine.structure import Swing
    # wave3 (P3-P2 = 2) shorter than wave1 (10) and wave5 (13) -> rule 2 violated
    pts = [Swing(0, 0, 100, "L"), Swing(1, 1, 110, "H"), Swing(2, 2, 104, "L"),
           Swing(3, 3, 106, "H"), Swing(4, 4, 102, "L"), Swing(5, 5, 115, "H")]
    out = ew.validate_impulse(pts, "long")
    assert out["valid"] is False
    assert any("rule2" in r for r in out["failed_rules"])


def test_detect_finds_valid_impulse_on_constructed_data():
    df = _valid_impulse_df()
    out = ew.detect(df)
    assert out["impulse"] == "long"
    assert out["expected_correction"] == "short"


def test_elliott_alignment_matches_expected_correction():
    df = _valid_impulse_df()
    out = ew.alignment(df, "short")
    assert out["supports"] is True
    out2 = ew.alignment(df, "long")
    assert out2["supports"] is False


def test_elliott_no_crash_on_random_noise():
    idx = _bars(300)
    rng = np.random.default_rng(11)
    px = 70 + np.cumsum(rng.normal(0, 0.05, 300))
    df = pd.DataFrame({"Open": px, "High": px + 0.1, "Low": px - 0.1, "Close": px}, index=idx)
    out = ew.alignment(df, "long")
    assert out["supports"] in (None, True, False)


def test_elliott_no_crash_on_too_few_bars():
    idx = _bars(5)
    df = pd.DataFrame({"Open": 100.0, "High": 100.5, "Low": 99.5, "Close": 100.0}, index=idx)
    out = ew.alignment(df, "long")
    assert out["supports"] is None


# ------------------------------------------------------------------------ ICC
def _icc_continuation_df():
    """P0=100(L) -> P1=110(H) indication long, correction to P2=105(L)
    (between P0 and P1), then price closes just above P1=110 -> live
    continuation read (deliberately only 2-3 bars past P1, not enough for
    that push itself to confirm as a 4th swing -- ICC is designed to catch
    continuation on a closing basis before a new swing point confirms,
    same as this codebase's other close-based breakout checks). Lead-in
    above P0 for the same find_swings boundary reason as the impulse test."""
    pts = [106, 100, 110, 105]
    n = 10 * (len(pts) - 1) + 3
    idx = _bars(n)
    o = np.zeros(n); h = np.zeros(n); l = np.zeros(n); c = np.zeros(n)
    pos = 0
    for i in range(len(pts) - 1):
        start, end = pts[i], pts[i + 1]
        for k in range(10):
            t = (k + 1) / 10
            v = start + (end - start) * t
            o[pos] = v - 0.1 if end > start else v + 0.1
            c[pos] = v
            h[pos] = max(o[pos], c[pos]) + 0.15
            l[pos] = min(o[pos], c[pos]) - 0.15
            pos += 1
    # short continuation push: closes above P1 (110) but stays only 3 bars,
    # not enough for find_swings (k=2) to confirm a new swing there yet
    for k in range(3):
        v = 111.0 + k * 0.3
        o[pos], c[pos] = v - 0.1, v
        h[pos], l[pos] = v + 0.1, v - 0.2
        pos += 1
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=idx[:pos])


def test_icc_read_detects_continuation_phase():
    df = _icc_continuation_df()
    out = icc.read(df)
    assert out["direction"] == "long"
    assert out["phase"] == "continuation"


def test_icc_alignment_matches_continuation_direction():
    df = _icc_continuation_df()
    assert icc.alignment(df, "long")["supports"] is True
    assert icc.alignment(df, "short")["supports"] is False


def test_icc_no_crash_on_random_noise():
    idx = _bars(200)
    rng = np.random.default_rng(13)
    px = 70 + np.cumsum(rng.normal(0, 0.05, 200))
    df = pd.DataFrame({"Open": px, "High": px + 0.1, "Low": px - 0.1, "Close": px}, index=idx)
    out = icc.alignment(df, "long")
    assert out["supports"] in (None, True, False)


def test_icc_no_crash_on_too_few_bars():
    idx = _bars(5)
    df = pd.DataFrame({"Open": 100.0, "High": 100.5, "Low": 99.5, "Close": 100.0}, index=idx)
    out = icc.alignment(df, "long")
    assert out["supports"] is None


# ----------------------------------------------------------------- wiring
def test_confluence_survives_gap4_layers_offline():
    from engine import confluence as cf

    rows = []
    px = 70.0
    for i in range(1200):
        px += 0.05 + np.random.default_rng(i).normal(0, 0.05)
        rows.append([px - 0.1, px + 0.15, px - 0.15, px])
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"])
    df["Volume"] = 0.0
    df.index = pd.date_range("2026-01-01", periods=len(df), freq="15min")

    out = cf.analyze(df, symbol="WTIUSD")
    if out is not None:
        assert "elliott_wave" in out.layers
        assert "icc" in out.layers
        names = [c[0] for c in out.checklist]
        assert "Elliott Wave" in names
        assert "ICC (Indication/Correction/Continuation)" in names


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok ", fn.__name__)
    print(f"\n{len(fns)}/{len(fns)} gap4 tests passed")
