"""GromacsInputEditorNode implementation."""

from .common import *  # noqa: F401,F403

class GromacsInputEditorNode(BaseNode):
    """GROMACS Input Editor for modifying MDP parameters.
    Allows editing MDP file parameters before running MD simulation.
    """

    def __init__(self):
        super().__init__("gromacs_input_editor", "GROMACS Input Editor")
        self.logger = get_logger(__name__)
        # Single input/output: mdp_file
        self.add_input_port("mdp_file", "file")
        self.add_output_port("mdp_file", "file")

        # Properties
        self.set_property("needs_editing", True)
        self.set_property("_current_mdp_path", "")
        self.set_property("_mdp_text_content", "")

        # Inline UI: plain text editor + OK button, no labels
        try:
            from PySide6.QtWidgets import (QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

            self.width = 560
            self.height = 320
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)
            try:
                self.set_content_margins(0, 32, 0, 0)
            except Exception:
                pass

            container = QWidget()
            main_layout = QVBoxLayout(container)
            main_layout.setContentsMargins(6, 6, 6, 6)
            main_layout.setSpacing(6)

            self._txt = QPlainTextEdit()
            try:
                self._txt.setPlaceholderText("")
            except Exception:
                pass
            self._btn_ok = QPushButton("OK")
            try:
                self._btn_ok.setEnabled(True)
            except Exception:
                pass

            def _on_ok_clicked():
                try:
                    # Write current text back to the MDP file immediately
                    mdp_path = str(self.get_property("_current_mdp_path") or "")
                    if mdp_path:
                        try:
                            text = self._txt.toPlainText() if hasattr(self._txt, 'toPlainText') else str(self.get_property("_mdp_text_content") or "")
                        except Exception:
                            text = str(self.get_property("_mdp_text_content") or "")
                        try:
                            with open(mdp_path, 'w', encoding='utf-8') as f:
                                f.write(text)
                        except Exception as e:
                            self.logger.error(f"Failed to write MDP file: {e}")
                        # Update property so next run shows latest content
                        try:
                            self.set_property("_mdp_text_content", text)
                        except Exception:
                            pass
                    # Mark editing complete
                    try:
                        self.set_property("needs_editing", False)
                    except Exception:
                        pass
                    # Resume workflow
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
                except Exception as e:
                    self.logger.error(f"Error in OK button: {e}")

            try:
                self._btn_ok.clicked.connect(_on_ok_clicked)
            except Exception:
                pass

            # Assemble
            main_layout.addWidget(self._txt)
            main_layout.addWidget(self._btn_ok)

            content_layout = self.content_layout
            if content_layout is not None:
                content_layout.addWidget(container, 0, 0)
            self._update_port_positions()
        except Exception:
            self._txt = None
            self._btn_ok = None

    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        # Hide default painted labels inside the node body
        return []

    def on_result(self, result: object) -> None:  # type: ignore[override]
        # Keep editor content in sync when running with live canvas
        try:
            text = self.get_property("_mdp_text_content") or ""
            self._load_text_into_ui(str(text))
            # Show pause hint when waiting for user edit
            if bool(self.get_property("needs_editing")):
                try:
                    self.show_pause("Waiting for user: edit the MDP and click OK.")
                except Exception:
                    pass
            else:
                try:
                    self.clear_error()
                except Exception:
                    pass
            self._update_content_geometry(force=False)
            self.update()
        except Exception:
            pass
        super().on_result(result)

    def _load_text_into_ui(self, text: str) -> None:
        editor = getattr(self, "_txt", None)
        if editor is None:
            return
        try:
            editor.blockSignals(True)
            editor.setPlainText(text)
        except Exception:
            try:
                editor.setPlainText(text)
            except Exception:
                pass
        finally:
            try:
                editor.blockSignals(False)
            except Exception:
                pass

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        mdp_path = inputs.get("mdp_file") if inputs else None
        if not mdp_path:
            raise ValueError("MDP file is required")

        # Remember current path for OK handler
        try:
            self.set_property("_current_mdp_path", str(mdp_path))
        except Exception:
            pass

        # Load file content
        text = ""
        try:
            with open(mdp_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        except Exception:
            text = ""
        try:
            self.set_property("_mdp_text_content", text)
        except Exception:
            pass

        # Update UI text (in GUI this will apply via on_result too)
        self._load_text_into_ui(text)

        # Pause for user editing if needed
        if self.get_property("needs_editing"):
            try:
                msg = "Edit MDP content, then click OK to continue."
                self._manager.pause_user_input(self._node_id, msg)  # type: ignore[attr-defined]
            except Exception:
                # Headless: if cannot pause, continue without editing
                try:
                    self.set_property("needs_editing", False)
                except Exception:
                    pass
                return {"mdp_file": mdp_path}
            # While paused, return original file
            return {"mdp_file": mdp_path}

        # If not needing edits, pass-through current file
        return {"mdp_file": mdp_path}
