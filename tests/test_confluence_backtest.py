"""Offline tests for engine/confluence_backtest.py (V2.2 Priority 5
extension — the confluence-vs-backtest bridge triggered by the
qualification_diagnostics finding that MAST confluence has never been
backtested). All confluence.analyze() calls are monkeypatched to keep
these fast and deterministic — no real market-structure detection is
exercised here (that's confluence.py's own test suite's job); these tests
verify the REPLAY/COMPARISON logic only.
"""
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import confluence_backtest as cbt   # noqa: E402
from engine import backtest as bt                # noqa: E402
from engine import confluence as cf              # noqa: E402
from engine.signals import Signal                # noqa: E402


def _df(n=7000, seed=3):
    rng = np.random.default_rng(seed)
    closes = 2000 + rng.normal(0, 3, n).cumsum()
    idx = pd.date_range("2026-01-01", periods=n, freq="15min")
    return pd.DataFrame({
        "Open": closes, "High": closes + 1.5, "Low": closes - 1.5,
        "Close": closes, "Volume": np.ones(n),
    }, index=idx)


def _trade(df, i, direction="long", entry=100.0, outcome="win", result_r=1.5):
    sig = Signal(time=df.index[i], direction=direction, entry=entry, stop=99.0,
                target=103.0, rr=3.0, confidence=70, symbol="XAUUSD", tier="confirmed")
    return bt.Trade(signal=sig, fill_time=df.index[i + 1], exit_time=df.index[i + 5],
                    result_r=result_r, outcome=outcome)


def _cr(direction="long", entry=100.0, score=75, base_tier="confirmed", final_tier="confirmed"):
    sig = Signal(time=None, direction=direction, entry=entry, stop=99.0, target=103.0,
                rr=3.0, confidence=70, symbol="XAUUSD", tier=base_tier)
    return cf.ConfluenceRead(symbol="XAUUSD", direction=direction, base_tier=base_tier,
                             final_tier=final_tier, score=score, sig=sig)


# --------------------------------------------------------------------------
# replay_with_confluence
# --------------------------------------------------------------------------

def test_replay_ok_when_direction_and_entry_match(monkeypatch):
    df = _df()
    i = bt.WINDOW + 100
    trade = _trade(df, i)
    monkeypatch.setattr(cf, "analyze", lambda *a, **k: _cr(score=80))

    out = cbt.replay_with_confluence(df, "XAUUSD", [trade])
    assert len(out) == 1
    assert out[0]["status"] == "ok"
    assert out[0]["score"] == 80
    assert out[0]["hard_gate_rejected"] is False


def test_replay_flags_hard_gate_rejection(monkeypatch):
    df = _df()
    i = bt.WINDOW + 100
    trade = _trade(df, i)
    monkeypatch.setattr(cf, "analyze", lambda *a, **k: _cr(score=74, final_tier="rejected"))

    out = cbt.replay_with_confluence(df, "XAUUSD", [trade])
    assert out[0]["status"] == "ok"
    assert out[0]["hard_gate_rejected"] is True


def test_replay_mismatch_on_direction_disagreement(monkeypatch):
    df = _df()
    i = bt.WINDOW + 100
    trade = _trade(df, i, direction="long")
    monkeypatch.setattr(cf, "analyze", lambda *a, **k: _cr(direction="short"))

    out = cbt.replay_with_confluence(df, "XAUUSD", [trade])
    assert out[0]["status"] == "mismatch"


def test_replay_mismatch_on_entry_disagreement(monkeypatch):
    df = _df()
    i = bt.WINDOW + 100
    trade = _trade(df, i, entry=100.0)
    monkeypatch.setattr(cf, "analyze", lambda *a, **k: _cr(entry=150.0))

    out = cbt.replay_with_confluence(df, "XAUUSD", [trade])
    assert out[0]["status"] == "mismatch"


def test_replay_error_when_confluence_finds_nothing(monkeypatch):
    df = _df()
    i = bt.WINDOW + 100
    trade = _trade(df, i)
    monkeypatch.setattr(cf, "analyze", lambda *a, **k: None)

    out = cbt.replay_with_confluence(df, "XAUUSD", [trade])
    assert out[0]["status"] == "error"


def test_replay_error_when_bar_not_locatable(monkeypatch):
    df = _df()
    sig = Signal(time=pd.Timestamp("1999-01-01"), direction="long", entry=100.0, stop=99.0,
                target=103.0, rr=3.0, confidence=70, symbol="XAUUSD", tier="confirmed")
    trade = bt.Trade(signal=sig, fill_time=df.index[10], exit_time=df.index[20],
                     result_r=1.0, outcome="win")
    monkeypatch.setattr(cf, "analyze", lambda *a, **k: _cr())

    out = cbt.replay_with_confluence(df, "XAUUSD", [trade])
    assert out[0]["status"] == "error"


