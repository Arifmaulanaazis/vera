"""
Molecular Dynamics nodes integrating with GROMACS.
These nodes wrap common GROMACS tasks (grompp/mdrun) with simple properties.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
import re
import pandas as pd

from core.nodes import BaseNode
from utils.logging_utils import get_logger
from utils.external_tools import (
    resolve_gromacs_executable,
    build_grompp_command,
    build_mdrun_command,
)
from backend.temp_manager import get_subdir


class _BaseGromacsNode(BaseNode):
    """Common behavior for GROMACS nodes."""

    def __init__(self, node_type: str, title: str):
        super().__init__(node_type, title)
        self.logger = get_logger(__name__)
        # Common properties
        self.set_property("input_file", "")          # GRO/G96 input structure
        self.set_property("topology_file", "")       # TOP/TPR/ITP
        self.set_property("mdp_file", "")            # MDP params for grompp
        self.set_property("gromacs_version", "2025.1")
        self.set_property("use_gpu", False)
        self.set_property("threads", 0)               # 0 = auto
        self.set_property("deffnm", "run")           # default filename stem

    def _prepare_tpr(self) -> Path:
        """Run grompp to create a TPR file from mdp/top/gro."""
        gmx = resolve_gromacs_executable(self.get_property("gromacs_version"), use_gpu=None)

        mdp_file = Path(self.get_property("mdp_file"))
        structure = Path(self.get_property("input_file"))
        topology = Path(self.get_property("topology_file"))

        for f in (mdp_file, structure, topology):
            if not f or not f.exists():
                raise FileNotFoundError(f"Required file not found: {f}")

        out_dir = get_subdir("gromacs_work")
        tpr_path = out_dir / f"{self.get_property('deffnm')}.tpr"

        cmd = build_grompp_command(
            gmx=gmx,
            mdp=str(mdp_file),
            structure=str(structure),
            topology=str(topology),
            deffnm=str(out_dir / self.get_property("deffnm")),
        )

        self.logger.info(f"Running grompp: {' '.join(cmd)}")
        # Report progress: preparing TPR
        try:
            self.report_progress(-1, "Preparing TPR (grompp)")
        except Exception:
            pass
        subprocess.run(cmd, check=True, capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if not tpr_path.exists():
            raise RuntimeError("grompp did not produce a TPR file")
        # Parse expected nsteps from MDP if present (for later progress calc)
        try:
            nsteps = 0
            for line in mdp_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.strip().startswith(";") or line.strip() == "":
                    continue
                m = re.match(r"\s*nsteps\s*=\s*(-?\d+)", line)
                if m:
                    nsteps = int(m.group(1))
                    break
            try:
                self.set_property("_md_expected_nsteps", nsteps)
            except Exception:
                pass
        except Exception:
            try:
                self.set_property("_md_expected_nsteps", 0)
            except Exception:
                pass
        try:
            self.report_progress(40, "TPR ready")
        except Exception:
            pass
        return tpr_path

    def _run_mdrun(self) -> Dict[str, Any]:
        """Run mdrun using deffnm and GPU/threads settings."""
        gmx = resolve_gromacs_executable(self.get_property("gromacs_version"), use_gpu=bool(self.get_property("use_gpu")))
        deffnm = self.get_property("deffnm")
        out_dir = get_subdir("gromacs_work")

        cmd = build_mdrun_command(
            gmx=gmx,
            deffnm=str(out_dir / deffnm),
            use_gpu=bool(self.get_property("use_gpu")),
            threads=int(self.get_property("threads")),
        )
        # Ensure verbose output for better realtime step reporting
        try:
            if "-v" not in cmd:
                try:
                    idx = cmd.index("mdrun")
                    cmd.insert(idx + 1, "-v")
                except Exception:
                    cmd.append("-v")
        except Exception:
            pass
        self.logger.info(f"Running mdrun: {' '.join(cmd)}")
        try:
            self.report_progress(50, "Running MD (mdrun)")
        except Exception:
            pass
        # Stream stdout to capture progress
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            self.register_subprocess(proc)
        except Exception:
            pass
        last_step = 0
        try:
            expected = int(self.get_property("_md_expected_nsteps") or 0)
        except Exception:
            expected = 0
        step_re = re.compile(r"\b[Ss]tep\s+(\d+)")
        percent_re = re.compile(r"(\d{1,3})%")
        log_lines: list[str] = []
        while True:
            line = proc.stdout.readline() if proc.stdout else ""
            if not line:
                if proc.poll() is not None:
                    break
                continue
            log_lines.append(line)
            s = line.strip()
            # Percent pattern
            mperc = percent_re.search(s)
            if mperc:
                try:
                    pv = int(mperc.group(1))
                    if 0 <= pv <= 100:
                        self.report_progress(pv, s)
                        continue
                except Exception:
                    pass
            # Step pattern
            m = step_re.search(s)
            if m:
                try:
                    st = int(m.group(1))
                    if st > last_step:
                        last_step = st
                        if expected > 0:
                            pct = max(50, min(99, int(50 + (st / expected) * 49)))
                            self.report_progress(pct, f"Step {st}/{expected}")
                        else:
                            self.report_progress(-1, f"Step {st}")
                except Exception:
                    pass
        ret = proc.wait()
        try:
            self.unregister_subprocess(proc)
        except Exception:
            pass
        if ret != 0:
            tail = "".join(log_lines[-50:])
            raise RuntimeError(f"mdrun failed with code {ret}. Last output:\n{tail}")
        try:
            self.report_progress(100, "MD run completed")
        except Exception:
            pass
        log_file = out_dir / f"{deffnm}.log"
        edr_file = out_dir / f"{deffnm}.edr"
        trr_file = out_dir / f"{deffnm}.trr"
        gro_file = out_dir / f"{deffnm}.gro"
        return {
            "log_file": str(log_file) if log_file.exists() else None,
            "edr_file": str(edr_file) if edr_file.exists() else None,
            "trr_file": str(trr_file) if log_file.exists() else None,
            "structure_file": str(gro_file) if gro_file.exists() else None,
            "stdout": "",
            "stderr": "",
        }


class GromacsPreparationNode(_BaseGromacsNode):
    """Prepare TPR using provided MDP, structure (GRO), and topology (TOP)."""

    def __init__(self):
        super().__init__("gromacs_prep", "GROMACS Preparation")
        self.add_input_port("input_file", "file")
        self.add_input_port("topology_file", "file")
        self.add_input_port("mdp_file", "file")
        self.add_output_port("tpr_file", "file")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if inputs:
            for key in ("input_file", "topology_file", "mdp_file"):
                if key in inputs and inputs[key]:
                    self.set_property(key, inputs[key])
        tpr = self._prepare_tpr()
        return {"tpr_file": str(tpr)}


class GromacsMinimizeNode(BaseNode):
    """GROMACS Energy Minimization for CHARMM-GUI workflow.
    Performs energy minimization using optimized GPU settings.
    """

    def __init__(self):
        super().__init__("gromacs_minimize", "GROMACS Minimization")
        self.logger = get_logger(__name__)  
        self.add_input_port("gro_file", "file")
        self.add_input_port("top_file", "file")
        self.add_input_port("mdp_file", "file")
        self.add_input_port("index_file", "file")
        self.add_output_port("gro_file", "file")
        self.add_output_port("log_file", "file")
        self.add_output_port("tpr_file", "file")
        self.add_output_port("edr_file", "file")
        
        self.set_property("gromacs_version", "2025.1")
        self.set_property("use_gpu", True)
        self.set_property("maxwarn", 1)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        gro_file = inputs.get("gro_file") if inputs else None
        top_file = inputs.get("top_file") if inputs else None
        mdp_file = inputs.get("mdp_file") if inputs else None
        index_file = inputs.get("index_file") if inputs else None
        
        if not all([gro_file, top_file, mdp_file]):
            raise ValueError("Missing required input files")
        
        out_dir = get_subdir("gromacs_minimization")
        gmx = resolve_gromacs_executable(
            self.get_property("gromacs_version"),
            use_gpu=bool(self.get_property("use_gpu"))
        )
        
        # Step 1: grompp
        tpr_file = out_dir / "step4.0_minimization.tpr"
        cmd_grompp = [
            gmx, "grompp",
            "-f", str(mdp_file),
            "-o", str(tpr_file),
            "-c", str(gro_file),
            "-r", str(gro_file),
            "-p", str(top_file),
            "-maxwarn", str(self.get_property("maxwarn"))
        ]
        if index_file:
            cmd_grompp.extend(["-n", str(index_file)])
        
        try:
            self.report_progress(10, "Preparing minimization TPR...")
            subprocess.run(cmd_grompp, check=True, capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            
            # Step 2: mdrun
            self.report_progress(30, "Running energy minimization...")
            prefix = out_dir / "step4.0_minimization"
            
            cmd_mdrun = [
                gmx, "mdrun",
                "-v",
                "-deffnm", str(prefix)
            ]
            
            # Run mdrun with progress monitoring
            proc = subprocess.Popen(
                cmd_mdrun,
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
            
            # Monitor progress
            while True:
                line = proc.stdout.readline() if proc.stdout else ""
                if not line:
                    if proc.poll() is not None:
                        break
                    continue
                
                # Look for step progress
                if "step" in line.lower():
                    try:
                        import re
                        step_match = re.search(r"step[\s=]+(\d+)", line, re.IGNORECASE)
                        if step_match:
                            step = int(step_match.group(1))
                            # Estimate progress (minimization typically converges quickly)
                            progress = min(30 + (step // 10), 90)
                            self.report_progress(progress, f"Minimization step {step}")
                    except Exception:
                        pass
            
            ret = proc.wait()
            try:
                self.unregister_subprocess(proc)
            except Exception:
                pass
            
            if ret != 0:
                raise RuntimeError(f"mdrun failed with code {ret}")
            
            self.report_progress(100, "Minimization completed")
            
            # Return output files
            gro_out = out_dir / "step4.0_minimization.gro"
            log_out = out_dir / "step4.0_minimization.log"
            edr_out = out_dir / "step4.0_minimization.edr"
            
            return {
                "gro_file": str(gro_out) if gro_out.exists() else None,
                "log_file": str(log_out) if log_out.exists() else None,
                "tpr_file": str(tpr_file) if tpr_file.exists() else None,
                "edr_file": str(edr_out) if edr_out.exists() else None,
            }
            
        except Exception as e:
            self.logger.error(f"Minimization failed: {e}")
            raise


class GromacsEquilibrateNode(BaseNode):
    """GROMACS Equilibration for CHARMM-GUI workflow.
    Performs NVT/NPT equilibration using optimized GPU settings.
    """

    def __init__(self):
        super().__init__("gromacs_equilibrate", "GROMACS Equilibration")
        self.logger = get_logger(__name__)
        self.add_input_port("gro_file", "file")  # From minimization
        self.add_input_port("gro_ref", "file")   # Reference structure (step3_input.gro)
        self.add_input_port("top_file", "file")
        self.add_input_port("mdp_file", "file")
        self.add_input_port("index_file", "file")
        self.add_output_port("gro_file", "file")
        self.add_output_port("log_file", "file")
        self.add_output_port("tpr_file", "file")
        self.add_output_port("edr_file", "file")
        
        self.set_property("gromacs_version", "2025.1")
        self.set_property("use_gpu", True)
        self.set_property("maxwarn", 1)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        gro_file = inputs.get("gro_file") if inputs else None
        gro_ref = inputs.get("gro_ref") if inputs else None
        top_file = inputs.get("top_file") if inputs else None
        mdp_file = inputs.get("mdp_file") if inputs else None
        index_file = inputs.get("index_file") if inputs else None
        
        # Use input gro as reference if not provided
        if not gro_ref:
            gro_ref = gro_file
        
        if not all([gro_file, top_file, mdp_file]):
            raise ValueError("Missing required input files")
        
        out_dir = get_subdir("gromacs_equilibration")
        gmx = resolve_gromacs_executable(
            self.get_property("gromacs_version"),
            use_gpu=bool(self.get_property("use_gpu"))
        )
        
        # Step 1: grompp
        tpr_file = out_dir / "step4.1_equilibration.tpr"
        cmd_grompp = [
            gmx, "grompp",
            "-f", str(mdp_file),
            "-o", str(tpr_file),
            "-c", str(gro_file),
            "-r", str(gro_ref),
            "-p", str(top_file),
            "-maxwarn", str(self.get_property("maxwarn"))
        ]
        if index_file:
            cmd_grompp.extend(["-n", str(index_file)])
        
        try:
            self.report_progress(10, "Preparing equilibration TPR...")
            subprocess.run(cmd_grompp, check=True, capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            
            # Parse nsteps from MDP for progress tracking
            nsteps = 0
            try:
                with open(mdp_file, 'r') as f:
                    for line in f:
                        if line.strip().startswith('nsteps'):
                            _, value = line.split('=', 1)
                            nsteps = int(value.strip())
                            break
            except Exception:
                pass
            
            # Step 2: mdrun
            self.report_progress(20, "Running equilibration...")
            prefix = out_dir / "step4.1_equilibration"
            
            cmd_mdrun = [
                gmx, "mdrun",
                "-v",
                "-deffnm", str(prefix)
            ]
            
            # Run mdrun with progress monitoring
            proc = subprocess.Popen(
                cmd_mdrun,
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
            
            # Monitor progress
            last_step = 0
            while True:
                line = proc.stdout.readline() if proc.stdout else ""
                if not line:
                    if proc.poll() is not None:
                        break
                    continue
                
                # Look for step progress
                if "step" in line.lower():
                    try:
                        import re
                        step_match = re.search(r"step[\s=]+(\d+)", line, re.IGNORECASE)
                        if step_match:
                            step = int(step_match.group(1))
                            if step > last_step:
                                last_step = step
                                if nsteps > 0:
                                    progress = min(20 + int((step / nsteps) * 70), 90)
                                    self.report_progress(progress, f"Equilibration step {step}/{nsteps}")
                                else:
                                    self.report_progress(-1, f"Equilibration step {step}")
                    except Exception:
                        pass
            
            ret = proc.wait()
            try:
                self.unregister_subprocess(proc)
            except Exception:
                pass
            
            if ret != 0:
                raise RuntimeError(f"mdrun failed with code {ret}")
            
            self.report_progress(100, "Equilibration completed")
            
            # Return output files
            gro_out = out_dir / "step4.1_equilibration.gro"
            log_out = out_dir / "step4.1_equilibration.log"
            edr_out = out_dir / "step4.1_equilibration.edr"
            
            return {
                "gro_file": str(gro_out) if gro_out.exists() else None,
                "log_file": str(log_out) if log_out.exists() else None,
                "tpr_file": str(tpr_file) if tpr_file.exists() else None,
                "edr_file": str(edr_out) if edr_out.exists() else None,
            }
            
        except Exception as e:
            self.logger.error(f"Equilibration failed: {e}")
            raise


class GromacsProductionNode(BaseNode):
    """GROMACS Production MD for CHARMM-GUI workflow.
    Performs production MD simulation with optimized GPU settings.
    """

    def __init__(self):
        super().__init__("gromacs_production", "GROMACS Production")
        self.logger = get_logger(__name__)
        self.add_input_port("gro_file", "file")  # From equilibration
        self.add_input_port("top_file", "file")
        self.add_input_port("mdp_file", "file")
        self.add_input_port("index_file", "file")
        self.add_input_port("cpt_file", "file")  # Optional checkpoint for continuation
        self.add_output_port("gro_file", "file")
        self.add_output_port("xtc_file", "file")
        self.add_output_port("tpr_file", "file")
        self.add_output_port("edr_file", "file")
        self.add_output_port("log_file", "file")
        self.add_output_port("cpt_file", "file")
        
        self.set_property("gromacs_version", "2025.1")
        self.set_property("use_gpu", True)
        self.set_property("nsteps", 250000)  # Default 1ns with dt=0.004
        self.set_property("nstlist", 300)  # GPU optimized
        self.set_property("continuation", False)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        gro_file = inputs.get("gro_file") if inputs else None
        top_file = inputs.get("top_file") if inputs else None
        mdp_file = inputs.get("mdp_file") if inputs else None
        index_file = inputs.get("index_file") if inputs else None
        cpt_file = inputs.get("cpt_file") if inputs else None
        
        if not all([gro_file, top_file, mdp_file]):
            raise ValueError("Missing required input files")
        
        out_dir = get_subdir("gromacs_production")
        gmx = resolve_gromacs_executable(
            self.get_property("gromacs_version"),
            use_gpu=bool(self.get_property("use_gpu"))
        )
        
        # Check if this is a continuation run
        is_continuation = bool(cpt_file and Path(cpt_file).exists())
        
        # Step 1: grompp (if not continuation)
        tpr_file = out_dir / "step5_1.tpr"
        if not is_continuation:
            cmd_grompp = [
                gmx, "grompp",
                "-f", str(mdp_file),
                "-o", str(tpr_file),
                "-c", str(gro_file),
                "-p", str(top_file)
            ]
            if index_file:
                cmd_grompp.extend(["-n", str(index_file)])
            
            try:
                self.report_progress(5, "Preparing production TPR...")
                subprocess.run(cmd_grompp, check=True, capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except Exception as e:
                self.logger.error(f"grompp failed: {e}")
                raise
        
        # Get nsteps for progress tracking
        nsteps = self.get_property("nsteps")
        nstlist = self.get_property("nstlist")
        
        # Step 2: mdrun with GPU optimization
        self.report_progress(10, "Starting production MD...")
        prefix = out_dir / "step5_1"
        
        # Build mdrun command with GPU optimization
        cmd_mdrun = [
            gmx, "mdrun",
            "-v",
            "-deffnm", str(prefix),
            "-nb", "gpu",
            "-bonded", "gpu",
            "-gpu_id", "0",
            "-pme", "gpu",
            "-pin", "on",
            "-pinoffset", "0",
            "-pinstride", "1",
            "-pmefft", "gpu",
            "-nstlist", str(nstlist),
            "-nsteps", str(nsteps)
        ]
        
        # Add continuation flags if needed
        if is_continuation:
            cmd_mdrun.extend(["-cpi", str(cpt_file), "-append"])
        
        try:
            # Run mdrun with progress monitoring
            proc = subprocess.Popen(
                cmd_mdrun,
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
            
            # Monitor progress
            last_step = 0
            while True:
                line = proc.stdout.readline() if proc.stdout else ""
                if not line:
                    if proc.poll() is not None:
                        break
                    continue
                
                # Look for step progress or percentage
                if "%" in line:
                    try:
                        import re
                        percent_match = re.search(r"(\d{1,3})%", line)
                        if percent_match:
                            percent = int(percent_match.group(1))
                            self.report_progress(min(10 + percent * 0.85, 95), f"Production MD {percent}%")
                    except Exception:
                        pass
                elif "step" in line.lower():
                    try:
                        import re
                        step_match = re.search(r"step[\s=]+(\d+)", line, re.IGNORECASE)
                        if step_match:
                            step = int(step_match.group(1))
                            if step > last_step:
                                last_step = step
                                progress = min(10 + int((step / nsteps) * 85), 95)
                                self.report_progress(progress, f"Production step {step}/{nsteps}")
                    except Exception:
                        pass
            
            ret = proc.wait()
            try:
                self.unregister_subprocess(proc)
            except Exception:
                pass
            
            if ret != 0:
                raise RuntimeError(f"mdrun failed with code {ret}")
            
            self.report_progress(100, "Production MD completed")
            
            # Return output files
            gro_out = out_dir / "step5_1.gro"
            xtc_out = out_dir / "step5_1.xtc"
            tpr_out = tpr_file
            edr_out = out_dir / "step5_1.edr"
            log_out = out_dir / "step5_1.log"
            cpt_out = out_dir / "step5_1.cpt"
            
            return {
                "gro_file": str(gro_out) if gro_out.exists() else None,
                "xtc_file": str(xtc_out) if xtc_out.exists() else None,
                "tpr_file": str(tpr_out) if tpr_out.exists() else None,
                "edr_file": str(edr_out) if edr_out.exists() else None,
                "log_file": str(log_out) if log_out.exists() else None,
                "cpt_file": str(cpt_out) if cpt_out.exists() else None,
            }
            
        except Exception as e:
            self.logger.error(f"Production MD failed: {e}")
            raise


class MDAnalysisNode(BaseNode):
    """GROMACS analysis node for MD trajectories.
    Performs various analyses like RMSD, RMSF, Gyration, SASA, H-bonds, Energy.
    """

    def __init__(self):
        super().__init__("gromacs_analysis", "GROMACS Analysis")
        self.logger = get_logger(__name__)
        self.add_input_port("tpr_file", "file")
        self.add_input_port("xtc_file", "file")
        self.add_input_port("edr_file", "file")
        self.add_output_port("analysis_folder", "string")

        # Dataframe outputs (ready for plotting)
        self.add_output_port("rmsd", "data")
        self.add_output_port("rmsd_protein_ligand", "data")
        self.add_output_port("rmsf_atom", "data")
        self.add_output_port("rmsf_residue", "data")
        self.add_output_port("radius_of_gyration", "data")
        self.add_output_port("sasa", "data")
        self.add_output_port("hydrogen_bonds", "data")
        self.add_output_port("potential_energy", "data")

        # Properties for analysis types
        self.set_property("do_rmsd", True)
        self.set_property("do_rmsd_protein_ligand", True)
        self.set_property("do_rmsf", True)
        self.set_property("do_rmsf_residue", True)
        self.set_property("do_gyration", True)
        self.set_property("do_sasa", True)
        self.set_property("do_hbond", True)
        self.set_property("do_energy", True)
        self.set_property("gromacs_version", "2025.1")
        self.set_property("use_gpu", False)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        tpr_path = inputs.get("tpr_file") if inputs else None
        xtc_path = inputs.get("xtc_file") if inputs else None
        edr_path = inputs.get("edr_file") if inputs else None

        if not tpr_path or not Path(tpr_path).exists():
            raise FileNotFoundError(f"TPR file not found: {tpr_path}")
        if not xtc_path or not Path(xtc_path).exists():
            raise FileNotFoundError(f"XTC file not found: {xtc_path}")

        out_dir = get_subdir("gromacs_analysis")
        gmx = resolve_gromacs_executable(self.get_property("gromacs_version"), 
                                        use_gpu=bool(self.get_property("use_gpu")))

        results: Dict[str, Any] = {}

        def _read_xvg_numeric(xvg_path: Path) -> pd.DataFrame:
            rows: list[list[float]] = []
            with open(xvg_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith("#") or s.startswith("@"):
                        continue
                    parts = s.split()
                    try:
                        vals = [float(p) for p in parts]
                    except Exception:
                        continue
                    if len(vals) >= 2:
                        rows.append(vals)
            if not rows:
                return pd.DataFrame()
            max_cols = max(len(r) for r in rows)
            for r in rows:
                if len(r) < max_cols:
                    r.extend([float("nan")] * (max_cols - len(r)))
            df = pd.DataFrame(rows)
            df.columns = [f"col{i+1}" for i in range(df.shape[1])]
            return df
        
        try:
            # RMSD analysis - backbone (group 4)
            if self.get_property("do_rmsd"):
                self.report_progress(10, "Running RMSD analysis...")
                rmsd_file = out_dir / "rmsd.xvg"
                cmd = [gmx, "rms", "-s", str(tpr_path), "-f", str(xtc_path), 
                      "-o", str(rmsd_file), "-tu", "ns"]
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, 
                                      stderr=subprocess.PIPE, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                stdout, stderr = proc.communicate("4\n4\n")  # Select backbone twice
                if proc.returncode == 0:
                    df = _read_xvg_numeric(rmsd_file)
                    if not df.empty:
                        if df.shape[1] >= 2:
                            df = df.rename(columns={"col1": "time_ns", "col2": "rmsd_nm"})
                        results["rmsd"] = df

            # RMSD Protein-Ligand (groups 1 and 13)
            if self.get_property("do_rmsd_protein_ligand"):
                self.report_progress(18, "Running RMSD Protein-Ligand analysis...")
                rmsd_pl_file = out_dir / "rmsd_protein_ligand.xvg"
                cmd = [gmx, "rms", "-s", str(tpr_path), "-f", str(xtc_path),
                       "-o", str(rmsd_pl_file), "-tu", "ns"]
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                stdout, stderr = proc.communicate("1\n13\n")  # Protein and ligand
                if proc.returncode == 0:
                    df = _read_xvg_numeric(rmsd_pl_file)
                    if not df.empty:
                        if df.shape[1] >= 2:
                            df = df.rename(columns={"col1": "time_ns", "col2": "rmsd_nm"})
                        results["rmsd_protein_ligand"] = df

            # RMSF analysis - per atom
            if self.get_property("do_rmsf"):
                self.report_progress(25, "Running RMSF analysis...")
                rmsf_file = out_dir / "rmsf_atom.xvg"
                cmd = [gmx, "rmsf", "-s", str(tpr_path), "-f", str(xtc_path),
                      "-o", str(rmsf_file)]
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                stdout, stderr = proc.communicate("4\n")  # Select backbone
                if proc.returncode == 0:
                    df = _read_xvg_numeric(rmsf_file)
                    if not df.empty:
                        if df.shape[1] >= 2:
                            df = df.rename(columns={"col1": "atom_index", "col2": "rmsf_nm"})
                        results["rmsf_atom"] = df

            # RMSF analysis - per residue
            if self.get_property("do_rmsf_residue"):
                self.report_progress(32, "Running RMSF Residue analysis...")
                rmsf_res_file = out_dir / "rmsf_residue.xvg"
                cmd = [gmx, "rmsf", "-s", str(tpr_path), "-f", str(xtc_path),
                       "-res", "-o", str(rmsf_res_file)]
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                stdout, stderr = proc.communicate("4\n")  # Select backbone
                if proc.returncode == 0:
                    df = _read_xvg_numeric(rmsf_res_file)
                    if not df.empty:
                        if df.shape[1] >= 2:
                            df = df.rename(columns={"col1": "residue", "col2": "rmsf_nm"})
                        results["rmsf_residue"] = df

            # Gyration radius
            if self.get_property("do_gyration"):
                self.report_progress(40, "Running gyration analysis...")
                gyr_file = out_dir / "gyration.xvg"
                cmd = [gmx, "gyrate", "-s", str(tpr_path), "-f", str(xtc_path),
                      "-o", str(gyr_file)]
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                stdout, stderr = proc.communicate("4\n")  # Select backbone
                if proc.returncode == 0:
                    df = _read_xvg_numeric(gyr_file)
                    if not df.empty:
                        rename_map = {"col1": "time_ps", "col2": "Rg"}
                        if df.shape[1] >= 3:
                            rename_map["col3"] = "RgX"
                        if df.shape[1] >= 4:
                            rename_map["col4"] = "RgY"
                        if df.shape[1] >= 5:
                            rename_map["col5"] = "RgZ"
                        df = df.rename(columns=rename_map)
                        results["radius_of_gyration"] = df

            # SASA analysis
            if self.get_property("do_sasa"):
                self.report_progress(55, "Running SASA analysis...")
                sasa_file = out_dir / "sasa.xvg"
                cmd = [gmx, "sasa", "-s", str(tpr_path), "-f", str(xtc_path),
                      "-o", str(sasa_file)]
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                stdout, stderr = proc.communicate("4\n")  # Select backbone
                if proc.returncode == 0:
                    df = _read_xvg_numeric(sasa_file)
                    if not df.empty:
                        rename_map = {"col1": "time_ps", "col2": "SASA_nm2"}
                        for i in range(3, df.shape[1] + 1):
                            rename_map[f"col{i}"] = f"SASA_component_{i-2}"
                        df = df.rename(columns=rename_map)
                        results["sasa"] = df

            # H-bond analysis - protein and ligand (groups 1 and 13)
            if self.get_property("do_hbond"):
                self.report_progress(70, "Running H-bond analysis...")
                hbond_file = out_dir / "hbond.xvg"
                cmd = [gmx, "hbond", "-s", str(tpr_path), "-f", str(xtc_path),
                      "-num", str(hbond_file)]
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                stdout, stderr = proc.communicate("1\n13\n")  # Protein and ligand
                if proc.returncode == 0:
                    df = _read_xvg_numeric(hbond_file)
                    if not df.empty:
                        if df.shape[1] >= 2:
                            df = df.rename(columns={"col1": "time_ps", "col2": "num_hbonds"})
                        results["hydrogen_bonds"] = df

            # Energy analysis (potential)
            if self.get_property("do_energy") and edr_path and Path(edr_path).exists():
                self.report_progress(85, "Running energy analysis...")
                energy_file = out_dir / "potential_energy.xvg"
                cmd = [gmx, "energy", "-f", str(edr_path), "-o", str(energy_file)]
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                stdout, stderr = proc.communicate("11\n")  # Select Potential
                if proc.returncode == 0:
                    df = _read_xvg_numeric(energy_file)
                    if not df.empty:
                        if df.shape[1] >= 2:
                            df = df.rename(columns={"col1": "time_ps", "col2": "potential_kJ_per_mol"})
                        results["potential_energy"] = df

            self.report_progress(100, "Analysis completed")
            results["analysis_folder"] = str(out_dir)

        except Exception as e:
            self.logger.error(f"Analysis failed: {e}")
            raise

        return results


class GromacsPlotingNode(BaseNode):
    """
    Minimal inline plotting node for GROMACS analysis outputs.

    Inputs (dataframes from GROMACS Analysis):
      - rmsd
      - rmsd_protein_ligand
      - rmsf_atom
      - rmsf_residue
      - radius_of_gyration
      - sasa
      - hydrogen_bonds
      - potential_energy

    UI: Combobox (select which connected input to plot), 'View' button, and image area below.
    The combobox only lists inputs that currently have data.
    """

    def __init__(self):
        super().__init__("gromacs_ploting", "GROMACS Plotting")
        self.logger = get_logger(__name__)

        # Eight dataframe inputs mirroring gromacs_analysis outputs
        self.add_input_port("rmsd", "data")
        self.add_input_port("rmsd_protein_ligand", "data")
        self.add_input_port("rmsf_atom", "data")
        self.add_input_port("rmsf_residue", "data")
        self.add_input_port("radius_of_gyration", "data")
        self.add_input_port("sasa", "data")
        self.add_input_port("hydrogen_bonds", "data")
        self.add_input_port("potential_energy", "data")

        # Visual size
        self.width = 360
        self.height = 280
        try:
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)
            # Tighter margins to maximize image area
            self.set_content_margins(8, 48, 8, 8)
        except Exception:
            pass

        # Inline UI: [Combo] [Color] [View] on top row, image label below
        try:
            from PySide6.QtWidgets import QComboBox, QPushButton, QLabel, QSizePolicy, QSpacerItem, QColorDialog
            from PySide6.QtCore import Qt, QObject, Signal, QThread

            self._combo = QComboBox()
            self._combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            try:
                self._combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            except Exception:
                pass

            self._btn_view = QPushButton("View")
            try:
                self._btn_view.clicked.connect(self._on_view_clicked)
            except Exception:
                pass

            # Color selector button
            self._btn_color = QPushButton()
            try:
                self._btn_color.setFixedWidth(28)
                self._btn_color.setToolTip("Pick plot color")
            except Exception:
                pass
            # Default plot color
            try:
                if not self.get_property("plot_color"):
                    self.set_property("plot_color", "#4169e1")  # royalblue
            except Exception:
                pass
            try:
                def _pick_color():
                    try:
                        col = QColorDialog.getColor()
                        if col and col.isValid():
                            self.set_property("plot_color", col.name())
                            self._update_color_button_style()
                    except Exception:
                        pass
                self._btn_color.clicked.connect(_pick_color)
            except Exception:
                pass

            self._img = QLabel()
            self._img.setAlignment(Qt.AlignCenter)
            try:
                self._img.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                self._img.setStyleSheet("QLabel { background-color: rgba(40,40,40,100); border: 1px solid #666; border-radius: 4px; color: #ccc; }")
                self._img.setText("No plot")
            except Exception:
                pass

            layout = self.content_layout
            if layout is not None:
                # Top controls
                layout.addWidget(self._combo, 0, 0)
                layout.addWidget(self._btn_color, 0, 1, alignment=Qt.AlignLeft)
                layout.addWidget(self._btn_view, 0, 2, alignment=Qt.AlignLeft)
                # Make controls responsive
                try:
                    layout.setColumnStretch(0, 1)
                    layout.setColumnStretch(1, 0)
                    layout.setColumnStretch(2, 0)
                    layout.setRowStretch(1, 1)
                except Exception:
                    pass
                # Plot area
                layout.addWidget(self._img, 1, 0, 1, 3)

            # Populate initial options
            self._refresh_combo_items()
            self._update_color_button_style()
            # Align ports after custom content
            self._update_port_positions()

            # Async rendering members
            self._render_thread = None
            self._render_worker = None
        except Exception:
            self._combo = None
            self._btn_view = None
            self._btn_color = None
            self._img = None

    # Map friendly labels to input port keys
    _LABEL_TO_PORT = {
        "RMSD": "rmsd",
        "RMSD Protein-Ligand": "rmsd_protein_ligand",
        "RMSF Atom": "rmsf_atom",
        "RMSF Residue": "rmsf_residue",
        "Radius of Gyration": "radius_of_gyration",
        "SASA": "sasa",
        "Hydrogen Bonds": "hydrogen_bonds",
        "Potential Energy": "potential_energy",
    }

    def _available_inputs(self) -> dict[str, object]:
        """Return mapping of port_key -> dataframe-like for ports that currently have data."""
        available: dict[str, object] = {}
        for _label, port_key in self._LABEL_TO_PORT.items():
            val = self.properties.get(f"last_input_{port_key}")
            if val is None:
                continue
            try:
                # Accept pandas DataFrame or list-of-dicts non-empty
                if hasattr(val, "empty"):
                    if not bool(val.empty):
                        available[port_key] = val
                elif isinstance(val, list):
                    if len(val) == 0 or isinstance(val[0], dict):
                        if len(val) > 0:
                            available[port_key] = val
                elif isinstance(val, dict):
                    if len(val) > 0:
                        available[port_key] = val
            except Exception:
                # Be permissive: include if truthy
                try:
                    if val:
                        available[port_key] = val
                except Exception:
                    pass
        return available

    def _refresh_combo_items(self) -> None:
        try:
            if self._combo is None:
                return
            self._combo.clear()
            avail = self._available_inputs()
            # Add items using friendly labels, only for available ports
            for label, port in self._LABEL_TO_PORT.items():
                if port in avail:
                    self._combo.addItem(label, userData=port)
            if self._combo.count() == 0:
                self._combo.addItem("(no data)", userData=None)
        except Exception:
            pass

    def _update_color_button_style(self) -> None:
        try:
            if self._btn_color is None:
                return
            col = self.get_property("plot_color") or "#4169e1"
            # Show color as button background
            self._btn_color.setStyleSheet(f"QPushButton {{ background-color: {col}; border: 1px solid #666; }}")
        except Exception:
            pass

    def _on_view_clicked(self) -> None:
        try:
            if self._combo is None or self._img is None:
                return
            port_key = self._combo.currentData()
            if not port_key:
                return
            data_obj = self._available_inputs().get(port_key)
            if data_obj is None:
                return
            self._start_async_render(port_key, data_obj)
        except Exception:
            pass

    def _start_async_render(self, port_key: str, data_obj: object) -> None:
        """Render plot in background thread to avoid UI freeze."""
        try:
            from PySide6.QtCore import QObject, Signal, QThread
        except Exception:
            # Fallback to sync
            try:
                img_bytes = self._render_plot_bytes(port_key, data_obj)
                self._last_image_bytes = img_bytes
                self._set_image(img_bytes)
            except Exception:
                pass
            return

        class _PlotRenderWorker(QObject):  # type: ignore[misc]
            finished = Signal(bytes)
            failed = Signal(str)
            def __init__(self, outer: 'GromacsPlotingNode', key: str, obj: object):
                super().__init__()
                self._outer = outer
                self._key = key
                self._obj = obj
            def run(self) -> None:
                try:
                    data = self._outer._render_plot_bytes(self._key, self._obj)
                    self.finished.emit(data)
                except Exception as e:  # pragma: no cover - best-effort
                    self.failed.emit(str(e))

        try:
            # Show busy state
            if self._img is not None:
                try:
                    self._img.setText("Rendering…")
                except Exception:
                    pass
            if self._btn_view is not None:
                try:
                    self._btn_view.setEnabled(False)
                except Exception:
                    pass

            # Clean previous thread if any
            try:
                if getattr(self, "_render_thread", None) is not None:
                    try:
                        self._render_thread.quit()
                        self._render_thread.wait(50)
                    except Exception:
                        pass
            except Exception:
                pass

            thread = QThread()
            worker = _PlotRenderWorker(self, port_key, data_obj)
            worker.moveToThread(thread)
            try:
                thread.started.connect(worker.run)
            except Exception:
                pass

            def _on_done(data: bytes) -> None:
                try:
                    self._last_image_bytes = data
                except Exception:
                    pass
                self._set_image(data)
                try:
                    self._btn_view.setEnabled(True)
                except Exception:
                    pass
                try:
                    thread.quit()
                except Exception:
                    pass

            def _on_fail(_msg: str) -> None:
                try:
                    self._img.setText("Failed to render")
                except Exception:
                    pass
                try:
                    self._btn_view.setEnabled(True)
                except Exception:
                    pass
                try:
                    thread.quit()
                except Exception:
                    pass

            try:
                worker.finished.connect(_on_done)
                worker.failed.connect(_on_fail)
            except Exception:
                pass

            # Keep refs
            self._render_thread = thread
            self._render_worker = worker
            thread.start()
        except Exception:
            # Fallback to sync if threading fails
            try:
                img_bytes = self._render_plot_bytes(port_key, data_obj)
                self._last_image_bytes = img_bytes
                self._set_image(img_bytes)
            except Exception:
                pass

    def _render_plot_bytes(self, port_key: str, data_obj: object) -> bytes:
        """Create a PNG plot for the given dataset and return image bytes."""
        import io
        try:
            from utils.mpl_utils import import_pyplot_non_interactive
            plt = import_pyplot_non_interactive()
        except Exception:
            try:
                import matplotlib.pyplot as plt  # type: ignore
            except Exception:
                return b""

        # Normalize to pandas DataFrame when possible
        df = None
        try:
            import pandas as pd  # type: ignore
            if hasattr(data_obj, "empty"):
                df = data_obj
            elif isinstance(data_obj, list):
                df = pd.DataFrame(data_obj)
            elif isinstance(data_obj, dict):
                df = pd.DataFrame(data_obj)
        except Exception:
            df = None

        plt.figure(figsize=(4.8, 3.2))

        def _plot_xy(xcol: str, ycol: str, title: str, x_label: str, y_label: str):
            try:
                color = self.get_property("plot_color") or "#4169e1"
                plt.plot(df[xcol], df[ycol], color=color, linewidth=1.8)
                plt.xlabel(x_label)
                plt.ylabel(y_label)
                plt.title(title)
            except Exception:
                # Fallback to first two numeric columns
                try:
                    num_cols = [c for c in df.columns if str(c).strip()]
                    if len(num_cols) >= 2:
                        color = self.get_property("plot_color") or "#4169e1"
                        plt.plot(df[num_cols[0]], df[num_cols[1]], color=color, linewidth=1.8)
                        plt.xlabel(x_label or str(num_cols[0]))
                        plt.ylabel(y_label or str(num_cols[1]))
                        plt.title(title)
                except Exception:
                    pass

        try:
            if df is None or getattr(df, "empty", False):
                plt.text(0.5, 0.5, "No data", ha="center", va="center")
            else:
                key = port_key
                if key == "rmsd":
                    _plot_xy("time_ns", "rmsd_nm", "RMSD", "Time (ns)", "RMSD (nm)")
                elif key == "rmsd_protein_ligand":
                    _plot_xy("time_ns", "rmsd_nm", "RMSD Protein-Ligand", "Time (ns)", "RMSD (nm)")
                elif key == "rmsf_atom":
                    _plot_xy("atom_index", "rmsf_nm", "RMSF (Atom)", "Atom Index", "RMSF (nm)")
                elif key == "rmsf_residue":
                    _plot_xy("residue", "rmsf_nm", "RMSF (Residue)", "Residue", "RMSF (nm)")
                elif key == "radius_of_gyration":
                    _plot_xy("time_ps", "Rg", "Radius of Gyration", "Time (ps)", "Rg (nm)")
                elif key == "sasa":
                    _plot_xy("time_ps", "SASA_nm2", "SASA", "Time (ps)", "SASA (nm^2)")
                elif key == "hydrogen_bonds":
                    _plot_xy("time_ps", "num_hbonds", "Hydrogen Bonds", "Time (ps)", "Number of H-bonds")
                elif key == "potential_energy":
                    _plot_xy("time_ps", "potential_kJ_per_mol", "Potential Energy", "Time (ps)", "Potential Energy (kJ/mol)")
                else:
                    # Generic fallback
                    try:
                        num_cols = [c for c in df.columns if str(c).strip()]
                        if len(num_cols) >= 2:
                            color = self.get_property("plot_color") or "#4169e1"
                            plt.plot(df[num_cols[0]], df[num_cols[1]], color=color, linewidth=1.8)
                    except Exception:
                        plt.text(0.5, 0.5, "Unsupported data", ha="center", va="center")
        except Exception:
            plt.text(0.5, 0.5, "Error plotting", ha="center", va="center")

        buf = io.BytesIO()
        try:
            # tight_layout can be relatively expensive; skip if small figure
            if hasattr(plt, 'gcf'):
                fig = plt.gcf()
                try:
                    w, h = fig.get_size_inches()
                    if w * h > 10.0:
                        plt.tight_layout()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            # Use slightly lower DPI for faster rendering while keeping clarity
            plt.savefig(buf, format="png", dpi=150)
            plt.close()
        except Exception:
            return b""
        return buf.getvalue()

    def _set_image(self, data: bytes | None) -> None:
        if self._img is None:
            return
        try:
            from PySide6.QtGui import QPixmap, QImage
            from PySide6.QtCore import Qt
            if not data:
                self._img.setText("No plot")
                return
            img = QImage.fromData(data)
            if img.isNull():
                self._img.setText("Invalid image")
                return
            available_width = max(32, self.width - 24)
            available_height = max(32, self.height - 72)  # controls + margins
            scaled = img.scaled(available_width, available_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._img.setPixmap(QPixmap.fromImage(scaled))
            self._img.setText("")
        except Exception:
            try:
                self._img.setText("Error displaying image")
            except Exception:
                pass

    def on_result(self, result: object) -> None:
        # Update available options when new data flows in
        try:
            self._refresh_combo_items()
        except Exception:
            pass
        super().on_result(result)

    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        # Hide default inline summary to keep UI minimal
        return []

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """No-op compute: refresh UI and, if possible, auto-render a plot.

        Returns an empty dict since this node does not expose outputs.
        """
        try:
            # Ensure options reflect latest live inputs
            self._refresh_combo_items()
            # If a selection exists or only one option is available, render automatically
            port_key = None
            try:
                if self._combo is not None:
                    data_key = self._combo.currentData()
                    if data_key:
                        port_key = data_key
            except Exception:
                pass
            if not port_key:
                avail = self._available_inputs()
                if avail:
                    # pick first available dataset
                    port_key = next(iter(avail.keys()))
            if port_key:
                data_obj = self._available_inputs().get(port_key)
                if data_obj is not None:
                    img_bytes = self._render_plot_bytes(port_key, data_obj)
                    try:
                        self._last_image_bytes = img_bytes
                    except Exception:
                        pass
                    self._set_image(img_bytes)
        except Exception:
            pass
        return {}

    def _update_content_geometry(self, force: bool = False) -> None:  # type: ignore[override]
        try:
            super()._update_content_geometry(force)
        except Exception:
            pass
        # Rescale current image to fit new size for responsiveness
        try:
            img_bytes = getattr(self, "_last_image_bytes", None)
            if img_bytes:
                self._set_image(img_bytes)
        except Exception:
            pass

class CharmmGUIInputNode(BaseNode):
    """CHARMM-GUI Input node for MD preparation.
    Verifies and normalizes CHARMM-GUI output files for GROMACS MD simulation.
    """

    def __init__(self):
        super().__init__("charmm_gui_input", "CHARMM-GUI Input")
        self.logger = get_logger(__name__)
        self.add_input_port("folder", "string")
        self.add_output_port("gro_file", "file")
        self.add_output_port("top_file", "file")
        self.add_output_port("mdp_min", "file")
        self.add_output_port("mdp_eq", "file")
        self.add_output_port("mdp_prod", "file")
        self.add_output_port("index_file", "file")
        self.add_output_port("folder_path", "string")

        # Properties for file verification
        self.set_property("needs_confirmation", False)
        self.set_property("auto_detect", True)
        self.set_property("user_checked_keys", [])
        # Persist manual picks across re-runs
        self.set_property("user_selected_files", {})

        # Inline UI: scroll list of files; floating checklist panel on the right
        try:
            from PySide6.QtWidgets import (
                QScrollArea,
                QWidget,
                QVBoxLayout,
                QGridLayout,
                QLabel,
                QGraphicsProxyWidget,
                QFrame,
                QCheckBox,
                QPushButton,
            )

            self.width = 420
            self.height = 240
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)
            try:
                self.set_content_margins(0, 32, 0, 0)
            except Exception:
                pass
            
            # Node body: scroll area with file presence statuses
            body_container = QWidget()
            body_layout = QVBoxLayout()
            body_layout.setContentsMargins(6, 4, 6, 6)
            body_layout.setSpacing(4)

            self._scroll = QScrollArea()
            self._scroll.setWidgetResizable(True)
            self._scroll_widget = QWidget()
            self._files_layout = QGridLayout()
            self._files_layout.setContentsMargins(4, 4, 4, 4)
            self._files_layout.setSpacing(4)
            self._scroll_widget.setLayout(self._files_layout)
            self._scroll.setWidget(self._scroll_widget)
            # Keep a reference to body layout for further updates
            self._body_layout = body_layout
            body_layout.addWidget(self._scroll)
            # Finish button under the scroll (disabled until all resolved)
            self._btn_finish = QPushButton("Finish")
            try:
                self._btn_finish.setEnabled(False)
            except Exception:
                pass
            def _on_finish_clicked():
                try:
                    # User confirms all selections; resume workflow
                    self.set_property("needs_confirmation", False)
                    try:
                        sc = self.scene()
                        view = None
                        if sc is not None and hasattr(sc, 'views'):
                            vs = sc.views()
                            view = vs[0] if isinstance(vs, (list, tuple)) and vs else None
                        if view is not None:
                            win = view.window()
                            if hasattr(win, 'workflow_manager'):
                                win.workflow_manager.resume_user_input(self._node_id)
                    except Exception:
                        pass
                    # Trigger rerun
                    try:
                        if hasattr(self, 'rerun_requested'):
                            self.rerun_requested.emit(self)
                    except Exception:
                        pass
                except Exception:
                    pass
            try:
                self._btn_finish.clicked.connect(_on_finish_clicked)
            except Exception:
                pass
            try:
                # Ensure Finish button is visible inside the node body and persists
                self._body_layout.addWidget(self._btn_finish)
                self._btn_finish.setVisible(True)
            except Exception:
                pass
            body_container.setLayout(body_layout)
            
            content_layout = self.content_layout
            if content_layout is not None:
                content_layout.addWidget(body_container, 0, 0)
            self._update_port_positions()

            # Floating checklist panel (hidden by default)
            self._panel_proxy = None
            self._panel_widget = None
            self._panel_ok = None
            self._chk_map = {}
            self._panel_list_layout = None
            self._panel_file_checks = {}
            self._panel_current_key = None
            self._file_keys = [
                ("gro", "Structure (.gro)"),
                ("top", "Topology (.top)"),
                ("mdp_min", "MDP Minimization (.mdp)"),
                ("mdp_eq", "MDP Equilibration (.mdp)"),
                ("mdp_prod", "MDP Production (.mdp)"),
                ("index", "Index (.ndx)"),
            ]

            self._ensure_panel()
        except Exception:
            self._scroll = None
            self._files_layout = None
            self._panel_proxy = None
            self._panel_widget = None
            self._panel_ok = None
            self._chk_map = {}

    def _detect_files(self, folder_path: str) -> Dict[str, Optional[str]]:
        """Auto-detect CHARMM-GUI output files in the folder."""
        folder = Path(folder_path)
        files = {
            "gro": None,
            "top": None,
            "mdp_min": None,
            "mdp_eq": None,
            "mdp_prod": None,
            "index": None,
        }
        
        # Common CHARMM-GUI file patterns (strict: exact filenames only)
        patterns = {
            "gro": ["step3_input.gro"],
            "top": ["topol.top"],
            "mdp_min": ["step4.0_minimization.mdp"],
            "mdp_eq": ["step4.1_equilibration.mdp"],
            "mdp_prod": ["step5_production.mdp"],
            "index": ["index.ndx"],
        }
        
        for key, pattern_list in patterns.items():
            for pattern in pattern_list:
                # First, try in the provided folder root
                file_path = folder / pattern
                if file_path.exists():
                    files[key] = str(file_path)
                    break
                # Then, search recursively in subfolders (CHARMM-GUI often nests under gromacs/)
                try:
                    match = next(folder.rglob(pattern), None)
                except Exception:
                    match = None
                if match is not None and match.exists():
                    files[key] = str(match)
                    break
        
        return files

    def _update_status(self, status_text: str):
        """Deprecated in this node: status shown via file list."""
        return

    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        # Hide default painted labels entirely
        return []

    def _update_file_list_ui(self, detected: Dict[str, Optional[str]]) -> None:
        layout = getattr(self, "_files_layout", None)
        if layout is None:
            return
        try:
            from PySide6.QtWidgets import QLabel, QPushButton
        except Exception:
            return
        # Clear existing widgets
        try:
            while layout.count():
                item = layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()
        except Exception:
            pass
        # Add rows for each file
        row = 0
        for key, display in self._file_keys:
            present = bool(detected.get(key))
            status = "✓" if present else "✗"
            lbl_status = QLabel(status)
            btn_row = QPushButton(display)
            try:
                btn_row.setFlat(True)
            except Exception:
                pass
            def _make_on_click(k: str):
                def _on_click():
                    try:
                        folder_prop = self.get_property("last_input_folder") or self.get_property("folder")
                    except Exception:
                        folder_prop = None
                    if folder_prop:
                        try:
                            self._populate_panel_for_key(str(folder_prop), k)
                            self._set_panel_visible(True)
                        except Exception:
                            pass
                return _on_click
            try:
                btn_row.clicked.connect(_make_on_click(key))
            except Exception:
                pass
            try:
                # Green for present, red for missing
                if present:
                    lbl_status.setStyleSheet("color: #7bd88f; font-weight: bold;")
                else:
                    lbl_status.setStyleSheet("color: #e16a6a; font-weight: bold;")
            except Exception:
                pass
            layout.addWidget(lbl_status, row, 0)
            layout.addWidget(btn_row, row, 1)
            row += 1
        # Do not move the Finish button here; it lives under the scroll area in body layout

    def _ensure_panel(self) -> None:
        """Create the floating right-side panel if needed."""
        if getattr(self, "_panel_proxy", None) is not None and getattr(self, "_panel_widget", None) is not None:
            return
        try:
            from PySide6.QtWidgets import (
                QGraphicsProxyWidget,
                QFrame,
                QVBoxLayout,
                QHBoxLayout,
                QLabel,
                QPushButton,
                QCheckBox,
            )
        except Exception:
            return
        panel = QFrame()
        panel.setObjectName("NodeCharmmFilesPanel")
        try:
            panel.setStyleSheet(
                """
                QFrame#NodeCharmmFilesPanel {
                    background-color: #2b2b2b;
                    border: 1px solid #666666;
                    border-radius: 6px;
                }
                QLabel { color: #e0e0e0; }
                QCheckBox { color: #e0e0e0; }
                QPushButton { color: #e0e0e0; background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px; padding: 4px 8px; }
                """
            )
        except Exception:
            pass
        v = QVBoxLayout(panel)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(6)
        try:
            v.addWidget(QLabel("Select file(s) for the chosen category:"))
        except Exception:
            pass
        # Dynamic list of files from folder
        from PySide6.QtWidgets import QWidget, QScrollArea
        self._panel_scroll = QScrollArea()
        self._panel_scroll.setWidgetResizable(True)
        self._panel_list_container = QWidget()
        from PySide6.QtWidgets import QVBoxLayout
        self._panel_list_layout = QVBoxLayout(self._panel_list_container)
        self._panel_list_layout.setContentsMargins(4, 4, 4, 4)
        self._panel_list_layout.setSpacing(4)
        self._panel_scroll.setWidget(self._panel_list_container)
        v.addWidget(self._panel_scroll)
        # Buttons row
        row_btns = QHBoxLayout()
        self._panel_ok = QPushButton("OK")
        try:
            self._panel_ok.setEnabled(False)
        except Exception:
            pass

        def _on_ok_clicked():
            try:
                # Collect selected file(s) for current key and update detected mapping
                if not self._panel_current_key:
                    return
                chosen = []
                for path, chk in (self._panel_file_checks or {}).items():
                    try:
                        if chk.isChecked():
                            chosen.append(path)
                    except Exception:
                        pass
                if not chosen:
                    return
                # Persist selection for the category
                try:
                    # Save in user_selected_files for durability across runs
                    sel = self.get_property("user_selected_files") or {}
                    sel[self._panel_current_key] = str(chosen[0])
                    self.set_property("user_selected_files", dict(sel))
                    # Also update current detected snapshot
                    detected = self.get_property("_detected_files") or {}
                    detected[self._panel_current_key] = str(chosen[0])
                    self.set_property("_detected_files", dict(detected))
                    # Recompute missing keys snapshot
                    missing_keys = [k for k, v in detected.items() if not v]
                    self.set_property("_missing_keys", list(missing_keys))
                except Exception:
                    pass
                # Hide panel after selection
                self._set_panel_visible(False)
                # Refresh inline list
                self._update_file_list_ui(self.get_property("_detected_files") or {})
                # If all categories resolved, enable Finish; otherwise disable
                try:
                    if self._btn_finish is not None:
                        all_resolved = all(bool((self.get_property("_detected_files") or {}).get(k)) for k, _ in self._file_keys)
                        self._btn_finish.setEnabled(all_resolved)
                except Exception:
                    pass
            except Exception:
                pass

        try:
            self._panel_ok.clicked.connect(_on_ok_clicked)
        except Exception:
            pass
        row_btns.addStretch(1)
        row_btns.addWidget(self._panel_ok)
        v.addLayout(row_btns)

        self._panel_widget = panel
        self._panel_proxy = QGraphicsProxyWidget(self)
        self._panel_proxy.setWidget(panel)
        try:
            self._panel_proxy.setVisible(False)
        except Exception:
            pass
        # When panel visibility changes, update anchor and ports adaptively
        try:
            def _anchor_base() -> float:
                return float(self.width)
            object.__setattr__(self, "_get_output_port_anchor_x", _anchor_base)  # type: ignore[arg-type]
        except Exception:
            pass

    def _update_panel_state(self, detected: Dict[str, Optional[str]]) -> None:
        if not getattr(self, "_panel_widget", None):
            return
        # Enable Finish if all categories resolved
        try:
            if getattr(self, "_btn_finish", None) is not None:
                all_resolved = all(bool(detected.get(k)) for k, _ in self._file_keys)
                self._btn_finish.setEnabled(all_resolved)
        except Exception:
            pass

    def _set_panel_visible(self, visible: bool) -> None:
        try:
            if getattr(self, "_panel_proxy", None) is not None:
                self._panel_proxy.setVisible(bool(visible))
                self._update_content_geometry(force=True)
            # Ensure Finish button remains visible even while panel is shown
            if getattr(self, "_btn_finish", None) is not None:
                try:
                    self._btn_finish.setVisible(True)
                except Exception:
                    pass
        except Exception:
            pass

    def _populate_panel_for_key(self, folder_path: str, key: str) -> None:
        """Populate the floating panel with all files from folder for the selected category key."""
        container_layout = getattr(self, "_panel_list_layout", None)
        if container_layout is None:
            return
        self._panel_current_key = key
        # Clear current entries
        try:
            while container_layout.count():
                item = container_layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()
        except Exception:
            pass
        self._panel_file_checks = {}
        from pathlib import Path as _Path
        p = _Path(folder_path)
        candidates: list[str] = []
        try:
            for child in p.rglob("*"):
                try:
                    if child.is_file():
                        # Build display name relative to base folder (use forward slashes)
                        rel = str(child.relative_to(p)).replace("\\", "/")
                        candidates.append(rel)
                except Exception:
                    pass
        except Exception:
            candidates = []
        # Sort for stable UI
        try:
            candidates.sort()
        except Exception:
            pass
        # Add checkboxes
        try:
            from PySide6.QtWidgets import QCheckBox
            for rel_path in candidates:
                chk = QCheckBox(rel_path)
                container_layout.addWidget(chk)
                # Store absolute path mapping for selection apply step
                abs_path = str(p / rel_path)
                self._panel_file_checks[abs_path] = chk
            # Enable OK only if at least one selected
            def _on_any_change():
                try:
                    any_sel = any(cb.isChecked() for cb in self._panel_file_checks.values())
                    if self._panel_ok is not None:
                        self._panel_ok.setEnabled(any_sel)
                except Exception:
                    pass
            for cb in self._panel_file_checks.values():
                try:
                    cb.stateChanged.connect(_on_any_change)
                except Exception:
                    pass
            _on_any_change()
        except Exception:
            pass

    def _update_content_geometry(self, force: bool = False) -> None:  # type: ignore[override]
        try:
            super()._update_content_geometry(force)
        except Exception:
            pass
        # Position floating panel to the right similar to DataframeMergeNode
        try:
            if getattr(self, "_panel_proxy", None) is not None and getattr(self, "_panel_widget", None) is not None and self._panel_proxy.isVisible():
                try:
                    # Match height with node body
                    self._panel_widget.setFixedHeight(int(self.height))
                except Exception:
                    pass
                panel_w = int(max(220, min(320, self.width * 0.45)))
                try:
                    self._panel_widget.setFixedWidth(panel_w)
                    self._panel_widget.adjustSize()
                except Exception:
                    pass
                x_offset = float(self.width) + 12.0
                self._panel_proxy.setPos(x_offset, 0.0)
                # Shift output ports to the right edge of the floating panel
                try:
                    def _anchor_override() -> float:
                        return float(self.width) + 12.0 + float(panel_w)
                    object.__setattr__(self, "_get_output_port_anchor_x", _anchor_override)  # type: ignore[arg-type]
                    self._update_port_positions()
                except Exception:
                    pass
            else:
                # Panel hidden: restore default output anchor to node right edge
                try:
                    def _anchor_base() -> float:
                        return float(self.width)
                    object.__setattr__(self, "_get_output_port_anchor_x", _anchor_base)  # type: ignore[arg-type]
                    self._update_port_positions()
                except Exception:
                    pass
        except Exception:
            pass

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        folder_path = inputs.get("folder") if inputs else None
        if not folder_path:
            # Fallback to property in case folder was set via property editor
            try:
                folder_path = self.get_property("folder")
            except Exception:
                folder_path = None
        
        if not folder_path:
            raise ValueError("No folder path provided")
        
        if not Path(folder_path).exists():
            raise ValueError(f"Folder not found: {folder_path}")
        
        # Auto-detect files and overlay with any previous user selections
        detected = self._detect_files(folder_path)
        try:
            sel = self.get_property("user_selected_files") or {}
            if isinstance(sel, dict):
                for k, v in sel.items():
                    if v and (k in detected):
                        detected[k] = str(v)
        except Exception:
            pass
        try:
            self.set_property("_detected_files", dict(detected))
        except Exception:
            pass
        self._update_file_list_ui(detected)

        # Determine missing
        missing_keys = [k for k, v in detected.items() if not v]
        try:
            self.set_property("_missing_keys", list(missing_keys))
        except Exception:
            pass
        has_missing = len(missing_keys) > 0
        # Pause only if masih ada kategori yang kosong setelah overlay user selection
        should_pause = has_missing

        # Update floating panel state and visibility (effective in GUI via on_result)
        self._update_panel_state(detected)
        self._set_panel_visible(should_pause)

        if should_pause:
            # Pause the workflow (headless-safe like PubChem node) and wait for user actions
            try:
                msg = "Missing files detected. Click a red category to pick files on the right, then click Finish to continue."
                self._manager.pause_user_input(self._node_id, msg)  # type: ignore[attr-defined]
            except Exception:
                # Headless fallback: cannot pause → raise explicit error
                missing = ", ".join(missing_keys)
                raise ValueError(f"Missing required files: {missing}")
            # Mark that we are waiting and return no outputs
            try:
                self.set_property("needs_confirmation", True)
            except Exception:
                pass
            return {}

        # All files present or user confirmed → return results
        try:
            self.set_property("needs_confirmation", False)
        except Exception:
            pass
        return {
            "gro_file": detected["gro"],
            "top_file": detected["top"],
            "mdp_min": detected["mdp_min"],
            "mdp_eq": detected["mdp_eq"],
            "mdp_prod": detected["mdp_prod"],
            "index_file": detected["index"],
            "folder_path": folder_path,
        }

    def validate(self) -> tuple[bool, str]:
        if self.get_property("needs_confirmation"):
            return False, "Waiting for files checklist confirmation"
        return True, "Files confirmed"

    def on_result(self, result: object) -> None:  # type: ignore[override]
        # Show/hide pause hint below the node depending on confirmation state
        try:
            needs = bool(self.get_property("needs_confirmation"))
            # In GUI, also refresh the inline file list and floating panel visibility
            detected = self.get_property("_detected_files") or {}
            # If we don't have a detected snapshot yet, try to detect from last input folder (live-only convenience)
            if not detected:
                folder_prop = self.get_property("last_input_folder") or self.get_property("folder")
                if folder_prop:
                    try:
                        fp = str(folder_prop)
                        if Path(fp).exists():
                            detected = self._detect_files(fp)
                            self.set_property("_detected_files", dict(detected))
                            missing_keys = [k for k, v in detected.items() if not v]
                            self.set_property("_missing_keys", list(missing_keys))
                    except Exception:
                        pass
            if detected:
                self._update_file_list_ui(detected)
                missing_keys = self.get_property("_missing_keys") or []
                should_pause = bool(missing_keys) and needs
                self._update_panel_state(detected)
                self._set_panel_visible(should_pause)
            if needs:
                self.show_pause("Paused: click a red category to choose file(s) on the right, then click Finish to continue.")
            else:
                if hasattr(self, 'clear_error'):
                    self.clear_error()
            self._update_content_geometry(force=False)
            self.update()
        except Exception:
            pass
        super().on_result(result)


class GromacsInputEditorNode(BaseNode):
    """GROMACS Input Editor for modifying MDP parameters.
    Allows editing MDP file parameters before running MD simulation.
    """

    def __init__(self):
        super().__init__("gromacs_input_editor", "GROMACS Input Editor")
        self.logger = get_logger(__name__)
        # Single input/output: mdp_file
        self.add_input_port("mdp_file", "file")
        self.add_output_port("mdp_file", "file")

        # Properties
        self.set_property("needs_editing", True)
        self.set_property("_current_mdp_path", "")
        self.set_property("_mdp_text_content", "")

        # Inline UI: plain text editor + OK button, no labels
        try:
            from PySide6.QtWidgets import (QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

            self.width = 560
            self.height = 320
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)
            try:
                self.set_content_margins(0, 32, 0, 0)
            except Exception:
                pass

            container = QWidget()
            main_layout = QVBoxLayout(container)
            main_layout.setContentsMargins(6, 6, 6, 6)
            main_layout.setSpacing(6)

            self._txt = QPlainTextEdit()
            try:
                self._txt.setPlaceholderText("")
            except Exception:
                pass
            self._btn_ok = QPushButton("OK")
            try:
                self._btn_ok.setEnabled(True)
            except Exception:
                pass

            def _on_ok_clicked():
                try:
                    # Write current text back to the MDP file immediately
                    mdp_path = str(self.get_property("_current_mdp_path") or "")
                    if mdp_path:
                        try:
                            text = self._txt.toPlainText() if hasattr(self._txt, 'toPlainText') else str(self.get_property("_mdp_text_content") or "")
                        except Exception:
                            text = str(self.get_property("_mdp_text_content") or "")
                        try:
                            with open(mdp_path, 'w', encoding='utf-8') as f:
                                f.write(text)
                        except Exception as e:
                            self.logger.error(f"Failed to write MDP file: {e}")
                        # Update property so next run shows latest content
                        try:
                            self.set_property("_mdp_text_content", text)
                        except Exception:
                            pass
                    # Mark editing complete
                    try:
                        self.set_property("needs_editing", False)
                    except Exception:
                        pass
                    # Resume workflow
                    try:
                        sc = self.scene()
                        view = None
                        if sc is not None and hasattr(sc, 'views'):
                            vs = sc.views()
                            view = vs[0] if isinstance(vs, (list, tuple)) and vs else None
                        if view is not None:
                            win = view.window()
                            if hasattr(win, 'workflow_manager'):
                                win.workflow_manager.resume_user_input(self._node_id)
                    except Exception:
                        pass
                    # Trigger rerun
                    try:
                        if hasattr(self, 'rerun_requested'):
                            self.rerun_requested.emit(self)
                    except Exception:
                        pass
                except Exception as e:
                    self.logger.error(f"Error in OK button: {e}")

            try:
                self._btn_ok.clicked.connect(_on_ok_clicked)
            except Exception:
                pass

            # Assemble
            main_layout.addWidget(self._txt)
            main_layout.addWidget(self._btn_ok)

            content_layout = self.content_layout
            if content_layout is not None:
                content_layout.addWidget(container, 0, 0)
            self._update_port_positions()
        except Exception:
            self._txt = None
            self._btn_ok = None

    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        # Hide default painted labels inside the node body
        return []

    def on_result(self, result: object) -> None:  # type: ignore[override]
        # Keep editor content in sync when running with live canvas
        try:
            text = self.get_property("_mdp_text_content") or ""
            self._load_text_into_ui(str(text))
            # Show pause hint when waiting for user edit
            if bool(self.get_property("needs_editing")):
                try:
                    self.show_pause("Waiting for user: edit the MDP and click OK.")
                except Exception:
                    pass
            else:
                try:
                    self.clear_error()
                except Exception:
                    pass
            self._update_content_geometry(force=False)
            self.update()
        except Exception:
            pass
        super().on_result(result)

    def _load_text_into_ui(self, text: str) -> None:
        editor = getattr(self, "_txt", None)
        if editor is None:
            return
        try:
            editor.blockSignals(True)
            editor.setPlainText(text)
        except Exception:
            try:
                editor.setPlainText(text)
            except Exception:
                pass
        finally:
            try:
                editor.blockSignals(False)
            except Exception:
                pass

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        mdp_path = inputs.get("mdp_file") if inputs else None
        if not mdp_path:
            raise ValueError("MDP file is required")

        # Remember current path for OK handler
        try:
            self.set_property("_current_mdp_path", str(mdp_path))
        except Exception:
            pass

        # Load file content
        text = ""
        try:
            with open(mdp_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        except Exception:
            text = ""
        try:
            self.set_property("_mdp_text_content", text)
        except Exception:
            pass

        # Update UI text (in GUI this will apply via on_result too)
        self._load_text_into_ui(text)

        # Pause for user editing if needed
        if self.get_property("needs_editing"):
            try:
                msg = "Edit MDP content, then click OK to continue."
                self._manager.pause_user_input(self._node_id, msg)  # type: ignore[attr-defined]
            except Exception:
                # Headless: if cannot pause, continue without editing
                try:
                    self.set_property("needs_editing", False)
                except Exception:
                    pass
                return {"mdp_file": mdp_path}
            # While paused, return original file
            return {"mdp_file": mdp_path}

        # If not needing edits, pass-through current file
        return {"mdp_file": mdp_path}


class XTCExtractorNode(BaseNode):
    """XTC Extractor for GROMACS trajectory post-processing.
    Extracts and processes XTC trajectory files for analysis.
    """

    def __init__(self):
        super().__init__("xtc_extractor", "XTC Extractor")
        self.logger = get_logger(__name__)
        self.add_input_port("tpr_file", "file")
        self.add_input_port("xtc_file", "file")
        self.add_output_port("xtc_file", "file")
        self.add_output_port("tpr_file", "file")
        
        # Properties
        self.set_property("pbc_method", "mol")  # mol, res, atom, none
        self.set_property("ur_method", "compact")  # compact, rect, tric
        self.set_property("center", False)
        self.set_property("fit", False)
        self.set_property("gromacs_version", "2025.1")
        self.set_property("use_gpu", False)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        tpr_path = inputs.get("tpr_file") if inputs else None
        xtc_path = inputs.get("xtc_file") if inputs else None
        
        if not tpr_path or not Path(tpr_path).exists():
            raise FileNotFoundError(f"TPR file not found: {tpr_path}")
        if not xtc_path or not Path(xtc_path).exists():
            raise FileNotFoundError(f"XTC file not found: {xtc_path}")
        
        out_dir = get_subdir("gromacs_xtc_extracted")
        gmx = resolve_gromacs_executable(self.get_property("gromacs_version"),
                                        use_gpu=bool(self.get_property("use_gpu")))
        
        # Build trjconv command
        out_xtc = out_dir / "analysis.xtc"
        cmd = [gmx, "trjconv", 
               "-s", str(tpr_path),
               "-f", str(xtc_path),
               "-o", str(out_xtc),
               "-pbc", self.get_property("pbc_method"),
               "-ur", self.get_property("ur_method")]
        
        if self.get_property("center"):
            cmd.extend(["-center"])
        if self.get_property("fit"):
            cmd.extend(["-fit", "rot+trans"])
        
        try:
            self.report_progress(10, "Extracting XTC trajectory...")
            
            # Run trjconv with group selection (0 = System)
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            stdout, stderr = proc.communicate("0\n")  # Select System
            
            if proc.returncode != 0:
                raise RuntimeError(f"trjconv failed: {stderr}")
            
            self.report_progress(100, "XTC extraction completed")
            
            return {
                "xtc_file": str(out_xtc),
                "tpr_file": tpr_path,  # Pass through TPR
            }
            
        except Exception as e:
            self.logger.error(f"XTC extraction failed: {e}")
            raise


class GromacsViewerNode(BaseNode):
    """
    GROMACS Viewer Node for visualizing MD trajectories using web-based NGL.js viewer.
    """

    def __init__(self):
        super().__init__("gromacs_viewer", "GROMACS Viewer")
        self.logger = get_logger(__name__)
        self.add_input_port("gro_file", "file")
        self.add_input_port("xtc_file", "file")
        self.add_output_port("viewer_url", "string")

        # Properties for storing data
        self.set_property("gro_data", "")
        self.set_property("trajectory_data", "")
        self.set_property("background", "#000000")
        self.set_property("auto_spin", False)

        # Sizing similar to 3D web viewer
        try:
            self.width = 520
            self.height = 360
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)
            self.set_content_margins(0, 32, 0, 0)
        except Exception:
            pass

        # Add inline web viewer with simple controls
        try:
            from PySide6.QtWidgets import QPushButton, QLineEdit, QSizePolicy
            from PySide6.QtWebEngineWidgets import QWebEngineView
            from PySide6.QtWebEngineCore import QWebEngineSettings

            # Control buttons
            self._btn_view = QPushButton("View MD")
            self._btn_view.setToolTip("Open GROMACS MD trajectory viewer")
            self._btn_view.clicked.connect(self._on_open_viewer)

            # Embedded lightweight viewer
            from core.nodes import BaseNode as _BaseNode
            if not getattr(_BaseNode, "_lightweight_construction", False):
                self._inline_webview = QWebEngineView()
                try:
                    self._inline_webview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                    # Configure WebEngine for MD viewer
                    settings = self._inline_webview.page().settings()
                    settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
                    settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
                    settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
                    # Set initial blank page
                    self._inline_webview.setHtml(
                        "<html><body style='background-color:#000; margin:0; display:flex; align-items:center; justify-content:center; color:#fff; font-family:Arial;'>Load MD trajectory to view</body></html>"
                    )
                except Exception:
                    pass
            else:
                self._inline_webview = None  # type: ignore[assignment]

            layout = self.content_layout
            if layout is not None:
                # Top row: View button
                layout.addWidget(self._btn_view, 0, 0, 1, 3)
                # Second row: embedded webview fills the rest
                if self._inline_webview is not None:
                    layout.addWidget(self._inline_webview, 1, 0, 1, 3)
                try:
                    layout.setColumnStretch(0, 1)
                    layout.setColumnStretch(1, 0)
                    layout.setColumnStretch(2, 0)
                    layout.setRowStretch(1, 1)
                except Exception:
                    pass

            # Ports depend on width/height; ensure correct placement
            self._update_port_positions()

        except Exception:
            # If widgets cannot be created (headless), skip inline widgets
            self._btn_view = None
            self._inline_webview = None

    def __del__(self):
        """Cleanup threads on destruction."""
        try:
            # Clean up trajectory thread
            if hasattr(self, '_traj_thread') and self._traj_thread and self._traj_thread.isRunning():
                self._traj_thread.quit()
                if not self._traj_thread.wait(1000):
                    self._traj_thread.terminate()
                    self._traj_thread.wait(500)
            
            # Clean up GRO thread
            if hasattr(self, '_gro_thread') and self._gro_thread and self._gro_thread.isRunning():
                self._gro_thread.quit()
                if not self._gro_thread.wait(1000):
                    self._gro_thread.terminate()
                    self._gro_thread.wait(500)
        except Exception:
            pass  # Ignore errors during cleanup

    def _ensure_gromacs_viewer_file_exists(self) -> Path:
        """Ensure the GROMACS viewer HTML exists."""
        try:
            from backend.resource_access import is_using_compiled_resources, get_web_file_path
            
            if is_using_compiled_resources():
                self.logger.info("Using compiled resources for GROMACS web viewer")
                # return Path("web") / "gromacs_viewer.html"
                return get_web_file_path("gromacs_viewer.html")
        except ImportError:
            pass
        except Exception as e:
            self.logger.debug(f"Resource system check failed: {e}")
        
        # Fallback: check if file exists
        path = Path("web") / "gromacs_viewer.html"
        if not path.exists():
            self.logger.error("GROMACS viewer HTML file not found at web/gromacs_viewer.html")
            raise FileNotFoundError(f"GROMACS viewer file not found: {path}")
        
        return path

    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        # No painted labels inside node body
        return []

    def _update_content_geometry(self, force: bool = False) -> None:  # type: ignore[override]
        try:
            super()._update_content_geometry(force)
        except Exception:
            pass
        # Position right floating panel and shift output pins accordingly
        try:
            if getattr(self, "_panel_proxy", None) is not None and getattr(self, "_panel_widget", None) is not None:
                try:
                    self._panel_widget.setFixedHeight(int(self.height))
                except Exception:
                    pass
                panel_w = int(max(180, min(260, self.width * 0.42)))
                try:
                    self._panel_widget.setFixedWidth(panel_w)
                    self._panel_widget.adjustSize()
                except Exception:
                    pass
                x_offset = float(self.width) + 12.0
                self._panel_proxy.setPos(x_offset, 0.0)
                try:
                    def _anchor_override() -> float:
                        return float(self.width) + 12.0 + float(panel_w)
                    object.__setattr__(self, "_get_output_port_anchor_x", _anchor_override)  # type: ignore[arg-type]
                    self._update_port_positions()
                except Exception:
                    pass
        except Exception:
            pass

    # Legacy methods removed - now using web-based viewer

    # Legacy OpenGL viewer methods removed - replaced with web-based ngl.js viewer

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        gro_path = inputs.get("gro_file") if inputs else None
        xtc_path = inputs.get("xtc_file") if inputs else None
        
        if not gro_path:
            raise ValueError("gro_file input is required")
        
        # Store file paths
        try:
            self.set_property("gro_path", str(gro_path))
            self.set_property("xtc_path", str(xtc_path) if xtc_path else "")
            self.set_property("has_xtc", bool(xtc_path))
        except Exception:
            pass
        
        # Compute frame count for trajectory (do this async to avoid lag)
        try:
            if xtc_path:
                # For XTC files, defer frame count calculation to async processing
                self.set_property("frame_count", -1)  # -1 indicates pending calculation
            else:
                self.set_property("frame_count", 1)
        except Exception:
            pass
        
        # Build viewer URL
        try:
            self._ensure_gromacs_viewer_file_exists()
            url = self._build_gromacs_viewer_url(str(gro_path), str(xtc_path) if xtc_path else None)
            self.logger.info(f"Built GROMACS viewer URL with {len(url)} characters")
            
            # Schedule immediate update of inline viewer for responsiveness
            try:
                from PySide6.QtCore import QTimer
                if hasattr(self, '_inline_webview') and self._inline_webview is not None:
                    QTimer.singleShot(100, self._update_inline_viewer)
            except Exception:
                pass
            
            return {"viewer_url": url, "status": "ready"}
        except Exception as e:
            self.logger.error(f"Failed to build GROMACS viewer URL: {e}")
            return {"viewer_url": "", "status": "error"}

    def on_result(self, result: object) -> None:  # type: ignore[override]
        # Update embedded viewer when new results are available
        try:
            super().on_result(result)
        except Exception:
            pass
        
        try:
            self.logger.info("Node execution completed, updating inline viewer")
            
            # Force immediate update of inline viewer
            self._force_update_inline_viewer()
            
            # Update external viewer window if open
            viewer_window = getattr(self, "_viewer_window", None)
            if viewer_window is not None:
                gro_file = self.get_property("gro_path")
                xtc_file = self.get_property("xtc_path")
                
                if gro_file:
                    url = self._build_gromacs_viewer_url(gro_file, xtc_file)
                    if url:
                        try:
                            viewer_window.load_viewer_url(url)
                        except Exception:
                            pass
        except Exception as e:
            self.logger.error(f"Error in on_result: {e}")

    def _force_update_inline_viewer(self):
        """Force immediate update of the inline viewer."""
        try:
            if not hasattr(self, '_inline_webview') or not self._inline_webview:
                self.logger.warning("No inline webview to update")
                return
                
            gro_file = self.get_property("gro_path")
            xtc_file = self.get_property("xtc_path")
            
            self.logger.info(f"Forcing inline viewer update - GRO: {gro_file}, XTC: {xtc_file}")
            
            if gro_file and not xtc_file:
                # For GRO-only: load viewer pointing directly to the GRO file (avoid huge URL params)
                try:
                    url = self._build_gromacs_viewer_url(gro_file=gro_file)
                    if url:
                        from PySide6.QtCore import QUrl
                        qurl = QUrl(url)
                        self._inline_webview.setUrl(qurl)
                        self._inline_webview.load(qurl)
                    else:
                        self.logger.error("Failed to build viewer URL for GRO-only display")
                except Exception as e:
                    self.logger.error(f"Error in force update: {e}")
            else:
                # Call normal update for XTC files or when no files
                self._update_inline_viewer()
                
        except Exception as e:
            self.logger.error(f"Error forcing inline viewer update: {e}")

    def _build_gromacs_viewer_url(self, gro_file: Optional[str] = None, xtc_file: Optional[str] = None, traj_data: Optional[str] = None, traj_file: Optional[str] = None) -> str:
        """Build URL for GROMACS viewer with proper parameters."""
        try:
            from PySide6.QtCore import QUrl
            from urllib.parse import quote
            import base64
            
            # Get viewer file URL
            try:
                from backend.resource_access import get_web_file_url
                base_url = get_web_file_url("gromacs_viewer.html")
            except ImportError:
                viewer_path = self._ensure_gromacs_viewer_file_exists()
                base_url = QUrl.fromLocalFile(str(viewer_path.resolve()))

            params = []
            
            # Handle GRO file
            if gro_file:
                try:
                    gro_path = Path(gro_file)
                    if gro_path.exists():
                        gro_url = QUrl.fromLocalFile(str(gro_path.resolve()))
                        params.append(f"gro_file={quote(gro_url.toString())}")
                    else:
                        params.append(f"gro_file={quote(gro_file)}")
                except Exception:
                    params.append(f"gro_file={quote(gro_file)}")
            
            # Handle XTC trajectory file  
            if xtc_file:
                try:
                    xtc_path = Path(xtc_file)
                    if xtc_path.exists():
                        xtc_url = QUrl.fromLocalFile(str(xtc_path.resolve()))
                        params.append(f"xtc_file={quote(xtc_url.toString())}")
                    else:
                        params.append(f"xtc_file={quote(xtc_file)}")
                except Exception:
                    params.append(f"xtc_file={quote(xtc_file)}")
            
            # Handle trajectory data (processed frames as JSON)
            if traj_file:
                try:
                    # If a traj index file is provided, prefer that (better performance)
                    # Accept either local file path or already a URL
                    from pathlib import Path as _P
                    if traj_file.startswith("file:"):
                        traj_url = traj_file
                    elif _P(traj_file).exists():
                        traj_url = QUrl.fromLocalFile(str(_P(traj_file).resolve())).toString()
                    else:
                        traj_url = traj_file
                    params.append(f"traj_file={quote(traj_url)}")
                except Exception:
                    pass
            elif traj_data:
                try:
                    encoded_data = base64.b64encode(traj_data.encode('utf-8')).decode('ascii')
                    params.append(f"traj_data={quote(encoded_data)}")
                except Exception:
                    pass
            
            # Add display preferences
            params.append(f"bg={self.get_property('background')}")
            params.append(f"spin={'1' if self.get_property('auto_spin') else '0'}")

            query = ("?" + "&".join(params)) if params else ""
            return base_url.toString() + query
            
        except Exception as e:
            self.logger.error(f"Failed to build GROMACS viewer URL: {e}")
            return ""

    def _convert_gro_to_pdb(self, gro_file: str) -> Optional[str]:
        """Convert GRO file to PDB format for web viewer."""
        try:
            # Try with MDAnalysis first (more robust)
            try:
                import MDAnalysis as mda  # type: ignore
                
                # Load structure from GRO file
                u = mda.Universe(gro_file)
                
                # Convert to PDB text
                from io import StringIO
                output = StringIO()
                
                # Write atoms in PDB format
                for i, atom in enumerate(u.atoms):
                    try:
                        # PDB format: ATOM record
                        record = "ATOM  "
                        atom_num = str(i + 1).rjust(5)
                        atom_name = atom.name.ljust(4)
                        res_name = atom.resname.ljust(3)
                        chain_id = getattr(atom, 'chainID', 'A').ljust(1)
                        res_num = str(atom.resid).rjust(4)
                        x = f"{atom.position[0]:8.3f}"
                        y = f"{atom.position[1]:8.3f}"
                        z = f"{atom.position[2]:8.3f}"
                        occupancy = "  1.00"
                        temp_factor = "  0.00"
                        element = atom.element.rjust(2) if hasattr(atom, 'element') else atom.name[:2].rjust(2)
                        
                        line = f"{record}{atom_num} {atom_name} {res_name} {chain_id}{res_num}    {x}{y}{z}{occupancy}{temp_factor}          {element}\n"
                        output.write(line)
                    except Exception:
                        continue
                
                output.write("TER\nEND\n")
                return output.getvalue()
                
            except ImportError:
                # Fallback: simple GRO parser (without MDAnalysis)
                return self._parse_gro_to_pdb_simple(gro_file)
                
        except Exception as e:
            self.logger.error(f"Failed to convert GRO to PDB: {e}")
            # Try simple parser as last resort
            try:
                return self._parse_gro_to_pdb_simple(gro_file)
            except Exception:
                pass
        return None

    def _parse_gro_to_pdb_simple(self, gro_file: str) -> Optional[str]:
        """Simple GRO to PDB converter without MDAnalysis dependency."""
        try:
            from io import StringIO
            output = StringIO()
            
            with open(gro_file, 'r') as f:
                lines = f.readlines()
            
            if len(lines) < 3:
                return None
                
            # Skip first two lines (title and atom count)
            atom_count = int(lines[1].strip())
            
            for i, line in enumerate(lines[2:2+atom_count]):
                try:
                    # GRO format: resid resname atomname atomid x y z [vx vy vz]
                    if len(line) < 44:  # minimum length for coordinates
                        continue
                        
                    resid = int(line[0:5].strip())
                    resname = line[5:10].strip()
                    atomname = line[10:15].strip()
                    atomid = int(line[15:20].strip())
                    
                    # Coordinates in nm, convert to Angstrom
                    x = float(line[20:28].strip()) * 10.0
                    y = float(line[28:36].strip()) * 10.0  
                    z = float(line[36:44].strip()) * 10.0
                    
                    # Guess element from atom name
                    element = atomname[0].upper()
                    if len(atomname) > 1 and atomname[1].islower():
                        element = atomname[:2].capitalize()
                    
                    # PDB format
                    record = "ATOM  "
                    atom_num = str(i + 1).rjust(5)
                    atom_name = atomname.ljust(4)
                    res_name = resname.ljust(3)
                    chain_id = "A"
                    res_num = str(resid).rjust(4)
                    x_str = f"{x:8.3f}"
                    y_str = f"{y:8.3f}"
                    z_str = f"{z:8.3f}"
                    occupancy = "  1.00"
                    temp_factor = "  0.00"
                    element_str = element.rjust(2)
                    
                    line_pdb = f"{record}{atom_num} {atom_name} {res_name} {chain_id}{res_num}    {x_str}{y_str}{z_str}{occupancy}{temp_factor}          {element_str}\n"
                    output.write(line_pdb)
                    
                except Exception as e:
                    continue
            
            output.write("TER\nEND\n")
            result = output.getvalue()
            
            if len(result.split('\n')) > 2:  # At least some atoms converted
                return result
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"Simple GRO parser failed: {e}")
            return None

    def _process_trajectory_data(self, gro_file: str, xtc_file: Optional[str]) -> Optional[str]:
        """Process MD trajectory for web viewer (synchronous version for single GRO)."""
        try:
            if not xtc_file:
                # Only structure, no trajectory - this should work quickly
                pdb_data = self._convert_gro_to_pdb(gro_file)
                if pdb_data:
                    import json
                    traj_json = {
                        "frames": [pdb_data],
                        "frame_count": 1
                    }
                    return json.dumps(traj_json)
                return None
            
            # For trajectory files, we'll process asynchronously
            self.logger.info("XTC trajectory detected - will process asynchronously")
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to process trajectory: {e}")
            return None

    def _process_trajectory_async(self, gro_file: str, xtc_file: str):
        """Start asynchronous trajectory processing."""
        try:
            from PySide6.QtCore import QThread, QObject, Signal
            
            class TrajectoryWorker(QObject):
                finished = Signal(str, int)  # traj_data OR traj_file (URL), frame_count
                error = Signal(str)
                progress = Signal(int, str)
                
                def __init__(self, gro_file: str, xtc_file: str, parent_node):
                    super().__init__()
                    self.gro_file = gro_file
                    self.xtc_file = xtc_file
                    self.parent_node = parent_node
                
                def process(self):
                    try:
                        self.progress.emit(5, "Checking trajectory files...")
                        
                        # Validate files exist
                        from pathlib import Path
                        if not Path(self.gro_file).exists():
                            self.error.emit(f"GRO file not found: {self.gro_file}")
                            return
                        if not Path(self.xtc_file).exists():
                            self.error.emit(f"XTC file not found: {self.xtc_file}")
                            return
                        
                        self.progress.emit(10, "Loading trajectory...")
                        
                        import MDAnalysis as mda  # type: ignore
                        
                        # Load trajectory with better error handling
                        try:
                            u = mda.Universe(self.gro_file, self.xtc_file)
                        except Exception as e:
                            self.error.emit(f"Failed to load MD files: {str(e)}")
                            return
                        
                        total_frames = len(u.trajectory)
                        
                        # Decide sampling to cap to ~50 frames
                        max_frames = min(50, total_frames)
                        step = max(1, total_frames // max_frames)
                        self.progress.emit(20, f"Processing {max_frames} frames from {total_frames} total...")
                        
                        # Prepare temp output directory for frames
                        from backend.temp_manager import get_subdir
                        import uuid as _uuid
                        out_base = get_subdir(f"gmx_traj_{_uuid.uuid4().hex[:8]}")
                        frames_dir = out_base / "frames"
                        frames_dir.mkdir(parents=True, exist_ok=True)
                        
                        frame_file_urls = []
                        
                        idx = 0
                        i = 0
                        try:
                            # Use range by counting idx up to max_frames
                            while idx < max_frames and i < total_frames:
                                try:
                                    u.trajectory[i]
                                    # Convert frame to PDB text
                                    from io import StringIO
                                    output = StringIO()
                                    for j, atom in enumerate(u.atoms):
                                        try:
                                            record = "ATOM  "
                                            atom_num = str(j + 1).rjust(5)
                                            atom_name = atom.name.ljust(4)
                                            res_name = atom.resname.ljust(3)
                                            chain_id = getattr(atom, 'chainID', 'A').ljust(1)
                                            res_num = str(atom.resid).rjust(4)
                                            x = f"{atom.position[0]:8.3f}"
                                            y = f"{atom.position[1]:8.3f}"
                                            z = f"{atom.position[2]:8.3f}"
                                            occupancy = "  1.00"
                                            temp_factor = "  0.00"
                                            element = atom.element.rjust(2) if hasattr(atom, 'element') else atom.name[:2].rjust(2)
                                            
                                            line = f"{record}{atom_num} {atom_name} {res_name} {chain_id}{res_num}    {x}{y}{z}{occupancy}{temp_factor}          {element}\n"
                                            output.write(line)
                                        except Exception:
                                            continue
                                    output.write("TER\nEND\n")
                                    
                                    # Write to file
                                    frame_path = frames_dir / f"frame_{idx:04d}.pdb"
                                    frame_text = output.getvalue()
                                    frame_path.write_text(frame_text, encoding="utf-8")
                                    frame_file_urls.append(frame_path.as_uri())
                                    
                                    # Progress
                                    progress = 20 + int((idx / max_frames) * 70)
                                    self.progress.emit(progress, f"Frame {idx+1}/{max_frames} (source frame {i+1})")
                                    
                                    idx += 1
                                    i += step
                                except Exception as e:
                                    # Skip problematic frame, continue
                                    i += step
                                    continue
                        except Exception as _e:
                            pass
                        
                        if not frame_file_urls:
                            self.error.emit("No frames could be processed from trajectory")
                            return
                        
                        self.progress.emit(95, "Finalizing trajectory index...")
                        
                        # Write index.json
                        import json
                        index_data = {
                            "frameFiles": frame_file_urls,
                            "frame_count": len(frame_file_urls),
                            "source_frame_count": total_frames
                        }
                        index_path = out_base / "index.json"
                        index_path.write_text(json.dumps(index_data), encoding="utf-8")
                        
                        self.progress.emit(100, f"Complete! Processed {len(frame_file_urls)} frames")
                        # Return file URL to index.json so the viewer can fetch lazily
                        self.finished.emit(index_path.as_uri(), total_frames)
                        
                    except ImportError:
                        self.error.emit("MDAnalysis not available for trajectory processing. Please install MDAnalysis.")
                    except Exception as e:
                        self.error.emit(f"Trajectory processing failed: {str(e)}")
            
            # Check if already processing and stop previous thread
            if hasattr(self, '_traj_thread') and self._traj_thread and self._traj_thread.isRunning():
                self.logger.warning("Stopping previous trajectory processing")
                self._traj_thread.quit()
                self._traj_thread.wait(3000)  # Wait up to 3 seconds
                if self._traj_thread.isRunning():
                    self._traj_thread.terminate()
                    self._traj_thread.wait(1000)
            
            # Create worker and thread
            self._traj_thread = QThread(self)  # Set parent to prevent premature destruction
            self._traj_worker = TrajectoryWorker(gro_file, xtc_file, self)
            self._traj_worker.moveToThread(self._traj_thread)
            
            # Connect signals with Qt.QueuedConnection for thread safety
            from PySide6.QtCore import Qt
            self._traj_thread.started.connect(self._traj_worker.process, Qt.QueuedConnection)
            self._traj_worker.finished.connect(self._on_trajectory_ready, Qt.QueuedConnection)
            self._traj_worker.error.connect(self._on_trajectory_error, Qt.QueuedConnection)
            self._traj_worker.progress.connect(self._on_trajectory_progress, Qt.QueuedConnection)
            
            # Cleanup when done - use Qt.QueuedConnection for thread safety
            self._traj_worker.finished.connect(self._cleanup_trajectory_thread, Qt.QueuedConnection)
            self._traj_worker.error.connect(self._cleanup_trajectory_thread, Qt.QueuedConnection)
            
            # Start processing
            self._traj_thread.start()
            self.logger.info("Started asynchronous trajectory processing")
            
        except Exception as e:
            self.logger.error(f"Failed to start trajectory processing: {e}")
            self._on_trajectory_error(str(e))

    def _cleanup_trajectory_thread(self):
        """Clean up trajectory processing thread safely."""
        try:
            if hasattr(self, '_traj_thread') and self._traj_thread:
                self._traj_thread.quit()
                if not self._traj_thread.wait(2000):  # Wait 2 seconds
                    self._traj_thread.terminate()
                    self._traj_thread.wait(1000)
                self._traj_thread.deleteLater()
                self._traj_thread = None
            
            if hasattr(self, '_traj_worker') and self._traj_worker:
                self._traj_worker.deleteLater()
                self._traj_worker = None
        except Exception as e:
            self.logger.error(f"Error cleaning up trajectory thread: {e}")

    def _on_trajectory_ready(self, traj_data: str, frame_count: int = 1):
        """Handle completion of asynchronous trajectory processing."""
        try:
            self.logger.info(f"Trajectory processing completed with {frame_count} frames, data length: {len(traj_data) if traj_data else 0}")
            
            # Update frame count property
            try:
                self.set_property("frame_count", frame_count)
            except Exception:
                pass
            
            # Update viewer with processed data
            if hasattr(self, '_inline_webview') and self._inline_webview and traj_data:
                # Detect if we received a file URL (preferred) or inline JSON
                if isinstance(traj_data, str) and traj_data.startswith("file:"):
                    url = self._build_gromacs_viewer_url(traj_file=traj_data)
                else:
                    url = self._build_gromacs_viewer_url(traj_data=traj_data)
                self.logger.info(f"Built trajectory viewer URL: {len(url)} characters")
                
                if url:
                    from PySide6.QtCore import QUrl
                    qurl = QUrl(url)
                    self.logger.info(f"Loading trajectory URL in inline viewer: {qurl.toString()[:200]}...")
                    
                    # Force load the URL
                    self._inline_webview.setUrl(qurl)
                    self._inline_webview.load(qurl)
                else:
                    self._on_trajectory_error("Failed to build viewer URL")
            else:
                if not hasattr(self, '_inline_webview'):
                    self.logger.warning("No inline webview available for trajectory")
                elif not self._inline_webview:
                    self.logger.warning("Inline webview is None for trajectory")
                elif not traj_data:
                    self.logger.warning("No trajectory data to display")
            
            # Update external viewer if open
            viewer_window = getattr(self, "_viewer_window", None)
            if viewer_window is not None and traj_data:
                if isinstance(traj_data, str) and traj_data.startswith("file:"):
                    url = self._build_gromacs_viewer_url(traj_file=traj_data)
                else:
                    url = self._build_gromacs_viewer_url(traj_data=traj_data)
                if url:
                    try:
                        viewer_window.load_viewer_url(url)
                    except Exception:
                        pass
                        
        except Exception as e:
            self.logger.error(f"Failed to update viewer with trajectory: {e}")
            self._on_trajectory_error(str(e))

    def _on_trajectory_error(self, error_msg: str):
        """Handle trajectory processing errors."""
        self.logger.error(f"Trajectory processing failed: {error_msg}")
        
        # Show error in viewer
        try:
            error_html = f"""
            <html><body style='background-color:#000; margin:0; display:flex; align-items:center; justify-content:center; color:#fff; font-family:Arial;'>
                <div style='text-align:center;'>
                    <div style='font-size:18px; margin-bottom:10px; color:#ff6b6b;'>❌ Trajectory Processing Failed</div>
                    <div style='font-size:14px; color:#aaa; margin-bottom:15px;'>{error_msg[:100]}{'...' if len(error_msg) > 100 else ''}</div>
                    <div style='font-size:12px; color:#666;'>Attempting to show structure only...</div>
                </div>
            </body></html>
            """
            if hasattr(self, '_inline_webview') and self._inline_webview:
                self._inline_webview.setHtml(error_html)
        except Exception:
            pass
        
        # Fallback to GRO-only display
        try:
            gro_file = self.get_property("gro_path")
            if gro_file:
                # Use async processing for GRO fallback too
                self._process_gro_async(gro_file)
        except Exception as e:
            self.logger.error(f"Fallback to GRO failed: {e}")

    def _on_trajectory_progress(self, percent: int, message: str):
        """Handle trajectory processing progress updates with visual feedback."""
        self.logger.info(f"Trajectory processing: {percent}% - {message}")
        
        # Update the viewer with progress information
        try:
            if hasattr(self, '_inline_webview') and self._inline_webview:
                progress_html = f"""
                <html><body style='background-color:#000; margin:0; display:flex; align-items:center; justify-content:center; color:#fff; font-family:Arial;'>
                    <div style='text-align:center;'>
                        <div style='font-size:18px; margin-bottom:15px;'>Processing MD Trajectory...</div>
                        <div style='width:300px; height:6px; background:#333; border-radius:3px; margin:0 auto 15px;'>
                            <div style='width:{percent}%; height:100%; background:linear-gradient(90deg, #4CAF50, #45a049); border-radius:3px; transition:width 0.3s ease;'></div>
                        </div>
                        <div style='font-size:14px; color:#aaa; margin-bottom:5px;'>{percent}% Complete</div>
                        <div style='font-size:12px; color:#666;'>{message}</div>
                    </div>
                </body></html>
                """
                self._inline_webview.setHtml(progress_html)
        except Exception:
            pass

    def _on_open_viewer(self):
        """Open the GROMACS MD viewer window."""
        try:
            gro_file = self.get_property("gro_path")
            xtc_file = self.get_property("xtc_path")
            
            if not gro_file:
                self.logger.warning("No GRO file available to view")
                return
            
            # Build viewer URL
            url = self._build_gromacs_viewer_url(gro_file, xtc_file)
            
            if not url:
                self.logger.error("Failed to build viewer URL")
                return
            
            # Open in external viewer window
            from core.webviewer import MoleculeWebViewerWindow
            win = MoleculeWebViewerWindow()
            win.setWindowTitle("GROMACS MD Trajectory Viewer")
            win.load_viewer_url(url)
            win.show()
            self._viewer_window = win
            
        except Exception as e:
            self.logger.error(f"Failed to open GROMACS viewer: {e}")

    def _update_inline_viewer(self) -> None:
        """Update the embedded viewer with current data."""
        try:
            if not hasattr(self, '_inline_webview') or not self._inline_webview:
                return
            
            gro_file = self.get_property("gro_path")
            xtc_file = self.get_property("xtc_path")
            
            if not gro_file:
                # Show default message
                default_html = """
                <html><body style='background-color:#000; margin:0; display:flex; align-items:center; justify-content:center; color:#fff; font-family:Arial;'>
                    <div style='text-align:center;'>
                        <div style='font-size:18px; margin-bottom:10px;'>📁 Load MD Trajectory to view</div>
                        <div style='font-size:14px; color:#aaa;'>Connect GRO and/or XTC files</div>
                    </div>
                </body></html>
                """
                self._inline_webview.setHtml(default_html)
                return
            
            if xtc_file:
                # For trajectory files, check if already processing
                if hasattr(self, '_traj_thread') and self._traj_thread and self._traj_thread.isRunning():
                    # Already processing, don't start again
                    return
                
                # Show loading message in viewer
                loading_html = """
                <html><body style='background-color:#000; margin:0; display:flex; align-items:center; justify-content:center; color:#fff; font-family:Arial;'>
                    <div style='text-align:center;'>
                        <div style='font-size:18px; margin-bottom:10px;'>🔄 Processing MD Trajectory...</div>
                        <div style='font-size:14px; color:#aaa;'>This may take a few moments</div>
                        <div style='font-size:12px; color:#666; margin-top:10px;'>Processing up to 50 frames for web viewer</div>
                    </div>
                </body></html>
                """
                self._inline_webview.setHtml(loading_html)
                
                # Start async processing
                self.logger.info("Starting XTC trajectory processing...")
                self._process_trajectory_async(gro_file, xtc_file)
            else:
                # For GRO-only files, process in thread to avoid UI blocking
                self._process_gro_async(gro_file)
                    
        except Exception as e:
            self.logger.error(f"Failed to update inline viewer: {e}")
            # Show error in viewer
            try:
                error_html = f"""
                <html><body style='background-color:#000; margin:0; display:flex; align-items:center; justify-content:center; color:#fff; font-family:Arial;'>
                    <div style='text-align:center;'>
                        <div style='font-size:18px; margin-bottom:10px; color:#ff6b6b;'>❌ Error</div>
                        <div style='font-size:14px; color:#aaa;'>{str(e)[:100]}{'...' if len(str(e)) > 100 else ''}</div>
                    </div>
                </body></html>
                """
                if hasattr(self, '_inline_webview') and self._inline_webview:
                    self._inline_webview.setHtml(error_html)
            except Exception:
                pass

    def _process_gro_async(self, gro_file: str):
        """Process GRO file asynchronously to avoid UI blocking."""
        try:
            from PySide6.QtCore import QThread, QObject, Signal
            
            class GroWorker(QObject):
                finished = Signal(str)
                error = Signal(str)
                
                def __init__(self, gro_file: str, parent_node):
                    super().__init__()
                    self.gro_file = gro_file
                    self.parent_node = parent_node
                
                def process(self):
                    try:
                        # Process GRO file
                        traj_data = self.parent_node._process_trajectory_data(self.gro_file, None)
                        if traj_data:
                            self.finished.emit(traj_data)
                        else:
                            self.error.emit("Failed to convert GRO file")
                    except Exception as e:
                        self.error.emit(str(e))
            
            # Stop any existing GRO processing
            if hasattr(self, '_gro_thread') and self._gro_thread and self._gro_thread.isRunning():
                self._gro_thread.quit()
                self._gro_thread.wait(1000)
                if self._gro_thread.isRunning():
                    self._gro_thread.terminate()
                    self._gro_thread.wait(500)
            
            # Create worker and thread
            self._gro_thread = QThread(self)  # Set parent to prevent premature destruction
            self._gro_worker = GroWorker(gro_file, self)
            self._gro_worker.moveToThread(self._gro_thread)
            
            # Connect signals with Qt.QueuedConnection for thread safety
            from PySide6.QtCore import Qt
            self._gro_thread.started.connect(self._gro_worker.process, Qt.QueuedConnection)
            self._gro_worker.finished.connect(self._on_gro_ready, Qt.QueuedConnection)
            self._gro_worker.error.connect(self._on_gro_error, Qt.QueuedConnection)
            
            # Cleanup when done
            self._gro_worker.finished.connect(self._cleanup_gro_thread, Qt.QueuedConnection)
            self._gro_worker.error.connect(self._cleanup_gro_thread, Qt.QueuedConnection)
            
            # Start processing
            self._gro_thread.start()
            
        except Exception as e:
            self.logger.error(f"Failed to start GRO processing: {e}")
            self._on_gro_error(str(e))
    
    def _cleanup_gro_thread(self):
        """Clean up GRO processing thread safely."""
        try:
            if hasattr(self, '_gro_thread') and self._gro_thread:
                self._gro_thread.quit()
                if not self._gro_thread.wait(1000):  # Wait 1 second
                    self._gro_thread.terminate()
                    self._gro_thread.wait(500)
                self._gro_thread.deleteLater()
                self._gro_thread = None
            
            if hasattr(self, '_gro_worker') and self._gro_worker:
                self._gro_worker.deleteLater()
                self._gro_worker = None
        except Exception as e:
            self.logger.error(f"Error cleaning up GRO thread: {e}")
    
    def _on_gro_ready(self, traj_data: str):
        """Handle completion of GRO processing."""
        try:
            self.logger.info("GRO processing completed")
            
            # Update viewer with processed data
            if hasattr(self, '_inline_webview') and self._inline_webview:
                gro_file = self.get_property("gro_path")
                url = self._build_gromacs_viewer_url(gro_file=gro_file)
                self.logger.info(f"Built GRO viewer URL: {len(url)} characters")
                if url:
                    from PySide6.QtCore import QUrl
                    qurl = QUrl(url)
                    self.logger.info(f"Loading URL in inline viewer: {qurl.toString()[:200]}...")
                    self._inline_webview.setUrl(qurl)
                    self._inline_webview.load(qurl)
                else:
                    self._on_gro_error("Failed to build viewer URL")
            else:
                if not hasattr(self, '_inline_webview'):
                    self.logger.warning("No inline webview available")
                elif not self._inline_webview:
                    self.logger.warning("Inline webview is None")
                else:
                    self.logger.warning("Inline webview not ready to display GRO")
            
        except Exception as e:
            self.logger.error(f"Failed to update viewer with GRO data: {e}")
            self._on_gro_error(str(e))
    
    def _on_gro_error(self, error_msg: str):
        """Handle GRO processing errors."""
        self.logger.error(f"GRO processing failed: {error_msg}")
        
        try:
            error_html = f"""
            <html><body style='background-color:#000; margin:0; display:flex; align-items:center; justify-content:center; color:#fff; font-family:Arial;'>
                <div style='text-align:center;'>
                    <div style='font-size:18px; margin-bottom:10px; color:#ff6b6b;'>❌ Failed to load structure</div>
                    <div style='font-size:14px; color:#aaa;'>Check if the GRO file is valid</div>
                    <div style='font-size:12px; color:#666; margin-top:10px;'>{error_msg[:80]}{'...' if len(error_msg) > 80 else ''}</div>
                </div>
            </body></html>
            """
            if hasattr(self, '_inline_webview') and self._inline_webview:
                self._inline_webview.setHtml(error_html)
        except Exception:
            pass
