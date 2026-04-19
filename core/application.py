"""
Main application class for VERA.
Handles the main window and overall application logic.
"""
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QDockWidget, QApplication
from PySide6.QtCore import QSettings, QTimer, Qt

from UI.main_window_ui import MainWindowUI
from core.canvas import WorkflowCanvas
from core.toolbox import NodeToolbox
from core.floating_controls import FloatingControlPanel
from backend.workflow_manager import WorkflowManager
from PySide6.QtWebEngineCore import QWebEngineSettings  # ensure WebEngine initialized
from backend.temp_manager import init_session_temp_dir, cleanup_session_temp_dir
from core.toast import ToastOverlay
from UI.recent_projects_dialog import RecentProjectsDialog
from backend.resource_access import load_theme_qss, list_themes, detect_theme_is_dark
from backend.plugin_manager import reload_plugins_into_factory


class VERAApplication(QMainWindow):
    """Main application window for VERA."""
    
    def __init__(self):
        super().__init__()
        self.settings = QSettings()
        self.workflow_manager = WorkflowManager()
        # Track unsaved changes and guard during programmatic rebuilds
        self._is_dirty: bool = False
        self._is_rebuilding: bool = False
        # Timer to revert transient validation title back to normal
        self._validate_title_revert_timer: QTimer | None = None
        # Per-run progress tracking
        self._run_total_nodes: int = 0
        self._run_executed_nodes: int = 0
        # Initialize session temp workspace
        try:
            init_session_temp_dir()
        except Exception:
            pass
        
        self._setup_ui()
        self._setup_connections()
        self._restore_settings()
        # Apply persisted theme (if any)
        try:
            theme_id = str(self.settings.value("ui/theme_id", "") or "")
            self._apply_theme(theme_id)
            self.ui.set_theme_checked(theme_id)
        except Exception:
            pass
        # Ensure menu action reflects restored dock visibility
        try:
            self.ui.set_toolbox_action_checked(self.toolbox_dock.isVisible())
        except Exception:
            pass
        
        # Show recent projects dialog after main window is shown
        QTimer.singleShot(100, self._show_recent_projects_dialog)

    def _show_toast(self, title: str, message: str = "", status: str = "info", duration_ms: int = 2000, closable: bool = False) -> None:
        try:
            if getattr(self, "toast_overlay", None) is not None:
                self.toast_overlay.show_toast(title=title, message=message, status=status, duration_ms=duration_ms, closable=closable)
        except Exception:
            pass

    def _node_title_for(self, node_id: str) -> str:
        try:
            live = getattr(self.workflow_manager, "_node_live_map", {}).get(node_id)
            if live is not None:
                t = getattr(live, "title", None)
                if t:
                    return str(t)
        except Exception:
            pass
        return str(node_id)
        
    def _setup_ui(self):
        """Initialize the user interface."""
        # Load UI from file
        self.ui = MainWindowUI()
        self.ui.setup_ui(self)
        
        # Central canvas as main area
        central_widget = QWidget()
        central_layout = QHBoxLayout(central_widget)
        central_layout.setContentsMargins(5, 5, 5, 5)
        central_layout.setSpacing(5)
        self.setCentralWidget(central_widget)

        # Canvas
        self.canvas = WorkflowCanvas()
        central_layout.addWidget(self.canvas, 1)

        # Toolbox as a docked widget on the left
        self.toolbox = NodeToolbox()
        self.toolbox_dock = QDockWidget("VERA Toolbox", self)
        self.toolbox_dock.setObjectName("NodeToolboxDock")
        self.toolbox_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.toolbox_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable)
        self.toolbox_dock.setMinimumWidth(300)
        self.toolbox_dock.setWidget(self.toolbox)
        self.addDockWidget(Qt.RightDockWidgetArea, self.toolbox_dock)

        # Properties panel dock removed per request (properties now edited via double-click dialog)

        # Floating controls overlay (bottom-center over canvas)
        self.controls_panel = FloatingControlPanel()
        self.canvas.attach_overlay_widget(self.controls_panel)
        self._wire_controls()
        
        # Application-level toast overlay anchored to central widget (top-center)
        try:
            self.toast_overlay = ToastOverlay(self.centralWidget())
            # Hidden until first toast; reflow ensures correct size/position
            self.toast_overlay._reflow()
        except Exception:
            self.toast_overlay = None
        
        # Set window properties
        self.setWindowTitle("VERA - Virtual Execution and Reaction Architecture")
        self.setMinimumSize(1200, 800)
        self.resize(1600, 1000)
        # Reflect current file state in title initially
        try:
            self._update_window_title()
        except Exception:
            pass

        # Ensure toolbox action initial state matches dock visibility
        try:
            self.ui.set_toolbox_action_checked(self.toolbox_dock.isVisible())
        except Exception:
            pass

        # Optionally tune WebEngine defaults once for the app
        try:
            s = QWebEngineSettings.defaultSettings()
            s.setAttribute(QWebEngineSettings.PluginsEnabled, True)
            s.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
            s.setAttribute(QWebEngineSettings.WebGLEnabled, True)
            # Allow local viewer file to fetch other local files and remote URLs
            s.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
            s.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
            # Enhanced settings for better ProLIF interaction support
            s.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, False)  # Prevent auto-popup
            s.setAttribute(QWebEngineSettings.JavascriptCanAccessClipboard, True)
            s.setAttribute(QWebEngineSettings.AllowRunningInsecureContent, True)  # For mixed HTTPS/HTTP content
            s.setAttribute(QWebEngineSettings.DnsPrefetchEnabled, True)
        except Exception:
            pass
        
        # Prepare a reusable single-shot timer for reverting validation title
        try:
            self._validate_title_revert_timer = QTimer(self)
            self._validate_title_revert_timer.setSingleShot(True)
            self._validate_title_revert_timer.timeout.connect(self._update_window_title)
        except Exception:
            self._validate_title_revert_timer = None
        
    def _setup_connections(self):
        """Setup signal-slot connections."""
        # Connect toolbox to canvas
        self.toolbox.node_requested.connect(self.canvas.add_node)
        
        # Connect workflow manager: keep legacy update and add full sync
        self.canvas.workflow_changed.connect(self.workflow_manager.update_workflow)
        self.canvas.workflow_changed.connect(lambda: self.workflow_manager.update_from_canvas(self.canvas))
        # Mark window as dirty on any user-editing change
        self.canvas.workflow_changed.connect(self._on_canvas_modified)
        # Partial re-run from nodes (e.g., Select Columns)
        try:
            self.canvas.partial_rerun_requested.connect(self._on_partial_rerun_requested)
        except Exception:
            pass
        # Bind live canvas for inline UI updates during execution
        self.workflow_manager.bind_canvas(self.canvas)

        # Reflect workflow manager state on controls
        self.workflow_manager.workflow_started.connect(lambda: self.controls_panel.set_state(True, False))
        self.workflow_manager.workflow_finished.connect(lambda *_: self.controls_panel.set_state(False, False))
        self.workflow_manager.workflow_paused.connect(lambda: self.controls_panel.set_state(True, True))
        self.workflow_manager.workflow_resumed.connect(lambda: self.controls_panel.set_state(True, False))
        
        # Connect user input pause/resume signals (different from global pause)
        self.workflow_manager.user_input_paused.connect(self._on_user_input_paused)
        self.workflow_manager.user_input_resumed.connect(self._on_user_input_resumed)

        # Toasts for workflow lifecycle
        self.workflow_manager.workflow_started.connect(lambda: self._show_toast("Running workflow", "Execution started, please wait.", status="running", duration_ms=1200, closable=False))
        self.workflow_manager.workflow_paused.connect(lambda: self._show_toast("Workflow paused", "Execution paused, completing the last running node.", status="paused", duration_ms=0, closable=True))
        self.workflow_manager.workflow_resumed.connect(lambda: self._show_toast("Workflow resumed", "Continuing execution, resuming the last paused node.", status="info", duration_ms=1500, closable=False))
        self.workflow_manager.workflow_finished.connect(self._on_workflow_finished_toast)
        # Per-node error toast
        try:
            self.workflow_manager.node_error_reported.connect(self._on_node_error_toast)
        except Exception:
            pass

        # Wire top menu actions from UI to backend
        self.ui.new_workflow.connect(self._on_new_workflow)
        self.ui.open_workflow.connect(self._on_open_workflow)
        self.ui.save_workflow.connect(self._on_save_workflow)
        self.ui.save_workflow_as.connect(self._on_save_workflow_as)
        self.ui.validate_workflow.connect(self._on_validate_workflow)
        self.ui.run_workflow.connect(self._on_run_workflow)
        # Theme selection
        try:
            self.ui.theme_selected.connect(self._on_theme_selected)
        except Exception:
            pass

        # Edit actions
        self.ui.undo_requested.connect(self.canvas.undo)
        self.ui.redo_requested.connect(self.canvas.redo)
        self.ui.cut_requested.connect(self.canvas.cut_selected)
        self.ui.copy_requested.connect(self.canvas.copy_selected)
        self.ui.paste_requested.connect(self.canvas.paste_from_clipboard)
        self.ui.select_all_requested.connect(self.canvas.select_all)

        # View actions
        self.ui.zoom_in_requested.connect(lambda: self.canvas.zoom_in())
        self.ui.zoom_out_requested.connect(lambda: self.canvas.zoom_out())
        self.ui.zoom_fit_requested.connect(self.canvas.zoom_fit)
        # View -> Toolbox visibility toggle
        self.ui.toolbox_visibility_changed.connect(self._on_toolbox_visibility_changed)

        # Sync menu checked state with dock visibility and close events
        try:
            self.toolbox_dock.visibilityChanged.connect(self._on_toolbox_dock_visibility_changed)
        except Exception:
            pass

        # Properties dock removed; selection signals no longer wired to a side panel

        # Global floating workflow progress bar wiring
        self.workflow_manager.workflow_started.connect(self._on_workflow_started_for_progress)
        self.workflow_manager.node_finished.connect(self._on_node_finished_for_progress)
        self.workflow_manager.workflow_finished.connect(self._on_workflow_finished_for_progress)

        # Expose reload hook for UI menu
        try:
            self.reload_plugins_and_refresh = self._reload_plugins_and_refresh  # type: ignore[attr-defined]
        except Exception:
            pass
        
    def _wire_controls(self):
        """Wire floating controls to workflow actions."""
        self.controls_panel.run_requested.connect(self._on_run_workflow)
        self.controls_panel.stop_requested.connect(self._on_stop_requested)
        self.controls_panel.pause_requested.connect(self._on_pause_requested)
        self.controls_panel.resume_requested.connect(self._on_resume_requested)
        self.controls_panel.validate_requested.connect(self._on_validate_workflow)
        self.controls_panel.clear_requested.connect(self._on_clear_requested)
        
    def _restore_settings(self):
        """Restore application settings."""
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
            
        state = self.settings.value("windowState")
        if state:
            self.restoreState(state)
    
    def closeEvent(self, event):
        """Handle application close event: close all windows and cleanup temp."""
        # Save settings
        try:
            self.settings.setValue("geometry", self.saveGeometry())
            self.settings.setValue("windowState", self.saveState())
        except Exception:
            pass

        # Stop any running tasks/processes
        try:
            self.workflow_manager.cleanup()
        except Exception:
            pass

        # Proactively close any other top-level windows (viewers, dialogs, etc.)
        try:
            app = QApplication.instance()
            if app is not None:
                others = list(app.topLevelWidgets())
                for w in others:
                    if w is not self:
                        try:
                            w.close()
                        except Exception:
                            pass
        except Exception:
            pass

        # Remove the session temp root directory (vera_<hash>)
        try:
            cleanup_session_temp_dir()
        except Exception:
            pass

        event.accept()

    # -------------------
    # Theme management
    # -------------------
    def _on_theme_selected(self, theme_id: str) -> None:
        try:
            self._apply_theme(theme_id)
            self.settings.setValue("ui/theme_id", theme_id or "")
            self.ui.set_theme_checked(theme_id)
        except Exception:
            pass

    def _apply_theme(self, theme_id: str) -> None:
        try:
            app = QApplication.instance()
            if app is None:
                return
            if not theme_id:
                # Clear to system default
                app.setStyleSheet("")
            else:
                qss = load_theme_qss(theme_id)
                if qss is None:
                    qss = ""
                app.setStyleSheet(qss)
            
            # Sub-components style update
            try:
                if hasattr(self, 'toolbox') and hasattr(self.toolbox, 'apply_styles'):
                    self.toolbox.apply_styles(theme_id)
                if hasattr(self, 'controls_panel') and hasattr(self.controls_panel, 'apply_styles'):
                    self.controls_panel.apply_styles(theme_id)
            except Exception:
                pass

            # Optional: adjust canvas background for dark/light themes
            try:
                is_dark = detect_theme_is_dark(theme_id)
                if hasattr(self, "canvas") and self.canvas is not None:
                    from PySide6.QtGui import QColor, QBrush
                    bg = QColor(32, 32, 32) if is_dark else QColor(240, 240, 240)
                    self.canvas.setBackgroundBrush(QBrush(bg))
            except Exception:
                pass
        except Exception:
            pass

    # UI action handlers
    def _on_open_workflow(self, filename: str):
        # Load into manager, then rebuild canvas to reflect file contents
        if not filename:
            return
        if not self.workflow_manager.load_workflow(filename):
            self._show_toast("Open failed", "Could not load workflow file.", status="error", duration_ms=3000, closable=True)
            return
        self._rebuild_canvas_from_manager()
        # Opening a workflow reflects saved state -> not dirty
        try:
            self._is_dirty = False
        except Exception:
            pass
        self._update_window_title()
        self._show_toast("Opened", "Workflow loaded successfully.", status="success", duration_ms=1800, closable=False)
        # Add to recent projects
        try:
            dialog = RecentProjectsDialog()
            dialog.add_recent_project(filename)
        except Exception:
            pass

    def _on_save_workflow(self):
        # Ensure manager is synced with current canvas
        try:
            self.workflow_manager.update_from_canvas(self.canvas)
        except Exception:
            pass
        # If no file yet, trigger Save As UI flow via the UI (user chooses path)
        if not self.workflow_manager.current_workflow_file:
            # Mimic Save As flow: open a dialog via the UI helper
            # Reuse UI handler to prompt user; it will emit save_workflow_as
            try:
                self.ui._on_save_workflow_as()
            except Exception:
                pass
            return
        # Pre-toast
        self._show_toast("Saving workflow", "Please wait…", status="info", duration_ms=1000, closable=False)
        # Otherwise save to current file
        saved = self.workflow_manager.save_workflow(self.workflow_manager.current_workflow_file)
        if saved:
            try:
                self._is_dirty = False
            except Exception:
                pass
            self._update_window_title()
            self._show_toast("Saved", "Workflow saved.", status="success", duration_ms=1600, closable=False)
        else:
            self._show_toast("Save failed", "Could not save workflow.", status="error", duration_ms=3000, closable=True)

    def _on_save_workflow_as(self, filename: str):
        # Sync state from canvas then save to chosen filename
        try:
            self.workflow_manager.update_from_canvas(self.canvas)
        except Exception:
            pass
        # Pre-toast
        self._show_toast("Saving workflow", "Please wait…", status="info", duration_ms=1000, closable=False)
        if self.workflow_manager.save_workflow(filename):
            try:
                self._is_dirty = False
            except Exception:
                pass
            self._update_window_title()
            self._show_toast("Saved", "Workflow saved to new file.", status="success", duration_ms=1600, closable=False)
            # Add to recent projects
            try:
                dialog = RecentProjectsDialog()
                dialog.add_recent_project(filename)
            except Exception:
                pass
        else:
            self._show_toast("Save failed", "Could not save workflow.", status="error", duration_ms=3000, closable=True)

    def _on_validate_workflow(self):
        valid, message = self.workflow_manager.validate_workflow()
        # Tampilkan status sementara sebagai "Validating…" dan jalankan animasi dulu;
        # toast final (valid/invalid) akan ditampilkan setelah animasi selesai
        if valid:
            # Set judul sementara
            self.setWindowTitle("VERA - Validating…")
            # Hubungkan one-shot listener untuk akhir animasi
            def _on_anim_done():
                try:
                    self.workflow_manager.validation_animation_finished.disconnect(_on_anim_done)
                except Exception:
                    pass
                # Update judul dan toast akhir
                self.setWindowTitle("VERA - Valid")
                try:
                    if self._validate_title_revert_timer is not None:
                        if self._validate_title_revert_timer.isActive():
                            self._validate_title_revert_timer.stop()
                        self._validate_title_revert_timer.start(2000)
                except Exception:
                    pass
                self._show_toast("Workflow valid", "Ready to run.", status="success", duration_ms=2000, closable=False)
            try:
                self.workflow_manager.validation_animation_finished.connect(_on_anim_done)
            except Exception:
                pass
            try:
                self.workflow_manager.play_validation_animation()
            except Exception:
                # Jika animasi gagal, panggil handler manual
                _on_anim_done()
        else:
            # Invalid langsung tampilkan toast dan judul karena tidak ada animasi urutan
            title = f"VERA - Invalid: {message}"
            self.setWindowTitle(title)
            try:
                if self._validate_title_revert_timer is not None:
                    if self._validate_title_revert_timer.isActive():
                        self._validate_title_revert_timer.stop()
                    self._validate_title_revert_timer.start(2000)
            except Exception:
                pass
            self._show_toast("Workflow invalid", message, status="error", duration_ms=4000, closable=True)

    def _on_run_workflow(self):
        self.workflow_manager.execute_workflow()

    # ---- Floating progress bar handlers ----
    def _on_workflow_started_for_progress(self) -> None:
        try:
            # Total nodes on canvas per requirement
            self._run_total_nodes = len(getattr(self.canvas, 'nodes', []) or [])
        except Exception:
            self._run_total_nodes = 0
        self._run_executed_nodes = 0
        try:
            self.controls_panel.show_workflow_progress(self._run_total_nodes, self._run_executed_nodes)
        except Exception:
            pass

    def _on_node_finished_for_progress(self, node_id: str, success: bool, message: str) -> None:
        try:
            self._run_executed_nodes += 1
            self.controls_panel.update_workflow_progress(self._run_executed_nodes, self._run_total_nodes)
        except Exception:
            pass

    def _on_workflow_finished_for_progress(self, success: bool, message: str) -> None:
        try:
            self.controls_panel.hide_workflow_progress()
        except Exception:
            pass

    def _on_workflow_finished_toast(self, success: bool, message: str) -> None:
        if success:
            self._show_toast("Workflow completed", message or "Workflow completed successfully.", status="success", duration_ms=2500, closable=False)
        else:
            # Differentiate stopped vs error by message text
            msg = str(message or "")
            if "stopped" in msg.lower():
                self._show_toast("Workflow stopped", msg, status="warning", duration_ms=2500, closable=False)
            else:
                self._show_toast("Workflow failed", msg, status="error", duration_ms=4000, closable=True)

    def _reload_plugins_and_refresh(self) -> None:
        """Reload plugin registry and refresh UI components (toolbox + menu)."""
        try:
            from nodes import node_factory as _nf
            reload_plugins_into_factory(_nf)
        except Exception:
            pass
        # Recreate toolbox to force full repopulation
        try:
            dock = self.toolbox_dock
            self.toolbox = NodeToolbox()
            dock.setWidget(self.toolbox)
            self.toolbox.node_requested.connect(self.canvas.add_node)
        except Exception:
            pass

    def _on_node_error_toast(self, node_id: str, message: str) -> None:
        title = self._node_title_for(node_id)
        msg = str(message or "")
        self._show_toast("Node error", f"{title}: {msg}", status="error", duration_ms=5000, closable=True)
    
    def _on_user_input_paused(self, node_id: str, message: str) -> None:
        """Handle user input pause signal - different from global workflow pause."""
        try:
            title = self._node_title_for(node_id)
            self._show_toast("User input required", f"{title}: {message}", 
                           status="paused", duration_ms=0, closable=True)
            # Update floating controls to disable run button
            self.controls_panel.set_user_input_state(True)
        except Exception:
            pass
    
    def _on_user_input_resumed(self, node_id: str) -> None:
        """Handle user input resume signal."""
        try:
            # Clear any persistent "User input required" toast
            try:
                if getattr(self, "toast_overlay", None) is not None:
                    self.toast_overlay.clear_all()
            except Exception:
                pass
            title = self._node_title_for(node_id)
            self._show_toast("User input completed", f"{title}: Input received, continuing...", 
                           status="info", duration_ms=2000, closable=False)
            # Update floating controls to enable run button
            self.controls_panel.set_user_input_state(False)
        except Exception:
            pass

    def _on_partial_rerun_requested(self, node_obj):
        """Start partial execution from the requested node downstream only."""
        try:
            # Sync current graph
            self.workflow_manager.update_from_canvas(self.canvas)
            # Figure out the manager node id for this live node
            node_id = None
            for nid, nd in self.workflow_manager._node_live_map.items():
                if nd is node_obj:
                    node_id = nid
                    break
            if not node_id:
                return
            # Kick off partial execution
            self.workflow_manager.execute_from_node(node_id)
        except Exception:
            pass

    # -------- High-level helpers --------
    def _rebuild_canvas_from_manager(self) -> None:
        """Rebuild the visual canvas from the manager's serialized workflow state."""
        self._is_rebuilding = True
        try:
            # Clear canvas fully by creating a fresh instance to also reset history
            central_widget = self.centralWidget()
            layout: QHBoxLayout = central_widget.layout()  # type: ignore[assignment]
            old_canvas = getattr(self, 'canvas', None)
            if old_canvas is not None:
                layout.removeWidget(old_canvas)
                old_canvas.setParent(None)
                try:
                    old_canvas.deleteLater()
                except Exception:
                    pass
            self.canvas = WorkflowCanvas()
            layout.insertWidget(0, self.canvas, 1)

            # Re-bind toolbox hooks (no properties panel anymore)
            try:
                self.toolbox.node_requested.disconnect()
            except Exception:
                pass
            self.toolbox.node_requested.connect(self.canvas.add_node)
            self.canvas.workflow_changed.connect(self.workflow_manager.update_workflow)
            self.canvas.workflow_changed.connect(lambda: self.workflow_manager.update_from_canvas(self.canvas))
            # Mark window as dirty on any user-editing change (for the new canvas instance)
            self.canvas.workflow_changed.connect(self._on_canvas_modified)
            try:
                self.canvas.partial_rerun_requested.connect(self._on_partial_rerun_requested)
            except Exception:
                pass
            self.workflow_manager.bind_canvas(self.canvas)
            self.canvas.attach_overlay_widget(self.controls_panel)
            # Ensure clear action targets the new canvas instance
            try:
                # Disconnect all previous connections for safety (no-arg disconnect supported)
                self.controls_panel.clear_requested.disconnect()
            except Exception:
                pass
            self.controls_panel.clear_requested.connect(self.canvas.clear_canvas)

            # Reconnect menu actions to the new canvas instance
            try:
                self.ui.undo_requested.disconnect()
            except Exception:
                pass
            try:
                self.ui.redo_requested.disconnect()
            except Exception:
                pass
            try:
                self.ui.cut_requested.disconnect()
            except Exception:
                pass
            try:
                self.ui.copy_requested.disconnect()
            except Exception:
                pass
            try:
                self.ui.paste_requested.disconnect()
            except Exception:
                pass
            try:
                self.ui.zoom_in_requested.disconnect()
            except Exception:
                pass
            try:
                self.ui.zoom_out_requested.disconnect()
            except Exception:
                pass
            try:
                self.ui.zoom_fit_requested.disconnect()
            except Exception:
                pass
            try:
                self.ui.select_all_requested.disconnect()
            except Exception:
                pass

            self.ui.undo_requested.connect(self.canvas.undo)
            self.ui.redo_requested.connect(self.canvas.redo)
            self.ui.cut_requested.connect(self.canvas.cut_selected)
            self.ui.copy_requested.connect(self.canvas.copy_selected)
            self.ui.paste_requested.connect(self.canvas.paste_from_clipboard)
            self.ui.select_all_requested.connect(self.canvas.select_all)
            self.ui.zoom_in_requested.connect(lambda: self.canvas.zoom_in())
            self.ui.zoom_out_requested.connect(lambda: self.canvas.zoom_out())
            self.ui.zoom_fit_requested.connect(self.canvas.zoom_fit)

            # Ensure View->Toolbox connections remain
            try:
                self.ui.toolbox_visibility_changed.disconnect(self._on_toolbox_visibility_changed)
            except Exception:
                pass
            self.ui.toolbox_visibility_changed.connect(self._on_toolbox_visibility_changed)

            # Populate nodes and connections
            id_to_node = {}
            from nodes import node_factory
            for node_data in self.workflow_manager.nodes.values():
                node = node_factory.create_node(node_data.get('type', 'unknown'))
                if node is None:
                    continue
                pos = node_data.get('position', {"x": 0.0, "y": 0.0})
                node.setPos(pos.get('x', 0.0), pos.get('y', 0.0))
                # Restore size if present
                try:
                    sz = node_data.get('size')
                    if isinstance(sz, dict) and hasattr(node, 'set_node_size'):
                        w = float(sz.get('w', getattr(node, 'width', 200)))
                        h = float(sz.get('h', getattr(node, 'height', 100)))
                        node.set_node_size(w, h)
                except Exception:
                    pass
                # Restore saved custom title
                try:
                    if 'title' in node_data:
                        node.title = str(node_data.get('title', node.title))
                except Exception:
                    pass
                try:
                    props = node_data.get('properties', {}) or {}
                    for k, v in props.items():
                        node.set_property(k, v)
                except Exception:
                    pass
                self.canvas.scene.addItem(node)
                self.canvas.nodes.append(node)
                node.connection_requested.connect(self.canvas._on_connection_requested)
                node.position_changed.connect(self.canvas._on_node_moved)
                id_to_node[node_data['id']] = node

            for conn in self.workflow_manager.connections.values():
                try:
                    out_node = id_to_node.get(conn.get('source_node'))
                    in_node = id_to_node.get(conn.get('target_node'))
                    if out_node is None or in_node is None:
                        continue
                    self.canvas.add_connection(out_node, conn.get('source_port'), in_node, conn.get('target_port'))
                except Exception:
                    pass

            # Fit view to content
            self.canvas.zoom_fit()
        except Exception:
            pass
        finally:
            # Completed programmatic rebuild; consider this clean state
            try:
                self._is_rebuilding = False
                self._is_dirty = False
            except Exception:
                pass

    def _on_new_workflow(self) -> None:
        """Create a brand new empty canvas and reset workflow state."""
        try:
            self.workflow_manager.clear_workflow()
        except Exception:
            pass
        # Rebuild a fresh canvas
        self._rebuild_canvas_from_manager()
        try:
            self._is_dirty = False
        except Exception:
            pass
        self._update_window_title()
        self._show_toast("New workflow", "A new empty workflow has been created.", status="info", duration_ms=1600, closable=False)

    def _on_stop_requested(self) -> None:
        # Clear any persistent paused or previous toasts
        try:
            if getattr(self, "toast_overlay", None) is not None:
                self.toast_overlay.clear_all()
        except Exception:
            pass
        self._show_toast("Stopping workflow", "Attempting to stop…", status="warning", duration_ms=1500, closable=False)
        try:
            self.workflow_manager.stop_workflow()
        except Exception:
            pass

    def _on_pause_requested(self) -> None:
        try:
            self.workflow_manager.pause_workflow()
        except Exception:
            pass

    def _on_resume_requested(self) -> None:
        # Clear any persistent paused toast
        try:
            if getattr(self, "toast_overlay", None) is not None:
                self.toast_overlay.clear_all()
        except Exception:
            pass
        try:
            self.workflow_manager.resume_workflow()
        except Exception:
            pass

    def _on_clear_requested(self) -> None:
        try:
            # Stop any running workflow and cleanup resources before clearing
            if hasattr(self, 'workflow_manager') and self.workflow_manager:
                self.workflow_manager.cleanup()

            self.canvas.clear_canvas()
        except Exception:
            pass

    def _on_canvas_modified(self) -> None:
        """Mark the workflow as modified and update title unless rebuilding programmatically."""
        try:
            if getattr(self, '_is_rebuilding', False):
                return
            self._is_dirty = True
            self._update_window_title()
        except Exception:
            pass

    # ---- View -> Toolbox handlers ----
    def _on_toolbox_visibility_changed(self, should_show: bool) -> None:
        try:
            if bool(should_show):
                # Ensure the toolbox is docked and visible
                try:
                    self.toolbox_dock.setFloating(False)
                except Exception:
                    pass
                try:
                    area = self.dockWidgetArea(self.toolbox_dock)
                except Exception:
                    area = Qt.NoDockWidgetArea
                if area == Qt.NoDockWidgetArea:
                    self.addDockWidget(Qt.RightDockWidgetArea, self.toolbox_dock)
                self.toolbox_dock.show()
            else:
                self.toolbox_dock.hide()
        except Exception:
            pass

    def _on_toolbox_dock_visibility_changed(self, visible: bool) -> None:
        # Reflect dock visibility back to menu action (e.g., when user closes the dock)
        try:
            self.ui.set_toolbox_action_checked(bool(visible))
        except Exception:
            pass

    def _update_window_title(self) -> None:
        """Update the window title to reflect current workflow file name and dirty flag.
        - Shows file base name or 'untitled workflow'
        - Prefixes '*' while there are unsaved changes
        """
        try:
            file_path = getattr(self.workflow_manager, 'current_workflow_file', None)
            dirty = getattr(self, '_is_dirty', False)
            import os
            if not file_path:
                name = "untitled workflow"
            else:
                try:
                    name = os.path.basename(file_path)
                except Exception:
                    name = str(file_path)
            if dirty:
                name = f"*{name}"
            self.setWindowTitle(f"VERA - {name}")
        except Exception:
            # Fallback: do nothing on error
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            if getattr(self, "toast_overlay", None) is not None:
                self.toast_overlay._reflow()
        except Exception:
            pass
    
    def _show_recent_projects_dialog(self):
        """Show the recent projects dialog on startup"""
        try:
            dialog = RecentProjectsDialog(self)
            dialog.project_selected.connect(self._on_open_workflow)
            dialog.new_project_requested.connect(self._on_new_workflow)
            
            # Center dialog on main window
            if self.isVisible():
                dialog.move(
                    self.x() + (self.width() - dialog.width()) // 2,
                    self.y() + (self.height() - dialog.height()) // 2
                )
            
            # Show dialog (non-blocking)
            dialog.show()
        except Exception as e:
            print(f"Error showing recent projects dialog: {e}")
    

