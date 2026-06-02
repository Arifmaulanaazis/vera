"""
Model evaluation nodes: confusion matrix, classification report, regression metrics.

Inputs are typically predictions and optionally ground-truth labels, or a
trained model plus test_data and target column.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.nodes import BaseNode
from utils.logging_utils import get_logger


def _as_dataframe(obj: Any):
    try:
        import pandas as pd  # type: ignore
    except Exception:
        return None
    if isinstance(obj, pd.DataFrame):
        return obj
    if isinstance(obj, list) and (len(obj) == 0 or isinstance(obj[0], dict)):
        try:
            return pd.DataFrame(obj)
        except Exception:
            return None
    return None


def _extract_target_series(table: Any, target_column: str) -> List[Any]:
    if not target_column:
        return []
    df = _as_dataframe(table)
    if df is not None and target_column in df.columns:
        try:
            return list(df[target_column])  # type: ignore[list-item]
        except Exception:
            return []
    # Fallback list-of-dicts
    if isinstance(table, list) and (len(table) == 0 or isinstance(table[0], dict)):
        out: List[Any] = []
        for r in table:
            try:
                out.append(r.get(target_column))  # type: ignore[union-attr]
            except Exception:
                out.append(None)
        return out
    return []

# Re-export every helper/import so split node files keep the original module namespace.
__all__ = [name for name in globals() if not name.startswith("__")]
