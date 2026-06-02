"""ClassificationReportNode implementation."""

from .common import *  # noqa: F401,F403

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
