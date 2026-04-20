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

class MolDescriptorNode(BaseNode):
    """Calculate RDKit molecular descriptors for a list of molecules.

    Inputs:  molecules
    Outputs: data (pandas DataFrame, one row per molecule)

    Preset options:
      - lipinski   : MW, LogP, HBD, HBA, TPSA, RotBonds
      - physicochemical : lipinski + RingCount, AromaticRings, FractionCSP3, MolarRefractivity
      - all        : all available RDKit descriptors (~200 columns)
    """

    _LIPINSKI_DESCS = [
        "MolWt", "MolLogP", "NumHDonors", "NumHAcceptors",
        "TPSA", "NumRotatableBonds",
    ]
    _PHYSICOCHEMICAL_DESCS = _LIPINSKI_DESCS + [
        "RingCount", "NumAromaticRings", "FractionCSP3", "MolMR",
    ]

    def __init__(self):
        super().__init__("mol_descriptor", "Mol Descriptor")
        self.logger = get_logger(__name__)
        self.add_input_port("molecules", "molecules")
        self.add_output_port("data", "data")

        self.set_property("preset", "lipinski")
        # comma-separated list used when preset == "custom"
        self.set_property("custom_descriptors", "")

        try:
            from core.nodes import BaseNode as _BaseNode
            if getattr(_BaseNode, "_lightweight_construction", False):
                self._combo = None
            else:
                from PySide6.QtWidgets import QComboBox, QLabel, QSpacerItem, QSizePolicy
                lbl = QLabel("Descriptor Preset")
                lbl.setStyleSheet("QLabel { background: transparent; font-size: 10px; }")
                self._combo = QComboBox()
                self._combo.addItems(["lipinski", "physicochemical", "all"])
                idx = self._combo.findText(self.get_property("preset") or "lipinski")
                if idx >= 0:
                    self._combo.setCurrentIndex(idx)
                self._combo.currentTextChanged.connect(
                    lambda t: self.set_property("preset", t)
                )
                layout = self.content_layout
                if layout is not None:
                    layout.addItem(QSpacerItem(0, 4, QSizePolicy.Minimum, QSizePolicy.Fixed), 0, 0)
                    layout.addWidget(lbl, 1, 0)
                    layout.addWidget(self._combo, 2, 0)
                self._update_port_positions()
        except Exception:
            self._combo = None

    def _inline_summary(self) -> list[str]:
        return [f"Preset: {self.get_property('preset') or 'lipinski'}"]

    def _get_desc_names(self) -> List[str]:
        preset = (self.get_property("preset") or "lipinski").lower()
        if preset == "lipinski":
            return list(self._LIPINSKI_DESCS)
        if preset == "physicochemical":
            return list(self._PHYSICOCHEMICAL_DESCS)
        if preset == "custom":
            raw = self.get_property("custom_descriptors") or ""
            return [d.strip() for d in raw.split(",") if d.strip()]
        # "all"
        try:
            from rdkit.Chem import Descriptors
            return [name for name, _ in Descriptors.descList]
        except Exception:
            return list(self._PHYSICOCHEMICAL_DESCS)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        import pandas as pd
        from rdkit.Chem import Descriptors

        mols: List[Any] = (inputs or {}).get("molecules") or []
        if not mols:
            raise ValueError("No molecules provided")

        desc_names = self._get_desc_names()
        # Build a callable map: name -> function
        desc_map: Dict[str, Any] = {name: fn for name, fn in Descriptors.descList}

        rows = []
        for i, mol in enumerate(mols):
            if mol is None:
                continue
            row: Dict[str, Any] = {"name": _mol_name(mol, i)}
            for d in desc_names:
                fn = desc_map.get(d)
                if fn is None:
                    row[d] = None
                    continue
                try:
                    row[d] = fn(mol)
                except Exception:
                    row[d] = None
            rows.append(row)

        if not rows:
            raise ValueError("No valid molecules to compute descriptors")

        df = pd.DataFrame(rows)
        self.logger.info(f"MolDescriptorNode: {len(df)} rows, {len(desc_names)} descriptors")
        return {"data": df}

    def validate(self) -> tuple[bool, str]:
        return True, "Node configuration is valid"


