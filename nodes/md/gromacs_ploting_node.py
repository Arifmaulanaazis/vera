"""GromacsPlotingNode implementation."""

from .common import *  # noqa: F401,F403

class GromacsPlotingNode(BaseNode):
    """
    Minimal inline plotting node for GROMACS analysis outputs.

    Inputs (dataframes from GROMACS Analysis):
      - rmsd
      - rmsd_protein_ligand
      - rmsf_atom
      - rmsf_residue
      - radius_of_gyration
      - sasa
      - hydrogen_bonds
      - potential_energy

    UI: Combobox (select which connected input to plot), 'View' button, and image area below.
    The combobox only lists inputs that currently have data.
    """

    def __init__(self):
        super().__init__("gromacs_ploting", "GROMACS Plotting")
        self.logger = get_logger(__name__)

        # Eight dataframe inputs mirroring gromacs_analysis outputs
        self.add_input_port("rmsd", "data")
        self.add_input_port("rmsd_protein_ligand", "data")
        self.add_input_port("rmsf_atom", "data")
        self.add_input_port("rmsf_residue", "data")
        self.add_input_port("radius_of_gyration", "data")
        self.add_input_port("sasa", "data")
        self.add_input_port("hydrogen_bonds", "data")
        self.add_input_port("potential_energy", "data")

        # Visual size
        self.width = 360
        self.height = 280
        try:
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)
            # Tighter margins to maximize image area
            self.set_content_margins(8, 48, 8, 8)
        except Exception:
            pass

        # Inline UI: [Combo] [Color] [View] on top row, image label below
        try:
            from PySide6.QtWidgets import QComboBox, QPushButton, QLabel, QSizePolicy, QSpacerItem, QColorDialog
            from PySide6.QtCore import Qt, QObject, Signal, QThread

            self._combo = QComboBox()
            self._combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            try:
                self._combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            except Exception:
                pass

            self._btn_view = QPushButton("View")
            try:
                self._btn_view.clicked.connect(self._on_view_clicked)
            except Exception:
                pass

            # Color selector button
            self._btn_color = QPushButton()
            try:
                self._btn_color.setFixedWidth(28)
                self._btn_color.setToolTip("Pick plot color")
            except Exception:
                pass
            # Default plot color
            try:
                if not self.get_property("plot_color"):
                    self.set_property("plot_color", "#4169e1")  # royalblue
            except Exception:
                pass
            try:
                def _pick_color():
                    try:
                        col = QColorDialog.getColor()
                        if col and col.isValid():
                            self.set_property("plot_color", col.name())
                            self._update_color_button_style()
                    except Exception:
                        pass
                self._btn_color.clicked.connect(_pick_color)
            except Exception:
                pass

            self._img = QLabel()
            self._img.setAlignment(Qt.AlignCenter)
            try:
                self._img.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                self._img.setStyleSheet("QLabel { background-color: rgba(40,40,40,100); border: 1px solid #666; border-radius: 4px; color: #ccc; }")
                self._img.setText("No plot")
            except Exception:
                pass

            layout = self.content_layout
            if layout is not None:
                # Top controls
                layout.addWidget(self._combo, 0, 0)
                layout.addWidget(self._btn_color, 0, 1, alignment=Qt.AlignLeft)
                layout.addWidget(self._btn_view, 0, 2, alignment=Qt.AlignLeft)
                # Make controls responsive
                try:
                    layout.setColumnStretch(0, 1)
                    layout.setColumnStretch(1, 0)
                    layout.setColumnStretch(2, 0)
                    layout.setRowStretch(1, 1)
                except Exception:
                    pass
                # Plot area
                layout.addWidget(self._img, 1, 0, 1, 3)

            # Populate initial options
            self._refresh_combo_items()
            self._update_color_button_style()
            # Align ports after custom content
            self._update_port_positions()

            # Async rendering members
            self._render_thread = None
            self._render_worker = None
        except Exception:
            self._combo = None
            self._btn_view = None
            self._btn_color = None
            self._img = None

    # Map friendly labels to input port keys
    _LABEL_TO_PORT = {
        "RMSD": "rmsd",
        "RMSD Protein-Ligand": "rmsd_protein_ligand",
        "RMSF Atom": "rmsf_atom",
        "RMSF Residue": "rmsf_residue",
        "Radius of Gyration": "radius_of_gyration",
        "SASA": "sasa",
        "Hydrogen Bonds": "hydrogen_bonds",
        "Potential Energy": "potential_energy",
    }

    def _available_inputs(self) -> dict[str, object]:
        """Return mapping of port_key -> dataframe-like for ports that currently have data."""
        available: dict[str, object] = {}
        for _label, port_key in self._LABEL_TO_PORT.items():
            val = self.properties.get(f"last_input_{port_key}")
            if val is None:
                continue
            try:
                # Accept pandas DataFrame or list-of-dicts non-empty
                if hasattr(val, "empty"):
                    if not bool(val.empty):
                        available[port_key] = val
                elif isinstance(val, list):
                    if len(val) == 0 or isinstance(val[0], dict):
                        if len(val) > 0:
                            available[port_key] = val
                elif isinstance(val, dict):
                    if len(val) > 0:
                        available[port_key] = val
            except Exception:
                # Be permissive: include if truthy
                try:
                    if val:
                        available[port_key] = val
                except Exception:
                    pass
        return available

    def _refresh_combo_items(self) -> None:
        try:
            if self._combo is None:
                return
            self._combo.clear()
            avail = self._available_inputs()
            # Add items using friendly labels, only for available ports
            for label, port in self._LABEL_TO_PORT.items():
                if port in avail:
                    self._combo.addItem(label, userData=port)
            if self._combo.count() == 0:
                self._combo.addItem("(no data)", userData=None)
        except Exception:
            pass

    def _update_color_button_style(self) -> None:
        try:
            if self._btn_color is None:
                return
            col = self.get_property("plot_color") or "#4169e1"
            # Show color as button background
            self._btn_color.setStyleSheet(f"QPushButton {{ background-color: {col}; border: 1px solid #666; }}")
        except Exception:
            pass

    def _on_view_clicked(self) -> None:
        try:
            if self._combo is None or self._img is None:
                return
            port_key = self._combo.currentData()
            if not port_key:
                return
            data_obj = self._available_inputs().get(port_key)
            if data_obj is None:
                return
            self._start_async_render(port_key, data_obj)
        except Exception:
            pass

    def _start_async_render(self, port_key: str, data_obj: object) -> None:
        """Render plot in background thread to avoid UI freeze."""
        try:
            from PySide6.QtCore import QObject, Signal, QThread
        except Exception:
            # Fallback to sync
            try:
                img_bytes = self._render_plot_bytes(port_key, data_obj)
                self._last_image_bytes = img_bytes
                self._set_image(img_bytes)
            except Exception:
                pass
            return

        class _PlotRenderWorker(QObject):  # type: ignore[misc]
            finished = Signal(bytes)
            failed = Signal(str)
            def __init__(self, outer: 'GromacsPlotingNode', key: str, obj: object):
                super().__init__()
                self._outer = outer
                self._key = key
                self._obj = obj
            def run(self) -> None:
                try:
                    data = self._outer._render_plot_bytes(self._key, self._obj)
                    self.finished.emit(data)
                except Exception as e:  # pragma: no cover - best-effort
                    self.failed.emit(str(e))

        try:
            # Show busy state
            if self._img is not None:
                try:
                    self._img.setText("Rendering…")
                except Exception:
                    pass
            if self._btn_view is not None:
                try:
                    self._btn_view.setEnabled(False)
                except Exception:
                    pass

            # Clean previous thread if any
            try:
                if getattr(self, "_render_thread", None) is not None:
                    try:
                        self._render_thread.quit()
                        self._render_thread.wait(50)
                    except Exception:
                        pass
            except Exception:
                pass

            thread = QThread()
            worker = _PlotRenderWorker(self, port_key, data_obj)
            worker.moveToThread(thread)
            try:
                thread.started.connect(worker.run)
            except Exception:
                pass

            def _on_done(data: bytes) -> None:
                try:
                    self._last_image_bytes = data
                except Exception:
                    pass
                self._set_image(data)
                try:
                    self._btn_view.setEnabled(True)
                except Exception:
                    pass
                try:
                    thread.quit()
                except Exception:
                    pass

            def _on_fail(_msg: str) -> None:
                try:
                    self._img.setText("Failed to render")
                except Exception:
                    pass
                try:
                    self._btn_view.setEnabled(True)
                except Exception:
                    pass
                try:
                    thread.quit()
                except Exception:
                    pass

            try:
                worker.finished.connect(_on_done)
                worker.failed.connect(_on_fail)
            except Exception:
                pass

            # Keep refs
            self._render_thread = thread
            self._render_worker = worker
            thread.start()
        except Exception:
            # Fallback to sync if threading fails
            try:
                img_bytes = self._render_plot_bytes(port_key, data_obj)
                self._last_image_bytes = img_bytes
                self._set_image(img_bytes)
            except Exception:
                pass

    def _render_plot_bytes(self, port_key: str, data_obj: object) -> bytes:
        """Create a PNG plot for the given dataset and return image bytes."""
        import io
        try:
            from utils.mpl_utils import import_pyplot_non_interactive
            plt = import_pyplot_non_interactive()
        except Exception:
            try:
                import matplotlib.pyplot as plt  # type: ignore
            except Exception:
                return b""

        # Normalize to pandas DataFrame when possible
        df = None
        try:
            import pandas as pd  # type: ignore
            if hasattr(data_obj, "empty"):
                df = data_obj
            elif isinstance(data_obj, list):
                df = pd.DataFrame(data_obj)
            elif isinstance(data_obj, dict):
                df = pd.DataFrame(data_obj)
        except Exception:
            df = None

        plt.figure(figsize=(4.8, 3.2))

        def _plot_xy(xcol: str, ycol: str, title: str, x_label: str, y_label: str):
            try:
                color = self.get_property("plot_color") or "#4169e1"
                plt.plot(df[xcol], df[ycol], color=color, linewidth=1.8)
                plt.xlabel(x_label)
                plt.ylabel(y_label)
                plt.title(title)
            except Exception:
                # Fallback to first two numeric columns
                try:
                    num_cols = [c for c in df.columns if str(c).strip()]
                    if len(num_cols) >= 2:
                        color = self.get_property("plot_color") or "#4169e1"
                        plt.plot(df[num_cols[0]], df[num_cols[1]], color=color, linewidth=1.8)
                        plt.xlabel(x_label or str(num_cols[0]))
                        plt.ylabel(y_label or str(num_cols[1]))
                        plt.title(title)
                except Exception:
                    pass

        try:
            if df is None or getattr(df, "empty", False):
                plt.text(0.5, 0.5, "No data", ha="center", va="center")
            else:
                key = port_key
                if key == "rmsd":
                    _plot_xy("time_ns", "rmsd_nm", "RMSD", "Time (ns)", "RMSD (nm)")
                elif key == "rmsd_protein_ligand":
                    _plot_xy("time_ns", "rmsd_nm", "RMSD Protein-Ligand", "Time (ns)", "RMSD (nm)")
                elif key == "rmsf_atom":
                    _plot_xy("atom_index", "rmsf_nm", "RMSF (Atom)", "Atom Index", "RMSF (nm)")
                elif key == "rmsf_residue":
                    _plot_xy("residue", "rmsf_nm", "RMSF (Residue)", "Residue", "RMSF (nm)")
                elif key == "radius_of_gyration":
                    _plot_xy("time_ps", "Rg", "Radius of Gyration", "Time (ps)", "Rg (nm)")
                elif key == "sasa":
                    _plot_xy("time_ps", "SASA_nm2", "SASA", "Time (ps)", "SASA (nm^2)")
                elif key == "hydrogen_bonds":
                    _plot_xy("time_ps", "num_hbonds", "Hydrogen Bonds", "Time (ps)", "Number of H-bonds")
                elif key == "potential_energy":
                    _plot_xy("time_ps", "potential_kJ_per_mol", "Potential Energy", "Time (ps)", "Potential Energy (kJ/mol)")
                else:
                    # Generic fallback
                    try:
                        num_cols = [c for c in df.columns if str(c).strip()]
                        if len(num_cols) >= 2:
                            color = self.get_property("plot_color") or "#4169e1"
                            plt.plot(df[num_cols[0]], df[num_cols[1]], color=color, linewidth=1.8)
                    except Exception:
                        plt.text(0.5, 0.5, "Unsupported data", ha="center", va="center")
        except Exception:
            plt.text(0.5, 0.5, "Error plotting", ha="center", va="center")

        buf = io.BytesIO()
        try:
            # tight_layout can be relatively expensive; skip if small figure
            if hasattr(plt, 'gcf'):
                fig = plt.gcf()
                try:
                    w, h = fig.get_size_inches()
                    if w * h > 10.0:
                        plt.tight_layout()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            # Use slightly lower DPI for faster rendering while keeping clarity
            plt.savefig(buf, format="png", dpi=150)
            plt.close()
        except Exception:
            return b""
        return buf.getvalue()

    def _set_image(self, data: bytes | None) -> None:
        if self._img is None:
            return
        try:
            from PySide6.QtGui import QPixmap, QImage
            from PySide6.QtCore import Qt
            if not data:
                self._img.setText("No plot")
                return
            img = QImage.fromData(data)
            if img.isNull():
                self._img.setText("Invalid image")
                return
            available_width = max(32, self.width - 24)
            available_height = max(32, self.height - 72)  # controls + margins
            scaled = img.scaled(available_width, available_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._img.setPixmap(QPixmap.fromImage(scaled))
            self._img.setText("")
        except Exception:
            try:
                self._img.setText("Error displaying image")
            except Exception:
                pass

    def on_result(self, result: object) -> None:
        # Update available options when new data flows in
        try:
            self._refresh_combo_items()
        except Exception:
            pass
        super().on_result(result)

    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        # Hide default inline summary to keep UI minimal
        return []

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """No-op compute: refresh UI and, if possible, auto-render a plot.

        Returns an empty dict since this node does not expose outputs.
        """
        try:
            # Ensure options reflect latest live inputs
            self._refresh_combo_items()
            # If a selection exists or only one option is available, render automatically
            port_key = None
            try:
                if self._combo is not None:
                    data_key = self._combo.currentData()
                    if data_key:
                        port_key = data_key
            except Exception:
                pass
            if not port_key:
                avail = self._available_inputs()
                if avail:
                    # pick first available dataset
                    port_key = next(iter(avail.keys()))
            if port_key:
                data_obj = self._available_inputs().get(port_key)
                if data_obj is not None:
                    img_bytes = self._render_plot_bytes(port_key, data_obj)
                    try:
                        self._last_image_bytes = img_bytes
                    except Exception:
                        pass
                    self._set_image(img_bytes)
        except Exception:
            pass
        return {}

    def _update_content_geometry(self, force: bool = False) -> None:  # type: ignore[override]
        try:
            super()._update_content_geometry(force)
        except Exception:
            pass
        # Rescale current image to fit new size for responsiveness
        try:
            img_bytes = getattr(self, "_last_image_bytes", None)
            if img_bytes:
                self._set_image(img_bytes)
        except Exception:
            pass
