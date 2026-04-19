"""
Molecular docking nodes for AutoDock Vina and related tools.
"""

import subprocess
import os
from pathlib import Path
from typing import Dict, Any, Optional

from core.nodes import BaseNode
from utils.logging_utils import get_logger
from utils.external_tools import (
    resolve_vina_executable,
    resolve_vina_gpu_executable,
    resolve_openbabel_executable,
)
from backend.temp_manager import get_subdir


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


class GridSearchNode(BaseNode):
    """Compute docking grid box from molecules (similar to AutoDockTools).

    Inputs:
      - ligand_molecules (molecules) optional
      - protein_molecules (molecules) optional
    Outputs:
      - grid_params (data): dict with center_x/y/z and size_x/y/z
    """

    def __init__(self):
        super().__init__("grid_search", "Grid Box Search")
        self.logger = get_logger(__name__)
        # No input ports; this node fetches from PDB and computes grid
        self.add_output_port("grid_params", "data")
        # Properties
        self.set_property("padding", 5.0)
        # PDB fetch and selection
        self.set_property("pdb_code", "")
        self.set_property("selected_residue", "")  # format: RES:CHAIN:RESNUM[ICODE]
        # Behavior and safety clamps
        self.set_property("mode", "ligand")  # ligand | protein | custom
        self.set_property("min_size", 16.0)
        self.set_property("max_size", 60.0)
        self.set_property("override_center", False)
        self.set_property("center_x", 0.0)
        self.set_property("center_y", 0.0)
        self.set_property("center_z", 0.0)
        self.set_property("override_size", False)
        self.set_property("size_x", 20.0)
        self.set_property("size_y", 20.0)
        self.set_property("size_z", 20.0)

        # Inline widgets: PDB code input, Fetch button, Residue combobox
        # Keep optional in non-GUI environments
        self._residue_coords_map: dict[str, list[tuple[float, float, float]]] = {}
        self._ligand_options: list[str] = []
        try:
            from PySide6.QtWidgets import QLineEdit, QPushButton, QComboBox


            # Resize node to fit inline widgets
            self.width = 340
            self.height = 180
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)

            # PDB code line edit
            self._pdb_edit = QLineEdit()
            self._pdb_edit.setPlaceholderText("PDB ID (e.g., 1ABC)")
            self._pdb_edit.setText(self.get_property("pdb_code") or "")
            def _on_pdb_text_changed(text: str):
                try:
                    self.set_property("pdb_code", (text or "").strip())
                except Exception:
                    pass
            self._pdb_edit.textChanged.connect(_on_pdb_text_changed)

            # Fetch button
            self._fetch_btn = QPushButton("Fetch")
            self._fetch_btn.clicked.connect(self._on_fetch_clicked)

            # Residue combobox
            self._res_combo = QComboBox()
            self._res_combo.addItem("")
            # Restore last selection if any
            sel = self.get_property("selected_residue") or ""
            if sel:
                self._res_combo.addItem(sel)
                self._res_combo.setCurrentText(sel)
            def _on_res_changed(text: str):
                try:
                    self.set_property("selected_residue", text or "")
                except Exception:
                    pass
            self._res_combo.currentTextChanged.connect(_on_res_changed)

            # Place widgets into the node's grid layout
            layout = self.content_layout
            if layout is not None:
                # Add a top spacer row to push content slightly down
                from PySide6.QtWidgets import QSpacerItem, QSizePolicy
                layout.addItem(QSpacerItem(0, 6, QSizePolicy.Minimum, QSizePolicy.Fixed), 0, 0, 1, 2)
                # Row 1: line edit + fetch button
                layout.addWidget(self._pdb_edit, 1, 0)
                layout.addWidget(self._fetch_btn, 1, 1)
                # Row 2: residue combo spanning both columns
                layout.addWidget(self._res_combo, 2, 0, 1, 2)
                try:
                    layout.setColumnStretch(0, 1)
                    layout.setColumnStretch(1, 0)
                except Exception:
                    pass
            # Ensure ports arranged after sizing
            self._update_port_positions()
        except Exception:
            # Headless or missing Qt, skip inline UI
            self._pdb_edit = None
            self._fetch_btn = None
            self._res_combo = None

    def _bbox_from_molecules(self, mols: list) -> Optional[tuple[float, float, float, float, float, float]]:
        try:
            import numpy as np
            from rdkit.Chem import rdMolTransforms
            coords = []
            for m in mols:
                if m is None or m.GetNumConformers() == 0:
                    continue
                conf = m.GetConformer(0)
                for idx in range(m.GetNumAtoms()):
                    p = conf.GetAtomPosition(idx)
                    coords.append([p.x, p.y, p.z])
            if not coords:
                return None
            arr = np.array(coords, dtype=float)
            mins = arr.min(axis=0)
            maxs = arr.max(axis=0)
            return mins[0], mins[1], mins[2], maxs[0], maxs[1], maxs[2]
        except Exception:
            return None

    def _bbox_from_coords(self, coords: list[tuple[float, float, float]]) -> Optional[tuple[float, float, float, float, float, float]]:
        try:
            if not coords:
                return None
            import numpy as np
            arr = np.array(coords, dtype=float)
            mins = arr.min(axis=0)
            maxs = arr.max(axis=0)
            return mins[0], mins[1], mins[2], maxs[0], maxs[1], maxs[2]
        except Exception:
            return None

    # --- Inline UI handlers ---
    def _on_fetch_clicked(self):
        try:
            pdb_code = (self.get_property("pdb_code") or "").strip()
            if not pdb_code:
                return
            options, coords_map = self._fetch_and_index_structure(pdb_code)
            if not options:
                # No ligands found
                self._residue_coords_map = {}
                if self._res_combo is not None:
                    try:
                        self._res_combo.clear()
                        self._res_combo.addItem("")
                    except Exception:
                        pass
                return
            self._residue_coords_map = coords_map
            self._ligand_options = options
            if self._res_combo is not None:
                try:
                    current = self.get_property("selected_residue") or ""
                    self._res_combo.blockSignals(True)
                    self._res_combo.clear()
                    for opt in options:
                        self._res_combo.addItem(opt)
                    # Restore current if still present, else first option
                    if current and current in options:
                        self._res_combo.setCurrentText(current)
                    else:
                        self._res_combo.setCurrentIndex(0)
                        self.set_property("selected_residue", options[0])
                finally:
                    try:
                        self._res_combo.blockSignals(False)
                    except Exception:
                        pass
        except Exception as e:
            try:
                self.logger.warning(f"PDB fetch failed: {e}")
            except Exception:
                pass

    def _fetch_and_index_structure(self, pdb_code: str) -> tuple[list[str], dict[str, list[tuple[float, float, float]]]]:
        """Fetch PDB/mmCIF from RCSB and index ligand residues.

        Returns (options_list, coords_map) where options are strings like RES:CHAIN:RESSEQ[ICODE].
        """
        import io
        import requests
        options: list[str] = []
        coords_map: dict[str, list[tuple[float, float, float]]] = {}

        code = (pdb_code or "").strip().upper()
        if not code:
            return options, coords_map
        urls = [
            f"https://files.rcsb.org/download/{code}.pdb",
            f"https://files.rcsb.org/download/{code}.cif",
            f"https://files.rcsb.org/download/{code}.mmcif",
        ]

        text = None
        used_fmt = None
        for url in urls:
            try:
                r = requests.get(url, timeout=20)
                if r.status_code == 200 and r.text:
                    text = r.text
                    if url.endswith(".pdb"):
                        used_fmt = "pdb"
                    else:
                        used_fmt = "cif"
                    break
            except Exception:
                continue
        if text is None:
            raise RuntimeError(f"Could not download PDB for {code}")

        # Parse with Biopython
        try:
            from Bio.PDB import PDBParser, MMCIFParser
            if used_fmt == "pdb":
                parser = PDBParser(QUIET=True)
                handle = io.StringIO(text)
                structure = parser.get_structure(code, handle)
            else:
                parser = MMCIFParser(QUIET=True)
                handle = io.StringIO(text)
                structure = parser.get_structure(code, handle)
        except Exception as e:
            raise RuntimeError(f"Parsing failed for {code}: {e}")

        # Collect ligand-like residues (hetero, non-water)
        try:
            for model in structure:
                for chain in model:
                    chain_id = getattr(chain, 'id', 'A')
                    for residue in chain:
                        resname = residue.get_resname() if hasattr(residue, 'get_resname') else None
                        if not resname:
                            continue
                        hetflag = residue.id[0] if isinstance(residue.id, tuple) and len(residue.id) > 0 else ' '
                        # Skip standard amino acids and waters
                        if (hetflag == ' ' and resname in {
                            'ALA','ARG','ASN','ASP','CYS','GLN','GLU','GLY','HIS','ILE','LEU','LYS','MET','PHE','PRO','SER','THR','TRP','TYR','VAL'
                        }):
                            continue
                        if resname in {"HOH", "WAT", "DOD"}:
                            continue
                        # Build key
                        resseq = residue.id[1] if isinstance(residue.id, tuple) and len(residue.id) > 1 else 0
                        icode = residue.id[2] if isinstance(residue.id, tuple) and len(residue.id) > 2 else ' '
                        icode_str = '' if (not icode or icode == ' ') else str(icode)
                        key = f"{resname}:{chain_id}:{resseq}{icode_str}"
                        # Collect atom coords
                        coords: list[tuple[float, float, float]] = []
                        try:
                            for atom in residue:
                                try:
                                    pos = atom.get_coord()
                                    coords.append((float(pos[0]), float(pos[1]), float(pos[2])))
                                except Exception:
                                    continue
                        except Exception:
                            coords = []
                        if coords:
                            if key not in coords_map:
                                options.append(key)
                                coords_map[key] = coords
        except Exception as e:
            raise RuntimeError(f"Failed to index ligands: {e}")

        # Deduplicate while preserving order
        seen = set()
        uniq_options: list[str] = []
        for k in options:
            if k not in seen:
                uniq_options.append(k)
                seen.add(k)
        return uniq_options, coords_map

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Validate required inputs for ligand/protein modes
        mode = (self.get_property("mode") or "ligand").lower()
        if mode in ("ligand", "protein"):
            pdb_code = (self.get_property("pdb_code") or "").strip()
            sel_residue = (self.get_property("selected_residue") or "").strip()
            
            if not pdb_code or not sel_residue:
                raise ValueError("Required inputs not provided: PDB code and selected residue. Please configure the node.")

        
        padding = float(self.get_property("padding") or 5.0)
        min_size = float(self.get_property("min_size") or 0.0)
        max_size = float(self.get_property("max_size") or 1e9)
        override_center = bool(self.get_property("override_center"))
        override_size = bool(self.get_property("override_size"))

        cx = cy = cz = 0.0
        sx = sy = sz = 20.0

        bbox = None
        # Selected residue from fetched PDB
        if bbox is None and mode in ("ligand", "protein"):
            sel_key = self.get_property("selected_residue") or ""
            pdb_code = (self.get_property("pdb_code") or "").strip()
            coords = []
            if sel_key:
                # Use cached map; if missing, try on-demand fetch
                coords_map_cached = getattr(self, "_residue_coords_map", None)
                if (not coords_map_cached) and pdb_code:
                    try:
                        options, coords_map = self._fetch_and_index_structure(pdb_code)
                        try:
                            self._residue_coords_map = coords_map
                            self._ligand_options = options
                        except Exception:
                            pass
                    except Exception:
                        try:
                            self._residue_coords_map = {}
                        except Exception:
                            pass
                coords_map_cached = getattr(self, "_residue_coords_map", {})
                coords = coords_map_cached.get(sel_key, [])
            if coords:
                bbox = self._bbox_from_coords(coords)

        # Priority 3: Custom
        if bbox is None and mode == "custom":
            override_center = True
            override_size = True

        if bbox is None:
            # Fallback to default centered at origin
            cx = float(self.get_property("center_x") or 0.0)
            cy = float(self.get_property("center_y") or 0.0)
            cz = float(self.get_property("center_z") or 0.0)
            sx = float(self.get_property("size_x") or 20.0)
            sy = float(self.get_property("size_y") or 20.0)
            sz = float(self.get_property("size_z") or 20.0)
        else:
            x0, y0, z0, x1, y1, z1 = bbox
            # Center and size with padding
            cx = (x0 + x1) / 2.0
            cy = (y0 + y1) / 2.0
            cz = (z0 + z1) / 2.0
            sx = abs(x1 - x0) + padding
            sy = abs(y1 - y0) + padding
            sz = abs(z1 - z0) + padding
            # Clamp sizes
            sx = max(min_size, min(sx, max_size))
            sy = max(min_size, min(sy, max_size))
            sz = max(min_size, min(sz, max_size))

        # Overrides from properties when requested
        if override_center:
            cx = float(self.get_property("center_x") or cx)
            cy = float(self.get_property("center_y") or cy)
            cz = float(self.get_property("center_z") or cz)
        if override_size:
            sx = float(self.get_property("size_x") or sx)
            sy = float(self.get_property("size_y") or sy)
            sz = float(self.get_property("size_z") or sz)

        grid = {"center_x": cx, "center_y": cy, "center_z": cz, "size_x": sx, "size_y": sy, "size_z": sz}
        # Store to properties for visibility
        try:
            self.set_property("center_x", cx)
            self.set_property("center_y", cy)
            self.set_property("center_z", cz)
            self.set_property("size_x", sx)
            self.set_property("size_y", sy)
            self.set_property("size_z", sz)
        except Exception:
            pass
        self.logger.info(f"Grid params: {grid}")
        return {"grid_params": grid}