# ---------------------------------------------------------------------------
# MolFingerprintNode
# ---------------------------------------------------------------------------

class MolFingerprintNode(BaseNode):
    """Generate molecular fingerprints as a DataFrame (bit vectors as columns).

    Inputs:  molecules
    Outputs: data  (DataFrame: 'name' + one column per bit/key)

    Fingerprint types: Morgan (ECFP), MACCS, RDKit, TopologicalTorsion, AtomPair
    """

    def __init__(self):
        super().__init__("mol_fingerprint", "Mol Fingerprint")
        self.logger = get_logger(__name__)
        self.add_input_port("molecules", "molecules")
        self.add_output_port("data", "data")

        self.set_property("fp_type", "Morgan")
        self.set_property("radius", 2)       # Morgan radius
        self.set_property("n_bits", 2048)    # bit vector length for bit-based FPs

        try:
            from core.nodes import BaseNode as _BaseNode
            if getattr(_BaseNode, "_lightweight_construction", False):
                self._combo = None
            else:
                from PySide6.QtWidgets import QComboBox, QLabel, QSpacerItem, QSizePolicy
                lbl = QLabel("Fingerprint Type")
                lbl.setStyleSheet("QLabel { background: transparent; font-size: 10px; }")
                self._combo = QComboBox()
                self._combo.addItems(["Morgan", "MACCS", "RDKit", "TopologicalTorsion", "AtomPair"])
                idx = self._combo.findText(self.get_property("fp_type") or "Morgan")
                if idx >= 0:
                    self._combo.setCurrentIndex(idx)
                self._combo.currentTextChanged.connect(
                    lambda t: self.set_property("fp_type", t)
                )
                layout = self.content_layout
                if layout is not None:
                    layout.addItem(QSpacerItem(0, 4, QSizePolicy.Minimum, QSizePolicy.Fixed), 0, 0)
                    layout.addWidget(lbl, 1, 0)
                    layout.addWidget(self._combo, 2, 0)
                self._update_port_positions()
        except Exception:
            self._combo = None

    def _inline_summary(self) -> list[str]:
        fp = self.get_property("fp_type") or "Morgan"
        if fp == "Morgan":
            return [f"Morgan r={self.get_property('radius')} n={self.get_property('n_bits')}"]
        return [f"FP: {fp}"]

    def _compute_fp(self, mol) -> List[int]:
        fp_type = (self.get_property("fp_type") or "Morgan").lower()
        n_bits = int(self.get_property("n_bits") or 2048)
        radius = int(self.get_property("radius") or 2)
        from rdkit.Chem import AllChem, MACCSkeys
        from rdkit.Chem import rdMolDescriptors

        if fp_type == "morgan":
            bv = AllChem.GetMorganFingerprintAsBitVect(mol, radius=radius, nBits=n_bits)
        elif fp_type == "maccs":
            bv = MACCSkeys.GenMACCSKeys(mol)
        elif fp_type == "rdkit":
            from rdkit.Chem import RDKFingerprint
            bv = RDKFingerprint(mol, fpSize=n_bits)
        elif fp_type == "topologicaltorsion":
            fp = rdMolDescriptors.GetTopologicalTorsionFingerprintAsBitVect(mol)
            bv = fp
        elif fp_type == "atompair":
            fp = rdMolDescriptors.GetAtomPairFingerprintAsBitVect(mol)
            bv = fp
        else:
            bv = AllChem.GetMorganFingerprintAsBitVect(mol, radius=radius, nBits=n_bits)

        return list(bv)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        import pandas as pd

        mols: List[Any] = (inputs or {}).get("molecules") or []
        if not mols:
            raise ValueError("No molecules provided")

        rows = []
        for i, mol in enumerate(mols):
            if mol is None:
                continue
            try:
                bits = self._compute_fp(mol)
            except Exception as e:
                self.logger.warning(f"Fingerprint error on mol {i}: {e}")
                continue
            row: Dict[str, Any] = {"name": _mol_name(mol, i)}
            for j, b in enumerate(bits):
                row[f"bit_{j}"] = int(b)
            rows.append(row)

        if not rows:
            raise ValueError("No valid molecules to compute fingerprints")

        df = pd.DataFrame(rows)
        self.logger.info(f"MolFingerprintNode: {len(df)} rows, {df.shape[1]-1} bits")
        return {"data": df}

    def validate(self) -> tuple[bool, str]:
        n_bits = int(self.get_property("n_bits") or 0)
        if n_bits <= 0:
            return False, "n_bits must be > 0"
        return True, "Node configuration is valid"


