"""
Resource Access Wrapper
Provides easy-to-use functions for accessing theme and web resources with automatic fallback.
"""

import logging
from pathlib import Path
from typing import Optional, Union, List, Tuple
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import QUrl

from .resource_manager import get_resource_manager

logger = logging.getLogger(__name__)


def get_theme_icon_path(icon_name: str) -> str:
    """
    Get path to theme icon with resource fallback.
    
    Args:
        icon_name: Icon filename (e.g., 'vera.ico' or 'play.png')
        
    Returns:
        Path to icon (either resource path or file path)
    """
    if not icon_name:
        return ""
    
    # Ensure .png extension if not provided
    if not icon_name.endswith(('.png', '.ico', '.jpg', '.jpeg', '.gif', '.svg')):
        icon_name = f"{icon_name}.png"
    
    resource_path = f"theme/icons/{icon_name}"
    return get_resource_manager().get_resource_path(resource_path)


def get_theme_icon(icon_name: str) -> QIcon:
    """
    Load theme icon with resource fallback.
    
    Args:
        icon_name: Icon filename or node type name
        
    Returns:
        QIcon (fallback icon if file not found)
    """
    try:
        icon_path = get_theme_icon_path(icon_name)
        if icon_path:
            return QIcon(icon_path)
    except Exception as e:
        logger.debug(f"Failed to load icon {icon_name}: {e}")
    
    # Return empty icon as fallback
    return QIcon()


def get_theme_pixmap(icon_name: str) -> QPixmap:
    """
    Load theme icon as QPixmap with resource fallback.
    
    Args:
        icon_name: Icon filename or node type name
        
    Returns:
        QPixmap (empty pixmap if file not found)
    """
    try:
        icon_path = get_theme_icon_path(icon_name)
        if icon_path:
            return QPixmap(icon_path)
    except Exception as e:
        logger.debug(f"Failed to load pixmap {icon_name}: {e}")
    
    # Return empty pixmap as fallback
    return QPixmap()


def get_web_file_path(filename: str) -> str:
    """
    Get path to web file with resource fallback.
    
    Args:
        filename: Web file name (e.g., 'viewer.html', 'vendor/ngl.js')
        
    Returns:
        Path to file (either resource path or file path)
    """
    if not filename:
        return ""
    
    resource_path = f"web/{filename}"
    return get_resource_manager().get_resource_path(resource_path)


def get_web_file_url(filename: str) -> QUrl:
    """
    Get QUrl for web file with resource fallback.
    
    Args:
        filename: Web file name (e.g., 'viewer.html')
        
    Returns:
        QUrl pointing to the file
    """
    try:
        file_path = get_web_file_path(filename)
        if file_path.startswith(":/"):
            # Resource path - need to handle differently
            # For web files, we may need to extract to temp location
            return _get_web_resource_url(filename)
        else:
            # Regular file path
            return QUrl.fromLocalFile(str(Path(file_path).resolve()))
    except Exception as e:
        logger.error(f"Failed to get URL for web file {filename}: {e}")
        # Fallback to original path
        project_root = Path(__file__).parent.parent
        original_path = project_root / "web" / filename
        return QUrl.fromLocalFile(str(original_path.resolve()))


def _get_web_resource_url(filename: str) -> QUrl:
    """
    Handle web resource files by extracting to temporary location if needed.
    """
    try:
        from backend.temp_manager import get_subdir
        
        # Get resource data
        resource_path = f"web/{filename}"
        data = get_resource_manager().get_resource_data(resource_path)
        
        if data:
            # Extract to temp directory - recreate the web folder structure
            temp_web_dir = get_subdir("web_resources")
            temp_file = temp_web_dir / filename
            
            # Ensure parent directory exists
            temp_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write resource data to temp file
            temp_file.write_bytes(data)
            
            # Also extract vendor/ngl.js if this is a viewer file
            if filename in ["viewer.html", "viewer_embed.html"]:
                try:
                    ngl_data = get_resource_manager().get_resource_data("web/vendor/ngl.js")
                    if ngl_data:
                        ngl_file = temp_web_dir / "vendor" / "ngl.js"
                        ngl_file.parent.mkdir(parents=True, exist_ok=True)
                        ngl_file.write_bytes(ngl_data)
                        logger.debug(f"Extracted NGL.js to {ngl_file}")
                except Exception as e:
                    logger.debug(f"Failed to extract NGL.js: {e}")
            
            return QUrl.fromLocalFile(str(temp_file.resolve()))
    except Exception as e:
        logger.error(f"Failed to extract web resource {filename}: {e}")
    
    # Fallback to resource path (may not work for web viewer)
    return QUrl(f"qrc:///web/{filename}")


def get_web_file_content(filename: str, encoding: str = 'utf-8') -> Optional[str]:
    """
    Get web file content as string with resource fallback.
    
    Args:
        filename: Web file name
        encoding: Text encoding (default: utf-8)
        
    Returns:
        File content as string, or None if not found
    """
    resource_path = f"web/{filename}"
    return get_resource_manager().get_resource_text(resource_path, encoding)


