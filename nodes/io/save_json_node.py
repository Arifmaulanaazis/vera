"""SaveJsonNode implementation."""

from .common import *  # noqa: F401,F403

class SaveJsonNode(BaseNode):
    """Save data as JSON file with pretty formatting."""

    def __init__(self):
        super().__init__("save_json", "Save JSON")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("saved_file", "string")
        self.set_property("output_path", "")
        self.set_property("overwrite", True)

        # Inline Browse UI
        try:
            from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QFileDialog, QSpacerItem, QSizePolicy

            self.width = 320
            self.height = 140
            try:
                self.setMinimumSize(self.width, self.height)
                self.setMaximumSize(self.width, self.height)
            except Exception:
                pass

            layout = self.content_layout
            if layout is not None:
                layout.addItem(QSpacerItem(0, 6, QSizePolicy.Minimum, QSizePolicy.Fixed), 0, 0, 1, 3)
                lbl = QLabel("Output Path")
                lbl.setStyleSheet("QLabel { background: transparent; }")
                edit = QLineEdit(self.get_property("output_path") or "")
                btn = QPushButton("Browse…")

                def on_browse():  # pragma: no cover - UI-only
                    try:
                        filters = "JSON (*.json);;All Files (*)"
                        filename, _ = QFileDialog.getSaveFileName(None, "Select Output File", edit.text(), filters)
                        if filename:
                            edit.setText(filename)
                            self.set_property("output_path", filename)
                    except Exception:
                        pass

                def on_text_changed(text: str):
                    try:
                        self.set_property("output_path", text)
                    except Exception:
                        pass

                edit.textChanged.connect(on_text_changed)
                btn.clicked.connect(on_browse)

                layout.addWidget(lbl, 1, 0)
                layout.addWidget(edit, 1, 1)
                layout.addWidget(btn, 1, 2)
            self._update_port_positions()
        except Exception:
            pass

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        out_path = self.get_property("output_path")
        if not out_path:
            raise ValueError("Output path is required")
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists() and not bool(self.get_property("overwrite")):
            raise ValueError(f"File exists and overwrite disabled: {out}")
        data = (inputs or {}).get("data")
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return {"saved_file": str(out), "file_size": out.stat().st_size if out.exists() else 0}

    def validate(self) -> tuple[bool, str]:
        p = self.get_property("output_path")
        if not p:
            return False, "Output path not specified"
        try:
            Path(p).parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return False, f"Cannot create output directory: {e}"
        return True, "Node configuration is valid"
