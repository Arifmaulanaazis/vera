"""PubChemSearchNode implementation."""

from .common import *  # noqa: F401,F403

class PubChemSearchNode(BaseNode):
    """Search PubChem for one or many queries and return a comprehensive table.

    Inputs:
      - query (string): single compound name/identifier
      - data (data): pandas.DataFrame or list-of-dicts/strings containing queries

    Output (only 1 pin):
      - data (data): pandas.DataFrame with columns like
        query, cid, Name, Synonyms, SMILES, IUPAC Name, InChI,
        InChIKey, Molecular Formula, Molecular Weight, XLogP, TPSA,
        H-Bond Donor Count, H-Bond Acceptor Count, Rotatable Bond Count,
        Exact Mass, Monoisotopic Mass, Charge, Complexity
    """

    def __init__(self):
        super().__init__("pubchem_search", "PubChem Search")
        self.logger = get_logger(__name__)
        # Inputs
        self.add_input_port("query", "string")
        self.add_input_port("data", "data")
        # Single output: DataFrame/list-of-dicts
        self.add_output_port("data", "data")

        # Properties
        self.set_property("query", "")
        self.set_property("selected_column", "")  # for dataframe input
        self.set_property("available_query_columns", [])
        self.set_property("needs_user_action", False)
        self.set_property("max_workers", 4)

        # Inline UI: combobox + OK button for selecting a query column when needed
        try:
            from PySide6.QtWidgets import QLabel, QComboBox, QPushButton, QHBoxLayout, QWidget

            self.width = 360
            self.height = 150
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)

            row = QHBoxLayout()
            lbl = QLabel("Query column")
            lbl.setStyleSheet("QLabel { background: transparent; }")
            # Custom combobox to handle z-index for dropdown
            class ZIndexComboBox(QComboBox):
                def __init__(self, parent_node):
                    super().__init__()
                    self.parent_node = parent_node
                
                def showPopup(self):
                    try:
                        if hasattr(self.parent_node, '_content_proxy') and self.parent_node._content_proxy is not None:
                            self.parent_node._content_proxy.setZValue(15)  # Higher than pause hint
                    except Exception:
                        pass
                    super().showPopup()
                
                def hidePopup(self):
                    super().hidePopup()
                    try:
                        if hasattr(self.parent_node, '_content_proxy') and self.parent_node._content_proxy is not None:
                            self.parent_node._content_proxy.setZValue(5)  # Back to default
                    except Exception:
                        pass
            
            self._cmb_query = ZIndexComboBox(self)
            self._cmb_query.setEditable(False)
            self._btn_ok = QPushButton("OK")

            def _on_ok_clicked():
                try:
                    col = self._cmb_query.currentText()
                    if col:
                        self.set_property("selected_column", col)
                        self.set_property("needs_user_action", False)
                        # Ask host app to partially re-run from this node
                        try:
                            if hasattr(self, 'rerun_requested'):
                                self.rerun_requested.emit(self)  # type: ignore[arg-type]
                        except Exception:
                            pass
                        # Resume user input (not global workflow pause)
                        try:
                            sc = self.scene()
                            view = None
                            if sc is not None and hasattr(sc, 'views'):
                                vs = sc.views()
                                view = vs[0] if isinstance(vs, (list, tuple)) and vs else None
                            if view is not None:
                                win = view.window()
                                if hasattr(win, 'workflow_manager'):
                                    # Resume user input for this specific node
                                    win.workflow_manager.resume_user_input(self._node_id)  # type: ignore[attr-defined]
                        except Exception:
                            pass
                except Exception:
                    pass

            self._btn_ok.clicked.connect(_on_ok_clicked)

            row.addWidget(lbl)
            row.addWidget(self._cmb_query, 1)
            row.addWidget(self._btn_ok)
            # Pack into a small container to insert in grid
            container = QWidget()
            container.setStyleSheet("QWidget { background: transparent; }")
            container.setLayout(row)

            layout = self.content_layout
            if layout is not None:
                layout.addWidget(container, 0, 0)
            self._update_port_positions()
        except Exception:
            # Headless safe
            pass

    # --- Helpers (headless-safe) ---
    def _normalize_to_rows(self, obj: Any) -> list[dict]:
        try:
            import pandas as pd  # type: ignore
        except Exception:
            pd = None  # type: ignore
        if obj is None:
            return []
        # If DataFrame → records
        if pd is not None and isinstance(obj, pd.DataFrame):  # type: ignore[arg-type]
            try:
                return obj.to_dict(orient="records")
            except Exception:
                return []
        # list-of-dicts
        if isinstance(obj, list) and (len(obj) == 0 or isinstance(obj[0], dict)):
            return obj  # type: ignore[return-value]
        # list-of-strings → wrap as {'value': s}
        if isinstance(obj, list) and (len(obj) == 0 or isinstance(obj[0], str)):
            return [{"value": s} for s in obj]  # type: ignore[list-item]
        # dict → one row
        if isinstance(obj, dict):
            return [obj]
        # Fallback: single string
        try:
            if isinstance(obj, str) and obj.strip():
                return [{"value": obj.strip()}]
        except Exception:
            pass
        return []

    def _extract_dataframe_columns(self, data_obj: Any) -> list[str]:
        """Return top-level column names from a table-like input.
        Accepts pandas.DataFrame or list-of-dicts.
        """
        try:
            import pandas as pd  # type: ignore
        except Exception:
            pd = None  # type: ignore
        if data_obj is None:
            return []
        try:
            if pd is not None and isinstance(data_obj, pd.DataFrame):  # type: ignore[arg-type]
                return [str(c) for c in list(data_obj.columns)]
        except Exception:
            pass
        rows = self._normalize_to_rows(data_obj)
        keys: set[str] = set()
        for r in rows[:50]:
            try:
                for k in r.keys():
                    keys.add(str(k))
            except Exception:
                pass
        return sorted(list(keys))

    def _resolve_query_list(self, inputs: Optional[Dict[str, Any]]) -> tuple[list[str], bool]:
        """Return (queries, needs_user_action).
        - If 'data' input is provided and has >1 columns with no selected_column set,
          populate available_query_columns and request user action.
        - If single column, use it.
        - Otherwise, use 'query' property or input.
        """
        # Prefer 'data' input when present
        data_input = (inputs or {}).get("data") if inputs else None
        if data_input is not None:
            cols = self._extract_dataframe_columns(data_input)
            if len(cols) == 0:
                # Could be a list-of-strings
                rows = self._normalize_to_rows(data_input)
                vals = [str(r.get("value", "")).strip() for r in rows if str(r.get("value", "")).strip()]
                return vals, False
            if len(cols) == 1:
                col = cols[0]
                # Extract values from that column
                try:
                    import pandas as pd  # type: ignore
                except Exception:
                    pd = None  # type: ignore
                if pd is not None:
                    try:
                        from pandas import DataFrame as _PDDataFrame  # type: ignore
                    except Exception:
                        _PDDataFrame = None  # type: ignore
                if pd is not None and _PDDataFrame is not None and isinstance(data_input, _PDDataFrame):
                    try:
                        series = data_input[col]  # type: ignore[index]
                        vals = [str(v).strip() for v in list(series)]
                    except Exception:
                        vals = []
                else:
                    rows = self._normalize_to_rows(data_input)
                    vals = [str(r.get(col, "")).strip() for r in rows if str(r.get(col, "")).strip()]
                return vals, False
            # Multiple columns: need user to choose unless we already have one
            preselected = str(self.get_property("selected_column") or "").strip()
            if preselected and preselected in cols:
                # Extract using preselected
                try:
                    import pandas as pd  # type: ignore
                except Exception:
                    pd = None  # type: ignore
                if pd is not None:
                    try:
                        from pandas import DataFrame as _PDDataFrame  # type: ignore
                    except Exception:
                        _PDDataFrame = None  # type: ignore
                if pd is not None and _PDDataFrame is not None and isinstance(data_input, _PDDataFrame):
                    try:
                        series = data_input[preselected]  # type: ignore[index]
                        vals = [str(v).strip() for v in list(series)]
                    except Exception:
                        vals = []
                else:
                    rows = self._normalize_to_rows(data_input)
                    vals = [str(r.get(preselected, "")).strip() for r in rows if str(r.get(preselected, "")).strip()]
                return vals, False
            # Ask user to select
            try:
                self.set_property("available_query_columns", cols)
                self.set_property("needs_user_action", True)
            except Exception:
                pass
            # Use user input specific pause (not global workflow pause)
            try:
                msg = "Select a query column and click OK on this node to continue."
                self._manager.pause_user_input(self._node_id, msg)  # type: ignore[attr-defined]
            except Exception:
                pass
            return [], True

        # Fallback: single text query
        q = None
        if inputs and "query" in inputs and inputs.get("query"):
            q = inputs.get("query")
        if not q:
            q = self.get_property("query")
        q = str(q or "").strip()
        if q:
            return [q], False
        return [], False

    def _friendly_columns_order(self) -> list[str]:
        # Stable order; extras will be appended after these
        return [
            "query",
            "cid",
            "Name",
            "Synonyms",
            "SMILES",
            "IUPAC Name",
            "InChI",
            "InChIKey",
            "Molecular Formula",
            "Molecular Weight",
            "XLogP",
            "TPSA",
            "H-Bond Donor Count",
            "H-Bond Acceptor Count",
            "Rotatable Bond Count",
            "Exact Mass",
            "Monoisotopic Mass",
            "Charge",
            "Complexity"
        ]

    def _row_not_found(self, query_text: str) -> dict:
        base = {k: "Data not found" for k in self._friendly_columns_order() if k not in {"query"}}
        base["query"] = query_text
        return base

    def _safe_get(self, obj: Any, attr: str) -> Any:
        try:
            return getattr(obj, attr, None)
        except Exception:
            return None

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        import time
        try:
            import pandas as pd  # type: ignore
        except Exception:
            pd = None  # type: ignore
        try:
            import pubchempy as pcp
        except Exception as e:
            raise ValueError(f"pubchempy is required: {e}")

        # Determine query list (and possibly pause for user selection)
        queries, needs_action = self._resolve_query_list(inputs)
        if needs_action:
            # Surface a progress hint while waiting for user
            try:
                self.report_progress(-1, "Waiting for user to select query column…")
            except Exception:
                pass
            # Return an empty payload for now; user will click OK and re-run this node
            return {"data": pd.DataFrame([]) if pd is not None else []}

        if not queries:
            raise ValueError("Query is required (string) or a dataframe/list input must contain at least one value")

        total = len(queries)
        try:
            self.report_progress(-1, f"PubChem: resolving {total} querie(s)…")
        except Exception:
            pass

        # Helper to resolve one query → row dict
        def process_one(qtext: str) -> dict:
            try:
                # Resolve CID
                q_clean = (qtext or "").strip()
                cid_value = None
                if q_clean.isdigit():
                    try:
                        cid_value = int(q_clean)
                    except Exception:
                        cid_value = None
                if cid_value is None:
                    cids = []
                    last_err = None
                    for attempt in range(3):
                        try:
                            cids = pcp.get_cids(q_clean, "name")
                            break
                        except Exception as e:
                            last_err = e
                            time.sleep(0.5 + 0.5 * attempt)
                    if not cids:
                        # Try as SMILES/InChI as a fallback
                        try:
                            cids = pcp.get_cids(q_clean, "smiles")
                        except Exception:
                            pass
                    if not cids:
                        try:
                            cids = pcp.get_cids(q_clean, "inchi")
                        except Exception:
                            pass
                    if not cids and last_err is not None:
                        self.logger.warning(f"PubChem: failed to resolve CID for '{q_clean}': {last_err}")
                    if not cids:
                        return self._row_not_found(q_clean)
                    cid_value = int(cids[0])

                # Fetch core compound
                compound = None
                last_err2 = None
                for attempt in range(3):
                    try:
                        compound = pcp.Compound.from_cid(cid_value)
                        break
                    except Exception as e:
                        last_err2 = e
                        time.sleep(0.5 + 0.5 * attempt)
                if compound is None:
                    self.logger.warning(f"PubChem: failed to load Compound for CID {cid_value}: {last_err2}")
                    row = self._row_not_found(q_clean)
                    row["cid"] = str(cid_value)
                    return row

                # Try a wide property fetch in one API call
                prop_names = [
                    "MolecularFormula",
                    "MolecularWeight",
                    "SMILES",
                    "InChI",
                    "InChIKey",
                    "IUPACName",
                    "Title",
                    "XLogP",
                    "TPSA",
                    "HBondDonorCount",
                    "HBondAcceptorCount",
                    "RotatableBondCount",
                    "ExactMass",
                    "MonoisotopicMass",
                    "Charge",
                    "Complexity",
                ]
                props: dict = {}
                try:
                    vals = pcp.get_properties(
                        properties=",".join(prop_names),
                        identifier=cid_value,
                        namespace="cid",
                    )
                    if isinstance(vals, list) and vals:
                        props = vals[0] if isinstance(vals[0], dict) else {}
                except Exception:
                    props = {}

                # Synonyms
                synonyms_str = None
                syns = None
                try:
                    syns = self._safe_get(compound, "synonyms")
                except Exception:
                    syns = None
                if not syns:
                    try:
                        syn_ret = pcp.get_synonyms(cid_value)
                        # pcp.get_synonyms returns list[{'CID': cid, 'Synonym': [..]}]
                        if isinstance(syn_ret, list) and syn_ret:
                            maybe = syn_ret[0]
                            if isinstance(maybe, dict) and isinstance(maybe.get("Synonym"), list):
                                syns = maybe.get("Synonym")
                    except Exception:
                        pass
                if isinstance(syns, list):
                    try:
                        synonyms_str = "; ".join([str(s) for s in syns[:100]])
                    except Exception:
                        synonyms_str = None

                # Build row with friendly names
                def _val_or_nf(v: Any) -> Any:
                    return v if v not in (None, "", [], {}) else "Data not found"

                # Preferred human name: IUPACName > Title > first Synonym
                human_name = (
                    props.get("IUPACName")
                    or props.get("Title")
                    or (syns[0] if isinstance(syns, list) and syns else None)
                )

                row: dict[str, Any] = {
                    "query": q_clean,
                    "cid": str(getattr(compound, "cid", props.get("CID", "Data not found"))),
                    "Name": _val_or_nf(human_name),
                    "Synonyms": _val_or_nf(synonyms_str),
                    "SMILES": _val_or_nf(props.get("SMILES")),
                    "IUPAC Name": _val_or_nf(props.get("IUPACName")),
                    "InChI": _val_or_nf(props.get("InChI")),
                    "InChIKey": _val_or_nf(props.get("InChIKey")),
                    "Molecular Formula": _val_or_nf(props.get("MolecularFormula")),
                    "Molecular Weight": _val_or_nf(props.get("MolecularWeight")),
                    "XLogP": _val_or_nf(props.get("XLogP")),
                    "TPSA": _val_or_nf(props.get("TPSA")),
                    "H-Bond Donor Count": _val_or_nf(props.get("HBondDonorCount")),
                    "H-Bond Acceptor Count": _val_or_nf(props.get("HBondAcceptorCount")),
                    "Rotatable Bond Count": _val_or_nf(props.get("RotatableBondCount")),
                    "Exact Mass": _val_or_nf(props.get("ExactMass")),
                    "Monoisotopic Mass": _val_or_nf(props.get("MonoisotopicMass")),
                    "Charge": _val_or_nf(props.get("Charge")),
                    "Complexity": _val_or_nf(props.get("Complexity"))
                }
                return row
            except Exception as e:
                self.logger.warning(f"PubChem processing error for '{qtext}': {e}")
                return self._row_not_found(str(qtext))

        # Process sequentially with progress (PubChem API is rate limited)
        rows_out: list[dict] = []
        for idx, q in enumerate(queries, start=1):
            try:
                pct = int((idx - 1) / max(1, total) * 100)
                self.report_progress(pct, f"PubChem: {idx}/{total}…")
            except Exception:
                pass
            rows_out.append(process_one(q))
            # gentle throttle to avoid hammering
            time.sleep(0.05)

        # Assemble DataFrame with stable column ordering and fill missing
        pref = self._friendly_columns_order()
        # Collect all keys seen
        all_keys: list[str] = []
        try:
            keys_set = set()
            for r in rows_out:
                for k in r.keys():
                    if k not in keys_set:
                        keys_set.add(k)
            # Start with preferred, then append others
            all_keys = [k for k in pref if k in keys_set] + [k for k in keys_set if k not in pref]
        except Exception:
            all_keys = pref

        if pd is not None:
            try:
                df = pd.DataFrame(rows_out, columns=all_keys)
                # Ensure 'query' is first
                cols = list(df.columns)
                if 'query' in cols:
                    cols = ['query'] + [c for c in cols if c != 'query']
                    df = df[cols]
            except Exception:
                df = pd.DataFrame(rows_out)
        else:
            # Fallback to list-of-dicts
            df = rows_out  # type: ignore[assignment]

        try:
            self.report_progress(100, "PubChem: completed")
        except Exception:
            pass

        return {"data": df}

    # --- Live UI update ---
    def on_result(self, result: object) -> None:  # type: ignore[override]
        try:
            # Refresh combobox options based on properties written by headless execution
            cols = self.get_property("available_query_columns") or []
            needs = bool(self.get_property("needs_user_action"))
            if hasattr(self, "_cmb_query") and self._cmb_query is not None:
                try:
                    self._cmb_query.blockSignals(True)
                    self._cmb_query.clear()
                    for c in cols:
                        self._cmb_query.addItem(str(c))
                    # Restore selected if present
                    sel = str(self.get_property("selected_column") or "")
                    if sel:
                        idx = self._cmb_query.findText(sel)
                        if idx >= 0:
                            self._cmb_query.setCurrentIndex(idx)
                finally:
                    try:
                        self._cmb_query.blockSignals(False)
                    except Exception:
                        pass
            # Show pause hint only when waiting for user input
            if needs:
                try:
                    self.show_pause("Waiting for user: select query column and click OK.")
                except Exception:
                    pass
            else:
                try:
                    # Hide pause panel if previously shown
                    if hasattr(self, 'clear_error'):
                        self.clear_error()
                except Exception:
                    pass
            # Keep geometry updated
            try:
                self._update_content_geometry(force=False)
                self.update()
            except Exception:
                pass
        except Exception:
            pass
        super().on_result(result)
