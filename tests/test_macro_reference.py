"""Offline tests for engine/macro_reference.py (Day 11). All tests use a
monkeypatched REFERENCE_PATH pointing at a tmp_path file — no real
config/production file is ever touched.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import macro_reference as mref  # noqa: E402


def test_central_bank_stance_not_configured_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(mref, "REFERENCE_PATH", tmp_path / "missing.json")
    out = mref.central_bank_stance("Federal Reserve")
    assert out["configured"] is False
    assert out["stance"] == "unknown"


def test_central_bank_stance_configured_when_populated(tmp_path, monkeypatch):
    data = {"central_banks": {"Federal Reserve": {
        "stance": "restrictive", "expected_direction": "hold",
        "uncertainty": "medium", "next_scheduled_event": "2026-09-17",
        "updated": "2026-08-01T00:00:00+00:00", "source": "FOMC statement",
        "example": False}}}
    f = tmp_path / "macro_reference.json"
    f.write_text(json.dumps(data))
    monkeypatch.setattr(mref, "REFERENCE_PATH", f)
    out = mref.central_bank_stance("Federal Reserve")
    assert out["configured"] is True
    assert out["stance"] == "restrictive"


def test_central_bank_stance_example_entry_reported_as_not_configured(tmp_path, monkeypatch):
    data = {"central_banks": {"ECB": {"stance": "x", "expected_direction": "x",
                                      "uncertainty": "x", "example": True}}}
    f = tmp_path / "macro_reference.json"
    f.write_text(json.dumps(data))
    monkeypatch.setattr(mref, "REFERENCE_PATH", f)
    out = mref.central_bank_stance("ECB")
    assert out["configured"] is False


def test_all_central_bank_stances_covers_all_five(tmp_path, monkeypatch):
    monkeypatch.setattr(mref, "REFERENCE_PATH", tmp_path / "missing.json")
    out = mref.all_central_bank_stances()
    assert set(out.keys()) == set(mref.CENTRAL_BANKS)


def test_geopolitical_flags_filters_by_symbol(tmp_path, monkeypatch):
    data = {"geopolitical_flags": [
        {"category": "energy_supply_disruption", "affected_assets": ["WTIUSD"], "example": False},
        {"category": "sanctions", "affected_assets": ["XAUUSD", "EURUSD"], "example": False},
    ]}
    f = tmp_path / "macro_reference.json"
    f.write_text(json.dumps(data))
    monkeypatch.setattr(mref, "REFERENCE_PATH", f)
    assert len(mref.geopolitical_flags("WTIUSD")) == 1
    assert len(mref.geopolitical_flags("XAUUSD")) == 1
    assert len(mref.geopolitical_flags("BTCUSD")) == 0
    assert len(mref.geopolitical_flags()) == 2


def test_economic_print_not_configured_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(mref, "REFERENCE_PATH", tmp_path / "missing.json")
    out = mref.economic_print("CPI")
    assert out["configured"] is False


def test_economic_print_configured(tmp_path, monkeypatch):
    data = {"economic_prints": {"CPI": {"last_value": 3.1, "prior_value": 3.3,
                                        "period": "2026-07", "surprise": "in-line",
                                        "updated": "2026-08-01T00:00:00+00:00",
                                        "source": "BLS", "example": False}}}
    f = tmp_path / "macro_reference.json"
    f.write_text(json.dumps(data))
    monkeypatch.setattr(mref, "REFERENCE_PATH", f)
    out = mref.economic_print("CPI")
    assert out["configured"] is True and out["last_value"] == 3.1


def test_ensure_reference_file_does_not_overwrite_existing(tmp_path, monkeypatch):
    f = tmp_path / "macro_reference.json"
    f.write_text(json.dumps({"custom": True}))
    monkeypatch.setattr(mref, "REFERENCE_PATH", f)
    mref.ensure_reference_file()
    assert json.loads(f.read_text()) == {"custom": True}


def test_ensure_reference_file_writes_default_when_missing(tmp_path, monkeypatch):
    f = tmp_path / "macro_reference.json"
    monkeypatch.setattr(mref, "REFERENCE_PATH", f)
    mref.ensure_reference_file()
    assert f.exists()
    data = json.loads(f.read_text())
    assert "central_banks" in data and "geopolitical_flags" in data


def test_update_central_bank_writes_and_marks_not_example(tmp_path, monkeypatch):
    f = tmp_path / "macro_reference.json"
    monkeypatch.setattr(mref, "REFERENCE_PATH", f)
    result = mref.update_central_bank("BOJ", stance="ultra-easy", expected_direction="hold",
                                      uncertainty="low", source="BOJ statement")
    assert result["ok"] is True
    out = mref.central_bank_stance("BOJ")
    assert out["configured"] is True and out["stance"] == "ultra-easy"


def test_functions_never_raise_on_corrupted_file(tmp_path, monkeypatch):
    f = tmp_path / "macro_reference.json"
    f.write_text("{not valid json")
    monkeypatch.setattr(mref, "REFERENCE_PATH", f)
    assert mref.central_bank_stance("Federal Reserve")["configured"] in (True, False)
    assert mref.geopolitical_flags() == [] or isinstance(mref.geopolitical_flags(), list)
    assert mref.economic_print("CPI")["configured"] in (True, False)
