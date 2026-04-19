"""
Visualization nodes: ProLIF interaction fingerprint, 3D Web viewer, and generic plotting stubs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional, List

from core.nodes import BaseNode
from utils.logging_utils import get_logger
from backend.temp_manager import get_subdir


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


class ProLIFInteractionNode(BaseNode):
    """Protein–ligand interactions using ProLIF with strict I/O rules.

    Inputs (only 2 pins):
      - protein (molecules): RDKit Mol list; single used via selector. Internally staged to PDB.
      - ligand (molecules): RDKit Mol list; single used via selector. Internally staged to SDF/MOL2/PDBQT (uses SDF).

    Output (only 1 pin):
      - interactions_table (data): pandas DataFrame of interaction fingerprint.
    """

    def __init__(self):
        super().__init__("prolif_interaction", "ProLIF Interaction")
        self.logger = get_logger(__name__)

        # Inputs (rename to concise names)
        self.add_input_port("protein", "molecules")
        self.add_input_port("ligand", "molecules")
        # Single output: interaction table
        self.add_output_port("interactions_table", "data")

        # Properties: indices and last saved HTML path
        self.set_property("protein_index", 0)
        self.set_property("ligand_index", 0)
        self.set_property("last_2d_html", "")
        
        # Inline UI: embedded 2D web view ONLY. All controls moved to properties.
        try:
            # Match 3D viewer node sizing and margins
            self.width = 520
            self.height = 660
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)
            try:
                self.set_content_margins(0, 32, 0, 0)
            except Exception:
                pass

        # Port labels are now visible by default

            from core.nodes import BaseNode as _BaseNode
            if not getattr(_BaseNode, "_lightweight_construction", False):
                from PySide6.QtWebEngineWidgets import QWebEngineView
                from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile
                from PySide6.QtCore import QUrl
                from PySide6.QtWidgets import QSizePolicy
                self._inline_webview = QWebEngineView()
                try:
                    self._inline_webview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                    # Configure WebEngine (safe mode) to avoid GPU-related freezes for 2D content
                    settings = self._inline_webview.page().settings()
                    settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
                    settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
                    settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
                    settings.setAttribute(QWebEngineSettings.PluginsEnabled, True)
                    settings.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, False)
                    # Disable GPU/WebGL and accelerated 2D canvas for stability on some Windows setups
                    try:
                        settings.setAttribute(QWebEngineSettings.WebGLEnabled, False)
                    except Exception:
                        pass
                    try:
                        settings.setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, False)
                    except Exception:
                        pass
                    # Use an ephemeral/no-cache profile to reduce resource pressure
                    try:
                        profile = self._inline_webview.page().profile()
                        if isinstance(profile, QWebEngineProfile):
                            profile.setHttpCacheType(QWebEngineProfile.NoCache)  # type: ignore[attr-defined]
                            profile.setHttpCacheMaximumSize(0)
                            profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    # Initialize to a blank page to ensure the view is ready
                    try:
                        #self._inline_webview.setUrl(QUrl("about:blank"))
                        self._inline_webview.setHtml(
                            "<html><body style='background-color:#000; margin:0;'></body></html>"
                            )
                    except Exception:
                        pass
                except Exception:
                    pass
                layout = self.content_layout
                if layout is not None:
                    layout.addWidget(self._inline_webview, 0, 0, 1, 3)
                    try:
                        layout.setColumnStretch(0, 1)
                        layout.setColumnStretch(1, 0)
                        layout.setColumnStretch(2, 0)
                        layout.setRowStretch(0, 1)
                    except Exception:
                        pass
            else:
                # Lightweight probing mode — skip creating web views
                self._inline_webview = None  # type: ignore[assignment]
            self._update_port_positions()
        except Exception:
            self._inline_webview = None  # type: ignore[assignment]

    # --- Helpers ---
    def _get_selected_mol(self, value: Any, index: int):
        if value is None:
            return None
        try:
            if isinstance(value, list):
                if not value:
                    return None
                i = max(0, min(len(value) - 1, int(index)))
                return value[i]
            # tolerate single mol
            return value
        except Exception:
            return None

    def _stage_protein_to_pdb(self, mol) -> Optional[Path]:
        """Stage protein RDKit Mol to PDB file (required by ProLIF via MDAnalysis)."""
        try:
            if mol is None:
                return None
            from rdkit import Chem
            out_dir = get_subdir("prolif")
            pdb_path = out_dir / "protein_selected.pdb"
            # Write as-is; assume PDB-residue info carried when source was PDB
            Chem.MolToPDBFile(mol, str(pdb_path))
            return pdb_path
        except Exception as e:
            try:
                self.logger.warning(f"Protein PDB staging failed: {e}")
            except Exception:
                pass
            return None

    def _stage_ligand_allowed_format(self, mol) -> Optional[Path]:
        """Stage ligand to one of allowed formats (SDF/MOL2/PDBQT). Use SDF here."""
        try:
            if mol is None:
                return None
            from rdkit import Chem
            out_dir = get_subdir("prolif")
            sdf_path = out_dir / "ligand_selected.sdf"
            w = Chem.SDWriter(str(sdf_path))
            try:
                w.write(mol)
            finally:
                try:
                    w.close()
                except Exception:
                    pass
            return sdf_path
        except Exception as e:
            try:
                self.logger.warning(f"Ligand SDF staging failed: {e}")
            except Exception:
                pass
            return None

    def _save_2d_network_html(self, fp, lig_plf) -> Optional[str]:
        try:
            import prolif as plf  # noqa: F401  # keep for types
            from utils.prolif_darktheme_generator import ProlifDarkThemeEditor
            fig_or_html = fp.plot_lignetwork(lig_plf, kind="frame", frame=0, display_all=False)
            out_dir = get_subdir("prolif")
            out_html = out_dir / "ligand_interaction_network.html"
            editor = ProlifDarkThemeEditor()
            
            # Extract HTML content from iframe and fix for local WebEngine loading
            try:
                from IPython.display import HTML
                if isinstance(fig_or_html, HTML):
                    # Extract the HTML content from iframe srcdoc
                    iframe_html = fig_or_html.data
                    if '<iframe' in iframe_html and 'srcdoc=' in iframe_html:
                        # Extract content from srcdoc attribute
                        import html
                        import re
                        srcdoc_match = re.search(r'srcdoc="([^"]*)"', iframe_html)
                        if srcdoc_match:
                            escaped_content = srcdoc_match.group(1)
                            # Decode HTML entities
                            content = html.unescape(escaped_content)
                            # Replace CDN URLs with local fallbacks for better compatibility
                            content = content.replace(
                                'https://unpkg.com/vis-network@9.0.4/dist/vis-network.min.js',
                                'https://cdn.jsdelivr.net/npm/vis-network@9.1.9/dist/vis-network.min.js'
                            )
                            content = content.replace(
                                'https://unpkg.com/vis-network@9.0.4/dist/dist/vis-network.min.css',
                                'https://cdn.jsdelivr.net/npm/vis-network@9.1.9/dist/vis-network.min.css'
                            )
                            
                            # Replace "background: #fff;" to "background: #000;"
                            #content = content.replace('background: #fff;', 'background: #000;')

                            # Replace ""color": "black"" to ""color": "#ddd""
                            #content = content.replace('"color": "black"', '"color": "#ddd"')
                            
                            # Replace "color: #555 !important;" to "color: #ccc !important;"
                            #content = content.replace('color: #555 !important;', 'color: #ccc !important;')
                            content = editor.apply_dark_theme(content)

                            # Ensure proper HTML structure
                            if not content.strip().startswith('<!doctype html>'):
                                content = f"<!doctype html>\n{content}"
                            out_html.write_text(content, encoding="utf-8")
                            return str(out_html)
                    else:
                        # Direct HTML content
                        out_html.write_text(iframe_html, encoding="utf-8")
                        return str(out_html)
            except Exception:
                pass
            
            # Fallback to plotly methods with inline JS for better WebEngine compatibility
            try:
                import plotly.io as pio
                pio.write_html(fig_or_html, file=str(out_html), auto_open=False, include_plotlyjs="inline", full_html=True)
                return str(out_html)
            except Exception:
                try:
                    fig_or_html.write_html(str(out_html), include_plotlyjs="inline", full_html=True)  # type: ignore[attr-defined]
                    return str(out_html)
                except Exception:
                    return None
        except Exception:
            return None

    # --- Execution ---
    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            import prolif as plf
            import MDAnalysis as mda
            from rdkit import Chem
            import pandas as pd

            if not inputs:
                raise ValueError("No inputs provided")

            # Select single protein and ligand using indices
            p_idx = int(self.get_property("protein_index") or 0)
            l_idx = int(self.get_property("ligand_index") or 0)
            prot_mol = self._get_selected_mol((inputs or {}).get("protein"), p_idx)
            lig_mol = self._get_selected_mol((inputs or {}).get("ligand"), l_idx)
            if prot_mol is None:
                raise ValueError("Protein input is required (single molecule)")
            if lig_mol is None:
                raise ValueError("Ligand input is required (single molecule)")

            # Stage formats as required by ProLIF
            prot_pdb = self._stage_protein_to_pdb(prot_mol)
            if prot_pdb is None:
                raise RuntimeError("Failed to stage protein to PDB for ProLIF")
            lig_sdf = self._stage_ligand_allowed_format(lig_mol)
            if lig_sdf is None:
                raise RuntimeError("Failed to stage ligand to SDF for ProLIF")

            # Load ProLIF molecules via MDAnalysis for protein and RDKit for ligand (from SDF)
            u = mda.Universe(str(prot_pdb))
            try:
                prot_plf = plf.Molecule.from_mda(u)
            except Exception:
                prot_plf = plf.Molecule.from_mda(u, NoImplicit=False, force=True)  # type: ignore[attr-defined] 
            try:
                suppl = plf.sdf_supplier(str(lig_sdf))
                lig_rdkit = suppl[0]
            except Exception:
                lig_rdkit = Chem.SDMolSupplier(str(lig_sdf), sanitize=True, removeHs=False)[0]
            if lig_rdkit is None:
                raise RuntimeError("Failed to load ligand from staged SDF")
            lig_plf = plf.Molecule(lig_rdkit)

            # Fingerprint
            fp = plf.Fingerprint()
            ran = False
            try:
                fp.run(lig_plf, prot_plf, n_jobs=1)  # type: ignore[attr-defined]
                ran = True
            except Exception:
                try:
                    fp.run(prot_plf, lig_plf, n_jobs=1)  # type: ignore[attr-defined]
                    ran = True
                except Exception:
                    try:
                        fp.run_from_iterable([lig_plf], prot_plf, n_jobs=1)  # type: ignore[attr-defined]
                        ran = True
                    except Exception as e:
                        raise RuntimeError(f"ProLIF fingerprint computation failed: {e}")
            if not ran:
                raise RuntimeError("ProLIF fingerprint computation did not run")

            df = fp.to_dataframe()
            if df.empty:
                self.logger.info("ProLIF: No interactions detected between protein and ligand")
                with open(get_subdir("prolif") / "no_interactions.html", "w") as f:
                    f.write("""
                            <html>
                            <head>
                            <meta charset="UTF-8">
                            <title>No Interactions</title>
                            <style>
                                body {
                                background-color: #121212;
                                color: #e0e0e0;
                                font-family: Arial, Helvetica, sans-serif;
                                display: flex;
                                flex-direction: column;
                                justify-content: center;
                                align-items: center;
                                height: 100vh;
                                margin: 0;
                                }
                                h1 {
                                color: #ff6b6b;
                                font-size: 2rem;
                                margin-bottom: 10px;
                                }
                                p {
                                font-size: 1rem;
                                color: #b0b0b0;
                                }
                                .card {
                                background-color: #1e1e1e;
                                padding: 20px 30px;
                                border-radius: 12px;
                                box-shadow: 0 4px 20px rgba(0,0,0,0.6);
                                text-align: center;
                                max-width: 500px;
                                }
                            </style>
                            </head>
                            <body>
                            <div class="card">
                                <h1>No interactions detected</h1>
                                <p>Between protein and ligand</p>
                            </div>
                            </body>
                            </html>
                            """)
                html_path = get_subdir("prolif") / "no_interactions.html"
                self.set_property("last_2d_html", html_path or "")
                return {"interactions_table": pd.DataFrame(columns=['Ligand', 'Residue', 'Interaction'])}
            else:
                self.logger.info("ProLIF: Interactions detected between protein and ligand")

            df = self._transform_interaction_dataframe(df)

            # Save 2D HTML for UI embedding/view
            html_path = self._save_2d_network_html(fp, lig_plf)
            try:
                self.set_property("last_2d_html", html_path or "")
            except Exception:
                pass

            return {"interactions_table": df}
        except Exception as e:
            try:
                self.logger.error(f"ProLIF Interaction failed: {e}")
            except Exception:
                pass
            raise

    # --- UI updates ---
    def _open_2d_window(self) -> None:
        # Intentionally disabled: ProLIF node should not open external windows/dialogs
        return

    def on_result(self, result: object) -> None:  # type: ignore[override]
        # Refresh embedded 2D viewer, but never open a new window automatically
        try:
            path = self.get_property("last_2d_html") or ""
            if path and getattr(self, "_inline_webview", None) is not None:
                from PySide6.QtCore import QUrl
                # Use a timer to delay loading slightly to avoid issues with WebEngine initialization
                def delayed_load():
                    try:
                        if getattr(self, "_inline_webview", None) is not None:
                            # Prefer loading with file:// URL and disable background loading causing freezes
                            url = QUrl.fromLocalFile(str(Path(path).resolve()))
                            self._inline_webview.setUrl(url)
                    except Exception:
                        pass
                
                from PySide6.QtCore import QTimer
                QTimer.singleShot(150, delayed_load)
        except Exception:
            pass
        try:
            super().on_result(result)
        except Exception:
            pass

    # Hide any summary text inside node body (embed viewer only)
    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        return []
    
    # --- Helpers ---
    def _transform_interaction_dataframe(self, df):
        """
        Transform interaction dataframe to a more readable format
        - Input: DataFrame with original structure (columns = interactions, rows = protein, interaction, frame values)
        - Output: DataFrame with columns [Ligand, Residue, Interaction]
        """
        import pandas as pd
        
        # Debug: Check the structure of the dataframe
        # print(f"DataFrame columns type: {type(df.columns)}")
        # print(f"DataFrame columns: {df.columns}")
        # print(f"DataFrame index: {df.index}")
        # print(f"DataFrame shape: {df.shape}")
        
        transformed_data = []
        
        # Handle MultiIndex columns
        if isinstance(df.columns, pd.MultiIndex):
            # print("Processing MultiIndex columns...")
            
            # Get all column tuples and process each one
            for col_idx, col_tuple in enumerate(df.columns):
                try:
                    # Extract components from MultiIndex tuple
                    ligand = str(col_tuple[0])      # First level: ligand name
                    protein = str(col_tuple[1])     # Second level: protein/residue
                    interaction = str(col_tuple[2]) # Third level: interaction type
                    
                    # print(f"Processing column {col_idx}: {col_tuple}")
                    
                    # Access the value using iloc with column index
                    # This is the most reliable way for MultiIndex
                    frame_value = df.iloc[0, col_idx]  # First (and likely only) row
                    
                    # print(f"  Value: {frame_value}")
                    
                    # Check if interaction is active (True)
                    is_active = False
                    if isinstance(frame_value, bool):
                        is_active = frame_value
                    elif isinstance(frame_value, (int, float)):
                        is_active = bool(frame_value)
                    elif isinstance(frame_value, str):
                        is_active = frame_value.lower() in ['true', '1', 'yes']
                    else:
                        # If uncertain, check if the value is truthy
                        is_active = bool(frame_value)
                    
                    if is_active:
                        transformed_data.append({
                            'Ligand': ligand,
                            'Residue': protein,
                            'Interaction': interaction
                        })
                        # print(f"  ✓ Added interaction: {ligand} - {protein} - {interaction}")
                    # else:
                        # print(f"  ✗ Skipped (False): {ligand} - {protein} - {interaction}")
                        
                except Exception as e:
                    # print(f"  ✗ Error processing column {col_idx} ({col_tuple}): {e}")
                    continue
        
        else:
            # Handle regular columns (original logic for backward compatibility)
            # print("Processing regular columns...")
            
            # Extract base ligand name from first column
            first_col = df.columns[0]
            if isinstance(first_col, tuple):
                base_ligand = str(first_col[0]) if len(first_col) > 0 else "UNL1"
            else:
                base_ligand = str(first_col).split('.')[0]
            
            # If the dataframe doesn't have the expected row structure, try to transpose
            if 'protein' not in df.index and 'interaction' not in df.index:
                if 'protein' in df.columns or 'ligand' in df.columns:
                    df = df.T
            
            try:
                for col in df.columns:
                    # Extract ligand name
                    if isinstance(col, tuple):
                        ligand = str(col[0]) if len(col) > 0 else base_ligand
                    else:
                        ligand = base_ligand
                    
                    # Get protein and interaction info
                    try:
                        protein = df.loc['protein', col]
                        interaction = df.loc['interaction', col]
                        
                        # Check frame value (could be in different rows)
                        frame_value = None
                        for possible_frame in ['0', 0, 'Frame']:
                            try:
                                frame_value = df.loc[possible_frame, col]
                                break
                            except KeyError:
                                continue
                        
                        # If no frame found, assume True (all interactions are valid)
                        if frame_value is None:
                            frame_value = True
                        
                        if str(frame_value).lower() == 'true' or frame_value is True:
                            transformed_data.append({
                                'Ligand': ligand,
                                'Residue': str(protein),
                                'Interaction': str(interaction)
                            })
                            
                    except KeyError as e:
                        # print(f"KeyError for column {col}: {e}")
                        continue
                        
            except Exception as e:
                self.logger.error(f"Error processing regular dataframe: {e}")
        
        # Create dataframe with transformed data
        if not transformed_data:
            # print("No data transformed - returning empty DataFrame")
            return pd.DataFrame(columns=['Ligand', 'Residue', 'Interaction'])
        
        # print(f"Total interactions found: {len(transformed_data)}")
        result_df = pd.DataFrame(transformed_data)
        
        # Combine unique interactions per Ligand-Residue pair
        try:
            final_df = (
                result_df.groupby(['Ligand', 'Residue'])['Interaction']
                .apply(lambda x: ','.join(sorted(x.unique())))
                .reset_index()
            )
            # print(f"Final DataFrame shape: {final_df.shape}")
            return final_df
        except Exception as e:
            # print(f"Error in grouping: {e}")
            return result_df


class Web3DViewerNode(BaseNode):
    """3D molecule viewer using Qt WebEngine + NGL.js.

    Inputs:
      - molecules: list of RDKit Mol objects (required)
    Outputs:
      - viewer_url: file URL to viewer with query params
      - html_path: path to the viewer HTML file
    UI:
      - Inline button opens a viewer window (QWebEngineView) without blocking.
    """

    def __init__(self):
        super().__init__("web3d_viewer", "3D Web Viewer")
        self.logger = get_logger(__name__)
        # Input is molecules only; we serialize to PDB text for the viewer
        self.add_input_port("molecules", "molecules")
        self.add_output_port("viewer_url", "string")

        # Default properties (internal cache / style)
        self.set_property("protein_pdb", "")
        self.set_property("molecules_data", "")
        self.set_property("pdb_code", "")  # For direct PDB code input
        self.set_property("background", "#0e0e0e")
        self.set_property("spin", True)
        self.set_property("representation", "cartoon+licorice")  # or surface

        # Add minimal inline UI: a single line edit for PDB code, a View 3D button,
        # and an embedded QWebEngineView below for instant preview
        try:
            from PySide6.QtWidgets import QPushButton, QGraphicsProxyWidget, QLineEdit
            from PySide6.QtWidgets import QSizePolicy
            from PySide6.QtWebEngineWidgets import QWebEngineView

            self.width = 520
            self.height = 360
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)
            try:
                # Fill the node neatly like Image/Table viewers
                self.set_content_margins(0, 32, 0, 0)
            except Exception:
                pass

            # PDB code input and button (top row)
            self._pdb_input = QLineEdit()
            self._pdb_input.setPlaceholderText("e.g., 1HIV, 4ZUD")
            self._pdb_input.setToolTip("Enter PDB code to load structure from RCSB")
            self._pdb_input.setText(self.get_property("pdb_code") or "")
            self._pdb_input.textChanged.connect(self._on_pdb_code_changed)

            btn = QPushButton("View 3D")
            btn.setToolTip("Open interactive 3D viewer")
            btn.clicked.connect(self._on_open_viewer)

            # Embedded lightweight viewer (no panels)
            from core.nodes import BaseNode as _BaseNode
            if not getattr(_BaseNode, "_lightweight_construction", False):
                self._inline_webview = QWebEngineView()
                try:
                    self._inline_webview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                except Exception:
                    pass
            else:
                self._inline_webview = None  # type: ignore[assignment]

            layout = self.content_layout
            if layout is not None:
                # Top row: input spans two columns, button on the right
                layout.addWidget(self._pdb_input, 0, 0, 1, 2)
                layout.addWidget(btn, 0, 2, 1, 1)
                # Second row: embedded webview fills the rest
                if self._inline_webview is not None:
                    layout.addWidget(self._inline_webview, 1, 0, 1, 3)
                try:
                    layout.setColumnStretch(0, 1)
                    layout.setColumnStretch(1, 0)
                    layout.setColumnStretch(2, 0)
                    layout.setRowStretch(1, 1)
                except Exception:
                    pass

            # Ports depend on width/height; ensure correct placement
            self._update_port_positions()

            # Initial inline viewer load (if PDB/molecules already present)
            if self._inline_webview is not None:
                try:
                    self._update_inline_viewer()
                except Exception:
                    pass
        except Exception:
            # If widgets cannot be created (headless), skip inline widgets
            pass

    def _stage_local_file_for_viewer(self, path_str: str) -> Optional[str]:
        """Return a file URL for a local file without copying into project root.

        This avoids writing to the repository by referencing the original path
        directly via a file:// URL.
        """
        try:
            from PySide6.QtCore import QUrl
            src = Path(path_str)
            if not src.exists():
                return None
            return QUrl.fromLocalFile(str(src.resolve())).toString()
        except Exception:
            return None

    def _stage_pdb_text_for_viewer(self, pdb_text: str, tag: str = "molecules") -> Optional[str]:
        """Write PDB text into the session temp and return a file URL."""
        try:
            from PySide6.QtCore import QUrl
            cache_dir = get_subdir("viewer_cache")
            import hashlib
            digest = hashlib.sha1(pdb_text.encode("utf-8")).hexdigest()[:12]
            name = f"{tag}_{digest}.pdb"
            dst = cache_dir / name
            if not dst.exists():
                dst.write_text(pdb_text, encoding="utf-8")
            return QUrl.fromLocalFile(str(dst.resolve())).toString()
        except Exception:
            return None

    def _build_viewer_url(self, protein: Optional[str], ligand: Optional[str], molecules_data: Optional[str] = None, use_embed: bool = False) -> str:
        from PySide6.QtCore import QUrl
        from urllib.parse import quote
        import base64
        
        # Try to get web viewer file through resource system
        try:
            from backend.resource_access import get_web_file_url
            filename = "viewer_embed.html" if use_embed else "viewer.html"
            base_url = get_web_file_url(filename)
        except ImportError:
            # Fallback to original method
            base = Path("web") / ("viewer_embed.html" if use_embed else "viewer.html")
            base_url = QUrl.fromLocalFile(str(base.resolve()))

        params = []
        
        # Handle protein file
        if protein:
            # If it's a local path, stage it into web/cache and reference relatively
            try:
                p = Path(protein)
                if p.exists():
                    rel = self._stage_local_file_for_viewer(protein)
                    if rel:
                        params.append(f"protein={quote(rel)}")
                    else:
                        p_url = QUrl.fromLocalFile(str(p.resolve()))
                        params.append(f"protein={quote(p_url.toString())}")
                else:
                    # Assume it's already a URL or relative path
                    params.append(f"protein={quote(protein)}")
            except Exception:
                params.append(f"protein={quote(protein)}")
            
        # Handle ligand file
        if ligand:
            try:
                l = Path(ligand)
                if l.exists():
                    rel = self._stage_local_file_for_viewer(ligand)
                    if rel:
                        params.append(f"ligand={quote(rel)}")
                    else:
                        l_url = QUrl.fromLocalFile(str(l.resolve()))
                        params.append(f"ligand={quote(l_url.toString())}")
                else:
                    params.append(f"ligand={quote(ligand)}")
            except Exception:
                params.append(f"ligand={quote(ligand)}")
            
        # Handle molecules data (inline PDB data)
        if molecules_data:
            # Prefer embedding to avoid file:// fetch/CORS issues in WebEngine
            try:
                encoded_data = base64.b64encode(molecules_data.encode('utf-8')).decode('ascii')
                params.append(f"molecules_data={quote(encoded_data)}")
            except Exception:
                # Last resort: stage to file
                try:
                    rel = self._stage_pdb_text_for_viewer(molecules_data, tag="molecules")
                    if rel:
                        params.append(f"ligand={quote(rel)}")
                except Exception:
                    pass
            
        # Handle PDB code for direct download
        pdb_code = self.get_property('pdb_code')
        # Only include pdb_code param if we are NOT already providing a local protein file
        if pdb_code and not protein:
            params.append(f"pdb_code={quote(pdb_code)}")
            
        # Styling parameters
        params.append(f"bg={self.get_property('background')}")
        params.append(f"spin={'1' if self.get_property('spin') else '0'}")
        params.append(f"repr={self.get_property('representation')}")

        query = ("?" + "&".join(params)) if params else ""
        return base_url.toString() + query

    def _download_pdb_locally(self, code: str) -> Optional[Path]:
        """Download a PDB/mmCIF for the given code to a local cache and return its path.

        Tries a couple of endpoints and formats. Returns None if all attempts fail.
        """
        try:
            code_up = (code or "").strip().upper()
            if not code_up:
                return None

            cache_dir = get_subdir("viewer_cache")

            candidates = [
                (f"https://files.rcsb.org/download/{code_up}.pdb", cache_dir / f"{code_up}.pdb"),
                (f"https://files.rcsb.org/download/{code_up}.cif", cache_dir / f"{code_up}.cif"),
            ]

            import urllib.request
            for url, out_path in candidates:
                try:
                    self.logger.info(f"Fetching structure for {code_up} from {url}")
                    with urllib.request.urlopen(url, timeout=10) as resp:
                        data = resp.read()
                    # Basic validation: ensure non-trivial size
                    if data and len(data) > 100:
                        out_path.write_bytes(data)
                        self.logger.info(f"Saved {code_up} to {out_path}")
                        return out_path
                except Exception as e:
                    self.logger.warning(f"Failed to download from {url}: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error downloading PDB code {code}: {e}")
        return None

    def _ensure_viewer_file_exists(self) -> Path:
        """Ensure the static viewer HTML exists (written by repo or at runtime)."""
        # Try to use resource system first
        try:
            from backend.resource_access import is_using_compiled_resources, get_web_file_path
            
            if is_using_compiled_resources():
                # Using compiled resources - don't create directories or download files
                self.logger.info("Using compiled resources for web viewer")
                # Return a path that indicates we're using resources
                # The actual file loading will be handled by resource system
                return Path("web") / "viewer.html"
        except ImportError:
            # Resource system not available, continue with fallback
            pass
        except Exception as e:
            self.logger.debug(f"Resource system check failed: {e}")
        
        # Fallback: create files if not using resources
        path = Path("web") / "viewer.html"
        
        # Check if source directories exist - if not, we might be in final app mode without resources
        if not path.parent.exists():
            self.logger.info("Web folder doesn't exist and resource system not available - creating fallback")
        
        path.parent.mkdir(exist_ok=True)
        
        # Prepare local vendor directory and attempt to fetch NGL.js for offline usage
        try:
            vendor_dir = path.parent / "vendor"
            vendor_dir.mkdir(exist_ok=True)
            ngl_js_path = vendor_dir / "ngl.js"
            if not ngl_js_path.exists():
                self.logger.info("NGL.js not found locally. Attempting download to web/vendor/ngl.js ...")
                urls = [
                    "https://cdn.jsdelivr.net/npm/ngl@2.2.1/dist/ngl.js",
                    "https://unpkg.com/ngl@2.2.1/dist/ngl.js",
                ]
                for u in urls:
                    try:
                        import urllib.request
                        with urllib.request.urlopen(u, timeout=6) as resp:
                            data = resp.read()
                        ngl_js_path.write_bytes(data)
                        self.logger.info(f"Downloaded NGL.js from {u}")
                        break
                    except Exception as e:
                        self.logger.warning(f"Failed to download NGL.js from {u}: {e}")
        except Exception as e:
            # Non-fatal: user can manually place the file if needed
            self.logger.warning(f"Could not prepare local NGL.js: {e}")
        if not path.exists():
            # Enhanced HTML viewer with chain selection controls
            html = """<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>VERA 3D Viewer</title>
    <style>
      html, body { height: 100%; margin: 0; font-family: Arial, sans-serif; }
      #viewport { height: 100%; overflow: hidden; }
      #controls {
        position: absolute; top: 10px; left: 10px; z-index: 1000;
        background: rgba(0,0,0,0.8); color: white; padding: 10px;
        border-radius: 5px; font-size: 12px; min-width: 200px;
      }
      #controls h4 { margin: 0 0 8px 0; color: #4CAF50; }
      #controls label { display: block; margin: 4px 0; cursor: pointer; }
      #controls input[type="checkbox"] { margin-right: 6px; }
      #loading {
        position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
        color: white; z-index: 1000; background: rgba(0,0,0,0.7);
        padding: 20px; border-radius: 5px; display: none;
      }
      #error {
        position: absolute; top: 10px; right: 10px; max-width: 300px;
        background: rgba(255, 0, 0, 0.8); color: white; padding: 10px;
        border-radius: 5px; display: none; z-index: 1001;
      }
      .chain-group { margin-bottom: 10px; }
      .chain-protein { color: #81C784; }
      .chain-ligand { color: #FFB74D; }
    </style>
    <script>
      let stage, structureComponent;
      let chainRepresentations = {};
      
      function loadNGL() {
        const sources = [
          './vendor/ngl.js',
          './ngl.js',
          'https://cdn.jsdelivr.net/npm/ngl@2.2.1/dist/ngl.js',
          'https://unpkg.com/ngl@2.2.1/dist/ngl.js'
        ];
        function tryLoad(index) {
          if (index >= sources.length) {
            const msg = 'Failed to load NGL.js. Place ngl.js in web/vendor/ngl.js for offline use.';
            document.getElementById('error').textContent = msg;
            document.getElementById('error').style.display = 'block';
            return;
          }
          const script = document.createElement('script');
          script.src = sources[index];
          script.onload = () => initViewer();
          script.onerror = () => tryLoad(index + 1);
          document.head.appendChild(script);
        }
        tryLoad(0);
      }
      
      function initViewer() {
        const bg = new URL(location).searchParams.get('bg') || '#0e0e0e';
        stage = new NGL.Stage('viewport', { backgroundColor: bg });
        window.addEventListener('resize', () => stage.handleResize());
        
        const spin = new URL(location).searchParams.get('spin') === '1';
        const moleculesData = new URL(location).searchParams.get('molecules_data');
        
        if (moleculesData) {
          // Decode base64 embedded data
          try {
            const pdbData = atob(decodeURIComponent(moleculesData));
            loadStructureData(pdbData);
          } catch (e) {
            console.error('Failed to decode molecules data:', e);
          }
        } else {
          // Fallback to old protein/ligand loading
          loadLegacyStructures();
        }
        
        if (spin) stage.setSpin(true);
      }
      
      function loadStructureData(pdbData) {
        const blob = new Blob([pdbData], { type: 'text/plain' });
        const file = new File([blob], 'structure.pdb');
        
        stage.loadFile(file).then(component => {
          structureComponent = component;
          component.removeAllRepresentations();
          analyzeStructure(component);
          createChainControls(component);
          stage.autoView();
        }).catch(err => {
          console.error('Failed to load structure:', err);
          document.getElementById('error').textContent = 'Failed to load structure: ' + err.message;
          document.getElementById('error').style.display = 'block';
        });
      }
      
      function analyzeStructure(component) {
        const structure = component.structure;
        const chains = [];
        const proteinChains = [];
        const ligandChains = [];
        
        structure.eachChain(chain => {
          const chainId = chain.chainname;
          chains.push(chainId);
          
          // Determine if protein or ligand based on residue names
          let hasProteinResidues = false;
          let hasLigandResidues = false;
          
          chain.eachResidue(residue => {
            const resName = residue.resname;
            if (resName === 'PRO' || ['ALA', 'ARG', 'ASN', 'ASP', 'CYS', 'GLN', 'GLU', 'GLY', 'HIS', 'ILE', 'LEU', 'LYS', 'MET', 'PHE', 'PRO', 'SER', 'THR', 'TRP', 'TYR', 'VAL'].includes(resName)) {
              hasProteinResidues = true;
            } else if (resName === 'LIG' || !['HOH', 'WAT'].includes(resName)) {
              hasLigandResidues = true;
            }
          });
          
          if (hasProteinResidues || (!hasLigandResidues && chainId.match(/[A-Z]/))) {
            proteinChains.push(chainId);
          } else {
            ligandChains.push(chainId);
          }
        });
        
        // Store for controls
        window.structureInfo = { chains, proteinChains, ligandChains };
        
        // Add default representations
        proteinChains.forEach(chainId => addChainRepresentation(chainId, 'protein'));
        ligandChains.forEach(chainId => addChainRepresentation(chainId, 'ligand'));
      }
      
      function addChainRepresentation(chainId, type) {
        if (!structureComponent) return;
        
        const selection = ':' + chainId;
        const key = 'chain_' + chainId;
        
        if (type === 'protein') {
          // Protein: cartoon for backbone, licorice for sidechains
          const cartoonRepr = structureComponent.addRepresentation('cartoon', {
            sele: selection,
            colorScheme: 'chainname',
            aspectRatio: 5
          });
          chainRepresentations[key + '_cartoon'] = cartoonRepr;
        } else {
          // Ligand: licorice with element colors
          const licoriceRepr = structureComponent.addRepresentation('licorice', {
            sele: selection,
            colorScheme: 'element'
          });
          chainRepresentations[key + '_licorice'] = licoriceRepr;
        }
      }
      
      function toggleChain(chainId, visible) {
        const keyPrefix = 'chain_' + chainId;
        Object.keys(chainRepresentations).forEach(key => {
          if (key.startsWith(keyPrefix)) {
            chainRepresentations[key].setVisibility(visible);
          }
        });
      }
      
      function createChainControls(component) {
        const info = window.structureInfo;
        if (!info) return;
        
        const controls = document.getElementById('controls');
        let html = '<h4>Chain Selection</h4>';
        
        if (info.proteinChains.length > 0) {
          html += '<div class="chain-group"><strong class="chain-protein">Proteins:</strong><br>';
          info.proteinChains.forEach(chainId => {
            html += `<label class="chain-protein">
              <input type="checkbox" checked onchange="toggleChain('${chainId}', this.checked)">
              Chain ${chainId}
            </label>`;
          });
          html += '</div>';
        }
        
        if (info.ligandChains.length > 0) {
          html += '<div class="chain-group"><strong class="chain-ligand">Ligands:</strong><br>';
          info.ligandChains.forEach(chainId => {
            html += `<label class="chain-ligand">
              <input type="checkbox" checked onchange="toggleChain('${chainId}', this.checked)">
              Chain ${chainId}
            </label>`;
          });
          html += '</div>';
        }
        
        controls.innerHTML = html;
      }
      
      function loadLegacyStructures() {
        // Fallback to old protein/ligand URL loading
        const proteinUrl = new URL(location).searchParams.get('protein');
        const ligandUrl = new URL(location).searchParams.get('ligand');
        
        const loadPromises = [];
        if (proteinUrl) {
          loadPromises.push(stage.loadFile(decodeURIComponent(proteinUrl)).then(comp => {
            comp.addRepresentation('cartoon', { colorScheme: 'sstruc' });
            return comp;
          }));
        }
        if (ligandUrl) {
          loadPromises.push(stage.loadFile(decodeURIComponent(ligandUrl)).then(comp => {
            comp.addRepresentation('licorice', { colorScheme: 'element' });
            return comp;
          }));
        }
        
        Promise.all(loadPromises).then(() => {
          stage.autoView();
        });
      }
      
      document.addEventListener('DOMContentLoaded', loadNGL);
    </script>
  </head>
  <body>
    <div id="controls"></div>
    <div id="loading">Loading...</div>
    <div id="error"></div>
    <div id="viewport"></div>
  </body>
</html>"""
            path.write_text(html, encoding="utf-8")
        return path

    def _on_pdb_code_changed(self, text: str):
        """Handle PDB code input change."""
        try:
            new_code = text.strip().upper()
            self.set_property("pdb_code", new_code)
            # Clear previously staged protein file so new code takes effect
            self.set_property("protein_pdb", "")
            # Also clear any existing molecules_data to avoid mixed loads
            self.set_property("molecules_data", "")
            # Update inline embedded viewer immediately
            try:
                self._update_inline_viewer()
            except Exception:
                pass
        except Exception:
            pass

    def _on_open_viewer(self):
        """Open the interactive viewer window."""
        try:
            protein = self.get_property("protein_pdb")
            ligand = None
            molecules_data = self.get_property("molecules_data")
            # If molecules were provided live, convert to PDB blocks
            if not molecules_data:
                live_mols = self.get_property("last_input_molecules")
                if live_mols:
                    try:
                        molecules_data = self._convert_molecules_to_pdb_data(live_mols)
                        if molecules_data:
                            self.set_property("molecules_data", molecules_data)
                    except Exception:
                        pass
            pdb_code = self.get_property("pdb_code")
            
            # Fall back to a warning if nothing set
            if not protein and not ligand and not molecules_data and not pdb_code:
                self.logger.warning("No structures set to view")
                return

            # If only PDB code provided, fetch locally without blocking UI (QThread)
            if (not protein) and pdb_code:
                try:
                    from PySide6.QtCore import QObject, Signal, QThread

                    class _Worker(QObject):
                        finished = Signal(object)
                        def __init__(self, outer, code):
                            super().__init__()
                            self._outer = outer
                            self._code = code
                        def run(self):  # type: ignore[override]
                            try:
                                path_obj = self._outer._download_pdb_locally(self._code)
                            except Exception:
                                path_obj = None
                            self.finished.emit(path_obj)

                    thread = QThread()
                    worker = _Worker(self, pdb_code)
                    worker.moveToThread(thread)
                    thread.started.connect(worker.run)

                    # Ensure UI actions and cleanup run in the GUI thread
                    worker.finished.connect(self._on_pdb_fetch_finished)
                    worker.finished.connect(thread.quit)
                    thread.finished.connect(worker.deleteLater)
                    thread.finished.connect(thread.deleteLater)

                    # Keep refs to avoid GC
                    self._fetch_thread = thread
                    self._fetch_worker = worker

                    thread.start()
                    return  # Defer actual open to async callback
                except Exception:
                    # Fallback to synchronous (last resort)
                    local_path = self._download_pdb_locally(pdb_code)
                    if local_path is not None:
                        protein = str(local_path)
                        self.set_property("protein_pdb", protein)

            # Ensure viewer HTML exists
            self._open_viewer_window(protein, ligand, molecules_data)
        except Exception as e:
            self.logger.error(f"Failed to open 3D viewer: {e}")

    def _on_pdb_fetch_finished(self, path_obj):
        """Handle completion of async PDB fetch (runs in GUI thread)."""
        try:
            ligand = None
            molecules_data = self.get_property("molecules_data")
            if path_obj is not None:
                self.set_property("protein_pdb", str(path_obj))
                self._open_viewer_window(str(path_obj), ligand, molecules_data)
            else:
                # Open with pdb_code so viewer can try online fallback
                self._open_viewer_window(None, ligand, molecules_data)
        except Exception:
            pass

    def _open_viewer_window(self, protein: Optional[str], ligand: Optional[str], molecules_data: Optional[str]) -> None:
        """Helper to build URL and display the viewer window."""
        try:
            # Always clear any previous content indicators before opening
            try:
                self.set_property("last_opened_url", "")
            except Exception:
                pass
            # If an older viewer window exists, close it to ensure a full reset
            try:
                if getattr(self, "_viewer_window", None) is not None:
                    try:
                        self._viewer_window.close()
                    except Exception:
                        pass
                    self._viewer_window = None
            except Exception:
                pass
            html_path = self._ensure_viewer_file_exists()
            url = self._build_viewer_url(protein, ligand, molecules_data)
            from core.webviewer import MoleculeWebViewerWindow
            win = MoleculeWebViewerWindow()
            win.load_viewer_url(url)
            win.show()
            self._viewer_window = win
            try:
                self.set_property("last_opened_url", url)
            except Exception:
                pass
        except Exception as e:
            self.logger.error(f"Failed to show 3D viewer: {e}")

    def _update_inline_viewer(self) -> None:
        """Load or refresh the embedded viewer with minimal UI (embed mode)."""
        try:
            # Ensure viewer HTML exists
            try:
                self._ensure_viewer_file_exists()
            except Exception:
                pass

            # Determine current content to show
            protein = self.get_property("protein_pdb") or None
            molecules_data = self.get_property("molecules_data") or None
            if not molecules_data:
                # Prefer freshly provided molecules from upstream if available
                try:
                    live_mols = self.get_property("last_input_molecules")
                    if live_mols:
                        md = self._convert_molecules_to_pdb_data(live_mols)
                        if md:
                            molecules_data = md
                            self.set_property("molecules_data", md)
                except Exception:
                    pass

            # Build URL targeting the dedicated embed viewer (clean, no panels)
            url = self._build_viewer_url(protein, None, molecules_data, use_embed=True)
            if isinstance(url, str) and url.strip():
                try:
                    from PySide6.QtCore import QUrl
                    if getattr(self, "_inline_webview", None) is not None:
                        self._inline_webview.setUrl(QUrl(url))
                except Exception:
                    pass
        except Exception:
            pass

    def on_result(self, result: object) -> None:  # type: ignore[override]
        """Live UI refresh when upstream inputs change or this node finishes.

        If the preview window is currently open, reload it with the latest inputs
        without requiring the user to close/reopen the window.
        """
        try:
            # Keep base behavior (store last_result and repaint node)
            super().on_result(result)
        except Exception:
            pass

        # Update the inline viewer and only refresh an already-open external window.
        # Never create or show a new external window automatically here.
        try:
            win = getattr(self, "_viewer_window", None)
            # Rebuild data from latest properties/inputs
            protein = self.get_property("protein_pdb") or None
            molecules_data = None
            # Prefer freshly provided molecules from upstream
            try:
                live_mols = self.get_property("last_input_molecules")
                if live_mols:
                    md = self._convert_molecules_to_pdb_data(live_mols)
                    if md:
                        molecules_data = md
                        self.set_property("molecules_data", md)
            except Exception:
                pass
            # If execution of this node produced a direct URL, use it
            url_from_result = None
            try:
                if isinstance(result, dict) and "viewer_url" in result and result.get("viewer_url"):
                    url_from_result = result.get("viewer_url")
            except Exception:
                pass
            # Build URL if not supplied
            if not url_from_result:
                if molecules_data is None:
                    molecules_data = self.get_property("molecules_data") or None
                url = self._build_viewer_url(protein, None, molecules_data)
            else:
                url = url_from_result
            # Always refresh inline embed to reflect current inputs
            try:
                self._update_inline_viewer()
            except Exception:
                pass
            # Only refresh an existing external viewer window; do not create or show it here
            if win is None:
                return
            last_url = self.get_property("last_opened_url") or ""
            if not isinstance(url, str) or url.strip() == "":
                return
            if url != last_url:
                try:
                    win.load_viewer_url(url)
                    self.set_property("last_opened_url", url)
                except Exception:
                    pass
        except Exception:
            pass

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Only accept molecules as input
        protein = None
        ligand = None
        molecules_data = None

        # Clear stale properties on a new run
        try:
            if inputs is not None:
                # If molecules input is provided (even empty), clear previous molecules_data and cached protein
                if "molecules" in inputs:
                    self.set_property("molecules_data", "")
                    self.set_property("protein_pdb", "")
                    self.set_property("last_input_molecules", [])
                # If user intends to use pdb_code, ensure molecules_data is cleared to avoid mixing
                elif (self.get_property("pdb_code") or "") != "":
                    self.set_property("molecules_data", "")
        except Exception:
            pass

        # Always clear any previously cached structures so each run reflects only current input
        try:
            self.set_property("molecules_data", "")
            self.set_property("protein_pdb", "")
            self.set_property("last_input_molecules", [])
        except Exception:
            pass

        if inputs:
            # Accept either canonical 'molecules' or common aliases from upstream nodes
            molecules = inputs.get("molecules") or inputs.get("minimized_molecules")
            if molecules and isinstance(molecules, list) and len(molecules) > 0:
                molecules_data = self._convert_molecules_to_pdb_data(molecules)
                try:
                    self.set_property("last_input_molecules", molecules)
                except Exception:
                    pass

        if not molecules_data:
            molecules_data = self.get_property("molecules_data")

        # If no molecules provided but we have a PDB code, fetch locally now
        if not molecules_data:
            pdb_code = self.get_property("pdb_code")
            if pdb_code:
                local_path = self._download_pdb_locally(pdb_code)
                if local_path is not None:
                    protein = str(local_path)
                    self.set_property("protein_pdb", protein)

        # Update stored molecules_data
        if molecules_data:
            self.set_property("molecules_data", molecules_data)

        # Check if we have any data to display
        pdb_code = self.get_property("pdb_code")
        if not protein and not molecules_data and not pdb_code:
            self.logger.warning("No structures provided for 3D viewer")
            return {"viewer_url": "", "status": "no_data"}

        self._ensure_viewer_file_exists()
        url = self._build_viewer_url(protein, ligand, molecules_data)
        self.logger.info(f"Built viewer URL with {len(url)} characters")
        return {"viewer_url": url, "status": "ready"}

    # UI summary override: hide any text labels inside the node header
    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        return []

    def _convert_molecules_to_pdb_data(self, molecules: list) -> Optional[str]:
        """Convert a list of RDKit Mol objects to a concatenated PDB text string."""
        try:
            from rdkit import Chem  # type: ignore
            from rdkit.Chem import AllChem

            self.logger.info(f"Processing {len(molecules)} molecules for 3D viewer")
            pdb_blocks: list[str] = []
            for i, mol in enumerate(molecules):
                if mol is None:
                    continue
                try:
                    if mol.GetNumConformers() == 0:
                        try:
                            AllChem.EmbedMolecule(mol)
                        except Exception:
                            try:
                                AllChem.Compute2DCoords(mol)
                            except Exception:
                                pass
                    block = Chem.MolToPDBBlock(mol)
                    if block and block.strip():
                        pdb_blocks.append(block)
                except Exception as e:
                    try:
                        self.logger.warning(f"Failed to convert molecule {i} to PDB: {e}")
                    except Exception:
                        pass
            if pdb_blocks:
                self.logger.info(f"Successfully converted {len(pdb_blocks)} molecules to PDB format")
                return "\n".join(pdb_blocks)
            self.logger.warning("No molecules could be converted to PDB format")
        except ImportError:
            self.logger.error("RDKit not available for molecule conversion")
        except Exception as e:
            self.logger.error(f"Error processing molecules: {e}")
        return None





