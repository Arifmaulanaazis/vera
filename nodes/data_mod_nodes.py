"""
Data modification nodes for table-like data (list of dicts or pandas.DataFrame).

Nodes included:
- SelectColumnsNode: keep only selected columns
- FilterRowsNode: filter rows by key/operator/value
- SliceRowsNode: slice rows by start/end/step
- DropDuplicatesNode: remove duplicate rows
- SortRowsNode: sort rows by one or more keys
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import json

from core.nodes import BaseNode
from utils.logging_utils import get_logger


def _to_rows(data: Any) -> List[Dict[str, Any]]:
    """Normalize incoming data to list[dict].

    - If pandas DataFrame, convert to records
    - If list of dicts, return as-is
    - If dict, wrap into one-row list
    - Otherwise, try best-effort string conversion
    """
    try:
        import pandas as pd  # type: ignore
        if isinstance(data, pd.DataFrame):
            # MultiIndex produces tuple keys in to_dict; flatten to plain columns first
            if isinstance(data.index, pd.MultiIndex):
                data = data.reset_index()
            return data.to_dict(orient="records")
    except Exception:
        pass

    if data is None:
        return []
    if isinstance(data, list):
        if len(data) == 0 or (len(data) > 0 and isinstance(data[0], dict)):
            return data  # type: ignore[return-value]
        # list of primitives -> try to parse JSON strings into dicts when possible
        try:
            looks_like_json = all(isinstance(x, str) and str(x).lstrip().startswith(("{", "[")) for x in data[:5])
        except Exception:
            looks_like_json = False
        if looks_like_json:
            parsed: List[Dict[str, Any]] = []
            json_parsed_any = False
            for x in data:
                try:
                    obj = json.loads(str(x))
                    json_parsed_any = True
                    if isinstance(obj, dict):
                        parsed.append(obj)
                    elif isinstance(obj, list):
                        # Flatten lists of dicts; if primitives, keep as value
                        added = False
                        for it in obj:
                            if isinstance(it, dict):
                                parsed.append(it)
                                added = True
                        if not added:
                            parsed.append({"value": obj})
                    else:
                        parsed.append({"value": obj})
                except Exception:
                    parsed.append({"value": x})
            if json_parsed_any and len(parsed) > 0 and isinstance(parsed[0], dict):
                return parsed
        # fallback: wrap primitives
        return [{"value": x} for x in data]
    if isinstance(data, dict):
        return [data]
    # fallback
    return [{"value": data}]


def _coerce_number(value: Any) -> Tuple[bool, float]:
    """Try to coerce value to float. Return (success, number).

    On failure returns (False, nan) — never 0.0 — so callers can
    distinguish a coercion error from a legitimate zero value.
    """
    try:
        if isinstance(value, bool):  # avoid True/False as 1/0 surprises
            return False, float("nan")
        if isinstance(value, (int, float)):
            return True, float(value)
        if isinstance(value, str):
            v = value.strip()
            if v.lower() in {"nan", "inf", "-inf"}:
                return False, float("nan")
            return True, float(v)
        return False, float("nan")
    except Exception:
        return False, float("nan")


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



class DataframeMergeNode(BaseNode):
    """Merge two table-like datasets (list[dict] or pandas.DataFrame).

    Inputs: left (data), right (data)
    Output: data (list[dict])

    Properties:
    - how: one of [inner, left, right, outer]
    - left_on: list[str] or comma-separated str of key columns on left
    - right_on: list[str] or comma-separated str of key columns on right (defaults to left_on)
    - auto_detect_keys: bool (infer common columns if keys not provided)
    - suffix_left: str (suffix for overlapping non-key columns from left)
    - suffix_right: str (suffix for overlapping non-key columns from right)
    - auto_refresh_preview: bool (update preview when inputs/properties change)
    """

    def __init__(self):
        super().__init__("merge_dataframes", "Dataframe Merge")
        self.logger = get_logger(__name__)
        self.add_input_port("left", "data")
        self.add_input_port("right", "data")
        self.add_output_port("data", "data")

        # Core merge properties
        self.set_property("how", "inner")  # inner | left | right | outer
        self.set_property("left_on", [])
        self.set_property("right_on", [])
        self.set_property("auto_detect_keys", True)
        self.set_property("suffix_left", "_x")
        self.set_property("suffix_right", "_y")
        self.set_property("auto_refresh_preview", True)
        # Behavior when no join keys can be determined or there are no common columns
        # Options: 'zip_by_index' (default) or 'concat_rows'
        self.set_property("no_keys_behavior", "zip_by_index")

        # Inline UI with table preview + right-side floating params panel
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
            QCheckBox,
            QFrame,
        )
        try:
            from PySide6.QtCore import Qt
        except Exception:
            Qt = None  # type: ignore

        # Size similar to SelectColumns but tuned for params on right
        self.width = 560
        self.height = 280
        self.setMinimumSize(self.width, self.height)
        self.setMaximumSize(self.width, self.height)
        try:
            self.set_content_margins(0, 32, 0, 0)
        except Exception:
            pass

        # Table preview in node body
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
            panel.setObjectName("NodeMergeParams")
            try:
                panel.setStyleSheet(
                    """
                    QFrame#NodeMergeParams {
                        background-color: #2b2b2b;
                        border: 1px solid #666666;
                        border-radius: 6px;
                    }
                    QLabel { color: #e0e0e0; }
                    QLineEdit { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 2px 6px; }
                    QCheckBox { color: #e0e0e0; }
                    QComboBox { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 2px 6px; }
                    QPushButton { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 4px 8px; }
                    """
                )
            except Exception:
                pass

            v = QVBoxLayout(panel)
            v.setContentsMargins(8, 6, 8, 6)
            v.setSpacing(6)

            # Join type
            row_how = QHBoxLayout()
            lbl_how = QLabel("Join type")
            self._cmb_how = QComboBox()
            try:
                self._cmb_how.addItems(["inner", "left", "right", "outer"])  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                current_how = str(self.get_property("how") or "inner")
                idx = self._cmb_how.findText(current_how) if hasattr(self._cmb_how, 'findText') else -1
                if idx >= 0:
                    self._cmb_how.setCurrentIndex(idx)
            except Exception:
                pass
            row_how.addWidget(lbl_how)
            row_how.addWidget(self._cmb_how)
            v.addLayout(row_how)

            # Keys (left/right)
            self._chk_auto = QCheckBox("Auto-detect keys")
            try:
                self._chk_auto.setChecked(bool(self.get_property("auto_detect_keys")))
            except Exception:
                pass
            v.addWidget(self._chk_auto)

            # No-keys behavior
            row_no_keys = QHBoxLayout()
            lbl_no_keys = QLabel("No-keys mode")
            self._cmb_no_keys = QComboBox()
            try:
                self._cmb_no_keys.addItems(["zip_by_index", "concat_rows"])  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                current_mode = str(self.get_property("no_keys_behavior") or "zip_by_index")
                idx = self._cmb_no_keys.findText(current_mode) if hasattr(self._cmb_no_keys, 'findText') else -1
                if idx >= 0:
                    self._cmb_no_keys.setCurrentIndex(idx)
            except Exception:
                pass
            row_no_keys.addWidget(lbl_no_keys)
            row_no_keys.addWidget(self._cmb_no_keys)
            v.addLayout(row_no_keys)

            row_left = QVBoxLayout()
            lbl_left = QLabel("Left keys (comma-separated)")
            self._edit_left = QLineEdit()
            try:
                left_val = self.get_property("left_on") or []
                if isinstance(left_val, list):
                    self._edit_left.setText(", ".join(str(x) for x in left_val))
                else:
                    self._edit_left.setText(str(left_val))
            except Exception:
                pass
            row_left.addWidget(lbl_left)
            row_left.addWidget(self._edit_left)
            v.addLayout(row_left)

            row_right = QVBoxLayout()
            lbl_right = QLabel("Right keys (comma-separated)")
            self._edit_right = QLineEdit()
            try:
                right_val = self.get_property("right_on") or []
                if isinstance(right_val, list):
                    self._edit_right.setText(", ".join(str(x) for x in right_val))
                else:
                    self._edit_right.setText(str(right_val))
            except Exception:
                pass
            row_right.addWidget(lbl_right)
            row_right.addWidget(self._edit_right)
            v.addLayout(row_right)

            # Suffixes
            row_suf = QHBoxLayout()
            self._edit_suf_l = QLineEdit(str(self.get_property("suffix_left") or "_x"))
            self._edit_suf_r = QLineEdit(str(self.get_property("suffix_right") or "_y"))
            row_suf.addWidget(QLabel("Suffix L"))
            row_suf.addWidget(self._edit_suf_l)
            row_suf.addWidget(QLabel("Suffix R"))
            row_suf.addWidget(self._edit_suf_r)
            v.addLayout(row_suf)

            # Buttons
            row_btns = QHBoxLayout()
            self._btn_detect = QPushButton("Detect now")
            self._btn_refresh = QPushButton("Refresh")
            row_btns.addWidget(self._btn_detect)
            row_btns.addStretch(1)
            row_btns.addWidget(self._btn_refresh)
            v.addLayout(row_btns)

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

            # Wire interactions
            try:
                self._cmb_how.currentTextChanged.connect(self._on_how_changed)  # type: ignore[attr-defined]
            except Exception:
                pass
            self._chk_auto.toggled.connect(self._on_auto_detect_toggled)
            self._edit_left.textChanged.connect(self._on_left_keys_changed)
            self._edit_right.textChanged.connect(self._on_right_keys_changed)
            self._edit_suf_l.textChanged.connect(self._on_suffix_changed)
            self._edit_suf_r.textChanged.connect(self._on_suffix_changed)
            self._btn_detect.clicked.connect(self._on_detect_clicked)
            self._btn_refresh.clicked.connect(self._on_refresh_clicked)

            # Respect auto mode
            try:
                auto = bool(self.get_property("auto_detect_keys"))
                self._edit_left.setEnabled(not auto)
                self._edit_right.setEnabled(not auto)
            except Exception:
                pass
            try:
                self._cmb_no_keys.currentTextChanged.connect(self._on_no_keys_mode_changed)  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception:
            self._params_proxy = None
            self._params_widget = None

    # --- Helpers ---
    def _parse_keys(self, value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            return [s.strip() for s in value.split(",") if s.strip()]
        return []

    def _rows_keyset(self, rows: List[Dict[str, Any]]) -> set[str]:
        keys: set[str] = set()
        for r in rows[:100]:
            try:
                keys |= set(str(k) for k in r.keys())
            except Exception:
                pass
        return keys

    def _infer_common_keys(self, left_rows: List[Dict[str, Any]], right_rows: List[Dict[str, Any]]) -> List[str]:
        """Heuristically infer a small set of join keys.

        Strategy:
        - Prefer well-known identifier columns (case-insensitive): inchikey, smiles, id, cid, name
        - If multiple exist, pick the first that appears unique-ish in both tables
        - Fallback to 'smiles' if present in both
        - Final fallback: first common column name
        """
        try:
            left_keys = self._rows_keyset(left_rows)
            right_keys = self._rows_keyset(right_rows)
            common = list(left_keys & right_keys)
            if not common:
                return []

            # Case-insensitive lookup maps
            common_lower_to_orig: Dict[str, str] = {name.lower(): name for name in common}

            priority = [
                "inchikey", "inchi_key", "inchi",  # InChI keys
                "smiles",
                "id", "_id", "idx", "index",
                "cid", "pubchem_cid",
                "name", "compound", "molid", "mol_id",
            ]

            def uniqueness_ratio(rows: List[Dict[str, Any]], key: str) -> float:
                try:
                    values = [r.get(key) for r in rows]
                    if not values:
                        return 0.0
                    uniq = len({v for v in values})
                    return uniq / max(1, len(values))
                except Exception:
                    return 0.0

            # Pick the best priority key present in both
            best_key: str | None = None
            best_score = -1.0
            for cand in priority:
                if cand.lower() in common_lower_to_orig:
                    orig = common_lower_to_orig[cand.lower()]
                    score = (uniqueness_ratio(left_rows, orig) + uniqueness_ratio(right_rows, orig)) / 2.0
                    # Favor presence strongly even if uniqueness is modest
                    score += 0.1
                    if score > best_score:
                        best_key = orig
                        best_score = score

            if best_key is not None:
                return [best_key]

            # Fallback: 'smiles' if exists
            if "smiles" in common_lower_to_orig:
                return [common_lower_to_orig["smiles"]]

            # Final fallback: first common
            return [sorted(common)[0]]
        except Exception:
            return []

    def _set_table_data(self, data: Any) -> None:
        try:
            from PySide6.QtWidgets import QTableWidgetItem
        except Exception:
            return
        if self._table is None:
            return
        try:
            self._table.setUpdatesEnabled(False)
            self._table.setSortingEnabled(False)
        except Exception:
            pass
        # Normalize to rows
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
                    rows = [
                        {"value": str(item)} for item in (data if isinstance(data, list) else [data])
                    ]
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
        for r, row in enumerate(rows):
            for c, key in enumerate(headers):
                val = row.get(key, "")
                try:
                    item = QTableWidgetItem(str(val))
                    self._table.setItem(r, c, item)
                except Exception:
                    pass
        try:
            self._table.setSortingEnabled(True)
            self._table.setUpdatesEnabled(True)
        except Exception:
            pass

    def _combine_rows(
        self,
        left_r: Dict[str, Any] | None,
        right_r: Dict[str, Any] | None,
        key_pairs: List[tuple[str, str]],
        overlap_non_keys: set[str],
        suffix_left: str,
        suffix_right: str,
    ) -> Dict[str, Any]:
        # Start with left row or empty
        result: Dict[str, Any] = {}
        if left_r is not None:
            result.update(left_r)

        # If both rows present, handle overlaps
        if right_r is not None:
            # Equal-named join keys should appear once; drop right-side duplicates
            equal_key_names = {rk for lk, rk in key_pairs if lk == rk}

            # Apply suffixing for overlapping non-key columns
            # Determine overlapped names among current left result and right row
            right_cols = set(right_r.keys())
            left_cols = set(result.keys())
            to_suffix = (left_cols & right_cols) - equal_key_names
            # Restrict to provided known overlaps if available
            if overlap_non_keys:
                to_suffix |= (overlap_non_keys - equal_key_names)

            # Rename left overlapped columns in result
            for col in list(to_suffix):
                if col in result and col not in {lk for lk, _ in key_pairs}:
                    result[col + suffix_left] = result.pop(col)

            # Add right row, suffixing when needed
            for col, val in right_r.items():
                # Skip right key if same-named pair
                if col in equal_key_names:
                    continue
                name = col
                if name in result and name not in {lk for lk, _ in key_pairs}:
                    name = name + suffix_right
                result[name] = val

        # Ensure that equal-named join keys exist (prefer left values)
        # If left missing but right present, place right values under their original names
        if left_r is None and right_r is not None:
            for lk, rk in key_pairs:
                if lk == rk:
                    result[lk] = right_r.get(rk)
        return result

    def _key_of(self, row: Dict[str, Any], keys: List[str]) -> tuple:
        return tuple(row.get(k) for k in keys)

    def _concat_rows_align_columns(
        self,
        left_rows: List[Dict[str, Any]],
        right_rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Concatenate rows from two tables, aligning by the union of columns.

        Missing columns in any row are filled with None. This is a safe fallback
        when no join keys are specified or could be inferred.
        """
        try:
            all_cols = list(self._rows_keyset(left_rows) | self._rows_keyset(right_rows))
        except Exception:
            all_cols = []
        if not all_cols:
            return (left_rows or []) + (right_rows or [])
        out: List[Dict[str, Any]] = []
        for r in (left_rows + right_rows):
            try:
                out.append({c: r.get(c) for c in all_cols})
            except Exception:
                try:
                    out.append(dict(r))  # best effort
                except Exception:
                    out.append({"value": str(r)})
        return out

    def _zip_rows_by_index(
        self,
        left_rows: List[Dict[str, Any]],
        right_rows: List[Dict[str, Any]],
        suffix_left: str,
        suffix_right: str,
    ) -> List[Dict[str, Any]]:
        """Zip rows by index, merging columns side-by-side.

        - Length is max(len(left), len(right))
        - For rows missing on one side, values from that side are treated as absent (None)
        - Overlapping non-key column names are suffixed consistently using provided suffixes
        - Final rows are aligned to a uniform set of columns
        """
        try:
            left_all_cols = self._rows_keyset(left_rows)
        except Exception:
            left_all_cols = set()
        try:
            right_all_cols = self._rows_keyset(right_rows)
        except Exception:
            right_all_cols = set()

        overlap_non_keys = (left_all_cols & right_all_cols)
        key_pairs: List[tuple[str, str]] = []

        max_len = max(len(left_rows), len(right_rows))
        zipped: List[Dict[str, Any]] = []
        for i in range(max_len):
            lr = left_rows[i] if i < len(left_rows) else None
            rr = right_rows[i] if i < len(right_rows) else None
            combined = self._combine_rows(lr, rr, key_pairs, overlap_non_keys, suffix_left, suffix_right)
            zipped.append(combined)

        # Build expected final columns with consistent suffixing for overlaps
        all_cols: List[str] = []
        try:
            # Preserve a stable, readable order: left unique, left-overlaps (suffixed), right unique, right-overlaps (suffixed)
            left_uniques = sorted(list(left_all_cols - overlap_non_keys))
            left_overlaps = sorted(list(overlap_non_keys))
            right_uniques = sorted(list(right_all_cols - overlap_non_keys))
            right_overlaps = sorted(list(overlap_non_keys))
            all_cols = (
                left_uniques
                + [c + suffix_left for c in left_overlaps]
                + right_uniques
                + [c + suffix_right for c in right_overlaps]
            )
        except Exception:
            # Fallback: union of keys seen in zipped rows
            try:
                all_cols = sorted(list(self._rows_keyset(zipped)))
            except Exception:
                all_cols = []

        if not all_cols:
            return zipped

        # Align each row to the final column set
        aligned: List[Dict[str, Any]] = []
        for r in zipped:
            try:
                aligned.append({c: r.get(c) for c in all_cols})
            except Exception:
                try:
                    # Best-effort: copy existing and fill missing
                    row_copy = dict(r)
                    for c in all_cols:
                        if c not in row_copy:
                            row_copy[c] = None
                    aligned.append(row_copy)
                except Exception:
                    aligned.append(r)
        return aligned

    # --- Execution ---
    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not inputs or "left" not in inputs or "right" not in inputs:
            raise ValueError("Both 'left' and 'right' inputs are required")

        left_rows = _to_rows(inputs["left"])  # list[dict]
        right_rows = _to_rows(inputs["right"])  # list[dict]

        # Determine keys
        left_on = self._parse_keys(self.get_property("left_on"))
        right_on = self._parse_keys(self.get_property("right_on"))
        auto = bool(self.get_property("auto_detect_keys"))

        # Quick path: if no keys provided and schemas match, concatenate rows
        try:
            left_all_cols_quick = self._rows_keyset(left_rows)
            right_all_cols_quick = self._rows_keyset(right_rows)
        except Exception:
            left_all_cols_quick = set()
            right_all_cols_quick = set()
        if (not left_on and not right_on) and left_all_cols_quick and (left_all_cols_quick == right_all_cols_quick):
            return {"data": left_rows + right_rows}

        if auto or not left_on:
            inferred = self._infer_common_keys(left_rows, right_rows)
            if not inferred:
                # No reliable keys found; honor the configured no-keys behavior
                suffix_left_prop = str(self.get_property("suffix_left") or "_x")
                suffix_right_prop = str(self.get_property("suffix_right") or "_y")
                mode = str(self.get_property("no_keys_behavior") or "zip_by_index").lower()
                if mode == "zip_by_index":
                    return {"data": self._zip_rows_by_index(left_rows, right_rows, suffix_left_prop, suffix_right_prop)}
                # Default fallback: concatenate rows and align columns
                return {"data": self._concat_rows_align_columns(left_rows, right_rows)}
            if not left_on:
                left_on = list(inferred)
        if auto or not right_on:
            if not right_on:
                right_on = list(left_on)

        if len(left_on) != len(right_on):
            raise ValueError("left_on and right_on must have same length")

        key_pairs: List[tuple[str, str]] = list(zip(left_on, right_on))
        how = str(self.get_property("how") or "inner").lower()
        suffix_left = str(self.get_property("suffix_left") or "_x")
        suffix_right = str(self.get_property("suffix_right") or "_y")

        # Pre-compute overlaps (non-key) across datasets to stabilize naming
        left_all_cols = self._rows_keyset(left_rows)
        right_all_cols = self._rows_keyset(right_rows)
        key_names_equal = {lk for lk, rk in key_pairs if lk == rk}
        overlap_non_keys = (left_all_cols & right_all_cols) - key_names_equal

        # Build index for right
        right_index: Dict[tuple, List[Dict[str, Any]]] = {}
        if right_on:
            for rr in right_rows:
                k = self._key_of(rr, right_on)
                right_index.setdefault(k, []).append(rr)
        else:
            # Should never happen due to checks
            right_index[tuple()] = right_rows[:]

        out: List[Dict[str, Any]] = []

        # Track matched right keys for right/outer
        matched_right_keys: set[tuple] = set()

        # Left side iteration
        for lr in left_rows:
            lk = self._key_of(lr, left_on)
            matches = right_index.get(lk, [])
            if matches:
                for rr in matches:
                    out.append(
                        self._combine_rows(lr, rr, key_pairs, overlap_non_keys, suffix_left, suffix_right)
                    )
                matched_right_keys.add(lk)
            else:
                if how in {"left", "outer"}:
                    out.append(
                        self._combine_rows(lr, None, key_pairs, overlap_non_keys, suffix_left, suffix_right)
                    )

        # Right-only rows for right/outer
        if how in {"right", "outer"}:
            for rr in right_rows:
                rk = self._key_of(rr, right_on)
                if rk not in matched_right_keys:
                    out.append(
                        self._combine_rows(None, rr, key_pairs, overlap_non_keys, suffix_left, suffix_right)
                    )

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

            # Progress and error panels below node body
            try:
                if getattr(self, "_progress_proxy", None) is not None and self._progress_proxy.isVisible():
                    if getattr(self, "_progress_widget", None) is not None:
                        try:
                            self._progress_widget.setFixedWidth(int(self.width))
                            self._progress_widget.adjustSize()
                        except Exception:
                            pass
                    self._progress_proxy.setPos(0.0, float(self.height) + 6.0)
            except Exception:
                pass
            try:
                if getattr(self, "_error_proxy", None) is not None and self._error_proxy.isVisible():
                    if getattr(self, "_error_widget", None) is not None:
                        try:
                            self._error_widget.setFixedWidth(int(self.width))
                            self._error_widget.adjustSize()
                        except Exception:
                            pass
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

    def _update_preview_from_last_inputs(self) -> None:
        try:
            # Prefer last_result if available; else use last inputs if stored
            res = self.properties.get("last_result")
            if isinstance(res, dict) and "data" in res:
                self._set_table_data(res["data"])
                return
            # Fallback: try to merge current cached inputs if manager stores them
            left = None
            right = None
            # Prefer explicit per-port snapshots populated by WorkflowManager
            if self.properties.get("last_input_left") is not None:
                left = self.properties.get("last_input_left")
            if self.properties.get("last_input_right") is not None:
                right = self.properties.get("last_input_right")
            # Backward-compatible fallbacks
            if left is None and self.properties.get("last_input_data") is not None:
                left = self.properties.get("last_input_data")
            if right is None and self.properties.get("last_input_results") is not None:
                right = self.properties.get("last_input_results")
            # If both present, show their merged preview via execute-lite
            if left is not None and right is not None:
                try:
                    tmp = self.execute({"left": left, "right": right})
                    self._set_table_data(tmp.get("data"))
                    return
                except Exception:
                    pass
            # Otherwise clear preview
            self._set_table_data([])
        except Exception:
            pass

    # --- UI callbacks ---
    def _on_how_changed(self, how: str) -> None:
        try:
            self.set_property("how", str(how).lower())
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_auto_detect_toggled(self, enabled: bool) -> None:
        try:
            self.set_property("auto_detect_keys", bool(enabled))
            if hasattr(self, "_edit_left") and hasattr(self, "_edit_right"):
                self._edit_left.setEnabled(not bool(enabled))
                self._edit_right.setEnabled(not bool(enabled))
            # Update preview immediately to reflect the new keying mode
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_left_keys_changed(self, text: str) -> None:
        try:
            keys = [s.strip() for s in str(text).split(",") if s.strip()]
            self.set_property("left_on", keys)
            # Always refresh preview when manual keys change
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_right_keys_changed(self, text: str) -> None:
        try:
            keys = [s.strip() for s in str(text).split(",") if s.strip()]
            self.set_property("right_on", keys)
            # Always refresh preview when manual keys change
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_suffix_changed(self, _text: str) -> None:
        try:
            self.set_property("suffix_left", str(self._edit_suf_l.text()))
            self.set_property("suffix_right", str(self._edit_suf_r.text()))
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_no_keys_mode_changed(self, mode: str) -> None:
        try:
            # Ensure only supported values are set
            mode_norm = str(mode).strip().lower()
            if mode_norm not in {"zip_by_index", "concat_rows"}:
                mode_norm = "zip_by_index"
            self.set_property("no_keys_behavior", mode_norm)
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_detect_clicked(self) -> None:
        try:
            # Try infer based on last inputs
            left = None
            right = None
            # Attempt to find cached inputs/results on explicit ports
            data_a = self.properties.get("last_input_left")
            data_b = self.properties.get("last_input_right")
            # Backward-compatible fallbacks
            if data_a is None:
                data_a = self.properties.get("last_input_data")
            if data_b is None:
                data_b = self.properties.get("last_input_results")
            left_rows = _to_rows(data_a) if data_a is not None else []
            right_rows = _to_rows(data_b) if data_b is not None else []
            if left_rows and right_rows:
                inferred = self._infer_common_keys(left_rows, right_rows)
                self.set_property("left_on", inferred)
                self.set_property("right_on", inferred)
                try:
                    self._edit_left.setText(", ".join(inferred))
                    self._edit_right.setText(", ".join(inferred))
                except Exception:
                    pass
                self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_refresh_clicked(self) -> None:
        try:
            # Refresh preview to show current state
            self._update_preview_from_last_inputs()
            # Trigger downstream partial re-run to propagate merged data
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
                self._update_preview_from_last_inputs()
            try:
                self._update_content_geometry(force=False)
                self.update()
            except Exception:
                pass
        except Exception:
            pass
        super().on_result(result)