def get_theme_file_path(filename: str) -> str:
    """
    Get path to theme file with resource fallback.
    
    Args:
        filename: Theme file name (e.g., 'style.css')
        
    Returns:
        Path to file (either resource path or file path)
    """
    if not filename:
        return ""
    
    resource_path = f"theme/{filename}"
    return get_resource_manager().get_resource_path(resource_path)


def list_theme_icons() -> list[str]:
    """
    List available theme icons.
    
    Returns:
        List of icon filenames
    """
    try:
        manager = get_resource_manager()
        
        # If compiled resources are active, enumerate directly from Qt's resource system
        if manager.is_using_resources():
            try:
                from PySide6.QtCore import QDir
                resource_dir = QDir(":/theme/icons")
                if resource_dir.exists():
                    entries = resource_dir.entryList(["*.png", "*.ico", "*.jpg", "*.jpeg", "*.gif", "*.svg"], QDir.Files | QDir.NoDotAndDotDot)
                    return sorted(entries)
            except Exception as e:
                logger.debug(f"Qt resource enumeration failed for theme icons: {e}")
        
        # Fallback to scanning original directory when not using compiled resources
        project_root = Path(__file__).parent.parent
        icons_dir = project_root / "theme" / "icons"
        if icons_dir.exists():
            return sorted([
                f.name for f in icons_dir.iterdir() 
                if f.is_file() and f.suffix in {'.png', '.ico', '.jpg', '.jpeg', '.gif', '.svg'}
            ])
    except Exception as e:
        logger.error(f"Failed to list theme icons: {e}")
    
    return []


