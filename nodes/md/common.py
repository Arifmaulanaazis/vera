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

# Re-export every helper/import so split node files keep the original module namespace.
__all__ = [name for name in globals() if not name.startswith("__")]