class ManualGridBoxNode(BaseNode):
    """Manual grid box input for docking.
    
    User directly inputs all center and size coordinates.
    Validates that all 6 parameters are provided before execution.
    
    Outputs:
      - grid_params (data): dict with center_x/y/z and size_x/y/z
    """
    
    def __init__(self):
        super().__init__("manual_grid_box", "Manual Grid Box")
        self.logger = get_logger(__name__)
        
        # Output port
        self.add_output_port("grid_params", "data")
        
        # Properties for grid parameters - all required
        self.set_property("center_x", None)
        self.set_property("center_y", None)
        self.set_property("center_z", None)
        self.set_property("size_x", None)
        self.set_property("size_y", None)
        self.set_property("size_z", None)
        
        # UI setup - create input fields
        try:
            from PySide6.QtWidgets import QLabel, QDoubleSpinBox, QGridLayout
            from PySide6.QtCore import Qt
            
            
            # Resize node to fit inputs
            self.width = 280
            self.height = 300
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)
            
            # Create spinboxes for all 6 parameters
            self._spin_boxes = {}
            
            layout = self.content_layout
            if layout is not None:
                # Add labels and spin boxes in grid layout
                params = [
                    ("center_x", "Center X:", 0),
                    ("center_y", "Center Y:", 1),
                    ("center_z", "Center Z:", 2),
                    ("size_x", "Size X:", 3),
                    ("size_y", "Size Y:", 4),
                    ("size_z", "Size Z:", 5),
                ]
                
                for prop_name, label_text, row in params:
                    label = QLabel(label_text)
                    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    
                    spinbox = QDoubleSpinBox()
                    spinbox.setRange(-9999.0, 9999.0)
                    spinbox.setDecimals(3)
                    spinbox.setSingleStep(1.0)
                    
                    # Set current value if exists
                    val = self.get_property(prop_name)
                    if val is not None:
                        try:
                            spinbox.setValue(float(val))
                        except:
                            pass
                    else:
                        # Set placeholder value (will show as unset)
                        spinbox.setSpecialValueText("(not set)")
                        spinbox.setValue(spinbox.minimum())
                    
                    # Connect value changed signal
                    def make_handler(name):
                        def handler(value):
                            try:
                                # Only set if not at minimum (our "not set" indicator)
                                if value > spinbox.minimum():
                                    self.set_property(name, value)
                                else:
                                    self.set_property(name, None)
                            except Exception:
                                pass
                        return handler
                    
                    spinbox.valueChanged.connect(make_handler(prop_name))
                    
                    layout.addWidget(label, row, 0)
                    layout.addWidget(spinbox, row, 1)
                    self._spin_boxes[prop_name] = spinbox
                
                layout.setColumnStretch(0, 0)
                layout.setColumnStretch(1, 1)
            
            self._update_port_positions()
        except Exception:
            # Headless mode
            self._spin_boxes = {}

    
    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Validate that all 6 parameters are provided
        params = ["center_x", "center_y", "center_z", "size_x", "size_y", "size_z"]
        missing = []
        values = {}
        
        for param in params:
            val = self.get_property(param)
            if val is None:
                missing.append(param)
            else:
                try:
                    values[param] = float(val)
                except (ValueError, TypeError):
                    missing.append(param)
        
        if missing:
            missing_str = ", ".join(missing)
            raise ValueError(f"Required parameters not provided: {missing_str}. Please configure all grid box parameters.")


        
        # All parameters provided, create grid dict
        grid = {
            "center_x": values["center_x"],
            "center_y": values["center_y"],
            "center_z": values["center_z"],
            "size_x": values["size_x"],
            "size_y": values["size_y"],
            "size_z": values["size_z"],
        }
        
        self.logger.info(f"Manual grid box: {grid}")
        return {"grid_params": grid}



