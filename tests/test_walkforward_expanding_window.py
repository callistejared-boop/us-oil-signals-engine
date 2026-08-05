"""Offline tests for engine/walkforward.py's Day 9 addition,
expanding_window_series() — the generalized walk-forward methodology.
Existing walkforward.py tests (test_walkforward.py) are untouched; this is
a separate file for the new, additive function only.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import walkforward as wf  # noqa: E402


def _mk(i, r):
    return {"opened": f"2026-01-01 {i//60:02d}:{i%60:02d}:00", "confidence": 80,
           "status": "win" if r > 0 else "loss", "result_r": r}


def test_expanding_window_basic_shape():
    data = [_mk(i, 1.0 if i % 2 == 0 else -1.0) for i in range(50)]
    series = wf.expanding_window_series(lambda train: len(train), data, min_train=30)
    assert len(series) == 20   # trades 30..49
    assert series[0]["i"] == 30
    assert series[0]["value"] == 30   # train set size at i=30 is exactly 30
    assert series[-1]["value"] == 49  # train set size at i=49 is 49


def test_expanding_window_never_includes_current_or_future_trade():
    """The look-ahead-safety proof: metric_fn only ever sees trades
    strictly before i."""
    seen_max_i = []

    def probe(train):
        seen_max_i.append(len(train))
        return len(train)

    data = [_mk(i, 1.0) for i in range(40)]
    wf.expanding_window_series(probe, data, min_train=30)
    # train size at step i should be exactly i (0..i-1), never i or more
    for step_idx, n in enumerate(seen_max_i):
        assert n == 30 + step_idx


def test_expanding_window_respects_window_size_for_rolling_behavior():
    data = [_mk(i, 1.0) for i in range(60)]
    series = wf.expanding_window_series(lambda train: len(train), data, min_train=30, window_size=10)
    assert all(s["value"] <= 10 for s in series)
    assert series[-1]["value"] == 10


def test_expanding_window_metric_error_is_isolated_not_fatal():
    data = [_mk(i, 1.0) for i in range(35)]

    def flaky(train):
        if len(train) == 32:
            raise ValueError("boom")
        return 1.0

    series = wf.expanding_window_series(flaky, data, min_train=30)
    errored = [s for s in series if "error" in s]
    assert len(errored) == 1
    assert errored[0]["value"] is None
    # every other step still produced a value
    assert sum(1 for s in series if s.get("value") == 1.0) == len(series) - 1


def test_expanding_window_empty_when_below_min_train():
    data = [_mk(i, 1.0) for i in range(10)]
    series = wf.expanding_window_series(lambda train: 1, data, min_train=30)
    assert series == []
