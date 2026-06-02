"""
Python Script Node — execute custom Python code inside the workflow.

The user's code runs in an isolated local namespace with access to:
  - inputs  : dict of all connected input values (keyed by port name)
  - output  : dict the script must populate with output values

Any key set in `output` becomes available as the node's output port.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.nodes import BaseNode
from utils.logging_utils import get_logger

_DEFAULT_SCRIPT = """\
# Available: inputs (dict), output (dict)
# Example: pass molecules through unchanged
output["result"] = inputs.get("data")
"""

# Re-export every helper/import so split node files keep the original module namespace.
__all__ = [name for name in globals() if not name.startswith("__")]