class DockingAnalysisNode(BaseNode):
    """Analyze Vina docking outputs.

    Inputs:
      - docking_results (data): DataFrame or list[dict] with columns at least 'affinity' and preferably 'name'
      - molecules (molecules): either all poses (docked_molecules) or best poses per ligand (best_pose)

    Outputs:
      - analysis_dataframe (data): DataFrame suitable for plotting
      - molecules (molecules): molecules selected by the chosen analysis
      - best_pose (molecule): single molecule with the best (lowest) affinity overall
    """

    def __init__(self):
        super().__init__("docking_analysis", "Docking Analysis")
        self.logger = get_logger(__name__)

        # Two input pins only
        self.add_input_port("docking_results", "data")
        self.add_input_port("molecules", "molecules")

        # Outputs
        self.add_output_port("analysis_dataframe", "data")
        self.add_output_port("molecules", "molecules")
        self.add_output_port("best_pose", "molecule")

        # Analysis configuration
        self.set_property("analysis_mode", "best_per_ligand")  # best_per_ligand | top_k_global | top_k_per_ligand | threshold | summary
        self.set_property("top_k", 1)
        self.set_property("affinity_threshold", -7.0)
        # Additional UX properties
        self.set_property("ligand_filter", "")  # comma-separated names or substring
        self.set_property("sort_by", "affinity")  # affinity | name | mode | rmsd_lb | rmsd_ub
        self.set_property("sort_desc", False)
        self.set_property("preview_source", "analysis")  # analysis | input
        self.set_property("auto_refresh_preview", True)

        # Inline UI with table preview + floating params panel (pattern from DataframeMergeNode)
        from PySide6.QtWidgets import (
            QTableWidget,
            QGraphicsProxyWidget,
            QWidget,
            QVBoxLayout,
            QHBoxLayout,
            QLabel,
            QComboBox,
            QPushButton,
            QFrame,
            QLineEdit,
            QSpinBox,
            QDoubleSpinBox,
        )
        try:
            from PySide6.QtCore import Qt
        except Exception:
            Qt = None  # type: ignore

        # Node sizing similar to merge node
        self.width = 560
        self.height = 300
        try:
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)
            self.set_content_margins(0, 32, 0, 0)
        except Exception:
            pass

        # Table preview
        try:
            self._table = QTableWidget()
            self._table.setColumnCount(0)
            self._table.setRowCount(0)
            try:
                self._table.setAlternatingRowColors(True)
                self._table.setShowGrid(True)
                header = self._table.horizontalHeader()
                header.setStretchLastSection(True)
            except Exception:
                pass
            layout = self.content_layout
            if layout is not None:
                layout.addWidget(self._table, 0, 0)
            self._update_port_positions()
        except Exception:
            self._table = None

        # Floating params panel
        self._params_proxy = None
        self._params_widget = None
        try:
            panel = QFrame()
            panel.setObjectName("NodeDockingAnalysisParams")
            try:
                panel.setStyleSheet(
                    """
                    QFrame#NodeDockingAnalysisParams {
                        background-color: #2b2b2b;
                        border: 1px solid #666666;
                        border-radius: 6px;
                    }
                    QLabel { color: #e0e0e0; }
                    QLineEdit { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 2px 6px; }
                    QComboBox { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 2px 6px; }
                    QPushButton { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 4px 8px; }
                    QSpinBox, QDoubleSpinBox { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 2px 6px; }
                    """
                )
            except Exception:
                pass

            v = QVBoxLayout(panel)
            v.setContentsMargins(8, 6, 8, 6)
            v.setSpacing(6)

            # Analysis mode
            row_mode = QHBoxLayout()
            row_mode.addWidget(QLabel("Mode"))
            self._cmb_mode = QComboBox()
            try:
                self._cmb_mode.addItems(["best_per_ligand", "top_k_global", "top_k_per_ligand", "threshold", "summary"])  # type: ignore[attr-defined]
                cur = str(self.get_property("analysis_mode") or "best_per_ligand")
                idx = self._cmb_mode.findText(cur) if hasattr(self._cmb_mode, 'findText') else -1
                if idx >= 0:
                    self._cmb_mode.setCurrentIndex(idx)
            except Exception:
                pass
            row_mode.addWidget(self._cmb_mode)
            v.addLayout(row_mode)

            # Top K and threshold
            row_nums = QHBoxLayout()
            row_nums.addWidget(QLabel("Top K"))
            self._spin_topk = QSpinBox()
            self._spin_topk.setRange(1, 999)
            try:
                self._spin_topk.setValue(int(self.get_property("top_k") or 1))
            except Exception:
                pass
            row_nums.addWidget(self._spin_topk)

            row_nums.addWidget(QLabel("Threshold"))
            self._spin_thr = QDoubleSpinBox()
            self._spin_thr.setDecimals(2)
            self._spin_thr.setRange(-1000.0, 1000.0)
            self._spin_thr.setSingleStep(0.1)
            try:
                self._spin_thr.setValue(float(self.get_property("affinity_threshold") or -7.0))
            except Exception:
                pass
            row_nums.addWidget(self._spin_thr)
            v.addLayout(row_nums)

            # Ligand filter
            row_filter = QVBoxLayout()
            row_filter.addWidget(QLabel("Ligand filter (names or substring)"))
            self._edit_filter = QLineEdit(str(self.get_property("ligand_filter") or ""))
            row_filter.addWidget(self._edit_filter)
            v.addLayout(row_filter)

            # Sorting
            row_sort = QHBoxLayout()
            row_sort.addWidget(QLabel("Sort"))
            self._cmb_sort_by = QComboBox()
            try:
                self._cmb_sort_by.addItems(["affinity", "name", "mode", "rmsd_lb", "rmsd_ub"])  # type: ignore[attr-defined]
                cur_sb = str(self.get_property("sort_by") or "affinity")
                idx_sb = self._cmb_sort_by.findText(cur_sb) if hasattr(self._cmb_sort_by, 'findText') else -1
                if idx_sb >= 0:
                    self._cmb_sort_by.setCurrentIndex(idx_sb)
            except Exception:
                pass
            self._cmb_sort_dir = QComboBox()
            try:
                self._cmb_sort_dir.addItems(["asc", "desc"])  # type: ignore[attr-defined]
                if bool(self.get_property("sort_desc")):
                    self._cmb_sort_dir.setCurrentIndex(1)
            except Exception:
                pass
            row_sort.addWidget(self._cmb_sort_by)
            row_sort.addWidget(self._cmb_sort_dir)
            v.addLayout(row_sort)

            # Preview source
            row_prev = QHBoxLayout()
            row_prev.addWidget(QLabel("Preview"))
            self._cmb_preview = QComboBox()
            try:
                self._cmb_preview.addItems(["analysis", "input"])  # type: ignore[attr-defined]
                cur_pv = str(self.get_property("preview_source") or "analysis")
                idx_pv = self._cmb_preview.findText(cur_pv) if hasattr(self._cmb_preview, 'findText') else -1
                if idx_pv >= 0:
                    self._cmb_preview.setCurrentIndex(idx_pv)
            except Exception:
                pass
            row_prev.addWidget(self._cmb_preview)
            v.addLayout(row_prev)

            # Buttons
            row_btns = QHBoxLayout()
            self._btn_apply = QPushButton("Apply")
            self._btn_refresh = QPushButton("Refresh")
            row_btns.addWidget(self._btn_apply)
            row_btns.addStretch(1)
            row_btns.addWidget(self._btn_refresh)
            v.addLayout(row_btns)

            self._params_widget = panel
            self._params_proxy = QGraphicsProxyWidget(self)
            self._params_proxy.setWidget(panel)
            try:
                self._params_proxy.setZValue(8)
                self._params_proxy.setVisible(True)
            except Exception:
                pass

            # Wire interactions
            try:
                self._cmb_mode.currentTextChanged.connect(self._on_mode_changed)  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                self._spin_topk.valueChanged.connect(self._on_topk_changed)  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                self._spin_thr.valueChanged.connect(self._on_thr_changed)  # type: ignore[attr-defined]
            except Exception:
                pass
            self._edit_filter.textChanged.connect(self._on_filter_changed)
            try:
                self._cmb_sort_by.currentTextChanged.connect(self._on_sort_changed)  # type: ignore[attr-defined]
                self._cmb_sort_dir.currentTextChanged.connect(self._on_sort_changed)  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                self._cmb_preview.currentTextChanged.connect(self._on_preview_changed)  # type: ignore[attr-defined]
            except Exception:
                pass
            self._btn_apply.clicked.connect(self._on_apply_clicked)
            self._btn_refresh.clicked.connect(self._on_refresh_clicked)

            # Initial geometry sync
            try:
                self._update_content_geometry(force=True)
                self.update()
            except Exception:
                pass
        except Exception:
            self._params_proxy = None
            self._params_widget = None

    def _normalize_results_df(self, docking_results):
        try:
            import pandas as pd  # type: ignore
        except Exception:
            pd = None  # type: ignore

        df = None
        if pd is not None and docking_results is not None:
            if isinstance(docking_results, pd.DataFrame):
                df = docking_results.copy()
            elif isinstance(docking_results, list) and (len(docking_results) == 0 or isinstance(docking_results[0], dict)):
                df = pd.DataFrame(docking_results)
            elif isinstance(docking_results, dict) and isinstance(docking_results.get("poses"), list):
                df = pd.DataFrame(docking_results["poses"])  # type: ignore
        # Ensure required columns
        if df is not None and not df.empty:
            if "affinity" not in df.columns:
                # Try 'energy' fallback
                for alt in ("energy", "Energy", "ENERGY"):
                    if alt in df.columns:
                        df = df.rename(columns={alt: "affinity"})
                        break
            # Ensure 'name' column exists for ligand grouping
            if "name" not in df.columns:
                # Assign to a single ligand group if missing
                df.insert(0, "name", ["1"] * len(df))
        return df

    def _detect_molecule_mode(self, df, molecules: list) -> str:
        """Return 'all_poses' if molecules count matches df rows, or 'best_pose' if it matches unique ligands."""
        if not isinstance(molecules, list):
            return "unknown"
        try:
            n_rows = 0 if df is None else int(len(df))
            unique_names = 0 if df is None or "name" not in df.columns else int(len(set(df["name"].astype(str))))
            if len(molecules) == n_rows and n_rows > 0:
                return "all_poses"
            if unique_names > 0 and len(molecules) == unique_names:
                return "best_pose"
        except Exception:
            pass
        return "unknown"

    # --- Inline UI helpers ---
    def _set_table_data(self, data: Any) -> None:
        try:
            from PySide6.QtWidgets import QTableWidgetItem
        except Exception:
            return
        if getattr(self, "_table", None) is None:
            return
        try:
            self._table.setUpdatesEnabled(False)
            self._table.setSortingEnabled(False)
        except Exception:
            pass
        # Normalize to rows
        rows: list[dict]
        if data is None:
            rows = []
        else:
            try:
                import pandas as pd
                if isinstance(data, pd.DataFrame):
                    rows = data.to_dict(orient="records")
                elif isinstance(data, list) and (len(data) == 0 or isinstance(data[0], dict)):
                    rows = data
                else:
                    rows = [{"value": str(data)}]
            except Exception:
                rows = [{"value": str(data)}]

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
                try:
                    item = QTableWidgetItem(str(val))
                    self._table.setItem(r, c, item)
                except Exception:
                    pass
        try:
            self._table.setSortingEnabled(True)
            self._table.setUpdatesEnabled(True)
        except Exception:
            pass

    def _apply_sort_and_filter(self, df):
        try:
            import pandas as pd  # type: ignore
        except Exception:
            pd = None  # type: ignore
        if df is None:
            return df
        try:
            # Ligand filter
            filt = str(self.get_property("ligand_filter") or "").strip()
            if filt and "name" in df.columns:
                if "," in filt:
                    allow = {s.strip() for s in filt.split(",") if s.strip()}
                    df = df[df["name"].astype(str).isin(allow)]
                else:
                    sub = filt.lower()
                    df = df[df["name"].astype(str).str.lower().str.contains(sub, na=False)]
            # Sorting
            by = str(self.get_property("sort_by") or "")
            desc = bool(self.get_property("sort_desc"))
            if by and by in df.columns:
                df = df.sort_values(by=by, ascending=not desc)
            # Reset index for cleaner view
            try:
                df = df.reset_index(drop=True)
            except Exception:
                pass
        except Exception:
            pass
        return df

    def _update_preview_from_last_inputs(self) -> None:
        try:
            # Determine preview source
            preview_src = str(self.get_property("preview_source") or "analysis")
            # Pull last cached inputs
            docking_results = self.properties.get("last_input_docking_results")
            df = self._normalize_results_df(docking_results)
            if preview_src == "input":
                shown = self._apply_sort_and_filter(df) if df is not None else []
                self._set_table_data(shown)
                return
            # analysis preview
            mols_input = self.properties.get("last_input_molecules") or []
            analysis_df, _mols = self._perform_analysis(df, mols_input)
            shown = self._apply_sort_and_filter(analysis_df) if analysis_df is not None else []
            self._set_table_data(shown)
        except Exception:
            try:
                self._set_table_data([])
            except Exception:
                pass

    # Keep output ports anchored to the right of the params panel
    def _update_content_geometry(self, force: bool = False) -> None:  # type: ignore[override]
        try:
            super()._update_content_geometry(force)
        except Exception:
            pass
        try:
            if getattr(self, "_params_proxy", None) is not None and getattr(self, "_params_widget", None) is not None:
                try:
                    self._params_widget.setFixedHeight(int(self.height))
                except Exception:
                    pass
                panel_w = int(max(140, min(240, self.width * 0.35)))
                try:
                    self._params_widget.setFixedWidth(panel_w)
                    self._params_widget.adjustSize()
                except Exception:
                    pass
                x_offset = float(self.width) + 12.0
                self._params_proxy.setPos(x_offset, 0.0)
                try:
                    def _anchor_override() -> float:
                        return float(self.width) + 12.0 + float(panel_w)
                    object.__setattr__(self, "_get_output_port_anchor_x", _anchor_override)  # type: ignore[arg-type]
                    self._update_port_positions()
                except Exception:
                    pass
        except Exception:
            pass

    # UI callbacks
    def _on_mode_changed(self, mode: str) -> None:
        try:
            self.set_property("analysis_mode", str(mode))
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_topk_changed(self, value: int) -> None:
        try:
            self.set_property("top_k", int(value))
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_thr_changed(self, value: float) -> None:
        try:
            self.set_property("affinity_threshold", float(value))
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_filter_changed(self, text: str) -> None:
        try:
            self.set_property("ligand_filter", str(text))
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_sort_changed(self, _text: str) -> None:
        try:
            self.set_property("sort_by", str(self._cmb_sort_by.currentText()))
            self.set_property("sort_desc", bool(self._cmb_sort_dir.currentText() == "desc"))
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_preview_changed(self, _text: str) -> None:
        try:
            self.set_property("preview_source", str(self._cmb_preview.currentText()))
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _on_apply_clicked(self) -> None:
        try:
            # Trigger downstream re-execution from this node
            if hasattr(self, 'rerun_requested'):
                self.rerun_requested.emit(self)
        except Exception:
            pass

    def _on_refresh_clicked(self) -> None:
        try:
            self._update_preview_from_last_inputs()
        except Exception:
            pass

    def _inline_summary(self) -> list[str]:  # pragma: no cover - UI painting helper
        try:
            mode = str(self.get_property("analysis_mode") or "best_per_ligand")
            lines = [f"Mode: {mode}"]
            if mode.startswith("top_k"):
                lines.append(f"Top K: {int(self.get_property('top_k') or 1)}")
            if mode == "threshold":
                try:
                    thr = float(self.get_property("affinity_threshold") or -7.0)
                    lines.append(f"Thr: {thr:.2f}")
                except Exception:
                    pass
            lf = str(self.get_property("ligand_filter") or "").strip()
            if lf:
                lines.append(f"Filter: {lf}")
            return lines
        except Exception:
            return []

    # Shared analysis logic (used by execute and preview)
    def _perform_analysis(self, df, mols_input: list) -> tuple:
        try:
            import pandas as pd  # type: ignore
        except Exception:
            pd = None  # type: ignore

        if df is None or (hasattr(df, 'empty') and df.empty) or (isinstance(df, list) and not df):
            return df, []

        # Normalize dtypes and prepare original row index for molecule mapping
        try:
            if hasattr(df, 'astype'):
                df["name"] = df["name"].astype(str)
                df["affinity"] = df["affinity"].astype(float)
        except Exception:
            pass
        df_work = df
        try:
            if hasattr(df, 'copy'):
                df_work = df.copy()
                df_work["__row_idx"] = list(range(len(df_work)))
        except Exception:
            df_work = df

        mode = (self.get_property("analysis_mode") or "best_per_ligand").strip().lower()
        top_k = max(1, int(self.get_property("top_k") or 1))
        thr = float(self.get_property("affinity_threshold") or -7.0)

        # How molecules correspond to rows
        mol_mode = self._detect_molecule_mode(df, mols_input)

        def select_molecules_by_indices(indices: list[int]) -> list:
            if mol_mode == "all_poses" and isinstance(mols_input, list) and len(mols_input) >= max(indices + [0]):
                try:
                    return [mols_input[i] for i in indices if i < len(mols_input) and mols_input[i] is not None]
                except Exception:
                    return []
            if mol_mode == "best_pose":
                return list(mols_input)
            return []

        analysis_df = None
        molecules_out: list = []

        if mode == "best_per_ligand":
            if pd is not None and hasattr(df_work, 'groupby'):
                idxs = df_work.groupby("name")["affinity"].idxmin()
                best_rows = df_work.loc[idxs]
                analysis_df = best_rows.reset_index(drop=True)
                try:
                    sel_indices = list(best_rows["__row_idx"].astype(int).tolist())
                except Exception:
                    sel_indices = list(idxs.astype(int).tolist())
            else:
                analysis_df = df_work
                sel_indices = []
            if mol_mode == "best_pose":
                # Best per ligand: map ligand names to best_pose positions (1-based names)
                try:
                    names = []
                    if hasattr(analysis_df, 'to_dict'):
                        names = [str(n) for n in list(analysis_df["name"].astype(str).tolist()) if n is not None]
                    mapped: list = []
                    for n in names:
                        try:
                            idx = int(float(n)) - 1
                        except Exception:
                            idx = None
                        if idx is not None and 0 <= idx < len(mols_input):
                            mapped.append(mols_input[idx])
                    molecules_out = mapped
                except Exception:
                    molecules_out = list(mols_input)
            else:
                molecules_out = select_molecules_by_indices(sel_indices)

        elif mode == "top_k_global":
            if hasattr(df_work, 'sort_values'):
                sorted_df = df_work.sort_values(by="affinity", ascending=True)
                analysis_head = sorted_df.head(top_k)
                analysis_df = analysis_head.reset_index(drop=True)
                try:
                    sel_indices = list(analysis_head["__row_idx"].astype(int).tolist())
                except Exception:
                    sel_indices = list(analysis_df.index)
            else:
                analysis_df = df_work
                sel_indices = []
            if mol_mode == "best_pose":
                # Map selected ligand names to best_pose list
                try:
                    names = []
                    if hasattr(analysis_df, 'to_dict'):
                        names = [str(n) for n in list(analysis_df["name"].astype(str).tolist()) if n is not None]
                    unique_names = []
                    seen = set()
                    for n in names:
                        if n not in seen:
                            unique_names.append(n); seen.add(n)
                    mapped: list = []
                    for n in unique_names:
                        try:
                            idx = int(float(n)) - 1  # supports "1" or "1.0"
                        except Exception:
                            idx = None
                        if idx is not None and 0 <= idx < len(mols_input):
                            mapped.append(mols_input[idx])
                    molecules_out = mapped if mapped else list(mols_input)
                except Exception:
                    molecules_out = list(mols_input)
            else:
                molecules_out = select_molecules_by_indices(sel_indices)

        elif mode == "top_k_per_ligand":
            if hasattr(df_work, 'sort_values') and hasattr(df_work, 'groupby'):
                sorted_group = df_work.sort_values(["name", "affinity"], ascending=[True, True])
                take = sorted_group.groupby("name", as_index=False).head(top_k)
                analysis_df = take.reset_index(drop=True)
                try:
                    sel_indices = list(take["__row_idx"].astype(int).tolist())
                except Exception:
                    sel_indices = list(analysis_df.index)
            else:
                sel_indices = []
            if mol_mode == "best_pose":
                # One best molecule per ligand; map by ligand name
                try:
                    names = []
                    if hasattr(analysis_df, 'to_dict'):
                        names = [str(n) for n in list(analysis_df["name"].astype(str).tolist()) if n is not None]
                    unique_names = []
                    seen = set()
                    for n in names:
                        if n not in seen:
                            unique_names.append(n); seen.add(n)
                    mapped: list = []
                    for n in unique_names:
                        try:
                            idx = int(float(n)) - 1
                        except Exception:
                            idx = None
                        if idx is not None and 0 <= idx < len(mols_input):
                            mapped.append(mols_input[idx])
                    molecules_out = mapped if mapped else list(mols_input)
                except Exception:
                    molecules_out = list(mols_input)
            else:
                molecules_out = select_molecules_by_indices(sel_indices)

        elif mode == "threshold":
            if hasattr(df_work, 'reset_index'):
                filt = df_work[df_work["affinity"] <= thr]
                analysis_df = filt.reset_index(drop=True)
                try:
                    sel_indices = list(filt["__row_idx"].astype(int).tolist())
                except Exception:
                    sel_indices = list(analysis_df.index)
            else:
                sel_indices = []
            if mol_mode == "best_pose":
                # Map to best_pose by ligand name subset
                try:
                    names = []
                    if hasattr(analysis_df, 'to_dict'):
                        names = [str(n) for n in list(analysis_df["name"].astype(str).tolist()) if n is not None]
                    unique_names = []
                    seen = set()
                    for n in names:
                        if n not in seen:
                            unique_names.append(n); seen.add(n)
                    mapped: list = []
                    for n in unique_names:
                        try:
                            idx = int(float(n)) - 1
                        except Exception:
                            idx = None
                        if idx is not None and 0 <= idx < len(mols_input):
                            mapped.append(mols_input[idx])
                    molecules_out = mapped if mapped else list(mols_input)
                except Exception:
                    molecules_out = list(mols_input)
            else:
                molecules_out = select_molecules_by_indices(sel_indices)

        else:  # summary
            if hasattr(df_work, 'groupby'):
                grp = df_work.groupby("name")["affinity"]
                try:
                    analysis_df = grp.agg(best="min", worst="max", mean="mean", count="count").reset_index()
                except Exception:
                    # Fallback for older pandas
                    analysis_df = grp.agg(["min", "max", "mean", "count"]).reset_index()
                    try:
                        analysis_df = analysis_df.rename(columns={"min": "best", "max": "worst", "count": "count"})
                    except Exception:
                        pass
            else:
                analysis_df = df_work
            molecules_out = list(mols_input) if mol_mode == "best_pose" else []

        # Drop helper column from display/output if present
        try:
            if hasattr(analysis_df, 'drop') and "__row_idx" in list(analysis_df.columns):
                analysis_df = analysis_df.drop(columns=["__row_idx"])  # type: ignore
        except Exception:
            pass
        # Sanitize molecule list and provide robust fallback to ensure viewer compatibility
        try:
            if isinstance(molecules_out, list):
                molecules_out = [m for m in molecules_out if m is not None]
        except Exception:
            pass
        # Only fallback for best_pose wiring; never auto-fallback to all poses
        try:
            if (not molecules_out) and (self._detect_molecule_mode(df, mols_input) == "best_pose"):
                if isinstance(mols_input, list):
                    molecules_out = [m for m in mols_input if m is not None]
        except Exception:
            pass
        # Fallback: ensure we always return a list like AutoDock outputs
        try:
            if not isinstance(molecules_out, list):
                molecules_out = list(molecules_out) if molecules_out is not None else []
        except Exception:
            molecules_out = []
        return analysis_df, molecules_out

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            docking_results = (inputs or {}).get("docking_results")
            mols_input = (inputs or {}).get("molecules") or []

            df = self._normalize_results_df(docking_results)
            if df is None or df.empty or "affinity" not in df.columns:
                raise ValueError("Invalid docking_results: expected DataFrame or list of poses with 'affinity'")
            analysis_df, molecules_out = self._perform_analysis(df, mols_input)

            # Compute single best pose molecule across all entries
            best_pose_mol = None
            try:
                # Find index/row of global minimum affinity
                # Use argmin over values to get positional index robustly
                import numpy as _np  # type: ignore
                affinities = _np.array(list(df["affinity"].astype(float)))
                pos_min = int(affinities.argmin()) if affinities.size > 0 else -1
                if 0 <= pos_min < len(df):
                    mol_mode = self._detect_molecule_mode(df, mols_input)
                    if mol_mode == "all_poses":
                        if 0 <= pos_min < len(mols_input):
                            cand = mols_input[pos_min]
                            if cand is not None:
                                best_pose_mol = cand
                    elif mol_mode == "best_pose":
                        # Map ligand name of best row to best_pose index (1-based)
                        try:
                            lig_name = str(df.iloc[pos_min]["name"]) if "name" in df.columns else None
                        except Exception:
                            lig_name = None
                        if lig_name is not None:
                            try:
                                lig_idx = int(float(lig_name)) - 1
                                if 0 <= lig_idx < len(mols_input):
                                    cand = mols_input[lig_idx]
                                    if cand is not None:
                                        best_pose_mol = cand
                            except Exception:
                                pass
                    else:
                        # Unknown mapping; best-effort: if counts match rows, treat as all_poses
                        if len(mols_input) == len(df) and 0 <= pos_min < len(mols_input):
                            cand = mols_input[pos_min]
                            if cand is not None:
                                best_pose_mol = cand
            except Exception:
                best_pose_mol = None

            result = {
                "analysis_dataframe": analysis_df if analysis_df is not None else df,
                "molecules": molecules_out,
                "best_pose": best_pose_mol,
            }
            return result
        except Exception as e:
            self.logger.error(f"Error in docking analysis: {e}")
            raise

    # Live update hook for preview
    def on_result(self, result: object) -> None:  # pragma: no cover - UI update hook
        try:
            if bool(self.get_property("auto_refresh_preview")):
                self._update_preview_from_last_inputs()
            try:
                self._update_content_geometry(force=False)
                self.update()
            except Exception:
                pass
        except Exception:
            pass
        super().on_result(result)


