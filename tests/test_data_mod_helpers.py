"""
Tests for helper functions in nodes/data_mod_nodes.py

_to_rows and _coerce_number are pure Python utilities with no Qt dependency.
"""

import pytest
from nodes.data_mod import _to_rows, _coerce_number


class TestToRows:
    def test_none_returns_empty_list(self):
        assert _to_rows(None) == []

    def test_empty_list_returns_empty_list(self):
        assert _to_rows([]) == []

    def test_list_of_dicts_passthrough(self):
        data = [{"a": 1}, {"a": 2}]
        assert _to_rows(data) == data

    def test_dict_wraps_in_list(self):
        data = {"a": 1, "b": 2}
        result = _to_rows(data)
        assert result == [{"a": 1, "b": 2}]

    def test_primitive_wrapped_as_value(self):
        result = _to_rows("hello")
        assert result == [{"value": "hello"}]

    def test_list_of_primitives_wrapped(self):
        result = _to_rows([1, 2, 3])
        assert result == [{"value": 1}, {"value": 2}, {"value": 3}]

    def test_pandas_dataframe_converted(self):
        pytest.importorskip("pandas")
        import pandas as pd

        df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
        rows = _to_rows(df)
        assert rows == [{"x": 1, "y": 3}, {"x": 2, "y": 4}]

    def test_pandas_multiindex_dataframe_flattened(self):
        pytest.importorskip("pandas")
        import pandas as pd

        arrays = [["a", "a", "b"], [1, 2, 1]]
        idx = pd.MultiIndex.from_arrays(arrays, names=("first", "second"))
        df = pd.DataFrame({"val": [10, 20, 30]}, index=idx)
        rows = _to_rows(df)
        assert isinstance(rows, list)
        assert len(rows) == 3
        assert "val" in rows[0]

    def test_list_of_json_strings_parsed(self):
        data = ['{"a": 1}', '{"a": 2}']
        result = _to_rows(data)
        assert result == [{"a": 1}, {"a": 2}]


class TestCoerceNumber:
    def test_integer_succeeds(self):
        ok, val = _coerce_number(42)
        assert ok is True
        assert val == 42.0

    def test_float_succeeds(self):
        ok, val = _coerce_number(3.14)
        assert ok is True
        assert abs(val - 3.14) < 1e-9

    def test_numeric_string_succeeds(self):
        ok, val = _coerce_number("7.5")
        assert ok is True
        assert val == 7.5

    def test_negative_number_succeeds(self):
        ok, val = _coerce_number(-100)
        assert ok is True
        assert val == -100.0

    def test_zero_succeeds(self):
        ok, val = _coerce_number(0)
        assert ok is True
        assert val == 0.0

    def test_boolean_fails(self):
        ok, _ = _coerce_number(True)
        assert ok is False

    def test_non_numeric_string_fails(self):
        ok, _ = _coerce_number("hello")
        assert ok is False

    def test_nan_string_fails(self):
        ok, _ = _coerce_number("nan")
        assert ok is False

    def test_inf_string_fails(self):
        ok, _ = _coerce_number("inf")
        assert ok is False

    def test_none_fails(self):
        ok, _ = _coerce_number(None)
        assert ok is False

    def test_empty_string_fails(self):
        ok, _ = _coerce_number("")
        assert ok is False
