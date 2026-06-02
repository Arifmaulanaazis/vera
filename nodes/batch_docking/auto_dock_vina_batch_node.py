"""AutoDockVinaBatchNode implementation."""

from .common import *  # noqa: F401,F403

class AutoDockVinaBatchNode(BaseNode):
    """Batch docking from SMILES with automatic minimization and preparation.
    
    Inputs:
      - receptor (molecule): receptor molecule
      - ligands_smiles (data): DataFrame/list with SMILES strings
      - grid_params (data): grid box parameters dict
      - replications (string, optional): number of docking replications per ligand
    
    Outputs:
      - docking_results (data): DataFrame preserving all input columns + docking columns
      - docked_molecules (molecules): all docked molecules from all ligands/replications
      - folder_path (string): path to temp folder with all docking results
      - docking_log (string): concatenated docking logs
      - best_pose (molecule): best-scoring docked molecule
    """
    
    def __init__(self):
        super().__init__("autodock_vina_batch", "AutoDock Vina Batch")
        self.logger = get_logger(__name__)
        
        # Input ports
        self.add_input_port("receptor", "molecule")
        self.add_input_port("ligands_smiles", "data")
        self.add_input_port("grid_params", "data")
        self.add_input_port("replications", "string")  # optional
        
        # Output ports
        self.add_output_port("docking_results", "data")
        self.add_output_port("docked_molecules", "molecules")  # All docked molecules
        self.add_output_port("best_pose", "molecule")  # Best-scoring docked molecule
        self.add_output_port("folder_path", "string")
        self.add_output_port("docking_log", "string")

        
        # Minimization properties (from RDKit Minimize)
        self.set_property("force_field", "MMFF94")  # MMFF94 | UFF
        self.set_property("max_iterations", 1000)
        self.set_property("convergence_threshold", 1e-6)
        self.set_property("optimize_conformers", False)
        self.set_property("num_conformers", 10)
        
        # Ligand preparation properties (from Ligand Preparation)
        self.set_property("remove_salts", True)
        self.set_property("neutralize", True)
        self.set_property("add_hydrogens_mode", "all")  # none | polar_only | all
        self.set_property("embed_3d", True)
        self.set_property("minimize", True)
        self.set_property("compute_charges", "gasteiger")  # none | gasteiger
        
        # Docking properties (from AutoDock Vina)
        self.set_property("exhaustiveness", 8)
        self.set_property("num_modes", 9)
        self.set_property("energy_range", 3.0)
        self.set_property("vina_version", "1.2.5")
        
        # Grid box properties (used if grid_params not connected)
        self.set_property("center_x", 0.0)
        self.set_property("center_y", 0.0)
        self.set_property("center_z", 0.0)
        self.set_property("size_x", 20.0)
        self.set_property("size_y", 20.0)
        self.set_property("size_z", 20.0)
        
        # Merge molecules property
        self.set_property("merge_molecules", True)  # Auto-merge best poses with receptor
    
    def _detect_smiles_column(self, data):
        """Detect and extract SMILES column from various input formats.
        
        Returns: (smiles_list, original_rows_data)
        """
        try:
            from rdkit import Chem
        except Exception as e:
            raise RuntimeError("RDKit is required for SMILES parsing") from e
        
        import pandas as pd
        
        smiles_list = []
        original_rows = []
        
        # Convert to DataFrame for uniform handling
        df = None
        if isinstance(data, pd.DataFrame):
            df = data.copy()
        elif isinstance(data, list):
            if len(data) > 0 and isinstance(data[0], dict):
                df = pd.DataFrame(data)
            elif len(data) > 0 and isinstance(data[0], str):
                # List of SMILES strings
                df = pd.DataFrame({"smiles": data})
            else:
                raise ValueError("Unsupported list format for ligands_smiles")
        else:
            raise ValueError("ligands_smiles must be DataFrame or list")
        
        if df is None or df.empty:
            raise ValueError("Empty data provided for ligands_smiles")
        
        # Find SMILES column
        smiles_col = None
        for col in df.columns:
            if "smiles" in str(col).lower():
                smiles_col = col
                break
        
        if smiles_col is None:
            raise ValueError("No SMILES column found in input data. Column name must contain 'smiles'")
        
        # Validate and collect SMILES
        for idx, row in df.iterrows():
            smi = str(row[smiles_col]).strip()
            if not smi or smi.lower() in ('nan', 'none', ''):
                self.logger.warning(f"Row {idx}: Empty or invalid SMILES, skipping")
                continue
            
            # Validate SMILES
            try:
                mol = Chem.MolFromSmiles(smi)
                if mol is None:
                    self.logger.warning(f"Row {idx}: Invalid SMILES '{smi}', skipping")
                    continue
            except Exception as e:
                self.logger.warning(f"Row {idx}: SMILES validation failed: {e}")
                continue
            
            # Store valid SMILES and original row data
            smiles_list.append(smi)
            original_rows.append(row.to_dict())
        
        if len(smiles_list) == 0:
            raise ValueError("No valid SMILES found in input data")
        
        self.logger.info(f"Detected {len(smiles_list)} valid SMILES from column '{smiles_col}'")
        return smiles_list, original_rows
    
    def _minimize_molecule(self, mol):
        """Minimize a molecule using configured force field settings.
        
        Returns: (minimized_mol, energy)
        """
        from rdkit import Chem
        from rdkit.Chem import AllChem
        from rdkit.Chem import rdForceFieldHelpers as FF
        
        force_field = self.get_property("force_field")
        max_iter = int(self.get_property("max_iterations"))
        optimize_conformers = bool(self.get_property("optimize_conformers"))
        num_conformers = int(self.get_property("num_conformers"))
        
        # Add hydrogens if not present
        m = Chem.AddHs(mol)
        
        # Generate 3D coordinates if needed
        if m.GetNumConformers() == 0:
            AllChem.EmbedMolecule(m, randomSeed=42)
        
        # Conformer optimization
        if optimize_conformers and num_conformers > 1:
            conf_ids = AllChem.EmbedMultipleConfs(m, numConfs=num_conformers, randomSeed=42)
            if not conf_ids:
                AllChem.EmbedMolecule(m, randomSeed=42)
                conf_ids = [0]
            
            conformer_energies = []
            for conf_id in conf_ids:
                if force_field == "MMFF94":
                    mmff_props = FF.MMFFGetMoleculeProperties(m, mmffVariant="MMFF94")
                    if mmff_props is None:
                        ff = AllChem.UFFGetMoleculeForceField(m, confId=conf_id)
                    else:
                        ff = FF.MMFFGetMoleculeForceField(m, mmff_props, confId=conf_id)
                else:
                    ff = AllChem.UFFGetMoleculeForceField(m, confId=conf_id)
                
                if ff is not None:
                    ff.Minimize(maxIts=max_iter)
                    energy = ff.CalcEnergy()
                    conformer_energies.append((conf_id, energy))
            
            # Select best conformer
            if conformer_energies:
                best_conf_id, best_energy = min(conformer_energies, key=lambda x: x[1])
                best_mol = Chem.Mol(m)
                best_mol.RemoveAllConformers()
                best_mol.AddConformer(m.GetConformer(best_conf_id), assignId=True)
                return best_mol, best_energy
        
        # Single conformer minimization
        if force_field == "MMFF94":
            mmff_props = FF.MMFFGetMoleculeProperties(m, mmffVariant="MMFF94")
            if mmff_props is None:
                ff = AllChem.UFFGetMoleculeForceField(m)
            else:
                ff = FF.MMFFGetMoleculeForceField(m, mmff_props, confId=0)
        else:
            ff = AllChem.UFFGetMoleculeForceField(m)
        
        if ff is not None:
            ff.Minimize(maxIts=max_iter)
            energy = ff.CalcEnergy()
        else:
            energy = 0.0
        
        return m, energy
    
    def _prepare_ligand(self, mol):
        """Prepare ligand molecule for docking.
        
        Returns: prepared_mol
        """
        from rdkit import Chem
        from rdkit.Chem import AllChem
        try:
            from rdkit.Chem import rdMolStandardize
        except Exception:
            rdMolStandardize = None
        
        m = Chem.Mol(mol)
        
        #1) Remove salts
        remove_salts = bool(self.get_property("remove_salts"))
        if remove_salts and rdMolStandardize is not None:
            try:
                chooser = rdMolStandardize.LargestFragmentChooser()
                m = chooser.choose(m)
            except Exception:
                pass
        
        # 2) Neutralize
        neutralize = bool(self.get_property("neutralize"))
        if neutralize and rdMolStandardize is not None:
            try:
                uncharger = rdMolStandardize.Uncharger()
                m = uncharger.uncharge(m)
            except Exception:
                pass
        
        # 3) Add hydrogens
        add_h_mode = str(self.get_property("add_hydrogens_mode") or "all").strip().lower()
        if add_h_mode == "all":
            m = Chem.AddHs(m, addCoords=True)
        elif add_h_mode == "polar_only":
            try:
                m = Chem.AddHs(m, addCoords=True, onlyOnElements=[7, 8, 15, 16])
            except Exception:
                # Fallback
                full = Chem.AddHs(m, addCoords=True)
                rw = Chem.RWMol(full)
                to_del = []
                for a in full.GetAtoms():
                    if a.GetAtomicNum() == 1:
                        nbrs = a.GetNeighbors()
                        if nbrs and nbrs[0].GetAtomicNum() == 6:
                            to_del.append(a.GetIdx())
                for ai in sorted(to_del, reverse=True):
                    try:
                        rw.RemoveAtom(int(ai))
                    except Exception:
                        pass
                m = rw.GetMol()
        
        # 4) Embed 3D
        embed_3d = bool(self.get_property("embed_3d"))
        if embed_3d:
            try:
                params = AllChem.ETKDGv3()
            except Exception:
                try:
                    params = AllChem.ETKDGv2()
                except Exception:
                    params = None
            
            if params is not None:
                AllChem.EmbedMolecule(m, params)
            else:
                AllChem.EmbedMolecule(m, randomSeed=42)
        
        # 5) Minimize
        do_minimize = bool(self.get_property("minimize"))
        if do_minimize:
            force_field = str(self.get_property("force_field") or "MMFF94").strip().upper()
            max_iter = int(self.get_property("max_iterations") or 200)
            
            if force_field == "MMFF94":
                from rdkit.Chem import rdForceFieldHelpers as FF
                mmff_props = FF.MMFFGetMoleculeProperties(m, mmffVariant="MMFF94")
                if mmff_props is None:
                    ff = AllChem.UFFGetMoleculeForceField(m)
                else:
                    ff = FF.MMFFGetMoleculeForceField(m, mmff_props, confId=0)
            else:
                ff = AllChem.UFFGetMoleculeForceField(m)
            
            if ff is not None:
                ff.Minimize(maxIts=max_iter)
        
        # 6) Compute charges
        charge_mode = str(self.get_property("compute_charges") or "gasteiger").strip().lower()
        if charge_mode == "gasteiger":
            try:
                AllChem.ComputeGasteigerCharges(m)
            except Exception:
                self.logger.warning("Gasteiger charge computation failed")
        
        # Final sanitize
        try:
            Chem.SanitizeMol(m, catchErrors=True)
        except Exception:
            pass
        
        return m
    
    def _stage_to_pdbqt(self, mol, name: str):
        """Convert RDKit molecule to PDBQT file.
        
        Returns: (pdb_path, pdbqt_path)
        """
        from rdkit import Chem
        from rdkit.Chem import AllChem
        
        tmp_dir = get_subdir("docking_batch_stage")
        pdb_path = tmp_dir / f"{name}.pdb"
        pdbqt_path = tmp_dir / f"{name}.pdbqt"
        
        # Ensure single conformer
        m = Chem.AddHs(mol)
        if m.GetNumConformers() == 0:
            AllChem.EmbedMolecule(m)
        elif m.GetNumConformers() > 1:
            c0 = m.GetConformer(0)
            m_single = Chem.Mol(m)
            m_single.RemoveAllConformers()
            m_single.AddConformer(c0, assignId=True)
            m = m_single
        
        # Write PDB
        Chem.MolToPDBFile(m, str(pdb_path))
        
        # Convert to PDBQT
        obabel = resolve_openbabel_executable("obabel")
        cmd = [obabel, str(pdb_path), "-O", str(pdbqt_path), "-h"]
        
        try:
            ob_dir = Path(obabel).parent if isinstance(obabel, str) else None
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                check=True, 
                cwd=str(ob_dir) if ob_dir else None,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
        except subprocess.CalledProcessError as e:
            raise ValueError(f"OpenBabel conversion failed: {(e.stderr or e.stdout or '').strip()}")
        
        if not pdbqt_path.exists() or pdbqt_path.stat().st_size == 0:
            raise ValueError("OpenBabel produced empty PDBQT output")
        
        return pdb_path, pdbqt_path
    
    def _parse_vina_output(self, log_file: Path):
        """Parse AutoDock Vina output log.
        
        Returns: list of dicts with keys: mode, affinity, rmsd_lb, rmsd_ub
        """
        poses = []
        
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
            
            parsing_results = False
            for line in lines:
                if "-----+------------+----------+----------" in line:
                    parsing_results = True
                    continue
                
                if parsing_results and line.strip():
                    parts = line.split()
                    if len(parts) >= 4 and parts[0].isdigit():
                        pose_data = {
                            "mode": int(parts[0]),
                            "affinity": float(parts[1]),
                            "rmsd_lb": float(parts[2]),
                            "rmsd_ub": float(parts[3])
                        }
                        poses.append(pose_data)
        except Exception as e:
            self.logger.warning(f"Could not parse Vina output: {e}")
        
        return poses
    
    def _prepare_clean_receptor(self, receptor_mol):
        """Prepare receptor without hydrogens and charges for merging/visualization.
        
        Returns: cleaned RDKit molecule
        """
        from rdkit import Chem
        from rdkit.Chem import AllChem
        
        try:
            # Step 1: Manually remove ALL hydrogen atoms (atomic number = 1)
            # This is more reliable than RemoveHs() which can leave orphan hydrogens
            rw_mol = Chem.RWMol(receptor_mol)
            
            # Collect indices of all hydrogen atoms
            h_indices = []
            for atom in rw_mol.GetAtoms():
                if atom.GetAtomicNum() == 1:  # Hydrogen
                    h_indices.append(atom.GetIdx())
            
            # Remove hydrogens in reverse order to avoid index shifting
            for idx in sorted(h_indices, reverse=True):
                rw_mol.RemoveAtom(idx)
            
            clean_rec = rw_mol.GetMol()
            
            # Step 2: Reset all charges to zero  
            for atom in clean_rec.GetAtoms():
                # Reset formal charge
                atom.SetFormalCharge(0)
                # Clear partial charges if present
                if atom.HasProp("_GasteigerCharge"):
                    atom.ClearProp("_GasteigerCharge")
                if atom.HasProp("_TriposPartialCharge"):
                    atom.ClearProp("_TriposPartialCharge")
            
            # Step 3: Sanitize
            try:
                Chem.SanitizeMol(clean_rec)
            except Exception:
                pass
            
            self.logger.info(f"Clean receptor: {clean_rec.GetNumAtoms()} heavy atoms (removed {len(h_indices)} H atoms, cleared charges)")
            return clean_rec
            
        except Exception as e:
            self.logger.error(f"Failed to prepare clean receptor: {e}")
            # Fallback: try basic RemoveHs
            try:
                return Chem.RemoveHs(receptor_mol)
            except Exception:
                return Chem.Mol(receptor_mol)
    
    def _merge_molecules(self, receptor_mol, ligand_mol):
        """Merge receptor and ligand into a single complex.
        
        Returns: merged RDKit molecule
        """
        from rdkit import Chem
        from rdkit.Chem import AllChem
        
        if receptor_mol is None or ligand_mol is None:
            return None
        
        try:
            # Combine molecules
            combined = Chem.CombineMols(receptor_mol, ligand_mol)
            
            # Preserve conformers
            if combined.GetNumConformers() == 0:
                # Build conformer from both molecules
                total_atoms = combined.GetNumAtoms()
                conf = Chem.Conformer(total_atoms)
                
                rec_atoms = receptor_mol.GetNumAtoms()
                lig_atoms = ligand_mol.GetNumAtoms()
                
                # Copy receptor coordinates
                if receptor_mol.GetNumConformers() > 0:
                    rec_conf = receptor_mol.GetConformer(0)
                    for i in range(rec_atoms):
                        pos = rec_conf.GetAtomPosition(i)
                        conf.SetAtomPosition(i, pos)
                
                # Copy ligand coordinates
                if ligand_mol.GetNumConformers() > 0:
                    lig_conf = ligand_mol.GetConformer(0)
                    for i in range(lig_atoms):
                        pos = lig_conf.GetAtomPosition(i)
                        conf.SetAtomPosition(rec_atoms + i, pos)
                
                # Add conformer to combined molecule
                rwm = Chem.RWMol(combined)
                try:
                    rwm.RemoveAllConformers()
                except Exception:
                    pass
                rwm.AddConformer(conf, assignId=True)
                combined = rwm.GetMol()
            
            return combined
        except Exception as e:
            self.logger.warning(f"Failed to merge molecules: {e}")
            return None
    
    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute batch docking with SMILES input."""
        try:
            # Get inputs
            receptor_input = (inputs or {}).get("receptor")
            ligands_smiles = (inputs or {}).get("ligands_smiles")
            grid_params = (inputs or {}).get("grid_params") or {}
            replications_str = (inputs or {}).get("replications") or "1"
            
            # Validate receptor
            if not receptor_input or not isinstance(receptor_input, list) or len(receptor_input) == 0:
                raise ValueError("receptor input is required (single molecule)")
            receptor_mol = receptor_input[0]
            
            # Parse replications with validation
            reps_input = (inputs or {}).get("replications", "1")
            try:
                reps = int(reps_input) if reps_input else 1
                if reps < 1:
                    self.logger.warning(f"Invalid replications value '{reps_input}': must be >= 1. Using default: 1")
                    reps = 1
                elif reps > 100:
                    self.logger.warning(f"Replications value '{reps}' is very high. Consider using <= 100 for reasonable runtime.")
            except (ValueError, TypeError) as e:
                self.logger.error(f"Invalid replications input '{reps_input}': not a valid number. Using default: 1")
                reps = 1
            
            self.logger.info(f"Batch docking with {reps} replication(s)")
            
            # Detect and extract SMILES
            smiles_list, original_rows = self._detect_smiles_column(ligands_smiles)
            total_ligands = len(smiles_list)
            
            self.logger.info(f"Processing {total_ligands} ligands with {reps} replication(s) each")
            
            # Get grid parameters
            cx = float(grid_params.get("center_x", self.get_property("center_x")))
            cy = float(grid_params.get("center_y", self.get_property("center_y")))
            cz = float(grid_params.get("center_z", self.get_property("center_z")))
            sx = float(grid_params.get("size_x", self.get_property("size_x")))
            sy = float(grid_params.get("size_y", self.get_property("size_y")))
            sz = float(grid_params.get("size_z", self.get_property("size_z")))
            
            # Prepare receptor PDBQT ONCE (same as AutoDockVinaNode)
            from rdkit import Chem
            from rdkit.Chem import AllChem
            
            try:
                self.report_progress(1, "Preparing receptor PDBQT...")
            except Exception:
                pass
            
            # Stage receptor to PDBQT (same method as AutoDockVinaNode)
            def _stage_receptor_pdbqt(mol, name: str) -> Path:
                """Convert receptor molecule to PDBQT."""
                tmp_dir = get_subdir("docking_batch_stage")
                pdb_path = tmp_dir / f"{name}.pdb"
                pdbqt_path = tmp_dir / f"{name}.pdbqt"
                
                # Ensure single conformer
                m = Chem.AddHs(mol)
                try:
                    if m.GetNumConformers() == 0:
                        AllChem.EmbedMolecule(m)
                    elif m.GetNumConformers() > 1:
                        c0 = m.GetConformer(0)
                        m_single = Chem.Mol(m)
                        m_single.RemoveAllConformers()
                        m_single.AddConformer(c0, assignId=True)
                        m = m_single
                except Exception:
                    pass
                
                # Write PDB
                Chem.MolToPDBFile(m, str(pdb_path))
                
                # Convert to PDBQT with -xr flag for rigid receptor
                obabel = resolve_openbabel_executable("obabel")
                cmd = [obabel, str(pdb_path), "-O", str(pdbqt_path), "-xr"]
                
                try:
                    ob_dir = Path(obabel).parent if isinstance(obabel, str) else None
                    subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        check=True,
                        cwd=str(ob_dir) if ob_dir else None,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    )
                except subprocess.CalledProcessError as e:
                    raise ValueError(f"Receptor PDBQT conversion failed: {(e.stderr or e.stdout or '').strip()}")
                
                if not pdbqt_path.exists() or pdbqt_path.stat().st_size == 0:
                    raise ValueError("Receptor PDBQT conversion produced empty output")
                
                # Sanitize receptor PDBQT (remove torsion tags)
                try:
                    with open(pdbqt_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    banned = ("ROOT", "ENDROOT", "BRANCH", "ENDBRANCH", "TORSDOF")
                    if any(line.startswith(banned) for line in lines):
                        sanitized = pdbqt_path.with_name(pdbqt_path.stem + "_rigid.pdbqt")
                        with open(sanitized, "w", encoding="utf-8") as w:
                            for line in lines:
                                if not line.startswith(banned):
                                    w.write(line)
                        return sanitized
                except Exception:
                    pass
                
                return pdbqt_path
            
            rec_pdbqt = _stage_receptor_pdbqt(receptor_mol, "receptor")
            
            # Prepare clean receptor for merging (if enabled)
            clean_receptor = None
            merge_enabled = bool(self.get_property("merge_molecules"))
            if merge_enabled:
                try:
                    self.report_progress(2, "Preparing clean receptor for merging...")
                except Exception:
                    pass
                clean_receptor = self._prepare_clean_receptor(receptor_mol)
                self.logger.info("Clean receptor prepared for merging (no H, no charges)")
            
            # Create output directory
            output_parent_dir = get_subdir("batch_docking_results")
            
            # Create merged complexes folder if merging is enabled
            merged_dir = None
            if merge_enabled:
                merged_dir = output_parent_dir / "merged_complexes"
                merged_dir.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"Merged complexes will be saved to: {merged_dir}")
            
            all_results_rows = []
            all_logs = []
            all_docked_molecules = []  # Collect ALL docked molecules
            best_affinity = float('inf')
            best_pose_mol = None
            
            from nodes.io_nodes import _read_pdbqt
            vina_exe = resolve_vina_executable(self.get_property("vina_version") or None)
            
            # Process each ligand
            for lig_idx, (smiles, orig_row) in enumerate(zip(smiles_list, original_rows), start=1):
                # Generate sanitized filename
                ligand_file_base = f"ligand_{lig_idx}"
                ligand_file_name = f"{ligand_file_base}.pdbqt"
                
                try:
                    # Progress: Ligand X of Y - Parsing SMILES
                    base_progress = int((lig_idx - 1) / total_ligands * 100)
                    self.report_progress(base_progress, f"Ligand {lig_idx}/{total_ligands}: Parsing SMILES")
                except Exception:
                    pass
                
                # Parse SMILES
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    self.logger.warning(f"Ligand {lig_idx}: Failed to parse SMILES, skipping")
                    continue
                
                # Minimize ONCE per ligand
                try:
                    self.report_progress(base_progress + 1, f"Ligand {lig_idx}/{total_ligands}: Minimizing")
                except Exception:
                    pass
                
                try:
                    mol, energy = self._minimize_molecule(mol)
                    self.logger.info(f"Ligand {lig_idx}: Minimized (energy={energy:.2f})")
                except Exception as e:
                    self.logger.warning(f"Ligand {lig_idx}: Minimization failed: {e}")
                
                # Prepare ONCE per ligand
                try:
                    self.report_progress(base_progress + 2, f"Ligand {lig_idx}/{total_ligands}: Preparing")
                except Exception:
                    pass
                
                try:
                    mol = self._prepare_ligand(mol)
                    self.logger.info(f"Ligand {lig_idx}: Prepared")
                except Exception as e:
                    self.logger.warning(f"Ligand {lig_idx}: Preparation failed: {e}")
                    continue
                
                # Convert to PDBQT ONCE per ligand
                try:
                    self.report_progress(base_progress + 3, f"Ligand {lig_idx}/{total_ligands}: Converting to PDBQT")
                except Exception:
                    pass
                
                try:
                    lig_pdb, lig_pdbqt = self._stage_to_pdbqt(mol, ligand_file_base)
                    self.logger.info(f"Ligand {lig_idx}: PDBQT created ({lig_pdbqt.name})")
                except Exception as e:
                    self.logger.error(f"Ligand {lig_idx}: PDBQT conversion failed: {e}")
                    continue
                
                # NOW perform docking replications using THE SAME PDBQT file
                for rep_num in range(1, reps + 1):
                    try:
                        self.report_progress(
                            base_progress + 4, 
                            f"Ligand {lig_idx}/{total_ligands}: Docking rep {rep_num}/{reps}"
                        )
                    except Exception:
                        pass
                    
                    rep_dir = output_parent_dir / f"{ligand_file_base}_rep_{rep_num}"
                    rep_dir.mkdir(parents=True, exist_ok=True)
                    
                    output_file = rep_dir / f"docking_result.pdbqt"
                    log_file = rep_dir / "docking.log"
                    
                    # Build Vina command
                    cmd = [
                        vina_exe,
                        "--receptor", str(rec_pdbqt),
                        "--ligand", str(lig_pdbqt),  # REUSE same PDBQT!
                        "--out", str(output_file),
                        "--center_x", str(cx),
                        "--center_y", str(cy),
                        "--center_z", str(cz),
                        "--size_x", str(sx),
                        "--size_y", str(sy),
                        "--size_z", str(sz),
                        "--exhaustiveness", str(self.get_property("exhaustiveness")),
                        "--num_modes", str(self.get_property("num_modes")),
                        "--energy_range", str(self.get_property("energy_range"))
                    ]
                    
                    self.logger.info(f"Running Vina: ligand {lig_idx} rep {rep_num}/{reps}")
                    
                    # Run Vina
                    log_lines = []
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    )
                    
                    try:
                        self.register_subprocess(proc)
                    except Exception:
                        pass
                    
                    while True:
                        line = proc.stdout.readline() if proc.stdout else ""
                        if not line:
                            if proc.poll() is not None:
                                break
                            continue
                        log_lines.append(line)
                    
                    ret = proc.wait()
                    try:
                        self.unregister_subprocess(proc)
                    except Exception:
                        pass
                    
                    if ret != 0:
                        tail = "".join(log_lines[-50:])
                        self.logger.error(f"Vina failed for ligand {lig_idx} rep {rep_num}: {tail}")
                        continue
                    
                    # Save log
                    try:
                        with open(log_file, "w", encoding="utf-8") as lf:
                            lf.write("".join(log_lines))
                        all_logs.append("".join(log_lines))
                    except Exception:
                        pass
                    
                    # Parse results
                    poses = self._parse_vina_output(log_file)
                    
                    # Read docked molecules for best pose tracking AND output
                    try:
                        docked_mols = _read_pdbqt(str(output_file), logger=self.logger)
                        # Add all docked molecules from this replication to collection
                        if isinstance(docked_mols, list):
                            all_docked_molecules.extend(docked_mols)
                            # Set best_pose_mol if this is the first or has better affinity
                            if len(docked_mols) > 0 and docked_mols[0] is not None:
                                # First molecule in PDBQT is always the best for this run
                                if best_pose_mol is None:
                                    # First ever docked molecule
                                    best_pose_mol = docked_mols[0]
                                
                                # Merge best pose with clean receptor and save if enabled
                                if merge_enabled and clean_receptor is not None and merged_dir is not None:
                                    try:
                                        best_ligand = docked_mols[0]  # Best pose for this replication
                                        merged_complex = self._merge_molecules(clean_receptor, best_ligand)
                                        
                                        if merged_complex is not None:
                                            # Save as PDB file
                                            merged_filename = f"{ligand_file_base}_rep{rep_num}_complex.pdb"
                                            merged_path = merged_dir / merged_filename
                                            
                                            Chem.MolToPDBFile(merged_complex, str(merged_path))
                                            self.logger.info(f"Saved merged complex: {merged_filename}")
                                    except Exception as e:
                                        self.logger.warning(f"Failed to save merged complex for {ligand_file_base} rep {rep_num}: {e}")
                    except Exception:
                        docked_mols = []
                    
                    # Build result rows
                    for pose_idx, pose_data in enumerate(poses):
                        affinity = pose_data.get("affinity", float('inf'))
                        
                        # Track globally best affinity and update best_pose if better
                        if affinity < best_affinity:
                            best_affinity = affinity
                            if isinstance(docked_mols, list) and len(docked_mols) > pose_idx:
                                best_pose_mol = docked_mols[pose_idx]
                        
                        # Merge original row data with docking results
                        result_row = orig_row.copy()
                        result_row["ligand_file"] = ligand_file_name
                        result_row["replication"] = rep_num
                        result_row["mode"] = pose_data.get("mode", pose_idx + 1)
                        result_row["affinity"] = affinity
                        result_row["rmsd_lb"] = pose_data.get("rmsd_lb", 0.0)
                        result_row["rmsd_ub"] = pose_data.get("rmsd_ub", 0.0)
                        
                        all_results_rows.append(result_row)
            
            # Build final DataFrame
            import pandas as pd
            results_df = pd.DataFrame(all_results_rows)
            
            # Final progress
            try:
                self.report_progress(100, f"Completed: {total_ligands} ligands × {reps} replications")
            except Exception:
                pass
            
            self.logger.info(f"Batch docking completed: {len(results_df)} total results")
            
            return {
                "docking_results": results_df,
                "docked_molecules": all_docked_molecules,  # All docked molecules for analysis
                "folder_path": str(output_parent_dir),
                "docking_log": "\n".join(all_logs),
                "best_pose": [best_pose_mol] if best_pose_mol is not None else []  # Return as list
            }
            
        except Exception as e:
            self.logger.error(f"Error in batch docking execution: {e}")
            raise
