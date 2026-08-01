"""Unit tests for the structure and signal modules."""
import numpy as np
import pandas as pd
import pytest

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine import structure as st          # noqa: E402
from engine.data_loader import resample     # noqa: E402


def make_df(closes, spread=0.5, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(closes), freq="15min")
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "Open": c, "High": c + spread, "Low": c - spread,
        "Close": c, "Volume": np.ones(len(c)),
    }, index=idx)


def test_swing_detection_finds_obvious_extremes():
    prices = [10, 11, 12, 15, 12, 11, 10, 9, 8, 5, 8, 9, 10]
    df = make_df(prices)
    swings = st.find_swings(df["High"].values, df["Low"].values, k=2)
    kinds = {(s.kind, s.idx) for s in swings}
    assert ("H", 3) in kinds       # peak at 15
    assert ("L", 9) in kinds       # trough at 5


def test_swing_confirmation_lag_prevents_lookahead():
    prices = [10, 11, 12, 15, 12, 11, 10]
    df = make_df(prices)
    swings = st.find_swings(df["High"].values, df["Low"].values, k=2)
    peak = [s for s in swings if s.kind == "H"][0]
    assert peak.confirmed_idx == peak.idx + 2


def test_bullish_fvg_detected_and_fill_marked():
    # bar0 high=10.5, bar2 low=12 -> bullish gap (10.5..12); later bar dips to 10
    df = make_df([10, 11, 12.5, 13, 10.5])
    df.loc[df.index[2], "Low"] = 12.0
    df.loc[df.index[4], "Low"] = 10.0
    gaps = st.find_fvgs(df)
    bulls = [g for g in gaps if g.kind == "bull"]
    assert bulls, "expected a bullish FVG"
    g = bulls[0]
    assert g.bottom == pytest.approx(10.5)
    assert g.filled_idx == 4


def zigzag(*legs):
    """Build a price path from alternating legs, e.g. zigzag((30,25),(25,28),...)."""
    out = []
    for a, b in legs:
        step = 1 if b > a else -1
        out.extend(range(a, b, step))
    out.append(legs[-1][1])
    return out


def test_structure_trend_turns_bullish_on_break():
    # lower-highs down move, then an up-leg that closes above the last swing high
    prices = zigzag((30, 24), (24, 27), (27, 22), (22, 40))
    df = make_df(prices, spread=0.2)
    s = st.structure_series(df)
    assert s["trend"].iloc[-1] == "bull"
    assert (s["event"] != "").any()


def test_structure_trend_turns_bearish_on_break():
    prices = zigzag((20, 26), (26, 23), (23, 28), (28, 10))
    df = make_df(prices, spread=0.2)
    s = st.structure_series(df)
    assert s["trend"].iloc[-1] == "bear"


def test_range_position_bounds():
    assert st.range_position(5, 10, 0) == pytest.approx(0.5)
    assert st.range_position(0, 10, 0) == pytest.approx(0.0)
    assert st.range_position(10, 10, 0) == pytest.approx(1.0)
    assert st.range_position(7, 5, 5) == pytest.approx(0.5)  # degenerate


def test_atr_positive_and_finite():
    rng = np.random.default_rng(7)
    prices = 2000 + rng.normal(0, 3, 300).cumsum()
    df = make_df(prices, spread=2.0)
    a = st.atr(df)
    assert (a.iloc[20:] > 0).all()
    assert np.isfinite(a.iloc[-1])


def test_resample_ohlc_integrity():
    df = make_df(range(100))
    h1 = resample(df, "1h")
    first = df.iloc[:4]
    assert h1["Open"].iloc[0] == first["Open"].iloc[0]
    assert h1["High"].iloc[0] == first["High"].max()
    assert h1["Low"].iloc[0] == first["Low"].min()
    assert h1["Close"].iloc[0] == first["Close"].iloc[-1]


def test_killzone_hours():
    assert st.in_killzone(pd.Timestamp("2024-01-03 08:30"))
    assert st.in_killzone(pd.Timestamp("2024-01-03 13:00"))
    assert not st.in_killzone(pd.Timestamp("2024-01-03 22:00"))
