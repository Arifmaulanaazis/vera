"""XTCExtractorNode implementation."""

from .common import *  # noqa: F401,F403

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
