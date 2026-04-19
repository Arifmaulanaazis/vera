"""
Qt-related utilities.
"""

from __future__ import annotations


def in_gui_thread() -> bool:
    """Return True if the current thread is the Qt GUI (main) thread.

    Safe if Qt is not initialized; will return False.
    """
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QThread
        app = QApplication.instance()
        if app is None:
            return False
        return QThread.currentThread() == app.thread()
    except Exception:
        return False