class VinaSplitNode(BaseNode):
    """Split a molecules list into individual molecule outputs.

    Inputs:
      - molecules (molecules): list or single RDKit Mol, typically from AutoDock Vina/GPU outputs

    Outputs (dynamic count):
      - molecule_<k> (molecules): single molecule per pin, where k runs from start to start+N-1

    Properties:
      - start_index_1based (int): 1-based start index (1 maps to list index 0). Default 1.
      - num_outputs (int): number of output pins to expose starting from start_index_1based. Default 3.
    """

    def __init__(self):
        super().__init__("vina_split", "Vina Split")
        self.logger = get_logger(__name__)

        # Single input: molecules (accepts list or single)
        self.add_input_port("molecules", "molecules")

        # Properties controlling dynamic outputs
        self.set_property("start_index_1based", 1)
        self.set_property("num_outputs", 3)

        # Build initial output pins
        self._rebuild_output_ports()

    # Headless-safe property setter that rebuilds output pins when relevant properties change
    def set_property(self, key, value):  # type: ignore[override]
        try:
            if hasattr(self, "_created_in_gui_thread") and hasattr(self, "update"):
                try:
                    super().set_property(key, value)
                except Exception:
                    if hasattr(self, "properties"):
                        self.properties[key] = value
            else:
                if hasattr(self, "properties"):
                    self.properties[key] = value
        except Exception:
            pass

        if key in ("num_outputs", "start_index_1based"):
            # Normalize stored values
            try:
                if key == "num_outputs":
                    n = int(value)
                    if n < 1:
                        n = 1
                    if self.get_property("num_outputs") != n and hasattr(self, "properties"):
                        self.properties["num_outputs"] = n
                elif key == "start_index_1based":
                    s = int(value)
                    if s < 1:
                        s = 1
                    if self.get_property("start_index_1based") != s and hasattr(self, "properties"):
                        self.properties["start_index_1based"] = s
            except Exception:
                pass

            # Rebuild dynamic outputs (only in GUI context where ports exist)
            if hasattr(self, "output_ports") and hasattr(self, "add_output_port"):
                self._rebuild_output_ports()

    def _rebuild_output_ports(self) -> None:
        try:
            # Remove existing output ports from the scene and dict
            for p in list(self.output_ports.values()):
                try:
                    if p.scene() is not None:
                        p.scene().removeItem(p)
                except Exception:
                    pass
                try:
                    p.setParentItem(None)
                except Exception:
                    pass
            self.output_ports = {}

            # Compute current labels based on properties
            try:
                start_1 = int(self.get_property("start_index_1based") or 1)
            except Exception:
                start_1 = 1
            if start_1 < 1:
                start_1 = 1
            try:
                num = int(self.get_property("num_outputs") or 1)
            except Exception:
                num = 1
            num = max(1, num)

            # Add outputs molecule_<k> for k in [start_1, start_1+num-1]
            for k in range(start_1, start_1 + num):
                self.add_output_port(f"molecule_{k}", "molecules")

            # Adjust height based on ports (simple heuristic)
            try:
                total_ports = len(self.input_ports) + len(self.output_ports)
                base_h = 120
                self.height = max(base_h, 30 * (total_ports + 1))
                self.setMinimumSize(self.width, self.height)
                self.setMaximumSize(self.width, self.height)
            except Exception:
                pass
            self._update_port_positions()
        except Exception:
            pass

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            # Gather input molecules (accept list or single)
            val = (inputs or {}).get("molecules") if inputs else None
            molecules: list = []
            if val is None:
                pass
            elif isinstance(val, list):
                molecules = [m for m in val if m is not None]
            else:
                molecules = [val]

            if not molecules:
                raise ValueError("Input 'molecules' is required and must contain at least one molecule")

            # Resolve properties
            try:
                start_1 = int(self.get_property("start_index_1based") or 1)
            except Exception:
                start_1 = 1
            if start_1 < 1:
                start_1 = 1
            start_0 = start_1 - 1

            try:
                desired_outputs = int(self.get_property("num_outputs") or 3)
            except Exception:
                desired_outputs = 3
            if desired_outputs < 1:
                desired_outputs = 1

            # Clamp to available molecules
            available_from_start = max(0, len(molecules) - start_0)
            effective_outputs = min(desired_outputs, available_from_start) if available_from_start > 0 else 0

            # If start is beyond available, reset to 1
            if effective_outputs == 0:
                start_1 = 1
                start_0 = 0
                available_from_start = len(molecules)
                effective_outputs = min(desired_outputs, available_from_start)

            # If UI property exceeds available, normalize and rebuild pins
            try:
                if effective_outputs != desired_outputs:
                    self.set_property("num_outputs", effective_outputs)
                # Ensure output pins reflect current start/index range
                self.set_property("start_index_1based", start_1)
            except Exception:
                pass

            # Build outputs: molecule_<k> -> single RDKit Mol (not a list)
            outputs: Dict[str, Any] = {}
            for i in range(effective_outputs):
                k_1 = start_1 + i
                idx = start_0 + i
                if 0 <= idx < len(molecules):
                    outputs[f"molecule_{k_1}"] = molecules[idx]

            return outputs
        except Exception as e:
            self.logger.error(f"Error in VinaSplitNode: {e}")
            raise


