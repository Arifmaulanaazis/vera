"""ChromSmoothingNode implementation."""

from .common import *  # noqa: F401,F403

class ChromSmoothingNode(BaseNode):
    """Smooth a time-series using Savitzky-Golay or moving average.

    Inputs:
      - data (data): list-of-dicts table with columns x_label, y_label

    Outputs:
      - data (data): smoothed series with same columns
    """

    def __init__(self):
        super().__init__("chrom_smoothing", "Chrom Smoothing")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("data", "data")

        self.set_property("method", "savgol")  # savgol|moving_average
        self.set_property("window_length", 11)
        self.set_property("polyorder", 2)
        self.set_property("ma_window", 5)
        self.set_property("x_label", "x")
        self.set_property("y_label", "y")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rows = (inputs or {}).get("data")
        df = _rows_to_dataframe(rows)
        if df is None or len(df) == 0:
            return {"data": []}

        import numpy as np  # type: ignore
        try:
            import pandas as pd  # type: ignore
        except Exception:
            return {"data": []}

        x_label = str(self.get_property("x_label") or "x")
        y_label = str(self.get_property("y_label") or "y")
        df = _ensure_numeric(df, x_label, y_label)

        method = str(self.get_property("method") or "savgol")
        if method == "savgol":
            try:
                from scipy.signal import savgol_filter  # type: ignore
                wl = int(self.get_property("window_length") or 11)
                po = int(self.get_property("polyorder") or 2)
                wl = max(3, wl | 1)  # make odd and >=3
                y_s = savgol_filter(df[y_label].values.astype(float), wl, max(1, po))
                df[y_label] = y_s
            except Exception as e:
                self.logger.error(f"Savitzky-Golay failed: {e}")
        else:
            # Moving average
            try:
                w = max(1, int(self.get_property("ma_window") or 5))
                df[y_label] = df[y_label].rolling(window=w, min_periods=1, center=True).mean()
            except Exception as e:
                self.logger.error(f"Moving average failed: {e}")

        return {"data": _dataframe_to_rows(df)}
