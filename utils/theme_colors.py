"""
Theme-aware color utilities for nodes and ports.

This module provides functions to extract colors from the current Qt theme
and use them for node and port styling, ensuring consistency with the overall theme.
"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
import re
from typing import Dict, Optional


def get_theme_colors() -> Dict[str, QColor]:
    """
    Extract colors from the current Qt application stylesheet.

    Returns:
        Dictionary of color names to QColor objects
    """
    app = QApplication.instance()
    if app is None:
        return get_default_theme_colors()

    stylesheet = app.styleSheet()
    if not stylesheet:
        return get_default_theme_colors()

    colors = {}

    # Common color patterns in QSS
    color_patterns = {
        'background': re.compile(r'background:\s*([#\w]+)', re.IGNORECASE),
        'color': re.compile(r'color:\s*([#\w]+)', re.IGNORECASE),
        'border-color': re.compile(r'border-color:\s*([#\w]+)', re.IGNORECASE),
        'selection-background-color': re.compile(r'selection-background-color:\s*([#\w]+)', re.IGNORECASE),
    }

    # Extract colors from stylesheet
    for color_type, pattern in color_patterns.items():
        matches = pattern.findall(stylesheet)
        if matches:
            # Use the most common color for this type
            color_value = matches[0] if matches else None
            if color_value:
                try:
                    colors[color_type] = QColor(color_value)
                except:
                    pass

    # If we couldn't extract enough colors, use defaults
    if len(colors) < 3:
        return get_default_theme_colors()

    return colors


def get_default_theme_colors() -> Dict[str, QColor]:
    """Get balanced Tailwind-style default theme colors for when theme extraction fails."""
    return {
        'background': QColor(55, 65, 81),      # gray-700 - balanced dark
        'color': QColor(243, 244, 246),        # gray-100 - light text
        'border-color': QColor(107, 114, 128), # gray-500 - balanced border
        'selection-background-color': QColor(59, 130, 246), # blue-500 - balanced selection
    }


def get_node_colors_for_state(is_validating: bool = False, is_running: bool = False, is_paused: bool = False,
                             is_completed: bool = False, is_error: bool = False,
                             is_selected: bool = False) -> tuple[QColor, int, QColor, QColor]:
    """
    Get node colors based on execution state, using theme-aware colors.

    Returns:
        Tuple of (border_color, border_width, background_color, title_color)
    """
    theme_colors = get_theme_colors()

    # Base colors from theme
    base_background = theme_colors.get('background', QColor(60, 60, 60))
    base_text = theme_colors.get('color', QColor(230, 230, 230))
    base_border = theme_colors.get('border-color', QColor(100, 100, 100))
    selection_color = theme_colors.get('selection-background-color', QColor(96, 165, 250))

    if is_selected:
        border_color = QColor(59, 130, 246)  # blue-500 for consistency
        border_width = 3
    else:
        border_width = 1

    # Calculate state-based colors using Tailwind CSS palette - balanced
    if is_validating:
        # Tailwind blue-600 - balanced professional blue
        border_color = QColor(37, 99, 235)  # blue-600
        border_width = 3
        background_color = QColor(
            min(255, base_background.red() + 18),
            min(255, base_background.green() + 25),
            min(255, base_background.blue() + 42)
        )
        title_color = QColor(
            min(255, base_background.red() + 30),
            min(255, base_background.green() + 40),
            min(255, base_background.blue() + 60)
        )
    elif is_running:
        # Tailwind green-600 - balanced professional green
        border_color = QColor(5, 150, 105)  # green-600
        border_width = 3
        background_color = QColor(
            min(255, base_background.red() + 15),
            min(255, base_background.green() + 30),
            min(255, base_background.blue() + 15)
        )
        title_color = QColor(
            min(255, base_background.red() + 25),
            min(255, base_background.green() + 50),
            min(255, base_background.blue() + 25)
        )
    elif is_paused:
        # Tailwind amber-600 - balanced professional yellow/amber
        border_color = QColor(245, 158, 11)  # amber-600
        border_width = 3
        background_color = QColor(
            min(255, base_background.red() + 30),
            min(255, base_background.green() + 28),
            min(255, base_background.blue() + 10)
        )
        title_color = QColor(
            min(255, base_background.red() + 45),
            min(255, base_background.green() + 38),
            min(255, base_background.blue() + 12)
        )
    elif is_completed:
        # Tailwind purple-600 - balanced professional purple
        border_color = QColor(124, 58, 237)  # purple-600
        border_width = 2
        background_color = QColor(
            min(255, base_background.red() + 22),
            min(255, base_background.green() + 12),
            min(255, base_background.blue() + 38)
        )
        title_color = QColor(
            min(255, base_background.red() + 35),
            min(255, base_background.green() + 18),
            min(255, base_background.blue() + 55)
        )
    elif is_error:
        # Tailwind red-600 - balanced professional red
        border_color = QColor(220, 38, 38)  # red-600
        border_width = 2
        background_color = QColor(
            min(255, base_background.red() + 30),
            min(255, base_background.green() + 15),
            min(255, base_background.blue() + 15)
        )
        title_color = QColor(
            min(255, base_background.red() + 50),
            min(255, base_background.green() + 22),
            min(255, base_background.blue() + 22)
        )
    else:  # IDLE state - balanced professional title
        border_color = base_border
        border_width = 1
        background_color = base_background
        title_color = QColor(
            min(255, base_background.red() + 35),
            min(255, base_background.green() + 35),
            min(255, base_background.blue() + 35)
        )

    return border_color, border_width, background_color, title_color


def get_port_color_for_type(data_type: str) -> QColor:
    """
    Get port color based on data type, using theme-aware approach.

    Args:
        data_type: The data type string (e.g., 'file', 'string', 'molecules')

    Returns:
        QColor for the port
    """
    theme_colors = get_theme_colors()
    base_text = theme_colors.get('color', QColor(230, 230, 230))
    selection_color = theme_colors.get('selection-background-color', QColor(96, 165, 250))

    # Tailwind CSS port colors - balanced and professional
    type_colors = {
        "any": QColor(156, 163, 175),  # gray-400 - balanced
        "file": QColor(59, 130, 246),  # blue-500 - balanced
        "string": QColor(249, 115, 22),  # orange-500 - balanced
        "data": QColor(16, 185, 129),  # emerald-500 - balanced
        "list": QColor(139, 92, 246),  # violet-500 - balanced
        "molecules": QColor(236, 72, 153),  # pink-500 - balanced
        "bytes": QColor(6, 182, 212),  # cyan-500 - balanced
        "image": QColor(239, 68, 68),  # red-500 - balanced
        "model": QColor(14, 165, 233),  # sky-500 - balanced
    }

    return type_colors.get(data_type, type_colors["any"])

