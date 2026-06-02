"""BoxPlotNode implementation."""

from .common import *  # noqa: F401,F403

class BoxPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_box", "Box Plot")
        self.add_input_port("values", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Box Plot")
        self.set_property("value_key", "")
        self.set_property("group_key", "")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        vals = (inputs or {}).get("values")
        df = _as_dataframe((inputs or {}).get("table"))
        plt.figure(figsize=(4.6, 3.6))
        try:
            if df is not None and str(self.get_property("value_key") or "") in df.columns:
                vkey = str(self.get_property("value_key"))
                gkey = str(self.get_property("group_key") or "")
                if gkey and gkey in df.columns:
                    groups = list(df[gkey].astype(str).unique())
                    data = [list(df[df[gkey].astype(str) == g][vkey].astype(float)) for g in groups]
                    plt.boxplot(data, labels=groups)
                else:
                    plt.boxplot(list(df[vkey].astype(float)))
            else:
                data = _as_numeric_list(vals)
                plt.boxplot(data if data else [])
        except Exception:
            plt.boxplot([])
        plt.title(self.get_property("title") or "Box Plot")
        return {"plot_image": self._finish_png()}
