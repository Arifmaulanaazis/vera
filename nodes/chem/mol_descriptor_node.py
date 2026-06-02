"""MolDescriptorNode implementation."""

from .common import *  # noqa: F401,F403

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
