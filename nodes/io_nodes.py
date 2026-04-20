"""
Input/Output nodes for file operations and data handling.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Iterable

import pandas as pd

from core.nodes import BaseNode
from utils.logging_utils import get_logger


def _as_path_list(value: Any) -> List[str]:
    """Normalize a property or input into a list[str] of file paths.

    Accepts:
    - list[str]
    - semicolon/comma/newline separated string
    - single string path
    Filters out non-existing paths.
    """
    paths: List[str] = []
    if isinstance(value, list):
        for v in value:
            if isinstance(v, (str, Path)):
                paths.append(str(v))
    elif isinstance(value, (str, Path)):
        text = str(value).strip()
        if ";" in text or "\n" in text or "," in text:
            for part in text.replace("\n", ";").replace(",", ";").split(";"):
                p = part.strip()
                if p:
                    paths.append(p)
        elif text:
            paths.append(text)
    # Deduplicate and keep only existing
    uniq: List[str] = []
    seen = set()
    for p in paths:
        if p in seen:
            continue
        seen.add(p)
        try:
            if Path(p).exists():
                uniq.append(p)
        except Exception:
            # keep anyway if path string is unusual; downstream may handle
            uniq.append(p)
    return uniq


# --- Module-level molecule readers (RDKit) for headless compatibility ---
def _read_sdf(path: str) -> List[Any]:
    from rdkit import Chem
    # Preserve all atoms (including hydrogens) and avoid dropping atoms due to sanitization errors
    suppl = Chem.SDMolSupplier(str(path), sanitize=False, removeHs=False, strictParsing=False)
    mols: List[Any] = []
    for m in suppl:
        if m is None:
            continue
        try:
            # Try a safe sanitize; keep Hs
            Chem.SanitizeMol(m, catchErrors=True)
        except Exception:
            pass
        mols.append(m)
    return mols


def _read_mol(path: str) -> List[Any]:
    from rdkit import Chem
    m = Chem.MolFromMolFile(str(path), sanitize=False, removeHs=False, strictParsing=False)
    if m is None:
        return []
    try:
        Chem.SanitizeMol(m, catchErrors=True)
    except Exception:
        pass
    return [m]


def _read_mol2(path: str) -> List[Any]:
    from rdkit import Chem
    m = Chem.MolFromMol2File(str(path), sanitize=False, removeHs=False)
    if m is None:
        return []
    try:
        Chem.SanitizeMol(m, catchErrors=True)
    except Exception:
        pass
    return [m]


def _read_pdb(path: str) -> List[Any]:
    from rdkit import Chem
    # Keep hydrogens and avoid dropping atoms during read; use proximity bonding when CONECT is missing
    m = Chem.MolFromPDBFile(str(path), sanitize=False, removeHs=False, proximityBonding=True)
    if m is None:
        return []
    try:
        Chem.SanitizeMol(m, catchErrors=True)
    except Exception:
        pass
    return [m]


def _read_pdbqt(path: str, logger=None) -> List[Any]:
    """Read a PDBQT file by converting ATOM/HETATM records to PDB blocks.

    - Extracts coordinates from PDBQT (ignores ROOT/BRANCH markers and scoring columns)
    - Supports multi-model/pose files by returning a list of molecules
    - Falls back to direct PDB parsing if conversion fails
    """
    def _safe_float(text: str) -> bool:
        try:
            float(text)
            return True
        except Exception:
            return False

    def _guess_element(atom_name: str, ad_type: str) -> str:
        # Prefer element hinted by atom name, then fallback to AutoDock type
        periodic = {
            "H","He","Li","Be","B","C","N","O","F","Ne","Na","Mg","Al","Si","P","S","Cl","Ar",
            "K","Ca","Sc","Ti","V","Cr","Mn","Fe","Co","Ni","Cu","Zn","Ga","Ge","As","Se","Br","Kr",
            "Rb","Sr","Y","Zr","Nb","Mo","Tc","Ru","Rh","Pd","Ag","Cd","In","Sn","Sb","Te","I","Xe",
            "Cs","Ba","La","Ce","Pr","Nd","Sm","Eu","Gd","Tb","Dy","Ho","Er","Tm","Yb","Lu","Hf","Ta","W",
            "Re","Os","Ir","Pt","Au","Hg","Tl","Pb","Bi","Po","At","Rn"
        }
        an = (atom_name or "").strip()
        candidate = an[:2].title() if len(an) >= 2 and an[0].isalpha() and an[1].islower() else (an[:1].upper() if an else "")
        if candidate in periodic:
            return candidate
        t = (ad_type or "").strip().replace("+", "").replace("-", "").lower()
        ad_map = {
            "a": "C", "c": "C",
            "o": "O", "oa": "O",
            "h": "H", "hd": "H",
            "n": "N", "na": "N",
            "s": "S", "sa": "S",
            "p": "P",
            "f": "F",
            "cl": "Cl",
            "br": "Br",
            "i": "I",
            "zn": "Zn", "mg": "Mg", "fe": "Fe", "ca": "Ca"
        }
        return ad_map.get(t, (candidate or "C"))

    def _split_models(lines: List[str]) -> List[List[str]]:
        models: List[List[str]] = []
        current: List[str] = []
        in_model = False
        for line in lines:
            if line.startswith("MODEL"):
                if current:
                    models.append(current)
                    current = []
                in_model = True
                continue
            if line.startswith("ENDMDL"):
                if current:
                    models.append(current)
                    current = []
                in_model = False
                continue
            if line.startswith("ATOM") or line.startswith("HETATM"):
                current.append(line.rstrip("\n\r"))
        if current:
            models.append(current)
        # If no explicit MODEL sections were found, this yields a single model of ATOM lines
        return models

    def _atoms_to_pdb_block(atom_lines: List[str]) -> str:
        out: List[str] = []
        serial_ctr = 1
        chain_id = "A"
        for raw in atom_lines:
            tok = raw.split()
            if len(tok) < 8:
                continue
            # Try to locate x,y,z as the first triple of floats after residue index
            # Typical PDBQT tokens: ATOM, serial, atom_name, resname, resnum, x, y, z, vdW, Elec, q, type
            atom_name = tok[2] if len(tok) > 2 else "C"
            resname = (tok[3] if len(tok) > 3 else "LIG")[:3]
            # Find residue number token (first integer after resname)
            resnum_idx = 4 if len(tok) > 4 else -1
            resnum = 1
            if resnum_idx >= 0:
                try:
                    resnum = int(float(tok[resnum_idx]))
                except Exception:
                    # Try next token as residue number
                    try:
                        resnum = int(float(tok[resnum_idx + 1]))
                        resnum_idx += 1
                    except Exception:
                        resnum = 1
            # Find coordinate start index
            xyz_idx = None
            for i in range(max(resnum_idx + 1, 5), len(tok) - 2):
                if _safe_float(tok[i]) and _safe_float(tok[i + 1]) and _safe_float(tok[i + 2]):
                    xyz_idx = i
                    break
            if xyz_idx is None:
                # Fallback to common positions
                xyz_idx = 5 if len(tok) > 7 else None
            if xyz_idx is None:
                continue
            try:
                x = float(tok[xyz_idx]); y = float(tok[xyz_idx + 1]); z = float(tok[xyz_idx + 2])
            except Exception:
                continue
            ad_type = tok[-1] if tok else ""
            element = _guess_element(atom_name, ad_type)
            # Preserve ATOM vs HETATM to enable cartoon/backbone in viewers
            record = "ATOM  " if raw.startswith("ATOM") else "HETATM"
            # Build a minimal but well-formed PDB line
            line = (
                f"{record}{serial_ctr:5d} "
                f"{atom_name:<4s}"
                f" {resname:>3s} {chain_id}{resnum:4d}    "
                f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00          {element:>2s}"
            )
            out.append(line)
            serial_ctr += 1
        out.append("TER")
        out.append("END")
        return "\n".join(out) + "\n"

    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        models = _split_models(lines)
        if not models:
            # If no ATOM records found, try as plain PDB
            return _read_pdb(path)
        from rdkit import Chem
        mols: List[Any] = []
        for atoms in models:
            pdb_block = _atoms_to_pdb_block(atoms)
            try:
                m = Chem.MolFromPDBBlock(pdb_block, sanitize=True, removeHs=False)
            except Exception:
                m = None
            if m is not None:
                mols.append(m)
        if mols:
            return mols
        # Fallback to direct PDB parse if conversion yielded nothing
        return _read_pdb(path)
    except Exception as e:
        if logger:
            try:
                logger.warning(f"PDBQT parse failed for {path}: {e}")
            except Exception:
                pass
        try:
            return _read_pdb(path)
        except Exception:
            return []


def _read_xyz(path: str) -> List[Any]:
    """Read an XYZ file into RDKit molecules.
    
    XYZ format:
    - First line: number of atoms
    - Second line: comment (optional) or blank line
    - Following lines: atom_symbol x y z coordinates
    - Multiple molecules separated by blank lines
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except ImportError:
        raise RuntimeError("RDKit is required for XYZ file reading")
    
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    
    mols: List[Any] = []
    
    # Find molecule boundaries
    molecule_starts = []
    for i, line in enumerate(lines):
        line = line.strip()
        if line.isdigit() and i + 1 < len(lines):
            # This could be the start of a molecule
            try:
                atom_count = int(line)
                if atom_count > 0 and i + 1 + atom_count <= len(lines):
                    molecule_starts.append(i)
            except ValueError:
                continue
    
    # Parse each molecule
    for start_idx in molecule_starts:
        try:
            atom_count = int(lines[start_idx])
            mol_lines = [lines[start_idx]]  # atom count
            
            # Add comment line (could be blank)
            if start_idx + 1 < len(lines):
                mol_lines.append(lines[start_idx + 1])
            
            # Add coordinate lines
            for i in range(atom_count):
                if start_idx + 2 + i < len(lines):
                    mol_lines.append(lines[start_idx + 2 + i])
            
            # Validate and parse
            if len(mol_lines) >= 2 + atom_count:
                is_valid, error_msg = _validate_xyz_format(mol_lines)
                if is_valid:
                    mol = _parse_xyz_molecule(mol_lines)
                    if mol is not None:
                        mols.append(mol)
                else:
                    print(f"Warning: Invalid XYZ format at line {start_idx + 1}: {error_msg}")
            
        except Exception as e:
            print(f"Warning: Error parsing molecule starting at line {start_idx + 1}: {e}")
            continue
    
    return mols


