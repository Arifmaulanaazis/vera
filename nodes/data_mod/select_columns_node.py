"""SelectColumnsNode implementation."""

from .common import *  # noqa: F401,F403

class SelectColumnsNode(BaseNode):
    """Keep only selected columns from a table-like dataset.

    Input: data (list[dict] or DataFrame)
    Output: data (list[dict])
    """

    def __init__(self):
        super().__init__("select_columns", "Select Columns")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("data", "data")
        # Properties
        self.set_property("columns", [])  # list[str]
        self.set_property("drop_missing", False)  # drop rows missing any selected column
        # UI/behavioral properties
        self.set_property("auto_refresh_schema", True)
        self.set_property("pin_schema", False)
        self.set_property("available_columns", [])  # cached discovered columns

        # Inline UI: table preview on the left and checkbox panel on the right
        try:
            from core.nodes import BaseNode as _BaseNode
            if getattr(_BaseNode, "_lightweight_construction", False):
                self._table = None
                self._schema_proxy = None
                self._schema_widget = None
                self._column_checkboxes = {}
                return
        except Exception:
            pass

        from PySide6.QtWidgets import (
            QTableWidget,
            QGraphicsProxyWidget,
            QWidget,
            QVBoxLayout,
            QHBoxLayout,
            QLineEdit,
            QCheckBox,
            QScrollArea,
            QFrame,
            QPushButton,
        )
        try:
            from PySide6.QtCore import Qt
        except Exception:
            Qt = None  # type: ignore

        # Match TableView margins, but widen for a right panel
        self.width = 560
        self.height = 280
        self.setMinimumSize(self.width, self.height)
        self.setMaximumSize(self.width, self.height)
        try:
            self.set_content_margins(0, 32, 0, 0)
        except Exception:
            pass

        # Table fills the node body (isolated try, never nuke UI if later parts fail)
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

        # Floating schema panel to the right (outside node body), like error/progress panels
        self._schema_proxy = None
        self._schema_widget = None
        try:
            schema_container = QFrame()
            schema_container.setObjectName("NodeSchemaPanel")
            try:
                schema_container.setStyleSheet(
                    """
                    QFrame#NodeSchemaPanel {
                        background-color: #2b2b2b;
                        border: 1px solid #666666;
                        border-radius: 6px;
                    }
                    QLineEdit { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 2px 6px; }
                    QCheckBox { color: #e0e0e0; }
                    """
                )
            except Exception:
                pass
            v = QVBoxLayout(schema_container)
            v.setContentsMargins(8, 6, 8, 6)
            v.setSpacing(4)

            # Top row: Select All and Search (no title)
            top = QHBoxLayout()
            self._check_all = QCheckBox("Select All")
            self._check_all.stateChanged.connect(self._on_select_all_changed)
            self._search = QLineEdit()
            self._search.setPlaceholderText("Search columns…")
            self._search.textChanged.connect(self._on_search_changed)
            top.addWidget(self._check_all)
            top.addStretch(1)
            top.addWidget(self._search)
            v.addLayout(top)

            # Scrollable checkbox list
            self._scroll = QScrollArea()
            self._scroll.setWidgetResizable(True)
            self._scroll.setFrameShape(QFrame.NoFrame)
            try:
                if Qt is not None:
                    self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                else:
                    self._scroll.setHorizontalScrollBarPolicy(1)  # fallback
            except Exception:
                pass
            self._check_container = QWidget()
            self._check_layout = QVBoxLayout(self._check_container)
            self._check_layout.setContentsMargins(4, 4, 4, 4)
            self._check_layout.setSpacing(2)
            self._check_layout.addStretch(1)
            self._scroll.setWidget(self._check_container)
            v.addWidget(self._scroll, 1)

            # Action buttons row (Refresh downstream)
            btns = QHBoxLayout()
            self._btn_refresh = QPushButton("Refresh")
            self._btn_refresh.clicked.connect(self._on_refresh_clicked)
            btns.addStretch(1)
            btns.addWidget(self._btn_refresh)
            v.addLayout(btns)

            # Create proxy widget and keep reference to position to the right of node
            self._schema_widget = schema_container
            self._schema_proxy = QGraphicsProxyWidget(self)
            self._schema_proxy.setWidget(schema_container)
            try:
                self._schema_proxy.setZValue(8)
                self._schema_proxy.setVisible(True)
            except Exception:
                pass
            try:
                # Force initial geometry so the floating panel appears immediately
                self._update_content_geometry(force=True)
                self.update()
            except Exception:
                pass
        except Exception:
            self._schema_proxy = None
            self._schema_widget = None

        # Internal state for checkboxes (always initialize)
        try:
            from PySide6.QtWidgets import QCheckBox as _QCheckBox
            self._column_checkboxes: dict[str, _QCheckBox] = {}
        except Exception:
            self._column_checkboxes = {}

        # Initial populate from cached schema if any
        try:
            cached_cols = self.get_property("available_columns") or []
            if cached_cols:
                self._rebuild_checkboxes([str(c) for c in cached_cols])
        except Exception:
            pass

    # --- Nested data helpers ---
    def _flatten_keys(self, value: Any, prefix: str = "", depth: int = 0, max_depth: int = 2) -> set[str]:
        keys: set[str] = set()
        if depth > max_depth:
            return keys
        try:
            # Support JSON strings embedded in cells: try to parse and recurse
            if isinstance(value, str):
                s = value.strip()
                if s.startswith("{") or s.startswith("["):
                    try:
                        obj = json.loads(s)
                        return self._flatten_keys(obj, prefix, depth, max_depth)
                    except Exception:
                        pass
            if isinstance(value, dict):
                for k, v in value.items():
                    name = f"{prefix}.{k}" if prefix else str(k)
                    keys.add(name)
                    # Recurse into dicts/lists for nested keys
                    if isinstance(v, dict):
                        keys |= self._flatten_keys(v, name, depth + 1, max_depth)
                    elif isinstance(v, list) and v:
                        # Look into first few list elements to infer schema
                        for item in v[:3]:
                            if isinstance(item, dict):
                                keys |= self._flatten_keys(item, name, depth + 1, max_depth)
                            else:
                                # Treat list of primitives as a scalar column
                                keys.add(name)
                                break
            elif isinstance(value, list) and value:
                # List at root: infer keys from first few elements
                for item in value[:3]:
                    keys |= self._flatten_keys(item, prefix, depth + 1, max_depth)
        except Exception:
            pass
        return keys

    def _get_value_by_path(self, data: Any, path: str) -> Any:
        try:
            parts = [p for p in str(path).split(".") if p]
            cur = data
            for p in parts:
                if isinstance(cur, dict):
                    if p in cur:
                        cur = cur[p]
                    else:
                        return None
                elif isinstance(cur, list):
                    # If list, try to take the first element for nested access
                    if not cur:
                        return None
                    first = cur[0]
                    if isinstance(first, dict):
                        cur = first
                        # Re-process current part at same level on dict
                        if p in cur:
                            cur = cur[p]
                        else:
                            return None
                    else:
                        # List of primitives -> return as-is for terminal path
                        return cur
                else:
                    return None
            return cur
        except Exception:
            return None

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not inputs or "data" not in inputs:
            raise ValueError("No input data provided")
        # Accept list[str] or comma-separated string
        raw_cols = self.get_property("columns")
        if isinstance(raw_cols, str):
            columns = [s.strip() for s in raw_cols.split(",") if s.strip()]
        elif isinstance(raw_cols, list):
            columns = [str(c) for c in raw_cols]
        else:
            columns = []
        drop_missing = bool(self.get_property("drop_missing"))
        rows = _to_rows(inputs["data"])  # list[dict]
        if not columns:
            return {"data": rows}

        selected: List[Dict[str, Any]] = []
        for r in rows:
            row_out: Dict[str, Any] = {}
            missing = False
            for col in columns:
                val = self._get_value_by_path(r, col)
                if val is None and drop_missing:
                    missing = True
                    break
                row_out[col] = val
            if not (drop_missing and missing):
                selected.append(row_out)
        return {"data": selected}

    # --- Inline UI helpers (GUI thread only) ---
    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        # Hide default painted labels inside node body
        return []

    def _update_content_geometry(self, force: bool = False) -> None:  # type: ignore[override]
        # Let base update the content area first
        try:
            super()._update_content_geometry(force)
        except Exception:
            pass
        # Then position our schema panel to the right with same height; progress/error remain below node
        try:
            # Right-side floating schema panel: align top, match node height, place with small gap
            if getattr(self, "_schema_proxy", None) is not None and getattr(self, "_schema_widget", None) is not None:
                try:
                    # Match height with node body
                    try:
                        self._schema_widget.setFixedHeight(int(self.height))
                    except Exception:
                        pass
                    # Reasonable width relative to node
                    panel_w = int(max(120, min(220, self.width * 0.3)))
                    self._schema_widget.setFixedWidth(panel_w)
                    self._schema_widget.adjustSize()
                except Exception:
                    pass
                # Position to the immediate right with margin
                x_offset = float(self.width) + 12.0
                self._schema_proxy.setPos(x_offset, 0.0)
                # Shift output ports to the right edge of the floating panel
                try:
                    def _anchor_override() -> float:
                        return float(self.width) + 12.0 + float(panel_w)
                    # Bind method dynamically on instance
                    object.__setattr__(self, "_get_output_port_anchor_x", _anchor_override)  # type: ignore[arg-type]
                    # Reposition ports now that anchor changed
                    self._update_port_positions()
                except Exception:
                    pass

            # Progress panel remains below node (not below schema)
            try:
                if getattr(self, "_progress_proxy", None) is not None and self._progress_proxy.isVisible():
                    try:
                        if getattr(self, "_progress_widget", None) is not None:
                            self._progress_widget.setFixedWidth(int(self.width))
                            self._progress_widget.adjustSize()
                    except Exception:
                        pass
                    self._progress_proxy.setPos(0.0, float(self.height) + 6.0)
            except Exception:
                pass
            # Error panel below progress panel
            try:
                if getattr(self, "_error_proxy", None) is not None and self._error_proxy.isVisible():
                    try:
                        if getattr(self, "_error_widget", None) is not None:
                            self._error_widget.setFixedWidth(int(self.width))
                            self._error_widget.adjustSize()
                    except Exception:
                        pass
                    # Estimate stacked y under progress
                    y_err = float(self.height) + 6.0
                    try:
                        if getattr(self, "_progress_proxy", None) is not None and self._progress_proxy.isVisible():
                            ph = self._progress_proxy.size().height() if hasattr(self._progress_proxy, 'size') else 22
                            y_err += float(max(18, ph + 4))
                    except Exception:
                        y_err += 22.0
                    self._error_proxy.setPos(0.0, y_err)
            except Exception:
                pass
        except Exception:
            pass
    def _set_table_data(self, data: Any) -> None:
        """Populate the preview table with up to 100 rows.
        Adopted from TableViewNode for robust normalization.
        """
        try:
            from PySide6.QtWidgets import QTableWidgetItem
        except Exception:
            return
        if self._table is None:
            return
        # Temporarily disable painting for faster updates and to avoid re-entrancy
        try:
            self._table.setUpdatesEnabled(False)
            self._table.setSortingEnabled(False)
        except Exception:
            pass
        # Normalize to list[dict]
        rows: list[dict]
        if data is None:
            rows = []
        elif isinstance(data, list) and (len(data) == 0 or isinstance(data[0], dict)):
            rows = data
        else:
            # Try pandas DataFrame
            try:
                import pandas as pd
                if isinstance(data, pd.DataFrame):
                    rows = data.to_dict(orient="records")
                else:
                    rows = [
                        {"value": str(item)} for item in (data if isinstance(data, list) else [data])
                    ]
            except Exception:
                rows = [
                    {"value": str(data)}
                ]
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
        for r, row in enumerate(rows):
            for c, key in enumerate(headers):
                val = row.get(key, "")
                item = QTableWidgetItem(str(val))
                self._table.setItem(r, c, item)
        try:
            self._table.setSortingEnabled(True)
            self._table.setUpdatesEnabled(True)
        except Exception:
            pass

    def _set_table_data_selected_only(self, data: Any, columns: List[str]) -> None:
        """Show only selected columns in the preview for clarity."""
        # Apply selection on rows then show
        rows = _to_rows(data)
        if not columns:
            self._set_table_data(rows)
            return
        filtered: List[Dict[str, Any]] = []
        for r in rows:
            filtered.append({col: self._get_value_by_path(r, col) for col in columns})
        self._set_table_data(filtered)

    def _extract_columns_from_data(self, data: Any) -> List[str]:
        rows = _to_rows(data)
        keys: set[str] = set()
        for r in rows[:100]:
            try:
                # Top-level keys
                for k in r.keys():
                    keys.add(str(k))
                    # Inspect nested structures for additional selectable paths
                    v = r.get(k)
                    keys |= self._flatten_keys(v, str(k), 0, 2)
            except Exception:
                pass
        cols = sorted([str(k) for k in keys])
        return cols

    def _rebuild_checkboxes(self, columns: List[str]) -> None:
        try:
            from PySide6.QtWidgets import QCheckBox
        except Exception:
            return
        if not hasattr(self, "_check_layout") or self._check_layout is None:
            return
        # Clear existing (except the stretch at the end)
        while self._check_layout.count() > 1:
            item = self._check_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._column_checkboxes.clear()

        # Current selected set to keep state where possible
        current_selected = set(str(c) for c in (self.get_property("columns") or []))
        for col in columns:
            cb = QCheckBox(col)
            cb.setChecked(col in current_selected)
            cb.toggled.connect(self._on_column_toggled)
            self._check_layout.insertWidget(self._check_layout.count() - 1, cb)
            self._column_checkboxes[col] = cb

        self.set_property("available_columns", columns)
        self._update_select_all_state()
        # Apply search filter if present
        self._on_search_changed(self._search.text() if hasattr(self, "_search") else "")

    def _update_select_all_state(self) -> None:
        try:
            total = len(self._column_checkboxes)
            if total == 0:
                self._check_all.setCheckState(0)  # Qt.Unchecked
                return
            checked = sum(1 for cb in self._column_checkboxes.values() if cb.isChecked())
            if checked == 0:
                self._check_all.setCheckState(0)
            elif checked == total:
                self._check_all.setCheckState(2)  # Qt.Checked
            else:
                self._check_all.setCheckState(1)  # Qt.PartiallyChecked
        except Exception:
            pass

    def _get_selected_columns(self) -> List[str]:
        selected: List[str] = []
        for name, cb in self._column_checkboxes.items():
            try:
                if cb.isChecked():
                    selected.append(name)
            except Exception:
                pass
        return selected

    def _refresh_schema_from_last_input(self) -> None:
        try:
            # Respect pinning: if pinned and we already have a schema, don't change it
            if bool(self.get_property("pin_schema")):
                existing = self.get_property("available_columns") or []
                if isinstance(existing, list) and len(existing) > 0:
                    return
            data = self.properties.get("last_input_data")
            # Fallbacks for nodes that output under different keys
            if data is None:
                data = self.properties.get("last_input_results")
            if data is None:
                # Some managers may only store last_result; inspect common payload keys
                res = self.properties.get("last_result")
                if isinstance(res, dict):
                    if "data" in res:
                        data = res.get("data")
                    elif "results" in res:
                        data = res.get("results")
            if data is None:
                return
            cols = self._extract_columns_from_data(data)
            if cols:
                self._rebuild_checkboxes(cols)
        except Exception:
            pass

    def _update_preview_from_last_input(self) -> None:
        try:
            data = self.properties.get("last_input_data")
            if data is None:
                # Fallback: show last result if any
                res = self.properties.get("last_result")
                if isinstance(res, dict):
                    if "data" in res:
                        data = res["data"]
                    elif "results" in res:
                        data = res["results"]
            if data is None:
                # Another fallback for managers that store last_input_results
                data = self.properties.get("last_input_results")
            # As a final fallback, try first non-empty key in last_result dict
            if data is None:
                res2 = self.properties.get("last_result")
                if isinstance(res2, dict):
                    for k in ("results", "records", "table", "preview", "preview_data"):
                        if k in res2 and res2[k] is not None:
                            data = res2[k]
                            break
            cols = self.get_property("columns") or []
            if not isinstance(cols, list):
                cols = [str(c).strip() for c in str(cols).split(",") if str(c).strip()]
            self._set_table_data_selected_only(data, [str(c) for c in cols])
        except Exception:
            pass

    # --- UI callbacks ---
    def _on_select_all_changed(self, state: int) -> None:
        try:
            # 0: unchecked, 1: partial (treat as unchecked->checked), 2: checked
            check = state == 2 or (state == 1 and any(not cb.isChecked() for cb in self._column_checkboxes.values()))
            for cb in self._column_checkboxes.values():
                cb.blockSignals(True)
                cb.setChecked(check)
                cb.blockSignals(False)
            # Persist selection
            self.set_property("columns", self._get_selected_columns())
            self._update_preview_from_last_input()
            self._update_select_all_state()
            # Trigger downstream partial re-run so connected nodes get updated
            try:
                if hasattr(self, 'rerun_requested'):
                    self.rerun_requested.emit(self)
            except Exception:
                pass
        except Exception:
            pass

    def _on_search_changed(self, text: str) -> None:
        try:
            q = (text or "").lower().strip()
            for name, cb in self._column_checkboxes.items():
                try:
                    match = q in name.lower()
                    cb.setVisible(match)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_column_toggled(self, checked: bool) -> None:
        try:
            self.set_property("columns", self._get_selected_columns())
            self._update_preview_from_last_input()
            self._update_select_all_state()
            # Trigger downstream partial re-run so connected nodes get updated
            try:
                if hasattr(self, 'rerun_requested'):
                    self.rerun_requested.emit(self)
            except Exception:
                pass
        except Exception:
            pass

    def _on_auto_refresh_toggled(self, enabled: bool) -> None:
        try:
            self.set_property("auto_refresh_schema", bool(enabled))
        except Exception:
            pass

    def _on_refresh_clicked(self) -> None:
        self._refresh_schema_from_last_input()
        self._update_preview_from_last_input()
        # Trigger downstream partial re-run to propagate selected data update
        try:
            if hasattr(self, 'rerun_requested'):
                self.rerun_requested.emit(self)
        except Exception:
            pass

    def _on_pin_schema_toggled(self, enabled: bool) -> None:
        try:
            self.set_property("pin_schema", bool(enabled))
        except Exception:
            pass

    def _on_clear_clicked(self) -> None:
        try:
            self.set_property("available_columns", [])
            # Rebuild empty to clear UI
            self._rebuild_checkboxes([])
        except Exception:
            pass

    # --- Live update hook ---
    def on_result(self, result: object) -> None:  # pragma: no cover - UI update hook
        try:
            if bool(self.get_property("auto_refresh_schema")):
                self._refresh_schema_from_last_input()
            self._update_preview_from_last_input()
            try:
                # Ensure floating panels are positioned and visible after updates
                self._update_content_geometry(force=False)
                self.update()
            except Exception:
                pass
        except Exception:
            pass
        # Store last_result and trigger repaint
        super().on_result(result)
