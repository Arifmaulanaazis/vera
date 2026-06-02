"""
Clustering and dimensionality reduction nodes.

This group includes KMeans, Agglomerative (hierarchical) clustering, and PCA.
Outputs include cluster labels and transformed coordinates for plotting.
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


def _numeric_df(df):
    try:
        return df.select_dtypes(include=["number", "bool"]).astype(float)
    except Exception:
        return df

# Re-export every helper/import so split node files keep the original module namespace.
__all__ = [name for name in globals() if not name.startswith("__")]
