"""ScatterPlotNode implementation."""

from .common import *  # noqa: F401,F403

class ScatterPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_scatter", "Scatter")
        self.add_input_port("x", "data")
        self.add_input_port("y", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Scatter")
        self.set_property("x_key", "")
        self.set_property("y_key", "")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        x = _as_numeric_list((inputs or {}).get("x"))
        y = _as_numeric_list((inputs or {}).get("y"))
        if not x or not y:
            table = (inputs or {}).get("table")
            x = _extract_series_from_table(table, self.get_property("x_key"))
            y = _extract_series_from_table(table, self.get_property("y_key"))
        plt.figure(figsize=(4.5, 3))
        plt.scatter(x, y, s=18, c="tomato", alpha=0.8)
        plt.title(self.get_property("title") or "Scatter")
        return {"plot_image": self._finish_png()}
