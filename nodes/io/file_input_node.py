"""FileInputNode implementation."""

from .common import *  # noqa: F401,F403

class FileInputNode(BaseNode):
    """File input that only selects/outputs path(s) without reading content.

    Outputs:
      - files (list): list of selected file paths
      - file (file): first file path (or empty string)
      - file_paths (string): semicolon-separated paths (for convenience)
    """

    def __init__(self):
        super().__init__("file_input", "File Input")
        self.logger = get_logger(__name__)

        # Outputs only
        self.add_output_port("files", "list")
        self.add_output_port("file", "file")
        self.add_output_port("file_paths", "string")

        # Properties
        self.set_property("file_paths", "")  # semicolon-separated or single

        # Inline select button for quick file picking (GUI only)
        try:
            from PySide6.QtWidgets import QPushButton, QFileDialog

            self.width = 260
            self.height = 120
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)

            btn = QPushButton("Select Files…")
            btn.setToolTip("Open file dialog (supports multi-select)")
            btn.clicked.connect(self._on_browse_clicked)  # type: ignore[attr-defined]

            layout = self.content_layout
            if layout is not None:
                from PySide6.QtWidgets import QSpacerItem, QSizePolicy
                layout.addItem(QSpacerItem(0, 8, QSizePolicy.Minimum, QSizePolicy.Fixed), 0, 0)
                layout.addWidget(btn, 1, 0)
            self._update_port_positions()
        except Exception:
            pass

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            raw = self.get_property("file_paths")
            files = _as_path_list(raw)
            first = files[0] if files else ""
            return {
                "files": files,
                "file": first,
                "file_paths": ";".join(files),
                "num_files": len(files),
            }
        except Exception as e:
            self.logger.error(f"Error collecting file paths: {e}")
            raise

    def validate(self) -> tuple[bool, str]:
        files = _as_path_list(self.get_property("file_paths"))
        if not files:
            return False, "No files selected"
        # if any don't exist, warn
        for p in files:
            if not Path(p).exists():
                return False, f"File not found: {p}"
        return True, "Node configuration is valid"

    # GUI callback
    def _on_browse_clicked(self):  # pragma: no cover - UI-only
        try:
            from PySide6.QtWidgets import QFileDialog
            files, _ = QFileDialog.getOpenFileNames(
                None,
                "Select Input Files",
                "",
                "All Files (*);;Chemistry (*.sdf *.mol *.mol2 *.pdb *.pdbqt *.xyz);;Data (*.csv *.tsv *.xlsx *.xls *.txt *.json *.arw)",
            )
            if files:
                self.set_property("file_paths", ";".join(files))
        except Exception:
            pass

    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        try:
            files = _as_path_list(self.get_property("file_paths") or "")
            if not files:
                return ["No files selected"]
            first = Path(files[0]).name
            more = len(files) - 1
            return ["Files:", f"{first}" + (f"  +{more} more" if more > 0 else "")]
        except Exception:
            return super()._inline_summary()
