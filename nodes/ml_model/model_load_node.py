"""ModelLoadNode implementation."""

from .common import *  # noqa: F401,F403

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
