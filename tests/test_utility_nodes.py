"""
Tests for nodes/utility_nodes.py

Covers NoteNode: execute(), validate(), set_property(), and color helpers.
Uses lightweight fixture to skip the Qt editor widget.
"""

import pytest


class TestNoteNodeExecute:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        from nodes.utility_nodes import NoteNode
        self.node = NoteNode()

    def test_execute_returns_empty_dict(self):
        result = self.node.execute({})
        assert result == {}

    def test_execute_with_none_returns_empty_dict(self):
        result = self.node.execute(None)
        assert result == {}

    def test_execute_ignores_inputs(self):
        result = self.node.execute({"data": [1, 2, 3], "molecules": "something"})
        assert result == {}


class TestNoteNodeValidate:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        from nodes.utility_nodes import NoteNode
        self.node = NoteNode()

    def test_validate_always_true(self):
        ok, msg = self.node.validate()
        assert ok is True

    def test_validate_message_not_empty(self):
        _, msg = self.node.validate()
        assert isinstance(msg, str) and len(msg) > 0

    def test_validate_with_empty_text(self):
        self.node.set_property("text", "")
        ok, _ = self.node.validate()
        assert ok is True

    def test_validate_with_any_text(self):
        self.node.set_property("text", "Random note content")
        ok, _ = self.node.validate()
        assert ok is True


class TestNoteNodeProperties:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        from nodes.utility_nodes import NoteNode
        self.node = NoteNode()

    def test_default_text(self):
        text = self.node.get_property("text")
        assert isinstance(text, str)
        assert len(text) > 0

    def test_default_color_is_yellow(self):
        color = self.node.get_property("color")
        assert color == "yellow"

    def test_set_text_property(self):
        self.node.set_property("text", "My test note")
        assert self.node.get_property("text") == "My test note"

    def test_set_color_blue(self):
        self.node.set_property("color", "blue")
        assert self.node.get_property("color") == "blue"

    def test_set_color_green(self):
        self.node.set_property("color", "green")
        assert self.node.get_property("color") == "green"

    def test_set_color_red(self):
        self.node.set_property("color", "red")
        assert self.node.get_property("color") == "red"

    def test_set_color_purple(self):
        self.node.set_property("color", "purple")
        assert self.node.get_property("color") == "purple"

    def test_set_color_gray(self):
        self.node.set_property("color", "gray")
        assert self.node.get_property("color") == "gray"


class TestNoteNodeColorHelpers:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        from nodes.utility_nodes import NoteNode
        self.node = NoteNode()

    def test_color_key_yellow(self):
        self.node.set_property("color", "yellow")
        assert self.node._color_key() == "yellow"

    def test_color_key_blue(self):
        self.node.set_property("color", "blue")
        assert self.node._color_key() == "blue"

    def test_color_key_uppercase_normalized(self):
        self.node.set_property("color", "YELLOW")
        assert self.node._color_key() == "yellow"

    def test_bg_color_returns_qcolor(self):
        from PySide6.QtGui import QColor
        self.node.set_property("color", "yellow")
        bg = self.node._bg_color()
        assert isinstance(bg, QColor)

    def test_border_color_returns_qcolor(self):
        from PySide6.QtGui import QColor
        bc = self.node._border_color()
        assert isinstance(bc, QColor)

    def test_text_color_returns_qcolor(self):
        from PySide6.QtGui import QColor
        tc = self.node._text_color()
        assert isinstance(tc, QColor)

    def test_inline_summary_returns_empty(self):
        result = self.node._inline_summary()
        assert result == []

    def test_no_input_ports(self):
        assert len(self.node.input_ports) == 0

    def test_no_output_ports(self):
        assert len(self.node.output_ports) == 0
