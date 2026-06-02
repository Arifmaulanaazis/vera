"""DonutPlotNode implementation."""

from .common import *  # noqa: F401,F403

class DonutPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_donut", "Donut Chart")
        self.add_input_port("labels", "data")
        self.add_input_port("values", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Donut Chart")
        self.set_property("label_key", "")
        self.set_property("value_key", "")
        self.set_property("hole", 0.5)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        labels = (inputs or {}).get("labels")
        values = _as_numeric_list((inputs or {}).get("values"))
        if not labels or not values:
            table = (inputs or {}).get("table")
            labels = _extract_labels_from_table(table, self.get_property("label_key"))
            values = _extract_series_from_table(table, self.get_property("value_key"))
        plt.figure(figsize=(4, 4))
        wedges, texts = plt.pie(values, labels=labels if labels else None, startangle=90)
        # Draw center circle for donut effect
        hole = float(self.get_property("hole") or 0.5)
        import matplotlib.pyplot as _plt
        centre_circle = _plt.Circle((0, 0), radius=max(0.0, min(0.9, hole)), color="white")
        fig = _plt.gcf()
        fig.gca().add_artist(centre_circle)
        plt.title(self.get_property("title") or "Donut")
        plt.axis("equal")
        return {"plot_image": self._finish_png()}
