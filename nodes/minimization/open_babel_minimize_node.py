"""OpenBabelMinimizeNode implementation."""

from .common import *  # noqa: F401,F403

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
