"""
Tests for execute() methods in nodes/plot_nodes.py

Each node produces PNG bytes on its ``plot_image`` output port.
Tests verify:
  - Output key is present
  - Returned value is non-empty bytes starting with the PNG magic number
  - Basic behaviour with both direct inputs and table inputs

Uses the ``lightweight`` fixture to skip inline Qt widget construction.
"""

import pytest

PNG_MAGIC = b"\x89PNG"


def _is_valid_png(data) -> bool:
    return isinstance(data, (bytes, bytearray)) and data[:4] == PNG_MAGIC


class TestHistogramPlotNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        from nodes.plot import HistogramPlotNode
        self.node = HistogramPlotNode()

    def test_returns_png_bytes_from_values(self):
        result = self.node.execute({"values": [1, 2, 2, 3, 3, 3, 4]})
        assert _is_valid_png(result.get("plot_image"))

    def test_returns_png_bytes_from_table(self):
        self.node.set_property("value_key", "v")
        table = [{"v": i} for i in range(20)]
        result = self.node.execute({"table": table})
        assert _is_valid_png(result.get("plot_image"))

    def test_output_key_present(self):
        result = self.node.execute({"values": [1, 2, 3]})
        assert "plot_image" in result

    def test_empty_values_still_produces_png(self):
        result = self.node.execute({"values": []})
        assert _is_valid_png(result.get("plot_image"))


class TestScatterPlotNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        from nodes.plot import ScatterPlotNode
        self.node = ScatterPlotNode()

    def test_returns_png_bytes_from_xy(self):
        result = self.node.execute({"x": [1, 2, 3], "y": [4, 5, 6]})
        assert _is_valid_png(result.get("plot_image"))

    def test_returns_png_bytes_from_table(self):
        self.node.set_property("x_key", "a")
        self.node.set_property("y_key", "b")
        table = [{"a": i, "b": i * 2} for i in range(5)]
        result = self.node.execute({"table": table})
        assert _is_valid_png(result.get("plot_image"))


class TestLinePlotNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        from nodes.plot import LinePlotNode
        self.node = LinePlotNode()

    def test_returns_png_bytes_from_xy(self):
        result = self.node.execute({"x": [0, 1, 2], "y": [0, 1, 4]})
        assert _is_valid_png(result.get("plot_image"))

    def test_returns_png_bytes_from_table(self):
        self.node.set_property("x_key", "t")
        self.node.set_property("y_key", "v")
        table = [{"t": i, "v": i ** 2} for i in range(5)]
        result = self.node.execute({"table": table})
        assert _is_valid_png(result.get("plot_image"))


class TestBarPlotNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        from nodes.plot import BarPlotNode
        self.node = BarPlotNode()

    def test_returns_png_bytes_from_direct_input(self):
        result = self.node.execute({"categories": ["A", "B", "C"], "values": [10, 20, 15]})
        assert _is_valid_png(result.get("plot_image"))

    def test_returns_png_bytes_from_table(self):
        self.node.set_property("label_key", "cat")
        self.node.set_property("value_key", "val")
        table = [{"cat": "X", "val": 5}, {"cat": "Y", "val": 8}]
        result = self.node.execute({"table": table})
        assert _is_valid_png(result.get("plot_image"))


class TestPiePlotNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        from nodes.plot import PiePlotNode
        self.node = PiePlotNode()

    def test_returns_png_bytes(self):
        result = self.node.execute({"labels": ["A", "B"], "values": [60, 40]})
        assert _is_valid_png(result.get("plot_image"))

    def test_table_input(self):
        self.node.set_property("label_key", "name")
        self.node.set_property("value_key", "pct")
        table = [{"name": "X", "pct": 70}, {"name": "Y", "pct": 30}]
        result = self.node.execute({"table": table})
        assert _is_valid_png(result.get("plot_image"))


class TestHeatmapPlotNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        from nodes.plot import HeatmapPlotNode
        self.node = HeatmapPlotNode()

    def test_matrix_input(self):
        matrix = [[1, 2], [3, 4], [5, 6]]
        result = self.node.execute({"matrix": matrix})
        assert _is_valid_png(result.get("plot_image"))

    def test_table_input(self):
        table = [{"a": 1.0, "b": 2.0}, {"a": 3.0, "b": 4.0}]
        result = self.node.execute({"table": table})
        assert _is_valid_png(result.get("plot_image"))

    def test_empty_matrix_uses_zero_fallback(self):
        result = self.node.execute({"matrix": None})
        assert _is_valid_png(result.get("plot_image"))
