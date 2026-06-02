"""
Tests for nodes/script_nodes.py â€” PythonScriptNode

Covers: execute() behaviour and validate() syntax checking.
Uses the ``lightweight`` fixture so the QPlainTextEdit editor is not built.
"""

import pytest


class TestPythonScriptNodeExecute:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        from nodes.script import PythonScriptNode
        self.node = PythonScriptNode()

    def test_basic_passthrough(self):
        self.node.set_property("script", 'output["result"] = inputs.get("data")')
        result = self.node.execute({"data": [1, 2, 3]})
        assert result["result"] == [1, 2, 3]

    def test_arithmetic_in_script(self):
        self.node.set_property("script", 'output["result"] = 2 + 2')
        result = self.node.execute({})
        assert result["result"] == 4

    def test_result2_populated(self):
        script = 'output["result"] = 1\noutput["result2"] = 2'
        self.node.set_property("script", script)
        result = self.node.execute({})
        assert result["result"] == 1
        assert result["result2"] == 2

    def test_inputs_accessible_in_script(self):
        self.node.set_property("script", 'output["result"] = inputs["x"] * 2')
        result = self.node.execute({"x": 5})
        assert result["result"] == 10

    def test_script_can_import_math(self):
        self.node.set_property("script", "import math\noutput['result'] = math.sqrt(16)")
        result = self.node.execute({})
        assert abs(result["result"] - 4.0) < 1e-9

    def test_empty_output_dict_returns_none_values(self):
        self.node.set_property("script", "x = 1  # does nothing")
        result = self.node.execute({})
        assert result["result"] is None
        assert result["result2"] is None

    def test_empty_script_raises(self):
        self.node.set_property("script", "")
        with pytest.raises(ValueError, match="empty"):
            self.node.execute({})

    def test_whitespace_only_script_raises(self):
        self.node.set_property("script", "   \n   ")
        with pytest.raises(ValueError, match="empty"):
            self.node.execute({})

    def test_runtime_error_wrapped(self):
        self.node.set_property("script", "raise ValueError('boom')")
        with pytest.raises(RuntimeError, match="Script error"):
            self.node.execute({})

    def test_no_inputs_uses_empty_dict(self):
        self.node.set_property("script", 'output["result"] = len(inputs)')
        result = self.node.execute(None)
        assert result["result"] == 0

    def test_list_manipulation(self):
        self.node.set_property("script", 'output["result"] = [x**2 for x in inputs["vals"]]')
        result = self.node.execute({"vals": [1, 2, 3, 4]})
        assert result["result"] == [1, 4, 9, 16]


class TestPythonScriptNodeValidate:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        from nodes.script import PythonScriptNode
        self.node = PythonScriptNode()

    def test_valid_script_passes(self):
        self.node.set_property("script", 'output["result"] = 42')
        ok, msg = self.node.validate()
        assert ok is True

    def test_empty_script_fails(self):
        self.node.set_property("script", "")
        ok, msg = self.node.validate()
        assert ok is False
        assert "empty" in msg.lower()

    def test_syntax_error_detected(self):
        self.node.set_property("script", "def broken(:\n    pass")
        ok, msg = self.node.validate()
        assert ok is False
        assert "syntax" in msg.lower()

    def test_multi_line_valid_script(self):
        script = "x = 1\ny = 2\noutput['result'] = x + y"
        self.node.set_property("script", script)
        ok, _ = self.node.validate()
        assert ok is True

    def test_runtime_error_not_caught_by_validate(self):
        # validate() only checks syntax, not runtime
        self.node.set_property("script", "raise RuntimeError('oops')")
        ok, _ = self.node.validate()
        assert ok is True  # syntactically valid
