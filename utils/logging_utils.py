"""
Logging utilities for VERA application.
Provides centralized logging configuration and utilities.
"""

import logging
import sys
import os
from pathlib import Path
from typing import Optional

def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None):
    """Setup logging configuration for the application."""
    
    logger = logging.getLogger("vera")
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Optional: still attach console handler (won't work in GUI mode)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Always log to a file
    if not log_file:
        default_log_dir = Path(os.path.expanduser("~")) / "tds"
        default_log_dir.mkdir(parents=True, exist_ok=True)
        log_file = default_log_dir / "app"
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(getattr(logging, log_level.upper()))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.debug(f"Logging initialized. Writing to: {log_file}")

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given name."""
    return logging.getLogger(f"vera.{name}")


# Setup default logging on import
setup_logging()
