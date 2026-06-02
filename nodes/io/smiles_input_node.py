"""SMILESInputNode implementation."""

from .common import *  # noqa: F401,F403

class SMILESInputNode(BaseNode):
    """Type SMILES strings directly to produce molecules.

    Each non-empty line in the text area is parsed as a SMILES string.
    Optionally a name can be appended with a space/tab after the SMILES.

    Output: molecules (list of RDKit Mol)
    """

    def __init__(self):
        super().__init__("smiles_input", "SMILES Input")
        self.logger = get_logger(__name__)
        self.add_output_port("molecules", "molecules")

        self.width = 300
        self.height = 200
        self.setMinimumSize(self.width, self.height)

        self.set_property("smiles_text", "")

        try:
            from core.nodes import BaseNode as _BaseNode
            if getattr(_BaseNode, "_lightweight_construction", False):
                self._edit = None
            else:
                from PySide6.QtWidgets import QPlainTextEdit, QLabel, QSpacerItem, QSizePolicy
                self._edit = QPlainTextEdit()
                self._edit.setPlaceholderText(
                    "One SMILES per line, optional name after space:\n"
                    "CCO ethanol\nCC(=O)O acetic_acid"
                )
                self._edit.setPlainText(self.get_property("smiles_text") or "")
                self._edit.textChanged.connect(self._on_text_changed)
                layout = self.content_layout
                if layout is not None:
                    lbl = QLabel("SMILES (one per line)")
                    lbl.setStyleSheet("QLabel { background: transparent; font-size: 10px; }")
                    layout.addItem(QSpacerItem(0, 4, QSizePolicy.Minimum, QSizePolicy.Fixed), 0, 0)
                    layout.addWidget(lbl, 1, 0)
                    layout.addWidget(self._edit, 2, 0)
                self._update_port_positions()
        except Exception:
            self._edit = None

    def _on_text_changed(self):
        try:
            if self._edit is not None:
                self.set_property("smiles_text", self._edit.toPlainText())
        except Exception:
            pass

    def _inline_summary(self) -> list[str]:
        text = self.get_property("smiles_text") or ""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return ["No SMILES entered"]
        return [f"{len(lines)} SMILES"]

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from rdkit import Chem
        text = self.get_property("smiles_text") or ""
        mols: List[Any] = []
        errors: List[str] = []
        for i, raw in enumerate(text.splitlines()):
            raw = raw.strip()
            if not raw:
                continue
            parts = raw.split(None, 1)
            smi = parts[0]
            name = parts[1] if len(parts) > 1 else f"mol_{i+1}"
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                errors.append(f"Line {i+1}: invalid SMILES '{smi}'")
                self.logger.warning(f"SMILESInputNode: invalid SMILES at line {i+1}: {smi}")
                continue
            try:
                mol.SetProp("_Name", name)
            except Exception:
                pass
            mols.append(mol)
        if not mols and errors:
            raise ValueError(f"No valid molecules. Errors: {'; '.join(errors[:3])}")
        return {"molecules": mols}

    def validate(self) -> tuple[bool, str]:
        text = self.get_property("smiles_text") or ""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return False, "No SMILES entered"
        return True, "Node configuration is valid"