def test_replay_error_when_bar_too_early_for_full_window(monkeypatch):
    """A signal in the first `window` bars has no full lookback slice
    available -- must be reported as an error, not silently truncated."""
    df = _df()
    trade = _trade(df, 10)   # far too early for WINDOW=6000
    monkeypatch.setattr(cf, "analyze", lambda *a, **k: _cr())

    out = cbt.replay_with_confluence(df, "XAUUSD", [trade])
    assert out[0]["status"] == "error"


def test_replay_never_raises_even_if_confluence_breaks(monkeypatch):
    df = _df()
    trade = _trade(df, bt.WINDOW + 100)
    monkeypatch.setattr(cf, "analyze", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    out = cbt.replay_with_confluence(df, "XAUUSD", [trade])   # must not raise
    assert out[0]["status"] == "error"


def test_replay_never_drops_a_trade():
    """Every input trade produces exactly one output row, whatever happens."""
    df = _df()
    trades = [_trade(df, bt.WINDOW + 50), _trade(df, bt.WINDOW + 150)]
    out = cbt.replay_with_confluence(df, "XAUUSD", trades)
    assert len(out) == len(trades)


# --------------------------------------------------------------------------
# would_qualify
# --------------------------------------------------------------------------

def test_would_qualify_true_above_threshold():
    row = {"status": "ok", "hard_gate_rejected": False, "base_tier": "confirmed", "score": 75}
    assert cbt.would_qualify(row, 70) is True


def test_would_qualify_false_below_threshold():
    row = {"status": "ok", "hard_gate_rejected": False, "base_tier": "confirmed", "score": 60}
    assert cbt.would_qualify(row, 70) is False


def test_would_qualify_false_on_hard_gate_rejection_regardless_of_score():
    row = {"status": "ok", "hard_gate_rejected": True, "base_tier": "confirmed", "score": 95}
    assert cbt.would_qualify(row, 0) is False


def test_would_qualify_false_when_base_tier_not_confirmed():
    row = {"status": "ok", "hard_gate_rejected": False, "base_tier": "watch", "score": 95}
    assert cbt.would_qualify(row, 0) is False


def test_would_qualify_false_on_non_ok_status():
    assert cbt.would_qualify({"status": "mismatch"}, 0) is False
    assert cbt.would_qualify({"status": "error"}, 0) is False


def test_would_qualify_never_raises_on_garbage():
    assert cbt.would_qualify(None, 70) is False
    assert cbt.would_qualify({}, 70) is False


# --------------------------------------------------------------------------
# compare_thresholds
# --------------------------------------------------------------------------

def test_compare_thresholds_higher_bar_never_admits_more_trades(monkeypatch):
    df = _df()
    trades = [_trade(df, bt.WINDOW + 50 + k * 10, outcome="win", result_r=1.0) for k in range(5)]
    scores = [40, 55, 65, 72, 90]

    def fake_analyze(df_slice, symbol="XAUUSD", min_score=cf.DEFAULT_MIN_SCORE):
        idx = list(df.index).index(df_slice.index[-1])
        k = (idx - bt.WINDOW - 50) // 10
        return _cr(score=scores[k])

    monkeypatch.setattr(cf, "analyze", fake_analyze)
    out = cbt.compare_thresholds(df, "XAUUSD", trades, thresholds=(0, 60, 70, 95))

    counts = {th: out["by_threshold"][th]["trades"] for th in (0, 60, 70, 95)}
    assert counts[0] >= counts[60] >= counts[70] >= counts[95]
    assert counts[0] == 5     # every trade qualifies at threshold 0
    assert counts[95] == 0    # nothing scored >= 95


def test_compare_thresholds_reports_replay_status_counts(monkeypatch):
    df = _df()
    trades = [_trade(df, bt.WINDOW + 50)]
    monkeypatch.setattr(cf, "analyze", lambda *a, **k: _cr(score=80))
    out = cbt.compare_thresholds(df, "XAUUSD", trades, thresholds=(70,))
    assert out["replay_status_counts"]["ok"] == 1
    assert out["total_trades_replayed"] == 1


def test_compare_thresholds_never_raises_on_empty_trade_list():
    df = _df()
    out = cbt.compare_thresholds(df, "XAUUSD", [], thresholds=(50, 70))
    assert out["total_trades_replayed"] == 0
    assert out["by_threshold"][50]["trades"] == 0
