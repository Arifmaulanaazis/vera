"""GridSearchNode implementation."""

from .common import *  # noqa: F401,F403

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
