"""Offline tests for engine/chart_patterns.py — the multi-swing chart
pattern module built from "Candlesticks, Fibonacci, and Chart Pattern
Trading Tools" (the last of the 8 uploaded documents to get a dedicated
module: double/triple top-bottom, head & shoulders, triangles, wedges,
rectangles, broadening formation). All pure OHLC math, no network.
"""
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import chart_patterns as chp  # noqa: E402


def _bars(n, freq="15min"):
    return pd.date_range("2026-01-01", periods=n, freq=freq)


def _flat_df(n=200, seed=1, level=100.0, noise=0.05):
    """Pure noise around a level — should never crash and should mostly
    yield no confirmed, directional pattern."""
    idx = _bars(n)
    rng = np.random.default_rng(seed)
    px = level + np.cumsum(rng.normal(0, noise, n))
    df = pd.DataFrame({
        "Open": px, "High": px + 0.1, "Low": px - 0.1,
        "Close": px + rng.normal(0, 0.02, n),
    }, index=idx)
    return df


def _double_top_df():
    """Two peaks at ~110 with a valley at ~100 between them, then a hard
    close-through break below the valley."""
    n = 120
    o = np.full(n, 100.0); h = np.full(n, 100.5); l = np.full(n, 99.5); c = np.full(n, 100.0)
    for i in range(0, 21):
        v = 100 + i * 0.5
        o[i], c[i], h[i], l[i] = v - 0.2, v, v + 0.3, v - 0.3
    for i in range(21, 41):
        v = 110 - (i - 20) * 0.5
        o[i], c[i], h[i], l[i] = v + 0.2, v, v + 0.3, v - 0.3
    for i in range(41, 61):
        v = 100 + (i - 40) * 0.5
        o[i], c[i], h[i], l[i] = v - 0.2, v, v + 0.3, v - 0.3
    for i in range(61, n):
        v = 110 - (i - 60) * 1.0
        o[i], c[i], h[i], l[i] = v + 0.2, v, v + 0.3, v - 0.5
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=_bars(n))


def _double_bottom_df():
    """Mirror of the double top: two valleys at ~90 with a peak at ~100
    between them, then a hard close-through break above the peak."""
    n = 120
    o = np.full(n, 100.0); h = np.full(n, 100.5); l = np.full(n, 99.5); c = np.full(n, 100.0)
    for i in range(0, 21):
        v = 100 - i * 0.5
        o[i], c[i], h[i], l[i] = v + 0.2, v, v + 0.3, v - 0.3
    for i in range(21, 41):
        v = 90 + (i - 20) * 0.5
        o[i], c[i], h[i], l[i] = v - 0.2, v, v + 0.3, v - 0.3
    for i in range(41, 61):
        v = 100 - (i - 40) * 0.5
        o[i], c[i], h[i], l[i] = v + 0.2, v, v + 0.3, v - 0.3
    for i in range(61, n):
        v = 90 + (i - 60) * 1.0
        o[i], c[i], h[i], l[i] = v - 0.2, v, v + 0.5, v - 0.3
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=_bars(n))


def _ascending_triangle_df():
    """Flat resistance near 110, rising support, then a breakout above 110."""
    n = 140
    o = np.zeros(n); h = np.zeros(n); l = np.zeros(n); c = np.zeros(n)
    support0 = 95.0
    for i in range(n):
        cycle = i % 20
        support = support0 + i * 0.06
        if i < 120:
            v = support + (110 - support) * (0.5 + 0.5 * np.sin(cycle / 20 * 3.14159))
            v = min(v, 110.2)
            o[i], c[i] = v - 0.2, v
            h[i] = max(v + 0.2, 110.0 if cycle in (9, 10) else v + 0.2)
            l[i] = min(v - 0.2, support if cycle in (0, 1) else v - 0.2)
        else:
            v = 110 + (i - 120) * 0.8
            o[i], c[i], h[i], l[i] = v - 0.2, v, v + 0.3, v - 0.3
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=_bars(n))


# ------------------------------------------------------------------ safety
def test_detect_no_crash_on_random_noise():
    df = _flat_df()
    out = chp.detect(df)
    assert isinstance(out, dict)
    assert "patterns" in out and "note" in out


def test_detect_no_crash_on_too_few_bars():
    df = _flat_df(n=10)
    out = chp.detect(df)
    assert out["patterns"] == []


def test_alignment_no_crash_on_random_noise():
    df = _flat_df()
    out = chp.alignment(df, "long")
    assert out["supports"] in (None, True, False)


def test_alignment_no_crash_on_empty_df():
    df = pd.DataFrame({"Open": [], "High": [], "Low": [], "Close": []})
    out = chp.alignment(df, "long")
    assert out["supports"] in (None, True, False)


# ------------------------------------------------------------ double top/bottom
def test_double_top_detected_confirmed_and_bearish():
    df = _double_top_df()
    out = chp.detect(df)
    tops = [p for p in out["patterns"] if p["pattern"] == "double_top"]
    assert tops, "expected a double_top entry"
    dt = tops[0]
    assert dt["confirmed"] is True
    assert dt["direction"] == "bear"
    assert dt["target"] is not None and dt["target"] < 99.7  # projected below the neckline


def test_double_top_alignment_supports_short_not_long():
    df = _double_top_df()
    short_align = chp.alignment(df, "short")
    long_align = chp.alignment(df, "long")
    assert short_align["supports"] is True
    assert long_align["supports"] is False


def test_double_bottom_detected_confirmed_and_bullish():
    df = _double_bottom_df()
    out = chp.detect(df)
    bots = [p for p in out["patterns"] if p["pattern"] == "double_bottom"]
    assert bots, "expected a double_bottom entry"
    db = bots[0]
    assert db["confirmed"] is True
    assert db["direction"] == "bull"


def test_double_bottom_alignment_supports_long_not_short():
    df = _double_bottom_df()
    assert chp.alignment(df, "long")["supports"] is True
    assert chp.alignment(df, "short")["supports"] is False


# --------------------------------------------------------------- triangles
def test_ascending_triangle_detected_confirmed_bullish_breakout():
    df = _ascending_triangle_df()
    out = chp.detect(df)
    tris = [p for p in out["patterns"] if p["pattern"] == "ascending_triangle"]
    assert tris, "expected an ascending_triangle entry"
    t = tris[0]
    assert t["confirmed"] is True
    assert t["direction"] == "bull"
    assert t["target"] > 110  # projected above the resistance breakout level


def test_triangle_alignment_supports_long():
    df = _ascending_triangle_df()
    assert chp.alignment(df, "long")["supports"] is True
    assert chp.alignment(df, "short")["supports"] is False


# ----------------------------------------------------------------- wiring
def test_confluence_survives_chart_pattern_layer_offline():
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
        assert "chart_pattern" in out.layers
        names = [c[0] for c in out.checklist]
        assert "Chart pattern" in names


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok ", fn.__name__)
    print(f"\n{len(fns)}/{len(fns)} chart-pattern tests passed")
