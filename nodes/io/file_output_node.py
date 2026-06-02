"""FileOutputNode implementation."""

from .common import *  # noqa: F401,F403

class FileOutputNode(BaseNode):
    """Node for saving data and molecules to files."""
    
    def __init__(self):
        super().__init__("file_output", "File Output")
        self.logger = get_logger(__name__)
        
        # Add ports
        self.add_input_port("molecules", "molecules")
        self.add_input_port("data", "data")
        self.add_input_port("string", "string")
        self.add_input_port("bytes", "bytes")
        self.add_input_port("image", "image")
        self.add_input_port("model", "model")
        self.add_output_port("saved_file", "string")
        self.add_output_port("file_size", "data")
        
        # Default properties
        self.set_property("output_path", "")
        # auto, sdf, mol, mol2, pdb, pdbqt, csv, tsv, xlsx, xls, json, txt
        self.set_property("file_type", "auto")
        self.set_property("overwrite", True)

        # Inline Browse UI for selecting save path (GUI only)
        try:
            from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QFileDialog, QSpacerItem, QSizePolicy

            # Tidy, consistent size
            self.width = 320
            self.height = 140
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)

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
                            "Molecules (*.sdf *.mol *.mol2 *.pdb *.pdbqt);;"
                            "Data (*.csv *.tsv *.xlsx *.xls *.json *.txt *.arw);;"
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
        """Execute file output operation."""
        try:
            output_path = self.get_property("output_path")
            
            if not output_path:
                raise ValueError("Output path is required")
            
            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            file_type = self.get_property("file_type")
            
            # Auto-detect file type if needed
            if file_type == "auto":
                file_type = output_path_obj.suffix.lower().lstrip('.')
            
            # Check for overwrite
            if output_path_obj.exists() and not self.get_property("overwrite"):
                raise ValueError(f"File already exists and overwrite is disabled: {output_path}")
            
            # Save data based on type
            if inputs and "molecules" in inputs and inputs["molecules"] is not None:
                molecules = inputs["molecules"]
                self._save_molecules(molecules, output_path, file_type)
            elif inputs and "model" in inputs and inputs["model"] is not None:
                self._save_model(inputs["model"], output_path, file_type)
            elif inputs and "bytes" in inputs and inputs["bytes"] is not None:
                # Save raw bytes (e.g., image, SDF, etc.)
                Path(output_path).write_bytes(inputs["bytes"])            
            elif inputs and "image" in inputs and inputs["image"] is not None:
                # Image bytes are also raw bytes
                Path(output_path).write_bytes(inputs["image"])           
            elif inputs and "string" in inputs and inputs["string"] is not None:
                text = inputs["string"]
                if not isinstance(text, str):
                    text = str(text)
                Path(output_path).write_text(text, encoding="utf-8")
            elif inputs and "data" in inputs:
                data = inputs["data"]
                self._save_data(data, output_path, file_type)
            else:
                raise ValueError("No valid input data provided")
            
            self.logger.info(f"Successfully saved file: {output_path}")
            
            return {
                "saved_file": str(output_path),
                "file_size": output_path_obj.stat().st_size if output_path_obj.exists() else 0
            }
            
        except Exception as e:
            self.logger.error(f"Error saving file: {e}")
            raise
    
    def _save_molecules(self, molecules, output_path: str, file_type: str):
        """Save molecules to file."""
        try:
            from rdkit import Chem
            from backend.temp_manager import get_subdir
            from utils.external_tools import resolve_openbabel_executable
            import subprocess

            if file_type == 'sdf':
                writer = Chem.SDWriter(str(output_path))
                for mol in molecules:
                    if mol:
                        writer.write(mol)
                writer.close()

            elif file_type == 'mol':
                if molecules:
                    Chem.MolToMolFile(molecules[0], str(output_path))

            elif file_type == 'mol2':
                # Save first molecule as MOL2
                if molecules:
                    Chem.MolToMol2File(molecules[0], str(output_path))

            elif file_type == 'pdb':
                # Save first molecule as PDB
                if molecules:
                    Chem.MolToPDBFile(molecules[0], str(output_path))

            elif file_type == 'pdbqt':
                # Convert first molecule to PDB then to PDBQT via OpenBabel
                if molecules:
                    tmp_dir = get_subdir("save_molecule")
                    pdb_tmp = Path(tmp_dir) / "tmp_for_pdbqt.pdb"
                    Chem.MolToPDBFile(molecules[0], str(pdb_tmp))
                    obabel = resolve_openbabel_executable("obabel")
                    ob_dir = Path(obabel).parent if isinstance(obabel, str) else None
                    cmd = [obabel, str(pdb_tmp), "-O", str(output_path)]
                    subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=120,
                        cwd=str(ob_dir) if ob_dir else None,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
            elif file_type == 'xyz':
                # Write XYZ format
                with open(output_path, 'w', encoding='utf-8') as f:
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
                raise ValueError(f"Unsupported molecule file type: {file_type}")
                
        except ImportError:
            self.logger.error("RDKit not available, cannot save molecular files")
            raise
        except Exception as e:
            self.logger.error(f"Error saving molecules: {e}")
            raise
    
    def _save_data(self, data, output_path: str, file_type: str):
        """Save data to file."""
        try:
            if file_type == 'csv':
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    df = pd.DataFrame(data)
                    df.to_csv(output_path, index=False)
                else:
                    if hasattr(data, 'to_csv'):
                        data.to_csv(output_path, index=False)
                    else:
                        raise ValueError("Data must be list-of-dicts or DataFrame for CSV output")
            
            elif file_type == 'tsv':
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    df = pd.DataFrame(data)
                    df.to_csv(output_path, index=False, sep='\t')
                else:
                    if hasattr(data, 'to_csv'):
                        data.to_csv(output_path, index=False, sep='\t')
                    else:
                        raise ValueError("Data must be list-of-dicts or DataFrame for TSV output")
                    
            elif file_type == 'json':
                with open(output_path, 'w') as f:
                    json.dump(data, f, indent=2)
                    
            elif file_type == 'txt':
                with open(output_path, 'w') as f:
                    if isinstance(data, str):
                        f.write(data)
                    else:
                        f.write(str(data))
            
            elif file_type in {'xlsx', 'xls'}:
                try:
                    # Check if openpyxl is available
                    try:
                        import openpyxl
                    except ImportError:
                        raise RuntimeError("openpyxl is not installed. Please install it with: pip install openpyxl")
                    
                    if hasattr(data, 'to_excel'):
                        data.to_excel(output_path, index=False, engine='openpyxl')
                    elif isinstance(data, list) and (len(data) == 0 or isinstance(data[0], dict)):
                        pd.DataFrame(data).to_excel(output_path, index=False, engine='openpyxl')
                    else:
                        raise ValueError("Data must be list-of-dicts or DataFrame for Excel output")
                except Exception as e:
                    # Show the actual error instead of masking it
                    raise RuntimeError(f"Error writing Excel file: {str(e)}") from e
                        
            else:
                # Default to JSON for complex data
                with open(output_path, 'w') as f:
                    json.dump(data, f, indent=2)
                    
        except Exception as e:
            self.logger.error(f"Error saving data: {e}")
            raise

    def _save_model(self, model_obj: Any, output_path: str, file_type: str) -> None:
        """Save ML model to file using joblib if available, otherwise pickle.

        Honors file_type if provided (joblib/pkl/pickle), otherwise infers from extension.
        Default falls back to pickle with highest protocol.
        """
        try:
            ext = Path(output_path).suffix.lower().lstrip('.')
            ft = (file_type or ext or "").lower()
            # Normalize common aliases
            if ft in {"", "auto"}:
                ft = ext
            if ft in {"jl"}:
                ft = "joblib"
            if ft in {"pickle"}:
                ft = "pkl"

            if ft in {"joblib"}:
                try:
                    import joblib  # type: ignore
                    joblib.dump(model_obj, output_path)
                    return
                except Exception as e:
                    # Fall back to pickle if joblib unavailable or fails
                    self.logger.warning(f"joblib save failed ({e}); falling back to pickle")

            import pickle
            with open(output_path, 'wb') as f:
                pickle.dump(model_obj, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as e:
            self.logger.error(f"Error saving model: {e}")
            raise
    
    def validate(self) -> tuple[bool, str]:
        """Validate the node configuration."""
        output_path = self.get_property("output_path")
        
        if not output_path:
            return False, "Output path not specified"
        
        # Check if parent directory can be created
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return False, f"Cannot create output directory: {e}"
        
        return True, "Node configuration is valid"
