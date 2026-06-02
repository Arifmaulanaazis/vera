"""Web3DViewerNode implementation."""

from .common import *  # noqa: F401,F403

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