class MergeMoleculeNode(BaseNode):
    """Merge protein and ligand molecules into a single protein-ligand complex.

    Inputs (configurable count):
      - protein_1 (molecules), protein_2, ... [num_proteins]
      - ligand_1 (molecules), ligand_2, ... [num_ligands]

    Outputs:
      - molecules (molecules): single-item list containing the protein-ligand complex
    """

    def __init__(self):
        super().__init__("merge_molecule", "Merge Molecule")
        self.logger = get_logger(__name__)

        # Default inputs: 1 protein + 1 ligand
        self.add_input_port("protein_1", "molecules")
        self.add_input_port("ligand_1", "molecules")

        # One output: merged complex as a single-item molecules list
        self.add_output_port("molecules", "molecules")

        # Properties for separate protein/ligand counts
        self.set_property("num_proteins", 1)  # number of protein input pins
        self.set_property("num_ligands", 1)   # number of ligand input pins
        self.set_property("add_hydrogens", False)  # optional H addition before merge
        self.set_property("embed_missing_coords", True)  # embed 3D if a mol has no conformer
        # Output mode: 'merged_single' (one RDKit Mol containing protein+ligand) or 'separate' (list)
        self.set_property("output_mode", "merged_single")

    # Rebuild input pins when protein/ligand counts change
    def set_property(self, key, value):  # type: ignore[override]
        # Headless-safe property write
        try:
            # Only call BaseNode.set_property when running on a real QGraphics node
            if hasattr(self, "_created_in_gui_thread") and hasattr(self, "update"):
                try:
                    super().set_property(key, value)
                except Exception:
                    # Fallback to direct dict write
                    if hasattr(self, "properties"):
                        self.properties[key] = value
            else:
                if hasattr(self, "properties"):
                    self.properties[key] = value
        except Exception:
            pass

        if key in ("num_proteins", "num_ligands"):
            try:
                n = int(value)
            except Exception:
                n = 1
            n = max(1, min(6, n))  # Allow 1-6 of each type
            # Normalize stored value
            try:
                if (self.get_property(key) != n) and hasattr(self, "properties"):
                    self.properties[key] = n
            except Exception:
                pass
            # Only rebuild pins in GUI context
            if hasattr(self, "input_ports") and hasattr(self, "add_input_port"):
                self._rebuild_input_ports()

    def _rebuild_input_ports(self) -> None:
        try:
            # Remove existing input ports from the scene and dict
            for p in list(self.input_ports.values()):
                try:
                    if p.scene() is not None:
                        p.scene().removeItem(p)
                except Exception:
                    pass
                try:
                    p.setParentItem(None)
                except Exception:
                    pass
            self.input_ports = {}

            # Get current counts
            num_proteins = max(1, int(self.get_property("num_proteins") or 1))
            num_ligands = max(1, int(self.get_property("num_ligands") or 1))

            # Add protein inputs
            for i in range(1, num_proteins + 1):
                self.add_input_port(f"protein_{i}", "molecules")

            # Add ligand inputs
            for i in range(1, num_ligands + 1):
                self.add_input_port(f"ligand_{i}", "molecules")

            # Adjust height based on total ports
            try:
                total_ports = num_proteins + num_ligands
                base_h = 120
                self.height = max(base_h, 30 * (total_ports + 1))
                self.setMinimumSize(self.width, self.height)
                self.setMaximumSize(self.width, self.height)
            except Exception:
                pass
            self._update_port_positions()
        except Exception:
            pass

    def _gather_input_molecules(self, inputs: Optional[Dict[str, Any]]) -> tuple[list, list]:
        """Gather protein and ligand molecules separately."""
        proteins: list = []
        ligands: list = []
        if not inputs:
            return proteins, ligands

        # Get current counts (headless-safe)
        try:
            num_proteins = max(1, int(self.get_property("num_proteins") or 1))
            num_ligands = max(1, int(self.get_property("num_ligands") or 1))
        except Exception:
            num_proteins = num_ligands = 1

        # Collect proteins
        for i in range(1, num_proteins + 1):
            val = inputs.get(f"protein_{i}")
            if val is None:
                continue
            if isinstance(val, list):
                for m in val:
                    if m is not None:
                        proteins.append(m)
            else:
                proteins.append(val)

        # Collect ligands
        for i in range(1, num_ligands + 1):
            val = inputs.get(f"ligand_{i}")
            if val is None:
                continue
            if isinstance(val, list):
                for m in val:
                    if m is not None:
                        ligands.append(m)
            else:
                ligands.append(val)

        return proteins, ligands

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            from rdkit import Chem  # type: ignore
            from rdkit.Chem import AllChem  # type: ignore
        except Exception:
            raise RuntimeError("RDKit is required for Merge Molecule")

        # Collect proteins and ligands separately
        proteins, ligands = self._gather_input_molecules(inputs)
        if not proteins and not ligands:
            raise ValueError("At least one protein or ligand molecule is required")

        add_h = bool(self.get_property("add_hydrogens"))
        embed_missing = bool(self.get_property("embed_missing_coords"))

        def _prepare_molecule(mol, add_hydrogens: bool = False):
            """Prepare a single molecule with optional H addition and conformer embedding."""
            if mol is None:
                return None
            try:
                prepared = Chem.Mol(mol)
                if add_hydrogens:
                    try:
                        prepared = Chem.AddHs(prepared)
                    except Exception:
                        pass
                # Ensure conformer exists
                if embed_missing and prepared.GetNumConformers() == 0:
                    try:
                        AllChem.EmbedMolecule(prepared)
                    except Exception:
                        try:
                            AllChem.Compute2DCoords(prepared)
                        except Exception:
                            pass
                return prepared
            except Exception:
                return mol

        def _assign_chain_info(mol, chain_id: str, res_name: str):
            """Assign chain ID and residue names to atoms via PDB info."""
            if mol is None:
                return mol
            try:
                for atom in mol.GetAtoms():
                    # Set PDB residue info for proper visualization
                    atom_info = Chem.AtomPDBResidueInfo()
                    atom_info.SetChainId(chain_id)
                    atom_info.SetResidueName(res_name)
                    atom_info.SetResidueNumber(1)
                    atom_info.SetName(atom.GetSymbol() + str(atom.GetIdx() + 1))
                    atom.SetPDBResidueInfo(atom_info)
                return mol
            except Exception:
                return mol

        def _merge_into_single_molecule(parts: list) -> Any:
            """Combine multiple RDKit molecules into a single molecule while preserving coordinates
            and PDB residue information (including HETATM flags for ligands).

            Returns a new RDKit Mol (single conformer with concatenated coordinates).
            """
            try:
                from rdkit import Chem  # type: ignore
                from rdkit.Chem import AllChem  # type: ignore
            except Exception:
                return None

            if not parts:
                return None

            # Topology union using CombineMols
            combined = None
            for m in parts:
                if m is None:
                    continue
                combined = m if combined is None else Chem.CombineMols(combined, m)
            if combined is None:
                return None

            # Build a single conformer with concatenated coordinates
            total_atoms = combined.GetNumAtoms()
            conf = Chem.Conformer(total_atoms)
            atom_offset = 0
            per_offsets: list[int] = []
            for m in parts:
                if m is None:
                    per_offsets.append(atom_offset)
                    continue
                na = m.GetNumAtoms()
                per_offsets.append(atom_offset)
                if m.GetNumConformers() > 0:
                    c = m.GetConformer(0)
                    for i in range(na):
                        p = c.GetAtomPosition(i)
                        conf.SetAtomPosition(atom_offset + i, p)
                atom_offset += na

            rwm = Chem.RWMol(combined)
            # Replace any existing conformers and attach the new one
            try:
                rwm.RemoveAllConformers()
            except Exception:
                pass
            try:
                rwm.AddConformer(conf, assignId=True)
            except Exception:
                # Fallback: return without coordinates (still usable)
                pass

            # Preserve PDB residue info from sources
            try:
                dst_atoms = [rwm.GetAtomWithIdx(i) for i in range(total_atoms)]
                off = 0
                for idx_part, m in enumerate(parts):
                    if m is None:
                        continue
                    na = m.GetNumAtoms()
                    for i in range(na):
                        src_atom = m.GetAtomWithIdx(i)
                        dst_atom = dst_atoms[off + i]
                        try:
                            info = src_atom.GetPDBResidueInfo()
                        except Exception:
                            info = None
                        if info is None:
                            # Leave as-is if none available
                            continue
                        try:
                            new_info = Chem.AtomPDBResidueInfo()
                            # Copy key fields
                            try: new_info.SetChainId(info.GetChainId())
                            except Exception: pass
                            try: new_info.SetResidueName(info.GetResidueName())
                            except Exception: pass
                            try: new_info.SetResidueNumber(info.GetResidueNumber())
                            except Exception: pass
                            try: new_info.SetIsHetero(info.GetIsHetero())
                            except Exception: pass
                            try: new_info.SetName(info.GetName())
                            except Exception: pass
                            try:
                                ic = info.GetInsertionCode()
                                if ic:
                                    new_info.SetInsertionCode(ic)
                            except Exception:
                                pass
                            dst_atom.SetPDBResidueInfo(new_info)
                        except Exception:
                            # Best-effort; ignore copy failures
                            pass
                    off += na
            except Exception:
                pass

            return rwm.GetMol()

        # Prepare proteins with original PDB residue info preserved
        prepared_proteins: list = []
        chain_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        for prot in proteins:
            # Do NOT add hydrogens or override PDB residue info for proteins
            prepared = _prepare_molecule(prot, add_hydrogens=False)
            if prepared is not None:
                prepared_proteins.append(prepared)

        # Prepare ligands with chain X, Y, Z... and residue name "LIG"
        prepared_ligands: list = []
        ligand_chains = "XYZUVWRST"
        for i, lig in enumerate(ligands):
            prepared = _prepare_molecule(lig, add_hydrogens=add_h)
            if prepared is not None:
                chain_id = ligand_chains[i % len(ligand_chains)]
                # Assign ligand residue info and mark as HETATM
                try:
                    for atom in prepared.GetAtoms():
                        info = Chem.AtomPDBResidueInfo()
                        info.SetChainId(chain_id)
                        info.SetResidueName("LIG")
                        info.SetResidueNumber(1 + i)
                        info.SetIsHetero(True)
                        info.SetName(atom.GetSymbol() + str(atom.GetIdx() + 1))
                        atom.SetPDBResidueInfo(info)
                except Exception:
                    pass
                prepared = prepared
                prepared_ligands.append(prepared)

        # Decide output mode
        output_mode = (self.get_property("output_mode") or "merged_single").strip().lower()
        all_mols = prepared_proteins + prepared_ligands
        if not all_mols:
            raise ValueError("No valid molecules after preparation")

        complex_info = {
            "num_proteins": len(prepared_proteins),
            "num_ligands": len(prepared_ligands),
            "ligand_chains": [ligand_chains[i % len(ligand_chains)] for i in range(len(prepared_ligands))],
            "output_mode": output_mode,
        }
        self.logger.info(f"Prepared complex: {len(prepared_proteins)} proteins, {len(prepared_ligands)} ligands; mode={output_mode}")

        if output_mode == "merged_single":
            merged = _merge_into_single_molecule(all_mols)
            if merged is not None:
                return {"molecules": [merged], "complex_info": complex_info}
            # Fallback to separate if merge failed
            self.logger.warning("Merging into single molecule failed; returning separate molecules")
            return {"molecules": all_mols, "complex_info": complex_info}
        else:
            # Separate output
            return {"molecules": all_mols, "complex_info": complex_info}


