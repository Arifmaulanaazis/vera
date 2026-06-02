"""AutoDockVinaNode implementation."""

from .common import *  # noqa: F401,F403

class AutoDockVinaNode(BaseNode):
    """Node for AutoDock Vina molecular docking.

    Inputs:
      - receptor_molecules (molecules)
      - ligand_molecules (molecules)
      - grid_params (data): optional dict with center/size
    Outputs:
      - docking_results (data): pandas DataFrame of poses (mode, affinity, rmsd_lb, rmsd_ub)
      - docked_molecules (molecules): all poses as RDKit molecules
      - best_pose (molecules): best pose as a single-item list of RDKit molecule
      - docking_log (string): raw docking log text
    """
    
    def __init__(self):
        super().__init__("autodock_vina", "AutoDock Vina")
        self.logger = get_logger(__name__)
        
        # In-memory inputs
        self.add_input_port("receptor_molecules", "molecules")
        self.add_input_port("ligand_molecules", "molecules")
        self.add_input_port("grid_params", "data")
        # Outputs
        self.add_output_port("docking_results", "data")
        self.add_output_port("docked_molecules", "molecules")
        self.add_output_port("best_pose", "molecules")
        # Docking logs for all ligands concatenated as a single string
        self.add_output_port("docking_log", "string")
        
        # Properties
        self.set_property("center_x", 0.0)
        self.set_property("center_y", 0.0)
        self.set_property("center_z", 0.0)
        self.set_property("size_x", 20.0)
        self.set_property("size_y", 20.0)
        self.set_property("size_z", 20.0)
        self.set_property("exhaustiveness", 8)
        self.set_property("num_modes", 9)
        self.set_property("energy_range", 3.0)
        self.set_property("vina_version", "1.2.5")
        
    # --- Live UI/inputs sync ---
    def on_result(self, result: object) -> None:  # pragma: no cover - UI update hook
        """When upstream provides grid_params, sync center/size props and repaint.

        Workflow manager stores upstream values under last_input_<port> keys and
        then calls on_result({"live_update": True}). We read the cached
        last_input_grid_params here and update properties so they are visible in
        the inline summary and settings dialog.
        """
        try:
            grid = self.get_property("last_input_grid_params")
            if isinstance(grid, dict):
                try:
                    cx = float(grid.get("center_x", self.get_property("center_x")))
                    cy = float(grid.get("center_y", self.get_property("center_y")))
                    cz = float(grid.get("center_z", self.get_property("center_z")))
                    sx = float(grid.get("size_x", self.get_property("size_x")))
                    sy = float(grid.get("size_y", self.get_property("size_y")))
                    sz = float(grid.get("size_z", self.get_property("size_z")))
                except Exception:
                    cx = self.get_property("center_x")
                    cy = self.get_property("center_y")
                    cz = self.get_property("center_z")
                    sx = self.get_property("size_x")
                    sy = self.get_property("size_y")
                    sz = self.get_property("size_z")
                # Write back so UI/body reflects current grid
                self.set_property("center_x", cx)
                self.set_property("center_y", cy)
                self.set_property("center_z", cz)
                self.set_property("size_x", sx)
                self.set_property("size_y", sy)
                self.set_property("size_z", sz)
        except Exception:
            pass
        # Keep default behavior (store last_result and repaint)
        try:
            super().on_result(result)
        except Exception:
            pass

    def _inline_summary(self) -> list[str]:  # pragma: no cover - UI painting helper
        """Show grid center and size prominently inside the node body."""
        try:
            cx = float(self.get_property("center_x"))
            cy = float(self.get_property("center_y"))
            cz = float(self.get_property("center_z"))
            sx = float(self.get_property("size_x"))
            sy = float(self.get_property("size_y"))
            sz = float(self.get_property("size_z"))
            ex = self.get_property("exhaustiveness")
            nm = self.get_property("num_modes")
        except Exception:
            cx = cy = cz = 0.0
            sx = sy = sz = 0.0
            ex = nm = None
        lines = [
            f"Center: {cx:.2f}, {cy:.2f}, {cz:.2f}",
            f"Size:   {sx:.2f}, {sy:.2f}, {sz:.2f}",
        ]
        try:
            if ex is not None:
                lines.append(f"Exhaustiveness: {ex}")
            if nm is not None:
                lines.append(f"Num modes: {nm}")
        except Exception:
            pass
        return lines

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute AutoDock Vina docking.

        Supports batch docking when multiple ligand molecules are provided. Aggregates
        poses and outputs across all ligands. Adds a 'name' column to results
        (1-based index per input ligand) before the energy ('affinity') column. The
        docking_log output is a single concatenated string of logs for all ligands.
        """
        try:
            # Resolve molecules
            rec_mols = (inputs or {}).get("receptor_molecules") or []
            lig_mols = (inputs or {}).get("ligand_molecules") or []
            if not isinstance(rec_mols, list) or len(rec_mols) == 0:
                raise ValueError("receptor_molecules input is required")
            if not isinstance(lig_mols, list) or len(lig_mols) == 0:
                raise ValueError("ligand_molecules input is required")
            
            receptor_mol = rec_mols[0]  # Use first receptor for all ligands

            # Stage RDKit -> PDB -> PDBQT
            def _stage_rdkit_to_pdb(mol, name: str) -> Path:
                from rdkit import Chem
                from rdkit.Chem import AllChem
                tmp_dir = get_subdir("docking_stage")
                pdb_path = tmp_dir / f"{name}.pdb"
                # Ensure a single conformer to avoid multi-MODEL PDBs
                m = Chem.AddHs(mol)
                try:
                    if m.GetNumConformers() == 0:
                        AllChem.EmbedMolecule(m)
                    elif m.GetNumConformers() > 1:
                        # Keep first conformer only
                        c0 = m.GetConformer(0)
                        m_single = Chem.Mol(m)
                        m_single.RemoveAllConformers()
                        m_single.AddConformer(c0, assignId=True)
                        m = m_single
                except Exception:
                    pass
                Chem.MolToPDBFile(m, str(pdb_path))
                return pdb_path

            def _to_pdbqt(pdb_path: Path, name: str, add_h: bool = False) -> Path:
                obabel = resolve_openbabel_executable("obabel")
                out_dir = get_subdir("docking_stage")
                out = out_dir / f"{name}.pdbqt"
                cmd = [obabel, str(pdb_path), "-O", str(out)]
                # For receptor PDBQT, strip torsion-tree to keep rigid format
                if "receptor" in name.lower():
                    cmd.append("-xr")
                if add_h:
                    cmd.append("-h")
                self.logger.info(f"Preparing PDBQT: {' '.join(map(str, cmd))}")
                try:
                    # Run with working directory set to OpenBabel folder for reliable plugin discovery
                    ob_dir = Path(obabel).parent if isinstance(obabel, str) else None
                    subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=str(ob_dir) if ob_dir else None, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                except subprocess.CalledProcessError as e:
                    raise ValueError(f"OpenBabel failed: {(e.stderr or e.stdout or '').strip()}")
                # Validate output exists and non-empty
                try:
                    if (not out.exists()) or out.stat().st_size == 0:
                        raise ValueError("OpenBabel produced empty output")
                except Exception as e:
                    raise ValueError(f"OpenBabel output validation failed: {e}")
                return out

            def _sanitize_receptor_pdbqt(pdbqt_path: Path) -> Path:
                """Remove torsion-tree tags not accepted by Vina for rigid receptors.
                Filters out: ROOT/ENDROOT/BRANCH/ENDBRANCH/TORSDOF lines.
                Returns path to sanitized file (may be the same path if nothing changed).
                """
                try:
                    with open(pdbqt_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    banned = ("ROOT", "ENDROOT", "BRANCH", "ENDBRANCH", "TORSDOF")
                    if any(line.startswith(banned) for line in lines):
                        sanitized_path = pdbqt_path.with_name(pdbqt_path.stem + "_rigid.pdbqt")
                        with open(sanitized_path, "w", encoding="utf-8", errors="ignore") as w:
                            for line in lines:
                                if line.startswith(banned):
                                    continue
                                w.write(line)
                        return sanitized_path
                except Exception:
                    pass
                return pdbqt_path

            rec_pdb = _stage_rdkit_to_pdb(receptor_mol, "receptor")
            rec_pdbqt = _to_pdbqt(rec_pdb, "receptor_prepared", add_h=False)
            rec_pdbqt = _sanitize_receptor_pdbqt(rec_pdbqt)

            # Prepare output directory
            output_dir = get_subdir("docking_results")

            # Grid params
            grid = (inputs or {}).get("grid_params") or {}
            cx = float(grid.get("center_x", self.get_property("center_x")))
            cy = float(grid.get("center_y", self.get_property("center_y")))
            cz = float(grid.get("center_z", self.get_property("center_z")))
            sx = float(grid.get("size_x", self.get_property("size_x")))
            sy = float(grid.get("size_y", self.get_property("size_y")))
            sz = float(grid.get("size_z", self.get_property("size_z")))
            # Sync back to properties so UI reflects the actual grid used
            try:
                self.set_property("center_x", cx)
                self.set_property("center_y", cy)
                self.set_property("center_z", cz)
                self.set_property("size_x", sx)
                self.set_property("size_y", sy)
                self.set_property("size_z", sz)
            except Exception:
                pass

            # Aggregate across ligands
            all_poses: list[dict] = []
            docked_molecules_all: list = []
            best_poses_all: list = []
            docking_logs_all: list[str] = []

            try:
                total = max(1, len(lig_mols))
                self.report_progress(0, f"Docking 0/{total} ligands")
            except Exception:
                pass

            from nodes.io_nodes import _read_pdbqt  # type: ignore
            vina_exe = resolve_vina_executable(self.get_property("vina_version") or None)

            for idx, ligand_mol in enumerate(lig_mols, start=1):
                # Name string 1-based
                lig_name = str(idx)
                lig_pdb = _stage_rdkit_to_pdb(ligand_mol, f"ligand_{idx}")
                lig_pdbqt = _to_pdbqt(lig_pdb, f"ligand_{idx}_prepared", add_h=True)

                # Per-ligand output paths
                output_file = output_dir / f"docking_result_{idx}.pdbqt"
                log_file = output_dir / f"docking_{idx}.log"

                # Build Vina command for this ligand
                cmd = [
                    vina_exe,
                    "--receptor", str(rec_pdbqt),
                    "--ligand", str(lig_pdbqt),
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
                self.logger.info(f"Running AutoDock Vina (ligand {lig_name}): {' '.join(map(str, cmd))}")

                log_lines: list[str] = []
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                try:
                    # Register with workflow manager for hard-stop
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
                    raise RuntimeError(f"Vina failed for ligand {lig_name} with code {ret}. Last output:\n{tail}")
                # Persist stdout to log file
                try:
                    with open(log_file, "w", encoding="utf-8", errors="ignore") as lf:
                        lf.write("".join(log_lines))
                except Exception:
                    pass

                # Parse results for this ligand
                docking_results = self._parse_vina_output(log_file)
                poses = docking_results.get("poses", []) if isinstance(docking_results, dict) else []
                # Inject 'name' before energy/affinity when forming DataFrame later; capture as dicts here
                for p in poses:
                    if isinstance(p, dict):
                        p["name"] = lig_name
                all_poses.extend(poses)

                # Read docked molecules and append
                try:
                    lig_docked_mols = _read_pdbqt(str(output_file), logger=self.logger)
                except Exception:
                    lig_docked_mols = []
                if isinstance(lig_docked_mols, list):
                    if len(lig_docked_mols) > 0 and lig_docked_mols[0] is not None:
                        best_poses_all.append(lig_docked_mols[0])
                    docked_molecules_all.extend([m for m in lig_docked_mols if m is not None])

                # Collect log text string
                try:
                    docking_logs_all.append(Path(log_file).read_text(encoding="utf-8", errors="ignore"))
                except Exception:
                    docking_logs_all.append("")

                # Update progress based on ligands completed
                try:
                    pct = min(100, int(idx / max(1, total) * 100))
                    self.report_progress(pct, f"Docked {idx}/{total} ligands")
                except Exception:
                    pass

            # Build DataFrame with 'name' inserted before 'affinity'
            try:
                import pandas as _pd
                poses_df = _pd.DataFrame(all_poses)
                if not poses_df.empty:
                    # Ensure columns order: mode, name, affinity, rmsd_lb, rmsd_ub (when present)
                    cols = list(poses_df.columns)
                    # Insert 'name' if not present
                    if 'name' not in cols:
                        poses_df.insert(0, 'name', [None] * len(poses_df))
                        cols = list(poses_df.columns)
                    # Reorder to put 'name' before 'affinity' if 'affinity' exists
                    if 'affinity' in cols and 'name' in cols:
                        def _reorder(c):
                            base = [c for c in cols if c not in ("name", "affinity")]
                            # Try to keep 'mode' first if exists
                            ordered = []
                            if 'mode' in cols:
                                ordered.append('mode')
                            if 'mode' in base:
                                base.remove('mode')
                            # Insert name and affinity
                            ordered += ['name', 'affinity']
                            # Append the rest
                            for k in [k for k in cols if k not in ordered]:
                                if k not in ordered:
                                    ordered.append(k)
                            return ordered
                        poses_df = poses_df[_reorder(cols)]
            except Exception:
                poses_df = all_poses  # Fallback to list of dicts

            self.logger.info("AutoDock Vina docking completed successfully for all ligands")
            try:
                self.report_progress(100, f"Docked {len(lig_mols)}/{len(lig_mols)} ligands")
            except Exception:
                pass
            return {
                "docking_results": poses_df,
                "docked_molecules": docked_molecules_all,
                "best_pose": best_poses_all,
                "docking_log": "\n".join(docking_logs_all),
            }
            
        
        except subprocess.CalledProcessError as e:
            error_msg = f"AutoDock Vina failed: {(e.stderr or e.stdout or '').strip()}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)
        except Exception as e:
            self.logger.error(f"Error in AutoDock Vina execution: {e}")
            raise ValueError(f"Docking execution error: {str(e)}")
    
    def _parse_vina_output(self, log_file: Path) -> Dict[str, Any]:
        """Parse AutoDock Vina output log."""
        results = {
            "poses": [],
            "best_affinity": None,
            "num_poses": 0
        }
        
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
            
            # Find results section
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
                        results["poses"].append(pose_data)
            
            if results["poses"]:
                results["best_affinity"] = results["poses"][0]["affinity"]
                results["num_poses"] = len(results["poses"])
                
        except Exception as e:
            self.logger.warning(f"Could not parse Vina output: {e}")
        
        return results
    
    def validate(self) -> tuple[bool, str]:
        """Validate the node configuration."""
        # Check grid box size
        size_x = float(self.get_property("size_x"))
        size_y = float(self.get_property("size_y"))
        size_z = float(self.get_property("size_z"))
        if any(size <= 0 for size in [size_x, size_y, size_z]):
            return False, "Grid box size must be positive"
        return True, "Node configuration is valid"
