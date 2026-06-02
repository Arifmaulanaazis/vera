"""RegressionMetricsNode implementation."""

from .common import *  # noqa: F401,F403

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
