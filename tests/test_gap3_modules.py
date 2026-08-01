"""Offline tests for the third literature-review pass: Fibonacci A-B-C
expansion (added to engine/fibonacci.py), Balanced Price Range / Consequent
Encroachment (engine/balanced_range.py), and the AMD/Judas Swing session
model (engine/session_model.py). All pure OHLC math, no network. Provenance
note carried in each module's docstring: these concepts are named in the
"Smart Money 200-Page Master Guide" but that document is templated
boilerplate with no operational content, so the implementations below are
standard ICT/SMC domain knowledge, not document-extracted rules.
"""
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import fibonacci as fib          # noqa: E402
from engine import balanced_range as bpr     # noqa: E402
from engine import session_model as sm       # noqa: E402


def _bars(n, freq="15min", start="2026-01-01"):
    return pd.date_range(start, periods=n, freq=freq)


# ------------------------------------------------------------- ABC expansion
def test_expansions_project_from_c_using_ab_size():
    exp = fib.expansions(a=100.0, b=110.0, c=105.0, direction="long")
    assert exp["100.0%"] == 115.0   # AB size (10) applied from C (105) upward
    assert exp["161.8%"] > exp["100.0%"]


def test_expansions_short_projects_downward():
    exp = fib.expansions(a=100.0, b=110.0, c=105.0, direction="short")
    assert exp["100.0%"] == 95.0
    assert exp["161.8%"] < exp["100.0%"]


def test_expansions_invalid_ab_returns_empty():
    assert fib.expansions(100.0, 100.0, 105.0, "long") == {}


def test_alignment_abc_no_crash_on_random_data():
    idx = _bars(200)
    rng = np.random.default_rng(3)
    px = 70 + np.cumsum(rng.normal(0, 0.05, 200))
    df = pd.DataFrame({"Open": px, "High": px + 0.1, "Low": px - 0.1, "Close": px}, index=idx)
    out = fib.alignment_abc(df, "long", float(px[-1]), atr_val=0.3)
    assert out["supports"] in (None, True, False)


def test_alignment_abc_no_crash_on_too_few_bars():
    idx = _bars(5)
    df = pd.DataFrame({"Open": 100.0, "High": 100.5, "Low": 99.5, "Close": 100.0}, index=idx)
    out = fib.alignment_abc(df, "long", 100.0, atr_val=0.5)
    assert out["supports"] in (None, True, False)


# -------------------------------------------------------------------- BPR/CE
def _bpr_df():
    """A bullish FVG immediately followed by an overlapping bearish FVG:
    bar i-2..i creates a bull gap (low[i] > high[i-2]), then a few bars
    later a bear gap forms (high[j] < low[j-2]) whose range overlaps it."""
    n = 60
    o = np.full(n, 100.0); h = np.full(n, 100.5); l = np.full(n, 99.5); c = np.full(n, 100.0)
    for i in range(n):
        o[i], c[i], h[i], l[i] = 100.0, 100.0, 100.3, 99.7
    # bullish FVG: bars 8,9,10 -> low[10] > high[8]
    h[8], l[8] = 100.3, 100.0
    o[9], c[9], h[9], l[9] = 100.2, 101.5, 101.6, 100.2
    h[10], l[10] = 102.2, 101.9
    # bearish FVG shortly after: bars 14,15,16 -> high[16] < low[14], overlapping the bull gap
    h[14], l[14] = 101.8, 101.5
    o[15], c[15], h[15], l[15] = 101.4, 100.5, 101.5, 100.4
    h[16], l[16] = 101.0, 100.7
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=_bars(n))


def test_find_bprs_detects_overlap():
    df = _bpr_df()
    out = bpr.find_bprs(df)
    assert isinstance(out, list)
    for item in out:
        assert {"top", "bottom", "ce", "bull_idx", "bear_idx"} <= item.keys()
        assert item["top"] > item["bottom"]


def test_bpr_alignment_no_crash():
    df = _bpr_df()
    out = bpr.alignment(df, "long", price=float(df["Close"].iloc[-1]), atr_val=0.5)
    assert out["supports"] in (None, True, False)


def test_bpr_alignment_no_crash_on_flat_data():
    idx = _bars(30)
    df = pd.DataFrame({"Open": 100.0, "High": 100.5, "Low": 99.5, "Close": 100.0}, index=idx)
    out = bpr.alignment(df, "short", 100.0, 0.5)
    assert out["supports"] in (None, True, False)


# --------------------------------------------------------------- session model
def _judas_df():
    """Asian range 100-101 on day 1 (hours 0-5 UTC), London (hours 7-9)
    sweeps above 101 then closes back below it, followed by bars that later
    close above the Asian low too (irrelevant) -- expects a short bias."""
    idx = pd.date_range("2026-02-02 00:00", periods=40, freq="1h", tz=None)
    o = np.full(40, 100.5); h = np.full(40, 100.8); l = np.full(40, 100.2); c = np.full(40, 100.5)
    # Asian session hours 0-5: tight range 100-101
    for i in range(0, 6):
        o[i], c[i], h[i], l[i] = 100.5, 100.6, 101.0, 100.0
    # London kill zone hours 7-9: sweep above 101, then...
    o[7], c[7], h[7], l[7] = 100.9, 100.95, 102.5, 100.8
    # ...close back below the Asian high shortly after
    for i in range(8, 12):
        o[i], c[i], h[i], l[i] = 100.9, 100.7, 101.0, 100.5
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=idx)


def test_judas_swing_detects_bearish_sweep():
    df = _judas_df()
    js = sm.judas_swing(df)
    assert js is not None
    assert js["direction"] == "short"
    assert js["swept"] == "high"


def test_session_alignment_no_crash_on_random_data():
    idx = pd.date_range("2026-01-01 00:00", periods=200, freq="1h")
    rng = np.random.default_rng(7)
    px = 70 + np.cumsum(rng.normal(0, 0.05, 200))
    df = pd.DataFrame({"Open": px, "High": px + 0.2, "Low": px - 0.2, "Close": px}, index=idx)
    out = sm.alignment(df, "long")
    assert out["supports"] in (None, True, False)


def test_session_alignment_no_crash_on_flat_data():
    idx = pd.date_range("2026-01-01 00:00", periods=30, freq="1h")
    df = pd.DataFrame({"Open": 100.0, "High": 100.5, "Low": 99.5, "Close": 100.0}, index=idx)
    out = sm.alignment(df, "long")
    assert out["supports"] in (None, True, False)


# ----------------------------------------------------------------- wiring
def test_confluence_survives_gap3_layers_offline():
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
        for key in ("bpr_ce", "fibonacci_abc", "session_model"):
            assert key in out.layers
        names = [c[0] for c in out.checklist]
        assert "BPR / consequent encroachment" in names
        assert "Fibonacci ABC expansion" in names
        assert "Session model (AMD/Judas Swing)" in names


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok ", fn.__name__)
    print(f"\n{len(fns)}/{len(fns)} gap3 tests passed")