def _parse_xyz_molecule(lines: List[str]) -> Any:
    """Parse a single XYZ molecule from lines."""
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except ImportError:
        raise RuntimeError("RDKit is required for XYZ file reading")

    if len(lines) < 2:
        return None
    
    try:
        # First line should be atom count
        atom_count = int(lines[0])
        if atom_count <= 0:
            return None
        
        # Second line is comment (optional) or blank
        comment = lines[1] if len(lines) > 1 else ""
        
        # Check if we have enough lines for all atoms
        if len(lines) < 2 + atom_count:
            return None
        
        # Create RDKit molecule
        mol = Chem.RWMol()
        
        # Parse atom coordinates
        for i in range(atom_count):
            atom_line = lines[2 + i]
            parts = atom_line.split()
            if len(parts) >= 4:
                element = parts[0].strip()
                try:
                    x = float(parts[1])
                    y = float(parts[2])
                    z = float(parts[3])
                except ValueError:
                    print(f"Warning: Invalid coordinates in line {2 + i + 1}: {atom_line}")
                    continue
                
                # Add atom
                atom = mol.AddAtom(Chem.Atom(element))
                mol.GetAtomWithIdx(atom).SetProp("_x", str(x))
                mol.GetAtomWithIdx(atom).SetProp("_y", str(y))
                mol.GetAtomWithIdx(atom).SetProp("_z", str(z))
            else:
                print(f"Warning: Insufficient data in line {2 + i + 1}: {atom_line}")
        
        # Convert to regular molecule
        rdmol = mol.GetMol()
        if rdmol is None or rdmol.GetNumAtoms() == 0:
            return None
        
        # Set explicit valence to prevent automatic hydrogen addition
        # This preserves the exact atomic structure from the XYZ file
        for atom in rdmol.GetAtoms():
            atom.SetNoImplicit(True)  # Prevent implicit hydrogens
            atom.SetNumExplicitHs(0)  # Set explicit hydrogen count to 0
        
        # Add 3D conformer
        conf = Chem.Conformer(rdmol.GetNumAtoms())
        for i in range(rdmol.GetNumAtoms()):
            atom = rdmol.GetAtomWithIdx(i)
            x = float(atom.GetProp("_x"))
            y = float(atom.GetProp("_y"))
            z = float(atom.GetProp("_z"))
            conf.SetAtomPosition(i, (x, y, z))
        
        rdmol.AddConformer(conf)
        
        # Try to sanitize but DO NOT add hydrogens to preserve original XYZ structure
        try:
            # Use minimal sanitization to preserve exact atomic structure
            # Only clean up basic issues without adding hydrogens
            Chem.SanitizeMol(rdmol, sanitizeOps=Chem.SANITIZE_CLEANUP, catchErrors=True)
            # DO NOT add hydrogens - preserve original XYZ structure
        except Exception:
            pass
        
        return rdmol
        
    except Exception as e:
        print(f"Error parsing XYZ molecule: {e}")
        return None


def _ensure_3d_coordinates(mol: Any) -> Any:
    """Ensure molecule has 3D coordinates, generate if missing."""
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except ImportError:
        raise RuntimeError("RDKit is required for XYZ file reading")
    
    if mol is None:
        return None
    
    # Check if molecule already has 3D conformer
    conf = mol.GetConformer()
    if conf is not None:
        return mol
    
    try:
        from rdkit.Chem import AllChem
        
        # Try to generate 3D coordinates
        mol_copy = Chem.Mol(mol)
        result = AllChem.EmbedMolecule(mol_copy)
        if result >= 0:
            # Successfully generated coordinates
            return mol_copy
        else:
            print("Warning: Failed to generate 3D coordinates")
            return mol
    except Exception as e:
        print(f"Warning: Could not generate 3D coordinates: {e}")
        return mol


def _validate_xyz_format(lines: List[str]) -> tuple[bool, str]:
    """Validate XYZ file format and return (is_valid, error_message)."""
    if not lines:
        return False, "Empty file"
    
    try:
        # Check first line is atom count
        atom_count = int(lines[0])
        if atom_count <= 0:
            return False, f"Invalid atom count: {lines[0]}"
        
        # Check we have enough lines
        if len(lines) < 2 + atom_count:
            return False, f"Not enough lines for {atom_count} atoms"
        
        # Check coordinate lines (skip first two lines: atom count and comment/blank)
        for i in range(atom_count):
            coord_line = lines[2 + i]
            parts = coord_line.split()
            if len(parts) < 4:
                return False, f"Line {2 + i + 1}: insufficient coordinates"
            
            # Check element symbol
            element = parts[0].strip()
            if not element or len(element) > 2:
                return False, f"Line {2 + i + 1}: invalid element symbol '{element}'"
            
            # Check coordinates are numbers
            try:
                float(parts[1])
                float(parts[2])
                float(parts[3])
            except ValueError:
                return False, f"Line {2 + i + 1}: invalid coordinates"
        
        return True, "Valid XYZ format"
        
    except ValueError:
        return False, f"Invalid atom count: {lines[0]}"
    except Exception as e:
        return False, f"Validation error: {str(e)}"


