"""DockingAnalysisNode implementation."""

from .common import *  # noqa: F401,F403

class DockingAnalysisNode(BaseNode):
    """Analyze Vina docking outputs.

    Inputs:
      - docking_results (data): DataFrame or list[dict] with columns at least 'affinity' and preferably 'name'
      - molecules (molecules): either all poses (docked_molecules) or best poses per ligand (best_pose)

    Outputs:
      - analysis_dataframe (data): DataFrame suitable for plotting
      - molecules (molecules): molecules selected by the chosen analysis
      - best_pose (molecule): single molecule with the best (lowest) affinity overall
    """

    def __init__(self):
        super().__init__("docking_analysis", "Docking Analysis")
        self.logger = get_logger(__name__)

        # Two input pins only
        self.add_input_port("docking_results", "data")
        self.add_input_port("molecules", "molecules")

        # Outputs
        self.add_output_port("analysis_dataframe", "data")
        self.add_output_port("molecules", "molecules")
        self.add_output_port("best_pose", "molecule")

        # Analysis configuration
        self.set_property("analysis_mode", "best_per_ligand")  # best_per_ligand | top_k_global | top_k_per_ligand | threshold | summary
        self.set_property("top_k", 1)
        self.set_property("affinity_threshold", -7.0)
        # Additional UX properties
        self.set_property("ligand_filter", "")  # comma-separated names or substring
        self.set_property("sort_by", "affinity")  # affinity | name | mode | rmsd_lb | rmsd_ub
        self.set_property("sort_desc", False)
        self.set_property("preview_source", "analysis")  # analysis | input
        self.set_property("auto_refresh_preview", True)

        # Inline UI with table preview + floating params panel (pattern from DataframeMergeNode)
        from PySide6.QtWidgets import (
            QTableWidget,
            QGraphicsProxyWidget,
            QWidget,
            QVBoxLayout,
            QHBoxLayout,
            QLabel,
            QComboBox,
            QPushButton,
            QFrame,
            QLineEdit,
            QSpinBox,
            QDoubleSpinBox,
        )
        try:
            from PySide6.QtCore import Qt
        except Exception:
            Qt = None  # type: ignore

        # Node sizing similar to merge node
        self.width = 560
        self.height = 300
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
            panel.setObjectName("NodeDockingAnalysisParams")
            try:
                panel.setStyleSheet(
                    """
                    QFrame#NodeDockingAnalysisParams {
                        background-color: #2b2b2b;
                        border: 1px solid #666666;
                        border-radius: 6px;
                    }
                    QLabel { color: #e0e0e0; }
                    QLineEdit { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 2px 6px; }
                    QComboBox { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 2px 6px; }
                    QPushButton { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 4px 8px; }
                    QSpinBox, QDoubleSpinBox { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 2px 6px; }
                    """
                )
            except Exception:
                pass

            v = QVBoxLayout(panel)
            v.setContentsMargins(8, 6, 8, 6)
            v.setSpacing(6)

            # Analysis mode
            row_mode = QHBoxLayout()
            row_mode.addWidget(QLabel("Mode"))
            self._cmb_mode = QComboBox()
            try:
                self._cmb_mode.addItems(["best_per_ligand", "top_k_global", "top_k_per_ligand", "threshold", "summary"])  # type: ignore[attr-defined]
                cur = str(self.get_property("analysis_mode") or "best_per_ligand")
                idx = self._cmb_mode.findText(cur) if hasattr(self._cmb_mode, 'findText') else -1
                if idx >= 0:
                    self._cmb_mode.setCurrentIndex(idx)
            except Exception:
                pass
            row_mode.addWidget(self._cmb_mode)
            v.addLayout(row_mode)

            # Top K and threshold
            row_nums = QHBoxLayout()
            row_nums.addWidget(QLabel("Top K"))
            self._spin_topk = QSpinBox()
            self._spin_topk.setRange(1, 999)
            try:
                self._spin_topk.setValue(int(self.get_property("top_k") or 1))
            except Exception:
                pass
            row_nums.addWidget(self._spin_topk)

            row_nums.addWidget(QLabel("Threshold"))
            self._spin_thr = QDoubleSpinBox()
            self._spin_thr.setDecimals(2)
            self._spin_thr.setRange(-1000.0, 1000.0)
            self._spin_thr.setSingleStep(0.1)
            try:
                self._spin_thr.setValue(float(self.get_property("affinity_threshold") or -7.0))
            except Exception:
                pass
            row_nums.addWidget(self._spin_thr)
            v.addLayout(row_nums)

            # Ligand filter
            row_filter = QVBoxLayout()
            row_filter.addWidget(QLabel("Ligand filter (names or substring)"))
            self._edit_filter = QLineEdit(str(self.get_property("ligand_filter") or ""))
            row_filter.addWidget(self._edit_filter)
            v.addLayout(row_filter)

            # Sorting
            row_sort = QHBoxLayout()
            row_sort.addWidget(QLabel("Sort"))
            self._cmb_sort_by = QComboBox()
            try:
                self._cmb_sort_by.addItems(["affinity", "name", "mode", "rmsd_lb", "rmsd_ub"])  # type: ignore[attr-defined]
                cur_sb = str(self.get_property("sort_by") or "affinity")
                idx_sb = self._cmb_sort_by.findText(cur_sb) if hasattr(self._cmb_sort_by, 'findText') else -1
                if idx_sb >= 0:
                    self._cmb_sort_by.setCurrentIndex(idx_sb)
            except Exception:
                pass
            self._cmb_sort_dir = QComboBox()
            try:
                self._cmb_sort_dir.addItems(["asc", "desc"])  # type: ignore[attr-defined]
                if bool(self.get_property("sort_desc")):
                    self._cmb_sort_dir.setCurrentIndex(1)
            except Exception:
                pass
            row_sort.addWidget(self._cmb_sort_by)
            row_sort.addWidget(self._cmb_sort_dir)
            v.addLayout(row_sort)

            # Preview source
            row_prev = QHBoxLayout()
            row_prev.addWidget(QLabel("Preview"))
            self._cmb_preview = QComboBox()
            try:
                self._cmb_preview.addItems(["analysis", "input"])  # type: ignore[attr-defined]
                cur_pv = str(self.get_property("preview_source") or "analysis")
                idx_pv = self._cmb_preview.findText(cur_pv) if hasattr(self._cmb_preview, 'findText') else -1
                if idx_pv >= 0:
                    self._cmb_preview.setCurrentIndex(idx_pv)
            except Exception:
                pass
            row_prev.addWidget(self._cmb_preview)
            v.addLayout(row_prev)

            # Buttons
            row_btns = QHBoxLayout()
            self._btn_apply = QPushButton("Apply")
            self._btn_refresh = QPushButton("Refresh")
            row_btns.addWidget(self._btn_apply)
            row_btns.addStretch(1)
            row_btns.addWidget(self._btn_refresh)
            v.addLayout(row_btns)

            self._params_widget = panel
            self._params_proxy = QGraphicsProxyWidget(self)
            self._params_proxy.setWidget(panel)
            try:
                self._params_proxy.setZValue(8)
                self._params_proxy.setVisible(True)
            except Exception:
                pass

            # Wire interactions
            try:
                self._cmb_mode.currentTextChanged.connect(self._on_mode_changed)  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                self._spin_topk.valueChanged.connect(self._on_topk_changed)  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                self._spin_thr.valueChanged.connect(self._on_thr_changed)  # type: ignore[attr-defined]
            except Exception:
                pass
            self._edit_filter.textChanged.connect(self._on_filter_changed)
            try:
                self._cmb_sort_by.currentTextChanged.connect(self._on_sort_changed)  # type: ignore[attr-defined]
                self._cmb_sort_dir.currentTextChanged.connect(self._on_sort_changed)  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                self._cmb_preview.currentTextChanged.connect(self._on_preview_changed)  # type: ignore[attr-defined]
            except Exception:
                pass
            self._btn_apply.clicked.connect(self._on_apply_clicked)
            self._btn_refresh.clicked.connect(self._on_refresh_clicked)

            # Initial geometry sync
            try:
                self._update_content_geometry(force=True)
                self.update()
            except Exception:
                pass
        except Exception:
            self._params_proxy = None
            self._params_widget = None

    def _normalize_results_df(self, docking_results):
        try:
            import pandas as pd  # type: ignore
        except Exception:
            pd = None  # type: ignore

        df = None
        if pd is not None and docking_results is not None:
            if isinstance(docking_results, pd.DataFrame):
                df = docking_results.copy()
            elif isinstance(docking_results, list) and (len(docking_results) == 0 or isinstance(docking_results[0], dict)):
                df = pd.DataFrame(docking_results)
            elif isinstance(docking_results, dict) and isinstance(docking_results.get("poses"), list):
                df = pd.DataFrame(docking_results["poses"])  # type: ignore
        # Ensure required columns
        if df is not None and not df.empty:
            if "affinity" not in df.columns:
                # Try 'energy' fallback
                for alt in ("energy", "Energy", "ENERGY"):
                    if alt in df.columns:
                        df = df.rename(columns={alt: "affinity"})
                        break
            # Ensure 'name' column exists for ligand grouping
            if "name" not in df.columns:
                # Assign to a single ligand group if missing
                df.insert(0, "name", ["1"] * len(df))
        return df

    def _detect_molecule_mode(self, df, molecules: list) -> str:
        """Return 'all_poses' if molecules count matches df rows, or 'best_pose' if it matches unique ligands."""
        if not isinstance(molecules, list):
            return "unknown"
        try:
            n_rows = 0 if df is None else int(len(df))
            unique_names = 0 if df is None or "name" not in df.columns else int(len(set(df["name"].astype(str))))
            if len(molecules) == n_rows and n_rows > 0:
                return "all_poses"
            if unique_names > 0 and len(molecules) == unique_names:
                return "best_pose"
        except Exception:
            pass
        return "unknown"

    # --- Inline UI helpers ---
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
        # Normalize to rows
        rows: list[dict]
        if data is None:
            rows = []
        else:
            try:
                import pandas as pd
                if isinstance(data, pd.DataFrame):
                    rows = data.to_dict(orient="records")
                elif isinstance(data, list) and (len(data) == 0 or isinstance(data[0], dict)):
                    rows = data
                else:
                    rows = [{"value": str(data)}]
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

    def _apply_sort_and_filter(self, df):
        try:
            import pandas as pd  # type: ignore
        except Exception:
            pd = None  # type: ignore
        if df is None:
            return df
        try:
            # Ligand filter
            filt = str(self.get_property("ligand_filter") or "").strip()
            if filt and "name" in df.columns:
                if "," in filt:
                    allow = {s.strip() for s in filt.split(",") if s.strip()}
                    df = df[df["name"].astype(str).isin(allow)]
                else:
                    sub = filt.lower()
                    df = df[df["name"].astype(str).str.lower().str.contains(sub, na=False)]
            # Sorting
            by = str(self.get_property("sort_by") or "")
            desc = bool(self.get_property("sort_desc"))
            if by and by in df.columns:
                df = df.sort_values(by=by, ascending=not desc)
            # Reset index for cleaner view
            try:
                df = df.reset_index(drop=True)
            except Exception:
                pass
        except Exception:
            pass
        return df

    def _update_preview_from_last_inputs(self) -> None:
        try:
            # Determine preview source
            preview_src = str(self.get_property("preview_source") or "analysis")
            # Pull last cached inputs
            docking_results = self.properties.get("last_input_docking_results")
            df = self._normalize_results_df(docking_results)
            if preview_src == "input":
                shown = self._apply_sort_and_filter(df) if df is not None else []
                self._set_table_data(shown)
                return
            # analysis preview
            mols_input = self.properties.get("last_input_molecules") or []
            analysis_df, _mols = self._perform_analysis(df, mols_input)
            shown = self._apply_sort_and_filter(analysis_df) if analysis_df is not None else []
            self._set_table_data(shown)
        except Exception:
            try:
                self._set_table_data([])
            except Exception:
                pass

    # Keep output ports anchored to the right of the params panel
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

    # UI callbacks
    def _on_mode_changed(self, mode: str) -> None:
        try:
            self.set_property("analysis_mode", str(mode))
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_topk_changed(self, value: int) -> None:
        try:
            self.set_property("top_k", int(value))
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_thr_changed(self, value: float) -> None:
        try:
            self.set_property("affinity_threshold", float(value))
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_filter_changed(self, text: str) -> None:
        try:
            self.set_property("ligand_filter", str(text))
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_sort_changed(self, _text: str) -> None:
        try:
            self.set_property("sort_by", str(self._cmb_sort_by.currentText()))
            self.set_property("sort_desc", bool(self._cmb_sort_dir.currentText() == "desc"))
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_preview_changed(self, _text: str) -> None:
        try:
            self.set_property("preview_source", str(self._cmb_preview.currentText()))
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_apply_clicked(self) -> None:
        try:
            # Trigger downstream re-execution from this node
            if hasattr(self, 'rerun_requested'):
                self.rerun_requested.emit(self)
        except Exception:
            pass

    def _on_refresh_clicked(self) -> None:
        try:
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _inline_summary(self) -> list[str]:  # pragma: no cover - UI painting helper
        try:
            mode = str(self.get_property("analysis_mode") or "best_per_ligand")
            lines = [f"Mode: {mode}"]
            if mode.startswith("top_k"):
                lines.append(f"Top K: {int(self.get_property('top_k') or 1)}")
            if mode == "threshold":
                try:
                    thr = float(self.get_property("affinity_threshold") or -7.0)
                    lines.append(f"Thr: {thr:.2f}")
                except Exception:
                    pass
            lf = str(self.get_property("ligand_filter") or "").strip()
            if lf:
                lines.append(f"Filter: {lf}")
            return lines
        except Exception:
            return []

    # Shared analysis logic (used by execute and preview)
    def _perform_analysis(self, df, mols_input: list) -> tuple:
        try:
            import pandas as pd  # type: ignore
        except Exception:
            pd = None  # type: ignore

        if df is None or (hasattr(df, 'empty') and df.empty) or (isinstance(df, list) and not df):
            return df, []

        # Normalize dtypes and prepare original row index for molecule mapping
        try:
            if hasattr(df, 'astype'):
                df["name"] = df["name"].astype(str)
                df["affinity"] = df["affinity"].astype(float)
        except Exception:
            pass
        df_work = df
        try:
            if hasattr(df, 'copy'):
                df_work = df.copy()
                df_work["__row_idx"] = list(range(len(df_work)))
        except Exception:
            df_work = df

        mode = (self.get_property("analysis_mode") or "best_per_ligand").strip().lower()
        top_k = max(1, int(self.get_property("top_k") or 1))
        thr = float(self.get_property("affinity_threshold") or -7.0)

        # How molecules correspond to rows
        mol_mode = self._detect_molecule_mode(df, mols_input)

        def select_molecules_by_indices(indices: list[int]) -> list:
            if mol_mode == "all_poses" and isinstance(mols_input, list) and len(mols_input) >= max(indices + [0]):
                try:
                    return [mols_input[i] for i in indices if i < len(mols_input) and mols_input[i] is not None]
                except Exception:
                    return []
            if mol_mode == "best_pose":
                return list(mols_input)
            return []

        analysis_df = None
        molecules_out: list = []

        if mode == "best_per_ligand":
            if pd is not None and hasattr(df_work, 'groupby'):
                idxs = df_work.groupby("name")["affinity"].idxmin()
                best_rows = df_work.loc[idxs]
                analysis_df = best_rows.reset_index(drop=True)
                try:
                    sel_indices = list(best_rows["__row_idx"].astype(int).tolist())
                except Exception:
                    sel_indices = list(idxs.astype(int).tolist())
            else:
                analysis_df = df_work
                sel_indices = []
            if mol_mode == "best_pose":
                # Best per ligand: map ligand names to best_pose positions (1-based names)
                try:
                    names = []
                    if hasattr(analysis_df, 'to_dict'):
                        names = [str(n) for n in list(analysis_df["name"].astype(str).tolist()) if n is not None]
                    mapped: list = []
                    for n in names:
                        try:
                            idx = int(float(n)) - 1
                        except Exception:
                            idx = None
                        if idx is not None and 0 <= idx < len(mols_input):
                            mapped.append(mols_input[idx])
                    molecules_out = mapped
                except Exception:
                    molecules_out = list(mols_input)
            else:
                molecules_out = select_molecules_by_indices(sel_indices)

        elif mode == "top_k_global":
            if hasattr(df_work, 'sort_values'):
                sorted_df = df_work.sort_values(by="affinity", ascending=True)
                analysis_head = sorted_df.head(top_k)
                analysis_df = analysis_head.reset_index(drop=True)
                try:
                    sel_indices = list(analysis_head["__row_idx"].astype(int).tolist())
                except Exception:
                    sel_indices = list(analysis_df.index)
            else:
                analysis_df = df_work
                sel_indices = []
            if mol_mode == "best_pose":
                # Map selected ligand names to best_pose list
                try:
                    names = []
                    if hasattr(analysis_df, 'to_dict'):
                        names = [str(n) for n in list(analysis_df["name"].astype(str).tolist()) if n is not None]
                    unique_names = []
                    seen = set()
                    for n in names:
                        if n not in seen:
                            unique_names.append(n); seen.add(n)
                    mapped: list = []
                    for n in unique_names:
                        try:
                            idx = int(float(n)) - 1  # supports "1" or "1.0"
                        except Exception:
                            idx = None
                        if idx is not None and 0 <= idx < len(mols_input):
                            mapped.append(mols_input[idx])
                    molecules_out = mapped if mapped else list(mols_input)
                except Exception:
                    molecules_out = list(mols_input)
            else:
                molecules_out = select_molecules_by_indices(sel_indices)

        elif mode == "top_k_per_ligand":
            if hasattr(df_work, 'sort_values') and hasattr(df_work, 'groupby'):
                sorted_group = df_work.sort_values(["name", "affinity"], ascending=[True, True])
                take = sorted_group.groupby("name", as_index=False).head(top_k)
                analysis_df = take.reset_index(drop=True)
                try:
                    sel_indices = list(take["__row_idx"].astype(int).tolist())
                except Exception:
                    sel_indices = list(analysis_df.index)
            else:
                sel_indices = []
            if mol_mode == "best_pose":
                # One best molecule per ligand; map by ligand name
                try:
                    names = []
                    if hasattr(analysis_df, 'to_dict'):
                        names = [str(n) for n in list(analysis_df["name"].astype(str).tolist()) if n is not None]
                    unique_names = []
                    seen = set()
                    for n in names:
                        if n not in seen:
                            unique_names.append(n); seen.add(n)
                    mapped: list = []
                    for n in unique_names:
                        try:
                            idx = int(float(n)) - 1
                        except Exception:
                            idx = None
                        if idx is not None and 0 <= idx < len(mols_input):
                            mapped.append(mols_input[idx])
                    molecules_out = mapped if mapped else list(mols_input)
                except Exception:
                    molecules_out = list(mols_input)
            else:
                molecules_out = select_molecules_by_indices(sel_indices)

        elif mode == "threshold":
            if hasattr(df_work, 'reset_index'):
                filt = df_work[df_work["affinity"] <= thr]
                analysis_df = filt.reset_index(drop=True)
                try:
                    sel_indices = list(filt["__row_idx"].astype(int).tolist())
                except Exception:
                    sel_indices = list(analysis_df.index)
            else:
                sel_indices = []
            if mol_mode == "best_pose":
                # Map to best_pose by ligand name subset
                try:
                    names = []
                    if hasattr(analysis_df, 'to_dict'):
                        names = [str(n) for n in list(analysis_df["name"].astype(str).tolist()) if n is not None]
                    unique_names = []
                    seen = set()
                    for n in names:
                        if n not in seen:
                            unique_names.append(n); seen.add(n)
                    mapped: list = []
                    for n in unique_names:
                        try:
                            idx = int(float(n)) - 1
                        except Exception:
                            idx = None
                        if idx is not None and 0 <= idx < len(mols_input):
                            mapped.append(mols_input[idx])
                    molecules_out = mapped if mapped else list(mols_input)
                except Exception:
                    molecules_out = list(mols_input)
            else:
                molecules_out = select_molecules_by_indices(sel_indices)

        else:  # summary
            if hasattr(df_work, 'groupby'):
                grp = df_work.groupby("name")["affinity"]
                try:
                    analysis_df = grp.agg(best="min", worst="max", mean="mean", count="count").reset_index()
                except Exception:
                    # Fallback for older pandas
                    analysis_df = grp.agg(["min", "max", "mean", "count"]).reset_index()
                    try:
                        analysis_df = analysis_df.rename(columns={"min": "best", "max": "worst", "count": "count"})
                    except Exception:
                        pass
            else:
                analysis_df = df_work
            molecules_out = list(mols_input) if mol_mode == "best_pose" else []

        # Drop helper column from display/output if present
        try:
            if hasattr(analysis_df, 'drop') and "__row_idx" in list(analysis_df.columns):
                analysis_df = analysis_df.drop(columns=["__row_idx"])  # type: ignore
        except Exception:
            pass
        # Sanitize molecule list and provide robust fallback to ensure viewer compatibility
        try:
            if isinstance(molecules_out, list):
                molecules_out = [m for m in molecules_out if m is not None]
        except Exception:
            pass
        # Only fallback for best_pose wiring; never auto-fallback to all poses
        try:
            if (not molecules_out) and (self._detect_molecule_mode(df, mols_input) == "best_pose"):
                if isinstance(mols_input, list):
                    molecules_out = [m for m in mols_input if m is not None]
        except Exception:
            pass
        # Fallback: ensure we always return a list like AutoDock outputs
        try:
            if not isinstance(molecules_out, list):
                molecules_out = list(molecules_out) if molecules_out is not None else []
        except Exception:
            molecules_out = []
        return analysis_df, molecules_out

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            docking_results = (inputs or {}).get("docking_results")
            mols_input = (inputs or {}).get("molecules") or []

            df = self._normalize_results_df(docking_results)
            if df is None or df.empty or "affinity" not in df.columns:
                raise ValueError("Invalid docking_results: expected DataFrame or list of poses with 'affinity'")
            analysis_df, molecules_out = self._perform_analysis(df, mols_input)

            # Compute single best pose molecule across all entries
            best_pose_mol = None
            try:
                # Find index/row of global minimum affinity
                # Use argmin over values to get positional index robustly
                import numpy as _np  # type: ignore
                affinities = _np.array(list(df["affinity"].astype(float)))
                pos_min = int(affinities.argmin()) if affinities.size > 0 else -1
                if 0 <= pos_min < len(df):
                    mol_mode = self._detect_molecule_mode(df, mols_input)
                    if mol_mode == "all_poses":
                        if 0 <= pos_min < len(mols_input):
                            cand = mols_input[pos_min]
                            if cand is not None:
                                best_pose_mol = cand
                    elif mol_mode == "best_pose":
                        # Map ligand name of best row to best_pose index (1-based)
                        try:
                            lig_name = str(df.iloc[pos_min]["name"]) if "name" in df.columns else None
                        except Exception:
                            lig_name = None
                        if lig_name is not None:
                            try:
                                lig_idx = int(float(lig_name)) - 1
                                if 0 <= lig_idx < len(mols_input):
                                    cand = mols_input[lig_idx]
                                    if cand is not None:
                                        best_pose_mol = cand
                            except Exception:
                                pass
                    else:
                        # Unknown mapping; best-effort: if counts match rows, treat as all_poses
                        if len(mols_input) == len(df) and 0 <= pos_min < len(mols_input):
                            cand = mols_input[pos_min]
                            if cand is not None:
                                best_pose_mol = cand
            except Exception:
                best_pose_mol = None

            result = {
                "analysis_dataframe": analysis_df if analysis_df is not None else df,
                "molecules": molecules_out,
                "best_pose": best_pose_mol,
            }
            return result
        except Exception as e:
            self.logger.error(f"Error in docking analysis: {e}")
            raise

    # Live update hook for preview
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
