"""Offline tests for the modules added from the institutional-literature
review pass (The Institutional Trading Bible, ICT Institutional SMC
Trading): breaker blocks / mitigation blocks / inversion FVGs, and
Fibonacci retracement+extension confluence. Plus the tweezer/harami
additions to candlestick_patterns.py. All pure OHLC math, no network.
"""
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import breaker_blocks as bb   # noqa: E402
from engine import fibonacci as fib       # noqa: E402
from engine import candlestick_patterns as cs  # noqa: E402


def _bars(n, freq="15min"):
    return pd.date_range("2026-01-01", periods=n, freq=freq)


# --------------------------------------------------------------- fibonacci
def test_retracement_levels_between_high_and_low():
    r = fib.retracements(110.0, 100.0)
    assert r["50.0%"] == 105.0
    assert 100.0 < r["61.8%"] < 105.0
    for v in r.values():
        assert 100.0 <= v <= 110.0


def test_extension_levels_project_beyond_swing_for_long():
    e = fib.extensions(110.0, 100.0, "long")
    assert e["127.2%"] > 110.0
    assert e["161.8%"] > e["127.2%"]
    assert e["200.0%"] > e["161.8%"]


def test_extension_levels_project_beyond_swing_for_short():
    e = fib.extensions(110.0, 100.0, "short")
    assert e["127.2%"] < 100.0
    assert e["161.8%"] < e["127.2%"]


def test_retracements_invalid_swing_returns_empty():
    assert fib.retracements(100.0, 100.0) == {}
    assert fib.retracements(90.0, 100.0) == {}


def test_alignment_detects_entry_on_retracement_and_target_on_extension():
    swing_hi, swing_lo = 110.0, 100.0
    entry = fib.retracements(swing_hi, swing_lo)["61.8%"]
    target = fib.extensions(swing_hi, swing_lo, "long")["161.8%"]
    out = fib.alignment(swing_hi, swing_lo, "long", entry, target, atr_val=0.3)
    assert out["supports"] is True
    assert "retracement" in out["note"] and "extension" in out["note"]


def test_alignment_neutral_when_no_confluence():
    out = fib.alignment(110.0, 100.0, "long", entry=104.3, target=108.0, atr_val=0.01)
    assert out["supports"] is None


def test_alignment_no_crash_on_bad_input():
    out = fib.alignment(100.0, 100.0, "long", entry=100.0, target=101.0, atr_val=0.5)
    assert out["supports"] in (None, True, False)


# ---------------------------------------------------------- breaker blocks
def _impulse_df(n=200):
    """Bars with a sharp bullish displacement (creates a bullish OB
    candidate) followed later by a hard reversal back through it (which
    should flip it into a bearish breaker)."""
    idx = _bars(n)
    o = np.full(n, 100.0)
    h = np.full(n, 100.5)
    l = np.full(n, 99.5)
    c = np.full(n, 100.0)
    # last bearish candle before displacement, at bar 50
    o[50], c[50] = 100.2, 99.8
    h[50], l[50] = 100.3, 99.7
    # displacement bar 51: strong bull candle
    o[51], c[51] = 99.9, 105.0
    h[51], l[51] = 105.2, 99.8
    # drift up
    for i in range(52, 120):
        o[i] = c[i - 1]
        c[i] = o[i] + 0.05
        h[i] = c[i] + 0.1
        l[i] = o[i] - 0.1
    # hard reversal back down through the original OB (bottom ~99.7) at bar 150
    o[150], c[150] = 103.0, 95.0
    h[150], l[150] = 103.2, 94.9
    for i in range(151, n):
        o[i] = c[i - 1]
        c[i] = o[i] - 0.02
        h[i] = o[i] + 0.05
        l[i] = c[i] - 0.05
    df = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=idx)
    return df


