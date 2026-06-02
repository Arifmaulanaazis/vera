"""
Machine Learning nodes: train/test split and common estimators.

Nodes in this module consume table-like "data" inputs (pandas.DataFrame or
list-of-dicts) and expose configurable hyperparameters per model. They output a
trained "model" object and optional predictions/derived tables.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.nodes import BaseNode
from utils.logging_utils import get_logger


def _is_dataframe(obj: Any) -> bool:
    try:
        import pandas as pd  # type: ignore
    except Exception:
        return False
    try:
        from pandas import DataFrame as _PDDataFrame  # type: ignore
    except Exception:
        return False
    return isinstance(obj, _PDDataFrame)


def _to_dataframe(rows: Any) -> Tuple[Optional[object], List[dict]]:
    """Return (DataFrame|None, rows_list) from input rows or DataFrame.

    If pandas is not available or conversion fails, returns (None, list_of_dicts).
    """
    try:
        import pandas as pd  # type: ignore
    except Exception:
        # Normalize list-of-dicts
        if isinstance(rows, list) and (len(rows) == 0 or isinstance(rows[0], dict)):
            return None, rows  # type: ignore[return-value]
        if rows is None:
            return None, []
        if isinstance(rows, dict):
            return None, [rows]
        return None, []

    # Already a DataFrame
    if _is_dataframe(rows):
        return rows, []  # type: ignore[return-value]

    # Try list-of-dicts
    if isinstance(rows, list) and (len(rows) == 0 or isinstance(rows[0], dict)):
        try:
            df = pd.DataFrame(rows)
            return df, rows  # type: ignore[return-value]
        except Exception:
            return None, rows  # type: ignore[return-value]

    return None, []


def _numeric_columns_of(df: Any) -> List[str]:
    try:
        import pandas as pd  # type: ignore
    except Exception:
        return []
    try:
        cols = [str(c) for c in df.select_dtypes(include=["number", "bool"]).columns]
        return cols
    except Exception:
        return []


class _InlineTargetSelectorMixin:
    """Inline UI helpers for selecting a target column (combobox + OK).

    Mirrors the pattern used in PubChemSearchNode to support user-input pause.
    """

    def _build_inline_target_selector(self, label_text: str = "Target column") -> None:
        try:
            from PySide6.QtWidgets import QLabel, QComboBox, QPushButton, QHBoxLayout, QWidget

            self.width = 360
            self.height = 150
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)

            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setStyleSheet("QLabel { background: transparent; }")

            class ZIndexComboBox(QComboBox):
                def __init__(self, parent_node):
                    super().__init__()
                    self.parent_node = parent_node
                def showPopup(self):
                    try:
                        if hasattr(self.parent_node, '_content_proxy') and self.parent_node._content_proxy is not None:
                            self.parent_node._content_proxy.setZValue(15)
                    except Exception:
                        pass
                    super().showPopup()
                def hidePopup(self):
                    super().hidePopup()
                    try:
                        if hasattr(self.parent_node, '_content_proxy') and self.parent_node._content_proxy is not None:
                            self.parent_node._content_proxy.setZValue(5)
                    except Exception:
                        pass

            self._cmb_target = ZIndexComboBox(self)
            self._cmb_target.setEditable(False)
            self._btn_ok = QPushButton("OK")

            def _on_ok_clicked():
                try:
                    col = self._cmb_target.currentText()
                    if col:
                        self.set_property("target_column", col)
                        self.set_property("needs_user_action", False)
                        try:
                            if hasattr(self, 'rerun_requested'):
                                self.rerun_requested.emit(self)  # type: ignore[arg-type]
                        except Exception:
                            pass
                        try:
                            sc = self.scene()
                            view = None
                            if sc is not None and hasattr(sc, 'views'):
                                vs = sc.views()
                                view = vs[0] if isinstance(vs, (list, tuple)) and vs else None
                            if view is not None:
                                win = view.window()
                                if hasattr(win, 'workflow_manager'):
                                    win.workflow_manager.resume_user_input(self._node_id)  # type: ignore[attr-defined]
                        except Exception:
                            pass
                except Exception:
                    pass

            self._btn_ok.clicked.connect(_on_ok_clicked)

            row.addWidget(lbl)
            row.addWidget(self._cmb_target, 1)
            row.addWidget(self._btn_ok)
            container = QWidget()
            container.setStyleSheet("QWidget { background: transparent; }")
            container.setLayout(row)
            layout = self.content_layout
            if layout is not None:
                layout.addWidget(container, 0, 0)
            self._update_port_positions()
        except Exception:
            pass

    def _refresh_inline_target_options(self, columns: List[str]) -> None:
        try:
            if hasattr(self, "_cmb_target") and self._cmb_target is not None:
                self._cmb_target.blockSignals(True)
                self._cmb_target.clear()
                for c in columns:
                    self._cmb_target.addItem(str(c))
                sel = str(self.get_property("target_column") or "")
                if sel:
                    idx = self._cmb_target.findText(sel)
                    if idx >= 0:
                        self._cmb_target.setCurrentIndex(idx)
        finally:
            try:
                if hasattr(self, "_cmb_target") and self._cmb_target is not None:
                    self._cmb_target.blockSignals(False)
            except Exception:
                pass

    def on_result(self, result: object) -> None:  # type: ignore[override]
        try:
            cols = self.get_property("available_columns") or []
            if isinstance(cols, list):
                self._refresh_inline_target_options([str(c) for c in cols])
            needs = bool(self.get_property("needs_user_action"))
            if needs:
                try:
                    self.show_pause("Waiting for user: select target column and click OK.")
                except Exception:
                    pass
            else:
                try:
                    if hasattr(self, 'clear_error'):
                        self.clear_error()
                except Exception:
                    pass
            try:
                self._update_content_geometry(force=False)
                self.update()
            except Exception:
                pass
        except Exception:
            pass
        try:
            super().on_result(result)  # type: ignore[misc]
        except Exception:
            pass




class _BaseEstimatorNode(_InlineTargetSelectorMixin, BaseNode):
    """Base utilities for estimator nodes (classification/regression)."""

    def __init__(self, node_type: str, title: str):
        super().__init__(node_type, title)
        self.logger = get_logger(__name__)
        self.add_input_port("train_data", "data")
        self.add_input_port("test_data", "data")
        self.add_output_port("model", "model")
        self.add_output_port("predictions", "data")
        self.add_output_port("probabilities", "data")

        self.set_property("target_column", "")
        self.set_property("available_columns", [])
        self.set_property("needs_user_action", False)
        self.set_property("standardize", False)
        self._build_inline_target_selector()

    # ---- Helpers ----
    def _split_xy(self, table: Any) -> Tuple[object | None, List[dict], object | None]:
        df, rows = _to_dataframe(table)
        target = str(self.get_property("target_column") or "").strip()
        if df is not None:
            # Pause to ask target when ambiguous
            if not target:
                cols = [str(c) for c in list(df.columns)]
                try:
                    self.set_property("available_columns", cols)
                    self.set_property("needs_user_action", True)
                except Exception:
                    pass
                try:
                    self._manager.pause_user_input(self._node_id, "Select target column and click OK to continue.")  # type: ignore[attr-defined]
                except Exception:
                    pass
                return df.iloc[0:0], [], None
            X = df.drop(columns=[target], errors="ignore")
            y = df[target] if target in df.columns else None
            return X, [], y
        return None, rows, None

    def _prepare_features(self, X: Any, fit: bool) -> Tuple[Any, Optional[object]]:
        """Deprecated: kept for backward compatibility; no-op since we use Pipeline."""
        return X, None

    def _pack_predictions_table(self, X_ref: Any | None, y_pred: Any, y_proba: Any = None) -> List[dict]:
        rows: List[dict] = []
        try:
            import numpy as np  # type: ignore
            if X_ref is not None:
                for i, idx in enumerate(list(X_ref.index)):
                    r: dict = {"index": int(i)}
                    for col in X_ref.columns:
                        try:
                            r[str(col)] = X_ref.loc[idx, col]
                        except Exception:
                            pass
                    try:
                        r["prediction"] = y_pred[i] if hasattr(y_pred, "__len__") else y_pred
                    except Exception:
                        r["prediction"] = None
                    if y_proba is not None:
                        try:
                            # Include first class probability or full vector as string
                            prob = y_proba[i]
                            if isinstance(prob, (list, tuple, np.ndarray)):
                                r["proba"] = [float(x) for x in list(prob)]
                            else:
                                r["proba"] = float(prob)
                        except Exception:
                            r["proba"] = None
                    rows.append(r)
            else:
                # Minimal fallback
                if hasattr(y_pred, "__len__"):
                    for i, v in enumerate(y_pred):
                        rows.append({"index": i, "prediction": v})
                else:
                    rows.append({"index": 0, "prediction": y_pred})
        except Exception:
            pass
        return rows

    # ---- Execution skeleton ----
    def _fit_and_predict(self, model_ctor, inputs: Optional[Dict[str, Any]] = None, proba_supported: bool = False) -> Dict[str, Any]:
        try:
            from sklearn.base import ClassifierMixin  # type: ignore
        except Exception:
            ClassifierMixin = object  # type: ignore[assignment]

        tr = (inputs or {}).get("train_data")
        te = (inputs or {}).get("test_data")
        X_tr, rows_tr, y_tr = self._split_xy(tr)
        if X_tr is None and not rows_tr:
            raise ValueError("train_data is required and must be a table")
        if y_tr is None:
            return {"model": None, "predictions": [], "probabilities": []}

        if X_tr is not None:
            use_std = bool(self.get_property("standardize"))
            model = None
            try:
                if use_std:
                    from sklearn.pipeline import make_pipeline  # type: ignore
                    from sklearn.preprocessing import StandardScaler  # type: ignore
                    model = make_pipeline(StandardScaler(), model_ctor())
                else:
                    model = model_ctor()
            except Exception as e:
                raise RuntimeError(f"Failed to construct model: {e}")
            try:
                model.fit(X_tr, y_tr)
            except Exception as e:
                raise RuntimeError(f"Model fit failed: {e}")

            # Predict
            preds_rows: List[dict] = []
            proba_rows: List[dict] = []
            if te is not None:
                X_te, _rows_te, _y_te = self._split_xy(te)
                if X_te is not None:
                    try:
                        y_pred = model.predict(X_te)
                        preds_rows = self._pack_predictions_table(X_te, y_pred, None)
                    except Exception:
                        preds_rows = []
                    if proba_supported and isinstance(model, ClassifierMixin):
                        try:
                            if hasattr(model, "predict_proba"):
                                y_prob = model.predict_proba(X_te)
                            elif hasattr(model, "decision_function"):
                                y_prob = model.decision_function(X_te)
                            else:
                                y_prob = None
                        except Exception:
                            y_prob = None
                        if y_prob is not None:
                            proba_rows = self._pack_predictions_table(X_te, [None] * len(X_te), y_prob)
            try:
                self.report_progress(100, "Model trained")
            except Exception:
                pass
            return {"model": model, "predictions": preds_rows, "probabilities": proba_rows}

        # Fallback path for list-of-dicts not implemented (requires schema); guide user
        raise ValueError("Please provide pandas DataFrame inputs for ML nodes")


# ---- Classifiers ----









# ---- Regressors ----

# Re-export every helper/import so split node files keep the original module namespace.
__all__ = [name for name in globals() if not name.startswith("__")]
