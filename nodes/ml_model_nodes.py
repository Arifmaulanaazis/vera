"""
ML model management nodes: save/load models, evaluate/test with metrics, batch predict.

Models are treated as generic scikit-learn style estimators/pipelines.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import os
import pickle

from core.nodes import BaseNode
from utils.logging_utils import get_logger


def _rows_to_dataframe(rows: Any):
    try:
        import pandas as pd  # type: ignore
    except Exception:
        return None
    if rows is None:
        return None
    try:
        from pandas import DataFrame as _PDDataFrame  # type: ignore
        if isinstance(rows, _PDDataFrame):
            return rows
    except Exception:
        pass
    if isinstance(rows, list) and (len(rows) == 0 or isinstance(rows[0], dict)):
        try:
            return pd.DataFrame(rows)
        except Exception:
            return None
    return None


def _df_to_rows(df: Any) -> List[dict]:
    try:
        return [] if df is None else df.to_dict("records")  # type: ignore
    except Exception:
        return []


class ModelLoadNode(BaseNode):
    """Load a saved model from disk (.pkl).

    Inputs:
      - file (file): path to .pkl

    Outputs:
      - model (model)
    """

    def __init__(self):
        super().__init__("ml_model_load", "Model Load (.pkl)")
        self.logger = get_logger(__name__)
        self.add_input_port("file", "file")
        self.add_output_port("model", "model")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        path = (inputs or {}).get("file")
        if not isinstance(path, str) or not path:
            return {"model": None}
        try:
            with open(path, "rb") as f:
                obj = pickle.load(f)
            # If file stores dict with 'model', unwrap; else pass-through
            if isinstance(obj, dict) and "model" in obj:
                return {"model": obj.get("model")}
            return {"model": obj}
        except Exception as e:
            self.logger.error(f"Failed to load model: {e}")
            return {"model": None}


class ModelSaveNode(BaseNode):
    """Save a model to disk (.pkl).

    Inputs:
      - model (model)
      - file (file) optional: destination path. If not provided, uses working dir and name.

    Outputs:
      - file (file): saved path
    """

    def __init__(self):
        super().__init__("ml_model_save", "Model Save (.pkl)")
        self.logger = get_logger(__name__)
        self.add_input_port("model", "model")
        self.add_input_port("file", "file")
        self.add_output_port("file", "file")

        self.set_property("filename", "saved_model.pkl")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        model = (inputs or {}).get("model")
        dst = (inputs or {}).get("file")
        if not dst or not isinstance(dst, str) or not dst.strip():
            dst = str(self.get_property("filename") or "saved_model.pkl")
        try:
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            with open(dst, "wb") as f:
                pickle.dump({"model": model}, f)
            return {"file": dst}
        except Exception as e:
            self.logger.error(f"Failed to save model: {e}")
            return {"file": ""}


class ModelTestNode(BaseNode):
    """Evaluate model on a dataset with a target column.

    Inputs:
      - model (model)
      - data (data): DataFrame/list-of-dicts including features and target

    Outputs:
      - metrics (data): MAE/MSE/R2
      - predictions (data): optional table of predictions
    """

    def __init__(self):
        super().__init__("ml_model_test", "Model Test")
        self.logger = get_logger(__name__)
        self.add_input_port("model", "model")
        self.add_input_port("data", "data")
        self.add_output_port("metrics", "data")
        self.add_output_port("predictions", "data")

        self.set_property("target_column", "target")
        self.set_property("include_predictions", True)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        model = (inputs or {}).get("model")
        df = _rows_to_dataframe((inputs or {}).get("data"))
        if model is None or df is None or len(df) == 0:
            return {"metrics": [], "predictions": []}

        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score  # type: ignore

        target = str(self.get_property("target_column") or "target")
        if target not in df.columns:
            return {"metrics": [], "predictions": []}

        X = df.drop(columns=[target], errors="ignore")
        y = df[target]
        try:
            y_pred = model.predict(X.values)
        except Exception as e:
            self.logger.error(f"Model prediction failed: {e}")
            return {"metrics": [], "predictions": []}

        mae = float(mean_absolute_error(y, y_pred))
        mse = float(mean_squared_error(y, y_pred))
        r2 = float(r2_score(y, y_pred))
        metrics = [{"mae": mae, "mse": mse, "r2": r2}]

        preds_rows: List[dict] = []
        if bool(self.get_property("include_predictions")):
            try:
                for i, val in enumerate(list(y_pred)):
                    preds_rows.append({"index": i, "prediction": float(val)})
            except Exception:
                pass
        return {"metrics": metrics, "predictions": preds_rows}


class ModelPredictNode(BaseNode):
    """Batch prediction for a dataset without target.

    Inputs:
      - model (model)
      - data (data)

    Outputs:
      - predictions (data)
    """

    def __init__(self):
        super().__init__("ml_model_predict", "Model Predict")
        self.logger = get_logger(__name__)
        self.add_input_port("model", "model")
        self.add_input_port("data", "data")
        self.add_output_port("predictions", "data")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        model = (inputs or {}).get("model")
        df = _rows_to_dataframe((inputs or {}).get("data"))
        if model is None or df is None or len(df) == 0:
            return {"predictions": []}
        try:
            y_pred = model.predict(df.values)
        except Exception as e:
            self.logger.error(f"Model prediction failed: {e}")
            return {"predictions": []}
        rows: List[dict] = []
        try:
            for i, val in enumerate(list(y_pred)):
                rows.append({"index": i, "prediction": float(val)})
        except Exception:
            pass
        return {"predictions": rows}


