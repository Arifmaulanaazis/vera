"""Venn2PlotNode implementation."""

from .common import *  # noqa: F401,F403

class Venn2PlotNode(_BasePlotNode):
    """Two-set Venn diagram without external deps.

    Inputs:
      - set_a (data): list of hashable items
      - set_b (data): list of hashable items
      - table (data): optional list-of-dicts/DataFrame; use properties a_key/b_key as columns forming sets
    Properties:
      - title, label_a, label_b, a_key, b_key
    Output:
      - plot_image (image)
    """

    def __init__(self):
        super().__init__("plot_venn", "Venn Diagram (2-Set)")
        self.add_input_port("set_a", "data")
        self.add_input_port("set_b", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Venn Diagram")
        self.set_property("label_a", "A")
        self.set_property("label_b", "B")
        self.set_property("a_key", "")
        self.set_property("b_key", "")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        a_vals = (inputs or {}).get("set_a")
        b_vals = (inputs or {}).get("set_b")
        if (not a_vals or not b_vals) and (inputs or {}).get("table") is not None:
            df = _as_dataframe((inputs or {}).get("table"))
            a_key = str(self.get_property("a_key") or "").strip()
            b_key = str(self.get_property("b_key") or "").strip()
            if df is not None and a_key and b_key and a_key in df.columns and b_key in df.columns:
                try:
                    a_vals = list(df[a_key])  # type: ignore
                    b_vals = list(df[b_key])  # type: ignore
                except Exception:
                    a_vals, b_vals = [], []
        try:
            set_a = set([str(x) for x in (a_vals or [])])
            set_b = set([str(x) for x in (b_vals or [])])
        except Exception:
            set_a, set_b = set(), set()

        only_a = len(set_a - set_b)
        only_b = len(set_b - set_a)
        both = len(set_a & set_b)

        # Draw simple overlapping circles
        import numpy as np  # type: ignore
        plt.figure(figsize=(4.6, 3.6))
        ax = plt.gca()
        ax.set_aspect('equal')
        ax.axis('off')
        # Circle params
        r = 1.4
        c1 = (0.8, 0)
        c2 = (2.0, 0)
        theta = np.linspace(0, 2 * np.pi, 200)
        x1 = c1[0] + r * np.cos(theta)
        y1 = c1[1] + r * np.sin(theta)
        x2 = c2[0] + r * np.cos(theta)
        y2 = c2[1] + r * np.sin(theta)
        ax.fill(x1, y1, color="#4c78a8", alpha=0.35, linewidth=2, edgecolor="#4c78a8")
        ax.fill(x2, y2, color="#f58518", alpha=0.35, linewidth=2, edgecolor="#f58518")
        # Labels
        ax.text(c1[0] - 0.1, c1[1] + r + 0.2, str(self.get_property("label_a") or "A"), ha='center', va='bottom', fontsize=10)
        ax.text(c2[0] + 0.1, c2[1] + r + 0.2, str(self.get_property("label_b") or "B"), ha='center', va='bottom', fontsize=10)
        # Counts positions (approximate)
        ax.text(c1[0] - 0.5, 0, str(only_a), ha='center', va='center', fontsize=11, weight='bold')
        ax.text((c1[0] + c2[0]) / 2, 0, str(both), ha='center', va='center', fontsize=11, weight='bold')
        ax.text(c2[0] + 0.5, 0, str(only_b), ha='center', va='center', fontsize=11, weight='bold')
        plt.title(self.get_property("title") or "Venn Diagram")
        return {"plot_image": self._finish_png()}