class ReceptorPreparationNode(BaseNode):
    """Prepare receptor molecules similar to AutoDockTools.

    Operations (configurable):
      - Remove waters (HOH/WAT)
      - Remove ligands (HETATM) with options to keep metals/ions or specific residues
      - Add hydrogens (none | polar_only | all)
      - Compute charges (none | gasteiger | kollman [placeholder])

    Inputs:
      - molecules (molecules): RDKit molecules (e.g., from RCSB PDB)

    Outputs:
      - molecules (molecules): cleaned/prepared RDKit molecules
    """

    def __init__(self):
        super().__init__("receptor_preparation", "Receptor Preparation")
        self.logger = get_logger(__name__)

        # Ports
        self.add_input_port("molecules", "molecules")
        self.add_output_port("molecules", "molecules")

        # Properties
        self.set_property("remove_waters", True)
        self.set_property("remove_ligands", True)
        self.set_property("keep_metals", True)
        self.set_property("keep_resnames", "")  # CSV e.g. HEM,NAG,ZN
        self.set_property("remove_nonstd_residues", False)
        self.set_property("add_hydrogens_mode", "polar_only")  # none | polar_only | all
        self.set_property("compute_charges", "kollman")  # none | gasteiger | kollman
        self.set_property("metal_elements", "ZN,MG,FE,MN,CU,CO,NI,CA,NA,K,CD,HG")
        self.set_property("unique_atom_names", False)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            from rdkit import Chem  # type: ignore
            from rdkit.Chem import AllChem  # type: ignore
        except Exception:
            raise RuntimeError("RDKit is required for Receptor Preparation")

        mols_in = None
        if inputs and inputs.get("molecules") is not None:
            val = inputs.get("molecules")
            mols_in = val if isinstance(val, list) else [val]
        if not mols_in:
            raise ValueError("Input 'molecules' is required")

        remove_waters = bool(self.get_property("remove_waters"))
        remove_ligands = bool(self.get_property("remove_ligands"))
        keep_metals = bool(self.get_property("keep_metals"))
        remove_nonstd = bool(self.get_property("remove_nonstd_residues"))
        add_h_mode = str(self.get_property("add_hydrogens_mode") or "polar_only").strip().lower()
        charge_mode = str(self.get_property("compute_charges") or "none").strip().lower()

        # Parse CSV properties
        def _parse_csv(text: Any) -> set[str]:
            try:
                s = str(text or "")
            except Exception:
                s = ""
            parts = []
            if s:
                for tok in s.replace(";", ",").split(","):
                    t = tok.strip().upper()
                    if t:
                        parts.append(t)
            return set(parts)

        keep_resnames = _parse_csv(self.get_property("keep_resnames"))
        metal_elems = _parse_csv(self.get_property("metal_elements")) or {
            "ZN", "MG", "FE", "MN", "CU", "CO", "NI", "CA", "NA", "K", "CD", "HG"
        }

        std_aas = {
            "CYS", "ILE", "SER", "VAL", "GLN", "LYS", "ASN", "PRO", "THR", "PHE", "ALA",
            "HIS", "GLY", "ASP", "LEU", "ARG", "TRP", "GLU", "TYR", "MET", "HID", "HSP",
            "HIE", "HIP", "CYX", "CSS"
        }
        nuc_res = {"DA", "DC", "DG", "DT", "DU", "A", "C", "G", "T", "U"}

        out_mols: list[Any] = []

        for idx, mol in enumerate(mols_in):
            if mol is None:
                continue
            try:
                try:
                    self.report_progress(min(90, int(idx / max(1, len(mols_in)) * 100)), f"Preparing receptor {idx+1}")
                except Exception:
                    pass

                m = Chem.Mol(mol)

                # Build atom deletion list based on residue info
                atoms_to_delete: list[int] = []
                for a in m.GetAtoms():
                    ai = a.GetIdx()
                    try:
                        info = a.GetPDBResidueInfo()
                    except Exception:
                        info = None
                    if info is None:
                        continue
                    resname = (info.GetResidueName() or "").strip().upper()
                    is_het = False
                    try:
                        is_het = bool(info.GetIsHetero())
                    except Exception:
                        # Heuristic: treat non-standard residue names as HETATM
                        is_het = resname not in std_aas and resname not in nuc_res

                    # Water removal
                    if remove_waters and resname in {"HOH", "WAT"}:
                        atoms_to_delete.append(ai)
                        continue

                    # Ligand removal (HETATM) with exceptions
                    if remove_ligands and is_het:
                        sym = a.GetSymbol().upper()
                        if keep_metals and sym in metal_elems:
                            continue
                        if resname in keep_resnames:
                            continue
                        atoms_to_delete.append(ai)
                        continue

                    # Non-standard residues (optional)
                    if remove_nonstd and (resname not in std_aas) and (resname not in nuc_res):
                        atoms_to_delete.append(ai)
                        continue

                if atoms_to_delete:
                    rw = Chem.RWMol(m)
                    for ai in sorted(set(atoms_to_delete), reverse=True):
                        try:
                            rw.RemoveAtom(int(ai))
                        except Exception:
                            pass
                    m = rw.GetMol()

                # Add hydrogens as configured
                add_coords = True
                if add_h_mode == "all":
                    try:
                        m = Chem.AddHs(m, addCoords=add_coords)
                    except Exception:
                        m = Chem.AddHs(m)
                elif add_h_mode == "polar_only":
                    # Prefer RDKit's onlyOnElements if available; fallback to filtering post-add
                    try:
                        # N, O, P, S get hydrogens
                        m = Chem.AddHs(m, addCoords=add_coords, onlyOnElements=[7, 8, 15, 16])
                    except Exception:
                        try:
                            full = Chem.AddHs(m, addCoords=add_coords)
                            # Remove H on carbons
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
                        except Exception:
                            pass
                else:
                    # none
                    pass

                # Compute charges if requested
                if charge_mode == "gasteiger":
                    try:
                        AllChem.ComputeGasteigerCharges(m)
                    except Exception:
                        self.logger.warning("Gasteiger charge computation failed; continuing without charges")
                elif charge_mode == "kollman":
                    # Use AutoDockTools ReceptorPreparation to assign Kollman charges and write PDBQS,
                    # then read back into RDKit.
                    try:
                        from AutoDockTools.MoleculePreparation import ReceptorPreparation as _ADTReceptorPreparation  # type: ignore
                        from MolKit import Read as _MolKitRead  # type: ignore
                        # Stage current RDKit molecule to a temporary PDB
                        stage_dir = get_subdir("receptor_prep")
                        pdb_in = stage_dir / f"rec_{idx+1}.pdb"
                        pdbqs_out = stage_dir / f"rec_{idx+1}_kollman.pdbqs"
                        try:
                            Chem.MolToPDBFile(m, str(pdb_in))
                        except Exception:
                            # As a fallback, use block writer
                            try:
                                pdb_block = Chem.MolToPDBBlock(m)
                                pdb_in.write_text(pdb_block, encoding="utf-8")  # type: ignore[attr-defined]
                            except Exception:
                                pass
                        # Read via MolKit and run preparation
                        mols = _MolKitRead(str(pdb_in))
                        if mols and len(mols) > 0:
                            mk_mol = mols[0]
                            cleanup_parts = []
                            if remove_waters:
                                cleanup_parts.append("waters")
                            # Merge nonpolar H and lone pairs to match ADT defaults
                            cleanup_parts.append("nphs_lps")
                            if remove_nonstd:
                                cleanup_parts.append("nonstdres")
                            cleanup_str = "_".join(cleanup_parts) if cleanup_parts else ""
                            try:
                                _ADTReceptorPreparation(
                                    mk_mol,
                                    mode='automatic',
                                    repairs='checkhydrogens',
                                    charges_to_add='Kollman',
                                    cleanup=cleanup_str,
                                    outputfilename=str(pdbqs_out),
                                    debug=False,
                                )
                                # Read back into RDKit
                                try:
                                    text = pdbqs_out.read_text(encoding="utf-8", errors="ignore")  # type: ignore[attr-defined]
                                    m2 = Chem.MolFromPDBBlock(text, sanitize=True, removeHs=False)
                                    if m2 is not None:
                                        m = m2
                                except Exception:
                                    # Fallback: attempt direct PDB read API if extension mismatch
                                    try:
                                        m2 = Chem.MolFromPDBFile(str(pdbqs_out), sanitize=True, removeHs=False)
                                        if m2 is not None:
                                            m = m2
                                    except Exception:
                                        pass
                            except Exception as _e:
                                self.logger.warning(f"AutoDockTools Kollman assignment failed: {_e}")
                    except Exception as _e:
                        self.logger.warning(f"AutoDockTools not available for Kollman charges: {_e}")

                # Optional: ensure unique atom names (for downstream PDB writers/viewers)
                if bool(self.get_property("unique_atom_names")):
                    try:
                        for a in m.GetAtoms():
                            info = a.GetPDBResidueInfo()
                            if info is None:
                                continue
                            name = info.GetName() if hasattr(info, "GetName") else a.GetSymbol()
                            new_info = Chem.AtomPDBResidueInfo()
                            try:
                                new_info.SetChainId(info.GetChainId())
                                new_info.SetResidueName(info.GetResidueName())
                                new_info.SetResidueNumber(info.GetResidueNumber())
                                new_info.SetIsHetero(info.GetIsHetero())
                            except Exception:
                                pass
                            try:
                                new_info.SetName(f"{(name or a.GetSymbol()).strip()}{a.GetIdx()+1}")
                            except Exception:
                                pass
                            a.SetPDBResidueInfo(new_info)
                    except Exception:
                        pass

                # Final sanitize (best-effort)
                try:
                    Chem.SanitizeMol(m, catchErrors=True)
                except Exception:
                    pass

                out_mols.append(m)
            except Exception as e:
                self.logger.warning(f"Receptor preparation failed for molecule {idx}: {e}")
                continue

        try:
            self.report_progress(100, f"Receptor Preparation: {len(out_mols)} molecule(s) prepared")
        except Exception:
            pass

        return {"molecules": out_mols, "num_molecules": len(out_mols)}


