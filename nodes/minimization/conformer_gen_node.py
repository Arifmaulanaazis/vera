"""ConformerGenNode implementation."""

from .common import *  # noqa: F401,F403

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
