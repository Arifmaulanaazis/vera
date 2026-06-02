"""SaveDataFrameNode implementation."""

from .common import *  # noqa: F401,F403

class SaveDataFrameNode(BaseNode):
    """Save DataFrame or tabular data (list-of-dicts) to CSV/TSV/Excel."""

    def __init__(self):
        super().__init__("save_dataframe", "Save DataFrame")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("saved_file", "string")
        self.set_property("output_path", "")
        self.set_property("file_type", "auto")  # auto|csv|tsv|xlsx|xls
        self.set_property("overwrite", True)
        self.set_property("include_index", False)

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
                        filters = "CSV (*.csv);;TSV (*.tsv);;Excel (*.xlsx *.xls);;All Files (*)"
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
        ftype = (self.get_property("file_type") or "auto").lower()
        if ftype == "auto":
            ftype = out.suffix.lower().lstrip('.')
        data = (inputs or {}).get("data")
        if data is None:
            raise ValueError("No data provided")
        include_index = bool(self.get_property("include_index"))
        if ftype == "csv":
            if hasattr(data, 'to_csv'):
                data.to_csv(out, index=include_index)
            elif isinstance(data, list) and (len(data) == 0 or isinstance(data[0], dict)):
                pd.DataFrame(data).to_csv(out, index=include_index)
            else:
                raise ValueError("Data must be DataFrame or list-of-dicts for CSV")
        elif ftype == "tsv":
            if hasattr(data, 'to_csv'):
                data.to_csv(out, index=include_index, sep='\t')
            elif isinstance(data, list) and (len(data) == 0 or isinstance(data[0], dict)):
                pd.DataFrame(data).to_csv(out, index=include_index, sep='\t')
            else:
                raise ValueError("Data must be DataFrame or list-of-dicts for TSV")
        elif ftype in {"xlsx", "xls"}:
            try:
                # Check if openpyxl is available
                try:
                    import openpyxl
                except ImportError:
                    raise RuntimeError("openpyxl is not installed. Please install it with: pip install openpyxl")
                
                if hasattr(data, 'to_excel'):
                    data.to_excel(out, index=include_index, engine='openpyxl')
                elif isinstance(data, list) and (len(data) == 0 or isinstance(data[0], dict)):
                    pd.DataFrame(data).to_excel(out, index=include_index, engine='openpyxl')
                else:
                    raise ValueError("Data must be DataFrame or list-of-dicts for Excel")
            except Exception as e:
                # Show the actual error instead of masking it
                raise RuntimeError(f"Error writing Excel file: {str(e)}") from e
        else:
            raise ValueError(f"Unsupported DataFrame file type: {ftype}")
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
