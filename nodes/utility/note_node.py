"""NoteNode implementation."""

from .common import *  # noqa: F401,F403

class NoteNode(BaseNode):
    """A sticky note / comment node — no ports, does not participate in execution.

    Double-click to edit text.  The note color can be changed via the
    settings dialog (Color property).
    """

    def __init__(self):
        super().__init__("note", "Note")
        self.logger = get_logger(__name__)

        # No ports — notes are purely visual
        self.width = 220
        self.height = 140
        self.setMinimumSize(120, 80)

        self.set_property("text", "Add your notes here…")
        self.set_property("color", "yellow")

        self._note_edit = None

        try:
            from core.nodes import BaseNode as _BaseNode
            if getattr(_BaseNode, "_lightweight_construction", False):
                return
            from PySide6.QtWidgets import QPlainTextEdit, QSpacerItem, QSizePolicy

            edit = QPlainTextEdit()
            edit.setPlainText(self.get_property("text") or "")
            edit.setStyleSheet(
                "QPlainTextEdit { background: transparent; border: none; "
                "color: #ffe28a; font-size: 11px; }"
            )
            edit.setFrameStyle(0)
            edit.textChanged.connect(self._on_text_changed)
            self._note_edit = edit

            layout = self.content_layout
            if layout is not None:
                layout.addItem(QSpacerItem(0, 2, QSizePolicy.Minimum, QSizePolicy.Fixed), 0, 0)
                layout.addWidget(edit, 1, 0)
            self._update_port_positions()
        except Exception:
            self._note_edit = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _color_key(self) -> str:
        return (self.get_property("color") or "yellow").lower()

    def _bg_color(self) -> QColor:
        return QColor(_NOTE_COLORS.get(self._color_key(), "#3a3820"))

    def _border_color(self) -> QColor:
        return QColor(_NOTE_BORDER_COLORS.get(self._color_key(), "#d8b400"))

    def _text_color(self) -> QColor:
        return QColor(_NOTE_TEXT_COLORS.get(self._color_key(), "#ffe28a"))

    def _on_text_changed(self):
        try:
            if self._note_edit is not None:
                self.set_property("text", self._note_edit.toPlainText())
        except Exception:
            pass

    def _sync_edit_style(self):
        try:
            if self._note_edit is not None:
                tc = self._text_color().name()
                self._note_edit.setStyleSheet(
                    f"QPlainTextEdit {{ background: transparent; border: none; "
                    f"color: {tc}; font-size: 11px; }}"
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Paint override — draw note-style background, skip default title bar
    # ------------------------------------------------------------------

    def paint(self, painter: QPainter, option, widget):
        bg = self._bg_color()
        border = self._border_color()

        node_rect = QRectF(0, 0, self.width, self.height)

        # Background
        painter.setPen(QPen(border, 1.5))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(node_rect, 6, 6)

        # Folded-corner decoration (top-right)
        fold = 14.0
        pts = [
            (self.width - fold, 0),
            (self.width, fold),
            (self.width - fold, fold),
        ]
        from PySide6.QtGui import QPolygonF
        from PySide6.QtCore import QPointF
        poly = QPolygonF([QPointF(x, y) for x, y in pts])
        darker = QColor(border)
        darker.setAlphaF(0.6)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(darker))
        painter.drawPolygon(poly)
        painter.setPen(QPen(border, 1))
        painter.drawLine(
            int(self.width - fold), 0,
            int(self.width - fold), int(fold),
        )
        painter.drawLine(
            int(self.width - fold), int(fold),
            int(self.width), int(fold),
        )

        # Selection highlight
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(node_rect, 6, 6)

        # Keep content geometry up to date
        self._update_content_geometry()
        self._sync_edit_style()

    # ------------------------------------------------------------------
    # NoteNode does NOT execute — return empty dict silently
    # ------------------------------------------------------------------

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {}

    def validate(self) -> tuple[bool, str]:
        return True, "Note is always valid"

    def _inline_summary(self) -> list[str]:
        return []

    # ------------------------------------------------------------------
    # Sync property changes to the inline editor
    # ------------------------------------------------------------------

    def set_property(self, key: str, value: Any):
        super().set_property(key, value)
        if key == "text":
            try:
                if self._note_edit is not None:
                    current = self._note_edit.toPlainText()
                    if current != str(value):
                        self._note_edit.blockSignals(True)
                        self._note_edit.setPlainText(str(value))
                        self._note_edit.blockSignals(False)
            except Exception:
                pass
        if key == "color":
            try:
                self._sync_edit_style()
                self.update()
            except Exception:
                pass
