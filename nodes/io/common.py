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








# DataViewerNode removed (unused)




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
















# --------------------------
# Tabular/Text Reader Nodes
# --------------------------

# Re-export every helper/import so split node files keep the original module namespace.
__all__ = [name for name in globals() if not name.startswith("__")]
