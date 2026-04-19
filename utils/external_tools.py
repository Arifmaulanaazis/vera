"""
Helpers to resolve external executables (GROMACS, Vina, OpenBabel)
from the project's bundled engines first, then fall back to PATH.

Also contains small command builders for GROMACS.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional, List


def _project_root() -> Path:
    # utils/ -> project root
    return Path(__file__).resolve().parent.parent


def _find_latest_exe(dir_path: Path, pattern: str) -> Optional[str]:
    """Find the latest versioned exe in dir_path matching pattern (regex)."""
    if not dir_path.exists():
        return None
    best: tuple[Optional[str], tuple[int, ...]] = (None, ())
    for p in dir_path.glob("*.exe"):
        m = re.search(pattern, p.name)
        if not m:
            continue
        # Extract version numbers if present
        version_str = "".join(m.groups()) if m.groups() else ""
        # Split digits from version e.g. 1.2.6 -> (1,2,6)
        nums = tuple(int(x) for x in re.findall(r"\d+", version_str)) if version_str else ()
        if best[0] is None or nums > best[1]:
            best = (str(p), nums)
    return best[0]


def resolve_gromacs_executable(version: Optional[str] = None, use_gpu: Optional[bool] = None) -> str:
    """Resolve the 'gmx' command.

    Preference order:
    1) Bundled engine: engine/gromacs/gromacs_<version>_{cpu,cuda}/bin/gmx(.exe)
    2) PATH: gmx-<version>, gmx, gmx.exe
    """
    root = _project_root()
    eng = root / "engine" / "gromacs"
    # Try bundled dirs if present
    if eng.exists():
        # Build candidate directories
        dirs: List[Path] = []
        # If explicit version known in bundle naming (e.g. 2025.1)
        if version:
            cpu_dir = eng / f"gromacs_{version}_cpu" / "bin"
            gpu_dir = eng / f"gromacs_{version}_cuda" / "bin"
            if use_gpu is True:
                dirs += [gpu_dir, cpu_dir]
            elif use_gpu is False:
                dirs += [cpu_dir, gpu_dir]
            else:
                dirs += [cpu_dir, gpu_dir]
        # Fallback: search any bundled gromacs_* dirs (prefer cuda if requested)
        for d in sorted(eng.glob("gromacs_*_cuda/bin")):
            if d not in dirs and (use_gpu in (None, True)):
                dirs.append(d)
        for d in sorted(eng.glob("gromacs_*_cpu/bin")):
            if d not in dirs and (use_gpu in (None, False)):
                dirs.append(d)
        for d in dirs:
            exe = d / ("gmx.exe" if shutil.which("cmd.exe") else "gmx")
            if exe.exists():
                return str(exe)

    # PATH fallbacks
    candidates: List[str] = []
    if version:
        candidates += [f"gmx-{version}"]
    candidates += ["gmx"]
    for c in candidates:
        exe = shutil.which(c)
        if exe:
            return exe
    exe = shutil.which("gmx.exe")
    if exe:
        return exe
    raise FileNotFoundError("GROMACS executable not found. Ensure bundled engine exists or gmx is in PATH.")


def build_grompp_command(gmx: str, mdp: str, structure: str, topology: str, deffnm: str) -> List[str]:
    return [gmx, "grompp", "-f", mdp, "-c", structure, "-p", topology, "-o", f"{deffnm}.tpr", "-maxwarn", "1"]


def build_mdrun_command(gmx: str, deffnm: str, use_gpu: bool, threads: int) -> List[str]:
    cmd = [gmx, "mdrun", "-deffnm", deffnm]
    if threads and threads > 0:
        cmd += ["-nt", str(threads)]
    if use_gpu:
        # Modern GROMACS uses auto GPU detection; for older builds: add -gpu_id 0
        cmd += ["-gpu_id", "0"]
    return cmd




# --- AutoDock Vina family ---

def resolve_vina_executable(version: Optional[str] = None) -> str:
    """Resolve AutoDock Vina executable from bundled backend/vina or PATH.

    If version is None, pick the highest available version in the bundle.
    """
    root = _project_root()
    # Prefer engine/vina then backend/vina
    candidates_dirs = [root / "engine" / "vina", root / "backend" / "vina"]
    vina_dir = None
    for d in candidates_dirs:
        if d.exists():
            vina_dir = d
            break
    # Bundled selection
    if vina_dir and vina_dir.exists():
        if version:
            # Try exact version match by filename convention
            candidates = list(vina_dir.glob(f"vina_{version}_windows.exe"))
            if candidates:
                return str(candidates[0])
        # Fallback to latest
        latest = _find_latest_exe(vina_dir, r"(\d+\.\d+\.\d+)")
        if latest:
            return latest
    # PATH fallback
    exe = shutil.which("vina") or shutil.which("vina.exe")
    if exe:
        return exe
    raise FileNotFoundError("AutoDock Vina executable not found. Provide it under backend/vina or set PATH.")


def resolve_vina_gpu_executable() -> str:
    root = _project_root()
    vg_dir = root / "engine" / "vina_gpu"
    if not vg_dir.exists():
        vg_dir = root / "backend" / "vina_gpu"
    if vg_dir.exists():
        latest = _find_latest_exe(vg_dir, r"(\d+\.\d+\.\d+)")
        if latest:
            return latest
        # If versions not embedded, pick any vina*.exe
        for p in vg_dir.glob("*.exe"):
            return str(p)
    exe = shutil.which("vina_gpu") or shutil.which("vina_gpu.exe")
    if exe:
        return exe
    raise FileNotFoundError("AutoDock Vina GPU executable not found. Provide it under backend/vina_gpu or set PATH.")


def resolve_vina_split_executable(version: Optional[str] = None) -> str:
    root = _project_root()
    vs_dir = root / "engine" / "vina_split"
    if not vs_dir.exists():
        vs_dir = root / "backend" / "vina_split"
    if vs_dir.exists():
        if version:
            candidates = list(vs_dir.glob(f"vina_split_{version}_windows.exe"))
            if candidates:
                return str(candidates[0])
        latest = _find_latest_exe(vs_dir, r"(\d+\.\d+\.\d+)")
        if latest:
            return latest
        for p in vs_dir.glob("vina_split*.exe"):
            return str(p)
    exe = shutil.which("vina_split") or shutil.which("vina_split.exe")
    if exe:
        return exe
    raise FileNotFoundError("vina_split executable not found. Provide it under backend/vina_split or set PATH.")


def resolve_openbabel_executable(tool: str) -> str:
    """Resolve an OpenBabel tool (e.g., 'obabel', 'obminimize') to bundled exe or PATH."""
    root = _project_root()
    ob_dir = root / "engine" / "openbabel"
    if not ob_dir.exists():
        ob_dir = root / "backend" / "openbabel"
    if ob_dir.exists():
        exe = ob_dir / f"{tool}.exe"
        if exe.exists():
            return str(exe)
    exe = shutil.which(tool) or shutil.which(f"{tool}.exe")
    if exe:
        return exe
    raise FileNotFoundError(f"OpenBabel tool '{tool}' not found. Provide it under backend/openbabel or set PATH.")


