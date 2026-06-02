"""KDEPlotNode implementation."""

from .common import *  # noqa: F401,F403

class KDEPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_kde", "KDE Plot")
        self.add_input_port("values", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "KDE Plot")
        self.set_property("value_key", "")
        self.set_property("fill", True)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        df = _as_dataframe((inputs or {}).get("table"))
        vals = _as_numeric_list((inputs or {}).get("values"))
        plt.figure(figsize=(4.6, 3.6))
        try:
            import seaborn as sns  # type: ignore
            if df is not None and str(self.get_property("value_key") or "") in df.columns:
                vkey = str(self.get_property("value_key"))
                sns.kdeplot(x=df[vkey].astype(float), fill=bool(self.get_property("fill")))
            else:
                import pandas as pd  # type: ignore
                sns.kdeplot(x=pd.Series(vals, dtype=float), fill=bool(self.get_property("fill")))
        except Exception:
            # Fallback: histogram with density
            plt.hist(vals, bins=30, density=True, color="steelblue", alpha=0.7)
        plt.title(self.get_property("title") or "KDE Plot")
        return {"plot_image": self._finish_png()}
