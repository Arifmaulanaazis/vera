"""PiePlotNode implementation."""

from .common import *  # noqa: F401,F403

class PiePlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_pie", "Pie Chart")
        self.add_input_port("labels", "data")
        self.add_input_port("values", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Pie Chart")
        self.set_property("label_key", "")
        self.set_property("value_key", "")

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
        plt.pie(values, labels=labels if labels else None, autopct="%1.1f%%", startangle=90)
        plt.title(self.get_property("title") or "Pie")
        plt.axis("equal")
        return {"plot_image": self._finish_png()}
