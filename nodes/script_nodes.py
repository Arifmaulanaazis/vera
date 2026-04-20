"""
Python Script Node — execute custom Python code inside the workflow.

The user's code runs in an isolated local namespace with access to:
  - inputs  : dict of all connected input values (keyed by port name)
  - output  : dict the script must populate with output values

Any key set in `output` becomes available as the node's output port.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.nodes import BaseNode
from utils.logging_utils import get_logger

_DEFAULT_SCRIPT = """\
# Available: inputs (dict), output (dict)
# Example: pass molecules through unchanged
output["result"] = inputs.get("data")
"""


class PythonScriptNode(BaseNode):
    """Execute a custom Python script.

    Inputs:
      - data      (any) : primary data input
      - molecules (any) : molecules input
      - extra     (any) : extra/secondary input

    Outputs:
      - result    (any) : value assigned to output["result"]
      - result2   (any) : value assigned to output["result2"] (optional)
    """

    def __init__(self):
        super().__init__("python_script", "Python Script")
        self.logger = get_logger(__name__)

        self.add_input_port("data", "any")
        self.add_input_port("molecules", "any")
        self.add_input_port("extra", "any")
        self.add_output_port("result", "any")
        self.add_output_port("result2", "any")

        self.width = 360
        self.height = 260
        self.setMinimumSize(self.width, self.height)

        self.set_property("script", _DEFAULT_SCRIPT)
        self._editor = None

        try:
            from core.nodes import BaseNode as _BaseNode
            if getattr(_BaseNode, "_lightweight_construction", False):
                return
            from PySide6.QtWidgets import QPlainTextEdit, QLabel, QSpacerItem, QSizePolicy
            from PySide6.QtGui import QFont

            lbl = QLabel("Python Script")
            lbl.setStyleSheet("QLabel { background: transparent; font-size: 10px; }")

            editor = QPlainTextEdit()
            try:
                mono = QFont("Consolas", 8)
                mono.setStyleHint(QFont.Monospace)
                editor.setFont(mono)
            except Exception:
                pass
            editor.setPlainText(self.get_property("script") or _DEFAULT_SCRIPT)
            editor.textChanged.connect(self._on_script_changed)
            self._editor = editor

            layout = self.content_layout
            if layout is not None:
                layout.addItem(QSpacerItem(0, 4, QSizePolicy.Minimum, QSizePolicy.Fixed), 0, 0)
                layout.addWidget(lbl, 1, 0)
                layout.addWidget(editor, 2, 0)
            self._update_port_positions()
        except Exception:
            self._editor = None

    def _on_script_changed(self):
        try:
            if self._editor is not None:
                self.set_property("script", self._editor.toPlainText())
        except Exception:
            pass

    def _inline_summary(self) -> list[str]:
        script = self.get_property("script") or ""
        lines = [l for l in script.splitlines() if l.strip() and not l.strip().startswith("#")]
        return [f"{len(lines)} line(s) of code"]

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        script = (self.get_property("script") or "").strip()
        if not script:
            raise ValueError("Script is empty")

        local_ns: Dict[str, Any] = {
            "inputs": inputs or {},
            "output": {},
        }

        try:
            exec(compile(script, "<vera_script>", "exec"), {}, local_ns)  # noqa: S102
        except Exception as e:
            raise RuntimeError(f"Script error: {e}") from e

        out: Dict[str, Any] = local_ns.get("output", {})
        if not out:
            self.logger.warning("PythonScriptNode: script did not populate the output dict")
        elif "result" not in out and "result2" not in out:
            self.logger.warning(
                "PythonScriptNode: neither output['result'] nor output['result2'] was set"
            )
        return {
            "result": out.get("result"),
            "result2": out.get("result2"),
        }

    def validate(self) -> tuple[bool, str]:
        script = (self.get_property("script") or "").strip()
        if not script:
            return False, "Script is empty"
        try:
            compile(script, "<vera_script>", "exec")
        except SyntaxError as e:
            return False, f"Syntax error: {e}"
        return True, "Node configuration is valid"
