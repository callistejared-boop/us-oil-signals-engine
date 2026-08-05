"""Offline tests for engine/regime_history.py (Day 4). All tests point
HISTORY_PATH at a tmp_path file via monkeypatch so nothing touches the real
repo's regime_history.jsonl.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import regime_history as rh  # noqa: E402


def _result(primary="Strong Bull Trend", confidence=70, quality=75,
           tr_risk=0.2, tr_label="low"):
    return {"primary": primary, "confidence": confidence, "quality_score": quality,
            "transition_risk": tr_risk, "transition_label": tr_label}


def test_record_writes_and_last_for_reads_back(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    rec = rh.record("XAUUSD", "strategic", _result())
    assert rec["symbol"] == "XAUUSD"
    assert rec["primary"] == "Strong Bull Trend"
    assert rec["transition_event"] is False   # first-ever record, nothing to transition from
    last = rh.last_for("XAUUSD", "strategic")
    assert last["primary"] == "Strong Bull Trend"


def test_transition_event_detected_on_primary_change(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    rh.record("XAUUSD", "strategic", _result(primary="Range"))
    rec2 = rh.record("XAUUSD", "strategic", _result(primary="Strong Bull Trend"))
    assert rec2["transition_event"] is True
    assert rec2["transition_from"] == "Range"


def test_no_transition_event_when_primary_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    rh.record("XAUUSD", "strategic", _result(primary="Range"))
    rec2 = rh.record("XAUUSD", "strategic", _result(primary="Range"))
    assert rec2["transition_event"] is False
    assert rec2["transition_from"] is None


def test_duration_since_prev_is_computed(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    rh.record("XAUUSD", "strategic", _result())
    rec2 = rh.record("XAUUSD", "strategic", _result())
    assert rec2["duration_s_since_prev"] is not None
    assert rec2["duration_s_since_prev"] >= 0


def test_symbols_are_isolated_from_each_other(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    rh.record("XAUUSD", "strategic", _result(primary="Range"))
    rec = rh.record("WTIUSD", "strategic", _result(primary="Strong Bull Trend"))
    # WTIUSD has no prior history of its own -> not a transition, even though
    # XAUUSD's last recorded primary differs.
    assert rec["transition_event"] is False
    assert rh.last_for("WTIUSD", "strategic")["primary"] == "Strong Bull Trend"
    assert rh.last_for("XAUUSD", "strategic")["primary"] == "Range"


def test_tail_returns_most_recent_n(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    for i in range(5):
        rh.record("XAUUSD", "strategic", _result(primary=f"Range{i}"))
    out = rh.tail(2, symbol="XAUUSD")
    assert len(out) == 2
    assert out[-1]["primary"] == "Range4"


def test_transitions_filters_to_transition_events_only(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    rh.record("XAUUSD", "strategic", _result(primary="Range"))
    rh.record("XAUUSD", "strategic", _result(primary="Range"))         # no transition
    rh.record("XAUUSD", "strategic", _result(primary="Strong Bull Trend"))  # transition
    out = rh.transitions(symbol="XAUUSD")
    assert len(out) == 1
    assert out[0]["transition_from"] == "Range"


def test_rotation_caps_at_max_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "regime_history.jsonl")
    monkeypatch.setattr(rh, "MAX_LINES", 10)
    for i in range(25):
        rh.record("XAUUSD", "strategic", _result(primary=f"R{i}"))
    lines = (tmp_path / "regime_history.jsonl").read_text().splitlines()
    assert len(lines) <= 10


def test_record_never_raises_on_unwritable_path(tmp_path, monkeypatch):
    # Point HISTORY_PATH at a path inside a nonexistent directory - the
    # write must fail silently (fail-safe), never raise, matching
    # ledger.py's own "a logging error must never disrupt trading logic".
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "does" / "not" / "exist" / "h.jsonl")
    rec = rh.record("XAUUSD", "strategic", _result())
    assert rec["symbol"] == "XAUUSD"   # still returns the record even though the write failed


def test_last_for_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(rh, "HISTORY_PATH", tmp_path / "nope.jsonl")
    assert rh.last_for("XAUUSD", "strategic") is None


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)
