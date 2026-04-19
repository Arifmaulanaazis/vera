"""
Molecular minimization nodes using RDKit and OpenBabel.
"""

import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from core.nodes import BaseNode
from utils.logging_utils import get_logger
from utils.external_tools import resolve_openbabel_executable
from backend.temp_manager import get_subdir


class RDKitMinimizeNode(BaseNode):
    """Node for molecular minimization using RDKit."""
    
    def __init__(self):
        super().__init__("rdkit_minimize", "RDKit Minimize")
        self.logger = get_logger(__name__)
        
        # Add ports - only output minimized molecules
        self.add_input_port("input_molecules", "molecules")
        # Optional SMILES input (list[str] or DataFrame with a SMILES column)
        self.add_input_port("smiles", "data")
        self.add_output_port("molecules", "molecules")
        self.add_output_port("energies", "data")
        
        # Default properties
        self.set_property("input_file", "")
        self.set_property("output_file", "")
        self.set_property("max_iterations", 1000)
        self.set_property("force_field", "MMFF94")
        self.set_property("convergence_threshold", 1e-6)
        self.set_property("optimize_conformers", False)  # Default to single conformer minimization
        self.set_property("num_conformers", 10)  # Reduced default
        # Preserve hydrogen state from input molecule
        self.set_property("add_hydrogens", False)
        # Optional: column name to read SMILES from when a DataFrame is provided
        self.set_property("smiles_column", "smiles")
        
    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute RDKit minimization.

        Returns energies as a pandas DataFrame with explicit units in the
        column name for clarity: "Energy (kcal/mol)".
        """
        try:
            # Import RDKit (only when needed)
            from rdkit import Chem
            from rdkit.Chem import AllChem  # noqa: F401
            # Import pandas lazily to format the energy table
            import pandas as pd  # type: ignore
            # Get input (molecules or SMILES)
            input_molecules = inputs.get("input_molecules") if inputs else None
            smiles_input = inputs.get("smiles") if inputs else None
            input_file = self.get_property("input_file")

            molecules = None
            names_from_smiles: list[str] = []
            if input_molecules:
                molecules = input_molecules
            elif smiles_input is not None:
                molecules, names_from_smiles = self._molecules_from_smiles_input(smiles_input)
            elif input_file and Path(input_file).exists():
                molecules = self._read_molecules_from_file(input_file)
            else:
                raise ValueError("No valid input molecules or file provided")

            minimized_molecules = []
            energies = []
            names: list[str] = []

            for i, mol in enumerate(molecules):
                if mol is None:
                    self.logger.warning(f"Skipping invalid molecule at index {i}")
                    continue
                try:
                    # Preserve original hydrogen state unless explicitly requested
                    add_h = bool(self.get_property("add_hydrogens"))
                    if add_h and not any(atom.GetAtomicNum() == 1 for atom in mol.GetAtoms()):
                        mol_to_min = Chem.AddHs(mol)
                    else:
                        mol_to_min = Chem.Mol(mol)
                    
                    # Ensure 1-based molecule naming: use SMILES order when provided, else sequential
                    try:
                        name_val = names_from_smiles[i] if (names_from_smiles and i < len(names_from_smiles)) else str(i + 1)
                        mol_to_min.SetProp("_Name", str(name_val))
                    except Exception:
                        pass

                    # Choose minimization strategy
                    if self.get_property("optimize_conformers"):
                        minimized_mol, energy = self._optimize_conformers_and_select_best(mol_to_min)
                        energies.append(energy)
                    else:
                        energy = self._minimize_molecule(mol_to_min)
                        minimized_mol = mol_to_min
                        energies.append(energy)
                    
                    minimized_molecules.append(minimized_mol)
                    # Try to capture molecule name if present
                    try:
                        names.append(mol.GetProp("_Name"))
                    except Exception:
                        # Fallback to 1-based sequential naming
                        names.append(str(len(minimized_molecules)))
                except Exception as e:
                    self.logger.error(f"Error minimizing molecule {i}: {e}")
                    continue

            self.logger.info(
                f"RDKit minimization completed. Processed {len(minimized_molecules)} molecules"
            )
            # Build a clear DataFrame for energies with explicit units
            force_field = str(self.get_property("force_field"))
            optimize_conformers = bool(self.get_property("optimize_conformers"))
            df_payload = {
                "Molecule Index": list(range(1, len(energies) + 1)),
                "Name": names,
                "Energy (kcal/mol)": energies,
                "Force Field": [force_field] * len(energies),
                "Optimized Conformers": [optimize_conformers] * len(energies),
            }
            energies_df = pd.DataFrame(df_payload)

            return {
                "molecules": minimized_molecules,
                "energies": energies_df,  # Keep the same port name, now a DataFrame
                "num_molecules": len(minimized_molecules),
            }
        except ImportError as e:
            error_msg = "RDKit is not installed. Please install RDKit to use this node."
            self.logger.error(error_msg)
            raise RuntimeError(error_msg) from e
        except Exception as e:
            self.logger.error(f"Error in RDKit minimization: {e}")
            raise

    def _molecules_from_smiles_input(self, smiles_input):
        """Create RDKit molecules from SMILES input which can be:
        - list[str] of SMILES
        - pandas DataFrame with a SMILES column (name contains 'smiles' case-insensitively or matches property 'smiles_column')
        Returns (molecules_list, names_list) where names_list are '1','2',... strings.
        """
        try:
            from rdkit import Chem
        except Exception as e:
            raise RuntimeError("RDKit is required to parse SMILES") from e

        smiles_list: list[str] = []
        try:
            # Case 1: direct list/tuple of strings
            if isinstance(smiles_input, (list, tuple)):
                if len(smiles_input) > 0 and isinstance(smiles_input[0], dict):
                    # List of dict rows (e.g., from Select Columns). Find SMILES key case-insensitively.
                    def _find_key(d: dict) -> str | None:
                        if not isinstance(d, dict):
                            return None
                        # Preferred explicit property
                        preferred = (self.get_property("smiles_column") or "smiles")
                        for k in d.keys():
                            if str(k).lower() == str(preferred).lower():
                                return k
                        # Fallback: any key containing 'smiles'
                        for k in d.keys():
                            if "smiles" in str(k).lower():
                                return k
                        # Last resort: single-value dict
                        if len(d) == 1:
                            return list(d.keys())[0]
                        return None
                    smiles_key = _find_key(smiles_input[0])
                    # If first row lacks the key, try to scan until found
                    if smiles_key is None:
                        for row in smiles_input:
                            smiles_key = _find_key(row)
                            if smiles_key is not None:
                                break
                    if smiles_key is None:
                        raise ValueError("Could not find a SMILES key in list of dictionaries")
                    for row in smiles_input:
                        if not isinstance(row, dict):
                            continue
                        val = row.get(smiles_key)
                        if val is None:
                            continue
                        s = str(val).strip()
                        if s:
                            smiles_list.append(s)
                else:
                    # Assume list of strings or convertible values
                    smiles_list = [str(s).strip() for s in smiles_input if s is not None and str(s).strip()]
            else:
                # Try pandas DataFrame-like
                try:
                    import pandas as pd  # type: ignore
                except Exception:
                    pd = None  # type: ignore
                if pd is not None and hasattr(smiles_input, "__class__") and smiles_input.__class__.__name__ in {"DataFrame", "Series"}:
                    if smiles_input.__class__.__name__ == "Series":
                        smiles_list = [str(x) for x in smiles_input.dropna().tolist()]
                    else:
                        # Prefer explicit column if set, else auto-detect by name containing 'smiles'
                        col = (self.get_property("smiles_column") or "smiles")
                        if col in smiles_input.columns:
                            smiles_list = [str(x) for x in smiles_input[col].dropna().tolist()]
                        else:
                            candidates = [c for c in smiles_input.columns if "smiles" in str(c).lower()]
                            if not candidates:
                                raise ValueError("No SMILES column found in DataFrame")
                            smiles_list = [str(x) for x in smiles_input[candidates[0]].dropna().tolist()]
                else:
                    raise ValueError("Unsupported SMILES input type; provide list[str] or DataFrame")
        except Exception as e:
            raise ValueError(f"Failed to interpret SMILES input: {e}")

        molecules = []
        names: list[str] = []
        for idx, smi in enumerate(smiles_list, start=1):
            try:
                m = Chem.MolFromSmiles(smi)
                if m is None:
                    continue
                # Set 1-based name from order
                try:
                    m.SetProp("_Name", str(idx))
                except Exception:
                    pass
                molecules.append(m)
                names.append(str(idx))
            except Exception:
                continue
        return molecules, names
    
    def _read_molecules_from_file(self, input_file: str):
        """Read molecules from file."""
        from rdkit import Chem
        
        file_path = Path(input_file)
        if file_path.suffix.lower() == '.sdf':
            supplier = Chem.SDMolSupplier(str(file_path))
            return [mol for mol in supplier if mol is not None]
        elif file_path.suffix.lower() == '.mol2':
            return [Chem.MolFromMol2File(str(file_path))]
        elif file_path.suffix.lower() == '.pdb':
            return [Chem.MolFromPDBFile(str(file_path))]
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")
    
    def _minimize_molecule(self, mol):
        """Minimize a single molecule."""
        from rdkit.Chem import AllChem
        from rdkit.Chem import rdForceFieldHelpers as FF
        
        # Generate 3D coordinates if needed
        if mol.GetNumConformers() == 0:
            AllChem.EmbedMolecule(mol, randomSeed=42)
        
        # Setup force field
        force_field = self.get_property("force_field")
        if force_field == "MMFF94":
            # Build MMFF properties once and bind to force field
            mmff_props = FF.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94")
            if mmff_props is None:
                # Fallback to UFF if MMFF properties cannot be created
                ff = AllChem.UFFGetMoleculeForceField(mol)
            else:
                ff = FF.MMFFGetMoleculeForceField(mol, mmff_props, confId=0)
        elif force_field == "UFF":
            ff = AllChem.UFFGetMoleculeForceField(mol)
        else:
            raise ValueError(f"Unsupported force field: {force_field}")
        
        if ff is None:
            raise ValueError("Could not create force field for molecule")
        
        # Minimize with periodic progress hints (iterations are internal; we approximate)
        max_iter = self.get_property("max_iterations")
        try:
            # RDKit doesn't stream per-iteration logs; emit coarse-grained progress by chunks
            chunks = max(1, min(10, int(max_iter // 50) or 1))
            done = 0
            while done < max_iter:
                step = min(chunks, max_iter - done)
                ff.Minimize(maxIts=step)
                done += step
                try:
                    pct = min(99, int(done / max(1, max_iter) * 100))
                    self.report_progress(pct, f"RDKit minimize: {done}/{max_iter}")
                except Exception:
                    pass
            convergence = 0
        except Exception:
            # Fallback single call
            convergence = ff.Minimize(maxIts=max_iter)
        
        # Get energy
        energy = ff.CalcEnergy()
        
        return energy
    
    def _optimize_conformers_and_select_best(self, mol):
        """Generate and optimize multiple conformers, return molecule with best conformer."""
        from rdkit import Chem
        from rdkit.Chem import AllChem
        from rdkit.Chem import rdForceFieldHelpers as FF
        
        num_conformers = self.get_property("num_conformers")
        
        # Generate conformers
        conf_ids = AllChem.EmbedMultipleConfs(mol, numConfs=num_conformers, randomSeed=42)
        
        if not conf_ids:
            # Fallback to single conformer
            AllChem.EmbedMolecule(mol, randomSeed=42)
            conf_ids = [0]
        
        # Optimize each conformer and track energies
        conformer_energies = []
        force_field = self.get_property("force_field")
        max_iter = self.get_property("max_iterations")
        mmff_props = None
        if force_field == "MMFF94":
            mmff_props = FF.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94")
        
        valid_conformers = []
        for conf_id in conf_ids:
            try:
                if force_field == "MMFF94":
                    if mmff_props is None:
                        # If properties could not be created, fallback to UFF
                        ff = AllChem.UFFGetMoleculeForceField(mol, confId=conf_id)
                    else:
                        ff = FF.MMFFGetMoleculeForceField(mol, mmff_props, confId=conf_id)
                else:  # UFF
                    ff = AllChem.UFFGetMoleculeForceField(mol, confId=conf_id)
                
                if ff:
                    ff.Minimize(maxIts=max_iter)
                    energy = ff.CalcEnergy()
                    conformer_energies.append((conf_id, energy))
                    valid_conformers.append(conf_id)
                
            except Exception as e:
                self.logger.warning(f"Error optimizing conformer {conf_id}: {e}")
                continue
        
        if not conformer_energies:
            # If no conformers could be optimized, return original with single conformer
            if mol.GetNumConformers() == 0:
                try:
                    AllChem.EmbedMolecule(mol, randomSeed=42)
                    energy = self._minimize_molecule(mol)
                    return mol, energy
                except Exception:
                    return mol, 0.0
            else:
                energy = self._minimize_molecule(mol)
                return mol, energy
        
        # Find the conformer with lowest energy
        best_conf_id, best_energy = min(conformer_energies, key=lambda x: x[1])
        
        # Create a new molecule with only the best conformer
        best_mol = Chem.Mol(mol)
        best_mol.RemoveAllConformers()
        best_mol.AddConformer(mol.GetConformer(best_conf_id), assignId=True)
        
        return best_mol, best_energy
    
    # removed: direct disk writes; use File Output
    
    # removed: direct disk writes; use File Output
    
    def validate(self) -> tuple[bool, str]:
        """Validate the node configuration."""
        input_file = self.get_property("input_file")
        
        if input_file and not Path(input_file).exists():
            return False, f"Input file not found: {input_file}"
        
        max_iter = self.get_property("max_iterations")
        if max_iter <= 0:
            return False, "Max iterations must be positive"
        
        return True, "Node configuration is valid"


class OpenBabelMinimizeNode(BaseNode):
    """Node for molecular minimization using OpenBabel."""
    
    def __init__(self):
        super().__init__("openbabel_minimize", "OpenBabel Minimize")
        self.logger = get_logger(__name__)
        
        # Molecule-based I/O - only output minimized molecules
        self.add_input_port("input_molecules", "molecules")
        self.add_output_port("molecules", "molecules")
        
        # Default properties (no file paths)
        self.set_property("force_field", "MMFF94")
        self.set_property("steps", 1000)
        self.set_property("convergence", 1e-6)
        self.set_property("steepest_descent", True)
        self.set_property("conjugate_gradient", True)
        # Preserve hydrogen state from input molecule
        self.set_property("add_hydrogens", False)
        
    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute OpenBabel minimization (molecule in/out)."""
        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem
            
            # Resolve input molecules
            mols = (inputs or {}).get("input_molecules")
            if not isinstance(mols, list) or len(mols) == 0:
                raise ValueError("input_molecules are required")
            
            out_mols = []
            tmp_dir = get_subdir("openbabel_minimize")
            exe = resolve_openbabel_executable("obminimize")
            exe_dir = Path(exe).parent if isinstance(exe, str) else None
            
            for idx, mol in enumerate(mols):
                if mol is None:
                    continue
                try:
                    # Preserve original hydrogen state unless explicitly requested
                    add_h = bool(self.get_property("add_hydrogens"))
                    if add_h and not any(atom.GetAtomicNum() == 1 for atom in mol.GetAtoms()):
                        m = Chem.AddHs(mol)
                    else:
                        m = Chem.Mol(mol)
                    
                    # Ensure molecule has a single 3D conformer
                    if m.GetNumConformers() == 0:
                        try:
                            AllChem.EmbedMolecule(m, randomSeed=42)
                        except Exception:
                            self.logger.warning(f"Could not generate 3D coordinates for molecule {idx}")
                            continue
                    elif m.GetNumConformers() > 1:
                        # Keep only the first conformer for minimization
                        c0 = m.GetConformer(0)
                        m_single = Chem.Mol(m)
                        m_single.RemoveAllConformers()
                        m_single.AddConformer(c0, assignId=True)
                        m = m_single
                    
                    # Use SDF format for better preservation of molecular data
                    in_path = tmp_dir / f"mol_{idx}.sdf"
                    out_path = tmp_dir / f"mol_{idx}_min.sdf"
                    
                    # Write molecule to SDF
                    writer = Chem.SDWriter(str(in_path))
                    writer.write(m)
                    writer.close()
                    
                    # Build OpenBabel minimize command
                    cmd = [
                        exe,
                        "-ff", str(self.get_property("force_field")),
                        "-n", str(self.get_property("steps")),
                        "-c", str(self.get_property("convergence")),
                        str(in_path),
                        "-O", str(out_path)
                    ]
                    if bool(self.get_property("steepest_descent")):
                        cmd.append("-sd")
                    if bool(self.get_property("conjugate_gradient")):
                        cmd.append("-cg")
                        
                    self.logger.info(f"Running OpenBabel minimize: {' '.join(map(str, cmd))}")
                    
                    # Run OpenBabel minimization
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        check=True,
                        cwd=str(exe_dir) if exe_dir else None,
                        timeout=300,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    )
                    
                    # Read back the minimized molecule from SDF
                    if out_path.exists():
                        supplier = Chem.SDMolSupplier(str(out_path))
                        minimized_mols = [mol for mol in supplier if mol is not None]
                        
                        if minimized_mols:
                            m_out = minimized_mols[0]  # Take the first molecule
                            # Verify that the molecule structure is intact
                            if m_out.GetNumAtoms() == m.GetNumAtoms():
                                out_mols.append(m_out)
                            else:
                                self.logger.warning(f"Atom count mismatch for molecule {idx}, using original")
                                out_mols.append(m)
                        else:
                            self.logger.warning(f"No valid molecules in OpenBabel output for molecule {idx}")
                            out_mols.append(m)
                    else:
                        self.logger.warning(f"OpenBabel output file not found for molecule {idx}")
                        out_mols.append(m)
                        
                except subprocess.CalledProcessError as e:
                    self.logger.error(f"OpenBabel minimization failed for molecule {idx}: {(e.stderr or e.stdout or '').strip()}")
                    # Fallback to original molecule
                    try:
                        out_mols.append(m)
                    except Exception:
                        pass
                    continue
                except Exception as e:
                    self.logger.error(f"Error minimizing molecule {idx} with OpenBabel: {e}")
                    continue
            
            self.logger.info(f"OpenBabel minimization completed for {len(out_mols)} molecule(s)")
            return {"molecules": out_mols, "num_molecules": len(out_mols)}
        except Exception as e:
            self.logger.error(f"Error in OpenBabel minimization: {e}")
            raise
    
    def validate(self) -> tuple[bool, str]:
        """Validate the node configuration (molecule I/O)."""
        steps = self.get_property("steps")
        if steps <= 0:
            return False, "Number of steps must be positive"
        return True, "Node configuration is valid"


