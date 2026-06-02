"""ChromBaselineNode implementation."""

from .common import *  # noqa: F401,F403

class ChromBaselineNode(BaseNode):
    """Baseline correction using rolling quantile or rolling min.

    Inputs:
      - data (data): list-of-dicts table with columns x_label, y_label

    Outputs:
      - data (data): baseline-corrected series with same columns
      - baseline (data): baseline series
    """

    def __init__(self):
        super().__init__("chrom_baseline", "Chrom Baseline")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("data", "data")
        self.add_output_port("baseline", "data")

        self.set_property("method", "quantile")  # quantile|min
        self.set_property("window", 51)
        self.set_property("quantile", 0.05)
        self.set_property("x_label", "x")
        self.set_property("y_label", "y")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rows = (inputs or {}).get("data")
        df = _rows_to_dataframe(rows)
        if df is None or len(df) == 0:
            return {"data": [], "baseline": []}

        try:
            import pandas as pd  # type: ignore
        except Exception:
            return {"data": [], "baseline": []}

        x_label = str(self.get_property("x_label") or "x")
        y_label = str(self.get_property("y_label") or "y")
        df = _ensure_numeric(df, x_label, y_label)

        method = str(self.get_property("method") or "quantile")
        window = max(3, int(self.get_property("window") or 51))

        bl = None
        if method == "quantile":
            q = float(self.get_property("quantile") or 0.05)
            try:
                bl = df[y_label].rolling(window=window, min_periods=1, center=True).quantile(q)
            except Exception as e:
                self.logger.error(f"Quantile baseline failed: {e}")
        else:
            try:
                bl = df[y_label].rolling(window=window, min_periods=1, center=True).min()
            except Exception as e:
                self.logger.error(f"Min baseline failed: {e}")

        if bl is None:
            return {"data": _dataframe_to_rows(df), "baseline": []}

        base_df = df[[x_label]].copy()
        base_df["baseline"] = bl.values

        out_df = df.copy()
        try:
            out_df[y_label] = (df[y_label] - bl).clip(lower=0)
        except Exception:
            out_df[y_label] = df[y_label]

        return {"data": _dataframe_to_rows(out_df), "baseline": _dataframe_to_rows(base_df)}
