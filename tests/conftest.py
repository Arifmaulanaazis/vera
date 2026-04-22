"""
Pytest configuration and shared fixtures for VERA tests.

Sets up a headless Qt application (offscreen platform) and provides
a lightweight-construction fixture so node __init__ methods skip
heavy inline widget creation during tests.
"""

import os
import sys

# Use offscreen platform so Qt widgets can be created without a display
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Ensure the project root is on sys.path so imports work
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest


@pytest.fixture(scope="session")
def qapp():
    """Return a QApplication instance valid for the whole test session."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


@pytest.fixture()
def lightweight(qapp):
    """Set BaseNode._lightweight_construction = True for the duration of a test.

    This prevents nodes from building inline Qt widgets (table views, editors,
    floating panels) during test setup, which speeds up tests significantly and
    avoids irrelevant Qt rendering code paths.
    """
    from core.nodes import BaseNode

    BaseNode._lightweight_construction = True
    yield
    BaseNode._lightweight_construction = False