class ConformerGenNode(BaseNode):
    """Node for generating molecular conformers."""
    
    def __init__(self):
        super().__init__("conformer_gen", "Conformer Generation")
        self.logger = get_logger(__name__)
        
        # Add ports
        self.add_input_port("input_molecules", "molecules")
        self.add_output_port("conformer", "molecules")  # Best conformers only
        self.add_output_port("energy", "data")  # Energy DataFrame
        
        # Default properties
        self.set_property("input_file", "")
        self.set_property("output_file", "")
        self.set_property("num_conformers", 50)
        self.set_property("energy_window", 10.0)  # kcal/mol
        self.set_property("rmsd_threshold", 1.0)  # Angstroms
        self.set_property("optimize_conformers", True)
        self.set_property("force_field", "MMFF94")
        self.set_property("max_iterations", 1000)
        
    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute conformer generation."""
        try:
            # Import RDKit and pandas
            from rdkit import Chem
            from rdkit.Chem import AllChem, TorsionFingerprints
            import pandas as pd
            
            # Get input
            input_molecules = inputs.get("input_molecules") if inputs else None
            input_file = self.get_property("input_file")
            
            if input_molecules:
                molecules = input_molecules
            elif input_file and Path(input_file).exists():
                molecules = self._read_molecules_from_file(input_file)
            else:
                raise ValueError("No valid input molecules or file provided")
            
            all_conformers = []  # Will store all generated conformers for energy tracking
            all_energies = []
            all_mol_names = []
            all_conformer_indices = []
            best_conformers = []  # Will store only the best conformers to output
            
            for i, mol in enumerate(molecules):
                if mol is None:
                    continue
                
                try:
                    # Generate conformers for this molecule
                    conformers, energies = self._generate_conformers(mol)
                    
                    if conformers:
                        # Track all conformers for energy DataFrame
                        all_conformers.extend(conformers)
                        all_energies.extend(energies)
                        
                        # Track molecule names and conformer indices
                        mol_name = mol.GetProp("_Name") if mol.HasProp("_Name") else f"Molecule_{i+1}"
                        all_mol_names.extend([mol_name] * len(conformers))
                        all_conformer_indices.extend(list(range(1, len(conformers) + 1)))
                        
                        # Find best conformer (lowest energy) for this molecule
                        if self.get_property("optimize_conformers") and energies:
                            best_idx = energies.index(min(energies))
                            best_conformers.append(conformers[best_idx])
                        else:
                            # If not optimized, take first conformer as "best"
                            best_conformers.append(conformers[0])
                        
                        self.logger.info(f"Generated {len(conformers)} conformers for molecule {i}, best energy: {min(energies) if energies else 'N/A'}")
                    
                except Exception as e:
                    self.logger.error(f"Error generating conformers for molecule {i}: {e}")
                    continue
            
            # Create energy DataFrame similar to RDKit minimization
            if all_conformers:
                force_field = str(self.get_property("force_field"))
                optimize_conformers = bool(self.get_property("optimize_conformers"))
                
                energy_df = pd.DataFrame({
                    "Conformer Index": list(range(1, len(all_conformers) + 1)),
                    "Molecule Name": all_mol_names,
                    "Conformer Number": all_conformer_indices,
                    "Energy (kcal/mol)": all_energies,
                    "Force Field": [force_field] * len(all_energies),
                    "Optimized": [optimize_conformers] * len(all_energies),
                })
            else:
                energy_df = pd.DataFrame()
            
            # In-memory only; persistence via File Output node
            self.logger.info(f"Conformer generation completed. Generated {len(all_conformers)} conformers total, returning {len(best_conformers)} best conformers")
            return {
                "conformer": best_conformers,  # Best conformers only
                "energy": energy_df,  # Energy DataFrame (includes all conformers info)
                "num_conformers": len(all_conformers),
                "num_best_conformers": len(best_conformers)
            }
            
        except ImportError:
            error_msg = "RDKit is not installed. Please install RDKit to use this node."
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            self.logger.error(f"Error in conformer generation: {e}")
            raise
    
    def _read_molecules_from_file(self, input_file: str):
        """Read molecules from file."""
        from rdkit import Chem
        
        file_path = Path(input_file)
        if file_path.suffix.lower() == '.sdf':
            supplier = Chem.SDMolSupplier(str(file_path))
            return [mol for mol in supplier if mol is not None]
        elif file_path.suffix.lower() == '.mol2':
            return [Chem.MolFromMol2File(str(file_path))]
        elif file_path.suffix.lower() == '.pdb':
            return [Chem.MolFromPDBFile(str(file_path))]
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")
    
    def _generate_conformers(self, mol):
        """Generate conformers for a molecule."""
        from rdkit import Chem
        from rdkit.Chem import AllChem
        
        # Add hydrogens
        mol_h = Chem.AddHs(mol)
        
        # Generate conformers
        num_conformers = self.get_property("num_conformers")
        conf_ids = AllChem.EmbedMultipleConfs(
            mol_h,
            numConfs=num_conformers,
            randomSeed=42,
            pruneRmsThresh=self.get_property("rmsd_threshold")
        )
        
        if not conf_ids:
            # Fallback to single conformer
            AllChem.EmbedMolecule(mol_h, randomSeed=42)
            conf_ids = [0]
        
        conformers = []
        energies = []
        
        # Optimize conformers if requested
        if self.get_property("optimize_conformers"):
            for conf_id in conf_ids:
                try:
                    # Create a copy of the molecule with this conformer
                    conf_mol = Chem.Mol(mol_h)
                    conf_mol.RemoveAllConformers()
                    conf_mol.AddConformer(mol_h.GetConformer(conf_id), assignId=True)
                    
                    # Optimize
                    energy = self._minimize_conformer(conf_mol)
                    
                    # Filter by energy window
                    if not energies or (energy - min(energies)) <= self.get_property("energy_window"):
                        conformers.append(conf_mol)
                        energies.append(energy)
                
                except Exception as e:
                    self.logger.warning(f"Error optimizing conformer {conf_id}: {e}")
                    continue
        else:
            # Just return all conformers without optimization
            for conf_id in conf_ids:
                conf_mol = Chem.Mol(mol_h)
                conf_mol.RemoveAllConformers()
                conf_mol.AddConformer(mol_h.GetConformer(conf_id), assignId=True)
                conformers.append(conf_mol)
                energies.append(0.0)  # No energy if not optimized
        
        return conformers, energies
    
    def _minimize_conformer(self, mol):
        """Minimize a conformer."""
        from rdkit.Chem import AllChem
        from rdkit.Chem import rdForceFieldHelpers as FF
        
        force_field = self.get_property("force_field")
        ff = None
        
        if force_field == "MMFF94":
            # Try to get MMFF properties first
            mmff_props = FF.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94")
            if mmff_props is not None:
                ff = FF.MMFFGetMoleculeForceField(mol, mmff_props)
            else:
                # Fallback to UFF if MMFF properties can't be generated
                ff = AllChem.UFFGetMoleculeForceField(mol)
        else:  # UFF
            ff = AllChem.UFFGetMoleculeForceField(mol)
        
        if ff is None:
            raise ValueError("Could not create force field for molecule")
        
        max_iter = self.get_property("max_iterations")
        ff.Minimize(maxIts=max_iter)
        energy = ff.CalcEnergy()
        
        return energy
    
    # removed: direct disk writes; use File Output
    
    # removed: direct disk writes; use File Output
    
    def validate(self) -> tuple[bool, str]:
        """Validate the node configuration."""
        input_file = self.get_property("input_file")
        
        if input_file and not Path(input_file).exists():
            return False, f"Input file not found: {input_file}"
        
        num_conformers = self.get_property("num_conformers")
        if num_conformers <= 0:
            return False, "Number of conformers must be positive"
        
        energy_window = self.get_property("energy_window")
        if energy_window < 0:
            return False, "Energy window must be non-negative"
        
        return True, "Node configuration is valid"
