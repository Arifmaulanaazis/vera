"""
Utility nodes: NoteNode (sticky note / comment on canvas).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont

from core.nodes import BaseNode
from utils.logging_utils import get_logger

# Predefined note colors (background fill)
_NOTE_COLORS: Dict[str, str] = {
    "yellow": "#3a3820",
    "blue": "#1e2a3a",
    "green": "#1e3a22",
    "red": "#3a1e1e",
    "purple": "#2a1e3a",
    "gray": "#2a2a2a",
}

_NOTE_BORDER_COLORS: Dict[str, str] = {
    "yellow": "#d8b400",
    "blue": "#4a8aba",
    "green": "#4aba6a",
    "red": "#ba4a4a",
    "purple": "#8a4aba",
    "gray": "#666666",
}

_NOTE_TEXT_COLORS: Dict[str, str] = {
    "yellow": "#ffe28a",
    "blue": "#a8d0f0",
    "green": "#a8f0b8",
    "red": "#f0a8a8",
    "purple": "#d0a8f0",
    "gray": "#cccccc",
}

# Re-export every helper/import so split node files keep the original module namespace.
__all__ = [name for name in globals() if not name.startswith("__")]
