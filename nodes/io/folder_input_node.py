"""FolderInputNode implementation."""

from .common import *  # noqa: F401,F403

class FolderInputNode(BaseNode):
    """Folder input that selects/outputs folder path.

    Outputs:
      - folder (string): selected folder path
    """

    def __init__(self):
        super().__init__("folder_input", "Folder Input")
        self.logger = get_logger(__name__)

        # Outputs only
        self.add_output_port("folder", "string")

        # Properties
        self.set_property("folder_path", "")  # folder path

        # Inline select button for quick folder picking (GUI only)
        try:
            from PySide6.QtWidgets import QPushButton, QFileDialog

            self.width = 260
            self.height = 120
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)

            btn = QPushButton("Select Folder…")
            btn.setToolTip("Open folder dialog")
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
            folder_path = self.get_property("folder_path")
            if not folder_path:
                raise ValueError("No folder selected")
            if not Path(folder_path).exists():
                raise ValueError(f"Folder not found: {folder_path}")
            if not Path(folder_path).is_dir():
                raise ValueError(f"Path is not a folder: {folder_path}")
            return {
                "folder": folder_path,
            }
        except Exception as e:
            self.logger.error(f"Error collecting folder path: {e}")
            raise

    def validate(self) -> tuple[bool, str]:
        folder_path = self.get_property("folder_path")
        if not folder_path:
            return False, "No folder selected"
        if not Path(folder_path).exists():
            return False, f"Folder not found: {folder_path}"
        if not Path(folder_path).is_dir():
            return False, f"Path is not a folder: {folder_path}"
        return True, "Node configuration is valid"

    # GUI callback
    def _on_browse_clicked(self):  # pragma: no cover - UI-only
        try:
            from PySide6.QtWidgets import QFileDialog
            folder = QFileDialog.getExistingDirectory(
                None,
                "Select Input Folder",
                "",
                QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
            )
            if folder:
                self.set_property("folder_path", folder)
        except Exception:
            pass

    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        try:
            folder_path = self.get_property("folder_path") or ""
            if not folder_path:
                return ["No folder selected"]
            folder_name = Path(folder_path).name
            return ["Folder:", f"{folder_name}"]
        except Exception:
            return super()._inline_summary()
