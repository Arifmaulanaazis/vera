"""DataframeMergeNode implementation."""

from .common import *  # noqa: F401,F403

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
