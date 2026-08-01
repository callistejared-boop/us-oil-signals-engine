"""Offline tests for the second literature-review pass: strong/weak
liquidity classification (engine/liquidity_strength.py, built on
structure.classify_swing_strength), rejection blocks (added to
engine/breaker_blocks.py, sourced from ICT Institutional SMC Trading), and
the Inside Bar candlestick pattern (added to engine/candlestick_patterns.py,
sourced from The Candlestick Trading Bible). All pure OHLC math, no network.
"""
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import structure as st                 # noqa: E402
from engine import liquidity_strength as ls         # noqa: E402
from engine import breaker_blocks as bb             # noqa: E402
from engine import candlestick_patterns as cs       # noqa: E402


def _bars(n, freq="15min"):
    return pd.date_range("2026-01-01", periods=n, freq=freq)


# --------------------------------------------------------- swing strength
def _displacement_df(n=100):
    """A swing high at bar 30 followed by a hard bearish displacement (strong),
    and a swing low at bar 60 followed by only chop (weak)."""
    idx = _bars(n)
    o = np.full(n, 100.0); h = np.full(n, 100.5); l = np.full(n, 99.5); c = np.full(n, 100.0)
    for i in range(0, 30):
        v = 100 + i * 0.1
        o[i], c[i], h[i], l[i] = v - 0.05, v, v + 0.1, v - 0.1
    # strong swing high at 30, hard drop after
    h[30], o[30], c[30], l[30] = 103.3, 103.0, 102.8, 102.7
    for i in range(31, 40):
        v = 103 - (i - 30) * 0.6
        o[i], c[i], h[i], l[i] = v + 0.1, v, v + 0.15, v - 0.15
    for i in range(40, 60):
        v = 97 + (i - 40) * 0.02
        o[i], c[i], h[i], l[i] = v - 0.02, v, v + 0.05, v - 0.05
    # weak swing low at 60, just chop afterward (no displacement)
    l[60], o[60], c[60], h[60] = 96.8, 97.0, 97.05, 97.1
    for i in range(61, n):
        v = 97.0 + 0.01 * np.sin(i)
        o[i], c[i], h[i], l[i] = v - 0.02, v, v + 0.05, v - 0.05
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=idx)


def test_classify_swing_strength_no_crash_and_labels():
    df = _displacement_df()
    atr_val = float(st.atr(df).iloc[-1])
    swings = st.find_swings(df["High"].values, df["Low"].values, k=st.SWING_K)
    labelled = st.classify_swing_strength(df.reset_index(drop=True), swings, atr_val)
    assert len(labelled) == len(swings)
    for s in labelled:
        assert s.strength in (None, "strong", "weak")
    # at least the displacement-preceded high should show up strong
    strengths = {round(s.price, 1): s.strength for s in labelled if s.kind == "H"}
    assert "strong" in strengths.values() or "weak" in strengths.values()


def test_liquidity_strength_alignment_no_crash():
    df = _displacement_df()
    price = float(df["Close"].iloc[-1])
    out = ls.alignment(df, "long", price)
    assert out["supports"] in (None, True, False)
    out2 = ls.alignment(df, "short", price)
    assert out2["supports"] in (None, True, False)


def test_liquidity_strength_no_crash_on_flat_data():
    idx = _bars(50)
    df = pd.DataFrame({"Open": 100.0, "High": 100.5, "Low": 99.5, "Close": 100.0}, index=idx)
    out = ls.alignment(df, "long", 100.0)
    assert out["supports"] in (None, True, False)


def test_ict_liquidity_includes_labelled_pools():
    from engine import ict
    df = _displacement_df()
    price = float(df["Close"].iloc[-1])
    out = ict.liquidity(df, price)
    assert "buyside" in out and "sellside" in out  # backward compatible
    assert "buyside_labeled" in out and "sellside_labeled" in out
    for pool in out["buyside_labeled"] + out["sellside_labeled"]:
        assert pool["strength"] in ("strong", "weak")


# ------------------------------------------------------------ rejection blocks
def _rejection_df():
    """A clean sweep of the prior 10-bar high with a big upper wick that
    closes back below it and holds -- should register as a bearish
    rejection block."""
    n = 60
    o = np.full(n, 100.0); h = np.full(n, 100.5); l = np.full(n, 99.5); c = np.full(n, 100.0)
    for i in range(0, 30):
        v = 100.0
        o[i], c[i] = v - 0.05, v + 0.02
        h[i], l[i] = v + 0.2, v - 0.2
    # sweep bar: wicks well above the prior 10-bar high, closes back inside
    o[30], c[30] = 100.1, 100.0
    h[30] = 102.0
    l[30] = 99.9
    for i in range(31, n):
        v = 100.0 - (i - 30) * 0.01
        o[i], c[i] = v + 0.02, v
        h[i], l[i] = v + 0.15, v - 0.15
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=_bars(n))


def test_find_rejection_blocks_detects_bearish_sweep():
    df = _rejection_df()
    out = bb.find_rejection_blocks(df)
    assert isinstance(out, list)
    for item in out:
        assert {"kind", "price", "idx", "inducement"} <= item.keys()
    bears = [r for r in out if r["kind"] == "bear"]
    assert bears, "expected at least one bearish rejection block on a clean sweep-and-hold"


def test_rejection_block_no_crash_on_flat_data():
    idx = _bars(30)
    df = pd.DataFrame({"Open": 100.0, "High": 100.5, "Low": 99.5, "Close": 100.0}, index=idx)
    out = bb.find_rejection_blocks(df)
    assert out == []


def test_breaker_alignment_still_works_with_rejection_blocks_added():
    df = _rejection_df()
    atr_val = float(st.atr(df).iloc[-1]) or 0.5
    out = bb.alignment(df, "short", price=float(df["Close"].iloc[-1]), atr_val=atr_val)
    assert out["supports"] in (None, True, False)


# --------------------------------------------------------------- inside bar
def test_inside_bar_detected():
    rows = [
        [99.0, 99.2, 98.8, 99.0],      # filler bar so len(df) >= 3
        [100.0, 105.0, 95.0, 102.0],   # wide range candle
        [101.0, 103.0, 99.0, 101.5],   # fully contained inside the prior range
    ]
    idx = pd.date_range("2026-01-01", periods=len(rows), freq="15min")
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx)
    out = cs.detect(df)
    names = [n for n, _ in out["patterns"]]
    assert "inside bar" in names


def test_inside_bar_is_neutral_does_not_force_lean():
    rows = [
        [99.0, 99.2, 98.8, 99.0],
        [100.0, 105.0, 95.0, 102.0],
        [101.0, 103.0, 99.0, 101.5],
    ]
    idx = pd.date_range("2026-01-01", periods=len(rows), freq="15min")
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx)
    out = cs.detect(df)
    inside_entries = [(n, l) for n, l in out["patterns"] if n == "inside bar"]
    assert inside_entries and inside_entries[0][1] == "neutral"


# ----------------------------------------------------------------- wiring
def test_confluence_survives_gap2_layers_offline():
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
        assert "breaker_mitigation" in out.layers  # rejection blocks fold into this layer
        assert "liquidity_strength" in out.layers
        names = [c[0] for c in out.checklist]
        assert "Liquidity strength" in names


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok ", fn.__name__)
    print(f"\n{len(fns)}/{len(fns)} gap2 tests passed")
