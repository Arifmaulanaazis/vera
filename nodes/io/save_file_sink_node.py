"""SaveFileSinkNode implementation."""

from .common import *  # noqa: F401,F403

class SaveFileSinkNode(BaseNode):
    """Sink node that saves incoming data to a file and produces no outputs.

    Accepts one of: molecules | bytes | image | string | data.
    """

    def __init__(self):
        super().__init__("save_file", "Save File")
        self.logger = get_logger(__name__)

        # Inputs only (no outputs)
        self.add_input_port("molecules", "molecules")
        self.add_input_port("bytes", "bytes")
        self.add_input_port("image", "image")
        self.add_input_port("string", "string")
        self.add_input_port("data", "data")
        self.add_input_port("model", "model")

        # Properties
        self.set_property("output_path", "")
        self.set_property("file_type", "auto")
        self.set_property("overwrite", True)

        # Inline Browse UI
        try:
            from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QFileDialog, QSpacerItem, QSizePolicy

            self.width = 320
            self.height = 140
            try:
                self.setMinimumSize(self.width, self.height)
                self.setMaximumSize(self.width, self.height)
            except Exception:
                pass

            layout = self.content_layout
            if layout is not None:
                layout.addItem(QSpacerItem(0, 6, QSizePolicy.Minimum, QSizePolicy.Fixed), 0, 0, 1, 3)
                lbl = QLabel("Output Path")
                lbl.setStyleSheet("QLabel { background: transparent; }")
                edit = QLineEdit(self.get_property("output_path") or "")
                btn = QPushButton("Browse…")

                def on_browse():  # pragma: no cover - UI-only
                    try:
                        filters = (
                            "Molecules (*.sdf *.mol *.mol2 *.pdb *.pdbqt *.xyz);;"
                            "Data (*.csv *.tsv *.xlsx *.xls *.json *.txt);;"
                            "Images (*.png *.jpg *.jpeg);;"
                            "All Files (*)"
                        )
                        filename, _ = QFileDialog.getSaveFileName(None, "Select Output File", edit.text(), filters)
                        if filename:
                            edit.setText(filename)
                            self.set_property("output_path", filename)
                    except Exception:
                        pass

                def on_text_changed(text: str):
                    try:
                        self.set_property("output_path", text)
                    except Exception:
                        pass

                edit.textChanged.connect(on_text_changed)
                btn.clicked.connect(on_browse)

                layout.addWidget(lbl, 1, 0)
                layout.addWidget(edit, 1, 1)
                layout.addWidget(btn, 1, 2)
            self._update_port_positions()
        except Exception:
            pass

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Headless-safe save logic (no GUI object instantiation)
        out_path = self.get_property("output_path")
        if not out_path:
            raise ValueError("Output path is required")
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        ftype = self.get_property("file_type") or "auto"
        if ftype == "auto":
            ftype = out.suffix.lower().lstrip('.')
        if out.exists() and not bool(self.get_property("overwrite")):
            raise ValueError(f"File already exists and overwrite is disabled: {out}")

        data = inputs or {}
        # Save molecules
        if data.get("molecules") is not None:
            try:
                from rdkit import Chem
                from backend.temp_manager import get_subdir
                import subprocess
                from utils.external_tools import resolve_openbabel_executable
                molecules = data.get("molecules") or []
                if ftype == 'sdf':
                    writer = Chem.SDWriter(str(out))
                    for m in molecules:
                        if m is not None:
                            writer.write(m)
                    writer.close()
                elif ftype == 'mol':
                    if molecules:
                        Chem.MolToMolFile(molecules[0], str(out))
                elif ftype == 'mol2':
                    if molecules:
                        Chem.MolToMol2File(molecules[0], str(out))
                elif ftype == 'pdb':
                    if molecules:
                        Chem.MolToPDBFile(molecules[0], str(out))
                elif ftype == 'pdbqt':
                    if molecules:
                        tmp_dir = get_subdir("save_molecule")
                        pdb_tmp = Path(tmp_dir) / "tmp_for_pdbqt.pdb"
                        Chem.MolToPDBFile(molecules[0], str(pdb_tmp))
                        obabel = resolve_openbabel_executable("obabel")
                        ob_dir = Path(obabel).parent if isinstance(obabel, str) else None
                        cmd = [obabel, str(pdb_tmp), "-O", str(out)]
                        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120, cwd=str(ob_dir) if ob_dir else None, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                elif ftype == 'xyz':
                    # Write XYZ format
                    with open(out, 'w', encoding='utf-8') as f:
                        for mol in molecules:
                            if mol is None:
                                continue
                            
                            # Create XYZ content
                            xyz_content = _create_xyz_content(mol)
                            if xyz_content:
                                f.write(xyz_content)
                                # Add blank line between molecules if multiple
                                if len(molecules) > 1:
                                    f.write("\n")
                else:
                    raise ValueError(f"Unsupported molecule file type: {ftype}")
            except ImportError:
                raise RuntimeError("RDKit not available, cannot save molecular files")
        # Raw bytes or image
        elif data.get("bytes") is not None:
            out.write_bytes(data.get("bytes") or b"")
        elif data.get("image") is not None:
            out.write_bytes(data.get("image") or b"")
        # ML model objects
        elif data.get("model") is not None:
            model_obj = data.get("model")
            try:
                ext = out.suffix.lower().lstrip('.')
                ft = (self.get_property("file_type") or ext or "").lower()
                if ft in ("", "auto"):
                    ft = ext
                if ft == "jl":
                    ft = "joblib"
                if ft == "pickle":
                    ft = "pkl"
                if ft == "joblib":
                    try:
                        import joblib  # type: ignore
                        joblib.dump(model_obj, str(out))
                    except Exception as e:
                        # Fallback to pickle
                        import pickle
                        self.logger.warning(f"joblib save failed ({e}); falling back to pickle")
                        with open(out, 'wb') as f:
                            pickle.dump(model_obj, f, protocol=pickle.HIGHEST_PROTOCOL)
                else:
                    import pickle
                    with open(out, 'wb') as f:
                        pickle.dump(model_obj, f, protocol=pickle.HIGHEST_PROTOCOL)
            except Exception as e:
                raise RuntimeError(f"Error saving model: {e}")
        # String
        elif data.get("string") is not None:
            text = data.get("string")
            if not isinstance(text, str):
                text = str(text)
            out.write_text(text, encoding="utf-8")
        # Generic data
        elif "data" in data:
            payload = data.get("data")
            if ftype == 'csv':
                import pandas as _pd
                if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                    _pd.DataFrame(payload).to_csv(out, index=False)
                else:
                    if hasattr(payload, 'to_csv'):
                        payload.to_csv(out, index=False)
                    else:
                        raise ValueError("Data must be list-of-dicts or DataFrame for CSV output")
            elif ftype == 'tsv':
                import pandas as _pd
                if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                    _pd.DataFrame(payload).to_csv(out, index=False, sep='\t')
                else:
                    if hasattr(payload, 'to_csv'):
                        payload.to_csv(out, index=False, sep='\t')
                    else:
                        raise ValueError("Data must be list-of-dicts or DataFrame for TSV output")
            elif ftype == 'json':
                out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            elif ftype == 'txt':
                out.write_text(str(payload), encoding="utf-8")
            elif ftype in {'xlsx', 'xls'}:
                try:
                    # Check if openpyxl is available
                    try:
                        import openpyxl
                    except ImportError:
                        raise RuntimeError("openpyxl is not installed. Please install it with: pip install openpyxl")
                    
                    if hasattr(payload, 'to_excel'):
                        payload.to_excel(out, index=False, engine='openpyxl')
                    elif isinstance(payload, list) and (len(payload) == 0 or isinstance(payload[0], dict)):
                        import pandas as _pd
                        _pd.DataFrame(payload).to_excel(out, index=False, engine='openpyxl')
                    else:
                        raise ValueError("Data must be list-of-dicts or DataFrame for Excel output")
                except Exception as e:
                    # Show the actual error instead of masking it
                    raise RuntimeError(f"Error writing Excel file: {str(e)}") from e
            else:
                out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        else:
            raise ValueError("No valid input provided to save")
        return {}

    def validate(self) -> tuple[bool, str]:
        output_path = self.get_property("output_path")
        if not output_path:
            return False, "Output path not specified"
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return False, f"Cannot create output directory: {e}"
        return True, "Node configuration is valid"
