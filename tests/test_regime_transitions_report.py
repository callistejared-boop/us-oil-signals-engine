"""Offline tests for engine/regime_transitions_report.py (V2.2 Priority 3:
regime transition reporting -- a thin formatting/query layer over
engine/regime_history.py's ALREADY-EXISTING transition detection, not a
new detection mechanism).

Tests point regime_history.HISTORY_PATH at a tmp_path file via monkeypatch
(same pattern tests/test_regime_history.py itself uses), so nothing
touches the real repo's regime_history.jsonl."""
import pathlib
import sys
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import regime_history as rh  # noqa: E402
from engine import regime_transitions_report as rtr  # noqa: E402


def _result(primary="Strong Bull Trend", confidence=70, quality=75,
           tr_risk=0.2, tr_label="low"):
    return {"primary": primary, "confidence": confidence, "quality_score": quality,
            "transition_risk": tr_risk, "transition_label": tr_label}


# --------------------------------------------------------------------------
# format_transition
# --------------------------------------------------------------------------

def test_format_transition_full_row():
    row = {"symbol": "XAUUSD", "transition_from": "Range", "primary": "Distribution",
          "ts": "2026-08-12T10:00:00+00:00", "duration_s_since_prev": 5400}
    line = rtr.format_transition(row)
    assert "XAUUSD" in line
    assert "Range -> Distribution" in line
    assert "1.5h" in line
    assert "2026-08-12T10:00:00+00:00" in line


def test_format_transition_short_duration_shown_in_minutes():
    row = {"symbol": "WTIUSD", "transition_from": "Accumulation", "primary": "Range",
          "ts": "2026-08-12T10:00:00+00:00", "duration_s_since_prev": 120}
    line = rtr.format_transition(row)
    assert "2min" in line


def test_format_transition_missing_fields_never_raises():
    line = rtr.format_transition({})
    assert "?" in line
    line2 = rtr.format_transition({"symbol": "BTCUSD"})
    assert "BTCUSD" in line2


def test_format_transition_missing_duration_falls_back():
    row = {"symbol": "XAUUSD", "transition_from": "Range", "primary": "Distribution",
          "ts": "2026-08-12T10:00:00+00:00", "duration_s_since_prev": None}
    line = rtr.format_transition(row)
    assert "from Range" in line


# --------------------------------------------------------------------------
# recent_transitions_summary -- integration against the REAL
# regime_history.py record()/transitions() (isolated to tmp_path)
# --------------------------------------------------------------------------

def test_recent_transitions_summary_empty_when_no_history(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    assert rtr.recent_transitions_summary() == []


def test_recent_transitions_summary_reflects_real_transition(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    rh.record("XAUUSD", "strategic", _result(primary="Range"))
    rh.record("XAUUSD", "strategic", _result(primary="Distribution"))
    summaries = rtr.recent_transitions_summary(symbol="XAUUSD")
    assert len(summaries) == 1
    assert "Range -> Distribution" in summaries[0]
    assert "XAUUSD" in summaries[0]


def test_recent_transitions_summary_excludes_non_transition_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    rh.record("XAUUSD", "strategic", _result(primary="Range"))
    rh.record("XAUUSD", "strategic", _result(primary="Range"))  # no change
    rh.record("XAUUSD", "strategic", _result(primary="Range"))  # no change
    assert rtr.recent_transitions_summary(symbol="XAUUSD") == []


def test_recent_transitions_summary_respects_symbol_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    rh.record("XAUUSD", "strategic", _result(primary="Range"))
    rh.record("XAUUSD", "strategic", _result(primary="Distribution"))
    rh.record("WTIUSD", "strategic", _result(primary="Range"))
    rh.record("WTIUSD", "strategic", _result(primary="Accumulation"))
    xau_only = rtr.recent_transitions_summary(symbol="XAUUSD")
    assert len(xau_only) == 1
    assert "XAUUSD" in xau_only[0]
    all_symbols = rtr.recent_transitions_summary(symbol=None)
    assert len(all_symbols) == 2


def test_recent_transitions_summary_respects_n_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    primaries = ["Range", "Distribution", "Range", "Accumulation", "Range"]
    for p in primaries:
        rh.record("XAUUSD", "strategic", _result(primary=p))
    summaries = rtr.recent_transitions_summary(symbol="XAUUSD", n=2)
    assert len(summaries) == 2


# --------------------------------------------------------------------------
# transition_frequency
# --------------------------------------------------------------------------

def test_transition_frequency_zero_when_no_transitions(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    out = rtr.transition_frequency("XAUUSD", hours=24)
    assert out["count"] == 0
    assert out["most_recent"] is None
    assert out["symbol"] == "XAUUSD"


def test_transition_frequency_counts_within_window(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    rh.record("XAUUSD", "strategic", _result(primary="Range"))
    rh.record("XAUUSD", "strategic", _result(primary="Distribution"))
    rh.record("XAUUSD", "strategic", _result(primary="Range"))
    out = rtr.transition_frequency("XAUUSD", hours=24)
    assert out["count"] == 2
    assert out["most_recent"] is not None
    assert "Distribution -> Range" in out["most_recent"]


def test_transition_frequency_excludes_events_outside_window(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    # Write one transition row directly with a stale timestamp (24h+ old),
    # bypassing record()'s "now" timestamp so the window-exclusion logic
    # can be tested deterministically.
    import json
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat(
        timespec="seconds")
    row = {"ts": stale_ts, "symbol": "XAUUSD", "timeframe": "strategic",
          "primary": "Distribution", "transition_event": True,
          "transition_from": "Range", "duration_s_since_prev": 100.0, "ref": ""}
    rh.HISTORY_PATH.write_text(json.dumps(row) + "\n", encoding="utf-8")
    out = rtr.transition_frequency("XAUUSD", hours=24)
    assert out["count"] == 0
    assert out["most_recent"] is None


def test_transition_frequency_never_raises_on_malformed_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    import json
    row = {"ts": "not-a-timestamp", "symbol": "XAUUSD", "timeframe": "strategic",
          "primary": "Distribution", "transition_event": True,
          "transition_from": "Range", "duration_s_since_prev": 100.0, "ref": ""}
    rh.HISTORY_PATH.write_text(json.dumps(row) + "\n", encoding="utf-8")
    out = rtr.transition_frequency("XAUUSD", hours=24)
    assert out["count"] == 0  # malformed row silently excluded, not raised
