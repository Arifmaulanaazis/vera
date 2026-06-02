"""ConfusionMatrixNode implementation."""

from .common import *  # noqa: F401,F403

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
