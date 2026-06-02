"""TableViewNode implementation."""

from .common import *  # noqa: F401,F403

class TableViewNode(BaseNode):
    """Inline table viewer that displays list-of-dicts or DataFrame-like data.

    Inputs: data (data)
    Outputs: none (viewer)
    """

    def __init__(self):
        super().__init__("table_view", "Table View")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        # Visual size
        self.width = 360
        self.height = 220
        self.setMinimumSize(self.width, self.height)
        self.setMaximumSize(self.width, self.height)
        # Fill the node body completely (no inner spacing)
        try:
            self.set_content_margins(0, 32, 0, 0)
        except Exception:
            pass
        # Inline widget
        try:
            # Respect lightweight construction mode to avoid heavy widget init during compatibility probing
            from core.nodes import BaseNode as _BaseNode
            if getattr(_BaseNode, "_lightweight_construction", False):  # type: ignore[attr-defined]
                self._table = None
            else:
                from PySide6.QtWidgets import QTableWidget
                self._table = QTableWidget()
            self._table.setColumnCount(0)
            self._table.setRowCount(0)
            # Visual tweaks to ensure it is visible and readable
            try:
                self._table.setAlternatingRowColors(True)
                self._table.setShowGrid(True)
                header = self._table.horizontalHeader()
                header.setStretchLastSection(True)
            except Exception:
                pass
            layout = self.content_layout
            if layout is not None and self._table is not None:
                layout.addWidget(self._table, 0, 0)
            # Re-align ports after custom width/height
            self._update_port_positions()
        except Exception:
            self._table = None

    def _set_table_data(self, data: Any) -> None:
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
            # Try pandas DataFrame or decode JSON strings for list elements
            try:
                import pandas as pd
                if isinstance(data, pd.DataFrame):
                    rows = data.to_dict(orient="records")
                else:
                    # If list of stringified JSON dicts, coerce
                    if isinstance(data, list) and data and all(isinstance(x, str) and str(x).lstrip().startswith(('{','[')) for x in data[:5]):
                        import json as _json
                        tmp = []
                        for x in data:
                            try:
                                obj = _json.loads(str(x))
                                if isinstance(obj, dict):
                                    tmp.append(obj)
                                else:
                                    tmp.append({"value": obj})
                            except Exception:
                                tmp.append({"value": x})
                        rows = tmp
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

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = inputs.get("data") if inputs else None
        # Return a tiny summary; UI is updated via on_result
        if isinstance(data, list):
            size = len(data)
        elif isinstance(data, dict):
            size = len(data)
        elif data is None:
            size = 0
        else:
            size = 1
        return {"preview_size": size, "preview_type": type(data).__name__}

    def on_result(self, result: object) -> None:
        # Pull last connected input if available via properties snapshot
        try:
            data = self.properties.get("last_input_data")
            if data is not None:
                self._set_table_data(data)
        except Exception:
            pass
        super().on_result(result)
