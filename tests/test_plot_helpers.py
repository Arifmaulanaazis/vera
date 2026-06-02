"""
Tests for helper functions in nodes/plot_nodes.py

_as_numeric_list, _as_dataframe, _extract_series_from_table, and
_extract_labels_from_table are pure Python utilities with no Qt dependency.
"""

import math
import pytest

from nodes.plot import (
    _as_numeric_list,
    _as_dataframe,
    _extract_series_from_table,
    _extract_labels_from_table,
)


class TestAsNumericList:
    def test_none_returns_empty(self):
        assert _as_numeric_list(None) == []

    def test_empty_list_returns_empty(self):
        assert _as_numeric_list([]) == []

    def test_integer_list(self):
        assert _as_numeric_list([1, 2, 3]) == [1.0, 2.0, 3.0]

    def test_float_list(self):
        result = _as_numeric_list([1.1, 2.2, 3.3])
        assert len(result) == 3
        assert abs(result[0] - 1.1) < 1e-9

    def test_string_numbers_converted(self):
        assert _as_numeric_list(["1", "2.5", "3"]) == [1.0, 2.5, 3.0]

    def test_non_numeric_strings_skipped(self):
        assert _as_numeric_list(["1", "bad", "3"]) == [1.0, 3.0]

    def test_single_scalar(self):
        assert _as_numeric_list(42) == [42.0]

    def test_tuple_input(self):
        assert _as_numeric_list((1, 2, 3)) == [1.0, 2.0, 3.0]

    def test_non_numeric_scalar_returns_empty(self):
        assert _as_numeric_list("hello") == []

    def test_mixed_valid_invalid(self):
        result = _as_numeric_list([0, None, 5, "abc", 3.0])
        assert 0.0 in result
        assert 5.0 in result
        assert 3.0 in result
        assert len(result) == 3


class TestAsDataframe:
    def test_none_returns_none(self):
        assert _as_dataframe(None) is None

    def test_dataframe_returns_self(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({"a": [1, 2]})
        result = _as_dataframe(df)
        assert result is df

    def test_list_of_dicts_converted(self):
        pd = pytest.importorskip("pandas")
        data = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        result = _as_dataframe(data)
        assert result is not None
        assert list(result.columns) == ["a", "b"]
        assert len(result) == 2

    def test_empty_list_returns_dataframe(self):
        pd = pytest.importorskip("pandas")
        result = _as_dataframe([])
        assert result is not None
        assert len(result) == 0

    def test_plain_string_returns_none(self):
        result = _as_dataframe("hello")
        assert result is None

    def test_integer_returns_none(self):
        result = _as_dataframe(42)
        assert result is None


class TestExtractSeriesFromTable:
    def _table(self):
        return [
            {"x": 1.0, "y": 10.0},
            {"x": 2.0, "y": 20.0},
            {"x": 3.0, "y": 30.0},
        ]

    def test_basic_extraction(self):
        result = _extract_series_from_table(self._table(), "y")
        assert result == [10.0, 20.0, 30.0]

    def test_no_key_returns_empty(self):
        assert _extract_series_from_table(self._table(), "") == []
        assert _extract_series_from_table(self._table(), None) == []

    def test_missing_key_returns_nans(self):
        result = _extract_series_from_table(self._table(), "missing")
        assert len(result) == 3
        assert all(math.isnan(v) for v in result)

    def test_empty_table_returns_empty(self):
        assert _extract_series_from_table([], "y") == []

    def test_non_list_input_returns_empty(self):
        assert _extract_series_from_table(None, "y") == []
        assert _extract_series_from_table("data", "y") == []


class TestExtractLabelsFromTable:
    def _table(self):
        return [
            {"label": "alpha", "val": 1},
            {"label": "beta", "val": 2},
            {"label": "gamma", "val": 3},
        ]

    def test_basic_extraction(self):
        result = _extract_labels_from_table(self._table(), "label")
        assert result == ["alpha", "beta", "gamma"]

    def test_no_key_returns_empty(self):
        assert _extract_labels_from_table(self._table(), "") == []
        assert _extract_labels_from_table(self._table(), None) == []

    def test_missing_key_returns_empty_strings(self):
        result = _extract_labels_from_table(self._table(), "missing")
        assert result == ["", "", ""]

    def test_values_converted_to_str(self):
        table = [{"k": 1}, {"k": 2.5}, {"k": None}]
        result = _extract_labels_from_table(table, "k")
        assert result == ["1", "2.5", "None"]

    def test_empty_table_returns_empty(self):
        assert _extract_labels_from_table([], "label") == []

    def test_non_list_input_returns_empty(self):
        assert _extract_labels_from_table(None, "label") == []
