import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.data_health import completeness as comp  # noqa: E402


def test_check_dict_none_payload_is_critical():
    result = comp.check_dict(None, required_fields=("a",))
    assert result["severity"] == comp.CRITICAL


def test_check_dict_non_dict_payload_is_critical():
    result = comp.check_dict("not a dict", required_fields=("a",))
    assert result["severity"] == comp.CRITICAL


def test_check_dict_empty_dict_is_critical():
    result = comp.check_dict({}, required_fields=("a",))
    assert result["severity"] == comp.CRITICAL


def test_check_dict_all_required_present_is_none():
    result = comp.check_dict({"a": 1, "b": 2}, required_fields=("a", "b"))
    assert result["severity"] == comp.NONE_


def test_check_dict_missing_some_required_is_major():
    result = comp.check_dict({"a": 1}, required_fields=("a", "b", "c"))
    assert result["severity"] == comp.MAJOR
    assert "b" in result["missing_required"]


def test_check_dict_missing_all_required_is_critical():
    result = comp.check_dict({"z": 1}, required_fields=("a", "b"))
    assert result["severity"] == comp.CRITICAL


def test_check_dict_missing_optional_only_is_minor():
    result = comp.check_dict({"a": 1}, required_fields=("a",), optional_fields=("b",))
    assert result["severity"] == comp.MINOR


def test_check_dict_none_value_treated_as_missing():
    result = comp.check_dict({"a": None}, required_fields=("a",))
    assert result["severity"] == comp.CRITICAL


def test_check_dataframe_none_is_critical():
    result = comp.check_dataframe(None, min_rows=5)
    assert result["severity"] == comp.CRITICAL


def test_check_dataframe_empty_is_critical():
    import pandas as pd
    result = comp.check_dataframe(pd.DataFrame(), min_rows=5)
    assert result["severity"] == comp.CRITICAL


def test_check_dataframe_missing_required_columns():
    import pandas as pd
    df = pd.DataFrame({"open": [1, 2, 3]})
    result = comp.check_dataframe(df, required_columns=("open", "high", "low", "close"))
    assert result["severity"] == comp.MAJOR
    assert "high" in result["missing_columns"]


def test_check_dataframe_truncated_below_min_rows():
    import pandas as pd
    df = pd.DataFrame({"close": [1, 2, 3]})
    result = comp.check_dataframe(df, min_rows=100)
    assert result["severity"] == comp.MAJOR


def test_check_dataframe_healthy():
    import pandas as pd
    df = pd.DataFrame({"open": range(20), "high": range(20), "low": range(20), "close": range(20)})
    result = comp.check_dataframe(df, min_rows=10, required_columns=("open", "high", "low", "close"))
    assert result["severity"] == comp.NONE_
    assert result["row_count"] == 20


def test_worst_severity_reduction():
    assert comp.worst_severity(comp.NONE_, comp.MINOR, comp.MAJOR) == comp.MAJOR
    assert comp.worst_severity(comp.CRITICAL, comp.NONE_) == comp.CRITICAL
    assert comp.worst_severity() == comp.NONE_


def test_worst_severity_unknown_string_treated_as_critical():
    assert comp.worst_severity("garbage") == comp.CRITICAL


def test_check_dict_never_raises_on_weird_types():
    result = comp.check_dict(12345, required_fields=("a",))
    assert result["severity"] == comp.CRITICAL
