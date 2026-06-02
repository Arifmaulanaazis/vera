"""LigandPreparationNode implementation."""

from .common import *  # noqa: F401,F403

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
