"""Incremental migration support for ImmiDock."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import docker
from docker.errors import DockerException

from dockshifter.utils.logger import setup_logger


def _collect_mounts(manifest: Dict[str, Any]) -> List[Dict[str, str]]:
    """Collect mount entries from the manifest."""
    mounts: List[Dict[str, str]] = []
    for container in manifest.get("containers", []):
        for mount in container.get("mounts", []):
            mount_type = mount.get("type")
            if mount_type in {"bind", "volume"}:
                mounts.append(mount)
    return mounts


def _resolve_volume_mountpoint(
    client: docker.DockerClient,
    source: str,
    logger,
) -> Optional[Path]:
    """Resolve a named volume to its mountpoint if needed."""
    if source.startswith("/"):
        return Path(source)
    if not source:
        return None
    try:
        volume = client.volumes.get(source)
    except DockerException as exc:
        logger.warning("Failed to inspect volume %s: %s", source, exc)
        return None
    mountpoint = volume.attrs.get("Mountpoint", "")
    if not mountpoint:
        logger.warning("Volume %s has no mountpoint", source)
        return None
    return Path(mountpoint)


def _rsync_path(source: Path, target: str) -> None:
    """Run rsync for a single path to the target host."""
    subprocess.run(
        ["rsync", "-az", "--delete", str(source), f"{target}:{source}"],
        check=True,
    )


def incremental_sync(target: str, manifest: Dict[str, Any]) -> None:
    """Synchronize volumes to the target host using rsync."""
    logger = setup_logger()
    if not shutil.which("rsync"):
        raise RuntimeError("rsync not found")

    try:
        client = docker.from_env()
    except DockerException as exc:
        logger.error("Docker connection failed: %s", exc)
        raise

    mounts = _collect_mounts(manifest)
    bind_paths: Set[str] = set()
    volume_sources: Set[str] = set()
    for mount in mounts:
        mount_type = mount.get("type")
        source = mount.get("source", "")
        if mount_type == "bind":
            if source:
                bind_paths.add(os.path.realpath(source))
        elif mount_type == "volume":
            if source:
                volume_sources.add(source)

    for bind_path in sorted(bind_paths):
        path = Path(bind_path)
        if not path.exists():
            logger.warning("Volume path not found: %s", path)
            continue
        logger.info("syncing_volume", path)
        _rsync_path(path, target)

    for source in sorted(volume_sources):
        mountpoint = _resolve_volume_mountpoint(client, source, logger)
        if not mountpoint:
            continue
        if not mountpoint.exists():
            logger.warning("Volume path not found: %s", mountpoint)
            continue
        logger.info("syncing_volume", mountpoint)
        _rsync_path(mountpoint, target)
