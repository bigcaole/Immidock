"""Checksum utilities for ImmiDock bundles."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional


def _checksum_path(file_path: Path) -> Path:
    """Return the checksum file path for a bundle."""
    return Path(f"{file_path}.sha256")


def generate_checksum(file_path: str) -> str:
    """Generate a SHA256 checksum file for the given bundle."""
    bundle = Path(file_path)
    digest = hashlib.sha256()
    with bundle.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    checksum = digest.hexdigest()
    checksum_path = _checksum_path(bundle)
    checksum_path.write_text(f"{checksum} {bundle.name}\n", encoding="utf-8")
    return checksum


def verify_checksum(file_path: str) -> bool:
    """Verify the checksum for the given bundle if present."""
    bundle = Path(file_path)
    checksum_path = _checksum_path(bundle)
    if not checksum_path.exists():
        return True

    content = checksum_path.read_text(encoding="utf-8").strip()
    if not content:
        return False

    expected = content.split()[0]
    digest = hashlib.sha256()
    with bundle.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest() == expected
