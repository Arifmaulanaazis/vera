"""StructureDraw2DNode implementation."""

from .common import *  # noqa: F401,F403

class StructureDraw2DNode(BaseNode):
    """Draw 2D structures from RDKit molecules or SMILES.

    Inputs:
      - molecules (molecules): list of RDKit Mol objects (protein/ligand/complex supported)
      - smiles_df (data): pandas.DataFrame or list-of-dicts or list[str] of SMILES
      - smiles (string): single SMILES

    Outputs:
      - image (image): PNG bytes of the rendered image
      - bytes (bytes): PNG bytes (duplicate for convenience)

    Customization (properties):
      - background: hex color string (e.g. '#ffffff')
      - cell_width, cell_height: per-panel size (int)
      - mode: 'auto' | 'single' | 'grid' (rendering layout)
      - grid_cols: number of columns in grid mode (int)
      - kekulize: bool
      - atom_indices: bool (annotate atom indices)
      - max_mols: int (limit number of molecules drawn)
      - prefer_coordgen: bool (use RDKit CoordGen if available)
    """

    def __init__(self):
        super().__init__("structure_draw_2d", "2D Structure Draw")
        self.logger = get_logger(__name__)

        # Inputs
        self.add_input_port("molecules", "molecules")
        self.add_input_port("smiles_df", "data")
        self.add_input_port("smiles", "string")

        # Outputs
        self.add_output_port("image", "image")
        self.add_output_port("bytes", "bytes")

        # Defaults
        self.set_property("background", "#ffffff")
        self.set_property("cell_width", 300)
        self.set_property("cell_height", 300)
        self.set_property("mode", "auto")  # auto | single | grid
        self.set_property("grid_cols", 4)
        self.set_property("kekulize", True)
        self.set_property("atom_indices", False)
        self.set_property("max_mols", 25)
        self.set_property("prefer_coordgen", True)
        self.set_property("skip_large_molecules", True)
        self.set_property("max_atoms", 200)
        self.set_property("max_total_pixels", 4_000_000)  # safety cap for composed image size
        self.set_property("use_text_placeholder_for_bondless", True)

    def _log(self, message: object) -> None:
        """Lightweight logger used in both GUI and headless execution."""
        try:
            text = str(message)
        except Exception:
            text = repr(message)
        try:
            self.logger.info(text)
        except Exception:
            try:
                print(f"[2D Structure Draw] {text}")
            except Exception:
                pass

    # --- helpers ---
    def _parse_hex_color(self, s: str) -> tuple[float, float, float]:
        try:
            s = (s or "").strip()
            if s.startswith("#"):
                s = s[1:]
            if len(s) == 3:
                s = "".join(ch * 2 for ch in s)
            r = int(s[0:2], 16) / 255.0
            g = int(s[2:4], 16) / 255.0
            b = int(s[4:6], 16) / 255.0
            return (r, g, b)
        except Exception:
            return (1.0, 1.0, 1.0)

    def _collect_smiles(self, data_obj: Any) -> List[str]:
        try:
            # Direct list[str]
            if isinstance(data_obj, list) and (len(data_obj) == 0 or isinstance(data_obj[0], str)):
                return [s for s in data_obj if isinstance(s, str) and s.strip()]
            # pandas.DataFrame
            try:
                import pandas as pd  # type: ignore
                if isinstance(data_obj, pd.DataFrame):
                    if data_obj.shape[1] == 1:
                        col = data_obj.columns[0]
                        return [str(x) for x in data_obj[col].dropna().astype(str).tolist() if str(x).strip()]
                    for name in ["SMILES", "smiles", "Smiles"]:
                        if name in data_obj.columns:
                            return [str(x) for x in data_obj[name].dropna().astype(str).tolist() if str(x).strip()]
            except Exception:
                pass
            # list-of-dicts
            if isinstance(data_obj, list) and (len(data_obj) == 0 or isinstance(data_obj[0], dict)):
                keys = set()
                for r in data_obj:
                    try:
                        keys.update(r.keys())
                    except Exception:
                        pass
                key = None
                if len(keys) == 1:
                    key = list(keys)[0]
                else:
                    for k in ["SMILES", "smiles", "Smiles"]:
                        if k in keys:
                            key = k
                            break
                if key is not None:
                    vals = []
                    for r in data_obj:
                        try:
                            vals.append(r.get(key))
                        except Exception:
                            pass
                    return [str(v) for v in vals if isinstance(v, (str, int, float)) and str(v).strip()]
        except Exception:
            pass
        return []

    def _collect_molecules(self, inputs: Optional[Dict[str, Any]]) -> List[Any]:
        mols: List[Any] = []
        try:
            from rdkit import Chem  # type: ignore
        except Exception:
            return []

        # From molecules input
        try:
            if inputs and inputs.get("molecules"):
                if isinstance(inputs["molecules"], list):
                    mols.extend([m for m in inputs["molecules"] if m is not None])
                else:
                    mols.append(inputs["molecules"])  # tolerate single mol
        except Exception:
            pass

        # From smiles_df
        try:
            data_obj = (inputs or {}).get("smiles_df")
            for smi in self._collect_smiles(data_obj):
                try:
                    m = Chem.MolFromSmiles(smi)
                    if m is not None:
                        mols.append(m)
                except Exception:
                    pass
        except Exception:
            pass

        # From single smiles
        try:
            smi = (inputs or {}).get("smiles")
            if isinstance(smi, (str, bytes)):
                smi_str = smi.decode("utf-8") if isinstance(smi, bytes) else smi
                smi_str = smi_str.strip()
                if smi_str:
                    m = Chem.MolFromSmiles(smi_str)
                    if m is not None:
                        mols.append(m)
        except Exception:
            pass

        # Sanitization pass for PDB ligands that may miss bonds (proximity bonding earlier may help but ensure valence)
        try:
            for i, m in enumerate(list(mols)):
                try:
                    Chem.SanitizeMol(m, catchErrors=True)
                except Exception:
                    pass
        except Exception:
            pass

        return mols

    def _filter_large(self, mols: List[Any]) -> List[Any]:
        try:
            skip = bool(self.get_property("skip_large_molecules"))
            max_atoms = int(self.get_property("max_atoms") or 200)
        except Exception:
            skip = True
            max_atoms = 200

        if not skip:
            return mols
        filtered: List[Any] = []
        for m in mols:
            try:
                if m is None:
                    continue
                if m.GetNumAtoms() <= max_atoms:
                    filtered.append(m)
            except Exception:
                # If cannot determine size, keep it
                filtered.append(m)
        return filtered

    def _prepare_2d(self, mols: List[Any]) -> List[Any]:
        try:
            from rdkit.Chem import AllChem  # type: ignore
            from rdkit.Chem import rdDepictor  # type: ignore
        except Exception:
            return mols

        prefer_coordgen = bool(self.get_property("prefer_coordgen"))
        prepared: List[Any] = []
        for m in mols:
            if m is None:
                continue
            try:
                if m.GetNumConformers() == 0:
                    # Generate 2D coords; prefer CoordGen if available
                    if prefer_coordgen:
                        try:
                            rdDepictor.SetPreferCoordGen(True)
                        except Exception:
                            pass
                    try:
                        AllChem.Compute2DCoords(m)
                    except Exception:
                        try:
                            # Fallback attempt
                            rdDepictor.Compute2DCoords(m)
                        except Exception:
                            pass
            except Exception:
                pass
            prepared.append(m)
        return prepared

    def _draw_single_png(self, mol, width: int, height: int, bg: tuple[float, float, float], kekulize: bool, atom_indices: bool) -> Optional[bytes]:
        # Strictly use PIL-based path to avoid platform-specific crashes with Cairo
        from rdkit.Chem import Draw  # type: ignore
        from PIL import Image, ImageDraw  # type: ignore
        import io

        # Handle molecules with no bonds to avoid RDKit depict hang
        try:
            if hasattr(mol, "GetNumBonds") and mol.GetNumBonds() == 0:
                if bool(self.get_property("use_text_placeholder_for_bondless")):
                    bg_rgb = tuple(int(x * 255) for x in bg)
                    img = Image.new("RGB", (width, height), bg_rgb)
                    try:
                        draw = ImageDraw.Draw(img)
                        text = f"atoms:{mol.GetNumAtoms()}\nno bonds"
                        draw.text((8, 8), text, fill=(0, 0, 0))
                    except Exception:
                        pass
                    out = io.BytesIO()
                    img.save(out, format="PNG")
                    return out.getvalue()
        except Exception:
            pass

        # Base image from RDKit (PIL image). Ensure non-interactive draw.
        try:
            from rdkit.Chem.Draw import rdMolDraw2D  # type: ignore
            drawer = rdMolDraw2D.MolDraw2DCairo(width, height)
            if not kekulize:
                try:
                    rdMolDraw2D.PrepareMolForDrawing(mol, kekulize=False)
                except Exception:
                    pass
            drawer.DrawMolecule(mol)
            drawer.FinishDrawing()
            png_bytes = drawer.GetDrawingText()
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        except Exception:
            img = Draw.MolToImage(mol, size=(width, height), kekulize=kekulize)

        # Atom indices overlay (simple approach)
        if atom_indices:
            try:
                draw = ImageDraw.Draw(img)
                idx_text = f"atoms:{mol.GetNumAtoms()}"
                draw.rectangle([(0, 0), (len(idx_text) * 7 + 6, 16)], fill=(255, 255, 255))
                draw.text((3, 2), idx_text, fill=(0, 0, 0))
            except Exception:
                pass

        # Background handling
        bg_rgb = tuple(int(x * 255) for x in bg)
        if bg_rgb != (255, 255, 255):
            try:
                img_rgba = img.convert("RGBA")
                datas = img_rgba.getdata()
                new_data = []
                for px in datas:
                    if px[0] > 250 and px[1] > 250 and px[2] > 250:
                        new_data.append((px[0], px[1], px[2], 0))
                    else:
                        new_data.append(px)
                img_rgba.putdata(new_data)
                bg_img = Image.new("RGBA", (width, height), bg_rgb + (255,))
                composed = Image.alpha_composite(bg_img, img_rgba).convert("RGB")
                img = composed
            except Exception:
                pass

        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()

    def _assemble_grid_png(self, mols: List[Any], width: int, height: int, cols: int, bg: tuple[float, float, float], kekulize: bool, atom_indices: bool) -> Optional[bytes]:
        # Try PIL composition for background and full control
        try:
            from PIL import Image  # type: ignore
            import io
            if not mols:
                return None
            rows = max(1, (len(mols) + cols - 1) // cols)
            grid_w = cols * width
            grid_h = rows * height
            bg_rgb = tuple(int(x * 255) for x in bg)
            grid_img = Image.new("RGB", (grid_w, grid_h), bg_rgb)

            for idx, m in enumerate(mols):
                cell_png = self._draw_single_png(m, width, height, bg, kekulize, atom_indices)
                if not cell_png:
                    continue
                try:
                    im = Image.open(io.BytesIO(cell_png)).convert("RGBA")
                    # Paste without transparency holes over solid background
                    x = (idx % cols) * width
                    y = (idx // cols) * height
                    grid_img.paste(im, (x, y), im)
                except Exception:
                    pass

            # Downscale if exceeding pixel cap
            try:
                max_pixels = int(self.get_property("max_total_pixels") or 4_000_000)
            except Exception:
                max_pixels = 4_000_000
            total_px = grid_w * grid_h
            if total_px > max_pixels and grid_w > 0 and grid_h > 0:
                scale = (max_pixels / float(total_px)) ** 0.5
                new_w = max(64, int(grid_w * scale))
                new_h = max(64, int(grid_h * scale))
                try:
                    grid_img = grid_img.resize((new_w, new_h))
                except Exception:
                    pass

            out = io.BytesIO()
            grid_img.save(out, format="PNG", optimize=True)
            return out.getvalue()
        except Exception as e:
            # If PIL composition fails, do not risk Cairo; return None to signal failure
            try:
                self.logger.warning(f"Grid composition failed: {e}")
            except Exception:
                pass
            return None

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            self._log("execute: begin")
            if inputs is not None:
                try:
                    keys = ",".join(list(inputs.keys())[:5])
                except Exception:
                    keys = "?"
                try:
                    self.logger.info(f"[2DDraw] inputs keys: {keys}")
                except Exception:
                    pass
            mols = self._collect_molecules(inputs)
            if not mols:
                raise ValueError("No valid molecules or SMILES provided")

            # Limit to avoid huge grids
            try:
                max_mols = int(self.get_property("max_mols") or 25)
            except Exception:
                max_mols = 25
            if len(mols) > max_mols:
                self._log(f"truncate mols from {len(mols)} to {max_mols}")
            mols = mols[:max_mols]

            # Filter very large molecules (e.g., proteins) to avoid freezes
            mols = self._filter_large(mols)
            self._log(f"after filter: {len(mols)} mols")
            if not mols:
                raise ValueError("All molecules exceed the max_atoms threshold; increase 'max_atoms' or disable 'skip_large_molecules'.")

            mols = self._prepare_2d(mols)

            # Special case: if single PDB ligand (few atoms) with no bonds, still try to draw placeholder
            try:
                if len(mols) == 1 and hasattr(mols[0], "GetNumBonds") and mols[0].GetNumBonds() == 0:
                    self.logger.info("Drawing bond-less molecule using placeholder renderer")
            except Exception:
                pass

            bg = self._parse_hex_color(str(self.get_property("background") or "#ffffff"))
            # Clamp cell size to prevent huge images
            width = int(self.get_property("cell_width") or 300)
            height = int(self.get_property("cell_height") or 300)
            width = max(50, min(width, 1024))
            height = max(50, min(height, 1024))
            mode = (self.get_property("mode") or "auto").strip().lower()
            cols = max(1, int(self.get_property("grid_cols") or 4))
            kekulize = bool(self.get_property("kekulize"))
            atom_indices = bool(self.get_property("atom_indices"))
            self._log(f"props: size={width}x{height} mode={mode} cols={cols} kekulize={kekulize} atom_indices={atom_indices}")

            # Decide mode
            effective_mode = mode
            if mode == "auto":
                effective_mode = "single" if len(mols) == 1 else "grid"
            self._log(f"effective_mode={effective_mode}")

            png_bytes: Optional[bytes]
            if effective_mode == "single":
                self._log("single draw start")
                png_bytes = self._draw_single_png(mols[0], width, height, bg, kekulize, atom_indices)
            else:
                self._log("grid draw start")
                png_bytes = self._assemble_grid_png(mols, width, height, cols, bg, kekulize, atom_indices)

            if not png_bytes:
                raise RuntimeError("Failed to render 2D structure image")

            self._log(f"execute: success bytes={len(png_bytes)}")
            return {"image": png_bytes, "bytes": png_bytes}
        except Exception as e:
            try:
                self.logger.error(f"2D Structure Draw failed: {e}")
            except Exception:
                pass
            raise

    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        try:
            lines: list[str] = []
            mode = (self.get_property("mode") or "auto").lower()
            bg = self.get_property("background") or "#ffffff"
            w = int(self.get_property("cell_width") or 300)
            h = int(self.get_property("cell_height") or 300)
            cols = int(self.get_property("grid_cols") or 4)
            max_atoms = int(self.get_property("max_atoms") or 200)
            lines.append(f"mode: {mode}")
            lines.append(f"size: {w}x{h} cols:{cols}")
            lines.append(f"bg: {bg} max_atoms:{max_atoms}")
            try:
                last_mols = self.get_property("last_input_molecules")
                if isinstance(last_mols, list):
                    lines.append(f"in mols: {len(last_mols)}")
            except Exception:
                pass
            return lines[:4] if lines else ["2D Draw"]
        except Exception:
            return ["2D Draw"]

    def on_result(self, result: object) -> None:  # type: ignore[override]
        # Avoid storing large PNG bytes in properties to keep UI responsive
        try:
            summary = {}
            if isinstance(result, dict):
                try:
                    size = len(result.get("image") or result.get("bytes") or b"")
                except Exception:
                    size = 0
                summary = {"image_size": int(size)}
            self.set_property("last_result_summary", summary)
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass
