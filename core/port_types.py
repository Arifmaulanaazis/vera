"""
Port type system utilities for nodes and connections.

Defines canonical port data types, compatibility rules, and colors.
"""

from __future__ import annotations

from typing import Dict
from PySide6.QtGui import QColor
from utils.theme_colors import get_port_color_for_type


# Canonical data types used across nodes
# Keep this small and strict. "any" matches anything.
CANONICAL_TYPES = {
    "any",
    "file",
    "string",
    "data",
    "list",
    "molecules",
    "bytes",     # arbitrary binary blob (e.g., PNG bytes)
    "image",     # image-like binary (PNG/JPG) as bytes
    "model",     # trained ML model object (e.g., scikit-learn estimator)
}


_TYPE_COLORS: Dict[str, QColor] = {
    # Distinct, readable colors on dark background
    "any": QColor(160, 160, 160),
    "file": QColor(83, 156, 255),       # blue
    "string": QColor(255, 180, 70),     # orange
    "data": QColor(140, 220, 120),      # green
    "list": QColor(200, 140, 255),      # violet
    "molecules": QColor(255, 110, 140), # pinkish red
    "bytes": QColor(120, 200, 200),     # teal
    "image": QColor(255, 140, 90),      # orange-red
    "model": QColor(90, 200, 255),      # light blue
}


_SYNONYMS = {
    # Map variations to canonical values
    "molecule": "molecules",
    "mol": "molecules",
    "sdf": "file",
    "pdb": "file",
    "pdbqt": "file",
    "xyz": "file",
    "csv": "file",
    "json": "data",
    "txt": "file",
    # Convenience plural
    "files": "list",
    # Workflow-specific conveniences
    "docking_results": "data",
    "report": "string",
    "plot": "image",
    "image": "image",
}


def normalize_type(t: str | None) -> str:
    if not t:
        return "any"
    t = str(t).strip().lower()
    t = _SYNONYMS.get(t, t)
    # Unknown types are allowed but for compatibility checks they must match exactly.
    # We do not coerce unknown types to 'any' to preserve strictness.
    return t


def is_compatible(output_type: str, input_type: str) -> bool:
    """Return True if an output port of output_type can connect to an input port of input_type.

    Rules:
    - "any" matches anything (either side).
    - Otherwise, types must match exactly.
    """
    out_t = normalize_type(output_type)
    in_t = normalize_type(input_type)
    if out_t == "any" or in_t == "any":
        return True
    return out_t == in_t


def compatibility_message(output_type: str, input_type: str) -> str:
    out_t = normalize_type(output_type)
    in_t = normalize_type(input_type)
    if is_compatible(out_t, in_t):
        return ""
    return f"Type mismatch: output '{out_t}' → input '{in_t}'"


def color_for_type(t: str) -> QColor:
    t = normalize_type(t)
    return get_port_color_for_type(t)  # Use theme-aware colors


