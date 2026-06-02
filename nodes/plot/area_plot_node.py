"""AreaPlotNode implementation."""

from .common import *  # noqa: F401,F403

class AreaPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_area", "Area Plot")
        self.add_input_port("x", "data")
        self.add_input_port("y", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Area Plot")
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
        plt.figure(figsize=(4.8, 3.6))
        try:
            import numpy as np  # type: ignore
            if not x:
                x = list(range(len(y)))
            plt.fill_between(x, y, step=None, alpha=0.6, color="#4c78a8")
        except Exception:
            pass
        plt.title(self.get_property("title") or "Area Plot")
        return {"plot_image": self._finish_png()}
