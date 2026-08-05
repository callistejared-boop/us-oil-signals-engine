"""Offline tests for confidence_calibration.raw_vs_composite_comparison()
(Day 7 addendum, per the platform owner's explicit decision: "Build a
raw-vs-composite calibration view — yes, but not yet. Design the
architecture now; keep it inactive until enough live observations exist.")
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import confidence_calibration as cc  # noqa: E402


def test_inactive_when_insufficient_matched_trades(monkeypatch):
    monkeypatch.setattr(cc, "join_trades_with_confidence", lambda: [
        {"overall_confidence": 75, "outcome": 1.0}])
    out = cc.raw_vs_composite_comparison()
    assert out["active"] is False
    assert out["n"] == 1
    assert "reason" in out and out["reason"]
    assert out["raw"] is None and out["composite"] is None


def test_active_when_sufficient_matched_trades(monkeypatch):
    joined = [{"overall_confidence": 75, "outcome": 1.0 if i < 20 else 0.0} for i in range(30)]
    monkeypatch.setattr(cc, "join_trades_with_confidence", lambda: joined)

    from engine import calibration as raw_cal
    monkeypatch.setattr(raw_cal, "brier", lambda: 0.20)
    monkeypatch.setattr(raw_cal, "reliability",
                        lambda: [{"bucket": "70-79", "predicted": 0.75, "realized": 0.55, "n": 30}])

    out = cc.raw_vs_composite_comparison(min_n=30)
    assert out["active"] is True
    assert out["n"] == 30
    assert out["composite"]["brier"] is not None
    assert out["raw"]["brier"] == 0.20
    assert isinstance(out["composite_improves_on_raw"], bool)


def test_never_raises_on_garbage(monkeypatch):
    monkeypatch.setattr(cc, "join_trades_with_confidence", lambda: [{"bad": "row"}] * 40)
    out = cc.raw_vs_composite_comparison()
    assert isinstance(out, dict)
    assert "active" in out


def test_not_wired_into_any_live_report_yet():
    """Confirms the 'inactive/not surfaced' part of the owner's decision
    structurally: report() (the function actually shown to operators today)
    must not call raw_vs_composite_comparison()."""
    import inspect
    src = inspect.getsource(cc.report)
    assert "raw_vs_composite_comparison" not in src
