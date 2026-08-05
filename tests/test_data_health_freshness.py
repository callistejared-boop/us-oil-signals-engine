import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.data_health import freshness as fr  # noqa: E402


def test_classify_fresh():
    assert fr.classify(5, 20) == fr.FRESH


def test_classify_aging():
    assert fr.classify(25, 20) == fr.AGING  # 1.25x expected


def test_classify_stale():
    assert fr.classify(50, 20) == fr.STALE  # 2.5x expected


def test_classify_expired():
    assert fr.classify(100, 20) == fr.EXPIRED  # 5x expected


def test_classify_unknown_on_none_age():
    assert fr.classify(None, 20) == fr.UNKNOWN


def test_classify_unknown_on_missing_expected():
    assert fr.classify(5, None) == fr.UNKNOWN
    assert fr.classify(5, 0) == fr.UNKNOWN


def test_classify_unknown_on_negative_age():
    assert fr.classify(-5, 20) == fr.UNKNOWN


def test_classify_never_raises_on_garbage():
    assert fr.classify("not a number", 20) == fr.UNKNOWN
    assert fr.classify(5, "also not a number") == fr.UNKNOWN


def test_age_minutes_from_mtime_missing_file(data_health_paths):
    age = fr.age_minutes_from_mtime("nonexistent.pkl")
    assert age is None


def test_age_minutes_from_mtime_existing_file(data_health_paths):
    tmp = data_health_paths["tmp_path"]
    p = tmp / "somefile.json"
    p.write_text("{}", encoding="utf-8")
    age = fr.age_minutes_from_mtime("somefile.json")
    assert age is not None
    assert age < 1.0  # just written


def test_age_minutes_from_json_field_missing_file(data_health_paths):
    assert fr.age_minutes_from_json_field("missing.json", "generated") is None


def test_age_minutes_from_json_field_missing_field(data_health_paths):
    tmp = data_health_paths["tmp_path"]
    (tmp / "cache.json").write_text(json.dumps({"other": 1}), encoding="utf-8")
    assert fr.age_minutes_from_json_field("cache.json", "generated") is None


def test_age_minutes_from_json_field_valid_iso(data_health_paths):
    tmp = data_health_paths["tmp_path"]
    ts = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(timespec="seconds")
    (tmp / "cache.json").write_text(json.dumps({"generated": ts}), encoding="utf-8")
    age = fr.age_minutes_from_json_field("cache.json", "generated")
    assert age is not None
    assert 28 <= age <= 32


def test_age_minutes_from_json_field_malformed_never_raises(data_health_paths):
    tmp = data_health_paths["tmp_path"]
    (tmp / "cache.json").write_text("not valid json{{{", encoding="utf-8")
    assert fr.age_minutes_from_json_field("cache.json", "generated") is None


def test_freshness_block_shape():
    block = fr.freshness_block(10, 20)
    assert set(block.keys()) == {"age_minutes", "expected_freshness_minutes", "state"}
    assert block["state"] == fr.FRESH


def test_freshness_block_state_override():
    block = fr.freshness_block(None, None, state_override="reference_data")
    assert block["state"] == "reference_data"


def test_record_and_read_observation(data_health_paths):
    fr.record_observation("news_calendar", True, "ok")
    row = fr.last_observation("news_calendar")
    assert row is not None
    assert row["ok"] is True
    assert row["feed_id"] == "news_calendar"


def test_observation_most_recent_wins(data_health_paths):
    fr.record_observation("news_calendar", True, "first")
    fr.record_observation("news_calendar", False, "second")
    row = fr.last_observation("news_calendar")
    assert row["detail"] == "second"
    assert row["ok"] is False


def test_last_observation_none_when_never_recorded(data_health_paths):
    assert fr.last_observation("never_seen_feed") is None


def test_age_minutes_from_observation_none_when_absent(data_health_paths):
    assert fr.age_minutes_from_observation("never_seen_feed") is None


def test_age_minutes_from_observation_recent(data_health_paths):
    fr.record_observation("news_calendar", True, "ok")
    age = fr.age_minutes_from_observation("news_calendar")
    assert age is not None
    assert age < 1.0


def test_record_observation_never_raises(data_health_paths, monkeypatch):
    # Point OBSERVATIONS_PATH at an unwritable location to force a failure
    monkeypatch.setattr(fr, "OBSERVATIONS_PATH", pathlib.Path("/nonexistent_dir_xyz/obs.jsonl"))
    fr.record_observation("news_calendar", True, "ok")  # must not raise
