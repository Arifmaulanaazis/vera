"""MergeMoleculeNode implementation."""

from .common import *  # noqa: F401,F403

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
