"""
Session-scoped temporary workspace management for VERA.

Provides a single temp directory per application session that nodes can
use to write intermediate files. The directory is removed when the app
closes (via explicit cleanup).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Optional

_SESSION_TEMP_DIR: Optional[Path] = None


def init_session_temp_dir(prefix: str = "vera_") -> Path:
    """Create the session temp directory if not already created.

    Returns the Path to the directory.
    """
    global _SESSION_TEMP_DIR
    if _SESSION_TEMP_DIR is None:
        path = Path(tempfile.mkdtemp(prefix=prefix))
        _SESSION_TEMP_DIR = path
    return _SESSION_TEMP_DIR


def get_session_temp_dir() -> Path:
    """Return the session temp directory Path, creating it if needed."""
    return init_session_temp_dir()


def get_subdir(name: str) -> Path:
    """Return a named subdirectory inside the session temp dir (created)."""
    base = get_session_temp_dir()
    sub = base / name
    sub.mkdir(parents=True, exist_ok=True)
    return sub


def cleanup_session_temp_dir() -> None:
    """Remove the session temp directory and all of its contents."""
    global _SESSION_TEMP_DIR
    try:
        if _SESSION_TEMP_DIR and _SESSION_TEMP_DIR.exists():
            shutil.rmtree(_SESSION_TEMP_DIR, ignore_errors=True)
    finally:
        _SESSION_TEMP_DIR = None


