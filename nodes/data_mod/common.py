"""
Data modification nodes for table-like data (list of dicts or pandas.DataFrame).

Nodes included:
- SelectColumnsNode: keep only selected columns
- FilterRowsNode: filter rows by key/operator/value
- SliceRowsNode: slice rows by start/end/step
- DropDuplicatesNode: remove duplicate rows
- SortRowsNode: sort rows by one or more keys
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import json

from core.nodes import BaseNode
from utils.logging_utils import get_logger


def _to_rows(data: Any) -> List[Dict[str, Any]]:
    """Normalize incoming data to list[dict].

    - If pandas DataFrame, convert to records
    - If list of dicts, return as-is
    - If dict, wrap into one-row list
    - Otherwise, try best-effort string conversion
    """
    try:
        import pandas as pd  # type: ignore
        if isinstance(data, pd.DataFrame):
            # MultiIndex produces tuple keys in to_dict; flatten to plain columns first
            if isinstance(data.index, pd.MultiIndex):
                data = data.reset_index()
            return data.to_dict(orient="records")
    except Exception:
        pass

    if data is None:
        return []
    if isinstance(data, list):
        if len(data) == 0 or (len(data) > 0 and isinstance(data[0], dict)):
            return data  # type: ignore[return-value]
        # list of primitives -> try to parse JSON strings into dicts when possible
        try:
            looks_like_json = all(isinstance(x, str) and str(x).lstrip().startswith(("{", "[")) for x in data[:5])
        except Exception:
            looks_like_json = False
        if looks_like_json:
            parsed: List[Dict[str, Any]] = []
            json_parsed_any = False
            for x in data:
                try:
                    obj = json.loads(str(x))
                    json_parsed_any = True
                    if isinstance(obj, dict):
                        parsed.append(obj)
                    elif isinstance(obj, list):
                        # Flatten lists of dicts; if primitives, keep as value
                        added = False
                        for it in obj:
                            if isinstance(it, dict):
                                parsed.append(it)
                                added = True
                        if not added:
                            parsed.append({"value": obj})
                    else:
                        parsed.append({"value": obj})
                except Exception:
                    parsed.append({"value": x})
            if json_parsed_any and len(parsed) > 0 and isinstance(parsed[0], dict):
                return parsed
        # fallback: wrap primitives
        return [{"value": x} for x in data]
    if isinstance(data, dict):
        return [data]
    # fallback
    return [{"value": data}]


def _coerce_number(value: Any) -> Tuple[bool, float]:
    """Try to coerce value to float. Return (success, number).

    On failure returns (False, nan) — never 0.0 — so callers can
    distinguish a coercion error from a legitimate zero value.
    """
    try:
        if isinstance(value, bool):  # avoid True/False as 1/0 surprises
            return False, float("nan")
        if isinstance(value, (int, float)):
            return True, float(value)
        if isinstance(value, str):
            v = value.strip()
            if v.lower() in {"nan", "inf", "-inf"}:
                return False, float("nan")
            return True, float(v)
        return False, float("nan")
    except Exception:
        return False, float("nan")

# Re-export every helper/import so split node files keep the original module namespace.
__all__ = [name for name in globals() if not name.startswith("__")]