def _create_xyz_content(mol: Any, name: str = "") -> str:
    """Create properly formatted XYZ content for a molecule."""
    if mol is None:
        return ""
    
    # For XYZ format, we should preserve the exact structure without modification
    # Only ensure we have 3D coordinates, but don't modify the molecule
    if mol.GetConformer() is None:
        mol = _ensure_3d_coordinates(mol)
    if mol is None:
        return ""
    
    # Get 3D coordinates
    conf = mol.GetConformer()
    if conf is None:
        return ""
    
    lines = []
    
    # Write atom count
    lines.append(str(mol.GetNumAtoms()))
    
    # Write comment line
    if not name:
        try:
            name = mol.GetProp("_Name") if mol.HasProp("_Name") else ""
            if not name:
                from rdkit import Chem
                name = Chem.MolToSmiles(mol)
        except Exception:
            name = "Molecule"
    
    lines.append(name)
    
    # Write atom coordinates with proper formatting
    for i in range(mol.GetNumAtoms()):
        atom = mol.GetAtomWithIdx(i)
        pos = conf.GetAtomPosition(i)
        element = atom.GetSymbol()
        # Format coordinates with consistent spacing (similar to example files)
        lines.append(f"  {element:<3} {pos.x:>12.6f} {pos.y:>12.6f} {pos.z:>12.6f}")
    
    return "\n".join(lines)


def _read_auto(path: str, logger=None) -> List[Any]:
    ext = Path(path).suffix.lower()
    if ext == ".sdf":
        return _read_sdf(path)
    if ext == ".mol":
        return _read_mol(path)
    if ext == ".mol2":
        return _read_mol2(path)
    if ext in {".pdb", ".ent"}:
        return _read_pdb(path)
    if ext == ".pdbqt":
        return _read_pdbqt(path, logger=logger)
    return []


class FolderInputNode(BaseNode):
    """Folder input that selects/outputs folder path.

    Outputs:
      - folder (string): selected folder path
    """

    def __init__(self):
        super().__init__("folder_input", "Folder Input")
        self.logger = get_logger(__name__)

        # Outputs only
        self.add_output_port("folder", "string")

        # Properties
        self.set_property("folder_path", "")  # folder path

        # Inline select button for quick folder picking (GUI only)
        try:
            from PySide6.QtWidgets import QPushButton, QFileDialog

            self.width = 260
            self.height = 120
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)

            btn = QPushButton("Select Folder…")
            btn.setToolTip("Open folder dialog")
            btn.clicked.connect(self._on_browse_clicked)  # type: ignore[attr-defined]

            layout = self.content_layout
            if layout is not None:
                from PySide6.QtWidgets import QSpacerItem, QSizePolicy
                layout.addItem(QSpacerItem(0, 8, QSizePolicy.Minimum, QSizePolicy.Fixed), 0, 0)
                layout.addWidget(btn, 1, 0)
            self._update_port_positions()
        except Exception:
            pass

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            folder_path = self.get_property("folder_path")
            if not folder_path:
                raise ValueError("No folder selected")
            if not Path(folder_path).exists():
                raise ValueError(f"Folder not found: {folder_path}")
            if not Path(folder_path).is_dir():
                raise ValueError(f"Path is not a folder: {folder_path}")
            return {
                "folder": folder_path,
            }
        except Exception as e:
            self.logger.error(f"Error collecting folder path: {e}")
            raise

    def validate(self) -> tuple[bool, str]:
        folder_path = self.get_property("folder_path")
        if not folder_path:
            return False, "No folder selected"
        if not Path(folder_path).exists():
            return False, f"Folder not found: {folder_path}"
        if not Path(folder_path).is_dir():
            return False, f"Path is not a folder: {folder_path}"
        return True, "Node configuration is valid"

    # GUI callback
    def _on_browse_clicked(self):  # pragma: no cover - UI-only
        try:
            from PySide6.QtWidgets import QFileDialog
            folder = QFileDialog.getExistingDirectory(
                None,
                "Select Input Folder",
                "",
                QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
            )
            if folder:
                self.set_property("folder_path", folder)
        except Exception:
            pass

    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        try:
            folder_path = self.get_property("folder_path") or ""
            if not folder_path:
                return ["No folder selected"]
            folder_name = Path(folder_path).name
            return ["Folder:", f"{folder_name}"]
        except Exception:
            return super()._inline_summary()


class FileInputNode(BaseNode):
    """File input that only selects/outputs path(s) without reading content.

    Outputs:
      - files (list): list of selected file paths
      - file (file): first file path (or empty string)
      - file_paths (string): semicolon-separated paths (for convenience)
    """

    def __init__(self):
        super().__init__("file_input", "File Input")
        self.logger = get_logger(__name__)

        # Outputs only
        self.add_output_port("files", "list")
        self.add_output_port("file", "file")
        self.add_output_port("file_paths", "string")

        # Properties
        self.set_property("file_paths", "")  # semicolon-separated or single

        # Inline select button for quick file picking (GUI only)
        try:
            from PySide6.QtWidgets import QPushButton, QFileDialog

            self.width = 260
            self.height = 120
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)

            btn = QPushButton("Select Files…")
            btn.setToolTip("Open file dialog (supports multi-select)")
            btn.clicked.connect(self._on_browse_clicked)  # type: ignore[attr-defined]

            layout = self.content_layout
            if layout is not None:
                from PySide6.QtWidgets import QSpacerItem, QSizePolicy
                layout.addItem(QSpacerItem(0, 8, QSizePolicy.Minimum, QSizePolicy.Fixed), 0, 0)
                layout.addWidget(btn, 1, 0)
            self._update_port_positions()
        except Exception:
            pass

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            raw = self.get_property("file_paths")
            files = _as_path_list(raw)
            first = files[0] if files else ""
            return {
                "files": files,
                "file": first,
                "file_paths": ";".join(files),
                "num_files": len(files),
            }
        except Exception as e:
            self.logger.error(f"Error collecting file paths: {e}")
            raise

    def validate(self) -> tuple[bool, str]:
        files = _as_path_list(self.get_property("file_paths"))
        if not files:
            return False, "No files selected"
        # if any don't exist, warn
        for p in files:
            if not Path(p).exists():
                return False, f"File not found: {p}"
        return True, "Node configuration is valid"

    # GUI callback
    def _on_browse_clicked(self):  # pragma: no cover - UI-only
        try:
            from PySide6.QtWidgets import QFileDialog
            files, _ = QFileDialog.getOpenFileNames(
                None,
                "Select Input Files",
                "",
                "All Files (*);;Chemistry (*.sdf *.mol *.mol2 *.pdb *.pdbqt *.xyz);;Data (*.csv *.tsv *.xlsx *.xls *.txt *.json *.arw)",
            )
            if files:
                self.set_property("file_paths", ";".join(files))
        except Exception:
            pass

    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        try:
            files = _as_path_list(self.get_property("file_paths") or "")
            if not files:
                return ["No files selected"]
            first = Path(files[0]).name
            more = len(files) - 1
            return ["Files:", f"{first}" + (f"  +{more} more" if more > 0 else "")]
        except Exception:
            return super()._inline_summary()


