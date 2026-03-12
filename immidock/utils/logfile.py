"""Persistent log file utilities for ImmiDock."""

from __future__ import annotations

import logging
from pathlib import Path


def get_log_handler() -> logging.Handler:
    """Create a file handler for ImmiDock logs."""
    log_dir = Path.home() / ".immidock"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "immidock.log"
    handler = logging.FileHandler(log_path)
    formatter = logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M")
    handler.setFormatter(formatter)
    return handler