# ---------------------------------------------------------------------------
# SMARTSFilterNode
# ---------------------------------------------------------------------------

class SMARTSFilterNode(BaseNode):
    """Filter molecules by a SMARTS substructure pattern.

    Inputs:  molecules
    Outputs:
      - matched   (molecules) : molecules that contain the substructure
      - unmatched (molecules) : molecules that do NOT contain it
    """

    def __init__(self):
        super().__init__("smarts_filter", "SMARTS Filter")
        self.logger = get_logger(__name__)
        self.add_input_port("molecules", "molecules")
        self.add_output_port("matched", "molecules")
        self.add_output_port("unmatched", "molecules")

        self.set_property("smarts", "")

        self.width = 300
        self.height = 140

        try:
            from core.nodes import BaseNode as _BaseNode
            if getattr(_BaseNode, "_lightweight_construction", False):
                self._edit = None
            else:
                from PySide6.QtWidgets import QLineEdit, QLabel, QSpacerItem, QSizePolicy
                lbl = QLabel("SMARTS Pattern")
                lbl.setStyleSheet("QLabel { background: transparent; font-size: 10px; }")
                self._edit = QLineEdit()
                self._edit.setPlaceholderText("e.g. [#6]-[#7]  or  c1ccccc1")
                self._edit.setText(self.get_property("smarts") or "")
                self._edit.textChanged.connect(lambda t: self.set_property("smarts", t))
                layout = self.content_layout
                if layout is not None:
                    layout.addItem(QSpacerItem(0, 4, QSizePolicy.Minimum, QSizePolicy.Fixed), 0, 0)
                    layout.addWidget(lbl, 1, 0)
                    layout.addWidget(self._edit, 2, 0)
                self._update_port_positions()
        except Exception:
            self._edit = None

    def _inline_summary(self) -> list[str]:
        s = self.get_property("smarts") or ""
        return [f"SMARTS: {s[:28]}" if s else "No SMARTS set"]

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from rdkit import Chem

        mols: List[Any] = (inputs or {}).get("molecules") or []
        if not mols:
            raise ValueError("No molecules provided")

        pattern_str = (self.get_property("smarts") or "").strip()
        if not pattern_str:
            raise ValueError("SMARTS pattern is empty")

        query = Chem.MolFromSmarts(pattern_str)
        if query is None:
            raise ValueError(f"Invalid SMARTS pattern: '{pattern_str}'")

        matched: List[Any] = []
        unmatched: List[Any] = []
        for mol in mols:
            if mol is None:
                continue
            try:
                if mol.HasSubstructMatch(query):
                    matched.append(mol)
                else:
                    unmatched.append(mol)
            except Exception as e:
                self.logger.warning(f"SMARTSFilterNode: error on molecule: {e}")
                unmatched.append(mol)

        self.logger.info(
            f"SMARTSFilterNode: {len(matched)} matched, {len(unmatched)} unmatched"
        )
        return {"matched": matched, "unmatched": unmatched}

    def validate(self) -> tuple[bool, str]:
        s = (self.get_property("smarts") or "").strip()
        if not s:
            return False, "SMARTS pattern is empty"
        try:
            from rdkit import Chem
            q = Chem.MolFromSmarts(s)
            if q is None:
                return False, f"Invalid SMARTS: '{s}'"
        except Exception as e:
            return False, f"SMARTS parse error: {e}"
        return True, "Node configuration is valid"
