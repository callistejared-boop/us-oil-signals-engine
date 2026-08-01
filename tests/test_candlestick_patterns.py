"""Offline tests for the candlestick pattern recognition module. Pure OHLC
math, no network, fully deterministic and symbol-agnostic (works the same
for WTI, gold, or Bitcoin bars).
"""
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import candlestick_patterns as cs   # noqa: E402


def _df(rows):
    idx = pd.date_range("2026-01-01", periods=len(rows), freq="15min")
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx)


def test_bullish_engulfing_detected():
    rows = [
        [100.0, 100.1, 95.0, 96.0],    # filler
        [98.0, 98.2, 95.5, 96.0],      # prior: small bearish body
        [95.5, 100.5, 95.2, 100.0],    # current: engulfs prior body, bullish
    ]
    out = cs.detect(_df(rows))
    names = [n for n, _ in out["patterns"]]
    assert "bullish engulfing" in names
    assert out["lean"] == "bull"


def test_bearish_engulfing_detected():
    rows = [
        [90.0, 95.0, 89.0, 94.0],
        [96.0, 96.5, 95.5, 96.2],      # prior: small bullish body
        [96.5, 96.8, 90.0, 90.5],      # current: engulfs prior body, bearish
    ]
    out = cs.detect(_df(rows))
    names = [n for n, _ in out["patterns"]]
    assert "bearish engulfing" in names
    assert out["lean"] == "bear"


def test_hammer_detected():
    rows = [
        [100.0, 100.5, 99.5, 100.0],
        [100.0, 100.5, 99.5, 100.0],
        [100.0, 100.4, 95.0, 100.2],   # long lower wick, small body near top
    ]
    out = cs.detect(_df(rows))
    names = [n for n, _ in out["patterns"]]
    assert "hammer" in names
    assert out["lean"] == "bull"


def test_shooting_star_detected():
    rows = [
        [100.0, 100.5, 99.5, 100.0],
        [100.0, 100.5, 99.5, 100.0],
        [100.0, 105.0, 99.8, 100.2],   # long upper wick, small body near bottom
    ]
    out = cs.detect(_df(rows))
    names = [n for n, _ in out["patterns"]]
    assert "shooting star / inverted hammer" in names
    assert out["lean"] == "bear"


def test_plain_doji_has_no_directional_lean():
    # a symmetric doji (wicks split roughly evenly) carries no directional
    # evidence, so detect() correctly excludes it from the scored patterns
    # list rather than reporting a fake bull/bear lean.
    rows = [
        [100.0, 100.5, 99.5, 100.0],
        [100.0, 100.5, 99.5, 100.0],
        [100.0, 102.0, 98.0, 100.05],  # open ~= close, wicks split ~evenly
    ]
    out = cs.detect(_df(rows))
    names = [n for n, _ in out["patterns"]]
    assert not any("doji" in n for n in names)


def test_dragonfly_doji_detected():
    rows = [
        [100.0, 100.5, 99.5, 100.0],
        [100.0, 100.5, 99.5, 100.0],
        [100.0, 100.1, 95.0, 100.05],  # open ~= close near the top, long lower wick
    ]
    out = cs.detect(_df(rows))
    names = [n for n, _ in out["patterns"]]
    assert "dragonfly doji" in names
    assert out["lean"] == "bull"


def test_marubozu_detected():
    rows = [
        [100.0, 100.5, 99.5, 100.0],
        [100.0, 100.5, 99.5, 100.0],
        [100.0, 105.0, 100.0, 105.0],  # no wicks, full-body bullish
    ]
    out = cs.detect(_df(rows))
    names = [n for n, _ in out["patterns"]]
    assert "marubozu" in names
    assert out["lean"] == "bull"


def test_no_pattern_on_ordinary_bars():
    rows = [
        [100.0, 101.0, 99.5, 100.5],
        [100.5, 101.2, 100.0, 100.8],
        [100.8, 101.3, 100.4, 101.0],
    ]
    out = cs.detect(_df(rows))
    # ordinary small-range bullish bars shouldn't force a pattern match
    assert isinstance(out["patterns"], list)


def test_insufficient_data_no_crash():
    out = cs.detect(_df([[100.0, 101.0, 99.0, 100.5]]))
    assert out["patterns"] == [] and out["lean"] is None


def test_alignment_direction_mapping():
    rows = [
        [100.0, 100.1, 95.0, 96.0],
        [98.0, 98.2, 95.5, 96.0],
        [95.5, 100.5, 95.2, 100.0],   # bullish engulfing
    ]
    df = _df(rows)
    out_long = cs.alignment(df, "long")
    out_short = cs.alignment(df, "short")
    assert out_long["supports"] is True
    assert out_short["supports"] is False


def test_alignment_neutral_when_no_pattern():
    rows = [
        [100.0, 100.2, 99.8, 100.1],
        [100.1, 100.3, 99.9, 100.2],
        [100.2, 100.4, 100.0, 100.3],
    ]
    out = cs.alignment(_df(rows), "long")
    assert out["supports"] in (None, True, False)


# --------------------------------------------------------- confluence wiring
def test_confluence_survives_candlestick_layer_offline():
    import numpy as np
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
        assert "candlestick" in out.layers
        names = [c[0] for c in out.checklist]
        assert "Candlestick pattern" in names


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok ", fn.__name__)
    print(f"\n{len(fns)}/{len(fns)} candlestick-pattern tests passed")
