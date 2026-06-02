"""ECDFPlotNode implementation."""

from .common import *  # noqa: F401,F403

class ECDFPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_ecdf", "ECDF Plot")
        self.add_input_port("values", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "ECDF Plot")
        self.set_property("value_key", "")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        vals = _as_numeric_list((inputs or {}).get("values"))
        if not vals and (inputs or {}).get("table") is not None:
            vals = _extract_series_from_table((inputs or {}).get("table"), self.get_property("value_key"))
        vals = [v for v in vals if v == v]  # drop NaNs
        try:
            import numpy as np  # type: ignore
            x = np.sort(np.array(vals, dtype=float))
            if x.size == 0:
                x = np.array([0.0])
            y = np.arange(1, x.size + 1) / x.size
        except Exception:
            x = []
            y = []
        plt.figure(figsize=(4.6, 3.6))
        plt.step(x, y, where='post')
        plt.ylim(0, 1)
        plt.title(self.get_property("title") or "ECDF Plot")
        return {"plot_image": self._finish_png()}
