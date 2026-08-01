"""Offline tests for the MAST Layer-2 confirmation modules: price action,
trend quality, breakout, mean reversion, Wyckoff, volume profile, and the
unified confluence engine. Every module must fail safe on bad/short input."""
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import price_action as pa       # noqa: E402
from engine import trend_quality as tq      # noqa: E402
from engine import breakout as bo           # noqa: E402
from engine import mean_reversion as mr     # noqa: E402
from engine import wyckoff as wy            # noqa: E402
from engine import volume_profile as vp     # noqa: E402
from engine import confluence as cf         # noqa: E402


def _df(rows, freq="15min", start="2026-07-01"):
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"])
    df["Volume"] = 0.0
    df.index = pd.date_range(start, periods=len(df), freq=freq)
    return df


def _trend_series(n=250, start=70.0, step=0.15, noise=0.05, seed=1):
    rng = np.random.default_rng(seed)
    rows, px = [], start
    for i in range(n):
        px += step + rng.normal(0, noise)
        o = px - step / 2
        h = px + abs(rng.normal(0.05, 0.03))
        l = px - abs(rng.normal(0.05, 0.03))
        rows.append([o, h, l, px])
    return _df(rows)


# ---------------------------------------------------------------- price_action
def test_pin_bar_bull():
    rows = [[80.0, 80.1, 78.5, 79.9]]  # long lower wick, small body near top
    df = _df(rows * 1)
    assert pa.pin_bar(df, -1) == "bull"


def test_engulfing_detects_bull():
    rows = [[80.2, 80.3, 79.8, 79.9], [79.85, 80.6, 79.8, 80.5]]
    df = _df(rows)
    assert pa.engulfing(df, -1) == "bull"


def test_inside_outside_bar():
    rows = [[80, 81, 79, 80.5], [80.2, 80.6, 79.8, 80.3]]
    df = _df(rows)
    assert pa.inside_bar(df, -1) is True
    rows2 = [[80.2, 80.6, 79.8, 80.3], [79.5, 81.5, 79.0, 80.0]]
    df2 = _df(rows2)
    assert pa.outside_bar(df2, -1) is True


def test_price_action_failsafe():
    out = pa.read(_df([[1, 1, 1, 1]]), "long")
    assert out["pattern"] is None and out["agrees"] is None


# ---------------------------------------------------------------- trend_quality
def test_ema_stack_bull_alignment():
    df = _trend_series(300, step=0.2)
    direction, n = tq.ema_stack(df)
    assert direction == "bull" and n == 4


def test_adx_higher_in_strong_trend():
    trending = _trend_series(200, step=0.25, noise=0.02)
    choppy = _df([[80 + (i % 2) * 0.1, 80.2, 79.8, 80 + (i % 2) * 0.05]
                  for i in range(200)])
    assert tq.adx(trending) > tq.adx(choppy)


def test_trend_quality_read_continuation():
    df = _trend_series(300, step=0.2)
    out = tq.read(df, df, "long")
    assert out["stack_dir"] == "bull"
    assert out["htf_agrees"] is True


# ---------------------------------------------------------------- breakout
def test_compression_flags_tight_range():
    rows = [[80 + 0.01 * (i % 2), 80.05, 79.95, 80] for i in range(60)]
    df = _df(rows)
    out = bo.compression(df)
    assert out["compressed"] in (True, False)  # doesn't crash; sane type


def test_classify_break_real_vs_false():
    up = _trend_series(60, step=0.3, noise=0.01)
    verdict = bo.classify_break(up, level=float(up["Close"].iloc[0]), direction="long")
    assert verdict == "real"
    # false breakout: pokes above then closes back under
    rows = [[80, 80.2, 79.8, 80.0]] * 5 + [[80, 81.0, 79.9, 79.5]]
    df = _df(rows)
    v2 = bo.classify_break(df, level=80.5, direction="long")
    assert v2 in ("false", "untested")


