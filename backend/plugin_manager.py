"""
Plugin management for VERA.

Responsibilities:
- Discover installed plugins from the user plugins directory
- Install plugins from .zip/.bsx archives or folders
- Dynamically load plugin entry modules and let them register nodes via a narrow API
- Expose loaded plugin categories and nodes for the toolbox and UI menu

Plugin layout (on disk):
<plugins_root>/<plugin_id>/
  manifest.json              # plugin metadata
  <entry_module>.py          # referenced by manifest.entry_module
  icons/                     # optional, arbitrary assets

manifest.json example:
{
  "id": "hello_vera",
  "name": "Hello VERA",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "Example plugin that adds a Hello World node",
  "entry_module": "hello_vera.py"
}

The entry module must define a function:

def register(api):
    # api.register_node(node_type, NodeClass, display_name, description, category, icon_relpath)
    ...

Notes:
- icon_relpath is optional and should be relative to the plugin root.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

import importlib.util


# -----------------------
# Paths and persistence
# -----------------------

def _user_plugins_root() -> Path:
    """Return the directory where user plugins are installed.

    On Windows: %APPDATA%/VERA/plugins
    Else: ~/.vera/plugins
    """
    try:
        if os.name == "nt":
            appdata = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
            return Path(appdata) / "VERA" / "plugins"
    except Exception:
        pass
    return Path.home() / ".vera" / "plugins"


def ensure_plugins_dir() -> Path:
    root = _user_plugins_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return root


# -----------------------
# Data structures
# -----------------------

@dataclass
class ToolboxNode:
    node_type: str
    display_name: str
    description: str = ""
    icon_path: Optional[Path] = None


@dataclass
class PluginInfo:
    plugin_id: str
    name: str
    version: str
    author: str = ""
    description: str = ""
    path: Path = Path("")
    entry_module: str = ""
    # category name -> list of ToolboxNode
    categories: Dict[str, List[ToolboxNode]] = field(default_factory=dict)
    loaded: bool = False
    load_error: Optional[str] = None


# -----------------------
# In-memory state
# -----------------------

_loaded_plugins: Dict[str, PluginInfo] = {}
_installed_plugins_cache: Optional[List[PluginInfo]] = None


# -----------------------
# Discovery & install
# -----------------------

def _read_manifest(path: Path) -> Optional[dict]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def discover_installed_plugins(force_rescan: bool = False) -> List[PluginInfo]:
    """Scan the plugins directory and return PluginInfo entries (not loaded)."""
    global _installed_plugins_cache
    if (not force_rescan) and (_installed_plugins_cache is not None):
        return list(_installed_plugins_cache)

    plugins: List[PluginInfo] = []
    root = ensure_plugins_dir()
    try:
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            manifest = _read_manifest(child / "manifest.json")
            if not manifest:
                continue
            plugin_id = str(manifest.get("id") or child.name)
            info = PluginInfo(
                plugin_id=plugin_id,
                name=str(manifest.get("name") or plugin_id),
                version=str(manifest.get("version") or "0.0.0"),
                author=str(manifest.get("author") or ""),
                description=str(manifest.get("description") or ""),
                path=child,
                entry_module=str(manifest.get("entry_module") or ""),
            )
            plugins.append(info)
    except Exception:
        # Ignore scanning errors to avoid blocking app start
        pass

    _installed_plugins_cache = plugins
    return list(plugins)


def install_plugin_from_zip(zip_path: str) -> Tuple[bool, str]:
    """Install a plugin from a .zip or .bsx archive.

    Returns (success, message_or_error).
    """
    try:
        p = Path(zip_path)
        if (not p.exists()) or (not p.is_file()):
            return False, "File not found"
        # Extract to temp, read manifest, then move to final dir <plugins_root>/<id>
        import tempfile
        import zipfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            try:
                with zipfile.ZipFile(p, "r") as zf:
                    zf.extractall(tmp)
            except Exception as e:
                return False, f"Failed to extract archive: {e}"

            # Support archive that contains a top-level folder or files directly
            manifest_path = None
            # First try direct
            if (tmp / "manifest.json").exists():
                manifest_path = tmp / "manifest.json"
                plugin_root = tmp
            else:
                # Search inside first-level directories
                for sub in tmp.iterdir():
                    if sub.is_dir() and (sub / "manifest.json").exists():
                        manifest_path = sub / "manifest.json"
                        plugin_root = sub
                        break
            if manifest_path is None:
                return False, "manifest.json not found in plugin archive"
            manifest = _read_manifest(manifest_path)
            if not manifest:
                return False, "Invalid manifest.json"
            pid = str(manifest.get("id") or "").strip()
            if not pid:
                return False, "Manifest is missing required 'id'"
            dest = ensure_plugins_dir() / pid
            # Replace existing installation
            if dest.exists():
                try:
                    shutil.rmtree(dest)
                except Exception:
                    return False, f"Failed to remove existing plugin directory: {dest}"
            shutil.copytree(plugin_root, dest)
        # Reset cache
        global _installed_plugins_cache
        _installed_plugins_cache = None
        return True, "Plugin installed"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def install_plugin_from_folder(folder_path: str) -> Tuple[bool, str]:
    """Install a plugin from a folder containing manifest.json.

    Copies the folder to the user plugins directory under <id>.
    """
    try:
        src = Path(folder_path)
        if (not src.exists()) or (not src.is_dir()):
            return False, "Folder not found"
        manifest = _read_manifest(src / "manifest.json")
        if not manifest:
            return False, "manifest.json not found or invalid"
        pid = str(manifest.get("id") or "").strip()
        if not pid:
            return False, "Manifest is missing required 'id'"
        dest = ensure_plugins_dir() / pid
        if dest.exists():
            try:
                shutil.rmtree(dest)
            except Exception:
                return False, f"Failed to remove existing plugin directory: {dest}"
        # Copytree including files; avoid copying virtual envs or __pycache__ heavy dir
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", ".git", ".venv", "venv"))
        # Reset cache
        global _installed_plugins_cache
        _installed_plugins_cache = None
        return True, "Plugin installed"
    except Exception as e:
        return False, f"Unexpected error: {e}"


# -----------------------
# Loading & API
# -----------------------

class _PluginAPI:
    """API instance passed to plugin entrypoints for registration."""

    def __init__(self, plugin_info: PluginInfo, node_registry_register: Callable[[str, type], None]):
        self._plugin_info = plugin_info
        self._register_node_internal = node_registry_register

    def register_node(
        self,
        node_type: str,
        node_class: type,
        display_name: str,
        description: str = "",
        category: str = "Plugins",
        icon_relpath: Optional[str] = None,
    ) -> None:
        """Register a node type provided by this plugin.

        - node_type: globally unique type id (str)
        - node_class: subclass of core.nodes.BaseNode
        - display_name: label shown in the toolbox
        - description: tooltip/help for the node
        - category: toolbox category name for grouping
        - icon_relpath: optional path to icon under the plugin folder
        """
        try:
            # Register into the core node registry
            self._register_node_internal(node_type, node_class)
            # Record toolbox entry for later UI population
            lst = self._plugin_info.categories.setdefault(str(category or "Plugins"), [])
            icon_path: Optional[Path] = None
            if icon_relpath:
                p = (self._plugin_info.path / icon_relpath).resolve()
                if p.exists() and p.is_file():
                    icon_path = p
            lst.append(ToolboxNode(node_type=node_type, display_name=display_name, description=description, icon_path=icon_path))
        except Exception:
            # Avoid crashing app due to plugin error
            traceback.print_exc()


def _load_plugin_entry_module(plugin_dir: Path, entry_module: str, logical_name: str) -> Optional[ModuleType]:
    """Load a plugin entry module from file path using importlib.util."""
    try:
        path = plugin_dir / entry_module
        if (not path.exists()) or (not path.is_file()):
            return None
        spec = importlib.util.spec_from_file_location(f"vera_plugins.{logical_name}", str(path))
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        # Temporarily ensure plugin can import from its own folder
        sys_path_added = False
        try:
            if str(plugin_dir) not in sys.path:
                sys.path.insert(0, str(plugin_dir))
                sys_path_added = True
            spec.loader.exec_module(module)  # type: ignore[attr-defined]
        finally:
            if sys_path_added:
                try:
                    sys.path.remove(str(plugin_dir))
                except Exception:
                    pass
        return module
    except Exception:
        traceback.print_exc()
        return None


def load_plugins_into_factory(node_factory_obj: Any) -> None:
    """Discover and load all plugins, registering their nodes into the given node factory.

    This is safe to call multiple times; it reloads the in-memory plugin table.
    """
    global _loaded_plugins
    _loaded_plugins = {}
    for info in discover_installed_plugins(force_rescan=True):
        try:
            # Fresh category map per load
            info.categories = {}
            info.loaded = False
            info.load_error = None
            if not info.entry_module:
                info.load_error = "Missing entry_module in manifest"
                _loaded_plugins[info.plugin_id] = info
                continue
            module = _load_plugin_entry_module(info.path, info.entry_module, info.plugin_id)
            if module is None:
                info.load_error = "Failed to import entry module"
                _loaded_plugins[info.plugin_id] = info
                continue
            register_fn = getattr(module, "register", None)
            if not callable(register_fn):
                info.load_error = "Entry module missing callable register(api)"
                _loaded_plugins[info.plugin_id] = info
                continue
            api = _PluginAPI(info, node_factory_obj.register_node)
            try:
                register_fn(api)
                info.loaded = True
            except Exception as e:
                info.load_error = f"Error in register(): {e}"
                traceback.print_exc()
            _loaded_plugins[info.plugin_id] = info
        except Exception:
            traceback.print_exc()
            try:
                info.load_error = "Unexpected error while loading"
                _loaded_plugins[info.plugin_id] = info
            except Exception:
                pass


def reload_plugins_into_factory(node_factory_obj: Any) -> None:
    """Reload all plugins and re-register their nodes into the given node factory.

    Note: Built-in node registrations remain; plugin registrations are additive.
    """
    load_plugins_into_factory(node_factory_obj)


# -----------------------
# UI helpers
# -----------------------

def get_loaded_toolbox_categories() -> List[Tuple[str, List[ToolboxNode]]]:
    """Return a list of (category_name, nodes[]) for currently loaded plugins."""
    items: List[Tuple[str, List[ToolboxNode]]] = []
    try:
        for pid, info in sorted(_loaded_plugins.items(), key=lambda kv: kv[1].name.lower()):
            for cat, nodes in info.categories.items():
                items.append((cat, list(nodes)))
    except Exception:
        pass
    return items


def get_installed_plugins_for_menu() -> List[Tuple[str, str, bool]]:
    """Return [(display_text, plugin_id, loaded_ok)] for the Plugins menu."""
    out: List[Tuple[str, str, bool]] = []
    try:
        # Prefer loaded set (has errors) but include non-loaded discovered entries too
        if _loaded_plugins:
            for pid, info in sorted(_loaded_plugins.items(), key=lambda kv: kv[1].name.lower()):
                name = f"{info.name} v{info.version}".strip()
                ok = bool(info.loaded and not info.load_error)
                out.append((name, pid, ok))
        else:
            for info in discover_installed_plugins(force_rescan=False):
                name = f"{info.name} v{info.version}".strip()
                out.append((name, info.plugin_id, False))
    except Exception:
        pass
    return out


def open_plugins_folder_in_explorer() -> None:
    try:
        root = ensure_plugins_dir()
        if os.name == "nt":
            os.startfile(str(root))  # type: ignore[attr-defined]
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(root)])
    except Exception:
        pass


