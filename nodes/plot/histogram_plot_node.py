"""HistogramPlotNode implementation."""

from .common import *  # noqa: F401,F403

class HistogramPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_histogram", "Histogram")
        self.add_input_port("values", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Histogram")
        self.set_property("value_key", "")  # when using table
        self.set_property("bins", 20)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        values = _as_numeric_list((inputs or {}).get("values"))
        if not values:
            table = (inputs or {}).get("table")
            key = self.get_property("value_key")
            values = _extract_series_from_table(table, key)
        plt.figure(figsize=(4.5, 3))
        bins = int(self.get_property("bins") or 20)
        plt.hist(values, bins=max(1, bins), color="steelblue", alpha=0.85)
        plt.title(self.get_property("title") or "Histogram")
        return {"plot_image": self._finish_png()}
