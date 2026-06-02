"""
Cheminformatics nodes: descriptor calculation, fingerprints, substructure filter.
All computation is done with RDKit (no external API calls).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.nodes import BaseNode
from utils.logging_utils import get_logger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mol_name(mol, idx: int) -> str:
    try:
        n = mol.GetProp("_Name")
        if n and n.strip():
            return n.strip()
    except Exception:
        pass
    return f"mol_{idx+1}"


# ---------------------------------------------------------------------------
# MolDescriptorNode
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# MolFingerprintNode
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# SMARTSFilterNode
# ---------------------------------------------------------------------------

# Re-export every helper/import so split node files keep the original module namespace.
__all__ = [name for name in globals() if not name.startswith("__")]