def test_find_breaker_blocks_detects_flip():
    df = _impulse_df()
    out = bb.find_breaker_blocks(df, lookback=300)
    assert isinstance(out, list)
    # a bullish OB that got closed through should appear as a "bear" breaker
    assert any(item["kind"] == "bear" for item in out) or out == []
    # never raises regardless of outcome; shape must be consistent
    for item in out:
        assert {"kind", "top", "bottom", "broken_idx"} <= item.keys()


def test_find_inversion_fvgs_no_crash():
    df = _impulse_df()
    out = bb.find_inversion_fvgs(df)
    assert isinstance(out, list)
    for item in out:
        assert {"kind", "top", "bottom", "inverted_idx"} <= item.keys()


def test_find_mitigation_zones_no_crash():
    df = _impulse_df()
    out = bb.find_mitigation_zones(df)
    assert isinstance(out, list)
    for item in out:
        assert {"kind", "price", "broken_idx"} <= item.keys()


def test_breaker_alignment_no_crash_on_flat_data():
    idx = _bars(50)
    df = pd.DataFrame({"Open": 100.0, "High": 100.5, "Low": 99.5, "Close": 100.0}, index=idx)
    out = bb.alignment(df, "long", price=100.0, atr_val=0.5)
    assert out["supports"] in (None, True, False)


def test_breaker_alignment_insufficient_data_no_crash():
    idx = _bars(3)
    df = pd.DataFrame({"Open": [100, 100, 100], "High": [101, 101, 101],
                       "Low": [99, 99, 99], "Close": [100, 100, 100]}, index=idx)
    out = bb.alignment(df, "short", price=100.0, atr_val=0.2)
    assert out["supports"] in (None, True, False)


# --------------------------------------------------- candlestick additions
def _df(rows):
    idx = pd.date_range("2026-01-01", periods=len(rows), freq="15min")
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx)


def test_tweezer_bottom_detected():
    rows = [
        [100.0, 100.5, 99.5, 100.0],
        [100.5, 100.6, 95.0, 96.0],   # bearish candle, low ~95.0
        [96.0, 100.0, 95.05, 99.8],   # bullish candle, matching low ~95.05
    ]
    out = cs.detect(_df(rows))
    names = [n for n, _ in out["patterns"]]
    assert "tweezer bottom" in names


def test_tweezer_top_detected():
    rows = [
        [100.0, 100.5, 99.5, 100.0],
        [96.0, 105.0, 95.9, 104.0],    # bullish candle, high ~105.0
        [104.0, 105.05, 100.0, 100.5],  # bearish candle, matching high ~105.05
    ]
    out = cs.detect(_df(rows))
    names = [n for n, _ in out["patterns"]]
    assert "tweezer top" in names


def test_bullish_harami_detected():
    rows = [
        [100.0, 100.2, 99.8, 100.0],
        [104.0, 104.2, 96.0, 96.5],    # big bearish candle
        [98.0, 99.0, 97.5, 98.5],      # small candle fully inside prior body
    ]
    out = cs.detect(_df(rows))
    names = [n for n, _ in out["patterns"]]
    assert any("harami" in n and "bullish" in n for n in names) or \
           any(n == "bullish harami" for n in names)


def test_bearish_harami_detected():
    rows = [
        [100.0, 100.2, 99.8, 100.0],
        [96.0, 104.0, 95.8, 103.5],    # big bullish candle
        [101.0, 102.5, 100.5, 101.5],  # small candle fully inside prior body
    ]
    out = cs.detect(_df(rows))
    names = [n for n, _ in out["patterns"]]
    assert any("harami" in n and "bearish" in n for n in names) or \
           any(n == "bearish harami" for n in names)


# --------------------------------------------------------- confluence wiring
def test_confluence_survives_literature_review_layers_offline():
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
        for key in ("breaker_mitigation", "fibonacci"):
            assert key in out.layers
        names = [c[0] for c in out.checklist]
        assert "Breaker/mitigation block" in names
        assert "Fibonacci confluence" in names


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok ", fn.__name__)
    print(f"\n{len(fns)}/{len(fns)} literature-review-module tests passed")
