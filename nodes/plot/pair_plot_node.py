"""PairPlotNode implementation."""

from .common import *  # noqa: F401,F403

class PairPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_pairplot", "Pair Plot")
        self.add_input_port("table", "data")
        self.set_property("title", "Pair Plot")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        df = _as_dataframe((inputs or {}).get("table"))
        if df is None:
            plt.figure(figsize=(4.6, 4.6))
            plt.text(0.5, 0.5, "No data", ha="center", va="center", fontsize=12, color="gray")
            return {"plot_image": self._finish_png()}
        try:
            import seaborn as sns  # type: ignore
            g = sns.pairplot(df.select_dtypes(include=["number"]).dropna())
            g.fig.suptitle(self.get_property("title") or "Pair Plot")
            try:
                plt.figure(g.fig.number)
            except Exception:
                pass
            return {"plot_image": self._finish_png()}
        except Exception:
            plt.figure(figsize=(4.6, 4.6))
            plt.text(0.5, 0.5, "Unable to render pair plot", ha="center", va="center", fontsize=10, color="gray")
            return {"plot_image": self._finish_png()}
