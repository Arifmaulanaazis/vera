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

















# ----------------------
# Additional plot nodes
# ----------------------

# Re-export every helper/import so split node files keep the original module namespace.
__all__ = [name for name in globals() if not name.startswith("__")]
