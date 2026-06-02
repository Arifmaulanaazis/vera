"""AutoDockVinaGPUNode implementation."""

from .common import *  # noqa: F401,F403
from .auto_dock_vina_node import AutoDockVinaNode

class AutoDockVinaGPUNode(AutoDockVinaNode):
    """Node for GPU-accelerated AutoDock Vina."""
    
    def __init__(self):
        super().__init__()
        self.node_type = "autodock_vina_gpu"
        self.title = "AutoDock Vina GPU"
        
        # Override default executable
        # GPU executable resolved dynamically
        self.set_property("gpu_batch", 50)
        self.set_property("thread", 1000)
        
    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute GPU-accelerated AutoDock Vina with in-memory molecules.

        Supports batch ligands analogous to CPU implementation. Aggregates outputs
        and returns logs concatenated into a single string.
        """
        try:
            # Reuse staging from parent
            rec_mols = (inputs or {}).get("receptor_molecules") or []
            lig_mols = (inputs or {}).get("ligand_molecules") or []
            if not isinstance(rec_mols, list) or not rec_mols:
                raise ValueError("receptor_molecules input is required")
            if not isinstance(lig_mols, list) or not lig_mols:
                raise ValueError("ligand_molecules input is required")
            
            receptor_mol = rec_mols[0]

            # Helper methods from parent scope
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
                if add_h:
                    cmd.append("-h")
                self.logger.info(f"Preparing PDBQT: {' '.join(map(str, cmd))}")
                subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                return out

            def _sanitize_receptor_pdbqt(pdbqt_path: Path) -> Path:
                """Remove torsion-tree tags not accepted by Vina for rigid receptors."""
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

            # Prepare output directory in session temp
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

            # Aggregate across ligands (GPU)
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
            percent_re = __import__('re').compile(r"(\d{1,3})%|\bmode\s+(\d+)\b", __import__('re').IGNORECASE)
            vina_gpu_exe = resolve_vina_gpu_executable()

            for idx, ligand_mol in enumerate(lig_mols, start=1):
                lig_name = str(idx)
                try:
                    self.report_progress(35, f"Preparing ligand {lig_name}")
                except Exception:
                    pass
                lig_pdb = _stage_rdkit_to_pdb(ligand_mol, f"ligand_{idx}")
                lig_pdbqt = _to_pdbqt(lig_pdb, f"ligand_{idx}_prepared", add_h=True)

                # Per-ligand output paths
                output_file = output_dir / f"docking_result_gpu_{idx}.pdbqt"
                log_file = output_dir / f"docking_gpu_{idx}.log"

                # Build GPU Vina command (no --log option)
                cmd = [
                    vina_gpu_exe,
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
                    "--energy_range", str(self.get_property("energy_range")),
                    "--gpu_batch", str(self.get_property("gpu_batch")),
                    "--thread", str(self.get_property("thread"))
                ]
                self.logger.info(f"Running AutoDock Vina GPU (ligand {lig_name}): {' '.join(map(str, cmd))}")

                log_lines: list[str] = []
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
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
                    raise RuntimeError(f"Vina GPU failed for ligand {lig_name} with code {ret}. Last output:\n{tail}")
                # Write stdout to log file
                try:
                    with open(log_file, "w", encoding="utf-8", errors="ignore") as lf:
                        lf.write("".join(log_lines))
                except Exception:
                    pass

                # Parse results (dict with poses list)
                docking_results = self._parse_vina_output(log_file)
                poses = docking_results.get("poses", []) if isinstance(docking_results, dict) else []
                for p in poses:
                    if isinstance(p, dict):
                        p["name"] = lig_name
                all_poses.extend(poses)

                docked_molecules = []
                try:
                    docked_molecules = _read_pdbqt(str(output_file), logger=self.logger)
                except Exception:
                    docked_molecules = []
                if isinstance(docked_molecules, list):
                    if len(docked_molecules) > 0 and docked_molecules[0] is not None:
                        best_poses_all.append(docked_molecules[0])
                    docked_molecules_all.extend([m for m in docked_molecules if m is not None])

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

            # Prepare outputs in requested forms
            try:
                import pandas as _pd
                poses_df = _pd.DataFrame(all_poses)
                if not poses_df.empty and 'affinity' in poses_df.columns:
                    # Ensure 'name' column exists and is placed before 'affinity'
                    if 'name' not in poses_df.columns:
                        poses_df.insert(0, 'name', [None] * len(poses_df))
                    cols = list(poses_df.columns)
                    # Reorder columns: mode (if exists), name, affinity, rest
                    ordered = []
                    if 'mode' in cols:
                        ordered.append('mode')
                    ordered += ['name', 'affinity']
                    ordered += [c for c in cols if c not in ordered]
                    poses_df = poses_df[ordered]
            except Exception:
                poses_df = all_poses

            self.logger.info("AutoDock Vina GPU docking completed successfully for all ligands")
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
            
        except Exception as e:
            self.logger.error(f"Error in AutoDock Vina GPU execution: {e}")
            raise
