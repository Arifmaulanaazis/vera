"""SliceRowsNode implementation."""

from .common import *  # noqa: F401,F403

class SliceRowsNode(BaseNode):
    """Slice rows by start:end:step, similar to Python slicing.

    Properties: start (int), end (int), step (int, default 1)
    """

    def __init__(self):
        super().__init__("slice_rows", "Slice Rows")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("data", "data")
        self.set_property("start", 0)
        self.set_property("end", None)
        self.set_property("step", 1)
        self.set_property("auto_refresh_preview", True)

        from PySide6.QtWidgets import (
            QTableWidget,
            QGraphicsProxyWidget,
            QWidget,
            QVBoxLayout,
            QHBoxLayout,
            QLineEdit,
            QLabel,
            QPushButton,
            QFrame,
        )

        # Sizing
        self.width = 560
        self.height = 240
        try:
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)
            self.set_content_margins(0, 32, 0, 0)
        except Exception:
            pass

        # Table in node
        try:
            self._table = QTableWidget()
            self._table.setColumnCount(0)
            self._table.setRowCount(0)
            try:
                self._table.setAlternatingRowColors(True)
                self._table.setShowGrid(True)
                header = self._table.horizontalHeader()
                header.setStretchLastSection(True)
            except Exception:
                pass
            layout = self.content_layout
            if layout is not None:
                layout.addWidget(self._table, 0, 0)
            self._update_port_positions()
        except Exception:
            self._table = None

        # Floating params panel
        self._params_proxy = None
        self._params_widget = None
        try:
            panel = QFrame()
            panel.setObjectName("NodeSliceParams")
            try:
                panel.setStyleSheet(
                    """
                    QFrame#NodeSliceParams {
                        background-color: #2b2b2b;
                        border: 1px solid #666;
                        border-radius: 6px;
                    }
                    QLabel { color: #e0e0e0; }
                    QLineEdit { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 2px 6px; }
                    QPushButton { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 4px 8px; }
                    """
                )
            except Exception:
                pass
            v = QVBoxLayout(panel)
            v.setContentsMargins(8, 6, 8, 6)
            v.setSpacing(6)

            row_start = QVBoxLayout()
            row_start.addWidget(QLabel("Start"))
            self._edit_start = QLineEdit(str(self.get_property("start") if self.get_property("start") is not None else ""))
            row_start.addWidget(self._edit_start)
            v.addLayout(row_start)

            row_end = QVBoxLayout()
            row_end.addWidget(QLabel("End"))
            self._edit_end = QLineEdit("" if self.get_property("end") is None else str(self.get_property("end")))
            row_end.addWidget(self._edit_end)
            v.addLayout(row_end)

            row_step = QVBoxLayout()
            row_step.addWidget(QLabel("Step"))
            self._edit_step = QLineEdit(str(self.get_property("step") or 1))
            row_step.addWidget(self._edit_step)
            v.addLayout(row_step)

            btns = QHBoxLayout()
            self._btn_refresh = QPushButton("Refresh")
            btns.addStretch(1)
            btns.addWidget(self._btn_refresh)
            v.addLayout(btns)

            self._params_widget = panel
            self._params_proxy = QGraphicsProxyWidget(self)
            self._params_proxy.setWidget(panel)
            try:
                self._params_proxy.setZValue(8)
                self._params_proxy.setVisible(True)
            except Exception:
                pass
            try:
                self._update_content_geometry(force=True)
                self.update()
            except Exception:
                pass

            # Wire
            self._edit_start.textChanged.connect(self._on_start_changed)
            self._edit_end.textChanged.connect(self._on_end_changed)
            self._edit_step.textChanged.connect(self._on_step_changed)
            self._btn_refresh.clicked.connect(self._on_refresh_clicked)
        except Exception:
            self._params_proxy = None
            self._params_widget = None

    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        return []

    def _update_content_geometry(self, force: bool = False) -> None:  # type: ignore[override]
        try:
            super()._update_content_geometry(force)
        except Exception:
            pass
        try:
            if getattr(self, "_params_proxy", None) is not None and getattr(self, "_params_widget", None) is not None:
                try:
                    self._params_widget.setFixedHeight(int(self.height))
                except Exception:
                    pass
                panel_w = int(max(140, min(240, self.width * 0.35)))
                try:
                    self._params_widget.setFixedWidth(panel_w)
                    self._params_widget.adjustSize()
                except Exception:
                    pass
                x_offset = float(self.width) + 12.0
                self._params_proxy.setPos(x_offset, 0.0)
                try:
                    def _anchor_override() -> float:
                        return float(self.width) + 12.0 + float(panel_w)
                    object.__setattr__(self, "_get_output_port_anchor_x", _anchor_override)  # type: ignore[arg-type]
                    self._update_port_positions()
                except Exception:
                    pass
        except Exception:
            pass

    def _set_table_data(self, data: Any) -> None:
        try:
            from PySide6.QtWidgets import QTableWidgetItem
        except Exception:
            return
        if getattr(self, "_table", None) is None:
            return
        try:
            self._table.setUpdatesEnabled(False)
            self._table.setSortingEnabled(False)
        except Exception:
            pass
        rows: list[dict]
        if data is None:
            rows = []
        elif isinstance(data, list) and (len(data) == 0 or isinstance(data[0], dict)):
            rows = data
        else:
            try:
                import pandas as pd
                if isinstance(data, pd.DataFrame):
                    rows = data.to_dict(orient="records")
                else:
                    rows = [{"value": str(item)} for item in (data if isinstance(data, list) else [data])]
            except Exception:
                rows = [{"value": str(data)}]
        max_rows = 100
        rows = rows[:max_rows]
        headers = list(rows[0].keys()) if rows else []
        self._table.clear()
        self._table.setColumnCount(len(headers))
        if headers:
            try:
                self._table.setHorizontalHeaderLabels(headers)
            except Exception:
                pass
        self._table.setRowCount(len(rows))
        for r_idx, row in enumerate(rows):
            for c_idx, key in enumerate(headers):
                try:
                    item = QTableWidgetItem(str(row.get(key, "")))
                    self._table.setItem(r_idx, c_idx, item)
                except Exception:
                    pass
        try:
            self._table.setSortingEnabled(True)
            self._table.setUpdatesEnabled(True)
        except Exception:
            pass

    def _update_preview_from_last_input(self) -> None:
        try:
            res = self.properties.get("last_result")
            if isinstance(res, dict) and "data" in res:
                self._set_table_data(res["data"])
                return
            data = self.properties.get("last_input_data")
            if data is None:
                data = self.properties.get("last_input_results")
            if data is None:
                self._set_table_data([])
                return
            try:
                tmp = self.execute({"data": data})
                self._set_table_data(tmp.get("data"))
            except Exception:
                self._set_table_data(_to_rows(data))
        except Exception:
            pass

    # UI callbacks
    def _on_start_changed(self, text: str) -> None:
        try:
            t = text.strip()
            self.set_property("start", None if t == "" else t)
            self._update_preview_from_last_input()
        except Exception:
            pass

    def _on_end_changed(self, text: str) -> None:
        try:
            t = text.strip()
            self.set_property("end", None if t == "" else t)
            self._update_preview_from_last_input()
        except Exception:
            pass

    def _on_step_changed(self, text: str) -> None:
        try:
            t = text.strip()
            self.set_property("step", None if t == "" else t)
            self._update_preview_from_last_input()
        except Exception:
            pass

    def _on_refresh_clicked(self) -> None:
        try:
            self._update_preview_from_last_input()
            try:
                if hasattr(self, 'rerun_requested'):
                    self.rerun_requested.emit(self)
            except Exception:
                pass
        except Exception:
            pass

    def on_result(self, result: object) -> None:  # pragma: no cover - UI update hook
        try:
            if bool(self.get_property("auto_refresh_preview")):
                self._update_preview_from_last_input()
            try:
                self._update_content_geometry(force=False)
                self.update()
            except Exception:
                pass
        except Exception:
            pass
        super().on_result(result)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not inputs or "data" not in inputs:
            raise ValueError("No input data provided")
        rows = _to_rows(inputs["data"])  # list[dict]
        start = self.get_property("start")
        end = self.get_property("end")
        step = self.get_property("step") or 1
        try:
            s_val = int(start) if start is not None else None
        except Exception:
            s_val = None
        try:
            e_val = int(end) if end is not None else None
        except Exception:
            e_val = None
        try:
            st_val = int(step) if step is not None else 1
            if st_val == 0:
                st_val = 1
        except Exception:
            st_val = 1
        sliced = rows[slice(s_val, e_val, st_val)]
        return {"data": sliced}
