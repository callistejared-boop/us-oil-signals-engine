import pathlib
import sys
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.data_health import anomaly as anom  # noqa: E402


def test_check_frozen_price_no_freeze():
    closes = [2000.0 + i * 0.1 for i in range(20)]
    result = anom.check_frozen_price(closes)
    assert result["severity"] == anom.NONE_


def test_check_frozen_price_detects_frozen_run():
    closes = [2000.0, 2001.0, 2002.0] + [2003.0] * 8 + [2004.0]
    result = anom.check_frozen_price(closes, threshold=6)
    assert result["frozen_run_length"] == 8
    assert result["severity"] in (anom.MAJOR, anom.CRITICAL)


def test_check_frozen_price_insufficient_data():
    result = anom.check_frozen_price([2000.0, 2000.0], threshold=6)
    assert result["severity"] == anom.NONE_
    assert "insufficient" in result["detail"]


def test_check_frozen_price_extreme_freeze_is_critical():
    closes = [2000.0] * 20
    result = anom.check_frozen_price(closes, threshold=6)
    assert result["severity"] == anom.CRITICAL


def test_check_frozen_price_never_raises_on_none():
    result = anom.check_frozen_price(None)
    assert result["severity"] == anom.NONE_


def test_check_price_jump_no_outlier():
    closes = [2000.0 + i * 0.5 for i in range(20)]
    result = anom.check_price_jump(closes)
    assert result["severity"] == anom.NONE_


def test_check_price_jump_detects_outlier():
    # 40 flat bars (zero bar-to-bar change) then one large single-bar jump —
    # for n-1 zero diffs plus one outlier, z approaches sqrt(n-1), so a
    # 40-bar baseline comfortably clears the 6.0 threshold.
    closes = [2000.0] * 40 + [2100.0]
    result = anom.check_price_jump(closes)
    assert result["max_abs_zscore"] > 6.0
    assert result["severity"] in (anom.MAJOR, anom.CRITICAL)


def test_check_price_jump_insufficient_data():
    result = anom.check_price_jump([1, 2, 3])
    assert result["severity"] == anom.NONE_
    assert "insufficient" in result["detail"]


def test_check_price_jump_zero_variance():
    result = anom.check_price_jump([2000.0] * 15)
    assert result["severity"] == anom.NONE_
    assert result["max_abs_zscore"] == 0.0


def test_check_price_jump_never_raises_on_none():
    result = anom.check_price_jump(None)
    assert result["severity"] == anom.NONE_


def test_check_timeline_gaps_no_gaps():
    base = datetime(2026, 1, 1)
    ts = [base + timedelta(minutes=15 * i) for i in range(10)]
    result = anom.check_timeline_gaps(ts, expected_interval_minutes=15)
    assert result["severity"] == anom.NONE_
    assert result["gap_count"] == 0


def test_check_timeline_gaps_detects_gap():
    base = datetime(2026, 1, 1)
    ts = [base + timedelta(minutes=15 * i) for i in range(5)]
    ts.append(ts[-1] + timedelta(hours=5))  # big gap
    result = anom.check_timeline_gaps(ts, expected_interval_minutes=15)
    assert result["gap_count"] == 1
    assert result["severity"] != anom.NONE_


def test_check_timeline_gaps_insufficient_data():
    result = anom.check_timeline_gaps([datetime(2026, 1, 1)], expected_interval_minutes=15)
    assert result["severity"] == anom.NONE_


def test_check_timeline_gaps_never_raises_on_none():
    result = anom.check_timeline_gaps(None, expected_interval_minutes=15)
    assert result["severity"] == anom.NONE_
