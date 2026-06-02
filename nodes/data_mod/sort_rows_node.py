"""SortRowsNode implementation."""

from .common import *  # noqa: F401,F403

class SortRowsNode(BaseNode):
    """Sort rows by one or more keys.

    Properties: by (list[str] or comma-separated str), ascending (bool), numeric (bool)
    """

    def __init__(self):
        super().__init__("sort_rows", "Sort Rows")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("data", "data")
        self.set_property("by", [])
        self.set_property("ascending", True)
        self.set_property("numeric", False)  # try numeric comparison where possible
        self.set_property("auto_refresh_preview", True)

        from PySide6.QtWidgets import (
            QTableWidget,
            QGraphicsProxyWidget,
            QWidget,
            QVBoxLayout,
            QHBoxLayout,
            QLineEdit,
            QLabel,
            QCheckBox,
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

        # Table
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
            panel.setObjectName("NodeSortParams")
            try:
                panel.setStyleSheet(
                    """
                    QFrame#NodeSortParams {
                        background-color: #2b2b2b;
                        border: 1px solid #666;
                        border-radius: 6px;
                    }
                    QLabel { color: #e0e0e0; }
                    QLineEdit { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 2px 6px; }
                    QCheckBox { color: #e0e0e0; }
                    QPushButton { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 4px 8px; }
                    """
                )
            except Exception:
                pass
            v = QVBoxLayout(panel)
            v.setContentsMargins(8, 6, 8, 6)
            v.setSpacing(6)

            row_by = QVBoxLayout()
            row_by.addWidget(QLabel("Columns (comma-separated)"))
            self._edit_by = QLineEdit(
                ", ".join(self.get_property("by")) if isinstance(self.get_property("by"), list) else str(self.get_property("by") or "")
            )
            row_by.addWidget(self._edit_by)
            v.addLayout(row_by)

            row_opts = QHBoxLayout()
            self._chk_asc = QCheckBox("Ascending")
            try:
                self._chk_asc.setChecked(bool(self.get_property("ascending")))
            except Exception:
                pass
            self._chk_num = QCheckBox("Numeric")
            try:
                self._chk_num.setChecked(bool(self.get_property("numeric")))
            except Exception:
                pass
            row_opts.addWidget(self._chk_asc)
            row_opts.addStretch(1)
            row_opts.addWidget(self._chk_num)
            v.addLayout(row_opts)

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
            self._edit_by.textChanged.connect(self._on_by_changed)
            self._chk_asc.toggled.connect(self._on_asc_toggled)
            self._chk_num.toggled.connect(self._on_num_toggled)
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
    def _on_by_changed(self, text: str) -> None:
        try:
            self.set_property("by", [s.strip() for s in str(text).split(",") if s.strip()])
            self._update_preview_from_last_input()
        except Exception:
            pass

    def _on_asc_toggled(self, enabled: bool) -> None:
        try:
            self.set_property("ascending", bool(enabled))
            self._update_preview_from_last_input()
        except Exception:
            pass

    def _on_num_toggled(self, enabled: bool) -> None:
        try:
            self.set_property("numeric", bool(enabled))
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

    def _by_keys(self) -> List[str]:
        by = self.get_property("by")
        if isinstance(by, str):
            by = [s.strip() for s in by.split(",") if s.strip()]
        if not isinstance(by, list):
            by = []
        return [str(s) for s in by]

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not inputs or "data" not in inputs:
            raise ValueError("No input data provided")
        rows = _to_rows(inputs["data"])  # list[dict]
        by = self._by_keys()
        ascending = bool(self.get_property("ascending"))
        numeric = bool(self.get_property("numeric"))

        if not by:
            return {"data": rows}

        def key_func(r: Dict[str, Any]):
            parts = []
            for k in by:
                v = r.get(k)
                if numeric:
                    ok, num = _coerce_number(v)
                    parts.append((0, num) if ok else (1, str(v)))
                else:
                    parts.append(str(v))
            return tuple(parts)

        try:
            sorted_rows = sorted(rows, key=key_func, reverse=not ascending)
        except Exception:
            # Fallback to string-only sort if mixed types cause errors
            def k2(r: Dict[str, Any]):
                return tuple(str(r.get(k)) for k in by)
            sorted_rows = sorted(rows, key=k2, reverse=not ascending)
        return {"data": sorted_rows}
