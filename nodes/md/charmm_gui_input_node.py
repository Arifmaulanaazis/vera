"""CharmmGUIInputNode implementation."""

from .common import *  # noqa: F401,F403

class CharmmGUIInputNode(BaseNode):
    """CHARMM-GUI Input node for MD preparation.
    Verifies and normalizes CHARMM-GUI output files for GROMACS MD simulation.
    """

    def __init__(self):
        super().__init__("charmm_gui_input", "CHARMM-GUI Input")
        self.logger = get_logger(__name__)
        self.add_input_port("folder", "string")
        self.add_output_port("gro_file", "file")
        self.add_output_port("top_file", "file")
        self.add_output_port("mdp_min", "file")
        self.add_output_port("mdp_eq", "file")
        self.add_output_port("mdp_prod", "file")
        self.add_output_port("index_file", "file")
        self.add_output_port("folder_path", "string")

        # Properties for file verification
        self.set_property("needs_confirmation", False)
        self.set_property("auto_detect", True)
        self.set_property("user_checked_keys", [])
        # Persist manual picks across re-runs
        self.set_property("user_selected_files", {})

        # Inline UI: scroll list of files; floating checklist panel on the right
        try:
            from PySide6.QtWidgets import (
                QScrollArea,
                QWidget,
                QVBoxLayout,
                QGridLayout,
                QLabel,
                QGraphicsProxyWidget,
                QFrame,
                QCheckBox,
                QPushButton,
            )

            self.width = 420
            self.height = 240
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)
            try:
                self.set_content_margins(0, 32, 0, 0)
            except Exception:
                pass
            
            # Node body: scroll area with file presence statuses
            body_container = QWidget()
            body_layout = QVBoxLayout()
            body_layout.setContentsMargins(6, 4, 6, 6)
            body_layout.setSpacing(4)

            self._scroll = QScrollArea()
            self._scroll.setWidgetResizable(True)
            self._scroll_widget = QWidget()
            self._files_layout = QGridLayout()
            self._files_layout.setContentsMargins(4, 4, 4, 4)
            self._files_layout.setSpacing(4)
            self._scroll_widget.setLayout(self._files_layout)
            self._scroll.setWidget(self._scroll_widget)
            # Keep a reference to body layout for further updates
            self._body_layout = body_layout
            body_layout.addWidget(self._scroll)
            # Finish button under the scroll (disabled until all resolved)
            self._btn_finish = QPushButton("Finish")
            try:
                self._btn_finish.setEnabled(False)
            except Exception:
                pass
            def _on_finish_clicked():
                try:
                    # User confirms all selections; resume workflow
                    self.set_property("needs_confirmation", False)
                    try:
                        sc = self.scene()
                        view = None
                        if sc is not None and hasattr(sc, 'views'):
                            vs = sc.views()
                            view = vs[0] if isinstance(vs, (list, tuple)) and vs else None
                        if view is not None:
                            win = view.window()
                            if hasattr(win, 'workflow_manager'):
                                win.workflow_manager.resume_user_input(self._node_id)
                    except Exception:
                        pass
                    # Trigger rerun
                    try:
                        if hasattr(self, 'rerun_requested'):
                            self.rerun_requested.emit(self)
                    except Exception:
                        pass
                except Exception:
                    pass
            try:
                self._btn_finish.clicked.connect(_on_finish_clicked)
            except Exception:
                pass
            try:
                # Ensure Finish button is visible inside the node body and persists
                self._body_layout.addWidget(self._btn_finish)
                self._btn_finish.setVisible(True)
            except Exception:
                pass
            body_container.setLayout(body_layout)
            
            content_layout = self.content_layout
            if content_layout is not None:
                content_layout.addWidget(body_container, 0, 0)
            self._update_port_positions()

            # Floating checklist panel (hidden by default)
            self._panel_proxy = None
            self._panel_widget = None
            self._panel_ok = None
            self._chk_map = {}
            self._panel_list_layout = None
            self._panel_file_checks = {}
            self._panel_current_key = None
            self._file_keys = [
                ("gro", "Structure (.gro)"),
                ("top", "Topology (.top)"),
                ("mdp_min", "MDP Minimization (.mdp)"),
                ("mdp_eq", "MDP Equilibration (.mdp)"),
                ("mdp_prod", "MDP Production (.mdp)"),
                ("index", "Index (.ndx)"),
            ]

            self._ensure_panel()
        except Exception:
            self._scroll = None
            self._files_layout = None
            self._panel_proxy = None
            self._panel_widget = None
            self._panel_ok = None
            self._chk_map = {}

    def _detect_files(self, folder_path: str) -> Dict[str, Optional[str]]:
        """Auto-detect CHARMM-GUI output files in the folder."""
        folder = Path(folder_path)
        files = {
            "gro": None,
            "top": None,
            "mdp_min": None,
            "mdp_eq": None,
            "mdp_prod": None,
            "index": None,
        }
        
        # Common CHARMM-GUI file patterns (strict: exact filenames only)
        patterns = {
            "gro": ["step3_input.gro"],
            "top": ["topol.top"],
            "mdp_min": ["step4.0_minimization.mdp"],
            "mdp_eq": ["step4.1_equilibration.mdp"],
            "mdp_prod": ["step5_production.mdp"],
            "index": ["index.ndx"],
        }
        
        for key, pattern_list in patterns.items():
            for pattern in pattern_list:
                # First, try in the provided folder root
                file_path = folder / pattern
                if file_path.exists():
                    files[key] = str(file_path)
                    break
                # Then, search recursively in subfolders (CHARMM-GUI often nests under gromacs/)
                try:
                    match = next(folder.rglob(pattern), None)
                except Exception:
                    match = None
                if match is not None and match.exists():
                    files[key] = str(match)
                    break
        
        return files

    def _update_status(self, status_text: str):
        """Deprecated in this node: status shown via file list."""
        return

    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        # Hide default painted labels entirely
        return []

    def _update_file_list_ui(self, detected: Dict[str, Optional[str]]) -> None:
        layout = getattr(self, "_files_layout", None)
        if layout is None:
            return
        try:
            from PySide6.QtWidgets import QLabel, QPushButton
        except Exception:
            return
        # Clear existing widgets
        try:
            while layout.count():
                item = layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()
        except Exception:
            pass
        # Add rows for each file
        row = 0
        for key, display in self._file_keys:
            present = bool(detected.get(key))
            status = "✓" if present else "✗"
            lbl_status = QLabel(status)
            btn_row = QPushButton(display)
            try:
                btn_row.setFlat(True)
            except Exception:
                pass
            def _make_on_click(k: str):
                def _on_click():
                    try:
                        folder_prop = self.get_property("last_input_folder") or self.get_property("folder")
                    except Exception:
                        folder_prop = None
                    if folder_prop:
                        try:
                            self._populate_panel_for_key(str(folder_prop), k)
                            self._set_panel_visible(True)
                        except Exception:
                            pass
                return _on_click
            try:
                btn_row.clicked.connect(_make_on_click(key))
            except Exception:
                pass
            try:
                # Green for present, red for missing
                if present:
                    lbl_status.setStyleSheet("color: #7bd88f; font-weight: bold;")
                else:
                    lbl_status.setStyleSheet("color: #e16a6a; font-weight: bold;")
            except Exception:
                pass
            layout.addWidget(lbl_status, row, 0)
            layout.addWidget(btn_row, row, 1)
            row += 1
        # Do not move the Finish button here; it lives under the scroll area in body layout

    def _ensure_panel(self) -> None:
        """Create the floating right-side panel if needed."""
        if getattr(self, "_panel_proxy", None) is not None and getattr(self, "_panel_widget", None) is not None:
            return
        try:
            from PySide6.QtWidgets import (
                QGraphicsProxyWidget,
                QFrame,
                QVBoxLayout,
                QHBoxLayout,
                QLabel,
                QPushButton,
                QCheckBox,
            )
        except Exception:
            return
        panel = QFrame()
        panel.setObjectName("NodeCharmmFilesPanel")
        try:
            panel.setStyleSheet(
                """
                QFrame#NodeCharmmFilesPanel {
                    background-color: #2b2b2b;
                    border: 1px solid #666666;
                    border-radius: 6px;
                }
                QLabel { color: #e0e0e0; }
                QCheckBox { color: #e0e0e0; }
                QPushButton { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 4px 8px; }
                """
            )
        except Exception:
            pass
        v = QVBoxLayout(panel)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(6)
        try:
            v.addWidget(QLabel("Select file(s) for the chosen category:"))
        except Exception:
            pass
        # Dynamic list of files from folder
        from PySide6.QtWidgets import QWidget, QScrollArea
        self._panel_scroll = QScrollArea()
        self._panel_scroll.setWidgetResizable(True)
        self._panel_list_container = QWidget()
        from PySide6.QtWidgets import QVBoxLayout
        self._panel_list_layout = QVBoxLayout(self._panel_list_container)
        self._panel_list_layout.setContentsMargins(4, 4, 4, 4)
        self._panel_list_layout.setSpacing(4)
        self._panel_scroll.setWidget(self._panel_list_container)
        v.addWidget(self._panel_scroll)
        # Buttons row
        row_btns = QHBoxLayout()
        self._panel_ok = QPushButton("OK")
        try:
            self._panel_ok.setEnabled(False)
        except Exception:
            pass

        def _on_ok_clicked():
            try:
                # Collect selected file(s) for current key and update detected mapping
                if not self._panel_current_key:
                    return
                chosen = []
                for path, chk in (self._panel_file_checks or {}).items():
                    try:
                        if chk.isChecked():
                            chosen.append(path)
                    except Exception:
                        pass
                if not chosen:
                    return
                # Persist selection for the category
                try:
                    # Save in user_selected_files for durability across runs
                    sel = self.get_property("user_selected_files") or {}
                    sel[self._panel_current_key] = str(chosen[0])
                    self.set_property("user_selected_files", dict(sel))
                    # Also update current detected snapshot
                    detected = self.get_property("_detected_files") or {}
                    detected[self._panel_current_key] = str(chosen[0])
                    self.set_property("_detected_files", dict(detected))
                    # Recompute missing keys snapshot
                    missing_keys = [k for k, v in detected.items() if not v]
                    self.set_property("_missing_keys", list(missing_keys))
                except Exception:
                    pass
                # Hide panel after selection
                self._set_panel_visible(False)
                # Refresh inline list
                self._update_file_list_ui(self.get_property("_detected_files") or {})
                # If all categories resolved, enable Finish; otherwise disable
                try:
                    if self._btn_finish is not None:
                        all_resolved = all(bool((self.get_property("_detected_files") or {}).get(k)) for k, _ in self._file_keys)
                        self._btn_finish.setEnabled(all_resolved)
                except Exception:
                    pass
            except Exception:
                pass

        try:
            self._panel_ok.clicked.connect(_on_ok_clicked)
        except Exception:
            pass
        row_btns.addStretch(1)
        row_btns.addWidget(self._panel_ok)
        v.addLayout(row_btns)

        self._panel_widget = panel
        self._panel_proxy = QGraphicsProxyWidget(self)
        self._panel_proxy.setWidget(panel)
        try:
            self._panel_proxy.setVisible(False)
        except Exception:
            pass
        # When panel visibility changes, update anchor and ports adaptively
        try:
            def _anchor_base() -> float:
                return float(self.width)
            object.__setattr__(self, "_get_output_port_anchor_x", _anchor_base)  # type: ignore[arg-type]
        except Exception:
            pass

    def _update_panel_state(self, detected: Dict[str, Optional[str]]) -> None:
        if not getattr(self, "_panel_widget", None):
            return
        # Enable Finish if all categories resolved
        try:
            if getattr(self, "_btn_finish", None) is not None:
                all_resolved = all(bool(detected.get(k)) for k, _ in self._file_keys)
                self._btn_finish.setEnabled(all_resolved)
        except Exception:
            pass

    def _set_panel_visible(self, visible: bool) -> None:
        try:
            if getattr(self, "_panel_proxy", None) is not None:
                self._panel_proxy.setVisible(bool(visible))
                self._update_content_geometry(force=True)
            # Ensure Finish button remains visible even while panel is shown
            if getattr(self, "_btn_finish", None) is not None:
                try:
                    self._btn_finish.setVisible(True)
                except Exception:
                    pass
        except Exception:
            pass

    def _populate_panel_for_key(self, folder_path: str, key: str) -> None:
        """Populate the floating panel with all files from folder for the selected category key."""
        container_layout = getattr(self, "_panel_list_layout", None)
        if container_layout is None:
            return
        self._panel_current_key = key
        # Clear current entries
        try:
            while container_layout.count():
                item = container_layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()
        except Exception:
            pass
        self._panel_file_checks = {}
        from pathlib import Path as _Path
        p = _Path(folder_path)
        candidates: list[str] = []
        try:
            for child in p.rglob("*"):
                try:
                    if child.is_file():
                        # Build display name relative to base folder (use forward slashes)
                        rel = str(child.relative_to(p)).replace("\\", "/")
                        candidates.append(rel)
                except Exception:
                    pass
        except Exception:
            candidates = []
        # Sort for stable UI
        try:
            candidates.sort()
        except Exception:
            pass
        # Add checkboxes
        try:
            from PySide6.QtWidgets import QCheckBox
            for rel_path in candidates:
                chk = QCheckBox(rel_path)
                container_layout.addWidget(chk)
                # Store absolute path mapping for selection apply step
                abs_path = str(p / rel_path)
                self._panel_file_checks[abs_path] = chk
            # Enable OK only if at least one selected
            def _on_any_change():
                try:
                    any_sel = any(cb.isChecked() for cb in self._panel_file_checks.values())
                    if self._panel_ok is not None:
                        self._panel_ok.setEnabled(any_sel)
                except Exception:
                    pass
            for cb in self._panel_file_checks.values():
                try:
                    cb.stateChanged.connect(_on_any_change)
                except Exception:
                    pass
            _on_any_change()
        except Exception:
            pass

    def _update_content_geometry(self, force: bool = False) -> None:  # type: ignore[override]
        try:
            super()._update_content_geometry(force)
        except Exception:
            pass
        # Position floating panel to the right similar to DataframeMergeNode
        try:
            if getattr(self, "_panel_proxy", None) is not None and getattr(self, "_panel_widget", None) is not None and self._panel_proxy.isVisible():
                try:
                    # Match height with node body
                    self._panel_widget.setFixedHeight(int(self.height))
                except Exception:
                    pass
                panel_w = int(max(220, min(320, self.width * 0.45)))
                try:
                    self._panel_widget.setFixedWidth(panel_w)
                    self._panel_widget.adjustSize()
                except Exception:
                    pass
                x_offset = float(self.width) + 12.0
                self._panel_proxy.setPos(x_offset, 0.0)
                # Shift output ports to the right edge of the floating panel
                try:
                    def _anchor_override() -> float:
                        return float(self.width) + 12.0 + float(panel_w)
                    object.__setattr__(self, "_get_output_port_anchor_x", _anchor_override)  # type: ignore[arg-type]
                    self._update_port_positions()
                except Exception:
                    pass
            else:
                # Panel hidden: restore default output anchor to node right edge
                try:
                    def _anchor_base() -> float:
                        return float(self.width)
                    object.__setattr__(self, "_get_output_port_anchor_x", _anchor_base)  # type: ignore[arg-type]
                    self._update_port_positions()
                except Exception:
                    pass
        except Exception:
            pass

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        folder_path = inputs.get("folder") if inputs else None
        if not folder_path:
            # Fallback to property in case folder was set via property editor
            try:
                folder_path = self.get_property("folder")
            except Exception:
                folder_path = None
        
        if not folder_path:
            raise ValueError("No folder path provided")
        
        if not Path(folder_path).exists():
            raise ValueError(f"Folder not found: {folder_path}")
        
        # Auto-detect files and overlay with any previous user selections
        detected = self._detect_files(folder_path)
        try:
            sel = self.get_property("user_selected_files") or {}
            if isinstance(sel, dict):
                for k, v in sel.items():
                    if v and (k in detected):
                        detected[k] = str(v)
        except Exception:
            pass
        try:
            self.set_property("_detected_files", dict(detected))
        except Exception:
            pass
        self._update_file_list_ui(detected)

        # Determine missing
        missing_keys = [k for k, v in detected.items() if not v]
        try:
            self.set_property("_missing_keys", list(missing_keys))
        except Exception:
            pass
        has_missing = len(missing_keys) > 0
        # Pause only if masih ada kategori yang kosong setelah overlay user selection
        should_pause = has_missing

        # Update floating panel state and visibility (effective in GUI via on_result)
        self._update_panel_state(detected)
        self._set_panel_visible(should_pause)

        if should_pause:
            # Pause the workflow (headless-safe like PubChem node) and wait for user actions
            try:
                msg = "Missing files detected. Click a red category to pick files on the right, then click Finish to continue."
                self._manager.pause_user_input(self._node_id, msg)  # type: ignore[attr-defined]
            except Exception:
                # Headless fallback: cannot pause → raise explicit error
                missing = ", ".join(missing_keys)
                raise ValueError(f"Missing required files: {missing}")
            # Mark that we are waiting and return no outputs
            try:
                self.set_property("needs_confirmation", True)
            except Exception:
                pass
            return {}

        # All files present or user confirmed → return results
        try:
            self.set_property("needs_confirmation", False)
        except Exception:
            pass
        return {
            "gro_file": detected["gro"],
            "top_file": detected["top"],
            "mdp_min": detected["mdp_min"],
            "mdp_eq": detected["mdp_eq"],
            "mdp_prod": detected["mdp_prod"],
            "index_file": detected["index"],
            "folder_path": folder_path,
        }

    def validate(self) -> tuple[bool, str]:
        if self.get_property("needs_confirmation"):
            return False, "Waiting for files checklist confirmation"
        return True, "Files confirmed"

    def on_result(self, result: object) -> None:  # type: ignore[override]
        # Show/hide pause hint below the node depending on confirmation state
        try:
            needs = bool(self.get_property("needs_confirmation"))
            # In GUI, also refresh the inline file list and floating panel visibility
            detected = self.get_property("_detected_files") or {}
            # If we don't have a detected snapshot yet, try to detect from last input folder (live-only convenience)
            if not detected:
                folder_prop = self.get_property("last_input_folder") or self.get_property("folder")
                if folder_prop:
                    try:
                        fp = str(folder_prop)
                        if Path(fp).exists():
                            detected = self._detect_files(fp)
                            self.set_property("_detected_files", dict(detected))
                            missing_keys = [k for k, v in detected.items() if not v]
                            self.set_property("_missing_keys", list(missing_keys))
                    except Exception:
                        pass
            if detected:
                self._update_file_list_ui(detected)
                missing_keys = self.get_property("_missing_keys") or []
                should_pause = bool(missing_keys) and needs
                self._update_panel_state(detected)
                self._set_panel_visible(should_pause)
            if needs:
                self.show_pause("Paused: click a red category to choose file(s) on the right, then click Finish to continue.")
            else:
                if hasattr(self, 'clear_error'):
                    self.clear_error()
            self._update_content_geometry(force=False)
            self.update()
        except Exception:
            pass
        super().on_result(result)
