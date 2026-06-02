"""ChromPeakDetectNode implementation."""

from .common import *  # noqa: F401,F403

class ChromPeakDetectNode(BaseNode):
    """Detect peaks using scipy.signal.find_peaks.

    Inputs:
      - data (data): list-of-dicts table

    Outputs:
      - peaks (data): table with columns index, x, y, prominence, width
    """

    def __init__(self):
        super().__init__("chrom_peak_detect", "Chrom Peak Detect")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("peaks", "data")

        self.set_property("x_label", "x")
        self.set_property("y_label", "y")
        self.set_property("height", None)
        self.set_property("prominence", 0.0)
        self.set_property("distance", 0)
        self.set_property("width", 0)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rows = (inputs or {}).get("data")
        df = _rows_to_dataframe(rows)
        if df is None or len(df) == 0:
            return {"peaks": []}

        import numpy as np  # type: ignore
        from scipy.signal import find_peaks, peak_prominences, peak_widths  # type: ignore

        x_label = str(self.get_property("x_label") or "x")
        y_label = str(self.get_property("y_label") or "y")
        df = _ensure_numeric(df, x_label, y_label)

        series = df[y_label].values.astype(float)
        kw: Dict[str, Any] = {}
        h = self.get_property("height")
        if h is not None:
            try:
                kw["height"] = float(h)
            except Exception:
                pass
        p = float(self.get_property("prominence") or 0.0)
        if p and p > 0:
            kw["prominence"] = p
        d = int(self.get_property("distance") or 0)
        if d and d > 0:
            kw["distance"] = d
        w = int(self.get_property("width") or 0)
        if w and w > 0:
            kw["width"] = w

        idxs, _props = find_peaks(series, **kw)
        if idxs is None or len(idxs) == 0:
            return {"peaks": []}

        prom, _, _ = peak_prominences(series, idxs)
        widths, w_heights, left_ips, right_ips = peak_widths(series, idxs, rel_height=0.5)

        out: List[dict] = []
        for i, idx in enumerate(list(idxs)):
            try:
                out.append({
                    "index": int(idx),
                    "x": float(df.iloc[idx][x_label]),
                    "y": float(df.iloc[idx][y_label]),
                    "prominence": float(prom[i]) if i < len(prom) else None,
                    "width": float(widths[i]) if i < len(widths) else None,
                })
            except Exception:
                pass

        return {"peaks": out}