class LigandPreparationNode(BaseNode):
    """Prepare ligand molecule for docking.

    Steps (configurable):
      - Remove salts: keep largest fragment
      - Neutralize (Uncharger)
      - Add hydrogens: none | polar_only | all
      - Embed 3D coordinates
      - Minimize (MMFF94 or UFF)
      - Compute charges: none | gasteiger

    Inputs:
      - molecule (molecule): single RDKit Mol

    Outputs:
      - molecule (molecule): prepared RDKit Mol
    """

    def __init__(self):
        super().__init__("ligand_preparation", "Ligand Preparation")
        self.logger = get_logger(__name__)

        # Ports: single molecule in/out
        self.add_input_port("molecule", "molecule")
        self.add_output_port("molecule", "molecule")

        # Properties
        self.set_property("remove_salts", True)
        self.set_property("neutralize", True)
        self.set_property("add_hydrogens_mode", "all")  # none | polar_only | all
        self.set_property("embed_3d", True)
        self.set_property("minimize", True)
        self.set_property("force_field", "MMFF94")  # MMFF94 | UFF
        self.set_property("max_iterations", 200)
        self.set_property("compute_charges", "gasteiger")  # none | gasteiger

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            from rdkit import Chem  # type: ignore
            from rdkit.Chem import AllChem  # type: ignore
            try:
                from rdkit.Chem import rdMolStandardize  # type: ignore
            except Exception:
                rdMolStandardize = None  # type: ignore
        except Exception:
            raise RuntimeError("RDKit is required for Ligand Preparation")

        if not inputs or inputs.get("molecule") is None:
            raise ValueError("Input 'molecule' is required")

        raw_val = inputs.get("molecule")
        is_list_input = isinstance(raw_val, list)
        raw_list = list(raw_val) if is_list_input else [raw_val]

        # Read properties once
        remove_salts = bool(self.get_property("remove_salts"))
        neutralize = bool(self.get_property("neutralize"))
        add_h_mode = str(self.get_property("add_hydrogens_mode") or "all").strip().lower()
        do_embed = bool(self.get_property("embed_3d"))
        do_min = bool(self.get_property("minimize"))
        ff_name = str(self.get_property("force_field") or "MMFF94").strip().upper()
        max_iter = int(self.get_property("max_iterations") or 200)
        charge_mode = str(self.get_property("compute_charges") or "gasteiger").strip().lower()

        prepared: list[Any] = []

        for idx, item in enumerate(raw_list, start=1):
            try:
                try:
                    self.report_progress(5, f"Ligand {idx}: start preparation")
                except Exception:
                    pass
                m = Chem.Mol(item) if item is not None else None
                if m is None:
                    continue

                # 1) Largest fragment (remove salts)
                if remove_salts and rdMolStandardize is not None:
                    try:
                        chooser = rdMolStandardize.LargestFragmentChooser()
                        m = chooser.choose(m)
                    except Exception:
                        pass

                # 2) Neutralize
                if neutralize and rdMolStandardize is not None:
                    try:
                        uncharger = rdMolStandardize.Uncharger()
                        m = uncharger.uncharge(m)
                    except Exception:
                        pass

                # 3) Add hydrogens
                try:
                    if add_h_mode == "all":
                        m = Chem.AddHs(m, addCoords=True)
                    elif add_h_mode == "polar_only":
                        try:
                            # Polar elements: N(7), O(8), P(15), S(16)
                            m = Chem.AddHs(m, addCoords=True, onlyOnElements=[7, 8, 15, 16])
                        except Exception:
                            # Fallback: add all then strip H on carbon
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
                    else:
                        # none
                        pass
                except Exception:
                    pass

                # 4) Embed 3D
                if do_embed:
                    try:
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
                    except Exception:
                        try:
                            AllChem.Compute2DCoords(m)
                        except Exception:
                            pass

                # 5) Minimize
                if do_min:
                    try:
                        if ff_name == "MMFF94":
                            from rdkit.Chem import rdForceFieldHelpers as FF  # type: ignore
                            mmff_props = FF.MMFFGetMoleculeProperties(m, mmffVariant="MMFF94")
                            if mmff_props is None:
                                ff = AllChem.UFFGetMoleculeForceField(m)
                            else:
                                ff = FF.MMFFGetMoleculeForceField(m, mmff_props, confId=0)
                        else:
                            ff = AllChem.UFFGetMoleculeForceField(m)
                        if ff is not None:
                            try:
                                done = 0
                                chunks = max(1, min(10, int(max_iter // 50) or 1))
                                while done < max_iter:
                                    step = min(chunks, max_iter - done)
                                    ff.Minimize(maxIts=step)
                                    done += step
                                    try:
                                        self.report_progress(30 + int(40 * done / max(1, max_iter)), f"Ligand {idx}: Minimize {done}/{max_iter}")
                                    except Exception:
                                        pass
                            except Exception:
                                ff.Minimize(maxIts=int(max_iter))
                    except Exception:
                        pass

                # 6) Charges
                if charge_mode == "gasteiger":
                    try:
                        AllChem.ComputeGasteigerCharges(m)
                    except Exception:
                        self.logger.warning("Gasteiger charge computation failed; continuing without charges")

                # Final sanitize
                try:
                    Chem.SanitizeMol(m, catchErrors=True)
                except Exception:
                    pass

                prepared.append(m)
            except Exception as e:
                self.logger.warning(f"Ligand preparation failed for entry {idx}: {e}")
                continue

        if not prepared:
            raise ValueError("No valid molecule(s) after ligand preparation")

        try:
            self.report_progress(100, f"Ligand: preparation complete ({len(prepared)})")
        except Exception:
            pass

        return {"molecule": prepared if is_list_input else prepared[0], "num_molecules": len(prepared)}
