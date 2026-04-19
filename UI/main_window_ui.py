"""
Main window UI for VERA application.
This file contains the UI layout and styling for the main window.
"""

from PySide6.QtWidgets import (QMenuBar, QToolBar, QStatusBar,
                               QFileDialog, QMessageBox)
from PySide6.QtCore import Qt, QObject, Signal, QUrl
from PySide6.QtGui import QKeySequence, QAction, QActionGroup, QIcon, QDesktopServices


class MainWindowUI(QObject):
    """Main window UI setup class."""
    
    # Signals
    new_workflow = Signal()
    open_workflow = Signal(str)
    save_workflow = Signal()
    save_workflow_as = Signal(str)
    validate_workflow = Signal()
    run_workflow = Signal()
    # Edit/View signals
    undo_requested = Signal()
    redo_requested = Signal()
    cut_requested = Signal()
    copy_requested = Signal()
    paste_requested = Signal()
    select_all_requested = Signal()
    zoom_in_requested = Signal()
    zoom_out_requested = Signal()
    zoom_fit_requested = Signal()
    # View -> Toolbox
    toolbox_visibility_changed = Signal(bool)
    # Theme selection
    theme_selected = Signal(str)
    
    def __init__(self):
        super().__init__()
        
    def setup_ui(self, main_window):
        """Setup the main window UI components."""
        self.main_window = main_window
        
        # Setup menu bar
        self._setup_menu_bar()
        
        # Setup status bar
        self._setup_status_bar()
        
    def _setup_menu_bar(self):
        """Setup the menu bar."""
        menubar = self.main_window.menuBar()
        
        # File Menu
        file_menu = menubar.addMenu("File")
        
        # New Workflow
        new_action = QAction("New Workflow", self.main_window)
        new_action.setShortcut(QKeySequence.New)
        new_action.setStatusTip("Create a new workflow")
        new_action.triggered.connect(self._on_new_workflow)
        file_menu.addAction(new_action)
        
        # Open Workflow
        open_action = QAction("Open Workflow", self.main_window)
        open_action.setShortcut(QKeySequence.Open)
        open_action.setStatusTip("Open an existing workflow")
        open_action.triggered.connect(self._on_open_workflow)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        # Save Workflow
        save_action = QAction("Save Workflow", self.main_window)
        save_action.setShortcut(QKeySequence.Save)
        save_action.setStatusTip("Save the current workflow")
        save_action.triggered.connect(self._on_save_workflow)
        file_menu.addAction(save_action)
        
        # Save As
        save_as_action = QAction("Save Workflow As...", self.main_window)
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.setStatusTip("Save the workflow with a new name")
        save_as_action.triggered.connect(self._on_save_workflow_as)
        file_menu.addAction(save_as_action)
        
        file_menu.addSeparator()
        
        # Exit
        exit_action = QAction("Exit", self.main_window)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.setStatusTip("Exit the application")
        exit_action.triggered.connect(self.main_window.close)
        file_menu.addAction(exit_action)
        
        # Edit Menu
        edit_menu = menubar.addMenu("Edit")
        
        # Undo
        undo_action = QAction("Undo", self.main_window)
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.setStatusTip("Undo the last action")
        undo_action.triggered.connect(self._on_undo)
        edit_menu.addAction(undo_action)
        
        # Redo
        redo_action = QAction("Redo", self.main_window)
        redo_action.setShortcut(QKeySequence.Redo)
        redo_action.setStatusTip("Redo the last undone action")
        redo_action.triggered.connect(self._on_redo)
        edit_menu.addAction(redo_action)
        
        edit_menu.addSeparator()
        
        # Cut, Copy, Paste
        cut_action = QAction("Cut", self.main_window)
        cut_action.setShortcut(QKeySequence.Cut)
        cut_action.setStatusTip("Cut selected items")
        cut_action.triggered.connect(self._on_cut)
        edit_menu.addAction(cut_action)
        
        copy_action = QAction("Copy", self.main_window)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.setStatusTip("Copy selected items")
        copy_action.triggered.connect(self._on_copy)
        edit_menu.addAction(copy_action)
        
        paste_action = QAction("Paste", self.main_window)
        paste_action.setShortcut(QKeySequence.Paste)
        paste_action.setStatusTip("Paste items from clipboard")
        paste_action.triggered.connect(self._on_paste)
        edit_menu.addAction(paste_action)

        # Select All (nodes on canvas)
        select_all_action = QAction("Select All", self.main_window)
        select_all_action.setShortcut(QKeySequence.SelectAll)
        select_all_action.setStatusTip("Select all nodes on the canvas")
        select_all_action.triggered.connect(self._on_select_all)
        edit_menu.addAction(select_all_action)
        
        # View Menu
        view_menu = menubar.addMenu("View")
        
        # Zoom
        zoom_in_action = QAction("Zoom In", self.main_window)
        zoom_in_action.setShortcut(QKeySequence.ZoomIn)
        zoom_in_action.setStatusTip("Zoom in the canvas")
        zoom_in_action.triggered.connect(self._on_zoom_in)
        view_menu.addAction(zoom_in_action)
        
        zoom_out_action = QAction("Zoom Out", self.main_window)
        zoom_out_action.setShortcut(QKeySequence.ZoomOut)
        zoom_out_action.setStatusTip("Zoom out the canvas")
        zoom_out_action.triggered.connect(self._on_zoom_out)
        view_menu.addAction(zoom_out_action)
        
        zoom_fit_action = QAction("Fit to Window", self.main_window)
        zoom_fit_action.setShortcut("Ctrl+F")
        zoom_fit_action.setStatusTip("Fit workflow to window")
        zoom_fit_action.triggered.connect(self._on_zoom_fit)
        view_menu.addAction(zoom_fit_action)

        # Separator and Toolbox toggle
        view_menu.addSeparator()
        self._toolbox_action = QAction("Hide/Show Toolbox", self.main_window)
        self._toolbox_action.setCheckable(True)
        self._toolbox_action.setChecked(True)
        self._toolbox_action.setStatusTip("Show or hide the docked toolbox")
        self._toolbox_action.toggled.connect(self._on_toolbox_toggle)
        view_menu.addAction(self._toolbox_action)
        
        # Tools Menu
        tools_menu = menubar.addMenu("Tools")
        
        # Validate Workflow
        validate_action = QAction("Validate Workflow", self.main_window)
        validate_action.setShortcut("Alt+V")
        validate_action.setStatusTip("Check workflow for errors")
        validate_action.triggered.connect(self._on_validate_workflow)
        tools_menu.addAction(validate_action)
        
        # Run Workflow
        run_action = QAction("Run Workflow", self.main_window)
        run_action.setShortcut("F5")
        run_action.setStatusTip("Execute the current workflow")
        run_action.triggered.connect(self._on_run_workflow)
        tools_menu.addAction(run_action)
        
        # Theme Menu
        theme_menu = menubar.addMenu("Theme")
        self._theme_menu = theme_menu
        self._theme_actions = {}
        self._theme_action_group = QActionGroup(self.main_window)
        self._theme_action_group.setExclusive(True)
        self._populate_theme_menu()
        
        # Help Menu
        help_menu = menubar.addMenu("Help")
        
        # Documentation
        docs_action = QAction("Documentation", self.main_window)
        docs_action.setShortcut("F1")
        docs_action.setStatusTip("Open online documentation")
        docs_action.triggered.connect(self._on_docs)
        help_menu.addAction(docs_action)
        
        # About
        about_action = QAction("About VERA", self.main_window)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)


        # Plugins Menu
        plugins_menu = menubar.addMenu("Plugins")
        self._plugins_menu = plugins_menu

        add_plugin_action = QAction("Add Plugin…", self.main_window)
        add_plugin_action.setStatusTip("Install a plugin from .zip/.bsx or folder")
        add_plugin_action.triggered.connect(self._on_add_plugin)
        plugins_menu.addAction(add_plugin_action)

        open_folder_action = QAction("Open Plugins Folder", self.main_window)
        open_folder_action.setStatusTip("Open the user plugins directory")
        open_folder_action.triggered.connect(self._on_open_plugins_folder)
        plugins_menu.addAction(open_folder_action)

        reload_plugins_action = QAction("Reload Plugins", self.main_window)
        reload_plugins_action.setStatusTip("Rescan and reload plugins")
        reload_plugins_action.triggered.connect(self._on_reload_plugins)
        plugins_menu.addAction(reload_plugins_action)

        plugins_menu.addSeparator()
        # Placeholder for dynamic list of installed plugins
        self._populate_plugins_menu()
        
    def _setup_status_bar(self):
        """Setup the status bar."""
        statusbar = self.main_window.statusBar()
        statusbar.showMessage("Ready")
        
    # Slot methods
    def _on_new_workflow(self):
        """Handle new workflow action."""
        self.new_workflow.emit()
        
    def _on_open_workflow(self):
        """Handle open workflow action."""
        filename, _ = QFileDialog.getOpenFileName(
            self.main_window,
            "Open Workflow",
            "",
            "VERA Workflows (*.vsw);;All Files (*)"
        )
        if filename:
            self.open_workflow.emit(filename)
            
    def _on_save_workflow(self):
        """Handle save workflow action."""
        self.save_workflow.emit()
        
    def _on_save_workflow_as(self):
        """Handle save workflow as action."""
        filename, _ = QFileDialog.getSaveFileName(
            self.main_window,
            "Save Workflow As",
            "",
            "VERA Workflows (*.vsw);;All Files (*)"
        )
        if filename:
            self.save_workflow_as.emit(filename)

    def _on_validate_workflow(self):
        """Handle validate workflow action."""
        self.validate_workflow.emit()

    def _on_run_workflow(self):
        """Handle run workflow action."""
        self.run_workflow.emit()
            
    def _on_about(self):
        """Handle about action."""
        try:
            from UI.about_dialog import AboutDialog
            about_dialog = AboutDialog(self.main_window)
            about_dialog.show_about_dialog()
        except Exception as e:
            print(f"Error opening about dialog: {str(e)}")
            # Fallback to simple message box
            from PySide6.QtWidgets import QMessageBox
            from core.app_control import APP_INFO
            QMessageBox.about(self.main_window, "About VERA", 
                            f"VERA\nVersion {APP_INFO.get('version', '1.0.0')}\n\n"
                            f"Virtual Execution and Reaction Architecture")

    # Edit/View handlers emit signals for the application to wire to canvas
    def _on_undo(self):
        self.undo_requested.emit()

    def _on_redo(self):
        self.redo_requested.emit()

    def _on_cut(self):
        self.cut_requested.emit()

    def _on_copy(self):
        self.copy_requested.emit()

    def _on_paste(self):
        self.paste_requested.emit()

    def _on_select_all(self):
        self.select_all_requested.emit()

    def _on_zoom_in(self):
        self.zoom_in_requested.emit()

    def _on_zoom_out(self):
        self.zoom_out_requested.emit()

    def _on_zoom_fit(self):
        self.zoom_fit_requested.emit()

    def _on_docs(self):
        # Open external documentation URL
        QDesktopServices.openUrl(QUrl("https://vera-desktop-app.netlify.app/docs"))

    def _on_toolbox_toggle(self, checked: bool):
        """Emit signal when the toolbox menu item is toggled."""
        self.toolbox_visibility_changed.emit(bool(checked))

    # -----------------------
    # Plugins menu helpers
    # -----------------------
    def _populate_plugins_menu(self) -> None:
        try:
            menu = getattr(self, "_plugins_menu", None)
            if menu is None:
                return
            # Remove old dynamic items (keep first 4 static actions and separators)
            # Static actions order: Add..., Open Folder, Reload, Separator
            while menu.actions()[4:]:
                act = menu.actions()[-1]
                menu.removeAction(act)
            # Load installed plugins for display
            entries = []
            try:
                from backend.plugin_manager import get_installed_plugins_for_menu
                entries = get_installed_plugins_for_menu()
            except Exception:
                entries = []
            if not entries:
                noact = QAction("No plugins installed", self.main_window)
                noact.setEnabled(False)
                menu.addAction(noact)
                return
            for display, pid, ok in entries:
                act = QAction(display, self.main_window)
                act.setEnabled(True)
                # Show a mark for loaded state
                if ok:
                    act.setIcon(QIcon.fromTheme("emblem-ok"))
                else:
                    act.setIcon(QIcon())
                # No direct action on click for now
                menu.addAction(act)
        except Exception:
            pass

    def _on_add_plugin(self) -> None:
        try:
            # Offer file or folder selection
            from PySide6.QtWidgets import QFileDialog
            path, sel = QFileDialog.getOpenFileName(self.main_window, "Select Plugin Archive (.zip/.bsx) or Python file", "", "Plugin packages (*.zip *.bsx);;All files (*.*)")
            success = False
            message = ""
            if path:
                try:
                    from backend.plugin_manager import install_plugin_from_zip
                    success, message = install_plugin_from_zip(path)
                except Exception as e:
                    success, message = False, str(e)
            else:
                # Try select folder fallback
                folder = QFileDialog.getExistingDirectory(self.main_window, "Select Plugin Folder")
                if folder:
                    try:
                        from backend.plugin_manager import install_plugin_from_folder
                        success, message = install_plugin_from_folder(folder)
                    except Exception as e:
                        success, message = False, str(e)
            if success:
                QMessageBox.information(self.main_window, "Plugin Installed", message or "Plugin installed successfully.")
                # Ask main app (owner) to reload plugins and refresh toolbox
                try:
                    getattr(self.main_window, "reload_plugins_and_refresh", lambda: None)()
                except Exception:
                    pass
                self._populate_plugins_menu()
            else:
                QMessageBox.warning(self.main_window, "Plugin Install Failed", message or "Failed to install plugin.")
        except Exception as e:
            try:
                QMessageBox.warning(self.main_window, "Plugin Install Failed", str(e))
            except Exception:
                pass

    def _on_reload_plugins(self) -> None:
        try:
            getattr(self.main_window, "reload_plugins_and_refresh", lambda: None)()
        except Exception:
            pass
        self._populate_plugins_menu()

    def _on_open_plugins_folder(self) -> None:
        try:
            from backend.plugin_manager import open_plugins_folder_in_explorer
            open_plugins_folder_in_explorer()
        except Exception:
            pass

    # External API for syncing action state with dock visibility
    def set_toolbox_action_checked(self, checked: bool) -> None:
        try:
            act = getattr(self, "_toolbox_action", None)
            if act is None:
                return
            # Prevent feedback loops
            was_blocked = act.blockSignals(True)
            act.setChecked(bool(checked))
            act.blockSignals(was_blocked)
        except Exception:
            pass

    # -----------------------
    # Theme menu helpers
    # -----------------------
    def _populate_theme_menu(self) -> None:
        try:
            menu = getattr(self, "_theme_menu", None)
            if menu is None:
                return
            menu.clear()
            self._theme_actions = {}
            # Optional default action
            default_action = QAction("System Default", self.main_window)
            default_action.setCheckable(True)
            default_action.triggered.connect(lambda: self.theme_selected.emit(""))
            menu.addAction(default_action)
            self._theme_action_group.addAction(default_action)
            menu.addSeparator()
            # Load available themes
            themes = []
            try:
                from backend.resource_access import list_themes
                themes = list_themes()
            except Exception:
                themes = []
            if not themes:
                noact = QAction("No themes found", self.main_window)
                noact.setEnabled(False)
                menu.addAction(noact)
            else:
                for theme_id, display_name in themes:
                    act = QAction(display_name, self.main_window)
                    act.setCheckable(True)
                    act.triggered.connect(lambda checked=False, tid=theme_id: self.theme_selected.emit(tid))
                    menu.addAction(act)
                    self._theme_action_group.addAction(act)
                    self._theme_actions[theme_id] = act
            menu.addSeparator()
            reload_action = QAction("Reload Themes", self.main_window)
            reload_action.setStatusTip("Rescan and reload available themes")
            reload_action.triggered.connect(self._populate_theme_menu)
            menu.addAction(reload_action)
        except Exception:
            pass

    def set_theme_checked(self, theme_id: str) -> None:
        """Check the action corresponding to the given theme id (empty for default)."""
        try:
            # Ensure menu exists and actions populated
            if getattr(self, "_theme_menu", None) is None:
                return
            if not getattr(self, "_theme_actions", None):
                self._populate_theme_menu()
            if theme_id and theme_id in self._theme_actions:
                act = self._theme_actions.get(theme_id)
                if act is not None:
                    was = act.blockSignals(True)
                    act.setChecked(True)
                    act.blockSignals(was)
            else:
                # System default
                try:
                    for act in self._theme_action_group.actions():
                        if act.text() == "System Default":
                            was = act.blockSignals(True)
                            act.setChecked(True)
                            act.blockSignals(was)
                            break
                except Exception:
                    pass
        except Exception:
            pass