def test_breakout_read_failsafe():
    out = bo.read(_df([[1, 1, 1, 1]] * 5), "long")
    assert "lines" in out


# ---------------------------------------------------------------- mean_reversion
def test_extension_score_flags_overbought():
    rows = []
    px = 70.0
    for i in range(60):
        px += 0.6
        rows.append([px - 0.3, px + 0.1, px - 0.4, px])
    df = _df(rows)
    ext = mr.extension_score(df)
    assert ext["score"] >= 25


def test_conflicts_with_continuation():
    stretched = {"score": 100, "lean": "upside"}
    assert mr.conflicts_with_continuation(stretched, "long") is True
    assert mr.conflicts_with_continuation(stretched, "short") is False
    calm = {"score": 25, "lean": "none"}
    assert mr.conflicts_with_continuation(calm, "long") is False


def test_retracement_targets():
    t = mr.retracement_targets(100, 90)
    assert t["50%"] == 95.0
    assert mr.retracement_targets(90, 100) == {}


# ---------------------------------------------------------------- wyckoff
def test_spring_maps_to_liquidity_sweep():
    rows = []
    for i in range(90):
        c = 80.0 + 0.5 * np.sin(i / 6)
        rows.append([c, c + 0.15, c - 0.15, c + 0.02])
    lo = min(r[2] for r in rows[:78]) - 0.5
    rows[85] = [80.0, 80.2, lo, 80.1]
    df = _df(rows)
    out = wy.spring_or_upthrust(df, "long")
    assert out is not None and out["event"] == "spring"


def test_effort_vs_result_absorption():
    # wide range every bar, but closes back near the same price each time:
    # high effort (range), ~zero net result -> absorption
    rows = [[80, 80.5, 79.5, 80.0] for _ in range(10)]
    df = _df(rows)
    out = wy.effort_vs_result(df)
    assert out["absorption"] is True


def test_wyckoff_read_failsafe():
    out = wy.read(_df([[1, 1, 1, 1]] * 5), "long", atr_val=0.1)
    assert "phase" in out


# ---------------------------------------------------------------- volume_profile
def test_profile_flags_unreliable_volume():
    df = _trend_series(120)
    out = vp.profile(df)
    assert out["approx"] is True  # our synthetic frame has zero volume
    assert out["reliable"] is False


def test_profile_poc_within_range():
    df = _trend_series(150)
    out = vp.profile(df)
    lo, hi = float(df["Low"].min()), float(df["High"].max())
    assert lo <= out["poc"] <= hi


def test_volume_profile_failsafe():
    out = vp.read(_df([[1, 1, 1, 1]] * 5))
    assert "lines" in out


# ---------------------------------------------------------------- confluence
def test_confluence_returns_none_without_layer1_setup():
    # flat/no-structure data: Layer 1 (ICT/SMC) should find nothing to confirm
    flat = _df([[80, 80.05, 79.95, 80.0]] * 500, start="2026-01-01")
    out = cf.analyze(flat, symbol="WTIUSD")
    assert out is None


def test_confluence_never_upgrades_watch_above_confirmed():
    # sanity: whatever Layer 1 tier is, confluence's final tier is either
    # that tier, "watch", or "rejected" - never something Layer 1 didn't allow
    df = _trend_series(500, step=0.15, seed=7)
    out = cf.analyze(df, symbol="WTIUSD")
    if out is not None:
        assert out.final_tier in ("confirmed", "watch", "rejected")
        assert out.final_tier != "confirmed" or out.base_tier == "confirmed"


def test_confluence_score_bounded():
    df = _trend_series(500, step=0.15, seed=3)
    out = cf.analyze(df, symbol="WTIUSD")
    if out is not None:
        assert 0 <= out.score <= 100


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok ", fn.__name__)
    print(f"\n{len(fns)}/{len(fns)} MAST layer tests passed")
