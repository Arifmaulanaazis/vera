"""
Floating control panel overlay similar to ComfyUI's bottom-center bar.
Provides actions for running, pausing, resuming, stopping, validating, and clearing the workflow.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize, QSettings
from PySide6.QtWidgets import QWidget, QHBoxLayout, QToolButton, QFrame, QSizePolicy, QGraphicsDropShadowEffect, QVBoxLayout, QProgressBar
from PySide6.QtGui import QIcon

def _get_floating_text_color(theme_id=None):
    if theme_id is None:
        try:
            theme_id = str(QSettings().value("ui/theme_id", "") or "").lower()
        except Exception:
            theme_id = ""
    theme_id = (theme_id or "").lower()
    dark_themes = ["amoled_dark", "dracula", "nord", "win11_dark"]
    is_dark = any(dt in theme_id for dt in dark_themes)
    return "#e0e0e0" if is_dark else "#000000"


class FloatingControlPanel(QFrame):
    """Bottom-center floating control panel with action buttons."""

    run_requested = Signal()
    pause_requested = Signal()
    resume_requested = Signal()
    stop_requested = Signal()
    validate_requested = Signal()
    clear_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._is_running = False
        self._is_paused = False
        self._is_waiting_user_input = False  # Track user input pause state
        self._build_ui()

    def _build_ui(self):
        self.setObjectName("FloatingControlPanel")
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        # Opaque panel (no transparency), like ComfyUI
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setWindowFlags(Qt.Widget | Qt.FramelessWindowHint)

        # Frame layout (vertical: progress bar on top, buttons row below)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Progress bar container (initially hidden)
        self._progress_container = QFrame(self)
        self._progress_container.setObjectName("WorkflowProgressPanel")
        p_layout = QHBoxLayout(self._progress_container)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(0)
        self._progress_bar = QProgressBar(self._progress_container)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(0)
        p_layout.addWidget(self._progress_bar)
        self._progress_container.setVisible(False)
        layout.addWidget(self._progress_container)

        # Inner row container to tightly group buttons together
        row = QWidget(self)
        row.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        # Buttons
        self.btn_run = QToolButton(row); self._style_button(self.btn_run, "floating_control_play.png", "Run workflow")
        self.btn_pause = QToolButton(row); self._style_button(self.btn_pause, "floating_control_pause.png", "Pause workflow")
        self.btn_resume = QToolButton(row); self._style_button(self.btn_resume, "floating_control_resume.png", "Resume workflow")
        self.btn_stop = QToolButton(row); self._style_button(self.btn_stop, "floating_control_stop.png", "Stop workflow")
        self.btn_validate = QToolButton(row); self._style_button(self.btn_validate, "floating_control_validate.png", "Validate workflow")
        self.btn_clear = QToolButton(row); self._style_button(self.btn_clear, "floating_control_clear.png", "Clear canvas")

        # Order similar to ComfyUI: run, pause/resume, stop, validate, clear
        row_layout.addWidget(self.btn_run)
        row_layout.addWidget(self.btn_pause)
        row_layout.addWidget(self.btn_resume)
        row_layout.addWidget(self.btn_stop)
        row_layout.addWidget(self.btn_validate)
        row_layout.addWidget(self.btn_clear)
        layout.addWidget(row)

        # Keep the entire frame sized to content
        from PySide6.QtWidgets import QLayout
        layout.setSizeConstraint(QLayout.SetFixedSize)

        # Subtle shadow for floating effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 2)
        shadow.setColor(Qt.black)
        self.setGraphicsEffect(shadow)

        # Connections
        self.btn_run.clicked.connect(self.run_requested.emit)
        self.btn_pause.clicked.connect(self.pause_requested.emit)
        self.btn_resume.clicked.connect(self.resume_requested.emit)
        self.btn_stop.clicked.connect(self.stop_requested.emit)
        self.btn_validate.clicked.connect(self.validate_requested.emit)
        self.btn_clear.clicked.connect(self.clear_requested.emit)

        # Initial state
        self.set_state(is_running=False, is_paused=False)

        # Styling
        self.apply_styles()

    def apply_styles(self, theme_id=None):
        text_color = _get_floating_text_color(theme_id)
        self.setStyleSheet(
            f"""
            QFrame#FloatingControlPanel {{
                background-color: #202020;
                border: 1px solid #505050;
                border-radius: 12px;
            }}
            QFrame#WorkflowProgressPanel {{
                background-color: #2b2b2b;
                border: 1px solid #666666;
                border-radius: 6px;
            }}
            QProgressBar {{
                color: {text_color};
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                text-align: center;
                padding: 2px;
            }}
            QProgressBar::chunk {{ background-color: #4CAF50; }}
            QToolButton {{
                color: {text_color};
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 6px 10px;
            }}
            QToolButton:hover {{ background-color: #505050; }}
            QToolButton:pressed {{ background-color: #2f2f2f; }}
            QToolButton:disabled {{ color: #888; background-color: #2a2a2a; border-color: #444; }}
            """
        )

    def _style_button(self, btn: QToolButton, icon_filename: str, tooltip: str):
        """Apply common styling and set icon from theme with graceful fallback to text."""
        try:
            # Try using resource system first
            from backend.resource_access import get_theme_icon_path
            icon_path = get_theme_icon_path(icon_filename)
            
            if icon_path and (icon_path.startswith(":/") or Path(icon_path).exists()):
                btn.setIcon(QIcon(icon_path))
                btn.setIconSize(QSize(20, 20))
                btn.setText("")
                btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
                btn.setToolTip(tooltip)
                btn.setCursor(Qt.PointingHandCursor)
                return
        except ImportError:
            # Resource system not available, try original path
            icon_path = (Path(__file__).resolve().parent.parent / "theme" / "icons" / icon_filename)
            try:
                if icon_path.exists():
                    btn.setIcon(QIcon(str(icon_path)))
                    btn.setIconSize(QSize(20, 20))
                    btn.setText("")
                    btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
                    btn.setToolTip(tooltip)
                    btn.setCursor(Qt.PointingHandCursor)
                    return
            except Exception:
                pass
        except Exception:
            pass
        
        # Fallback to unicode text if icon loading failed
        btn.setText(self._fallback_text_for_icon(icon_filename))
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)

    def _fallback_text_for_icon(self, icon_filename: str) -> str:
        mapping = {
            "floating_control_play.png": "▶",
            "floating_control_pause.png": "⏸",
            "floating_control_resume.png": "⏵",
            "floating_control_stop.png": "⏹",
            "floating_control_validate.png": "✔",
            "floating_control_clear.png": "✖",
        }
        return mapping.get(icon_filename, "•")

    def set_state(self, is_running: bool, is_paused: bool):
        """Update buttons enabled/visible state based on manager state."""
        self._is_running = is_running
        self._is_paused = is_paused

        # If waiting for user input, disable run button too
        run_enabled = not is_running and not self._is_waiting_user_input
        self.btn_run.setEnabled(run_enabled)
        self.btn_stop.setEnabled(is_running)
        self.btn_pause.setEnabled(is_running and not is_paused and not self._is_waiting_user_input)
        self.btn_resume.setEnabled(is_running and is_paused and not self._is_waiting_user_input)
        # Validate and Clear always available
        # Update progress bar color/label to reflect pause state
        self._apply_progress_visual_state()
    
    def set_user_input_state(self, waiting_for_input: bool):
        """Update state when waiting for user input (separate from workflow pause)."""
        self._is_waiting_user_input = waiting_for_input
        # Refresh button states
        self.set_state(self._is_running, self._is_paused)

    # ---- Workflow progress helpers (for application wiring) ----
    def show_workflow_progress(self, total_nodes: int, executed_nodes: int = 0) -> None:
        """Show progress bar above controls with executed/total nodes.

        The bar range is 0..total_nodes and the format shows "executed/total — %p%".
        """
        try:
            total = max(0, int(total_nodes))
            done = max(0, min(int(executed_nodes), total))
            if total <= 0:
                # Show indeterminate if nothing to count
                self._progress_bar.setRange(0, 0)
                base = "Working…"
                self._progress_bar.setFormat(base + ("  paused" if self._is_paused else ""))
            else:
                # Use node count range so %p% reflects percent of nodes
                self._progress_bar.setRange(0, total)
                self._progress_bar.setValue(done)
                suffix = "  paused" if self._is_paused else ""
                self._progress_bar.setFormat(f"{done} / {total} nodes — %p%{suffix}")
            self._progress_container.setVisible(True)
            # Ensure frame re-sizes to include progress bar
            try:
                from PySide6.QtWidgets import QLayout
                self.layout().setSizeConstraint(QLayout.SetFixedSize)  # type: ignore[union-attr]
            except Exception:
                pass
        except Exception:
            pass

    def update_workflow_progress(self, executed_nodes: int, total_nodes: int | None = None) -> None:
        try:
            total = self._progress_bar.maximum() if total_nodes is None else max(0, int(total_nodes))
            done = max(0, int(executed_nodes))
            if total <= 0:
                self._progress_bar.setRange(0, 0)
                base = "Working…"
                self._progress_bar.setFormat(base + ("  paused" if self._is_paused else ""))
            else:
                if self._progress_bar.maximum() != total:
                    self._progress_bar.setRange(0, total)
                self._progress_bar.setValue(min(done, total))
                suffix = "  paused" if self._is_paused else ""
                self._progress_bar.setFormat(f"{min(done, total)} / {total} nodes — %p%{suffix}")
            if not self._progress_container.isVisible():
                self._progress_container.setVisible(True)
        except Exception:
            pass

    def hide_workflow_progress(self) -> None:
        try:
            self._progress_container.setVisible(False)
        except Exception:
            pass

    # ---- Internal helpers ----
    def _apply_progress_visual_state(self) -> None:
        try:
            if self._progress_bar is None:
                return
            if self._is_paused:
                # Yellow chunk for paused state
                self._progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #f0c800; }")
            else:
                # Revert to default (blue) by clearing local override
                self._progress_bar.setStyleSheet("")
            # Also refresh text format to include/remove 'paused'
            # Re-emit current values to update format without changing value
            try:
                maxv = self._progress_bar.maximum()
                val = self._progress_bar.value()
                if maxv <= 0:
                    base = "Working…"
                    self._progress_bar.setFormat(base + ("  paused" if self._is_paused else ""))
                else:
                    suffix = "  paused" if self._is_paused else ""
                    self._progress_bar.setFormat(f"{val} / {maxv} nodes — %p%{suffix}")
            except Exception:
                pass
        except Exception:
            pass


