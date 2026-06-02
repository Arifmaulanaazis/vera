"""ChromViewerNode implementation."""

from .common import *  # noqa: F401,F403

class ChromViewerNode(BaseNode):
    """Plot time-series and optional peaks to PNG bytes.

    Inputs:
      - data (data): series
      - peaks (data) optional

    Outputs:
      - image (image): PNG bytes
    """

    def __init__(self):
        super().__init__("chrom_viewer", "Chrom Viewer")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_input_port("peaks", "data")
        self.add_output_port("image", "image")

        self.set_property("x_label", "x")
        self.set_property("y_label", "y")
        self.set_property("title", "Chromatogram/Spectrum")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rows = (inputs or {}).get("data")
        df = _rows_to_dataframe(rows)
        if df is None or len(df) == 0:
            return {"image": b""}

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore
        import numpy as np  # type: ignore

        peaks_df = _rows_to_dataframe((inputs or {}).get("peaks"))

        x_label = str(self.get_property("x_label") or "x")
        y_label = str(self.get_property("y_label") or "y")
        title = str(self.get_property("title") or "Chromatogram/Spectrum")

        df = _ensure_numeric(df, x_label, y_label)

        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(df[x_label].values, df[y_label].values, color="#2E5C8A", lw=1.2)
        if peaks_df is not None and len(peaks_df) > 0 and "x" in peaks_df.columns:
            try:
                ax.scatter(peaks_df["x"].values, peaks_df.get("y", None) if "y" in peaks_df.columns else None, color="#EF4444", s=20, zorder=3, label="Peaks")
                ax.legend(loc="best")
            except Exception:
                pass
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        ax.set_title(title)
        ax.grid(alpha=0.2)
        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format="png", dpi=150)
        plt.close(fig)
        return {"image": buf.getvalue()}
