"""
Resource Manager for Qt PySide Resources
Handles conversion of theme and web folders into compiled Qt resources with smart updating.
"""

import os
import sys
import json
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ResourceManifest:
    """Tracks all files in the resource for comparison with original folders."""
    files: Dict[str, str]  # relative_path -> file_hash
    total_count: int
    created_at: str
    source_folders: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'files': self.files,
            'total_count': self.total_count,
            'created_at': self.created_at,
            'source_folders': self.source_folders
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResourceManifest':
        return cls(
            files=data.get('files', {}),
            total_count=data.get('total_count', 0),
            created_at=data.get('created_at', ''),
            source_folders=data.get('source_folders', [])
        )


class ResourceManager:
    """Manages Qt PySide resources for theme and web folders."""
    
    def __init__(self, project_root: Optional[Path] = None):
        if project_root is None:
            project_root = Path(__file__).parent.parent
        
        self.project_root = Path(project_root)
        self.theme_dir = self.project_root / "theme"
        self.web_dir = self.project_root / "web"
        self.assets_dir = self.project_root / "assets"
        
        # Resource files
        self.qrc_file = self.assets_dir / "vera_resources.qrc"
        self.py_resource_file = self.assets_dir / "vera_resources.py"
        self.manifest_file = self.assets_dir / "resource_manifest.json"
        
        # Add rebuild lock to prevent concurrent rebuilds
        self._rebuild_in_progress = False
        self._rebuild_lock_file = self.assets_dir / ".resource_build.lock"
        
        # Ensure assets directory exists
        self.assets_dir.mkdir(exist_ok=True)
        
        # Try to import existing resources
        self._resource_module = None
        # Detect final/executable mode (packaged app)
        self._final_mode = self._detect_final_mode()
        self._load_resource_module()
    
    def _detect_final_mode(self) -> bool:
        """Detect if running in a packaged/final executable environment.

        Prioritizes compiled resources and skips .qrc/manifest in this mode.
        """
        try:
            if getattr(sys, "frozen", False):  # PyInstaller/py2exe-style
                return True
            # Optional override via environment variable
            if os.environ.get("VERA_FINAL", "").strip() in {"1", "true", "TRUE", "yes", "YES"}:
                return True
        except Exception:
            pass
        return False

    def _load_resource_module(self):
        """Try to load the compiled resource module."""
        # Try multiple import strategies so that packaged apps don't depend on on-disk files
        try:
            # 1) Try importing as a submodule of assets package (common layout)
            try:
                spec = __import__('assets.vera_resources', fromlist=['*'])
                self._resource_module = spec
                logger.info("Loaded resource module 'assets.vera_resources'")
                return
            except Exception:
                pass

            # 2) Try importing as a top-level module (works when assets path is injected)
            try:
                # Add assets directory to path if it exists on disk
                assets_path = str(self.assets_dir)
                if self.assets_dir.exists() and assets_path not in sys.path:
                    sys.path.insert(0, assets_path)
                spec = __import__('vera_resources')
                self._resource_module = spec
                logger.info("Loaded resource module 'vera_resources'")
                return
            except Exception:
                pass

            # Not available
            logger.info("Resource module not found; using original files as fallback")
            self._resource_module = None
        except Exception as e:
            logger.warning(f"Failed to load resource module: {e}")
            self._resource_module = None
    
    def _get_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of a file."""
        try:
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"Failed to hash file {file_path}: {e}")
            return ""
    
    def _scan_folder(self, folder: Path, relative_to: Path) -> Dict[str, str]:
        """Scan folder recursively and return {relative_path: file_hash} mapping."""
        files = {}
        if not folder.exists():
            return files
        
        try:
            for file_path in folder.rglob("*"):
                if file_path.is_file():
                    # Calculate relative path from the base directory
                    relative_path = file_path.relative_to(relative_to)
                    # Use forward slashes for consistency across platforms
                    relative_key = str(relative_path).replace("\\", "/")
                    file_hash = self._get_file_hash(file_path)
                    files[relative_key] = file_hash
        except Exception as e:
            logger.error(f"Failed to scan folder {folder}: {e}")
        
        return files
    
    def _create_current_manifest(self) -> ResourceManifest:
        """Create manifest from current theme and web folders."""
        files = {}
        
        # Scan theme folder
        if self.theme_dir.exists():
            theme_files = self._scan_folder(self.theme_dir, self.project_root)
            files.update(theme_files)
        
        # Scan web folder
        if self.web_dir.exists():
            web_files = self._scan_folder(self.web_dir, self.project_root)
            files.update(web_files)
        
        return ResourceManifest(
            files=files,
            total_count=len(files),
            created_at=str(__import__('datetime').datetime.now()),
            source_folders=['theme', 'web']
        )
    
    def _load_manifest(self) -> Optional[ResourceManifest]:
        """Load manifest from file."""
        try:
            if self.manifest_file.exists():
                with open(self.manifest_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return ResourceManifest.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load manifest: {e}")
        return None
    
    def _save_manifest(self, manifest: ResourceManifest):
        """Save manifest to file."""
        try:
            with open(self.manifest_file, 'w', encoding='utf-8') as f:
                json.dump(manifest.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save manifest: {e}")
    
    def _compare_manifests(self, current: ResourceManifest, stored: ResourceManifest) -> Tuple[bool, List[str]]:
        """Compare manifests and return (needs_rebuild, reasons)."""
        reasons = []
        needs_rebuild = False
        
        # Check if file counts differ
        if current.total_count != stored.total_count:
            reasons.append(f"File count changed: {stored.total_count} -> {current.total_count}")
            needs_rebuild = True
        
        # Check for new files
        new_files = set(current.files.keys()) - set(stored.files.keys())
        if new_files:
            reasons.append(f"New files: {', '.join(list(new_files)[:5])}" + 
                         (f" (and {len(new_files)-5} more)" if len(new_files) > 5 else ""))
            needs_rebuild = True
        
        # Check for removed files
        removed_files = set(stored.files.keys()) - set(current.files.keys())
        if removed_files:
            reasons.append(f"Removed files: {', '.join(list(removed_files)[:5])}" + 
                         (f" (and {len(removed_files)-5} more)" if len(removed_files) > 5 else ""))
            needs_rebuild = True
        
        # Check for modified files
        modified_files = []
        for file_path in set(current.files.keys()) & set(stored.files.keys()):
            if current.files[file_path] != stored.files[file_path]:
                modified_files.append(file_path)
        
        if modified_files:
            reasons.append(f"Modified files: {', '.join(modified_files[:5])}" + 
                         (f" (and {len(modified_files)-5} more)" if len(modified_files) > 5 else ""))
            needs_rebuild = True
        
        return needs_rebuild, reasons
    
    def _generate_qrc_file(self, manifest: ResourceManifest):
        """Generate QRC file from manifest."""
        qrc_content = ['<!DOCTYPE RCC>\n<RCC version="1.0">\n<qresource prefix="/">']
        
        for relative_path in sorted(manifest.files.keys()):
            # Convert back to original file path
            original_path = self.project_root / relative_path
            if original_path.exists():
                # Use forward slashes in QRC file
                qrc_content.append(f'    <file alias="{relative_path}">{original_path.as_posix()}</file>')
        
        qrc_content.append('</qresource>\n</RCC>')
        
        try:
            with open(self.qrc_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(qrc_content))
            logger.info(f"Generated QRC file with {len(manifest.files)} files")
        except Exception as e:
            logger.error(f"Failed to generate QRC file: {e}")
            raise
    
    def _compile_qrc_to_python(self):
        """Compile QRC file to Python resource module."""
        success = False
        errors = []
        
        # Try multiple compilation methods
        compilation_methods = [
            self._try_pyside6_rcc,
            self._try_qt_rcc,
            self._try_python_rcc_fallback
        ]
        
        for method in compilation_methods:
            try:
                method()
                success = True
                break
            except Exception as e:
                errors.append(str(e))
                continue
        
        if not success:
            error_msg = f"All resource compilation methods failed: {'; '.join(errors)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        logger.info(f"Successfully compiled resources to {self.py_resource_file}")
        
        # Make the resource module unreadable/uneditable by adding obfuscation comment
        self._obfuscate_resource_file()
    
    def _try_pyside6_rcc(self):
        """Try using pyside6-rcc tool."""
        cmd = [
            sys.executable, "-m", "PySide6.scripts.pyside_tool", "rcc",
            str(self.qrc_file),
            "-o", str(self.py_resource_file)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(self.project_root), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        
        if result.returncode != 0:
            raise RuntimeError(f"pyside6-rcc failed: {result.stderr}")
    
    def _try_qt_rcc(self):
        """Try using standalone rcc tool."""
        # Try different rcc command names
        rcc_commands = ["rcc", "pyside6-rcc", "pyside2-rcc"]
        
        for cmd_name in rcc_commands:
            try:
                cmd = [cmd_name, str(self.qrc_file), "-o", str(self.py_resource_file)]
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(self.project_root), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                
                if result.returncode == 0:
                    return  # Success
                    
            except FileNotFoundError:
                continue  # Try next command
        
        raise RuntimeError("No working rcc command found")
    
    def _try_python_rcc_fallback(self):
        """Python-based fallback for resource compilation."""
        logger.info("Using Python-based resource compilation fallback")
        
        # Read the QRC file to get file list
        import xml.etree.ElementTree as ET
        
        tree = ET.parse(self.qrc_file)
        root = tree.getroot()
        
        # Generate Python code
        python_code = [
            '"""',
            '# VERA COMPILED RESOURCES - DO NOT EDIT',
            '# This file is automatically generated and will be overwritten.',
            '# Editing this file may break the application.',
            '# To update resources, modify files in theme/ and web/ folders instead.',
            '"""',
            '',
            'import base64',
            'from PySide6.QtCore import QResource',
            '',
            '# Resource data',
            '_resource_data = {}'
        ]
        
        resource_data = {}
        
        # Process each file in the QRC
        for qresource in root.findall('qresource'):
            prefix = qresource.get('prefix', '/')
            
            for file_elem in qresource.findall('file'):
                alias = file_elem.get('alias', file_elem.text)
                file_path = Path(file_elem.text)
                
                if not file_path.is_absolute():
                    file_path = self.project_root / file_path
                
                if file_path.exists():
                    try:
                        import base64
                        with open(file_path, 'rb') as f:
                            file_data = f.read()
                        
                        # Encode as base64 for storage
                        encoded_data = base64.b64encode(file_data).decode('ascii')
                        resource_key = f"{prefix.rstrip('/')}/{alias.lstrip('/')}"
                        resource_data[resource_key] = encoded_data
                        
                    except Exception as e:
                        logger.warning(f"Failed to read resource file {file_path}: {e}")
        
        # Add resource data to Python code
        python_code.append(f'_resource_data = {repr(resource_data)}')
        python_code.extend([
            '',
            'def _register_resources():',
            '    """Register all resources with Qt."""',
            '    for resource_path, encoded_data in _resource_data.items():',
            '        try:',
            '            data = base64.b64decode(encoded_data.encode("ascii"))',
            '            QResource.registerResource(data, resource_path)',
            '        except Exception:',
            '            pass  # Ignore individual resource registration failures',
            '',
            '# Auto-register resources when module is imported',
            'try:',
            '    _register_resources()',
            'except Exception:',
            '    pass  # Ignore registration failures to maintain fallback behavior',
            ''
        ])
        
        # Write the Python file
        with open(self.py_resource_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(python_code))
    
    def _obfuscate_resource_file(self):
        """Add header to resource file to discourage editing."""
        backup_file = None
        try:
            # Create backup before modifying
            import tempfile
            import shutil
            
            # Create backup in same directory to ensure same filesystem
            backup_file = self.py_resource_file.with_suffix('.py.backup')
            if self.py_resource_file.exists():
                shutil.copy2(self.py_resource_file, backup_file)
            else:
                logger.warning("Resource file doesn't exist yet, skipping obfuscation")
                return
            
            # Read current content
            with open(self.py_resource_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Skip if header already exists
            if '# VERA COMPILED RESOURCES - DO NOT EDIT' in content:
                logger.debug("Resource file already has header, skipping")
                if backup_file and backup_file.exists():
                    backup_file.unlink()
                return
            
            header = '''"""
# VERA COMPILED RESOURCES - DO NOT EDIT
# This file is automatically generated and will be overwritten.
# Editing this file may break the application.
# To update resources, modify files in theme/ and web/ folders instead.
"""
'''
            
            # Write with header
            with open(self.py_resource_file, 'w', encoding='utf-8') as f:
                f.write(header + content)
            
            # Verify write was successful by reading back
            with open(self.py_resource_file, 'r', encoding='utf-8') as f:
                verify_content = f.read()
                if len(verify_content) < len(header):
                    raise ValueError("Written file is too small, may be corrupted")
            
            # Success - remove backup
            if backup_file and backup_file.exists():
                backup_file.unlink()
                
        except Exception as e:
            logger.warning(f"Failed to add header to resource file: {e}")
            # Restore from backup if write failed
            if backup_file and backup_file.exists():
                try:
                    import shutil
                    shutil.copy2(backup_file, self.py_resource_file)
                    logger.info("Restored resource file from backup")
                    backup_file.unlink()
                except Exception as restore_error:
                    logger.error(f"Failed to restore from backup: {restore_error}")
    
    def _folders_exist(self) -> bool:
        """Check if theme and web folders exist."""
        return self.theme_dir.exists() or self.web_dir.exists()
    
    def ensure_resources(self) -> bool:
        """
        Main entry point for resource management.
        Returns True if resources are available (either compiled or fallback).
        """
        try:
            logger.info("Checking resource status...")
            
            # In final/executable mode, never touch .qrc or manifest at runtime.
            if self._final_mode:
                logger.info("Final mode detected; using compiled resources only and skipping .qrc/manifest")
                self._load_resource_module()
                # Always return True to allow app to continue; accessors will fall back if needed
                return True
            
            # Case 4: Resource exists but source folders don't exist (final app/exe)
            if self.py_resource_file.exists() and not self._folders_exist():
                logger.info("Using resources in final app mode (no source folders)")
                self._load_resource_module()
                return True
            
            # Case 1: No resource file exists
            if not self.py_resource_file.exists():
                logger.info("No resource file found, creating new resources...")
                return self._build_resources()
            
            # Case 2 & 3: Resource exists, check if it needs updating
            stored_manifest = self._load_manifest()
            if stored_manifest is None:
                logger.info("No manifest found, rebuilding resources...")
                return self._build_resources()
            
            current_manifest = self._create_current_manifest()
            needs_rebuild, reasons = self._compare_manifests(current_manifest, stored_manifest)
            
            if needs_rebuild:
                logger.info(f"Resource needs rebuilding: {'; '.join(reasons)}")
                return self._build_resources()
            else:
                logger.info("Resources are up to date")
                self._load_resource_module()
                return True
                
        except Exception as e:
            logger.error(f"Resource management failed: {e}")
            # Fallback to original files
            return True
    
    def _build_resources(self) -> bool:
        """Build/rebuild resource files."""
        # Check if rebuild is already in progress
        if self._rebuild_in_progress:
            logger.warning("Resource rebuild already in progress, skipping")
            return True
        
        # Check for lock file from another process
        if self._rebuild_lock_file.exists():
            try:
                # Check if lock file is stale (older than 5 minutes)
                import time
                lock_age = time.time() - self._rebuild_lock_file.stat().st_mtime
                if lock_age > 300:  # 5 minutes
                    logger.warning(f"Removing stale lock file (age: {lock_age:.1f}s)")
                    self._rebuild_lock_file.unlink()
                else:
                    logger.warning("Another process is building resources, skipping")
                    return True
            except Exception:
                # If we can't check the lock, proceed anyway
                pass
        
        try:
            # Set rebuild flag and create lock file
            self._rebuild_in_progress = True
            self._rebuild_lock_file.touch()
            
            logger.info("Building resources...")
            
            # Create current manifest
            current_manifest = self._create_current_manifest()
            
            if current_manifest.total_count == 0:
                logger.warning("No files found in theme or web folders")
                return False
            
            # Generate QRC file
            self._generate_qrc_file(current_manifest)
            
            # Compile to Python
            self._compile_qrc_to_python()
            
            # Save manifest
            self._save_manifest(current_manifest)
            
            # Load the new resource module
            self._load_resource_module()
            
            logger.info(f"Successfully built resources with {current_manifest.total_count} files")
            return True
            
        except Exception as e:
            logger.error(f"Failed to build resources: {e}")
            return False
        finally:
            # Always clean up lock
            self._rebuild_in_progress = False
            try:
                if self._rebuild_lock_file.exists():
                    self._rebuild_lock_file.unlink()
            except Exception as cleanup_error:
                logger.warning(f"Failed to remove lock file: {cleanup_error}")
    
    def get_resource_data(self, resource_path: str) -> Optional[bytes]:
        """Get data from resource system with fallback to original file."""
        try:
            # Try resource first
            if self._resource_module:
                from PySide6.QtCore import QFile, QIODevice
                
                # Ensure path starts with :/ for resource access
                if not resource_path.startswith(":/"):
                    resource_path = f":/{resource_path}"
                
                qfile = QFile(resource_path)
                if qfile.open(QIODevice.ReadOnly):
                    data = qfile.readAll()
                    qfile.close()
                    return bytes(data)
        except Exception as e:
            logger.debug(f"Failed to read from resource {resource_path}: {e}")
        
        # Fallback to original file
        try:
            original_path = self.project_root / resource_path.lstrip(":/")
            if original_path.exists():
                return original_path.read_bytes()
        except Exception as e:
            logger.debug(f"Failed to read original file {resource_path}: {e}")
        
        return None
    
    def get_resource_text(self, resource_path: str, encoding: str = 'utf-8') -> Optional[str]:
        """Get text from resource system with fallback to original file."""
        data = self.get_resource_data(resource_path)
        if data:
            try:
                return data.decode(encoding)
            except UnicodeDecodeError as e:
                logger.error(f"Failed to decode resource {resource_path}: {e}")
        return None
    
    def get_resource_path(self, resource_path: str) -> str:
        """Get path for resource - either resource:// or file:// path."""
        try:
            # Check if resource is available
            if self._resource_module:
                from PySide6.QtCore import QFile
                
                qrc_path = f":/{resource_path.lstrip(':/')}"
                if QFile.exists(qrc_path):
                    return qrc_path
        except Exception:
            pass
        
        # Fallback to original file path
        original_path = self.project_root / resource_path.lstrip(":/")
        if original_path.exists():
            return str(original_path)
        
        # Return resource path anyway (might work if resource loads later)
        return f":/{resource_path.lstrip(':/')}"
    
    def is_using_resources(self) -> bool:
        """Check if currently using compiled resources."""
        return self._resource_module is not None
    
    def force_rebuild(self) -> bool:
        """Force rebuild of resources."""
        logger.info("Forcing resource rebuild...")
        return self._build_resources()


# Global instance
_resource_manager: Optional[ResourceManager] = None


def get_resource_manager() -> ResourceManager:
    """Get global resource manager instance."""
    global _resource_manager
    if _resource_manager is None:
        _resource_manager = ResourceManager()
    return _resource_manager


def initialize_resources() -> bool:
    """Initialize the resource system. Call this early in application startup."""
    try:
        manager = get_resource_manager()
        return manager.ensure_resources()
    except Exception as e:
        logger.error(f"Failed to initialize resources: {e}")
        return False


def get_resource_data(resource_path: str) -> Optional[bytes]:
    """Convenience function to get resource data."""
    return get_resource_manager().get_resource_data(resource_path)


def get_resource_text(resource_path: str, encoding: str = 'utf-8') -> Optional[str]:
    """Convenience function to get resource text."""
    return get_resource_manager().get_resource_text(resource_path, encoding)


def get_resource_path(resource_path: str) -> str:
    """Convenience function to get resource path."""
    return get_resource_manager().get_resource_path(resource_path)
