"""HexbinPlotNode implementation."""

from .common import *  # noqa: F401,F403

class HexbinPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_hexbin", "Hexbin Plot")
        self.add_input_port("x", "data")
        self.add_input_port("y", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Hexbin Plot")
        self.set_property("x_key", "")
        self.set_property("y_key", "")
        self.set_property("gridsize", 30)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        x = _as_numeric_list((inputs or {}).get("x"))
        y = _as_numeric_list((inputs or {}).get("y"))
        if not x or not y:
            table = (inputs or {}).get("table")
            x = _extract_series_from_table(table, self.get_property("x_key"))
            y = _extract_series_from_table(table, self.get_property("y_key"))
        plt.figure(figsize=(4.8, 3.6))
        plt.hexbin(x, y, gridsize=int(self.get_property("gridsize") or 30), cmap="viridis")
        plt.colorbar()
        plt.title(self.get_property("title") or "Hexbin")
        return {"plot_image": self._finish_png()}
