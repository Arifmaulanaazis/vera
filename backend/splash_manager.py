"""
Splash screen manager for VERA.
Shows a lightweight, borderless dialog with a background image and progress text
while the main application initializes.

UI responsibilities live in UI/splash_ui.py (generated from UI/splash.ui).
This module exposes a simple API for the app entry point to control the splash.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QVariantAnimation
from PySide6.QtGui import QPixmap, QIcon, QPainter, QLinearGradient, QColor, QFont, QBrush
from PySide6.QtWidgets import QDialog, QGraphicsDropShadowEffect, QGraphicsOpacityEffect

from UI.splash_ui import Ui_SplashDialog
from core.app_control import APP_INFO

try:
    from backend.resource_access import get_theme_icon_path, get_theme_icon
except Exception:  # pragma: no cover - fallback import path during early boot
    get_theme_icon_path = None  # type: ignore
    get_theme_icon = None  # type: ignore


class SplashController:
    """Controller for the splash dialog."""

    def __init__(self, parent=None):
        self._dialog = QDialog(parent)
        self._ui = Ui_SplashDialog()
        self._ui.setupUi(self._dialog)

        # Window flags: splash style, always on top, no taskbar icon
        flags = (
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.SplashScreen
        )
        try:
            self._dialog.setWindowFlags(flags)
            self._dialog.setAttribute(Qt.WA_TranslucentBackground)
        except Exception:
            pass
        
        # Add drop shadow effect for modern look
        # Note: Shadow will be applied after opacity setup to avoid conflicts
        self._setup_shadow_later = True

        # Set window/icon and texts
        try:
            from datetime import datetime
            app_name = APP_INFO.get("name", "VERA")
            version = APP_INFO.get("version", "1.0.0")
            copyright = APP_INFO.get("copyright", f"© {datetime.now().year} VERA, All Rights Reserved.")
            
            # Shorten full name for splash
            display_name = "Virtual Execution and Reaction Architecture"
            
            self._ui.labelAppName.setText(app_name)
            # Add subtitle with full name
            try:
                self._ui.labelStatus.setText(display_name)
                self._ui.labelStatus.setStyleSheet("color: rgba(255, 255, 255, 0.9); font-size: 11px; font-style: italic;")
            except Exception:
                pass
            self._ui.labelVersion.setText(f"Version {version} - {copyright}")
        except Exception:
            pass
        
        # Load logo image first to ensure immediate display
        self._load_logo_image()
        
        # Apply styling
        self._apply_styling()
        
        # Setup animations for fade-in effect (after content is loaded)
        self._setup_animations()
        
        # Apply shadow after animations to avoid conflicts
        if hasattr(self, '_setup_shadow_later') and self._setup_shadow_later:
            self._apply_shadow()

        # Try window icon
        try:
            if get_theme_icon is not None:
                icon = get_theme_icon("vera.ico")
                if not icon.isNull():
                    self._dialog.setWindowIcon(icon)
            elif get_theme_icon_path is not None:
                icon_path = get_theme_icon_path("vera.ico")
                if icon_path:
                    self._dialog.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass

        # Center on primary screen after shown
        QTimer.singleShot(0, self._center_on_primary_screen)
        
    def _setup_animations(self):
        """Setup fade-in animations for elements"""
        try:
            # Main window fade-in
            self._dialog.setWindowOpacity(0.0)
            self.fade_anim = QPropertyAnimation(self._dialog, b"windowOpacity")
            self.fade_anim.setDuration(600)
            self.fade_anim.setStartValue(0.0)
            self.fade_anim.setEndValue(1.0)
            self.fade_anim.setEasingCurve(QEasingCurve.OutCubic)
            self.fade_anim.start()
            
            # Setup smooth progress bar animation
            self._target_progress = 0
            self.progress_anim = QPropertyAnimation(self._ui.progressBar, b"value")
            self.progress_anim.setEasingCurve(QEasingCurve.OutQuad)
            
        except Exception as e:
            print(f"Splash animation setup failed: {e}")

    def _apply_shadow(self):
        """Apply drop shadow effect after other effects are set up"""
        try:
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(20)
            shadow.setXOffset(0)
            shadow.setYOffset(5)
            shadow.setColor(QColor(0, 0, 0, 60))
            # Apply shadow directly since we're not using opacity effects
            self._dialog.setGraphicsEffect(shadow)
        except Exception:
            pass

    def _load_logo_image(self) -> None:
        """Load and display the splash logo image"""
        # Load logo image immediately using resource system
        if hasattr(self._ui, 'labelLogo'):
            try:
                # Try to get logo from resources first
                logo_path = None
                if get_theme_icon_path is not None:
                    logo_path = get_theme_icon_path("vera.png")
                
                # If resource path not found, try fallback names
                if not logo_path:
                    for name in ("vera.png"):
                        try:
                            if get_theme_icon_path is not None:
                                logo_path = get_theme_icon_path(name)
                                if logo_path:
                                    break
                        except Exception:
                            continue
                
                # Load and display the logo
                if logo_path:
                    pixmap = QPixmap(logo_path)
                    if not pixmap.isNull():
                        # Scale to fit container better - use more space for logo
                        # Container is 700x300 (image frame), leave margins for text
                        # Use up to 500x200 for logo to make it more prominent
                        scaled_pixmap = pixmap.scaled(500, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self._ui.labelLogo.setPixmap(scaled_pixmap)
                        
                        # Add white glow shadow to make the logo pop out regardless of color
                        self.logo_shadow = QGraphicsDropShadowEffect()
                        self.logo_shadow.setBlurRadius(25)
                        self.logo_shadow.setXOffset(0)
                        self.logo_shadow.setYOffset(0)
                        self.logo_shadow.setColor(QColor(255, 255, 255, 150))
                        self._ui.labelLogo.setGraphicsEffect(self.logo_shadow)
                        
                        # Add a breathing/pulsating effect to the shadow
                        self.pulse_anim = QVariantAnimation(self._dialog)
                        self.pulse_anim.setDuration(1500)
                        self.pulse_anim.setStartValue(25) # Original blur radius
                        self.pulse_anim.setEndValue(50)   # Expanded glow
                        
                        def update_shadow(val):
                            self.logo_shadow.setBlurRadius(val)
                            
                        self.pulse_anim.valueChanged.connect(update_shadow)
                        self.pulse_anim.setLoopCount(-1) # Infinite loop
                        self.pulse_anim.setDirection(QVariantAnimation.Backward) # Yo-yo effect setup
                        self.pulse_anim.start()
                        
                        # Make sure logo shows immediately
                        self._ui.labelLogo.setVisible(True)
                        self._ui.labelLogo.update()
                else:
                    # If no logo found, hide the label to save space
                    self._ui.labelLogo.setVisible(False)
            except Exception as e:
                # Hide logo label if loading fails
                self._ui.labelLogo.setVisible(False)
    
    def _apply_styling(self) -> None:
        """Apply modern styling to the splash dialog"""
        style = """
        QDialog#SplashRoot {
            background-color: transparent;
            border-radius: 15px;
        }
        
        QFrame#imageFrame {
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 #1A2980,
                stop: 1 #26D0CE
            );
            border-top-left-radius: 15px;
            border-top-right-radius: 15px;
            border-bottom-left-radius: 0px;
            border-bottom-right-radius: 0px;
        }
        
        QFrame#progressFrame {
            background-color: rgba(255, 255, 255, 0.95);
            border-top-left-radius: 0px;
            border-top-right-radius: 0px;
            border-bottom-left-radius: 15px;
            border-bottom-right-radius: 15px;
            border: none;
        }
        
        QLabel#labelAppName {
            color: #ffffff;
            font-size: 28px;
            font-weight: bold;
            font-family: 'Segoe UI', 'Arial', sans-serif;
            background: transparent;
            padding: 5px;
        }
        
        QLabel#labelStatus {
            color: rgba(255, 255, 255, 0.9);
            font-size: 11px;
            font-style: italic;
            font-family: 'Segoe UI', 'Arial', sans-serif;
            background: transparent;
            padding: 2px;
        }
        
        QLabel#labelLogo {
            background: transparent;
        }
        
        QLabel#labelVersion {
            color: #666666;
            font-size: 10px;
            font-family: 'Segoe UI', 'Arial', sans-serif;
            background: transparent;
        }
        
        QProgressBar {
            background-color: #f0f0f0;
            border: 1px solid #d0d0d0;
            border-radius: 8px;
            height: 16px;
            text-align: center;
        }
        
        QProgressBar::chunk {
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 0,
                stop: 0 #00B4DB,
                stop: 1 #0083B0
            );
            border-radius: 7px;
        }
        """
        
        try:
            self._dialog.setStyleSheet(style)
            # Set a minimum size for better appearance
            self._dialog.setMinimumSize(700, 400)
            self._dialog.setMaximumSize(700, 400)
        except Exception:
            pass

    def _center_on_primary_screen(self) -> None:
        try:
            screen = self._dialog.screen()
            if screen is None:
                return
            geo = screen.availableGeometry()
            dlg = self._dialog.frameGeometry()
            dlg.moveCenter(geo.center())
            self._dialog.move(dlg.topLeft())
        except Exception:
            pass

    # Public API
    def show(self) -> None:
        try:
            self._dialog.show()
            self._dialog.raise_()
        except Exception:
            pass

    def close(self) -> None:
        try:
            self._dialog.close()
        except Exception:
            pass

    def set_status(self, text: str) -> None:
        # Update the status label with loading progress text
        try:
            if hasattr(self._ui, 'labelStatus'):
                self._ui.labelStatus.setText(text)
                self._ui.labelStatus.update()
        except Exception:
            pass

    def set_progress(self, value: int) -> None:
        try:
            v = max(0, min(100, int(value)))
            # Use smooth animation if available
            if hasattr(self, 'progress_anim'):
                self.progress_anim.stop()
                current = self._ui.progressBar.value()
                self.progress_anim.setDuration(150 + abs(v - current) * 3) # Dynamic duration
                self.progress_anim.setStartValue(current)
                self.progress_anim.setEndValue(v)
                self.progress_anim.start()
            else:
                self._ui.progressBar.setValue(v)
        except Exception:
            pass


_splash_controller: Optional[SplashController] = None


def show_splash(parent=None) -> SplashController:
    global _splash_controller
    if _splash_controller is None:
        _splash_controller = SplashController(parent)
    _splash_controller.show()
    return _splash_controller


def close_splash() -> None:
    global _splash_controller
    if _splash_controller is not None:
        _splash_controller.close()
        _splash_controller = None


def set_status(text: str) -> None:
    try:
        if _splash_controller is not None:
            _splash_controller.set_status(text)
    except Exception:
        pass


def set_progress(value: int) -> None:
    try:
        if _splash_controller is not None:
            _splash_controller.set_progress(value)
    except Exception:
        pass


