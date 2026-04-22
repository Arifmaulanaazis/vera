"""
Tests for node execute() methods in nodes/data_mod_nodes.py

Each test instantiates the node with _lightweight_construction=True
(via the ``lightweight`` fixture) so Qt inline widgets are skipped,
then exercises only the pure-logic execute() method.
"""

import pytest


# ---------------------------------------------------------------------------
# SelectColumnsNode
# ---------------------------------------------------------------------------

class TestSelectColumnsNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        from nodes.data_mod_nodes import SelectColumnsNode
        self.node = SelectColumnsNode()

    def test_no_columns_returns_all_rows(self):
        data = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        self.node.set_property("columns", [])
        result = self.node.execute({"data": data})
        assert result["data"] == data

    def test_select_single_column(self):
        data = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        self.node.set_property("columns", ["a"])
        result = self.node.execute({"data": data})
        assert result["data"] == [{"a": 1}, {"a": 3}]

    def test_select_multiple_columns(self):
        data = [{"a": 1, "b": 2, "c": 3}]
        self.node.set_property("columns", ["a", "c"])
        result = self.node.execute({"data": data})
        assert result["data"] == [{"a": 1, "c": 3}]

    def test_missing_column_defaults_to_none(self):
        data = [{"a": 1}]
        self.node.set_property("columns", ["a", "missing"])
        self.node.set_property("drop_missing", False)
        result = self.node.execute({"data": data})
        assert result["data"][0]["missing"] is None

    def test_drop_missing_removes_rows(self):
        data = [{"a": 1, "b": 2}, {"a": 3}]
        self.node.set_property("columns", ["a", "b"])
        self.node.set_property("drop_missing", True)
        result = self.node.execute({"data": data})
        assert len(result["data"]) == 1
        assert result["data"][0]["a"] == 1

    def test_columns_as_comma_separated_string(self):
        data = [{"x": 10, "y": 20, "z": 30}]
        self.node.set_property("columns", "x, z")
        result = self.node.execute({"data": data})
        assert list(result["data"][0].keys()) == ["x", "z"]

    def test_missing_input_raises(self):
        with pytest.raises(ValueError):
            self.node.execute({})

    def test_empty_data_returns_empty(self):
        self.node.set_property("columns", ["a"])
        result = self.node.execute({"data": []})
        assert result["data"] == []


# ---------------------------------------------------------------------------
# FilterRowsNode
# ---------------------------------------------------------------------------

class TestFilterRowsNode:
    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        from nodes.data_mod_nodes import FilterRowsNode
        self.node = FilterRowsNode()

    def _data(self):
        return [
            {"name": "Alice", "score": 90},
            {"name": "Bob", "score": 70},
            {"name": "Charlie", "score": 85},
        ]

    def test_no_key_returns_all_rows(self):
        self.node.set_property("filter_key", "")
        result = self.node.execute({"data": self._data()})
        assert len(result["data"]) == 3

    def test_equals(self):
        self.node.set_property("filter_key", "name")
        self.node.set_property("operator", "equals")
        self.node.set_property("value", "Alice")
        result = self.node.execute({"data": self._data()})
        assert len(result["data"]) == 1
        assert result["data"][0]["name"] == "Alice"

    def test_not_equals(self):
        self.node.set_property("filter_key", "name")
        self.node.set_property("operator", "not_equals")
        self.node.set_property("value", "Alice")
        result = self.node.execute({"data": self._data()})
        assert len(result["data"]) == 2

    def test_gt_numeric(self):
        self.node.set_property("filter_key", "score")
        self.node.set_property("operator", "gt")
        self.node.set_property("value", "80")
        result = self.node.execute({"data": self._data()})
        scores = [r["score"] for r in result["data"]]
        assert all(s > 80 for s in scores)

    def test_gte_numeric(self):
        self.node.set_property("filter_key", "score")
        self.node.set_property("operator", "gte")
        self.node.set_property("value", "85")
        result = self.node.execute({"data": self._data()})
        assert len(result["data"]) == 2

    def test_lt_numeric(self):
        self.node.set_property("filter_key", "score")
        self.node.set_property("operator", "lt")
        self.node.set_property("value", "85")
        result = self.node.execute({"data": self._data()})
        assert len(result["data"]) == 1
        assert result["data"][0]["name"] == "Bob"

    def test_lte_numeric(self):
        self.node.set_property("filter_key", "score")
        self.node.set_property("operator", "lte")
        self.node.set_property("value", "85")
        result = self.node.execute({"data": self._data()})
        assert len(result["data"]) == 2

    def test_contains(self):
        self.node.set_property("filter_key", "name")
        self.node.set_property("operator", "contains")
        self.node.set_property("value", "li")
        result = self.node.execute({"data": self._data()})
        names = [r["name"] for r in result["data"]]
        assert "Alice" in names
        assert "Charlie" in names

    def test_not_contains(self):
        self.node.set_property("filter_key", "name")
        self.node.set_property("operator", "not_contains")
        self.node.set_property("value", "li")
        result = self.node.execute({"data": self._data()})
        assert len(result["data"]) == 1
        assert result["data"][0]["name"] == "Bob"

    def test_startswith(self):
        self.node.set_property("filter_key", "name")
        self.node.set_property("operator", "startswith")
        self.node.set_property("value", "A")
        result = self.node.execute({"data": self._data()})
        assert len(result["data"]) == 1

    def test_endswith(self):
        self.node.set_property("filter_key", "name")
        self.node.set_property("operator", "endswith")
        self.node.set_property("value", "e")
        result = self.node.execute({"data": self._data()})
        names = [r["name"] for r in result["data"]]
        assert "Alice" in names
        assert "Charlie" in names

    def test_in_operator(self):
        self.node.set_property("filter_key", "name")
        self.node.set_property("operator", "in")
        self.node.set_property("value", "Alice, Bob")
        result = self.node.execute({"data": self._data()})
        assert len(result["data"]) == 2

    def test_not_in_operator(self):
        self.node.set_property("filter_key", "name")
        self.node.set_property("operator", "not_in")
        self.node.set_property("value", "Alice, Bob")
        result = self.node.execute({"data": self._data()})
        assert len(result["data"]) == 1
        assert result["data"][0]["name"] == "Charlie"

    def test_missing_input_raises(self):
        with pytest.raises(ValueError):
            self.node.execute({})

    def test_empty_data_returns_empty(self):
        self.node.set_property("filter_key", "name")
        self.node.set_property("operator", "equals")
        self.node.set_property("value", "Alice")
        result = self.node.execute({"data": []})
        assert result["data"] == []


