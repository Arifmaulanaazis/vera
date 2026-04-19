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


class MLTrainTestSplitNode(_InlineTargetSelectorMixin, BaseNode):
    """Split a dataset into train/test sets with optional stratification.

    Inputs:
      - data (data): DataFrame or list-of-dicts
    Outputs:
      - train_data (data)
      - test_data (data)
    """

    def __init__(self):
        super().__init__("ml_train_test_split", "Train/Test Split")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("train_data", "data")
        self.add_output_port("test_data", "data")

        self.set_property("target_column", "")
        self.set_property("test_size", 0.2)
        self.set_property("random_state", 42)
        self.set_property("shuffle", True)
        self.set_property("stratify", True)
        self.set_property("available_columns", [])
        self.set_property("needs_user_action", False)

        self._build_inline_target_selector("Target column (optional for stratify)")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data_obj = (inputs or {}).get("data")
        df, rows = _to_dataframe(data_obj)
        if df is None and not rows:
            raise ValueError("Input 'data' is required and must be a table")

        # Decide if we need target column for stratification
        target = str(self.get_property("target_column") or "").strip()
        want_stratify = bool(self.get_property("stratify"))

        if df is not None:
            # Column selection pause if stratify requested and no target set
            if want_stratify and not target:
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
                return {"train_data": df.iloc[0:0], "test_data": df.iloc[0:0]}  # empty shells

            # Perform split using scikit-learn when available
            try:
                from sklearn.model_selection import train_test_split  # type: ignore
            except Exception as e:
                raise RuntimeError(f"scikit-learn is required: {e}")

            test_size = float(self.get_property("test_size") or 0.2)
            random_state = int(self.get_property("random_state") or 42)
            shuffle = bool(self.get_property("shuffle"))

            if want_stratify and target and target in df.columns:
                y = df[target]
                tr, te = train_test_split(df, test_size=max(0.01, min(0.99, test_size)), random_state=random_state, shuffle=shuffle, stratify=y)
            else:
                tr, te = train_test_split(df, test_size=max(0.01, min(0.99, test_size)), random_state=random_state, shuffle=shuffle)
            try:
                self.report_progress(100, "Split completed")
            except Exception:
                pass
            return {"train_data": tr, "test_data": te}

        # Fallback split for list-of-dicts
        n = len(rows)
        if n <= 1:
            return {"train_data": rows, "test_data": []}
        test_size = float(self.get_property("test_size") or 0.2)
        k = max(1, int(n * max(0.01, min(0.99, test_size))))
        return {"train_data": rows[:-k], "test_data": rows[-k:]}


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

class LogisticRegressionNode(_BaseEstimatorNode):
    def __init__(self):
        super().__init__("ml_logistic_regression", "Logistic Regression")
        self.set_property("C", 1.0)
        self.set_property("max_iter", 200)
        self.set_property("solver", "lbfgs")
        self.set_property("penalty", "l2")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        def ctor():
            from sklearn.linear_model import LogisticRegression  # type: ignore
            return LogisticRegression(C=float(self.get_property("C") or 1.0), max_iter=int(self.get_property("max_iter") or 200), solver=str(self.get_property("solver") or "lbfgs"), penalty=str(self.get_property("penalty") or "l2"))
        return self._fit_and_predict(ctor, inputs, proba_supported=True)


class RandomForestClassifierNode(_BaseEstimatorNode):
    def __init__(self):
        super().__init__("ml_random_forest_classifier", "Random Forest (Classifier)")
        self.set_property("n_estimators", 200)
        self.set_property("max_depth", 0)  # 0 => None
        self.set_property("min_samples_split", 2)
        self.set_property("random_state", 42)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        def ctor():
            from sklearn.ensemble import RandomForestClassifier  # type: ignore
            md = int(self.get_property("max_depth") or 0)
            return RandomForestClassifier(
                n_estimators=int(self.get_property("n_estimators") or 200),
                max_depth=None if md <= 0 else md,
                min_samples_split=int(self.get_property("min_samples_split") or 2),
                random_state=int(self.get_property("random_state") or 42),
                n_jobs=-1,
            )
        return self._fit_and_predict(ctor, inputs, proba_supported=True)


class SVMClassifierNode(_BaseEstimatorNode):
    def __init__(self):
        super().__init__("ml_svm_classifier", "SVM (Classifier)")
        self.set_property("kernel", "rbf")
        self.set_property("C", 1.0)
        self.set_property("gamma", "scale")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        def ctor():
            from sklearn.svm import SVC  # type: ignore
            return SVC(kernel=str(self.get_property("kernel") or "rbf"), C=float(self.get_property("C") or 1.0), gamma=self.get_property("gamma") or "scale", probability=True)
        return self._fit_and_predict(ctor, inputs, proba_supported=True)


class KNNClassifierNode(_BaseEstimatorNode):
    def __init__(self):
        super().__init__("ml_knn_classifier", "KNN (Classifier)")
        self.set_property("n_neighbors", 5)
        self.set_property("weights", "uniform")
        self.set_property("metric", "minkowski")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        def ctor():
            from sklearn.neighbors import KNeighborsClassifier  # type: ignore
            return KNeighborsClassifier(n_neighbors=int(self.get_property("n_neighbors") or 5), weights=str(self.get_property("weights") or "uniform"), metric=str(self.get_property("metric") or "minkowski"))
        return self._fit_and_predict(ctor, inputs, proba_supported=True)


# ---- Regressors ----

class LinearRegressionNode(_BaseEstimatorNode):
    def __init__(self):
        super().__init__("ml_linear_regression", "Linear Regression")
        self.set_property("fit_intercept", True)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        def ctor():
            from sklearn.linear_model import LinearRegression  # type: ignore
            return LinearRegression(fit_intercept=bool(self.get_property("fit_intercept")))
        # Regressors don't provide predict_proba
        return self._fit_and_predict(ctor, inputs, proba_supported=False)


class RandomForestRegressorNode(_BaseEstimatorNode):
    def __init__(self):
        super().__init__("ml_random_forest_regressor", "Random Forest (Regressor)")
        self.set_property("n_estimators", 200)
        self.set_property("max_depth", 0)
        self.set_property("min_samples_split", 2)
        self.set_property("random_state", 42)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        def ctor():
            from sklearn.ensemble import RandomForestRegressor  # type: ignore
            md = int(self.get_property("max_depth") or 0)
            return RandomForestRegressor(
                n_estimators=int(self.get_property("n_estimators") or 200),
                max_depth=None if md <= 0 else md,
                min_samples_split=int(self.get_property("min_samples_split") or 2),
                random_state=int(self.get_property("random_state") or 42),
                n_jobs=-1,
            )
        return self._fit_and_predict(ctor, inputs, proba_supported=False)


class SVRNode(_BaseEstimatorNode):
    def __init__(self):
        super().__init__("ml_svr", "SVR")
        self.set_property("kernel", "rbf")
        self.set_property("C", 1.0)
        self.set_property("epsilon", 0.1)
        self.set_property("gamma", "scale")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        def ctor():
            from sklearn.svm import SVR  # type: ignore
            return SVR(kernel=str(self.get_property("kernel") or "rbf"), C=float(self.get_property("C") or 1.0), epsilon=float(self.get_property("epsilon") or 0.1), gamma=self.get_property("gamma") or "scale")
        return self._fit_and_predict(ctor, inputs, proba_supported=False)