def list_web_files() -> list[str]:
    """
    List available web files.
    
    Returns:
        List of web file paths (relative to web/ directory)
    """
    try:
        manager = get_resource_manager()
        
        # If compiled resources are active, enumerate via Qt's resource system
        if manager.is_using_resources():
            try:
                from PySide6.QtCore import QDir, QDirIterator
                web_root = QDir(":/web")
                if web_root.exists():
                    results: list[str] = []
                    it = QDirIterator(":/web", QDir.Files | QDir.NoDotAndDotDot, QDirIterator.Subdirectories)
                    while it.hasNext():
                        path = it.next()  # e.g., ':/web/vendor/ngl.js'
                        # Normalize to path relative to 'web/' root
                        if path.startswith(":/web/"):
                            results.append(path[len(":/web/"):])
                        elif path == ":/web":
                            continue
                    return sorted(results)
            except Exception as e:
                logger.debug(f"Qt resource enumeration failed for web files: {e}")
        
        # Fallback to scanning original directory when not using compiled resources
        project_root = Path(__file__).parent.parent
        web_dir = project_root / "web"
        if web_dir.exists():
            web_files = []
            for file_path in web_dir.rglob("*"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(web_dir)
                    web_files.append(str(relative_path).replace("\\", "/"))
            return sorted(web_files)
    except Exception as e:
        logger.error(f"Failed to list web files: {e}")
    
    return []


def is_using_compiled_resources() -> bool:
    """
    Check if application is currently using compiled resources.
    
    Returns:
        True if using compiled resources, False if using original files
    """
    return get_resource_manager().is_using_resources()


def rebuild_resources() -> bool:
    """
    Force rebuild of resources.
    
    Returns:
        True if rebuild successful
    """
    return get_resource_manager().force_rebuild()


# Convenience functions for backward compatibility
def load_node_icon(node_type: str, display_name: str = "") -> QIcon:
    """
    Load node icon with fallback logic - backward compatibility function.
    
    Args:
        node_type: Node type name
        display_name: Display name for fallback
        
    Returns:
        QIcon with colored background and theme icon if available
    """
    from PySide6.QtGui import QPainter, QBrush, QPen, QColor
    from PySide6.QtCore import QSize, Qt
    
    # Try exact PNG by node type, else by display name slug
    candidates = [f"{node_type}.png"]
    if display_name:
        candidates.append(f"{display_name.lower().replace(' ', '_')}.png")
    
    for icon_name in candidates:
        try:
            icon_path = get_theme_icon_path(icon_name)
            if icon_path and (icon_path.startswith(":/") or Path(icon_path).exists()):
                # Compose the provided transparent icon over a colored circular background
                size = 48
                pix = QPixmap(size, size)
                pix.fill(Qt.transparent)
                painter = QPainter(pix)
                painter.setRenderHint(QPainter.Antialiasing)
                
                try:
                    hue = (abs(hash(node_type)) % 360) / 360.0
                    base_color = QColor.fromHsvF(hue, 0.6, 0.9)
                    dark_color = QColor.fromHsvF(hue, 0.7, 0.6)
                    painter.setBrush(QBrush(base_color))
                    painter.setPen(QPen(dark_color, 2))
                    painter.drawEllipse(2, 2, size - 4, size - 4)
                    
                    # Subtle inner highlight
                    highlight_color = QColor.fromHsvF(hue, 0.3, 1.0, 0.6)
                    painter.setBrush(QBrush(highlight_color))
                    painter.setPen(Qt.NoPen)
                    painter.drawEllipse(6, 6, 12, 12)

                    # Draw the source icon centered, scaled to fit within the circle
                    src_pix = QPixmap(icon_path)
                    if not src_pix.isNull():
                        target = QSize(int(size * 0.58), int(size * 0.58))  # ~28px inside 48px circle
                        src_scaled = src_pix.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        x = (size - src_scaled.width()) // 2
                        y = (size - src_scaled.height()) // 2
                        painter.drawPixmap(x, y, src_scaled)
                finally:
                    painter.end()
                return QIcon(pix)
        except Exception as e:
            logger.debug(f"Failed to load composed icon {icon_name}: {e}")
    
    # Fallback: generate a colored circle with the first letter
    size = 48
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    
    try:
        hue = (abs(hash(node_type)) % 360) / 360.0
        base_color = QColor.fromHsvF(hue, 0.6, 0.9)
        dark_color = QColor.fromHsvF(hue, 0.7, 0.6)
        
        painter.setBrush(QBrush(base_color))
        painter.setPen(QPen(dark_color, 2))
        painter.drawEllipse(2, 2, size - 4, size - 4)
        
        # Add text
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.setFont(painter.font())
        text = display_name[0].upper() if display_name else node_type[0].upper()
        painter.drawText(pix.rect(), Qt.AlignCenter, text)
    finally:
        painter.end()
    
    return QIcon(pix)


# =============================
# Theme (QSS) helper utilities
# =============================

def _pretty_theme_name(theme_id: str) -> str:
    """
    Convert a theme id (file stem) into a human-friendly name.
    Examples:
      'win11_dark' -> 'Windows 11 Dark'
      'dracula' -> 'Dracula'
    """
    t = (theme_id or "").strip().lower()
    if not t:
        return ""
    # Special cases for common names
    replacements = {
        "win11": "Windows 11",
        "windows11": "Windows 11",
        "windows_11": "Windows 11",
        "amoled": "AMOLED",
    }
    parts: list[str] = []
    for chunk in t.replace("-", "_").split("_"):
        pretty = replacements.get(chunk, None)
        if pretty is None:
            pretty = chunk.capitalize()
        parts.append(pretty)
    # Merge consecutive 'Windows 11' tokens
    name = " ".join(parts)
    name = name.replace("Windows 11 11", "Windows 11")
    return name


def list_themes() -> List[Tuple[str, str]]:
    """
    Enumerate available QSS themes under theme/theme.

    Returns:
        List of (theme_id, display_name) sorted by display_name.
        theme_id corresponds to the file stem (without .qss).
    """
    results: list[tuple[str, str]] = []
    try:
        manager = get_resource_manager()
        # Prefer Qt resource enumeration when compiled resources are active
        if manager.is_using_resources():
            from PySide6.QtCore import QDir
            qdir = QDir(":/theme/theme")
            if qdir.exists():
                for fname in qdir.entryList(["*.qss"], QDir.Files | QDir.NoDotAndDotDot):
                    stem = fname[:-4] if fname.lower().endswith(".qss") else fname
                    results.append((stem, _pretty_theme_name(stem)))
        else:
            # Fallback to filesystem scan
            root = Path(__file__).parent.parent / "theme" / "theme"
            if root.exists():
                for p in sorted(root.glob("*.qss")):
                    stem = p.stem
                    results.append((stem, _pretty_theme_name(stem)))
    except Exception as e:
        logger.error(f"Failed to list QSS themes: {e}")
    # Stable sort by display name
    results.sort(key=lambda x: x[1].lower())
    return results


def load_theme_qss(theme_id: str) -> str:
    """
    Load QSS content for a theme by its id (file stem).

    Args:
        theme_id: e.g., 'win11_dark'

    Returns:
        QSS text (empty string if not found)
    """
    if not theme_id:
        return ""
    filename = f"theme/{theme_id}.qss" if theme_id.endswith(".qss") is False else f"theme/{theme_id}"
    # Our QSS files are under theme/theme
    if not filename.startswith("theme/theme"):
        filename = f"theme/theme/{theme_id}.qss"
    try:
        text = get_resource_manager().get_resource_text(filename, encoding="utf-8")
        if text is not None:
            return text
        # Fallback to disk read
        disk_path = Path(__file__).parent.parent / filename
        if disk_path.exists():
            return disk_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to load theme QSS '{theme_id}': {e}")
    return ""


def detect_theme_is_dark(theme_id: str) -> bool:
    """Heuristic to decide if theme is dark based on id."""
    t = (theme_id or "").lower()
    return any(k in t for k in ("dark", "dracula", "nord", "amoled"))
