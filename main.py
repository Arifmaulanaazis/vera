"""
VERA - Virtual Execution and Reaction Architecture
Main application entry point
"""

import sys
import os
import importlib.util
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon

from core.application import VERAApplication
from backend.temp_manager import cleanup_session_temp_dir
from backend.resource_manager import initialize_resources
from core.app_control import APP_INFO
from backend.splash_manager import show_splash, close_splash
from utils.logging_utils import get_logger

logger = get_logger("vera.main")


def main():
    """Main entry point for VERA application."""
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    os.environ["QT_SCALE_FACTOR"] = "1"
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

    app = QApplication(sys.argv)
    app.setApplicationName(APP_INFO.get("name", "VERA"))
    app.setApplicationVersion(APP_INFO.get("version", "1.0.0"))
    app.setOrganizationName(APP_INFO.get("organization", "VERA"))
    try:
        app.setQuitOnLastWindowClosed(True)
    except Exception:
        pass

    # Set application icon if available
    try:
        from backend.resource_access import get_theme_icon_path
        icon_path = get_theme_icon_path("vera.ico")
        if icon_path:
            app.setWindowIcon(QIcon(icon_path))
    except ImportError:
        icon_path = project_root / "theme" / "icons" / "vera.ico"
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))

    # Show splash screen
    splash = show_splash()
    splash.set_status("Loading VERA...")
    splash.set_progress(10)

    vera_app = None
    
    # Define core modules to check for a realistic startup
    core_modules = [
        "numpy", "pandas", "matplotlib", "scipy", 
        "sklearn", "rdkit", "Bio", "MDAnalysis",
        "requests", "bs4", "openpyxl", "urllib3"
    ]
    
    startup_steps = [
        {"msg": "Checking system environment...", "progress": 15},
        {"msg": "Initializing core resources...", "action": initialize_resources, "progress": 25},
    ]
    
    # Add realistic checks for critical packages
    for i, mod in enumerate(core_modules):
        prog = 25 + (i / len(core_modules)) * 50
        startup_steps.append({
            "msg": f"Verifying dependency: {mod}...", 
            "action": lambda m=mod: importlib.util.find_spec(m),
            "progress": int(prog)
        })
        
    startup_steps.append({"msg": "Building VERA core architecture...", "progress": 80})
    startup_steps.append({"msg": "Starting application...", "progress": 90})

    current_step = 0

    def execute_next_step():
        nonlocal current_step, vera_app
        if current_step < len(startup_steps):
            step = startup_steps[current_step]
            splash.set_status(step["msg"])
            splash.set_progress(step["progress"])
            
            if "action" in step:
                try:
                    step["action"]()
                except Exception as e:
                    logger.warning(f"Startup warning ({step['msg']}): {e}")
            
            current_step += 1
            # Add a slight delay between checks to make sure the user can see them and progress is smooth
            QTimer.singleShot(150, execute_next_step)
        else:
            # Final step: instantiate application
            try:
                vera_app = VERAApplication()
                import builtins
                builtins.VERA_APP_INSTANCE = vera_app # Ensure global access if needed
                vera_app.show()

                # Center main window on screen
                try:
                    screen = app.primaryScreen()
                    if screen:
                        geo = screen.availableGeometry()
                        vera_app.move(
                            (geo.width() - vera_app.width()) // 2,
                            (geo.height() - vera_app.height()) // 2
                        )
                except Exception:
                    pass

                splash.set_progress(100)
                splash.set_status("Ready!")

                # Close splash after main app is ready
                QTimer.singleShot(800, close_splash)

            except Exception as e:
                logger.error(f"Error creating main application: {e}")
                close_splash()

    # Startup sequence: show splash then process steps
    QTimer.singleShot(500, execute_next_step)

    # Ensure cleanup on application exit
    try:
        app.aboutToQuit.connect(cleanup_session_temp_dir)
    except Exception:
        pass

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
