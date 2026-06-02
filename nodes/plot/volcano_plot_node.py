"""VolcanoPlotNode implementation."""

from .common import *  # noqa: F401,F403

class VolcanoPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_volcano", "Volcano Plot")
        self.add_input_port("table", "data")
        self.set_property("title", "Volcano Plot")
        self.set_property("fc_key", "log2fc")
        self.set_property("p_key", "pvalue")
        self.set_property("label_key", "")
        self.set_property("fc_thresh", 1.0)
        self.set_property("p_thresh", 0.05)
        self.set_property("top_n_labels", 10)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        df = _as_dataframe((inputs or {}).get("table"))
        if df is None:
            raise ValueError("Volcano plot requires a table with fold-change and p-values")
        fc_key = str(self.get_property("fc_key") or "log2fc")
        p_key = str(self.get_property("p_key") or "pvalue")
        label_key = str(self.get_property("label_key") or "")
        try:
            import numpy as np  # type: ignore
            x = np.array(df[fc_key], dtype=float)
            p = np.array(df[p_key], dtype=float)
            y = -np.log10(np.clip(p, 1e-300, 1.0))
        except Exception as e:
            raise ValueError(f"Invalid columns for volcano plot: {e}")

        fc_thr = float(self.get_property("fc_thresh") or 1.0)
        p_thr = float(self.get_property("p_thresh") or 0.05)
        sig = (np.abs(x) >= fc_thr) & (p <= p_thr)

        plt.figure(figsize=(5, 3.6))
        plt.scatter(x[~sig], y[~sig], s=14, c="#b0b0b0", alpha=0.7)
        plt.scatter(x[sig], y[sig], s=18, c="#d62728", alpha=0.85)
        plt.axvline(+fc_thr, color="#888888", linestyle="--", linewidth=1)
        plt.axvline(-fc_thr, color="#888888", linestyle="--", linewidth=1)
        plt.axhline(-np.log10(p_thr), color="#888888", linestyle="--", linewidth=1)
        plt.xlabel("log2 Fold Change")
        plt.ylabel("-log10 p-value")
        plt.title(self.get_property("title") or "Volcano Plot")

        # Optional top-N labels among significant points
        try:
            if label_key and label_key in df.columns:
                import numpy as np  # type: ignore
                idx = np.where(sig)[0]
                if idx.size > 0:
                    # Rank by y (significance)
                    order = np.argsort(-y[idx])
                    top_n = int(self.get_property("top_n_labels") or 10)
                    for ii in idx[order[:max(0, top_n)]]:
                        lbl = str(df.iloc[ii][label_key])
                        plt.text(x[ii], y[ii], lbl, fontsize=8, ha='left', va='bottom')
        except Exception:
            pass

        return {"plot_image": self._finish_png()}
