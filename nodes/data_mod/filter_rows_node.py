"""FilterRowsNode implementation."""

from .common import *  # noqa: F401,F403

class FilterRowsNode(BaseNode):
    """Filter rows based on a key/operator/value rule.

    Supported operators:
    - equals, not_equals
    - lt, lte, gt, gte (numeric when possible)
    - contains, not_contains (string containment)
    - startswith, endswith (string)
    - in, not_in (comma-separated values)
    """

    def __init__(self):
        super().__init__("filter_rows", "Filter Rows")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("data", "data")
        # Properties
        self.set_property("filter_key", "")
        self.set_property("operator", "equals")
        self.set_property("value", "")
        self.set_property("auto_refresh_preview", True)

        # Inline UI with table preview + right-side params panel (pattern from DataframeMergeNode)
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
        try:
            from PySide6.QtCore import Qt
        except Exception:
            Qt = None  # type: ignore

        # Node sizing similar to merge node
        self.width = 560
        self.height = 280
        try:
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)
            self.set_content_margins(0, 32, 0, 0)
        except Exception:
            pass

        # Table preview inside node
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

        # Floating params panel on the right
        self._params_proxy = None
        self._params_widget = None
        try:
            panel = QFrame()
            panel.setObjectName("NodeFilterParams")
            try:
                panel.setStyleSheet(
                    """
                    QFrame#NodeFilterParams {
                        background-color: #2b2b2b;
                        border: 1px solid #666666;
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

            # Column chooser
            row_key = QVBoxLayout()
            row_key.addWidget(QLabel("Column"))
            self._cmb_key = QComboBox()
            row_key.addWidget(self._cmb_key)
            v.addLayout(row_key)

            # Operator chooser
            row_op = QVBoxLayout()
            row_op.addWidget(QLabel("Operator"))
            self._cmb_op = QComboBox()
            try:
                self._cmb_op.addItems([
                    "equals","not_equals","lt","lte","gt","gte",
                    "contains","not_contains","startswith","endswith","in","not_in"
                ])  # type: ignore[attr-defined]
                cur_op = str(self.get_property("operator") or "equals")
                idx = self._cmb_op.findText(cur_op) if hasattr(self._cmb_op, 'findText') else -1
                if idx >= 0:
                    self._cmb_op.setCurrentIndex(idx)
            except Exception:
                pass
            row_op.addWidget(self._cmb_op)
            v.addLayout(row_op)

            # Value edit
            row_val = QVBoxLayout()
            row_val.addWidget(QLabel("Value"))
            self._edit_val = QLineEdit(str(self.get_property("value") or ""))
            row_val.addWidget(self._edit_val)
            v.addLayout(row_val)

            # Buttons
            btns = QHBoxLayout()
            self._btn_refresh = QPushButton("Refresh")
            btns.addStretch(1)
            btns.addWidget(self._btn_refresh)
            v.addLayout(btns)

            # Proxy and position
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

            # Wire up interactions
            self._cmb_key.currentTextChanged.connect(self._on_key_changed)  # type: ignore[attr-defined]
            self._cmb_op.currentTextChanged.connect(self._on_op_changed)  # type: ignore[attr-defined]
            self._edit_val.textChanged.connect(self._on_value_changed)
            self._btn_refresh.clicked.connect(self._on_refresh_clicked)
        except Exception:
            self._params_proxy = None
            self._params_widget = None

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

    def _extract_columns_from_data(self, data: Any) -> List[str]:
        rows = _to_rows(data)
        keys: set[str] = set()
        for r in rows[:100]:
            try:
                for k in r.keys():
                    keys.add(str(k))
            except Exception:
                pass
        return sorted(keys)

    def _populate_keys_from_last_input(self) -> None:
        try:
            data = self.properties.get("last_input_data")
            if data is None:
                res = self.properties.get("last_result")
                if isinstance(res, dict) and "data" in res:
                    data = res["data"]
            cols = self._extract_columns_from_data(data)
            if hasattr(self, "_cmb_key") and self._cmb_key is not None:
                try:
                    self._cmb_key.blockSignals(True)
                    self._cmb_key.clear()
                    for c in cols:
                        self._cmb_key.addItem(c)
                    # Set current from property if exists
                    cur = str(self.get_property("filter_key") or "")
                    if cur:
                        idx = self._cmb_key.findText(cur) if hasattr(self._cmb_key, 'findText') else -1
                        if idx >= 0:
                            self._cmb_key.setCurrentIndex(idx)
                    self._cmb_key.blockSignals(False)
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
            # Prefer last_result (to reflect latest filtering) else last input
            res = self.properties.get("last_result")
            if isinstance(res, dict) and "data" in res:
                self._set_table_data(res["data"])
                return
            data = self.properties.get("last_input_data")
            if data is None:
                res2 = self.properties.get("last_input_results")
                if res2 is not None:
                    data = res2
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

    # --- UI callbacks ---
    def _on_key_changed(self, text: str) -> None:
        try:
            self.set_property("filter_key", str(text))
            self._update_preview_from_last_input()
        except Exception:
            pass

    def _on_op_changed(self, text: str) -> None:
        try:
            self.set_property("operator", str(text))
            self._update_preview_from_last_input()
        except Exception:
            pass

    def _on_value_changed(self, text: str) -> None:
        try:
            self.set_property("value", str(text))
            self._update_preview_from_last_input()
        except Exception:
            pass

    def _on_refresh_clicked(self) -> None:
        try:
            self._populate_keys_from_last_input()
            self._update_preview_from_last_input()
            try:
                if hasattr(self, 'rerun_requested'):
                    self.rerun_requested.emit(self)
            except Exception:
                pass
        except Exception:
            pass

    # Live update hook to keep preview synced
    def on_result(self, result: object) -> None:  # pragma: no cover - UI update hook
        try:
            if bool(self.get_property("auto_refresh_preview")):
                self._populate_keys_from_last_input()
                self._update_preview_from_last_input()
            try:
                self._update_content_geometry(force=False)
                self.update()
            except Exception:
                pass
        except Exception:
            pass
        super().on_result(result)

    def _match(self, cell: Any, op: str, val_str: str) -> bool:
        op = (op or "").lower().strip()
        # Prepare list for in/not_in
        if op in {"in", "not_in"}:
            choices = [s.strip() for s in str(val_str).split(",")]
            return (str(cell) in choices) if op == "in" else (str(cell) not in choices)

        # Attempt numeric compare
        c_ok, c_num = _coerce_number(cell)
        v_ok, v_num = _coerce_number(val_str)
        if op in {"lt", "lte", "gt", "gte"} and c_ok and v_ok:
            if op == "lt":
                return c_num < v_num
            if op == "lte":
                return c_num <= v_num
            if op == "gt":
                return c_num > v_num
            return c_num >= v_num

        # String/strict compares
        if op == "equals":
            return str(cell) == str(val_str)
        if op == "not_equals":
            return str(cell) != str(val_str)
        if op == "contains":
            return str(val_str) in str(cell)
        if op == "not_contains":
            return str(val_str) not in str(cell)
        if op == "startswith":
            return str(cell).startswith(str(val_str))
        if op == "endswith":
            return str(cell).endswith(str(val_str))
        # Unknown operator -> default False to be safe
        return False

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not inputs or "data" not in inputs:
            raise ValueError("No input data provided")
        key = (self.get_property("filter_key") or "").strip()
        op = (self.get_property("operator") or "equals").strip()
        val = self.get_property("value")
        if not key:
            return {"data": _to_rows(inputs["data"]) }
        rows = _to_rows(inputs["data"])  # list[dict]
        out = [r for r in rows if self._match(r.get(key), op, str(val))]
        return {"data": out}
