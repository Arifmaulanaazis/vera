"""StackedBarPlotNode implementation."""

from .common import *  # noqa: F401,F403

class StackedBarPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_stacked_bar", "Stacked Bar")
        self.add_input_port("table", "data")
        self.set_property("title", "Stacked Bar")
        self.set_property("category_key", "category")
        self.set_property("series_key", "series")
        self.set_property("value_key", "value")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        df = _as_dataframe((inputs or {}).get("table"))
        if df is None:
            plt.figure(figsize=(4.6, 3.6))
            plt.text(0.5, 0.5, "No data", ha="center", va="center", fontsize=12, color="gray")
            return {"plot_image": self._finish_png()}
        cat = str(self.get_property("category_key") or "category")
        ser = str(self.get_property("series_key") or "series")
        val = str(self.get_property("value_key") or "value")
        try:
            import pandas as pd  # type: ignore
            import numpy as np  # type: ignore
            pivot = df[[cat, ser, val]].copy()
            pivot[cat] = pivot[cat].astype(str)
            pivot[ser] = pivot[ser].astype(str)
            pivot[val] = pivot[val].astype(float)
            mat = pivot.pivot_table(index=cat, columns=ser, values=val, aggfunc='sum', fill_value=0.0)
            labels = list(mat.index)
            series = list(mat.columns)
            arr = mat.values
            x = np.arange(len(labels))
            plt.figure(figsize=(5.6, 3.6))
            bottom = np.zeros(len(labels))
            for i, sname in enumerate(series):
                plt.bar(x, arr[:, i], bottom=bottom, label=str(sname))
                bottom = bottom + arr[:, i]
            plt.xticks(x, labels, rotation=45, ha='right')
            plt.legend(fontsize=8, ncol=2)
            plt.title(self.get_property("title") or "Stacked Bar")
        except Exception:
            plt.figure(figsize=(4.6, 3.6))
        return {"plot_image": self._finish_png()}
