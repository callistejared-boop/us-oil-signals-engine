"""Offline tests for hourly_briefing.apply_risk_gate() — the Day 3 Phase 8
defense-in-depth suppression that closes the risk-bypass finding (F01)
without needing to drive markets.fetch/Telegram/journal.settle side effects
through the real main() loop. See hourly_briefing.py's module docstring and
RISK_SPECIFICATION.md Sec.6.
"""
import pathlib
import sys
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import hourly_briefing as hb  # noqa: E402


def _raw(tier="confirmed", direction="long", entry=2000.0, stop=1990.0):
    return SimpleNamespace(tier=tier, direction=direction, entry=entry, stop=stop)


class _Settings:
    portfolio_risk_mode = "block"


def test_non_confirmed_signal_passes_through_untouched():
    raw = _raw(tier="watch")
    sig, held, ev = hb.apply_risk_gate("XAUUSD", raw, _Settings(), guard={})
    assert sig is raw and held == "" and ev is None


def test_none_signal_passes_through():
    sig, held, ev = hb.apply_risk_gate("XAUUSD", None, _Settings(), guard={})
    assert sig is None and held == "" and ev is None


def test_news_blackout_suppresses_confirmed_signal():
    raw = _raw()
    sig, held, ev = hb.apply_risk_gate("XAUUSD", raw, _Settings(), guard={"blackout": True})
    assert sig is None
    assert "imminent high-impact news" in held
    assert ev is None   # pre-existing behavior, unchanged by Day 3


def test_risk_guard_lock_suppresses_confirmed_signal(monkeypatch):
    raw = _raw()
    monkeypatch.setattr(hb.risk_guard, "evaluate",
                        lambda sym: {"locked": True, "reason": "DAILY LOSS LOCK: -2.0R",
                                     "day_r": -2.0, "open_n": 0})
    sig, held, ev = hb.apply_risk_gate("XAUUSD", raw, _Settings(), guard={})
    assert sig is None
    assert "risk_guard is locked" in held
    assert ev["category"] == "risk_guard"


def test_portfolio_risk_rejection_suppresses_confirmed_signal(monkeypatch):
    raw = _raw()
    monkeypatch.setattr(hb.risk_guard, "evaluate",
                        lambda sym: {"locked": False, "reason": "clear", "day_r": 0.0, "open_n": 0})
    monkeypatch.setattr(hb.pr, "evaluate",
                        lambda *a, **kw: {"allow": False, "would_block": True,
                                          "category": "portfolio_exposure_exceeded",
                                          "reason": "would breach the 6% cap"})
    sig, held, ev = hb.apply_risk_gate("XAUUSD", raw, _Settings(), guard={})
    assert sig is None
    assert "portfolio risk engine would reject" in held
    assert ev["category"] == "portfolio_exposure_exceeded"


def test_portfolio_warn_mode_shows_signal_but_logs(monkeypatch):
    raw = _raw()
    monkeypatch.setattr(hb.risk_guard, "evaluate",
                        lambda sym: {"locked": False, "reason": "clear", "day_r": 0.0, "open_n": 0})
    monkeypatch.setattr(hb.pr, "evaluate",
                        lambda *a, **kw: {"allow": True, "would_block": True,
                                          "category": "portfolio_exposure_exceeded",
                                          "reason": "would have breached the cap"})
    sig, held, ev = hb.apply_risk_gate("XAUUSD", raw, _Settings(), guard={})
    assert sig is raw           # warn mode: signal still shown
    assert held == ""
    assert ev["event"] == "briefing_warn"


def test_clean_pass_shows_signal(monkeypatch):
    raw = _raw()
    monkeypatch.setattr(hb.risk_guard, "evaluate",
                        lambda sym: {"locked": False, "reason": "clear", "day_r": 0.0, "open_n": 0})
    monkeypatch.setattr(hb.pr, "evaluate",
                        lambda *a, **kw: {"allow": True, "would_block": False,
                                          "category": None, "reason": "portfolio checks clear"})
    sig, held, ev = hb.apply_risk_gate("XAUUSD", raw, _Settings(), guard={})
    assert sig is raw and held == "" and ev is None


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)
