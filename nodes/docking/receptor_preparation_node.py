"""ReceptorPreparationNode implementation."""

from .common import *  # noqa: F401,F403

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
