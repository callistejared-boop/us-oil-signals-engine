import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.data_health import consistency as cons  # noqa: E402


def _ohlc_df(rows):
    import pandas as pd
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])


def test_check_ohlc_valid_data_is_none_severity():
    df = _ohlc_df([[100, 105, 99, 103, 1000] for _ in range(20)])
    result = cons.check_ohlc(df)
    assert result["severity"] == cons.NONE_
    assert sum(result["violations"].values()) == 0


def test_check_ohlc_detects_high_less_than_low():
    rows = [[100, 105, 99, 103, 1000] for _ in range(19)]
    rows.append([100, 90, 99, 103, 1000])  # high < low, impossible
    df = _ohlc_df(rows)
    result = cons.check_ohlc(df)
    assert result["violations"]["high_lt_low"] == 1
    assert result["severity"] != cons.NONE_


def test_check_ohlc_detects_negative_volume():
    rows = [[100, 105, 99, 103, 1000] for _ in range(19)]
    rows.append([100, 105, 99, 103, -50])
    df = _ohlc_df(rows)
    result = cons.check_ohlc(df)
    assert result["violations"]["negative_volume"] == 1


def test_check_ohlc_detects_non_positive_price():
    rows = [[100, 105, 99, 103, 1000] for _ in range(19)]
    rows.append([0, 105, 99, 103, 1000])
    df = _ohlc_df(rows)
    result = cons.check_ohlc(df)
    assert result["violations"]["non_positive_price"] == 1


def test_check_ohlc_empty_df_is_none_severity():
    import pandas as pd
    result = cons.check_ohlc(pd.DataFrame())
    assert result["severity"] == cons.NONE_


def test_check_ohlc_none_df_never_raises():
    result = cons.check_ohlc(None)
    assert result["severity"] == cons.NONE_


def test_check_ohlc_non_price_dataframe_skipped():
    import pandas as pd
    df = pd.DataFrame({"foo": [1, 2, 3]})
    result = cons.check_ohlc(df)
    assert result["severity"] == cons.NONE_
    assert "not a price dataframe" in result["detail"]


def test_check_ohlc_high_severity_ratio():
    rows = [[100, 90, 99, 103, 1000] for _ in range(50)]  # every row broken
    df = _ohlc_df(rows)
    result = cons.check_ohlc(df)
    assert result["severity"] == cons.CRITICAL


def test_check_duplicate_timestamps_none():
    import pandas as pd
    idx = pd.date_range("2026-01-01", periods=10, freq="15min")
    df = pd.DataFrame({"close": range(10)}, index=idx)
    result = cons.check_duplicate_timestamps(df)
    assert result["duplicate_count"] == 0
    assert result["severity"] == cons.NONE_


def test_check_duplicate_timestamps_detects_dupes():
    import pandas as pd
    idx = list(pd.date_range("2026-01-01", periods=9, freq="15min")) + \
          [pd.Timestamp("2026-01-01 00:00:00")]
    df = pd.DataFrame({"close": range(10)}, index=idx)
    result = cons.check_duplicate_timestamps(df)
    assert result["duplicate_count"] == 1


def test_check_duplicate_timestamps_empty_df():
    import pandas as pd
    result = cons.check_duplicate_timestamps(pd.DataFrame())
    assert result["severity"] == cons.NONE_


def test_check_conflicting_sources_within_tolerance():
    result = cons.check_conflicting_sources({"src_a": 2000.0, "src_b": 2001.0}, tolerance_pct=5.0)
    assert result["severity"] == cons.NONE_


def test_check_conflicting_sources_outside_tolerance():
    result = cons.check_conflicting_sources({"src_a": 2000.0, "src_b": 2400.0}, tolerance_pct=5.0)
    assert result["severity"] != cons.NONE_


def test_check_conflicting_sources_single_value_is_none():
    result = cons.check_conflicting_sources({"src_a": 2000.0})
    assert result["severity"] == cons.NONE_
    assert result["sources_compared"] == 1


def test_check_conflicting_sources_ignores_non_numeric():
    result = cons.check_conflicting_sources({"src_a": 2000.0, "src_b": "bad"})
    assert result["sources_compared"] == 1


def test_check_symbol_metadata_present():
    result = cons.check_symbol_metadata("XAUUSD", {"XAUUSD": {"mult": 1, "label": "Gold", "dp": 2}})
    assert result["severity"] == cons.NONE_


def test_check_symbol_metadata_missing_entry():
    result = cons.check_symbol_metadata("FAKESYM", {"XAUUSD": {"mult": 1, "label": "Gold", "dp": 2}})
    assert result["severity"] == cons.CRITICAL


def test_check_symbol_metadata_incomplete_entry():
    result = cons.check_symbol_metadata("XAUUSD", {"XAUUSD": {"mult": 1}})
    assert result["severity"] == cons.MAJOR


def test_check_symbol_metadata_never_raises():
    result = cons.check_symbol_metadata("XAUUSD", None)
    assert result["severity"] == cons.CRITICAL
