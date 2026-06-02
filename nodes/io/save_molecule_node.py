"""SaveMoleculeNode implementation."""

from .common import *  # noqa: F401,F403

class SaveMoleculeNode(BaseNode):
    """Save RDKit molecules to SDF/MOL/MOL2/PDB/PDBQT."""

    def __init__(self):
        super().__init__("save_molecule", "Save Molecule")
        self.logger = get_logger(__name__)
        self.add_input_port("molecules", "molecules")
        self.add_output_port("saved_file", "string")
        self.set_property("output_path", "")
        self.set_property("file_type", "auto")  # auto|sdf|mol|mol2|pdb|pdbqt|xyz
        self.set_property("overwrite", True)

        # Inline Browse UI
        try:
            from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QFileDialog, QSpacerItem, QSizePolicy

            self.width = 320
            self.height = 140
            try:
                self.setMinimumSize(self.width, self.height)
                self.setMaximumSize(self.width, self.height)
            except Exception:
                pass

            layout = self.content_layout
            if layout is not None:
                layout.addItem(QSpacerItem(0, 6, QSizePolicy.Minimum, QSizePolicy.Fixed), 0, 0, 1, 3)
                lbl = QLabel("Output Path")
                lbl.setStyleSheet("QLabel { background: transparent; }")
                edit = QLineEdit(self.get_property("output_path") or "")
                btn = QPushButton("Browse…")

                def on_browse():  # pragma: no cover - UI-only
                    try:
                        filters = "Molecules (*.sdf *.mol *.mol2 *.pdb *.pdbqt *.xyz);;All Files (*)"
                        filename, _ = QFileDialog.getSaveFileName(None, "Select Output File", edit.text(), filters)
                        if filename:
                            edit.setText(filename)
                            self.set_property("output_path", filename)
                    except Exception:
                        pass

                def on_text_changed(text: str):
                    try:
                        self.set_property("output_path", text)
                    except Exception:
                        pass

                edit.textChanged.connect(on_text_changed)
                btn.clicked.connect(on_browse)

                layout.addWidget(lbl, 1, 0)
                layout.addWidget(edit, 1, 1)
                layout.addWidget(btn, 1, 2)
            self._update_port_positions()
        except Exception:
            pass

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        out_path = self.get_property("output_path")
        if not out_path:
            raise ValueError("Output path is required")
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists() and not bool(self.get_property("overwrite")):
            raise ValueError(f"File exists and overwrite disabled: {out}")
        ftype = (self.get_property("file_type") or "auto").lower()
        if ftype == "auto":
            ftype = out.suffix.lower().lstrip('.')
        molecules = (inputs or {}).get("molecules") or []
        if not isinstance(molecules, list) or len(molecules) == 0:
            raise ValueError("No molecules provided")
        # Use same logic as SaveFileSink
        try:
            from rdkit import Chem
            if ftype == 'sdf':
                w = Chem.SDWriter(str(out))
                for m in molecules:
                    if m is not None:
                        w.write(m)
                w.close()
            elif ftype == 'mol':
                Chem.MolToMolFile(molecules[0], str(out))
            elif ftype == 'mol2':
                Chem.MolToMol2File(molecules[0], str(out))
            elif ftype == 'pdb':
                # Write robust PDB with proper HETATM for ligands and TER between entities
                AA = {
                    'ALA','ARG','ASN','ASP','CYS','GLN','GLU','GLY','HIS','ILE','LEU','LYS','MET','PHE','PRO','SER','THR','TRP','TYR','VAL','SEC','PYL'
                }
                NA = {'A','U','G','C','T','DA','DT','DG','DC','DU','RA','RU','RG','RC','RT'}
                WAT = {'HOH','WAT','H2O','DOD'}
                ION = {'NA','K','CL','MG','MN','ZN','CA','FE','FE2','FE3','CO','CU','NI','CD','AL','SR','BA','YB','LI'}

                def _is_polymer_resname(rn: str) -> bool:
                    r = (rn or '').strip().upper()
                    return (r in AA) or (r in NA)

                def _is_water(rn: str) -> bool:
                    return (rn or '').strip().upper() in WAT

                def _is_ion(rn: str) -> bool:
                    return (rn or '').strip().upper() in ION

                def _block_from_mol(m) -> list[str]:
                    blk = Chem.MolToPDBBlock(m)
                    lines = [ln for ln in blk.splitlines() if ln and not ln.startswith('END') and not ln.startswith('TER')]
                    return lines

                # Collect lines from one or more molecules
                all_lines: list[str] = []
                for idx, m in enumerate(molecules):
                    if m is None:
                        continue
                    lines = _block_from_mol(m)
                    if not lines:
                        continue
                    # Insert TER between molecules if previous had atoms
                    if all_lines:
                        all_lines.append('TER')
                    all_lines.extend(lines)

                if not all_lines:
                    raise ValueError('No atoms to write')

                # Rewrite records to ensure ligands are HETATM and add TER between polymer/hetero boundaries
                out_lines: list[str] = []
                serial = 1
                last_was_polymer = None
                for raw in all_lines:
                    if raw.startswith('ATOM') or raw.startswith('HETATM'):
                        resname = raw[17:20].strip().upper() if len(raw) >= 20 else ''
                        is_poly = _is_polymer_resname(resname)
                        is_water = _is_water(resname)
                        is_ion = _is_ion(resname)
                        is_hetero = (not is_poly) or is_water or is_ion
                        # Boundary TER between polymer and hetero groups
                        if last_was_polymer is not None and (is_poly != last_was_polymer):
                            out_lines.append('TER')
                        last_was_polymer = is_poly
                        # Choose correct record type
                        record = 'HETATM' if is_hetero else 'ATOM  '
                        # Rebuild line with corrected record and continuous serial
                        tail = raw[11:] if len(raw) > 11 else ''
                        new_line = f"{record}{serial:5d}{tail}"
                        out_lines.append(new_line)
                        serial += 1
                    elif raw.startswith('ANISOU'):
                        # Keep ANISOU aligned with previous ATOM serial
                        tail = raw[11:] if len(raw) > 11 else ''
                        new_line = f"ANISOU{serial-1:5d}{tail}"
                        out_lines.append(new_line)
                    elif raw.startswith('TER'):
                        # Normalize single TER
                        if out_lines and out_lines[-1] != 'TER':
                            out_lines.append('TER')
                    else:
                        # Keep other records (e.g., MODEL) as-is
                        out_lines.append(raw)

                # Ensure final TER before END
                if out_lines and not out_lines[-1].startswith('TER'):
                    out_lines.append('TER')
                out_lines.append('END')
                out.write_text("\n".join(out_lines) + "\n")
            elif ftype == 'pdbqt':
                from backend.temp_manager import get_subdir
                from utils.external_tools import resolve_openbabel_executable
                import subprocess
                tmp = get_subdir("save_molecule")
                pdb_tmp = Path(tmp) / "tmp_for_pdbqt.pdb"
                Chem.MolToPDBFile(molecules[0], str(pdb_tmp))
                obabel = resolve_openbabel_executable("obabel")
                ob_dir = Path(obabel).parent if isinstance(obabel, str) else None
                cmd = [obabel, str(pdb_tmp), "-O", str(out)]
                subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120, cwd=str(ob_dir) if ob_dir else None, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            elif ftype == 'xyz':
                # Write XYZ format
                with open(out, 'w', encoding='utf-8') as f:
                    for mol in molecules:
                        if mol is None:
                            continue
                        
                        # Create XYZ content
                        xyz_content = _create_xyz_content(mol)
                        if xyz_content:
                            f.write(xyz_content)
                            # Add blank line between molecules if multiple
                            if len(molecules) > 1:
                                f.write("\n")
            else:
                raise ValueError(f"Unsupported molecule file type: {ftype}")
        except Exception as e:
            self.logger.error(f"Error saving molecules: {e}")
            raise
        return {"saved_file": str(out), "file_size": out.stat().st_size if out.exists() else 0}

    def validate(self) -> tuple[bool, str]:
        p = self.get_property("output_path")
        if not p:
            return False, "Output path not specified"
        try:
            Path(p).parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return False, f"Cannot create output directory: {e}"
        return True, "Node configuration is valid"
