"""MolFingerprintNode implementation."""

from .common import *  # noqa: F401,F403

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
