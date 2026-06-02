"""GromacsProductionNode implementation."""

from .common import *  # noqa: F401,F403

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
