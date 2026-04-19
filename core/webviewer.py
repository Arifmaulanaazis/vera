"""
Thin wrapper window for displaying the web-based molecule viewer using Qt WebEngine.

This keeps UI widgets outside the `UI/` directory per project rules.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings


class MoleculeWebViewerWindow(QMainWindow):
    """A simple window hosting a QWebEngineView for 3D visualization."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("VERA 3D Viewer")
        self.resize(1024, 768)

        self._view = QWebEngineView(self)
        self.setCentralWidget(self._view)

        # Allow local file access and JS for loading trajectory files
        try:
            settings = self._view.page().settings()
            settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        except Exception:
            pass

    def load_viewer_url(self, url: str):
        if isinstance(url, str):
            self._view.setUrl(QUrl(url))