# ---------------------------------------------------------------------------
# SliceRowsNode
# ---------------------------------------------------------------------------

class TestSliceRowsNode:
    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        from nodes.data_mod_nodes import SliceRowsNode
        self.node = SliceRowsNode()

    def _data(self, n=10):
        return [{"i": i} for i in range(n)]

    def test_default_slice_returns_all(self):
        self.node.set_property("start", None)
        self.node.set_property("end", None)
        self.node.set_property("step", 1)
        result = self.node.execute({"data": self._data()})
        assert len(result["data"]) == 10

    def test_start_end(self):
        self.node.set_property("start", 2)
        self.node.set_property("end", 5)
        self.node.set_property("step", 1)
        result = self.node.execute({"data": self._data()})
        assert [r["i"] for r in result["data"]] == [2, 3, 4]

    def test_step_2(self):
        self.node.set_property("start", 0)
        self.node.set_property("end", None)
        self.node.set_property("step", 2)
        result = self.node.execute({"data": self._data()})
        assert [r["i"] for r in result["data"]] == [0, 2, 4, 6, 8]

    def test_end_beyond_length_clips(self):
        self.node.set_property("start", 0)
        self.node.set_property("end", 100)
        self.node.set_property("step", 1)
        result = self.node.execute({"data": self._data(5)})
        assert len(result["data"]) == 5

    def test_missing_input_raises(self):
        with pytest.raises(ValueError):
            self.node.execute({})

    def test_empty_data_returns_empty(self):
        self.node.set_property("start", 0)
        self.node.set_property("end", None)
        self.node.set_property("step", 1)
        result = self.node.execute({"data": []})
        assert result["data"] == []


# ---------------------------------------------------------------------------
# DropDuplicatesNode
# ---------------------------------------------------------------------------

class TestDropDuplicatesNode:
    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        from nodes.data_mod_nodes import DropDuplicatesNode
        self.node = DropDuplicatesNode()

    def test_no_duplicates_unchanged(self):
        data = [{"a": 1}, {"a": 2}, {"a": 3}]
        self.node.set_property("subset", ["a"])
        result = self.node.execute({"data": data})
        assert len(result["data"]) == 3

    def test_removes_duplicate_rows(self):
        data = [{"a": 1}, {"a": 1}, {"a": 2}]
        self.node.set_property("subset", ["a"])
        result = self.node.execute({"data": data})
        assert len(result["data"]) == 2

    def test_keep_first(self):
        data = [{"a": 1, "b": "first"}, {"a": 1, "b": "second"}]
        self.node.set_property("subset", ["a"])
        self.node.set_property("keep", "first")
        result = self.node.execute({"data": data})
        assert result["data"][0]["b"] == "first"

    def test_keep_last(self):
        data = [{"a": 1, "b": "first"}, {"a": 1, "b": "second"}]
        self.node.set_property("subset", ["a"])
        self.node.set_property("keep", "last")
        result = self.node.execute({"data": data})
        assert result["data"][0]["b"] == "second"

    def test_multi_column_subset(self):
        data = [
            {"a": 1, "b": 1},
            {"a": 1, "b": 2},
            {"a": 1, "b": 1},  # duplicate of first
        ]
        self.node.set_property("subset", ["a", "b"])
        result = self.node.execute({"data": data})
        assert len(result["data"]) == 2

    def test_missing_input_raises(self):
        with pytest.raises(ValueError):
            self.node.execute({})

    def test_empty_data_returns_empty(self):
        self.node.set_property("subset", ["a"])
        result = self.node.execute({"data": []})
        assert result["data"] == []


