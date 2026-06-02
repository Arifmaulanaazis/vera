"""ViolinPlotNode implementation."""

from .common import *  # noqa: F401,F403

class ViolinPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_violin", "Violin Plot")
        self.add_input_port("values", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Violin Plot")
        self.set_property("value_key", "")
        self.set_property("group_key", "")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        df = _as_dataframe((inputs or {}).get("table"))
        vals = (inputs or {}).get("values")
        plt.figure(figsize=(4.6, 3.6))
        vkey = str(self.get_property("value_key") or "")
        gkey = str(self.get_property("group_key") or "")
        try:
            if df is not None and vkey in df.columns:
                if gkey and gkey in df.columns:
                    try:
                        import seaborn as sns  # type: ignore
                        sns.violinplot(x=df[gkey].astype(str), y=df[vkey].astype(float))
                    except Exception:
                        # Fallback single violin per group via matplotlib
                        groups = list(df[gkey].astype(str).unique())
                        data = [list(df[df[gkey].astype(str) == g][vkey].astype(float)) for g in groups]
                        plt.violinplot(data, showmedians=True)
                        plt.xticks(range(1, len(groups) + 1), groups)
                else:
                    plt.violinplot(list(df[vkey].astype(float)), showmedians=True)
            else:
                data = _as_numeric_list(vals)
                plt.violinplot(data if data else [], showmedians=True)
        except Exception:
            plt.violinplot([], showmedians=True)
        plt.title(self.get_property("title") or "Violin Plot")
        return {"plot_image": self._finish_png()}
