"""RadarPlotNode implementation."""

from .common import *  # noqa: F401,F403

class RadarPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_radar", "Radar Chart")
        self.add_input_port("labels", "data")
        self.add_input_port("values", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Radar Chart")
        self.set_property("label_key", "")
        self.set_property("value_key", "")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        labels = (inputs or {}).get("labels") or []
        values = _as_numeric_list((inputs or {}).get("values"))
        if (not labels or not values) and (inputs or {}).get("table") is not None:
            table = (inputs or {}).get("table")
            labels = _extract_labels_from_table(table, self.get_property("label_key"))
            values = _extract_series_from_table(table, self.get_property("value_key"))
        try:
            import numpy as np  # type: ignore
            lbls = [str(x) for x in (labels or [])]
            vals = [float(v) for v in (values or [])]
            if len(lbls) != len(vals) or len(vals) == 0:
                lbls = ["A", "B", "C", "D"]
                vals = [1, 1, 1, 1]
            # Close the polygon
            angles = np.linspace(0, 2 * np.pi, len(lbls), endpoint=False)
            vals = list(vals) + [vals[0]]
            angles = list(angles) + [angles[0]]
            plt.figure(figsize=(4.6, 4.6))
            ax = plt.subplot(111, polar=True)
            ax.plot(angles, vals, color="#4c78a8", linewidth=2)
            ax.fill(angles, vals, color="#4c78a8", alpha=0.25)
            ax.set_thetagrids([a * 180 / 3.14159 for a in angles[:-1]], lbls)
            plt.title(self.get_property("title") or "Radar Chart")
        except Exception:
            plt.figure(figsize=(4.6, 3.6))
            plt.text(0.5, 0.5, "Unable to render radar chart", ha='center', va='center')
        return {"plot_image": self._finish_png()}
