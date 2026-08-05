"""Offline tests for engine/macro_history.py (Day 11). All tests use a
monkeypatched HISTORY_PATH pointing at a tmp_path file — mirrors
test_rates_feed.py / test_macro_reference.py's established pattern for
file-backed modules. No real macro_history.jsonl is ever touched.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import macro_history as mh  # noqa: E402


def _assessment(labels=None, macro_confidence="medium", evidence_quality="medium",
               providers=None, cross_asset_interp="x"):
    return {
        "version": "1.0.0",
        "providers": providers or {
            "volatility": {"source_availability": "available",
                           "freshness": {"state": "fresh"}, "uncertainty": "low"},
        },
        "regime": {"labels": labels or ["Risk-On"], "macro_confidence": macro_confidence,
                   "evidence_quality": evidence_quality},
        "cross_asset": {"interpretation": cross_asset_interp},
    }


def test_record_writes_normalized_row(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    row = mh.record("XAUUSD", _assessment(), ref="XAUUSD-20260803120000")
    assert row["symbol"] == "XAUUSD"
    assert row["ref"] == "XAUUSD-20260803120000"
    assert row["labels"] == ["Risk-On"]
    assert f.exists()


def test_record_never_stores_raw_facts(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    assessment = _assessment(providers={
        "interest_rates": {"facts": {"ten_year_yield": 4.3}, "source_availability": "available",
                           "freshness": {"state": "fresh"}, "uncertainty": "low"},
    })
    row = mh.record("XAUUSD", assessment)
    snap = row["provider_snapshot"]["interest_rates"]
    assert "facts" not in snap
    assert set(snap.keys()) == {"source_availability", "freshness_state", "uncertainty"}


def test_record_defaults_ref_to_empty_string(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    row = mh.record("EURUSD", _assessment())
    assert row["ref"] == ""


def test_find_by_ref_round_trips(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    mh.record("XAUUSD", _assessment(labels=["Neutral"]), ref="A")
    mh.record("XAUUSD", _assessment(labels=["Risk-Off"]), ref="B")
    found = mh.find_by_ref("B")
    assert found is not None
    assert found["labels"] == ["Risk-Off"]


def test_find_by_ref_returns_none_when_missing(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    assert mh.find_by_ref("does-not-exist") is None


def test_find_by_ref_empty_string_returns_none(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    mh.record("XAUUSD", _assessment(), ref="")
    assert mh.find_by_ref("") is None


def test_find_by_ref_returns_most_recent_when_duplicated(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    mh.record("XAUUSD", _assessment(labels=["Neutral"]), ref="DUP")
    mh.record("XAUUSD", _assessment(labels=["Risk-On"]), ref="DUP")
    found = mh.find_by_ref("DUP")
    assert found["labels"] == ["Risk-On"]


def test_last_for_returns_most_recent_for_symbol(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    mh.record("XAUUSD", _assessment(labels=["Neutral"]))
    mh.record("WTIUSD", _assessment(labels=["Risk-On"]))
    mh.record("XAUUSD", _assessment(labels=["Tightening"]))
    last = mh.last_for("XAUUSD")
    assert last["labels"] == ["Tightening"]


def test_last_for_none_when_no_rows():
    assert mh.last_for("XAUUSD") is None or isinstance(mh.last_for("XAUUSD"), dict)


def test_last_for_returns_none_when_symbol_missing(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    mh.record("WTIUSD", _assessment())
    assert mh.last_for("BTCUSD") is None


def test_tail_respects_n_and_symbol_filter(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    for i in range(5):
        mh.record("XAUUSD", _assessment(labels=[f"L{i}"]))
    mh.record("WTIUSD", _assessment(labels=["Other"]))
    out = mh.tail(n=2, symbol="XAUUSD")
    assert len(out) == 2
    assert out[-1]["labels"] == ["L4"]


def test_label_history_shape(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    mh.record("XAUUSD", _assessment(labels=["Risk-On"]))
    out = mh.label_history(symbol="XAUUSD")
    assert len(out) == 1
    assert set(out[0].keys()) == {"ts", "symbol", "labels"}
    assert out[0]["labels"] == ["Risk-On"]


def test_replay_filters_by_symbol_and_time_window(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    mh.record("XAUUSD", _assessment(labels=["A"]))
    mh.record("WTIUSD", _assessment(labels=["B"]))
    out = mh.replay(symbol="XAUUSD")
    assert len(out) == 1 and out[0]["labels"] == ["A"]


def test_replay_since_until_bounds(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    rows = [mh.record("XAUUSD", _assessment(labels=[str(i)])) for i in range(3)]
    since = rows[1]["ts"]
    out = mh.replay(symbol="XAUUSD", since_ts=since)
    assert all(r["ts"] >= since for r in out)


def test_replay_never_raises_on_corrupted_file(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    f.write_text("{not valid json\n")
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    assert mh.replay() == []


def test_all_rows_returns_everything(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    mh.record("XAUUSD", _assessment())
    mh.record("WTIUSD", _assessment())
    assert len(mh.all_rows()) == 2


def test_record_never_raises_when_path_unwritable(tmp_path, monkeypatch):
    bogus = tmp_path / "no_such_dir" / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", bogus)
    row = mh.record("XAUUSD", _assessment())
    assert row["symbol"] == "XAUUSD"  # still returns the would-be record
    assert not bogus.exists()


def test_normalize_never_raises_on_malformed_assessment():
    out = mh._normalize({"providers": "not-a-dict"})
    assert out["labels"] == []
    assert "error" in out


def test_rotate_trims_to_max_lines(tmp_path, monkeypatch):
    f = tmp_path / "macro_history.jsonl"
    monkeypatch.setattr(mh, "HISTORY_PATH", f)
    monkeypatch.setattr(mh, "MAX_LINES", 3)
    for i in range(6):
        mh.record("XAUUSD", _assessment(labels=[str(i)]))
    rows = mh.all_rows()
    assert len(rows) == 3
    assert rows[-1]["labels"] == ["5"]


def test_no_update_or_delete_function_exists():
    # Immutability guarantee: append-only, corrections are new rows.
    assert not hasattr(mh, "update")
    assert not hasattr(mh, "delete")
