"""SMARTSFilterNode implementation."""

from .common import *  # noqa: F401,F403

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
