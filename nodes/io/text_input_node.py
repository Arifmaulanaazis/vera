"""TextInputNode implementation."""

from .common import *  # noqa: F401,F403

class TextInputNode(BaseNode):
    """Inline single-line text input that emits its content as a string.

    Outputs: string (text)
    """

    def __init__(self):
        super().__init__("text_input", "Text Input")
        self.logger = get_logger(__name__)
        # One output: the text content
        self.add_output_port("string", "string")

        # Visual size
        self.width = 280
        self.height = 120
        self.setMinimumSize(self.width, self.height)
        self.setMaximumSize(self.width, self.height)

        # Properties
        self.set_property("text", "")
        self.set_property("placeholder", "Type here…")

        # Inline QLineEdit
        try:
            # Skip heavy widget creation when in lightweight probing mode
            from core.nodes import BaseNode as _BaseNode
            if getattr(_BaseNode, "_lightweight_construction", False):  # type: ignore[attr-defined]
                self._edit = None
            else:
                from PySide6.QtWidgets import QLineEdit, QSpacerItem, QSizePolicy
                self._edit = QLineEdit()
                self._edit.setPlaceholderText(self.get_property("placeholder") or "")
                self._edit.setText(self.get_property("text") or "")
                self._edit.textChanged.connect(self._on_text_changed)

                layout = self.content_layout
                if layout is not None:
                    layout.addItem(QSpacerItem(0, 8, QSizePolicy.Minimum, QSizePolicy.Fixed), 0, 0)
                    layout.addWidget(self._edit, 1, 0)
                # Ensure the single output port sits on the far right after resize
                self._update_port_positions()
        except Exception:
            self._edit = None

    def _on_text_changed(self, text: str):
        try:
            self.set_property("text", text)
        except Exception:
            pass

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Emit current text as output
        text = self.get_property("text") or ""
        return {"string": text}
