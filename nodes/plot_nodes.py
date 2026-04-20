"""
Plotting nodes for the VERA workflow canvas.

Nodes in this module produce PNG image bytes on their output, suitable for
displaying with the `image_view` node or saving via `file_output`.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from core.nodes import BaseNode
from utils.logging_utils import get_logger


def _as_numeric_list(values: Any) -> list[float]:
    if values is None:
        return []
    if isinstance(values, (list, tuple)):
        result: list[float] = []
        for v in values:
            try:
                if isinstance(v, (int, float)):
                    result.append(float(v))
                else:
                    # try str -> float
                    result.append(float(str(v)))
            except Exception:
                # skip non-numeric
                continue
        return result
    # Single scalar
    try:
        return [float(values)]
    except Exception:
        return []


def _as_dataframe(obj: Any):
    try:
        import pandas as pd  # type: ignore
    except Exception:
        return None
    if obj is None:
        return None
    if isinstance(obj, pd.DataFrame):
        return obj
    if isinstance(obj, list) and (len(obj) == 0 or isinstance(obj[0], dict)):
        try:
            return pd.DataFrame(obj)
        except Exception:
            return None
    return None


def _extract_series_from_table(table: Any, key: Optional[str]) -> list[float]:
    if not key:
        return []
    if isinstance(table, list) and (len(table) == 0 or isinstance(table[0], dict)):
        out: list[float] = []
        for row in table:
            try:
                out.append(float(row.get(key, None)))
            except Exception:
                out.append(float("nan"))
        return out
    return []


def _extract_labels_from_table(table: Any, key: Optional[str]) -> list[str]:
    if not key:
        return []
    if isinstance(table, list) and (len(table) == 0 or isinstance(table[0], dict)):
        out: list[str] = []
        for row in table:
            out.append(str(row.get(key, "")))
        return out
    return []


class _BasePlotNode(BaseNode):
    def __init__(self, node_type: str, title: str):
        super().__init__(node_type, title)
        self.logger = get_logger(__name__)
        # All plots output image bytes
        self.add_output_port("plot_image", "image")
        # Standard node body size
        self.width = 280
        self.height = 160
        self.setMinimumSize(self.width, self.height)
        self.setMaximumSize(self.width, self.height)

    def _finish_png(self) -> bytes:
        import io
        buf = io.BytesIO()
        try:
            from utils.mpl_utils import import_pyplot_non_interactive
            plt = import_pyplot_non_interactive()
            plt.tight_layout()
            plt.savefig(buf, format="png", dpi=200)
            plt.close()
        except Exception:
            pass
        return buf.getvalue()


class HistogramPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_histogram", "Histogram")
        self.add_input_port("values", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Histogram")
        self.set_property("value_key", "")  # when using table
        self.set_property("bins", 20)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        values = _as_numeric_list((inputs or {}).get("values"))
        if not values:
            table = (inputs or {}).get("table")
            key = self.get_property("value_key")
            values = _extract_series_from_table(table, key)
        plt.figure(figsize=(4.5, 3))
        bins = int(self.get_property("bins") or 20)
        plt.hist(values, bins=max(1, bins), color="steelblue", alpha=0.85)
        plt.title(self.get_property("title") or "Histogram")
        return {"plot_image": self._finish_png()}


class ScatterPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_scatter", "Scatter")
        self.add_input_port("x", "data")
        self.add_input_port("y", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Scatter")
        self.set_property("x_key", "")
        self.set_property("y_key", "")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        x = _as_numeric_list((inputs or {}).get("x"))
        y = _as_numeric_list((inputs or {}).get("y"))
        if not x or not y:
            table = (inputs or {}).get("table")
            x = _extract_series_from_table(table, self.get_property("x_key"))
            y = _extract_series_from_table(table, self.get_property("y_key"))
        plt.figure(figsize=(4.5, 3))
        plt.scatter(x, y, s=18, c="tomato", alpha=0.8)
        plt.title(self.get_property("title") or "Scatter")
        return {"plot_image": self._finish_png()}


class LinePlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_line", "Line Plot")
        self.add_input_port("x", "data")
        self.add_input_port("y", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Line Plot")
        self.set_property("x_key", "")
        self.set_property("y_key", "")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        x = _as_numeric_list((inputs or {}).get("x"))
        y = _as_numeric_list((inputs or {}).get("y"))
        if not x or not y:
            table = (inputs or {}).get("table")
            x = _extract_series_from_table(table, self.get_property("x_key"))
            y = _extract_series_from_table(table, self.get_property("y_key"))
        plt.figure(figsize=(4.5, 3))
        plt.plot(x, y, color="royalblue", linewidth=2)
        plt.title(self.get_property("title") or "Line")
        return {"plot_image": self._finish_png()}


class BarPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_bar", "Bar Plot")
        self.add_input_port("categories", "data")
        self.add_input_port("values", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Bar Plot")
        self.set_property("label_key", "")
        self.set_property("value_key", "")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        labels: list[str] = [str(x) for x in (inputs or {}).get("categories", [])]
        values = _as_numeric_list((inputs or {}).get("values"))
        if not labels or not values:
            table = (inputs or {}).get("table")
            labels = _extract_labels_from_table(table, self.get_property("label_key"))
            values = _extract_series_from_table(table, self.get_property("value_key"))
        plt.figure(figsize=(4.8, 3))
        import numpy as np
        idx = np.arange(len(values))
        plt.bar(idx, values, color="seagreen", alpha=0.85)
        if labels:
            plt.xticks(idx, labels, rotation=45, ha="right")
        plt.title(self.get_property("title") or "Bar")
        return {"plot_image": self._finish_png()}


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


# ----------------------
# Additional plot nodes
# ----------------------


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


class VolcanoPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_volcano", "Volcano Plot")
        self.add_input_port("table", "data")
        self.set_property("title", "Volcano Plot")
        self.set_property("fc_key", "log2fc")
        self.set_property("p_key", "pvalue")
        self.set_property("label_key", "")
        self.set_property("fc_thresh", 1.0)
        self.set_property("p_thresh", 0.05)
        self.set_property("top_n_labels", 10)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        df = _as_dataframe((inputs or {}).get("table"))
        if df is None:
            raise ValueError("Volcano plot requires a table with fold-change and p-values")
        fc_key = str(self.get_property("fc_key") or "log2fc")
        p_key = str(self.get_property("p_key") or "pvalue")
        label_key = str(self.get_property("label_key") or "")
        try:
            import numpy as np  # type: ignore
            x = np.array(df[fc_key], dtype=float)
            p = np.array(df[p_key], dtype=float)
            y = -np.log10(np.clip(p, 1e-300, 1.0))
        except Exception as e:
            raise ValueError(f"Invalid columns for volcano plot: {e}")

        fc_thr = float(self.get_property("fc_thresh") or 1.0)
        p_thr = float(self.get_property("p_thresh") or 0.05)
        sig = (np.abs(x) >= fc_thr) & (p <= p_thr)

        plt.figure(figsize=(5, 3.6))
        plt.scatter(x[~sig], y[~sig], s=14, c="#b0b0b0", alpha=0.7)
        plt.scatter(x[sig], y[sig], s=18, c="#d62728", alpha=0.85)
        plt.axvline(+fc_thr, color="#888888", linestyle="--", linewidth=1)
        plt.axvline(-fc_thr, color="#888888", linestyle="--", linewidth=1)
        plt.axhline(-np.log10(p_thr), color="#888888", linestyle="--", linewidth=1)
        plt.xlabel("log2 Fold Change")
        plt.ylabel("-log10 p-value")
        plt.title(self.get_property("title") or "Volcano Plot")

        # Optional top-N labels among significant points
        try:
            if label_key and label_key in df.columns:
                import numpy as np  # type: ignore
                idx = np.where(sig)[0]
                if idx.size > 0:
                    # Rank by y (significance)
                    order = np.argsort(-y[idx])
                    top_n = int(self.get_property("top_n_labels") or 10)
                    for ii in idx[order[:max(0, top_n)]]:
                        lbl = str(df.iloc[ii][label_key])
                        plt.text(x[ii], y[ii], lbl, fontsize=8, ha='left', va='bottom')
        except Exception:
            pass

        return {"plot_image": self._finish_png()}


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


class HexbinPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_hexbin", "Hexbin Plot")
        self.add_input_port("x", "data")
        self.add_input_port("y", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Hexbin Plot")
        self.set_property("x_key", "")
        self.set_property("y_key", "")
        self.set_property("gridsize", 30)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        x = _as_numeric_list((inputs or {}).get("x"))
        y = _as_numeric_list((inputs or {}).get("y"))
        if not x or not y:
            table = (inputs or {}).get("table")
            x = _extract_series_from_table(table, self.get_property("x_key"))
            y = _extract_series_from_table(table, self.get_property("y_key"))
        plt.figure(figsize=(4.8, 3.6))
        plt.hexbin(x, y, gridsize=int(self.get_property("gridsize") or 30), cmap="viridis")
        plt.colorbar()
        plt.title(self.get_property("title") or "Hexbin")
        return {"plot_image": self._finish_png()}


class AreaPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_area", "Area Plot")
        self.add_input_port("x", "data")
        self.add_input_port("y", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Area Plot")
        self.set_property("x_key", "")
        self.set_property("y_key", "")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        x = _as_numeric_list((inputs or {}).get("x"))
        y = _as_numeric_list((inputs or {}).get("y"))
        if not x or not y:
            table = (inputs or {}).get("table")
            x = _extract_series_from_table(table, self.get_property("x_key"))
            y = _extract_series_from_table(table, self.get_property("y_key"))
        plt.figure(figsize=(4.8, 3.6))
        try:
            import numpy as np  # type: ignore
            if not x:
                x = list(range(len(y)))
            plt.fill_between(x, y, step=None, alpha=0.6, color="#4c78a8")
        except Exception:
            pass
        plt.title(self.get_property("title") or "Area Plot")
        return {"plot_image": self._finish_png()}


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


class BubblePlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_bubble", "Bubble Plot")
        self.add_input_port("x", "data")
        self.add_input_port("y", "data")
        self.add_input_port("size", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "Bubble Plot")
        self.set_property("x_key", "")
        self.set_property("y_key", "")
        self.set_property("size_key", "")
        self.set_property("size_scale", 20.0)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        x = _as_numeric_list((inputs or {}).get("x"))
        y = _as_numeric_list((inputs or {}).get("y"))
        s = _as_numeric_list((inputs or {}).get("size"))
        if not (x and y and s):
            table = (inputs or {}).get("table")
            x = _extract_series_from_table(table, self.get_property("x_key"))
            y = _extract_series_from_table(table, self.get_property("y_key"))
            s = _extract_series_from_table(table, self.get_property("size_key"))
        scale = float(self.get_property("size_scale") or 20.0)
        plt.figure(figsize=(4.8, 3.6))
        try:
            import numpy as np  # type: ignore
            sizes = (np.array(s, dtype=float) if s else 1.0) * scale
        except Exception:
            sizes = 20.0
        plt.scatter(x, y, s=sizes, c="#1f77b4", alpha=0.7)
        plt.title(self.get_property("title") or "Bubble Plot")
        return {"plot_image": self._finish_png()}


class StackedBarPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_stacked_bar", "Stacked Bar")
        self.add_input_port("table", "data")
        self.set_property("title", "Stacked Bar")
        self.set_property("category_key", "category")
        self.set_property("series_key", "series")
        self.set_property("value_key", "value")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        df = _as_dataframe((inputs or {}).get("table"))
        if df is None:
            plt.figure(figsize=(4.6, 3.6))
            plt.text(0.5, 0.5, "No data", ha="center", va="center", fontsize=12, color="gray")
            return {"plot_image": self._finish_png()}
        cat = str(self.get_property("category_key") or "category")
        ser = str(self.get_property("series_key") or "series")
        val = str(self.get_property("value_key") or "value")
        try:
            import pandas as pd  # type: ignore
            import numpy as np  # type: ignore
            pivot = df[[cat, ser, val]].copy()
            pivot[cat] = pivot[cat].astype(str)
            pivot[ser] = pivot[ser].astype(str)
            pivot[val] = pivot[val].astype(float)
            mat = pivot.pivot_table(index=cat, columns=ser, values=val, aggfunc='sum', fill_value=0.0)
            labels = list(mat.index)
            series = list(mat.columns)
            arr = mat.values
            x = np.arange(len(labels))
            plt.figure(figsize=(5.6, 3.6))
            bottom = np.zeros(len(labels))
            for i, sname in enumerate(series):
                plt.bar(x, arr[:, i], bottom=bottom, label=str(sname))
                bottom = bottom + arr[:, i]
            plt.xticks(x, labels, rotation=45, ha='right')
            plt.legend(fontsize=8, ncol=2)
            plt.title(self.get_property("title") or "Stacked Bar")
        except Exception:
            plt.figure(figsize=(4.6, 3.6))
        return {"plot_image": self._finish_png()}


class Hist2DPlotNode(_BasePlotNode):
    def __init__(self):
        super().__init__("plot_hist2d", "2D Histogram")
        self.add_input_port("x", "data")
        self.add_input_port("y", "data")
        self.add_input_port("table", "data")
        self.set_property("title", "2D Histogram")
        self.set_property("x_key", "")
        self.set_property("y_key", "")
        self.set_property("bins", 40)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from utils.mpl_utils import import_pyplot_non_interactive
        plt = import_pyplot_non_interactive()
        x = _as_numeric_list((inputs or {}).get("x"))
        y = _as_numeric_list((inputs or {}).get("y"))
        if not x or not y:
            table = (inputs or {}).get("table")
            x = _extract_series_from_table(table, self.get_property("x_key"))
            y = _extract_series_from_table(table, self.get_property("y_key"))
        plt.figure(figsize=(4.8, 3.6))
        plt.hist2d(x, y, bins=int(self.get_property("bins") or 40), cmap="viridis")
        plt.colorbar()
        plt.title(self.get_property("title") or "2D Histogram")
        return {"plot_image": self._finish_png()}


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
