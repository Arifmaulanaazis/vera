"""ModelTestNode implementation."""

from .common import *  # noqa: F401,F403

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
