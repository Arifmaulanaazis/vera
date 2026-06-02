"""BubblePlotNode implementation."""

from .common import *  # noqa: F401,F403

class BubblePlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_bubble", "Bubble Plot")
        self.add_input_port("x", "data")
        self.add_input_port("y", "data")
        self.add_input_port("size", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Bubble Plot")
        self.set_property("x_key", "")
        self.set_property("y_key", "")
        self.set_property("size_key", "")
        self.set_property("size_scale", 20.0)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        x = _as_numeric_list((inputs or {}).get("x"))
        y = _as_numeric_list((inputs or {}).get("y"))
        s = _as_numeric_list((inputs or {}).get("size"))
        if not (x and y and s):
            table = (inputs or {}).get("table")
            x = _extract_series_from_table(table, self.get_property("x_key"))
            y = _extract_series_from_table(table, self.get_property("y_key"))
            s = _extract_series_from_table(table, self.get_property("size_key"))
        scale = float(self.get_property("size_scale") or 20.0)
        plt.figure(figsize=(4.8, 3.6))
        try:
            import numpy as np  # type: ignore
            sizes = (np.array(s, dtype=float) if s else 1.0) * scale
        except Exception:
            sizes = 20.0
        plt.scatter(x, y, s=sizes, c="#1f77b4", alpha=0.7)
        plt.title(self.get_property("title") or "Bubble Plot")
        return {"plot_image": self._finish_png()}
