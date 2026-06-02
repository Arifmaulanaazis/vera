"""TextViewerNode implementation."""

from .common import *  # noqa: F401,F403

class TextViewerNode(BaseNode):
    """Inline text viewer that displays incoming string or JSON-serializable data."""

    def __init__(self):
        super().__init__("text_view", "Text View")
        self.logger = get_logger(__name__)
        self.add_input_port("string", "string")
        self.add_input_port("data", "data")
        self.width = 360
        self.height = 220
        self.setMinimumSize(self.width, self.height)
        self.setMaximumSize(self.width, self.height)
        # Fill the node body completely (no inner spacing)
        try:
            self.set_content_margins(0, 32, 0, 0)
        except Exception:
            pass
        try:
            # Respect lightweight construction
            from core.nodes import BaseNode as _BaseNode
            if getattr(_BaseNode, "_lightweight_construction", False):  # type: ignore[attr-defined]
                self._text = None
            else:
                from PySide6.QtWidgets import QPlainTextEdit
                from PySide6.QtCore import Qt
                self._text = QPlainTextEdit()
                self._text.setReadOnly(True)
                
                # Enable custom context menu
                self._text.setContextMenuPolicy(Qt.CustomContextMenu)
                self._text.customContextMenuRequested.connect(self._show_text_context_menu)
                
                layout = self.content_layout
                if layout is not None:
                    layout.addWidget(self._text, 0, 0)
                # Re-align ports after custom width/height
                self._update_port_positions()
        except Exception:
            self._text = None
    
    def _show_text_context_menu(self, position):
        """Show custom context menu for text widget."""
        try:
            from PySide6.QtWidgets import QMenu
            from PySide6.QtGui import QAction
            
            if self._text is None:
                return
            
            menu = QMenu(self._text)
            
            # Copy Selected Text action
            copy_action = QAction("Copy Selected Text", self._text)
            copy_action.setEnabled(self._text.textCursor().hasSelection())
            copy_action.triggered.connect(lambda: self._text.copy())
            menu.addAction(copy_action)
            
            menu.addSeparator()
            
            # Clear action
            clear_action = QAction("Clear", self._text)
            clear_action.triggered.connect(lambda: self._text.clear())
            menu.addAction(clear_action)
            
            # Show menu at cursor position
            menu.exec_(self._text.mapToGlobal(position))
        except Exception as e:
            self.logger.error(f"Error showing context menu: {e}")

    def _stringify(self, value: Any) -> str:
        try:
            if isinstance(value, (dict, list)):
                import json
                return json.dumps(value, indent=2)[:8000]
            return str(value)
        except Exception:
            return str(value)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        content = None
        if inputs:
            content = inputs.get("string") if inputs.get("string") is not None else inputs.get("data")
        text = self._stringify(content)
        return {"text_preview": text[:2000]}

    def on_result(self, result: object) -> None:
        try:
            content = self.properties.get("last_input_string")
            if content is None:
                content = self.properties.get("last_input_data")
            if self._text is not None:
                self._text.setPlainText(self._stringify(content))
        except Exception:
            pass
        super().on_result(result)
