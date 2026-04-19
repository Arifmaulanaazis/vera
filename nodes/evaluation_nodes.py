"""
Model evaluation nodes: confusion matrix, classification report, regression metrics.

Inputs are typically predictions and optionally ground-truth labels, or a
trained model plus test_data and target column.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.nodes import BaseNode
from utils.logging_utils import get_logger


def _as_dataframe(obj: Any):
    try:
        import pandas as pd  # type: ignore
    except Exception:
        return None
    if isinstance(obj, pd.DataFrame):
        return obj
    if isinstance(obj, list) and (len(obj) == 0 or isinstance(obj[0], dict)):
        try:
            return pd.DataFrame(obj)
        except Exception:
            return None
    return None


def _extract_target_series(table: Any, target_column: str) -> List[Any]:
    if not target_column:
        return []
    df = _as_dataframe(table)
    if df is not None and target_column in df.columns:
        try:
            return list(df[target_column])  # type: ignore[list-item]
        except Exception:
            return []
    # Fallback list-of-dicts
    if isinstance(table, list) and (len(table) == 0 or isinstance(table[0], dict)):
        out: List[Any] = []
        for r in table:
            try:
                out.append(r.get(target_column))  # type: ignore[union-attr]
            except Exception:
                out.append(None)
        return out
    return []


class ConfusionMatrixNode(BaseNode):
    """Compute confusion matrix and emit matrix as data and optional heatmap image.

    Inputs:
      - predictions (data): list-of-dicts with key 'prediction' or a DataFrame with 'prediction' column
      - test_data (data): to extract ground-truth by target_column
    Outputs:
      - matrix (data): list[list[int]]
      - plot_image (image): PNG bytes (optional)
    """

    def __init__(self):
        super().__init__("eval_confusion_matrix", "Confusion Matrix")
        self.logger = get_logger(__name__)
        self.add_input_port("predictions", "data")
        self.add_input_port("test_data", "data")
        self.add_output_port("matrix", "data")
        self.add_output_port("plot_image", "image")

        self.set_property("target_column", "")
        self.set_property("normalize", "none")  # none, true, pred
        self.set_property("title", "Confusion Matrix")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        preds_tbl = (inputs or {}).get("predictions")
        test_tbl = (inputs or {}).get("test_data")
        target = str(self.get_property("target_column") or "").strip()

        # Extract y_true and y_pred
        y_true = _extract_target_series(test_tbl, target)
        y_pred: List[Any] = []
        dfp = _as_dataframe(preds_tbl)
        if dfp is not None:
            key = "prediction" if "prediction" in dfp.columns else (dfp.columns[-1] if len(dfp.columns) > 0 else None)
            if key is not None:
                try:
                    y_pred = list(dfp[key])  # type: ignore[list-item]
                except Exception:
                    y_pred = []
        elif isinstance(preds_tbl, list) and (len(preds_tbl) == 0 or isinstance(preds_tbl[0], dict)):
            for r in preds_tbl:
                try:
                    y_pred.append(r.get("prediction"))  # type: ignore[union-attr]
                except Exception:
                    y_pred.append(None)

        if not y_true or not y_pred:
            raise ValueError("Missing predictions or ground-truth labels")

        try:
            from sklearn.metrics import confusion_matrix  # type: ignore
        except Exception as e:
            raise RuntimeError(f"scikit-learn is required: {e}")

        normalize = str(self.get_property("normalize") or "none")
        norm = None
        if normalize == "true":
            norm = "true"
        elif normalize == "pred":
            norm = "pred"
        cm = confusion_matrix(y_true, y_pred, normalize=norm)

        # Always return the numeric matrix as list-of-lists
        matrix_rows: List[List[float]] = []
        try:
            import numpy as np  # type: ignore
            arr = np.array(cm)
            for i in range(arr.shape[0]):
                matrix_rows.append([float(x) for x in arr[i].tolist()])
        except Exception:
            # Best-effort conversion
            try:
                matrix_rows = [[float(v) for v in row] for row in cm]  # type: ignore[assignment]
            except Exception:
                matrix_rows = []

        # Optional heatmap image
        plot_bytes: bytes = b""
        try:
            from utils.mpl_utils import import_pyplot_non_interactive
            plt = import_pyplot_non_interactive()
            import numpy as np  # type: ignore
            plt.figure(figsize=(4.6, 3.6))
            im = plt.imshow(np.array(matrix_rows), cmap="Blues")
            plt.colorbar(im)
            plt.title(self.get_property("title") or "Confusion Matrix")
            # Save to PNG
            import io
            buf = io.BytesIO()
            plt.tight_layout()
            plt.savefig(buf, format="png", dpi=200)
            plt.close()
            plot_bytes = buf.getvalue()
        except Exception:
            plot_bytes = b""

        try:
            self.report_progress(100, "Confusion matrix computed")
        except Exception:
            pass

        return {"matrix": matrix_rows, "plot_image": plot_bytes}


class ClassificationReportNode(BaseNode):
    """Generate a text classification report (precision/recall/F1) and a table."""

    def __init__(self):
        super().__init__("eval_classification_report", "Classification Report")
        self.logger = get_logger(__name__)
        self.add_input_port("predictions", "data")
        self.add_input_port("test_data", "data")
        self.add_output_port("report_text", "string")
        self.add_output_port("report_table", "data")

        self.set_property("target_column", "")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        preds_tbl = (inputs or {}).get("predictions")
        test_tbl = (inputs or {}).get("test_data")
        target = str(self.get_property("target_column") or "").strip()

        y_true = _extract_target_series(test_tbl, target)
        y_pred: List[Any] = []
        dfp = _as_dataframe(preds_tbl)
        if dfp is not None:
            key = "prediction" if "prediction" in dfp.columns else (dfp.columns[-1] if len(dfp.columns) > 0 else None)
            if key is not None:
                try:
                    y_pred = list(dfp[key])  # type: ignore[list-item]
                except Exception:
                    y_pred = []
        elif isinstance(preds_tbl, list) and (len(preds_tbl) == 0 or isinstance(preds_tbl[0], dict)):
            for r in preds_tbl:
                try:
                    y_pred.append(r.get("prediction"))  # type: ignore[union-attr]
                except Exception:
                    y_pred.append(None)

        if not y_true or not y_pred:
            raise ValueError("Missing predictions or ground-truth labels")

        try:
            from sklearn.metrics import classification_report  # type: ignore
            import pandas as pd  # type: ignore
        except Exception as e:
            raise RuntimeError(f"scikit-learn (and pandas) required: {e}")

        rep = classification_report(y_true, y_pred, output_dict=True)
        try:
            df = pd.DataFrame(rep).transpose()
            table = df.reset_index().rename(columns={"index": "label"}).to_dict(orient="records")
        except Exception:
            table = []
        try:
            from sklearn.metrics import classification_report as _cr
            text = _cr(y_true, y_pred)
        except Exception:
            text = ""

        return {"report_text": text, "report_table": table}


class RegressionMetricsNode(BaseNode):
    """Compute MAE/MSE/R2 given true vs predicted values.

    Inputs:
      - predictions (data): table with 'prediction' column or list-of-dicts
      - test_data (data): table with true target column
    Outputs:
      - metrics (data): single-row table with MAE, MSE, R2
    """

    def __init__(self):
        super().__init__("eval_regression_metrics", "Regression Metrics")
        self.logger = get_logger(__name__)
        self.add_input_port("predictions", "data")
        self.add_input_port("test_data", "data")
        self.add_output_port("metrics", "data")
        self.set_property("target_column", "")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        preds_tbl = (inputs or {}).get("predictions")
        test_tbl = (inputs or {}).get("test_data")
        target = str(self.get_property("target_column") or "").strip()

        y_true = _extract_target_series(test_tbl, target)
        y_pred: List[float] = []
        dfp = _as_dataframe(preds_tbl)
        if dfp is not None:
            key = "prediction" if "prediction" in dfp.columns else (dfp.columns[-1] if len(dfp.columns) > 0 else None)
            if key is not None:
                try:
                    y_pred = [float(x) for x in list(dfp[key])]  # type: ignore[list-item]
                except Exception:
                    y_pred = []
        elif isinstance(preds_tbl, list) and (len(preds_tbl) == 0 or isinstance(preds_tbl[0], dict)):
            for r in preds_tbl:
                try:
                    y_pred.append(float(r.get("prediction")))  # type: ignore[arg-type]
                except Exception:
                    y_pred.append(float("nan"))

        if not y_true or not y_pred:
            raise ValueError("Missing predictions or ground-truth values")

        try:
            from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score  # type: ignore
        except Exception as e:
            raise RuntimeError(f"scikit-learn is required: {e}")

        try:
            mae = float(mean_absolute_error(y_true, y_pred))
        except Exception:
            mae = float("nan")
        try:
            mse = float(mean_squared_error(y_true, y_pred))
        except Exception:
            mse = float("nan")
        try:
            r2 = float(r2_score(y_true, y_pred))
        except Exception:
            r2 = float("nan")

        return {"metrics": [{"MAE": mae, "MSE": mse, "R2": r2}]}


