"""DropDuplicatesNode implementation."""

from .common import *  # noqa: F401,F403

class DropDuplicatesNode(BaseNode):
    """Drop duplicate rows, optionally using a subset of columns.

    Properties: subset (list[str] or comma-separated str), keep (first|last)
    """

    def __init__(self):
        super().__init__("drop_duplicates", "Drop Duplicates")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("data", "data")
        self.set_property("subset", [])
        self.set_property("keep", "first")  # or "last"
        self.set_property("auto_refresh_preview", True)

        # Inline UI with table preview + right-side params panel (same pattern as merge/sort nodes)
        from PySide6.QtWidgets import (
            QTableWidget,
            QGraphicsProxyWidget,
            QWidget,
            QVBoxLayout,
            QHBoxLayout,
            QLineEdit,
            QLabel,
            QComboBox,
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

        # Table preview
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
            panel.setObjectName("NodeDropDupParams")
            try:
                panel.setStyleSheet(
                    """
                    QFrame#NodeDropDupParams {
                        background-color: #2b2b2b;
                        border: 1px solid #666;
                        border-radius: 6px;
                    }
                    QLabel { color: #e0e0e0; }
                    QLineEdit { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 2px 6px; }
                    QComboBox { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 2px 6px; }
                    QPushButton { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 4px 8px; }
                    """
                )
            except Exception:
                pass
            v = QVBoxLayout(panel)
            v.setContentsMargins(8, 6, 8, 6)
            v.setSpacing(6)

            # Subset columns
            row_subset = QVBoxLayout()
            row_subset.addWidget(QLabel("Columns (comma-separated)"))
            subset_val = self.get_property("subset")
            subset_str = ", ".join(subset_val) if isinstance(subset_val, list) else str(subset_val or "")
            self._edit_subset = QLineEdit(subset_str)
            row_subset.addWidget(self._edit_subset)
            v.addLayout(row_subset)

            # Keep option
            row_keep = QHBoxLayout()
            row_keep.addWidget(QLabel("Keep"))
            self._cmb_keep = QComboBox()
            try:
                self._cmb_keep.addItems(["first", "last"])
                cur = str(self.get_property("keep") or "first").lower()
                self._cmb_keep.setCurrentText(cur if cur in ("first", "last") else "first")
            except Exception:
                pass
            row_keep.addWidget(self._cmb_keep)
            row_keep.addStretch(1)
            v.addLayout(row_keep)

            # Refresh
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
            self._edit_subset.textChanged.connect(self._on_subset_changed)
            self._cmb_keep.currentTextChanged.connect(self._on_keep_changed)
            self._btn_refresh.clicked.connect(self._on_refresh_clicked)
        except Exception:
            self._params_proxy = None
            self._params_widget = None

    def _subset_keys(self) -> List[str]:
        subset = self.get_property("subset")
        if isinstance(subset, str):
            subset = [s.strip() for s in subset.split(",") if s.strip()]
        if not isinstance(subset, list):
            subset = []
        return [str(s) for s in subset]

    def _make_hashable(self, value: Any):
        try:
            hash(value)
            return value
        except Exception:
            pass
        # Coerce common unhashable types
        try:
            if isinstance(value, (list, tuple)):
                return tuple(self._make_hashable(v) for v in value)
            if isinstance(value, dict):
                return tuple(sorted((str(k), self._make_hashable(v)) for k, v in value.items()))
            # Fallback to string representation
            return json.dumps(value, sort_keys=True, default=str)
        except Exception:
            return str(value)

    def _ensure_default_subset_from_rows(self, rows: List[Dict[str, Any]]) -> None:
        try:
            current = self._subset_keys()
            if not current and rows:
                headers = list(rows[0].keys())
                if headers:
                    default_subset = [str(headers[0])]
                    self.set_property("subset", default_subset)
                    try:
                        if hasattr(self, "_edit_subset") and self._edit_subset is not None:
                            self._edit_subset.blockSignals(True)
                            self._edit_subset.setText(", ".join(default_subset))
                            self._edit_subset.blockSignals(False)
                    except Exception:
                        pass
        except Exception:
            pass

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not inputs or "data" not in inputs:
            raise ValueError("No input data provided")
        rows = _to_rows(inputs["data"])  # list[dict]
        # Ensure default subset (first column) when not specified
        self._ensure_default_subset_from_rows(rows)
        subset = self._subset_keys()
        keep = (self.get_property("keep") or "first").lower()
        seen = set()
        out: List[Dict[str, Any]] = []

        def key_of(r: Dict[str, Any]):
            if subset:
                return tuple(self._make_hashable(r.get(k)) for k in subset)
            # whole-row tuple (sorted by key to stabilize)
            items = sorted(r.items())
            return tuple((k, self._make_hashable(v)) for k, v in items)

        if keep == "last":
            # Process reversed and then reverse back
            tmp: List[Dict[str, Any]] = []
            for r in reversed(rows):
                k = key_of(r)
                if k in seen:
                    continue
                seen.add(k)
                tmp.append(r)
            out = list(reversed(tmp))
        else:  # first
            for r in rows:
                k = key_of(r)
                if k in seen:
                    continue
                seen.add(k)
                out.append(r)
        return {"data": out}

    # --- Inline UI helpers ---
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
                rows = _to_rows(res["data"])  # type: ignore[arg-type]
                self._ensure_default_subset_from_rows(rows)
                self._set_table_data(rows)
                return
            data = self.properties.get("last_input_data")
            if data is None:
                data = self.properties.get("last_input_results")
            if data is None:
                self._set_table_data([])
                return
            rows = _to_rows(data)
            self._ensure_default_subset_from_rows(rows)
            try:
                tmp = self.execute({"data": rows})
                self._set_table_data(tmp.get("data"))
            except Exception:
                self._set_table_data(rows)
        except Exception:
            pass

    # UI callbacks
    def _on_subset_changed(self, text: str) -> None:
        try:
            self.set_property("subset", [s.strip() for s in str(text).split(",") if s.strip()])
            self._update_preview_from_last_input()
        except Exception:
            pass

    def _on_keep_changed(self, keep: str) -> None:
        try:
            self.set_property("keep", str(keep).lower().strip() or "first")
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
