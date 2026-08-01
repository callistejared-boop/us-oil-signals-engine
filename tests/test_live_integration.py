"""Guard: live alerter surfaces news-adjusted grade + confidence.

The displayed GRADE is MAST confluence-based (score + final_tier), not raw
ICT confidence — build_prealert/build_entry take an optional `confluence`
object (duck-typed: .score, .final_tier) and derive the grade from it via
engine.grade, same as wti_note.py and the live dashboard."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import alert_signals as al  # noqa: E402
from engine import bias_adjust as ba  # noqa: E402


class _Sig:
    symbol = "WTIUSD"; direction = "long"; confidence = 84; tier = "confirmed"; prob = 72
    entry = 73.9; stop = 73.6; target = 74.8; rr = 3.0
    reasons = ["bull BOS", "OTE tap"]


class _CR:
    """Minimal stand-in for a confluence.ConfluenceRead."""
    def __init__(self, score, final_tier="confirmed"):
        self.score = score
        self.final_tier = final_tier


def test_prealert_shows_grade_and_news(monkeypatch):
    monkeypatch.setattr(ba, "apply_context", lambda *a, **k: (90, 6, "news BUY (HIGH) agrees with long (+6); session London kill zone (+4)"))
    r = {"session": "NY", "biases": {"1d": "bull", "4h": "bull", "1h": "bull", "15m": "bull"}}
    msg = al.build_prealert(_Sig(), r, confluence=_CR(95))  # 95/100 confirmed -> A+
    assert "GRADE A+" in msg
    assert "84->90/100" in msg and "+6 news" in msg
    assert "news:" in msg
    assert "MAST confluence: 95/100" in msg


def test_prealert_no_news_line_when_zero(monkeypatch):
    monkeypatch.setattr(ba, "apply_context", lambda *a, **k: (84, 0, "no fresh directional news; session off-hours (+0)"))
    r = {"session": "NY", "biases": {"1d": "bull", "4h": "bull", "1h": "bull", "15m": "bull"}}
    msg = al.build_prealert(_Sig(), r, confluence=_CR(85))  # 85/100 confirmed -> A
    assert "GRADE A" in msg and "+0 news" in msg and "+0 guard" in msg
    assert "\nnews:" not in msg  # suppressed when delta 0
    assert "RANGE GUARD" not in msg  # no guard warning when guard is clear/absent


def test_prealert_guard_caps_grade_and_warns(monkeypatch):
    monkeypatch.setattr(ba, "apply_context", lambda *a, **k: (92, 8, "news BUY (HIGH) agrees with long (+6); NY kill zone (+4)"))
    r = {"session": "NY", "biases": {"1d": "bull", "4h": "bull", "1h": "bull", "15m": "bull"}}
    guard = {"action": "downgrade", "penalty": -14, "grade_cap": "C (chase)",
             "note": "long chasing range-high", "macro_headwind": True}
    msg = al.build_prealert(_Sig(), r, guard, confluence=_CR(95))  # A+ capped down by the guard
    assert "GRADE C (chase)" in msg
    assert "-14 guard" in msg            # guard penalty surfaced in the conf line
    assert "RANGE GUARD" in msg          # explicit warning line present


def test_prealert_without_confluence_falls_back_gracefully(monkeypatch):
    """No confluence object available (engine error) -> still renders, no crash."""
    monkeypatch.setattr(ba, "apply_context", lambda *a, **k: (84, 0, "no fresh directional news; session off-hours (+0)"))
    r = {"session": "NY", "biases": {"1d": "bull", "4h": "bull", "1h": "bull", "15m": "bull"}}
    msg = al.build_prealert(_Sig(), r)
    assert "GRADE" in msg
    assert "MAST confluence" not in msg
