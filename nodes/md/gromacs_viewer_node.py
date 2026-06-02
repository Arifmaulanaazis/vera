"""GromacsViewerNode implementation."""

from .common import *  # noqa: F401,F403

class GromacsViewerNode(BaseNode):
    """
    GROMACS Viewer Node for visualizing MD trajectories using web-based NGL.js viewer.
    """

    def __init__(self):
        super().__init__("gromacs_viewer", "GROMACS Viewer")
        self.logger = get_logger(__name__)
        self.add_input_port("gro_file", "file")
        self.add_input_port("xtc_file", "file")
        self.add_output_port("viewer_url", "string")

        # Properties for storing data
        self.set_property("gro_data", "")
        self.set_property("trajectory_data", "")
        self.set_property("background", "#000000")
        self.set_property("auto_spin", False)

        # Sizing similar to 3D web viewer
        try:
            self.width = 520
            self.height = 360
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)
            self.set_content_margins(0, 32, 0, 0)
        except Exception:
            pass

        # Add inline web viewer with simple controls
        try:
            from PySide6.QtWidgets import QPushButton, QLineEdit, QSizePolicy
            from PySide6.QtWebEngineWidgets import QWebEngineView
            from PySide6.QtWebEngineCore import QWebEngineSettings

            # Control buttons
            self._btn_view = QPushButton("View MD")
            self._btn_view.setToolTip("Open GROMACS MD trajectory viewer")
            self._btn_view.clicked.connect(self._on_open_viewer)

            # Embedded lightweight viewer
            from core.nodes import BaseNode as _BaseNode
            if not getattr(_BaseNode, "_lightweight_construction", False):
                self._inline_webview = QWebEngineView()
                try:
                    self._inline_webview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                    # Configure WebEngine for MD viewer
                    settings = self._inline_webview.page().settings()
                    settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
                    settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
                    settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
                    # Set initial blank page
                    self._inline_webview.setHtml(
                        "<html><body style='background-color:#000; margin:0; display:flex; align-items:center; justify-content:center; color:#fff; font-family:Arial;'>Load MD trajectory to view</body></html>"
                    )
                except Exception:
                    pass
            else:
                self._inline_webview = None  # type: ignore[assignment]

            layout = self.content_layout
            if layout is not None:
                # Top row: View button
                layout.addWidget(self._btn_view, 0, 0, 1, 3)
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

        except Exception:
            # If widgets cannot be created (headless), skip inline widgets
            self._btn_view = None
            self._inline_webview = None

    def __del__(self):
        """Cleanup threads on destruction."""
        try:
            # Clean up trajectory thread
            if hasattr(self, '_traj_thread') and self._traj_thread and self._traj_thread.isRunning():
                self._traj_thread.quit()
                if not self._traj_thread.wait(1000):
                    self._traj_thread.terminate()
                    self._traj_thread.wait(500)
            
            # Clean up GRO thread
            if hasattr(self, '_gro_thread') and self._gro_thread and self._gro_thread.isRunning():
                self._gro_thread.quit()
                if not self._gro_thread.wait(1000):
                    self._gro_thread.terminate()
                    self._gro_thread.wait(500)
        except Exception:
            pass  # Ignore errors during cleanup

    def _ensure_gromacs_viewer_file_exists(self) -> Path:
        """Ensure the GROMACS viewer HTML exists."""
        try:
            from backend.resource_access import is_using_compiled_resources, get_web_file_path
            
            if is_using_compiled_resources():
                self.logger.info("Using compiled resources for GROMACS web viewer")
                # return Path("web") / "gromacs_viewer.html"
                return get_web_file_path("gromacs_viewer.html")
        except ImportError:
            pass
        except Exception as e:
            self.logger.debug(f"Resource system check failed: {e}")
        
        # Fallback: check if file exists
        path = Path("web") / "gromacs_viewer.html"
        if not path.exists():
            self.logger.error("GROMACS viewer HTML file not found at web/gromacs_viewer.html")
            raise FileNotFoundError(f"GROMACS viewer file not found: {path}")
        
        return path

    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        # No painted labels inside node body
        return []

    def _update_content_geometry(self, force: bool = False) -> None:  # type: ignore[override]
        try:
            super()._update_content_geometry(force)
        except Exception:
            pass
        # Position right floating panel and shift output pins accordingly
        try:
            if getattr(self, "_panel_proxy", None) is not None and getattr(self, "_panel_widget", None) is not None:
                try:
                    self._panel_widget.setFixedHeight(int(self.height))
                except Exception:
                    pass
                panel_w = int(max(180, min(260, self.width * 0.42)))
                try:
                    self._panel_widget.setFixedWidth(panel_w)
                    self._panel_widget.adjustSize()
                except Exception:
                    pass
                x_offset = float(self.width) + 12.0
                self._panel_proxy.setPos(x_offset, 0.0)
                try:
                    def _anchor_override() -> float:
                        return float(self.width) + 12.0 + float(panel_w)
                    object.__setattr__(self, "_get_output_port_anchor_x", _anchor_override)  # type: ignore[arg-type]
                    self._update_port_positions()
                except Exception:
                    pass
        except Exception:
            pass

    # Legacy methods removed - now using web-based viewer

    # Legacy OpenGL viewer methods removed - replaced with web-based ngl.js viewer

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        gro_path = inputs.get("gro_file") if inputs else None
        xtc_path = inputs.get("xtc_file") if inputs else None
        
        if not gro_path:
            raise ValueError("gro_file input is required")
        
        # Store file paths
        try:
            self.set_property("gro_path", str(gro_path))
            self.set_property("xtc_path", str(xtc_path) if xtc_path else "")
            self.set_property("has_xtc", bool(xtc_path))
        except Exception:
            pass
        
        # Compute frame count for trajectory (do this async to avoid lag)
        try:
            if xtc_path:
                # For XTC files, defer frame count calculation to async processing
                self.set_property("frame_count", -1)  # -1 indicates pending calculation
            else:
                self.set_property("frame_count", 1)
        except Exception:
            pass
        
        # Build viewer URL
        try:
            self._ensure_gromacs_viewer_file_exists()
            url = self._build_gromacs_viewer_url(str(gro_path), str(xtc_path) if xtc_path else None)
            self.logger.info(f"Built GROMACS viewer URL with {len(url)} characters")
            
            # Schedule immediate update of inline viewer for responsiveness
            try:
                from PySide6.QtCore import QTimer
                if hasattr(self, '_inline_webview') and self._inline_webview is not None:
                    QTimer.singleShot(100, self._update_inline_viewer)
            except Exception:
                pass
            
            return {"viewer_url": url, "status": "ready"}
        except Exception as e:
            self.logger.error(f"Failed to build GROMACS viewer URL: {e}")
            return {"viewer_url": "", "status": "error"}

    def on_result(self, result: object) -> None:  # type: ignore[override]
        # Update embedded viewer when new results are available
        try:
            super().on_result(result)
        except Exception:
            pass
        
        try:
            self.logger.info("Node execution completed, updating inline viewer")
            
            # Force immediate update of inline viewer
            self._force_update_inline_viewer()
            
            # Update external viewer window if open
            viewer_window = getattr(self, "_viewer_window", None)
            if viewer_window is not None:
                gro_file = self.get_property("gro_path")
                xtc_file = self.get_property("xtc_path")
                
                if gro_file:
                    url = self._build_gromacs_viewer_url(gro_file, xtc_file)
                    if url:
                        try:
                            viewer_window.load_viewer_url(url)
                        except Exception:
                            pass
        except Exception as e:
            self.logger.error(f"Error in on_result: {e}")

    def _force_update_inline_viewer(self):
        """Force immediate update of the inline viewer."""
        try:
            if not hasattr(self, '_inline_webview') or not self._inline_webview:
                self.logger.warning("No inline webview to update")
                return
                
            gro_file = self.get_property("gro_path")
            xtc_file = self.get_property("xtc_path")
            
            self.logger.info(f"Forcing inline viewer update - GRO: {gro_file}, XTC: {xtc_file}")
            
            if gro_file and not xtc_file:
                # For GRO-only: load viewer pointing directly to the GRO file (avoid huge URL params)
                try:
                    url = self._build_gromacs_viewer_url(gro_file=gro_file)
                    if url:
                        from PySide6.QtCore import QUrl
                        qurl = QUrl(url)
                        self._inline_webview.setUrl(qurl)
                        self._inline_webview.load(qurl)
                    else:
                        self.logger.error("Failed to build viewer URL for GRO-only display")
                except Exception as e:
                    self.logger.error(f"Error in force update: {e}")
            else:
                # Call normal update for XTC files or when no files
                self._update_inline_viewer()
                
        except Exception as e:
            self.logger.error(f"Error forcing inline viewer update: {e}")

    def _build_gromacs_viewer_url(self, gro_file: Optional[str] = None, xtc_file: Optional[str] = None, traj_data: Optional[str] = None, traj_file: Optional[str] = None) -> str:
        """Build URL for GROMACS viewer with proper parameters."""
        try:
            from PySide6.QtCore import QUrl
            from urllib.parse import quote
            import base64
            
            # Get viewer file URL
            try:
                from backend.resource_access import get_web_file_url
                base_url = get_web_file_url("gromacs_viewer.html")
            except ImportError:
                viewer_path = self._ensure_gromacs_viewer_file_exists()
                base_url = QUrl.fromLocalFile(str(viewer_path.resolve()))

            params = []
            
            # Handle GRO file
            if gro_file:
                try:
                    gro_path = Path(gro_file)
                    if gro_path.exists():
                        gro_url = QUrl.fromLocalFile(str(gro_path.resolve()))
                        params.append(f"gro_file={quote(gro_url.toString())}")
                    else:
                        params.append(f"gro_file={quote(gro_file)}")
                except Exception:
                    params.append(f"gro_file={quote(gro_file)}")
            
            # Handle XTC trajectory file  
            if xtc_file:
                try:
                    xtc_path = Path(xtc_file)
                    if xtc_path.exists():
                        xtc_url = QUrl.fromLocalFile(str(xtc_path.resolve()))
                        params.append(f"xtc_file={quote(xtc_url.toString())}")
                    else:
                        params.append(f"xtc_file={quote(xtc_file)}")
                except Exception:
                    params.append(f"xtc_file={quote(xtc_file)}")
            
            # Handle trajectory data (processed frames as JSON)
            if traj_file:
                try:
                    # If a traj index file is provided, prefer that (better performance)
                    # Accept either local file path or already a URL
                    from pathlib import Path as _P
                    if traj_file.startswith("file:"):
                        traj_url = traj_file
                    elif _P(traj_file).exists():
                        traj_url = QUrl.fromLocalFile(str(_P(traj_file).resolve())).toString()
                    else:
                        traj_url = traj_file
                    params.append(f"traj_file={quote(traj_url)}")
                except Exception:
                    pass
            elif traj_data:
                try:
                    encoded_data = base64.b64encode(traj_data.encode('utf-8')).decode('ascii')
                    params.append(f"traj_data={quote(encoded_data)}")
                except Exception:
                    pass
            
            # Add display preferences
            params.append(f"bg={self.get_property('background')}")
            params.append(f"spin={'1' if self.get_property('auto_spin') else '0'}")

            query = ("?" + "&".join(params)) if params else ""
            return base_url.toString() + query
            
        except Exception as e:
            self.logger.error(f"Failed to build GROMACS viewer URL: {e}")
            return ""

    def _convert_gro_to_pdb(self, gro_file: str) -> Optional[str]:
        """Convert GRO file to PDB format for web viewer."""
        try:
            # Try with MDAnalysis first (more robust)
            try:
                import MDAnalysis as mda  # type: ignore
                
                # Load structure from GRO file
                u = mda.Universe(gro_file)
                
                # Convert to PDB text
                from io import StringIO
                output = StringIO()
                
                # Write atoms in PDB format
                for i, atom in enumerate(u.atoms):
                    try:
                        # PDB format: ATOM record
                        record = "ATOM  "
                        atom_num = str(i + 1).rjust(5)
                        atom_name = atom.name.ljust(4)
                        res_name = atom.resname.ljust(3)
                        chain_id = getattr(atom, 'chainID', 'A').ljust(1)
                        res_num = str(atom.resid).rjust(4)
                        x = f"{atom.position[0]:8.3f}"
                        y = f"{atom.position[1]:8.3f}"
                        z = f"{atom.position[2]:8.3f}"
                        occupancy = "  1.00"
                        temp_factor = "  0.00"
                        element = atom.element.rjust(2) if hasattr(atom, 'element') else atom.name[:2].rjust(2)
                        
                        line = f"{record}{atom_num} {atom_name} {res_name} {chain_id}{res_num}    {x}{y}{z}{occupancy}{temp_factor}          {element}\n"
                        output.write(line)
                    except Exception:
                        continue
                
                output.write("TER\nEND\n")
                return output.getvalue()
                
            except ImportError:
                # Fallback: simple GRO parser (without MDAnalysis)
                return self._parse_gro_to_pdb_simple(gro_file)
                
        except Exception as e:
            self.logger.error(f"Failed to convert GRO to PDB: {e}")
            # Try simple parser as last resort
            try:
                return self._parse_gro_to_pdb_simple(gro_file)
            except Exception:
                pass
        return None

    def _parse_gro_to_pdb_simple(self, gro_file: str) -> Optional[str]:
        """Simple GRO to PDB converter without MDAnalysis dependency."""
        try:
            from io import StringIO
            output = StringIO()
            
            with open(gro_file, 'r') as f:
                lines = f.readlines()
            
            if len(lines) < 3:
                return None
                
            # Skip first two lines (title and atom count)
            atom_count = int(lines[1].strip())
            
            for i, line in enumerate(lines[2:2+atom_count]):
                try:
                    # GRO format: resid resname atomname atomid x y z [vx vy vz]
                    if len(line) < 44:  # minimum length for coordinates
                        continue
                        
                    resid = int(line[0:5].strip())
                    resname = line[5:10].strip()
                    atomname = line[10:15].strip()
                    atomid = int(line[15:20].strip())
                    
                    # Coordinates in nm, convert to Angstrom
                    x = float(line[20:28].strip()) * 10.0
                    y = float(line[28:36].strip()) * 10.0  
                    z = float(line[36:44].strip()) * 10.0
                    
                    # Guess element from atom name
                    element = atomname[0].upper()
                    if len(atomname) > 1 and atomname[1].islower():
                        element = atomname[:2].capitalize()
                    
                    # PDB format
                    record = "ATOM  "
                    atom_num = str(i + 1).rjust(5)
                    atom_name = atomname.ljust(4)
                    res_name = resname.ljust(3)
                    chain_id = "A"
                    res_num = str(resid).rjust(4)
                    x_str = f"{x:8.3f}"
                    y_str = f"{y:8.3f}"
                    z_str = f"{z:8.3f}"
                    occupancy = "  1.00"
                    temp_factor = "  0.00"
                    element_str = element.rjust(2)
                    
                    line_pdb = f"{record}{atom_num} {atom_name} {res_name} {chain_id}{res_num}    {x_str}{y_str}{z_str}{occupancy}{temp_factor}          {element_str}\n"
                    output.write(line_pdb)
                    
                except Exception as e:
                    continue
            
            output.write("TER\nEND\n")
            result = output.getvalue()
            
            if len(result.split('\n')) > 2:  # At least some atoms converted
                return result
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"Simple GRO parser failed: {e}")
            return None

    def _process_trajectory_data(self, gro_file: str, xtc_file: Optional[str]) -> Optional[str]:
        """Process MD trajectory for web viewer (synchronous version for single GRO)."""
        try:
            if not xtc_file:
                # Only structure, no trajectory - this should work quickly
                pdb_data = self._convert_gro_to_pdb(gro_file)
                if pdb_data:
                    import json
                    traj_json = {
                        "frames": [pdb_data],
                        "frame_count": 1
                    }
                    return json.dumps(traj_json)
                return None
            
            # For trajectory files, we'll process asynchronously
            self.logger.info("XTC trajectory detected - will process asynchronously")
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to process trajectory: {e}")
            return None

    def _process_trajectory_async(self, gro_file: str, xtc_file: str):
        """Start asynchronous trajectory processing."""
        try:
            from PySide6.QtCore import QThread, QObject, Signal
            
            class TrajectoryWorker(QObject):
                finished = Signal(str, int)  # traj_data OR traj_file (URL), frame_count
                error = Signal(str)
                progress = Signal(int, str)
                
                def __init__(self, gro_file: str, xtc_file: str, parent_node):
                    super().__init__()
                    self.gro_file = gro_file
                    self.xtc_file = xtc_file
                    self.parent_node = parent_node
                
                def process(self):
                    try:
                        self.progress.emit(5, "Checking trajectory files...")
                        
                        # Validate files exist
                        from pathlib import Path
                        if not Path(self.gro_file).exists():
                            self.error.emit(f"GRO file not found: {self.gro_file}")
                            return
                        if not Path(self.xtc_file).exists():
                            self.error.emit(f"XTC file not found: {self.xtc_file}")
                            return
                        
                        self.progress.emit(10, "Loading trajectory...")
                        
                        import MDAnalysis as mda  # type: ignore
                        
                        # Load trajectory with better error handling
                        try:
                            u = mda.Universe(self.gro_file, self.xtc_file)
                        except Exception as e:
                            self.error.emit(f"Failed to load MD files: {str(e)}")
                            return
                        
                        total_frames = len(u.trajectory)
                        
                        # Decide sampling to cap to ~50 frames
                        max_frames = min(50, total_frames)
                        step = max(1, total_frames // max_frames)
                        self.progress.emit(20, f"Processing {max_frames} frames from {total_frames} total...")
                        
                        # Prepare temp output directory for frames
                        from backend.temp_manager import get_subdir
                        import uuid as _uuid
                        out_base = get_subdir(f"gmx_traj_{_uuid.uuid4().hex[:8]}")
                        frames_dir = out_base / "frames"
                        frames_dir.mkdir(parents=True, exist_ok=True)
                        
                        frame_file_urls = []
                        
                        idx = 0
                        i = 0
                        try:
                            # Use range by counting idx up to max_frames
                            while idx < max_frames and i < total_frames:
                                try:
                                    u.trajectory[i]
                                    # Convert frame to PDB text
                                    from io import StringIO
                                    output = StringIO()
                                    for j, atom in enumerate(u.atoms):
                                        try:
                                            record = "ATOM  "
                                            atom_num = str(j + 1).rjust(5)
                                            atom_name = atom.name.ljust(4)
                                            res_name = atom.resname.ljust(3)
                                            chain_id = getattr(atom, 'chainID', 'A').ljust(1)
                                            res_num = str(atom.resid).rjust(4)
                                            x = f"{atom.position[0]:8.3f}"
                                            y = f"{atom.position[1]:8.3f}"
                                            z = f"{atom.position[2]:8.3f}"
                                            occupancy = "  1.00"
                                            temp_factor = "  0.00"
                                            element = atom.element.rjust(2) if hasattr(atom, 'element') else atom.name[:2].rjust(2)
                                            
                                            line = f"{record}{atom_num} {atom_name} {res_name} {chain_id}{res_num}    {x}{y}{z}{occupancy}{temp_factor}          {element}\n"
                                            output.write(line)
                                        except Exception:
                                            continue
                                    output.write("TER\nEND\n")
                                    
                                    # Write to file
                                    frame_path = frames_dir / f"frame_{idx:04d}.pdb"
                                    frame_text = output.getvalue()
                                    frame_path.write_text(frame_text, encoding="utf-8")
                                    frame_file_urls.append(frame_path.as_uri())
                                    
                                    # Progress
                                    progress = 20 + int((idx / max_frames) * 70)
                                    self.progress.emit(progress, f"Frame {idx+1}/{max_frames} (source frame {i+1})")
                                    
                                    idx += 1
                                    i += step
                                except Exception as e:
                                    # Skip problematic frame, continue
                                    i += step
                                    continue
                        except Exception as _e:
                            pass
                        
                        if not frame_file_urls:
                            self.error.emit("No frames could be processed from trajectory")
                            return
                        
                        self.progress.emit(95, "Finalizing trajectory index...")
                        
                        # Write index.json
                        import json
                        index_data = {
                            "frameFiles": frame_file_urls,
                            "frame_count": len(frame_file_urls),
                            "source_frame_count": total_frames
                        }
                        index_path = out_base / "index.json"
                        index_path.write_text(json.dumps(index_data), encoding="utf-8")
                        
                        self.progress.emit(100, f"Complete! Processed {len(frame_file_urls)} frames")
                        # Return file URL to index.json so the viewer can fetch lazily
                        self.finished.emit(index_path.as_uri(), total_frames)
                        
                    except ImportError:
                        self.error.emit("MDAnalysis not available for trajectory processing. Please install MDAnalysis.")
                    except Exception as e:
                        self.error.emit(f"Trajectory processing failed: {str(e)}")
            
            # Check if already processing and stop previous thread
            if hasattr(self, '_traj_thread') and self._traj_thread and self._traj_thread.isRunning():
                self.logger.warning("Stopping previous trajectory processing")
                self._traj_thread.quit()
                self._traj_thread.wait(3000)  # Wait up to 3 seconds
                if self._traj_thread.isRunning():
                    self._traj_thread.terminate()
                    self._traj_thread.wait(1000)
            
            # Create worker and thread
            self._traj_thread = QThread(self)  # Set parent to prevent premature destruction
            self._traj_worker = TrajectoryWorker(gro_file, xtc_file, self)
            self._traj_worker.moveToThread(self._traj_thread)
            
            # Connect signals with Qt.QueuedConnection for thread safety
            from PySide6.QtCore import Qt
            self._traj_thread.started.connect(self._traj_worker.process, Qt.QueuedConnection)
            self._traj_worker.finished.connect(self._on_trajectory_ready, Qt.QueuedConnection)
            self._traj_worker.error.connect(self._on_trajectory_error, Qt.QueuedConnection)
            self._traj_worker.progress.connect(self._on_trajectory_progress, Qt.QueuedConnection)
            
            # Cleanup when done - use Qt.QueuedConnection for thread safety
            self._traj_worker.finished.connect(self._cleanup_trajectory_thread, Qt.QueuedConnection)
            self._traj_worker.error.connect(self._cleanup_trajectory_thread, Qt.QueuedConnection)
            
            # Start processing
            self._traj_thread.start()
            self.logger.info("Started asynchronous trajectory processing")
            
        except Exception as e:
            self.logger.error(f"Failed to start trajectory processing: {e}")
            self._on_trajectory_error(str(e))

    def _cleanup_trajectory_thread(self):
        """Clean up trajectory processing thread safely."""
        try:
            if hasattr(self, '_traj_thread') and self._traj_thread:
                self._traj_thread.quit()
                if not self._traj_thread.wait(2000):  # Wait 2 seconds
                    self._traj_thread.terminate()
                    self._traj_thread.wait(1000)
                self._traj_thread.deleteLater()
                self._traj_thread = None
            
            if hasattr(self, '_traj_worker') and self._traj_worker:
                self._traj_worker.deleteLater()
                self._traj_worker = None
        except Exception as e:
            self.logger.error(f"Error cleaning up trajectory thread: {e}")

    def _on_trajectory_ready(self, traj_data: str, frame_count: int = 1):
        """Handle completion of asynchronous trajectory processing."""
        try:
            self.logger.info(f"Trajectory processing completed with {frame_count} frames, data length: {len(traj_data) if traj_data else 0}")
            
            # Update frame count property
            try:
                self.set_property("frame_count", frame_count)
            except Exception:
                pass
            
            # Update viewer with processed data
            if hasattr(self, '_inline_webview') and self._inline_webview and traj_data:
                # Detect if we received a file URL (preferred) or inline JSON
                if isinstance(traj_data, str) and traj_data.startswith("file:"):
                    url = self._build_gromacs_viewer_url(traj_file=traj_data)
                else:
                    url = self._build_gromacs_viewer_url(traj_data=traj_data)
                self.logger.info(f"Built trajectory viewer URL: {len(url)} characters")
                
                if url:
                    from PySide6.QtCore import QUrl
                    qurl = QUrl(url)
                    self.logger.info(f"Loading trajectory URL in inline viewer: {qurl.toString()[:200]}...")
                    
                    # Force load the URL
                    self._inline_webview.setUrl(qurl)
                    self._inline_webview.load(qurl)
                else:
                    self._on_trajectory_error("Failed to build viewer URL")
            else:
                if not hasattr(self, '_inline_webview'):
                    self.logger.warning("No inline webview available for trajectory")
                elif not self._inline_webview:
                    self.logger.warning("Inline webview is None for trajectory")
                elif not traj_data:
                    self.logger.warning("No trajectory data to display")
            
            # Update external viewer if open
            viewer_window = getattr(self, "_viewer_window", None)
            if viewer_window is not None and traj_data:
                if isinstance(traj_data, str) and traj_data.startswith("file:"):
                    url = self._build_gromacs_viewer_url(traj_file=traj_data)
                else:
                    url = self._build_gromacs_viewer_url(traj_data=traj_data)
                if url:
                    try:
                        viewer_window.load_viewer_url(url)
                    except Exception:
                        pass
                        
        except Exception as e:
            self.logger.error(f"Failed to update viewer with trajectory: {e}")
            self._on_trajectory_error(str(e))

    def _on_trajectory_error(self, error_msg: str):
        """Handle trajectory processing errors."""
        self.logger.error(f"Trajectory processing failed: {error_msg}")
        
        # Show error in viewer
        try:
            error_html = f"""
            <html><body style='background-color:#000; margin:0; display:flex; align-items:center; justify-content:center; color:#fff; font-family:Arial;'>
                <div style='text-align:center;'>
                    <div style='font-size:18px; margin-bottom:10px; color:#ff6b6b;'>❌ Trajectory Processing Failed</div>
                    <div style='font-size:14px; color:#aaa; margin-bottom:15px;'>{error_msg[:100]}{'...' if len(error_msg) > 100 else ''}</div>
                    <div style='font-size:12px; color:#666;'>Attempting to show structure only...</div>
                </div>
            </body></html>
            """
            if hasattr(self, '_inline_webview') and self._inline_webview:
                self._inline_webview.setHtml(error_html)
        except Exception:
            pass
        
        # Fallback to GRO-only display
        try:
            gro_file = self.get_property("gro_path")
            if gro_file:
                # Use async processing for GRO fallback too
                self._process_gro_async(gro_file)
        except Exception as e:
            self.logger.error(f"Fallback to GRO failed: {e}")

    def _on_trajectory_progress(self, percent: int, message: str):
        """Handle trajectory processing progress updates with visual feedback."""
        self.logger.info(f"Trajectory processing: {percent}% - {message}")
        
        # Update the viewer with progress information
        try:
            if hasattr(self, '_inline_webview') and self._inline_webview:
                progress_html = f"""
                <html><body style='background-color:#000; margin:0; display:flex; align-items:center; justify-content:center; color:#fff; font-family:Arial;'>
                    <div style='text-align:center;'>
                        <div style='font-size:18px; margin-bottom:15px;'>Processing MD Trajectory...</div>
                        <div style='width:300px; height:6px; background:#333; border-radius:3px; margin:0 auto 15px;'>
                            <div style='width:{percent}%; height:100%; background:linear-gradient(90deg, #4CAF50, #45a049); border-radius:3px; transition:width 0.3s ease;'></div>
                        </div>
                        <div style='font-size:14px; color:#aaa; margin-bottom:5px;'>{percent}% Complete</div>
                        <div style='font-size:12px; color:#666;'>{message}</div>
                    </div>
                </body></html>
                """
                self._inline_webview.setHtml(progress_html)
        except Exception:
            pass

    def _on_open_viewer(self):
        """Open the GROMACS MD viewer window."""
        try:
            gro_file = self.get_property("gro_path")
            xtc_file = self.get_property("xtc_path")
            
            if not gro_file:
                self.logger.warning("No GRO file available to view")
                return
            
            # Build viewer URL
            url = self._build_gromacs_viewer_url(gro_file, xtc_file)
            
            if not url:
                self.logger.error("Failed to build viewer URL")
                return
            
            # Open in external viewer window
            from core.webviewer import MoleculeWebViewerWindow
            win = MoleculeWebViewerWindow()
            win.setWindowTitle("GROMACS MD Trajectory Viewer")
            win.load_viewer_url(url)
            win.show()
            self._viewer_window = win
            
        except Exception as e:
            self.logger.error(f"Failed to open GROMACS viewer: {e}")

    def _update_inline_viewer(self) -> None:
        """Update the embedded viewer with current data."""
        try:
            if not hasattr(self, '_inline_webview') or not self._inline_webview:
                return
            
            gro_file = self.get_property("gro_path")
            xtc_file = self.get_property("xtc_path")
            
            if not gro_file:
                # Show default message
                default_html = """
                <html><body style='background-color:#000; margin:0; display:flex; align-items:center; justify-content:center; color:#fff; font-family:Arial;'>
                    <div style='text-align:center;'>
                        <div style='font-size:18px; margin-bottom:10px;'>📁 Load MD Trajectory to view</div>
                        <div style='font-size:14px; color:#aaa;'>Connect GRO and/or XTC files</div>
                    </div>
                </body></html>
                """
                self._inline_webview.setHtml(default_html)
                return
            
            if xtc_file:
                # For trajectory files, check if already processing
                if hasattr(self, '_traj_thread') and self._traj_thread and self._traj_thread.isRunning():
                    # Already processing, don't start again
                    return
                
                # Show loading message in viewer
                loading_html = """
                <html><body style='background-color:#000; margin:0; display:flex; align-items:center; justify-content:center; color:#fff; font-family:Arial;'>
                    <div style='text-align:center;'>
                        <div style='font-size:18px; margin-bottom:10px;'>🔄 Processing MD Trajectory...</div>
                        <div style='font-size:14px; color:#aaa;'>This may take a few moments</div>
                        <div style='font-size:12px; color:#666; margin-top:10px;'>Processing up to 50 frames for web viewer</div>
                    </div>
                </body></html>
                """
                self._inline_webview.setHtml(loading_html)
                
                # Start async processing
                self.logger.info("Starting XTC trajectory processing...")
                self._process_trajectory_async(gro_file, xtc_file)
            else:
                # For GRO-only files, process in thread to avoid UI blocking
                self._process_gro_async(gro_file)
                    
        except Exception as e:
            self.logger.error(f"Failed to update inline viewer: {e}")
            # Show error in viewer
            try:
                error_html = f"""
                <html><body style='background-color:#000; margin:0; display:flex; align-items:center; justify-content:center; color:#fff; font-family:Arial;'>
                    <div style='text-align:center;'>
                        <div style='font-size:18px; margin-bottom:10px; color:#ff6b6b;'>❌ Error</div>
                        <div style='font-size:14px; color:#aaa;'>{str(e)[:100]}{'...' if len(str(e)) > 100 else ''}</div>
                    </div>
                </body></html>
                """
                if hasattr(self, '_inline_webview') and self._inline_webview:
                    self._inline_webview.setHtml(error_html)
            except Exception:
                pass

    def _process_gro_async(self, gro_file: str):
        """Process GRO file asynchronously to avoid UI blocking."""
        try:
            from PySide6.QtCore import QThread, QObject, Signal
            
            class GroWorker(QObject):
                finished = Signal(str)
                error = Signal(str)
                
                def __init__(self, gro_file: str, parent_node):
                    super().__init__()
                    self.gro_file = gro_file
                    self.parent_node = parent_node
                
                def process(self):
                    try:
                        # Process GRO file
                        traj_data = self.parent_node._process_trajectory_data(self.gro_file, None)
                        if traj_data:
                            self.finished.emit(traj_data)
                        else:
                            self.error.emit("Failed to convert GRO file")
                    except Exception as e:
                        self.error.emit(str(e))
            
            # Stop any existing GRO processing
            if hasattr(self, '_gro_thread') and self._gro_thread and self._gro_thread.isRunning():
                self._gro_thread.quit()
                self._gro_thread.wait(1000)
                if self._gro_thread.isRunning():
                    self._gro_thread.terminate()
                    self._gro_thread.wait(500)
            
            # Create worker and thread
            self._gro_thread = QThread(self)  # Set parent to prevent premature destruction
            self._gro_worker = GroWorker(gro_file, self)
            self._gro_worker.moveToThread(self._gro_thread)
            
            # Connect signals with Qt.QueuedConnection for thread safety
            from PySide6.QtCore import Qt
            self._gro_thread.started.connect(self._gro_worker.process, Qt.QueuedConnection)
            self._gro_worker.finished.connect(self._on_gro_ready, Qt.QueuedConnection)
            self._gro_worker.error.connect(self._on_gro_error, Qt.QueuedConnection)
            
            # Cleanup when done
            self._gro_worker.finished.connect(self._cleanup_gro_thread, Qt.QueuedConnection)
            self._gro_worker.error.connect(self._cleanup_gro_thread, Qt.QueuedConnection)
            
            # Start processing
            self._gro_thread.start()
            
        except Exception as e:
            self.logger.error(f"Failed to start GRO processing: {e}")
            self._on_gro_error(str(e))
    
    def _cleanup_gro_thread(self):
        """Clean up GRO processing thread safely."""
        try:
            if hasattr(self, '_gro_thread') and self._gro_thread:
                self._gro_thread.quit()
                if not self._gro_thread.wait(1000):  # Wait 1 second
                    self._gro_thread.terminate()
                    self._gro_thread.wait(500)
                self._gro_thread.deleteLater()
                self._gro_thread = None
            
            if hasattr(self, '_gro_worker') and self._gro_worker:
                self._gro_worker.deleteLater()
                self._gro_worker = None
        except Exception as e:
            self.logger.error(f"Error cleaning up GRO thread: {e}")
    
    def _on_gro_ready(self, traj_data: str):
        """Handle completion of GRO processing."""
        try:
            self.logger.info("GRO processing completed")
            
            # Update viewer with processed data
            if hasattr(self, '_inline_webview') and self._inline_webview:
                gro_file = self.get_property("gro_path")
                url = self._build_gromacs_viewer_url(gro_file=gro_file)
                self.logger.info(f"Built GRO viewer URL: {len(url)} characters")
                if url:
                    from PySide6.QtCore import QUrl
                    qurl = QUrl(url)
                    self.logger.info(f"Loading URL in inline viewer: {qurl.toString()[:200]}...")
                    self._inline_webview.setUrl(qurl)
                    self._inline_webview.load(qurl)
                else:
                    self._on_gro_error("Failed to build viewer URL")
            else:
                if not hasattr(self, '_inline_webview'):
                    self.logger.warning("No inline webview available")
                elif not self._inline_webview:
                    self.logger.warning("Inline webview is None")
                else:
                    self.logger.warning("Inline webview not ready to display GRO")
            
        except Exception as e:
            self.logger.error(f"Failed to update viewer with GRO data: {e}")
            self._on_gro_error(str(e))
    
    def _on_gro_error(self, error_msg: str):
        """Handle GRO processing errors."""
        self.logger.error(f"GRO processing failed: {error_msg}")
        
        try:
            error_html = f"""
            <html><body style='background-color:#000; margin:0; display:flex; align-items:center; justify-content:center; color:#fff; font-family:Arial;'>
                <div style='text-align:center;'>
                    <div style='font-size:18px; margin-bottom:10px; color:#ff6b6b;'>❌ Failed to load structure</div>
                    <div style='font-size:14px; color:#aaa;'>Check if the GRO file is valid</div>
                    <div style='font-size:12px; color:#666; margin-top:10px;'>{error_msg[:80]}{'...' if len(error_msg) > 80 else ''}</div>
                </div>
            </body></html>
            """
            if hasattr(self, '_inline_webview') and self._inline_webview:
                self._inline_webview.setHtml(error_html)
        except Exception:
            pass
