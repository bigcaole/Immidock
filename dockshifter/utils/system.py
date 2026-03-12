"""System utility helpers for ImmiDock."""

from __future__ import annotations

import shutil
from typing import Optional


def check_binary_exists(name: str) -> bool:
    """Return True if the binary is available on PATH."""
    return shutil.which(name) is not None
