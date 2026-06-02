"""ProLIFInteractionNode implementation."""

from .common import *  # noqa: F401,F403

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
