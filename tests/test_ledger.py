import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from engine import ledger


def test_log_and_tail(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER", tmp_path / "l.jsonl")
    ledger.log({"event": "heads_up", "symbol": "WTIUSD", "dir": "long"})
    ledger.log({"event": "entry", "symbol": "XAUUSD", "dir": "short"})
    got = ledger.tail(5)
    assert len(got) == 2 and got[-1]["symbol"] == "XAUUSD" and "ts" in got[0]


def test_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER", tmp_path / "l.jsonl")
    monkeypatch.setattr(ledger, "MAX_LINES", 10)
    for i in range(25):
        ledger.log({"i": i})
    assert len(ledger.tail(999)) <= 11


def test_bad_event_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER", tmp_path / "l.jsonl")
    ledger.log(None)  # must not raise
    assert ledger.tail() == [] or isinstance(ledger.tail(), list)
