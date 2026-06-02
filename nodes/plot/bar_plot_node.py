"""BarPlotNode implementation."""

from .common import *  # noqa: F401,F403

class BarPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_bar", "Bar Plot")
        self.add_input_port("categories", "data")
        self.add_input_port("values", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Bar Plot")
        self.set_property("label_key", "")
        self.set_property("value_key", "")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        labels: list[str] = [str(x) for x in (inputs or {}).get("categories", [])]
        values = _as_numeric_list((inputs or {}).get("values"))
        if not labels or not values:
            table = (inputs or {}).get("table")
            labels = _extract_labels_from_table(table, self.get_property("label_key"))
            values = _extract_series_from_table(table, self.get_property("value_key"))
        plt.figure(figsize=(4.8, 3))
        import numpy as np
        idx = np.arange(len(values))
        plt.bar(idx, values, color="seagreen", alpha=0.85)
        if labels:
            plt.xticks(idx, labels, rotation=45, ha="right")
        plt.title(self.get_property("title") or "Bar")
        return {"plot_image": self._finish_png()}
