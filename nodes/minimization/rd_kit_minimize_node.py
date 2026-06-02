"""RDKitMinimizeNode implementation."""

from .common import *  # noqa: F401,F403

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
