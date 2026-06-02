"""ChromIntegrateNode implementation."""

from .common import *  # noqa: F401,F403

class ChromIntegrateNode(BaseNode):
    """Integrate areas around peaks or full curve using trapezoidal rule.

    Inputs:
      - data (data): full time-series table
      - peaks (data) optional: detected peaks table

    Outputs:
      - integrals (data): rows with region start/end/x_peak/area
    """

    def __init__(self):
        super().__init__("chrom_integrate", "Chrom Integrate")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_input_port("peaks", "data")
        self.add_output_port("integrals", "data")

        self.set_property("x_label", "x")
        self.set_property("y_label", "y")
        self.set_property("window", 0.1)  # integrate ±window in x-units if peaks provided

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        import numpy as np  # type: ignore

        df = _rows_to_dataframe((inputs or {}).get("data"))
        if df is None or len(df) == 0:
            return {"integrals": []}

        x_label = str(self.get_property("x_label") or "x")
        y_label = str(self.get_property("y_label") or "y")
        df = _ensure_numeric(df, x_label, y_label)

        peaks_rows = (inputs or {}).get("peaks")
        peaks_df = _rows_to_dataframe(peaks_rows)

        results: List[dict] = []
        if peaks_df is not None and len(peaks_df) > 0 and "x" in peaks_df.columns:
            half = float(self.get_property("window") or 0.1)
            for _, pr in peaks_df.iterrows():
                try:
                    x0 = float(pr["x"]) - half
                    x1 = float(pr["x"]) + half
                except Exception:
                    continue
                seg = df[(df[x_label] >= x0) & (df[x_label] <= x1)]
                if len(seg) < 2:
                    continue
                area = float(np.trapz(seg[y_label].values.astype(float), seg[x_label].values.astype(float)))
                results.append({
                    "x_peak": float(pr.get("x", 0.0)),
                    "start": x0,
                    "end": x1,
                    "area": max(0.0, area),
                })
        else:
            # integrate whole curve
            import numpy as np  # type: ignore
            area = float(np.trapz(df[y_label].values.astype(float), df[x_label].values.astype(float)))
            results.append({"x_peak": None, "start": float(df[x_label].min()), "end": float(df[x_label].max()), "area": max(0.0, area)})

        return {"integrals": results}
