"""HeatmapPlotNode implementation."""

from .common import *  # noqa: F401,F403

class HeatmapPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_heatmap", "Heatmap")
        # Accept flexible inputs: matrix (list of lists) or table with numeric columns
        self.add_input_port("matrix", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Heatmap")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        import numpy as np
        matrix = (inputs or {}).get("matrix")
        if matrix is None:
            # Try to extract from a table: expect list-of-dicts numeric rows
            table = (inputs or {}).get("table") or []
            try:
                if isinstance(table, list) and table and isinstance(table[0], dict):
                    # Use all numeric values per row preserving column order
                    cols = list(table[0].keys())
                    data_rows = []
                    for row in table:
                        vals = []
                        for c in cols:
                            try:
                                vals.append(float(row.get(c, float("nan"))))
                            except Exception:
                                vals.append(float("nan"))
                        data_rows.append(vals)
                    matrix = data_rows
            except Exception:
                matrix = None
        arr = None
        try:
            if matrix is not None:
                arr = np.array(matrix, dtype=float)
        except Exception:
            arr = None
        if arr is None or arr.size == 0:
            arr = np.zeros((2, 2), dtype=float)
        plt.figure(figsize=(5, 3.6))
        im = plt.imshow(arr, aspect="auto", cmap="viridis")
        plt.colorbar(im)
        plt.title(self.get_property("title") or "Heatmap")
        return {"plot_image": self._finish_png()}
