"""ModelSaveNode implementation."""

from .common import *  # noqa: F401,F403

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
