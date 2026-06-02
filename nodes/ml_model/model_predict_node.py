"""ModelPredictNode implementation."""

from .common import *  # noqa: F401,F403

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