# ---------------------------------------------------------------------------
# SortRowsNode
# ---------------------------------------------------------------------------

class TestSortRowsNode:
    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        from nodes.data_mod_nodes import SortRowsNode
        self.node = SortRowsNode()

    def _data(self):
        return [{"name": "Charlie", "score": 85}, {"name": "Alice", "score": 90}, {"name": "Bob", "score": 70}]

    def test_no_by_key_returns_unchanged(self):
        self.node.set_property("by", [])
        result = self.node.execute({"data": self._data()})
        assert [r["name"] for r in result["data"]] == ["Charlie", "Alice", "Bob"]

    def test_sort_ascending_string(self):
        self.node.set_property("by", ["name"])
        self.node.set_property("ascending", True)
        self.node.set_property("numeric", False)
        result = self.node.execute({"data": self._data()})
        assert [r["name"] for r in result["data"]] == ["Alice", "Bob", "Charlie"]

    def test_sort_descending_string(self):
        self.node.set_property("by", ["name"])
        self.node.set_property("ascending", False)
        result = self.node.execute({"data": self._data()})
        assert result["data"][0]["name"] == "Charlie"

    def test_sort_numeric_ascending(self):
        self.node.set_property("by", ["score"])
        self.node.set_property("ascending", True)
        self.node.set_property("numeric", True)
        result = self.node.execute({"data": self._data()})
        scores = [r["score"] for r in result["data"]]
        assert scores == sorted(scores)

    def test_sort_numeric_descending(self):
        self.node.set_property("by", ["score"])
        self.node.set_property("ascending", False)
        self.node.set_property("numeric", True)
        result = self.node.execute({"data": self._data()})
        scores = [r["score"] for r in result["data"]]
        assert scores == sorted(scores, reverse=True)

    def test_by_as_comma_string(self):
        self.node.set_property("by", "name")
        self.node.set_property("ascending", True)
        result = self.node.execute({"data": self._data()})
        assert result["data"][0]["name"] == "Alice"

    def test_missing_input_raises(self):
        with pytest.raises(ValueError):
            self.node.execute({})

    def test_empty_data_returns_empty(self):
        self.node.set_property("by", ["name"])
        result = self.node.execute({"data": []})
        assert result["data"] == []


# ---------------------------------------------------------------------------
# DataframeMergeNode
# ---------------------------------------------------------------------------

class TestDataframeMergeNode:
    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        from nodes.data_mod_nodes import DataframeMergeNode
        self.node = DataframeMergeNode()

    def _left(self):
        return [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}, {"id": 3, "name": "Charlie"}]

    def _right(self):
        return [{"id": 1, "score": 90}, {"id": 2, "score": 70}]

    def test_inner_join(self):
        self.node.set_property("how", "inner")
        self.node.set_property("left_on", ["id"])
        self.node.set_property("right_on", ["id"])
        self.node.set_property("auto_detect_keys", False)
        result = self.node.execute({"left": self._left(), "right": self._right()})
        assert len(result["data"]) == 2
        ids = {r["id"] for r in result["data"]}
        assert ids == {1, 2}

    def test_left_join_keeps_unmatched(self):
        self.node.set_property("how", "left")
        self.node.set_property("left_on", ["id"])
        self.node.set_property("right_on", ["id"])
        self.node.set_property("auto_detect_keys", False)
        result = self.node.execute({"left": self._left(), "right": self._right()})
        assert len(result["data"]) == 3

    def test_right_join_keeps_right_unmatched(self):
        left = [{"id": 1, "name": "Alice"}]
        right = [{"id": 1, "score": 90}, {"id": 99, "score": 50}]
        self.node.set_property("how", "right")
        self.node.set_property("left_on", ["id"])
        self.node.set_property("right_on", ["id"])
        self.node.set_property("auto_detect_keys", False)
        result = self.node.execute({"left": left, "right": right})
        assert len(result["data"]) == 2
        ids = {r["id"] for r in result["data"]}
        assert 99 in ids

    def test_outer_join_includes_all(self):
        self.node.set_property("how", "outer")
        self.node.set_property("left_on", ["id"])
        self.node.set_property("right_on", ["id"])
        self.node.set_property("auto_detect_keys", False)
        result = self.node.execute({"left": self._left(), "right": self._right()})
        assert len(result["data"]) == 3

    def test_missing_input_raises(self):
        with pytest.raises(ValueError):
            self.node.execute({"left": self._left()})

    def test_same_schema_concatenates(self):
        left = [{"a": 1}, {"a": 2}]
        right = [{"a": 3}, {"a": 4}]
        self.node.set_property("auto_detect_keys", True)
        result = self.node.execute({"left": left, "right": right})
        assert len(result["data"]) == 4
