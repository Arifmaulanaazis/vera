"""MDAnalysisNode implementation."""

from .common import *  # noqa: F401,F403

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
