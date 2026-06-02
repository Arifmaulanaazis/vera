"""
Response Surface Analysis nodes.

Fit simple response surface models (linear/quadratic/cubic or Gaussian Process)
on tabular data to produce metrics and surface grids for plotting/optimization.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.nodes import BaseNode
from utils.logging_utils import get_logger


def _rows_to_dataframe(rows: Any):
    try:
        import pandas as pd  # type: ignore
    except Exception:
        return None
    if rows is None:
        return None
    try:
        from pandas import DataFrame as _PDDataFrame  # type: ignore
        if isinstance(rows, _PDDataFrame):
            return rows
    except Exception:
        pass
    if isinstance(rows, list) and (len(rows) == 0 or isinstance(rows[0], dict)):
        try:
            return pd.DataFrame(rows)
        except Exception:
            return None
    return None


def _df_to_rows(df: Any) -> List[dict]:
    try:
        return [] if df is None else df.to_dict("records")  # type: ignore
    except Exception:
        return []

# Re-export every helper/import so split node files keep the original module namespace.
__all__ = [name for name in globals() if not name.startswith("__")]