class FileOutputNode(BaseNode):
    """Node for saving data and molecules to files."""
    
    def __init__(self):
        super().__init__("file_output", "File Output")
        self.logger = get_logger(__name__)
        
        # Add ports
        self.add_input_port("molecules", "molecules")
        self.add_input_port("data", "data")
        self.add_input_port("string", "string")
        self.add_input_port("bytes", "bytes")
        self.add_input_port("image", "image")
        self.add_input_port("model", "model")
        self.add_output_port("saved_file", "string")
        self.add_output_port("file_size", "data")
        
        # Default properties
        self.set_property("output_path", "")
        # auto, sdf, mol, mol2, pdb, pdbqt, csv, tsv, xlsx, xls, json, txt
        self.set_property("file_type", "auto")
        self.set_property("overwrite", True)

        # Inline Browse UI for selecting save path (GUI only)
        try:
            from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QFileDialog, QSpacerItem, QSizePolicy

            # Tidy, consistent size
            self.width = 320
            self.height = 140
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)

            layout = self.content_layout
            if layout is not None:
                layout.addItem(QSpacerItem(0, 6, QSizePolicy.Minimum, QSizePolicy.Fixed), 0, 0, 1, 3)
                lbl = QLabel("Output Path")
                lbl.setStyleSheet("QLabel { background: transparent; }")
                edit = QLineEdit(self.get_property("output_path") or "")
                btn = QPushButton("Browse…")

                def on_browse():  # pragma: no cover - UI-only
                    try:
                        filters = (
                            "Molecules (*.sdf *.mol *.mol2 *.pdb *.pdbqt);;"
                            "Data (*.csv *.tsv *.xlsx *.xls *.json *.txt *.arw);;"
                            "Images (*.png *.jpg *.jpeg);;"
                            "All Files (*)"
                        )
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
        """Execute file output operation."""
        try:
            output_path = self.get_property("output_path")
            
            if not output_path:
                raise ValueError("Output path is required")
            
            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            file_type = self.get_property("file_type")
            
            # Auto-detect file type if needed
            if file_type == "auto":
                file_type = output_path_obj.suffix.lower().lstrip('.')
            
            # Check for overwrite
            if output_path_obj.exists() and not self.get_property("overwrite"):
                raise ValueError(f"File already exists and overwrite is disabled: {output_path}")
            
            # Save data based on type
            if inputs and "molecules" in inputs and inputs["molecules"] is not None:
                molecules = inputs["molecules"]
                self._save_molecules(molecules, output_path, file_type)
            elif inputs and "model" in inputs and inputs["model"] is not None:
                self._save_model(inputs["model"], output_path, file_type)
            elif inputs and "bytes" in inputs and inputs["bytes"] is not None:
                # Save raw bytes (e.g., image, SDF, etc.)
                Path(output_path).write_bytes(inputs["bytes"])            
            elif inputs and "image" in inputs and inputs["image"] is not None:
                # Image bytes are also raw bytes
                Path(output_path).write_bytes(inputs["image"])           
            elif inputs and "string" in inputs and inputs["string"] is not None:
                text = inputs["string"]
                if not isinstance(text, str):
                    text = str(text)
                Path(output_path).write_text(text, encoding="utf-8")
            elif inputs and "data" in inputs:
                data = inputs["data"]
                self._save_data(data, output_path, file_type)
            else:
                raise ValueError("No valid input data provided")
            
            self.logger.info(f"Successfully saved file: {output_path}")
            
            return {
                "saved_file": str(output_path),
                "file_size": output_path_obj.stat().st_size if output_path_obj.exists() else 0
            }
            
        except Exception as e:
            self.logger.error(f"Error saving file: {e}")
            raise
    
    def _save_molecules(self, molecules, output_path: str, file_type: str):
        """Save molecules to file."""
        try:
            from rdkit import Chem
            from backend.temp_manager import get_subdir
            from utils.external_tools import resolve_openbabel_executable
            import subprocess

            if file_type == 'sdf':
                writer = Chem.SDWriter(str(output_path))
                for mol in molecules:
                    if mol:
                        writer.write(mol)
                writer.close()

            elif file_type == 'mol':
                if molecules:
                    Chem.MolToMolFile(molecules[0], str(output_path))

            elif file_type == 'mol2':
                # Save first molecule as MOL2
                if molecules:
                    Chem.MolToMol2File(molecules[0], str(output_path))

            elif file_type == 'pdb':
                # Save first molecule as PDB
                if molecules:
                    Chem.MolToPDBFile(molecules[0], str(output_path))

            elif file_type == 'pdbqt':
                # Convert first molecule to PDB then to PDBQT via OpenBabel
                if molecules:
                    tmp_dir = get_subdir("save_molecule")
                    pdb_tmp = Path(tmp_dir) / "tmp_for_pdbqt.pdb"
                    Chem.MolToPDBFile(molecules[0], str(pdb_tmp))
                    obabel = resolve_openbabel_executable("obabel")
                    ob_dir = Path(obabel).parent if isinstance(obabel, str) else None
                    cmd = [obabel, str(pdb_tmp), "-O", str(output_path)]
                    subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=120,
                        cwd=str(ob_dir) if ob_dir else None,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
            elif file_type == 'xyz':
                # Write XYZ format
                with open(output_path, 'w', encoding='utf-8') as f:
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
                raise ValueError(f"Unsupported molecule file type: {file_type}")
                
        except ImportError:
            self.logger.error("RDKit not available, cannot save molecular files")
            raise
        except Exception as e:
            self.logger.error(f"Error saving molecules: {e}")
            raise
    
    def _save_data(self, data, output_path: str, file_type: str):
        """Save data to file."""
        try:
            if file_type == 'csv':
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    df = pd.DataFrame(data)
                    df.to_csv(output_path, index=False)
                else:
                    if hasattr(data, 'to_csv'):
                        data.to_csv(output_path, index=False)
                    else:
                        raise ValueError("Data must be list-of-dicts or DataFrame for CSV output")
            
            elif file_type == 'tsv':
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    df = pd.DataFrame(data)
                    df.to_csv(output_path, index=False, sep='\t')
                else:
                    if hasattr(data, 'to_csv'):
                        data.to_csv(output_path, index=False, sep='\t')
                    else:
                        raise ValueError("Data must be list-of-dicts or DataFrame for TSV output")
                    
            elif file_type == 'json':
                with open(output_path, 'w') as f:
                    json.dump(data, f, indent=2)
                    
            elif file_type == 'txt':
                with open(output_path, 'w') as f:
                    if isinstance(data, str):
                        f.write(data)
                    else:
                        f.write(str(data))
            
            elif file_type in {'xlsx', 'xls'}:
                try:
                    # Check if openpyxl is available
                    try:
                        import openpyxl
                    except ImportError:
                        raise RuntimeError("openpyxl is not installed. Please install it with: pip install openpyxl")
                    
                    if hasattr(data, 'to_excel'):
                        data.to_excel(output_path, index=False, engine='openpyxl')
                    elif isinstance(data, list) and (len(data) == 0 or isinstance(data[0], dict)):
                        pd.DataFrame(data).to_excel(output_path, index=False, engine='openpyxl')
                    else:
                        raise ValueError("Data must be list-of-dicts or DataFrame for Excel output")
                except Exception as e:
                    # Show the actual error instead of masking it
                    raise RuntimeError(f"Error writing Excel file: {str(e)}") from e
                        
            else:
                # Default to JSON for complex data
                with open(output_path, 'w') as f:
                    json.dump(data, f, indent=2)
                    
        except Exception as e:
            self.logger.error(f"Error saving data: {e}")
            raise

    def _save_model(self, model_obj: Any, output_path: str, file_type: str) -> None:
        """Save ML model to file using joblib if available, otherwise pickle.

        Honors file_type if provided (joblib/pkl/pickle), otherwise infers from extension.
        Default falls back to pickle with highest protocol.
        """
        try:
            ext = Path(output_path).suffix.lower().lstrip('.')
            ft = (file_type or ext or "").lower()
            # Normalize common aliases
            if ft in {"", "auto"}:
                ft = ext
            if ft in {"jl"}:
                ft = "joblib"
            if ft in {"pickle"}:
                ft = "pkl"

            if ft in {"joblib"}:
                try:
                    import joblib  # type: ignore
                    joblib.dump(model_obj, output_path)
                    return
                except Exception as e:
                    # Fall back to pickle if joblib unavailable or fails
                    self.logger.warning(f"joblib save failed ({e}); falling back to pickle")

            import pickle
            with open(output_path, 'wb') as f:
                pickle.dump(model_obj, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as e:
            self.logger.error(f"Error saving model: {e}")
            raise
    
    def validate(self) -> tuple[bool, str]:
        """Validate the node configuration."""
        output_path = self.get_property("output_path")
        
        if not output_path:
            return False, "Output path not specified"
        
        # Check if parent directory can be created
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return False, f"Cannot create output directory: {e}"
        
        return True, "Node configuration is valid"


# DataViewerNode removed (unused)


class SaveFileSinkNode(BaseNode):
    """Sink node that saves incoming data to a file and produces no outputs.

    Accepts one of: molecules | bytes | image | string | data.
    """

    def __init__(self):
        super().__init__("save_file", "Save File")
        self.logger = get_logger(__name__)

        # Inputs only (no outputs)
        self.add_input_port("molecules", "molecules")
        self.add_input_port("bytes", "bytes")
        self.add_input_port("image", "image")
        self.add_input_port("string", "string")
        self.add_input_port("data", "data")
        self.add_input_port("model", "model")

        # Properties
        self.set_property("output_path", "")
        self.set_property("file_type", "auto")
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
                        filters = (
                            "Molecules (*.sdf *.mol *.mol2 *.pdb *.pdbqt *.xyz);;"
                            "Data (*.csv *.tsv *.xlsx *.xls *.json *.txt);;"
                            "Images (*.png *.jpg *.jpeg);;"
                            "All Files (*)"
                        )
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
        # Headless-safe save logic (no GUI object instantiation)
        out_path = self.get_property("output_path")
        if not out_path:
            raise ValueError("Output path is required")
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        ftype = self.get_property("file_type") or "auto"
        if ftype == "auto":
            ftype = out.suffix.lower().lstrip('.')
        if out.exists() and not bool(self.get_property("overwrite")):
            raise ValueError(f"File already exists and overwrite is disabled: {out}")

        data = inputs or {}
        # Save molecules
        if data.get("molecules") is not None:
            try:
                from rdkit import Chem
                from backend.temp_manager import get_subdir
                import subprocess
                from utils.external_tools import resolve_openbabel_executable
                molecules = data.get("molecules") or []
                if ftype == 'sdf':
                    writer = Chem.SDWriter(str(out))
                    for m in molecules:
                        if m is not None:
                            writer.write(m)
                    writer.close()
                elif ftype == 'mol':
                    if molecules:
                        Chem.MolToMolFile(molecules[0], str(out))
                elif ftype == 'mol2':
                    if molecules:
                        Chem.MolToMol2File(molecules[0], str(out))
                elif ftype == 'pdb':
                    if molecules:
                        Chem.MolToPDBFile(molecules[0], str(out))
                elif ftype == 'pdbqt':
                    if molecules:
                        tmp_dir = get_subdir("save_molecule")
                        pdb_tmp = Path(tmp_dir) / "tmp_for_pdbqt.pdb"
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
            except ImportError:
                raise RuntimeError("RDKit not available, cannot save molecular files")
        # Raw bytes or image
        elif data.get("bytes") is not None:
            out.write_bytes(data.get("bytes") or b"")
        elif data.get("image") is not None:
            out.write_bytes(data.get("image") or b"")
        # ML model objects
        elif data.get("model") is not None:
            model_obj = data.get("model")
            try:
                ext = out.suffix.lower().lstrip('.')
                ft = (self.get_property("file_type") or ext or "").lower()
                if ft in ("", "auto"):
                    ft = ext
                if ft == "jl":
                    ft = "joblib"
                if ft == "pickle":
                    ft = "pkl"
                if ft == "joblib":
                    try:
                        import joblib  # type: ignore
                        joblib.dump(model_obj, str(out))
                    except Exception as e:
                        # Fallback to pickle
                        import pickle
                        self.logger.warning(f"joblib save failed ({e}); falling back to pickle")
                        with open(out, 'wb') as f:
                            pickle.dump(model_obj, f, protocol=pickle.HIGHEST_PROTOCOL)
                else:
                    import pickle
                    with open(out, 'wb') as f:
                        pickle.dump(model_obj, f, protocol=pickle.HIGHEST_PROTOCOL)
            except Exception as e:
                raise RuntimeError(f"Error saving model: {e}")
        # String
        elif data.get("string") is not None:
            text = data.get("string")
            if not isinstance(text, str):
                text = str(text)
            out.write_text(text, encoding="utf-8")
        # Generic data
        elif "data" in data:
            payload = data.get("data")
            if ftype == 'csv':
                import pandas as _pd
                if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                    _pd.DataFrame(payload).to_csv(out, index=False)
                else:
                    if hasattr(payload, 'to_csv'):
                        payload.to_csv(out, index=False)
                    else:
                        raise ValueError("Data must be list-of-dicts or DataFrame for CSV output")
            elif ftype == 'tsv':
                import pandas as _pd
                if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                    _pd.DataFrame(payload).to_csv(out, index=False, sep='\t')
                else:
                    if hasattr(payload, 'to_csv'):
                        payload.to_csv(out, index=False, sep='\t')
                    else:
                        raise ValueError("Data must be list-of-dicts or DataFrame for TSV output")
            elif ftype == 'json':
                out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            elif ftype == 'txt':
                out.write_text(str(payload), encoding="utf-8")
            elif ftype in {'xlsx', 'xls'}:
                try:
                    # Check if openpyxl is available
                    try:
                        import openpyxl
                    except ImportError:
                        raise RuntimeError("openpyxl is not installed. Please install it with: pip install openpyxl")
                    
                    if hasattr(payload, 'to_excel'):
                        payload.to_excel(out, index=False, engine='openpyxl')
                    elif isinstance(payload, list) and (len(payload) == 0 or isinstance(payload[0], dict)):
                        import pandas as _pd
                        _pd.DataFrame(payload).to_excel(out, index=False, engine='openpyxl')
                    else:
                        raise ValueError("Data must be list-of-dicts or DataFrame for Excel output")
                except Exception as e:
                    # Show the actual error instead of masking it
                    raise RuntimeError(f"Error writing Excel file: {str(e)}") from e
            else:
                out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        else:
            raise ValueError("No valid input provided to save")
        return {}

    def validate(self) -> tuple[bool, str]:
        output_path = self.get_property("output_path")
        if not output_path:
            return False, "Output path not specified"
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return False, f"Cannot create output directory: {e}"
        return True, "Node configuration is valid"


# --------------------------
# Molecule Reader Nodes
# --------------------------


class _BaseMolReaderNode(BaseNode):
    """Base for molecule readers that parse one or more files into RDKit molecules.

    Subclasses should define:
      - self.node_type
      - self.title
      - self._supported_exts: set[str] like {".sdf"}
      - self._read_one(path: str) -> list[Mol]
    Inputs:
      - files (list): list of paths
      - file (file): single path
    Outputs:
      - molecules (molecules)
    """

    _supported_exts: set[str] = set()

    def __init__(self, node_type: str, title: str):
        super().__init__(node_type, title)
        self.logger = get_logger(__name__)
        self.add_input_port("files", "list")
        self.add_input_port("file", "file")
        self.add_output_port("molecules", "molecules")
        # Optional fallback property if not wired
        self.set_property("file_paths", "")

    def _paths_from_inputs(self, inputs: Optional[Dict[str, Any]]) -> List[str]:
        if inputs:
            if inputs.get("files"):
                return _as_path_list(inputs["files"])
            if inputs.get("file"):
                return _as_path_list(inputs["file"])
        return _as_path_list(self.get_property("file_paths"))

    def _read_one(self, path: str) -> List[Any]:  # RDKit Mol objects
        raise NotImplementedError

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            from rdkit import Chem  # noqa: F401
        except Exception as e:
            self.logger.error("RDKit not available; molecule readers require RDKit")
            raise

        paths = self._paths_from_inputs(inputs)
        if not paths:
            raise ValueError("No input files provided")

        mols: List[Any] = []
        for p in paths:
            ext = Path(p).suffix.lower()
            if self._supported_exts and ext not in self._supported_exts:
                # Skip unsupported file
                self.logger.warning(f"Skipping unsupported file for {self.node_type}: {p}")
                continue
            try:
                mlist = self._read_one(p)
                for m in (mlist or []):
                    if m is not None:
                        mols.append(m)
            except Exception as e:
                self.logger.warning(f"Failed to read {p}: {e}")

        return {"molecules": mols, "num_molecules": len(mols)}


class SDFReaderNode(_BaseMolReaderNode):
    def __init__(self):
        super().__init__("sdf_reader", "SDF Reader")
        self._supported_exts = {".sdf"}

    def _read_one(self, path: str) -> List[Any]:
        return _read_sdf(path)


class MOLReaderNode(_BaseMolReaderNode):
    def __init__(self):
        super().__init__("mol_reader", "MOL Reader")
        self._supported_exts = {".mol"}

    def _read_one(self, path: str) -> List[Any]:
        return _read_mol(path)


class MOL2ReaderNode(_BaseMolReaderNode):
    def __init__(self):
        super().__init__("mol2_reader", "MOL2 Reader")
        self._supported_exts = {".mol2"}

    def _read_one(self, path: str) -> List[Any]:
        return _read_mol2(path)


class PDBReaderNode(_BaseMolReaderNode):
    def __init__(self):
        super().__init__("pdb_reader", "PDB Reader")
        self._supported_exts = {".pdb", ".ent"}

    def _read_one(self, path: str) -> List[Any]:
        return _read_pdb(path)


class PDBQTReaderNode(_BaseMolReaderNode):
    def __init__(self):
        super().__init__("pdbqt_reader", "PDBQT Reader")
        self._supported_exts = {".pdbqt"}

    def _read_one(self, path: str) -> List[Any]:
        return _read_pdbqt(path, logger=self.logger)


class XYZReaderNode(_BaseMolReaderNode):
    """Node for reading XYZ format files into RDKit molecules."""
    
    def __init__(self):
        super().__init__("xyz_reader", "XYZ Reader")
        self._supported_exts = {".xyz"}

    def _read_one(self, path: str) -> List[Any]:
        return _read_xyz(path)


class AutoMolReaderNode(_BaseMolReaderNode):
    """Generic molecule reader that detects by extension (SDF/MOL/MOL2/PDB/PDBQT/XYZ)."""

    def __init__(self):
        super().__init__("mol_reader_auto", "Molecule Reader (Auto)")
        self._supported_exts = {".sdf", ".mol", ".mol2", ".pdb", ".ent", ".pdbqt", ".xyz"}

    def _read_one(self, path: str) -> List[Any]:
        return _read_auto(path, logger=self.logger)


# --------------------------
# Tabular/Text Reader Nodes
# --------------------------


class CSVReaderNode(BaseNode):
    """Read one or more CSV/TSV files into list-of-dicts data."""

    def __init__(self):
        super().__init__("csv_reader", "CSV/TSV Reader")
        self.logger = get_logger(__name__)
        self.add_input_port("files", "list")
        self.add_input_port("file", "file")
        self.add_output_port("data", "data")
        self.set_property("file_paths", "")
        self.set_property("delimiter", "auto")  # auto, comma, semicolon, tab
        self.set_property("encoding", "utf-8")

    def _detect_sep(self, path: str) -> str:
        ext = Path(path).suffix.lower()
        if ext == ".tsv":
            return "\t"
        if ext in {".csv"}:
            return ","
        # fallback
        return ","

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        paths = _as_path_list(inputs.get("files") if inputs else None) or _as_path_list(inputs.get("file") if inputs else None)
        if not paths:
            paths = _as_path_list(self.get_property("file_paths"))
        if not paths:
            raise ValueError("No CSV/TSV files provided")
        out_rows: List[Dict[str, Any]] = []
        delim = (self.get_property("delimiter") or "auto").lower()
        enc = self.get_property("encoding") or "utf-8"
        for p in paths:
            sep = {"comma": ",", "semicolon": ";", "tab": "\t"}.get(delim)
            if sep is None:
                sep = self._detect_sep(p)
            try:
                df = pd.read_csv(p, sep=sep, encoding=enc)
                out_rows.extend(df.to_dict("records"))
            except Exception as e:
                self.logger.warning(f"Failed to read {p}: {e}")
        return {"data": out_rows, "num_rows": len(out_rows)}


class ExcelReaderNode(BaseNode):
    """Read one or more Excel files (.xlsx, .xls) into list-of-dicts data."""

    def __init__(self):
        super().__init__("excel_reader", "Excel Reader")
        self.logger = get_logger(__name__)
        self.add_input_port("files", "list")
        self.add_input_port("file", "file")
        self.add_output_port("data", "data")
        self.set_property("file_paths", "")
        self.set_property("sheet", "")  # name or index (int)
        self.set_property("header", True)
        self.set_property("engine", "auto")  # auto/openpyxl/xlrd

    def _read_one(self, path: str) -> List[Dict[str, Any]]:
        sheet = self.get_property("sheet")
        header = 0 if bool(self.get_property("header")) else None
        engine = self.get_property("engine") or "auto"
        kwargs: Dict[str, Any] = {}
        if engine != "auto":
            kwargs["engine"] = engine
        try:
            df = pd.read_excel(path, sheet_name=sheet if sheet not in (None, "") else 0, header=header, **kwargs)
            # If multiple sheets returned as dict of DataFrames, concat
            if isinstance(df, dict):
                import pandas as _pd
                df = _pd.concat(df.values(), ignore_index=True)
            return df.to_dict("records")
        except Exception as e:
            self.logger.warning(f"Failed to read Excel {path}: {e}")
            return []

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        paths = _as_path_list(inputs.get("files") if inputs else None) or _as_path_list(inputs.get("file") if inputs else None)
        if not paths:
            paths = _as_path_list(self.get_property("file_paths"))
        if not paths:
            raise ValueError("No Excel files provided")
        out: List[Dict[str, Any]] = []
        for p in paths:
            out.extend(self._read_one(p))
        return {"data": out, "num_rows": len(out)}


class TXTReaderNode(BaseNode):
    """Read text files. Can emit as raw string or list of lines (data)."""

    def __init__(self):
        super().__init__("txt_reader", "TXT Reader")
        self.logger = get_logger(__name__)
        self.add_input_port("files", "list")
        self.add_input_port("file", "file")
        self.add_output_port("data", "data")
        self.add_output_port("string", "string")
        self.set_property("file_paths", "")
        self.set_property("mode", "lines")  # lines|text
        self.set_property("encoding", "utf-8")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        paths = _as_path_list(inputs.get("files") if inputs else None) or _as_path_list(inputs.get("file") if inputs else None)
        if not paths:
            paths = _as_path_list(self.get_property("file_paths"))
        if not paths:
            raise ValueError("No TXT files provided")
        mode = (self.get_property("mode") or "lines").lower()
        enc = self.get_property("encoding") or "utf-8"
        texts: List[str] = []
        rows: List[Dict[str, Any]] = []
        for p in paths:
            try:
                content = Path(p).read_text(encoding=enc)
                texts.append(content)
                if mode == "lines":
                    for i, line in enumerate(content.splitlines()):
                        rows.append({"file": str(p), "line_no": i + 1, "line": line})
            except Exception as e:
                self.logger.warning(f"Failed to read {p}: {e}")
        return {
            "string": "\n\n".join(texts),
            "data": rows if mode == "lines" else [{"file": str(p), "text": t} for p, t in zip(paths, texts)],
        }


class TableViewNode(BaseNode):
    """Inline table viewer that displays list-of-dicts or DataFrame-like data.

    Inputs: data (data)
    Outputs: none (viewer)
    """

    def __init__(self):
        super().__init__("table_view", "Table View")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        # Visual size
        self.width = 360
        self.height = 220
        self.setMinimumSize(self.width, self.height)
        self.setMaximumSize(self.width, self.height)
        # Fill the node body completely (no inner spacing)
        try:
            self.set_content_margins(0, 32, 0, 0)
        except Exception:
            pass
        # Inline widget
        try:
            # Respect lightweight construction mode to avoid heavy widget init during compatibility probing
            from core.nodes import BaseNode as _BaseNode
            if getattr(_BaseNode, "_lightweight_construction", False):  # type: ignore[attr-defined]
                self._table = None
            else:
                from PySide6.QtWidgets import QTableWidget
                self._table = QTableWidget()
            self._table.setColumnCount(0)
            self._table.setRowCount(0)
            # Visual tweaks to ensure it is visible and readable
            try:
                self._table.setAlternatingRowColors(True)
                self._table.setShowGrid(True)
                header = self._table.horizontalHeader()
                header.setStretchLastSection(True)
            except Exception:
                pass
            layout = self.content_layout
            if layout is not None and self._table is not None:
                layout.addWidget(self._table, 0, 0)
            # Re-align ports after custom width/height
            self._update_port_positions()
        except Exception:
            self._table = None

    def _set_table_data(self, data: Any) -> None:
        try:
            from PySide6.QtWidgets import QTableWidgetItem
        except Exception:
            return
        if self._table is None:
            return
        # Temporarily disable painting for faster updates and to avoid re-entrancy
        try:
            self._table.setUpdatesEnabled(False)
            self._table.setSortingEnabled(False)
        except Exception:
            pass
        # Normalize to list[dict]
        rows: list[dict]
        if data is None:
            rows = []
        elif isinstance(data, list) and (len(data) == 0 or isinstance(data[0], dict)):
            rows = data
        else:
            # Try pandas DataFrame or decode JSON strings for list elements
            try:
                import pandas as pd
                if isinstance(data, pd.DataFrame):
                    rows = data.to_dict(orient="records")
                else:
                    # If list of stringified JSON dicts, coerce
                    if isinstance(data, list) and data and all(isinstance(x, str) and str(x).lstrip().startswith(('{','[')) for x in data[:5]):
                        import json as _json
                        tmp = []
                        for x in data:
                            try:
                                obj = _json.loads(str(x))
                                if isinstance(obj, dict):
                                    tmp.append(obj)
                                else:
                                    tmp.append({"value": obj})
                            except Exception:
                                tmp.append({"value": x})
                        rows = tmp
                    else:
                        rows = [
                            {"value": str(item)} for item in (data if isinstance(data, list) else [data])
                        ]
            except Exception:
                rows = [
                    {"value": str(data)}
                ]
        max_rows = 100
        rows = rows[:max_rows]
        headers = list(rows[0].keys()) if rows else []
        self._table.clear()
        self._table.setColumnCount(len(headers))
        if headers:
            try:
                self._table.setHorizontalHeaderLabels(headers)
            except Exception:
                pass
        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, key in enumerate(headers):
                val = row.get(key, "")
                item = QTableWidgetItem(str(val))
                self._table.setItem(r, c, item)
        try:
            self._table.setSortingEnabled(True)
            self._table.setUpdatesEnabled(True)
        except Exception:
            pass

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = inputs.get("data") if inputs else None
        # Return a tiny summary; UI is updated via on_result
        if isinstance(data, list):
            size = len(data)
        elif isinstance(data, dict):
            size = len(data)
        elif data is None:
            size = 0
        else:
            size = 1
        return {"preview_size": size, "preview_type": type(data).__name__}

    def on_result(self, result: object) -> None:
        # Pull last connected input if available via properties snapshot
        try:
            data = self.properties.get("last_input_data")
            if data is not None:
                self._set_table_data(data)
        except Exception:
            pass
        super().on_result(result)


class TextInputNode(BaseNode):
    """Inline single-line text input that emits its content as a string.

    Outputs: string (text)
    """

    def __init__(self):
        super().__init__("text_input", "Text Input")
        self.logger = get_logger(__name__)
        # One output: the text content
        self.add_output_port("string", "string")

        # Visual size
        self.width = 280
        self.height = 120
        self.setMinimumSize(self.width, self.height)
        self.setMaximumSize(self.width, self.height)

        # Properties
        self.set_property("text", "")
        self.set_property("placeholder", "Type here…")

        # Inline QLineEdit
        try:
            # Skip heavy widget creation when in lightweight probing mode
            from core.nodes import BaseNode as _BaseNode
            if getattr(_BaseNode, "_lightweight_construction", False):  # type: ignore[attr-defined]
                self._edit = None
            else:
                from PySide6.QtWidgets import QLineEdit, QSpacerItem, QSizePolicy
                self._edit = QLineEdit()
                self._edit.setPlaceholderText(self.get_property("placeholder") or "")
                self._edit.setText(self.get_property("text") or "")
                self._edit.textChanged.connect(self._on_text_changed)

                layout = self.content_layout
                if layout is not None:
                    layout.addItem(QSpacerItem(0, 8, QSizePolicy.Minimum, QSizePolicy.Fixed), 0, 0)
                    layout.addWidget(self._edit, 1, 0)
                # Ensure the single output port sits on the far right after resize
                self._update_port_positions()
        except Exception:
            self._edit = None

    def _on_text_changed(self, text: str):
        try:
            self.set_property("text", text)
        except Exception:
            pass

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Emit current text as output
        text = self.get_property("text") or ""
        return {"string": text}


class TextViewerNode(BaseNode):
    """Inline text viewer that displays incoming string or JSON-serializable data."""

    def __init__(self):
        super().__init__("text_view", "Text View")
        self.logger = get_logger(__name__)
        self.add_input_port("string", "string")
        self.add_input_port("data", "data")
        self.width = 360
        self.height = 220
        self.setMinimumSize(self.width, self.height)
        self.setMaximumSize(self.width, self.height)
        # Fill the node body completely (no inner spacing)
        try:
            self.set_content_margins(0, 32, 0, 0)
        except Exception:
            pass
        try:
            # Respect lightweight construction
            from core.nodes import BaseNode as _BaseNode
            if getattr(_BaseNode, "_lightweight_construction", False):  # type: ignore[attr-defined]
                self._text = None
            else:
                from PySide6.QtWidgets import QPlainTextEdit
                from PySide6.QtCore import Qt
                self._text = QPlainTextEdit()
                self._text.setReadOnly(True)
                
                # Enable custom context menu
                self._text.setContextMenuPolicy(Qt.CustomContextMenu)
                self._text.customContextMenuRequested.connect(self._show_text_context_menu)
                
                layout = self.content_layout
                if layout is not None:
                    layout.addWidget(self._text, 0, 0)
                # Re-align ports after custom width/height
                self._update_port_positions()
        except Exception:
            self._text = None
    
    def _show_text_context_menu(self, position):
        """Show custom context menu for text widget."""
        try:
            from PySide6.QtWidgets import QMenu
            from PySide6.QtGui import QAction
            
            if self._text is None:
                return
            
            menu = QMenu(self._text)
            
            # Copy Selected Text action
            copy_action = QAction("Copy Selected Text", self._text)
            copy_action.setEnabled(self._text.textCursor().hasSelection())
            copy_action.triggered.connect(lambda: self._text.copy())
            menu.addAction(copy_action)
            
            menu.addSeparator()
            
            # Clear action
            clear_action = QAction("Clear", self._text)
            clear_action.triggered.connect(lambda: self._text.clear())
            menu.addAction(clear_action)
            
            # Show menu at cursor position
            menu.exec_(self._text.mapToGlobal(position))
        except Exception as e:
            self.logger.error(f"Error showing context menu: {e}")

    def _stringify(self, value: Any) -> str:
        try:
            if isinstance(value, (dict, list)):
                import json
                return json.dumps(value, indent=2)[:8000]
            return str(value)
        except Exception:
            return str(value)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        content = None
        if inputs:
            content = inputs.get("string") if inputs.get("string") is not None else inputs.get("data")
        text = self._stringify(content)
        return {"text_preview": text[:2000]}

    def on_result(self, result: object) -> None:
        try:
            content = self.properties.get("last_input_string")
            if content is None:
                content = self.properties.get("last_input_data")
            if self._text is not None:
                self._text.setPlainText(self._stringify(content))
        except Exception:
            pass
        super().on_result(result)


class ImageViewerNode(BaseNode):
    """Inline image viewer that displays PNG/JPEG bytes passed to input."""

    def __init__(self):
        super().__init__("image_view", "Image View")
        self.logger = get_logger(__name__)
        self.add_input_port("image", "image")
        self.add_input_port("bytes", "bytes")
        self.width = 300
        self.height = 250
        self.setMinimumSize(self.width, self.height)
        self.setMaximumSize(self.width, self.height)
        # Properties - remove lazy property as we want automatic display
        self.set_property("auto_scale", True)
        try:
            # Respect lightweight construction
            from core.nodes import BaseNode as _BaseNode
            if getattr(_BaseNode, "_lightweight_construction", False):  # type: ignore[attr-defined]
                self._label = None
            else:
                from PySide6.QtWidgets import QLabel
                from PySide6.QtCore import Qt
                from PySide6.QtWidgets import QSizePolicy
                self._label = QLabel()
                self._label.setAlignment(Qt.AlignCenter)
                try:
                    # Fill the node body completely for image display
                    self.set_content_margins(8, 40, 8, 8)
                    self._label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                    self._label.setText("No image")
                    self._label.setStyleSheet("QLabel { background-color: rgba(40, 40, 40, 100); border: 1px solid #666; border-radius: 4px; color: #ccc; }")
                except Exception:
                    pass
                layout = self.content_layout
                if layout is not None:
                    # Only add the label - no buttons needed
                    layout.addWidget(self._label, 0, 0)
                # Re-align ports after custom width/height
                self._update_port_positions()
        except Exception:
            self._label = None

    def set_property(self, key, value):
        super().set_property(key, value)
        # Auto-render when new image/bytes arrive
        try:
            if key in ("last_input_image", "last_input_bytes"):
                # Always show image immediately when data arrives
                try:
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, lambda d=value: self._set_image(d))
                except Exception:
                    self._set_image(value)
        except Exception:
            pass

    def _set_image(self, data: Optional[bytes]) -> None:
        """Display image data in the label with proper scaling."""
        if self._label is None or data is None or len(data) == 0:
            if self._label is not None:
                self._label.setText("No image")
            return
        
        try:
            from PySide6.QtGui import QPixmap, QImage
            from PySide6.QtCore import Qt
            
            # Try to load image with Qt first
            img = QImage.fromData(data)
            if img.isNull():
                # Fallback: decode with Pillow if Qt image plugins are unavailable
                try:
                    import io
                    from PIL import Image as _PILImage  # type: ignore
                    pil = _PILImage.open(io.BytesIO(data)).convert("RGBA")
                    w, h = pil.size
                    buf = pil.tobytes("raw", "RGBA")
                    img = QImage(buf, w, h, QImage.Format_RGBA8888).copy()
                except Exception as e:
                    self.logger.warning(f"Failed to decode image data: {e}")
                    self._label.setText("Invalid image")
                    return
            
            if img.isNull():
                self._label.setText("Invalid image")
                return
            
            # Calculate available space for image (account for margins and borders)
            available_width = max(32, self.width - 24)  # 8px margin on each side + some padding
            available_height = max(32, self.height - 56)  # 40px top margin + 8px bottom + padding
            
            # Scale image to fit available space while maintaining aspect ratio
            # Use positional args for PySide6 compatibility: scaled(w, h, mode, transform)
            scaled = img.scaled(
                available_width,
                available_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            
            # Set the scaled image
            self._label.setPixmap(QPixmap.fromImage(scaled))
            self._label.setText("")  # Clear "No image" text
            
            self.logger.info(f"Image displayed: {img.width()}x{img.height()} -> {scaled.width()}x{scaled.height()}")
            
        except Exception as e:
            self.logger.error(f"Error displaying image: {e}")
            self._label.setText("Error loading image")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Process image data and return summary."""
        if not inputs:
            return {"image_size": 0}
        
        # Get image data from either port
        image_data = inputs.get("image") or inputs.get("bytes")
        size = len(image_data) if image_data else 0
        
        return {"image_size": size}

    def on_result(self, result: object) -> None:
        """Handle execution result and display image."""
        try:
            # Get image data from stored inputs
            data = self.properties.get("last_input_image")
            if data is None:
                data = self.properties.get("last_input_bytes")
            
            # Always show image automatically when data is available
            if data:
                try:
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, lambda d=data: self._set_image(d))
                except Exception:
                    self._set_image(data)
        except Exception:
            pass
        super().on_result(result)

    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        # Hide inline summary (no label or size shown under the title)
        return []


 


class SaveDataFrameNode(BaseNode):
    """Save DataFrame or tabular data (list-of-dicts) to CSV/TSV/Excel."""

    def __init__(self):
        super().__init__("save_dataframe", "Save DataFrame")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("saved_file", "string")
        self.set_property("output_path", "")
        self.set_property("file_type", "auto")  # auto|csv|tsv|xlsx|xls
        self.set_property("overwrite", True)
        self.set_property("include_index", False)

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
                        filters = "CSV (*.csv);;TSV (*.tsv);;Excel (*.xlsx *.xls);;All Files (*)"
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
        data = (inputs or {}).get("data")
        if data is None:
            raise ValueError("No data provided")
        include_index = bool(self.get_property("include_index"))
        if ftype == "csv":
            if hasattr(data, 'to_csv'):
                data.to_csv(out, index=include_index)
            elif isinstance(data, list) and (len(data) == 0 or isinstance(data[0], dict)):
                pd.DataFrame(data).to_csv(out, index=include_index)
            else:
                raise ValueError("Data must be DataFrame or list-of-dicts for CSV")
        elif ftype == "tsv":
            if hasattr(data, 'to_csv'):
                data.to_csv(out, index=include_index, sep='\t')
            elif isinstance(data, list) and (len(data) == 0 or isinstance(data[0], dict)):
                pd.DataFrame(data).to_csv(out, index=include_index, sep='\t')
            else:
                raise ValueError("Data must be DataFrame or list-of-dicts for TSV")
        elif ftype in {"xlsx", "xls"}:
            try:
                # Check if openpyxl is available
                try:
                    import openpyxl
                except ImportError:
                    raise RuntimeError("openpyxl is not installed. Please install it with: pip install openpyxl")
                
                if hasattr(data, 'to_excel'):
                    data.to_excel(out, index=include_index, engine='openpyxl')
                elif isinstance(data, list) and (len(data) == 0 or isinstance(data[0], dict)):
                    pd.DataFrame(data).to_excel(out, index=include_index, engine='openpyxl')
                else:
                    raise ValueError("Data must be DataFrame or list-of-dicts for Excel")
            except Exception as e:
                # Show the actual error instead of masking it
                raise RuntimeError(f"Error writing Excel file: {str(e)}") from e
        else:
            raise ValueError(f"Unsupported DataFrame file type: {ftype}")
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


class SaveTextNode(BaseNode):
    """Save text/log content to a file."""

    def __init__(self):
        super().__init__("save_text", "Save Text")
        self.logger = get_logger(__name__)
        self.add_input_port("string", "string")
        self.add_input_port("data", "data")
        self.add_output_port("saved_file", "string")
        self.set_property("output_path", "")
        self.set_property("file_type", "auto")  # auto|txt|log
        self.set_property("overwrite", True)
        self.set_property("encoding", "utf-8")

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
                        filters = "Text (*.txt *.log);;All Files (*)"
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
        content = None
        if inputs:
            content = inputs.get("string") if inputs.get("string") is not None else inputs.get("data")
        if content is None:
            raise ValueError("No text provided")
        if not isinstance(content, str):
            try:
                content = json.dumps(content, indent=2)
            except Exception:
                content = str(content)
        enc = self.get_property("encoding") or "utf-8"
        out.write_text(content, encoding=enc)
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


class SaveJsonNode(BaseNode):
    """Save data as JSON file with pretty formatting."""

    def __init__(self):
        super().__init__("save_json", "Save JSON")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("saved_file", "string")
        self.set_property("output_path", "")
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
                        filters = "JSON (*.json);;All Files (*)"
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
        data = (inputs or {}).get("data")
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
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


class SaveImageNode(BaseNode):
    """Save image/bytes to file (PNG/JPG)."""

    def __init__(self):
        super().__init__("save_image", "Save Image")
        self.logger = get_logger(__name__)
        self.add_input_port("image", "image")
        self.add_input_port("bytes", "bytes")
        self.add_output_port("saved_file", "string")
        self.set_property("output_path", "")
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
                        filters = "Images (*.png *.jpg *.jpeg);;All Files (*)"
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
        data = None
        if inputs:
            data = inputs.get("image") if inputs.get("image") is not None else inputs.get("bytes")
        if data is None:
            raise ValueError("No image/bytes provided")
        out.write_bytes(data)
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
