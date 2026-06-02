"""RCSBPDBNode implementation."""

from .common import *  # noqa: F401,F403

class RCSBPDBNode(BaseNode):
    """Fetch structure(s) from RCSB PDB by PDB code and output RDKit molecules.

    UI: label "PDB Code" and a single line edit (placeholder: "ex: 7JOZ, 4ZUD").
    Inputs: none
    Outputs: molecules (molecules)
    """

    def __init__(self):
        super().__init__("rcsb_pdb", "RCSB PDB")
        self.logger = get_logger(__name__)

        # Single output: RDKit molecules list
        self.add_output_port("molecules", "molecules")

        # Visual size similar to simple input nodes
        self.width = 320
        self.height = 140
        self.setMinimumSize(self.width, self.height)
        self.setMaximumSize(self.width, self.height)

        # Properties
        self.set_property("pdb_code", "")  # Accepts comma-separated codes

        # Inline UI: label + line edit
        try:
            from PySide6.QtWidgets import QLabel, QLineEdit

            lbl = QLabel("PDB Code")
            edit = QLineEdit()
            edit.setPlaceholderText("ex: 7JOZ, 4ZUD")
            edit.setText(self.get_property("pdb_code") or "")

            def _on_text_changed(text: str):
                try:
                    self.set_property("pdb_code", text)
                except Exception:
                    pass

            edit.textChanged.connect(_on_text_changed)

            layout = self.content_layout
            if layout is not None:
                layout.addWidget(lbl, 0, 0)
                layout.addWidget(edit, 1, 0)
            self._update_port_positions()
        except Exception:
            pass

    def _parse_codes(self) -> List[str]:
        text = (self.get_property("pdb_code") or "").strip()
        if not text:
            return []
        # Split by comma/space/newline; keep alphanumerics
        raw_parts = [p.strip() for p in text.replace("\n", ",").replace(" ", ",").split(",")]
        codes: List[str] = []
        for part in raw_parts:
            if not part:
                continue
            # Normalize to uppercase
            codes.append(part.upper())
        # Deduplicate preserving order
        seen = set()
        unique_codes: List[str] = []
        for c in codes:
            if c not in seen:
                seen.add(c)
                unique_codes.append(c)
        return unique_codes

    def _download_pdb_text(self, code: str) -> str:
        import requests
        url = f"https://files.rcsb.org/download/{code}.pdb"
        # Small retry loop
        last_err: Exception | None = None
        for _ in range(2):
            try:
                r = requests.get(url, timeout=15)
                r.raise_for_status()
                return r.text
            except Exception as e:
                last_err = e
        raise ValueError(f"Failed to download PDB for code {code}: {last_err}")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from rdkit import Chem

        codes = self._parse_codes()
        if not codes:
            raise ValueError("PDB code is required (e.g., 7JOZ, 4ZUD)")

        molecules: List[Any] = []
        for idx, code in enumerate(codes):
            try:
                try:
                    self.report_progress(min(99, int(idx / max(1, len(codes)) * 100)), f"Fetching {code}…")
                except Exception:
                    pass
                pdb_text = self._download_pdb_text(code)
                m = Chem.MolFromPDBBlock(pdb_text, sanitize=False, removeHs=False, proximityBonding=True)
                if m is None:
                    self.logger.warning(f"RDKit failed to parse PDB for {code}")
                    continue
                try:
                    Chem.SanitizeMol(m, catchErrors=True)
                except Exception:
                    pass
                molecules.append(m)
            except Exception as e:
                self.logger.warning(f"Failed to process {code}: {e}")

        try:
            self.report_progress(100, f"RCSB PDB: {len(molecules)} molecule(s) loaded")
        except Exception:
            pass

        return {"molecules": molecules, "num_molecules": len(molecules), "codes": codes}
