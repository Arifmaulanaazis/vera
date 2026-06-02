"""
Chromatography & Spectroscopy nodes.

Provides generic time-series reader, smoothing, baseline correction,
peak detection, integration, and plotting that work for HPLC, IR, and
other instruments with similar time/wavenumber vs intensity outputs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import io

from core.nodes import BaseNode
from utils.logging_utils import get_logger


def _rows_to_dataframe(rows: Any):
    try:
        import pandas as pd  # type: ignore
    except Exception:
        return None
    if rows is None:
        return None
    # rows may be a DataFrame already
    try:
        from pandas import DataFrame as _PDDataFrame  # type: ignore
        if isinstance(rows, _PDDataFrame):
            return rows
    except Exception:
        pass
    # list-of-dicts → DataFrame
    if isinstance(rows, list) and (len(rows) == 0 or isinstance(rows[0], dict)):
        try:
            return pd.DataFrame(rows)
        except Exception:
            return None
    return None


def _dataframe_to_rows(df: Any) -> List[dict]:
    try:
        return [] if df is None else df.to_dict("records")  # type: ignore[attr-defined]
    except Exception:
        return []


def _ensure_numeric(df, x_col: str, y_col: str):
    try:
        import pandas as pd  # type: ignore
        out = df.copy()
        out[x_col] = pd.to_numeric(out[x_col], errors="coerce")
        out[y_col] = pd.to_numeric(out[y_col], errors="coerce")
        out = out.dropna(subset=[x_col, y_col]).reset_index(drop=True)
        return out
    except Exception:
        return df


def _infer_xy_columns(df, x_col_override: str, y_col_override: str):
    """Infer which two columns should be treated as X and Y.

    Priority order:
      1) Explicit overrides if both present in DataFrame.
      2) Heuristic by common header names.
      3) Highest numeric coverage across all columns after coercion.
      4) Fallback to first two columns.
    """
    try:
        import pandas as pd  # type: ignore
    except Exception:
        return None, None

    # 1) Explicit overrides
    if (
        x_col_override
        and y_col_override
        and x_col_override in df.columns
        and y_col_override in df.columns
    ):
        return x_col_override, y_col_override

    # 2) Header name heuristics
    cols_lower = {str(c).lower(): c for c in df.columns}
    x_name_candidates = [
        "time",
        "retention time",
        "rt",
        "wavenumber",
        "waveno",
        "cm-1",
        "frequency",
        "mz",
        "m/z",
        "x",
    ]
    y_name_candidates = [
        "intensity",
        "absorbance",
        "signal",
        "response",
        "counts",
        "area",
        "mau",
        "y",
        "value",
    ]
    for xn in x_name_candidates:
        for yn in y_name_candidates:
            if xn in cols_lower and yn in cols_lower:
                return cols_lower[xn], cols_lower[yn]

    # 3) Numeric coverage after coercion
    numeric_score = []
    for c in df.columns:
        try:
            s = pd.to_numeric(df[c], errors="coerce")
            score = int(s.notna().sum())
            numeric_score.append((score, c))
        except Exception:
            continue
    numeric_score.sort(reverse=True)
    top = [c for _score, c in numeric_score if _score > 0]
    if len(top) >= 2:
        return top[0], top[1]

    # 4) Fallback to first two columns
    if len(df.columns) >= 2:
        return df.columns[0], df.columns[1]
    return None, None


def _map_separator_property(sep_prop: str):
    """Map the UI separator property into pandas read_csv arguments.

    Returns (sep_value, extra_kwargs). If sep_value is None, pandas will infer.
    """
    s = (sep_prop or "").strip().lower()
    if s in ("auto", ""):
        return None, {"engine": "python"}
    if s in ("comma", ","):
        return ",", {"engine": "python"}
    if s in ("semicolon", "semi", ";"):
        return ";", {"engine": "python"}
    if s in ("tab", "\t"):
        return "\t", {}
    if s in ("space", "whitespace", "ws"):
        # Use regex sep → requires python engine
        return r"\s+", {"engine": "python"}
    # Custom literal separator
    return s, {"engine": "python"}

# Re-export every helper/import so split node files keep the original module namespace.
__all__ = [name for name in globals() if not name.startswith("__")]
