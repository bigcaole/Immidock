"""Archive and bundle management for ImmiDock."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import docker
from docker.errors import DockerException

from immidock.utils.checksum import generate_checksum
from immidock.utils.i18n import translate
from immidock.utils.logger import setup_logger

try:  # pragma: no cover - optional dependency
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    tqdm = None


def _progress(items: List[str], desc: str, unit: str):
    """Return an iterable wrapped with tqdm if available."""
    if tqdm:
        return tqdm(items, desc=desc, unit=unit)
    return items


def _archive_name_from_path(path: str) -> str:
    """Generate a filesystem-friendly archive name from a path."""
    cleaned = path.strip().strip("/")
    if not cleaned:
        return "root"
    return cleaned.replace("/", "_").replace(" ", "_")


def _unique_name(base: str, used: Set[str]) -> str:
    """Ensure archive names are unique within the bundle."""
    if base not in used:
        used.add(base)
        return base
    counter = 2
    while True:
        candidate = f"{base}_{counter}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        counter += 1


def _run_tar_zstd(source_path: Path, archive_path: Path, logger) -> None:
    """Archive a path using tar piped to zstd."""
    logger.info("archive_volume", source_path)
    tar_proc = subprocess.Popen(
        ["tar", "-pcf", "-", str(source_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        zstd_proc = subprocess.run(
            ["zstd", "-T0", "-o", str(archive_path)],
            stdin=tar_proc.stdout,
            check=False,
        )
    finally:
        if tar_proc.stdout:
            tar_proc.stdout.close()

    tar_stderr = tar_proc.stderr.read().decode("utf-8", errors="ignore") if tar_proc.stderr else ""
    tar_proc.stderr.close() if tar_proc.stderr else None
    tar_code = tar_proc.wait()

    if tar_code != 0:
        raise RuntimeError(f"tar failed for {source_path}: {tar_stderr.strip()}")
    if zstd_proc.returncode != 0:
        raise RuntimeError(f"zstd failed for {source_path} (code {zstd_proc.returncode})")


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


def _collect_mounts(manifest: Dict[str, Any]) -> List[Dict[str, str]]:
    """Collect mount entries from the manifest."""
    mounts: List[Dict[str, str]] = []
    for container in manifest.get("containers", []):
        for mount in container.get("mounts", []):
            mount_type = mount.get("type")
            if mount_type in {"bind", "volume"}:
                mounts.append(mount)
    return mounts


def build_bundle(manifest: Dict[str, Any], output_path: str, include_volumes: bool = True) -> None:
    """Build a ImmiDock bundle with manifest, images, and volumes."""
    logger = setup_logger()
    logger.info("bundle_start")
    build_dir = Path(".immidock_build")
    images_dir = build_dir / "images"
    volumes_dir = build_dir / "volumes"

    if build_dir.exists():
        shutil.rmtree(build_dir)

    images_dir.mkdir(parents=True, exist_ok=True)
    volumes_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = build_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)

    try:
        client = docker.from_env()
    except DockerException as exc:
        logger.error("Docker connection failed: %s", exc)
        raise

    if include_volumes:
        mounts = _collect_mounts(manifest)
        bind_paths: Set[str] = set()
        volume_sources: Set[str] = set()
        for mount in mounts:
            mount_type = mount.get("type")
            source = mount.get("source", "")
            if mount_type == "bind":
                if source:
                    bind_paths.add(source)
            elif mount_type == "volume":
                if source:
                    volume_sources.add(source)

        used_names: Set[str] = set()

        for bind_path in _progress(
            sorted(bind_paths), desc=translate("archiving_volumes"), unit="vol"
        ):
            path = Path(bind_path)
            if not path.exists():
                logger.warning("Volume path not found: %s", path)
                continue
            archive_name = _unique_name(_archive_name_from_path(bind_path), used_names)
            archive_path = volumes_dir / f"{archive_name}.tar.zst"
            _run_tar_zstd(path, archive_path, logger)

        for source in _progress(
            sorted(volume_sources), desc=translate("archiving_volumes"), unit="vol"
        ):
            mountpoint = _resolve_volume_mountpoint(client, source, logger)
            if not mountpoint:
                continue
            if not mountpoint.exists():
                logger.warning("Volume path not found: %s", mountpoint)
                continue
            base_name = _archive_name_from_path(source)
            archive_name = _unique_name(base_name, used_names)
            archive_path = volumes_dir / f"{archive_name}.tar.zst"
            _run_tar_zstd(mountpoint, archive_path, logger)

    image_list = list(manifest.get("images", []))
    for image_ref in _progress(image_list, desc=translate("exporting_images"), unit="img"):
        logger.info("export_image", image_ref)
        image_name = image_ref.split(":")[0].replace("/", "_").replace(" ", "_")
        archive_path = images_dir / f"{image_name}.tar"
        result = subprocess.run(
            ["docker", "save", "-o", str(archive_path), image_ref],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error("Image export failed for %s: %s", image_ref, result.stderr.strip())
            raise RuntimeError(f"Docker image export failed for {image_ref}")

    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    logger.info("creating_bundle", output)
    subprocess.run(
        ["tar", "-cf", str(output), "manifest.json", "images", "volumes"],
        cwd=build_dir,
        check=True,
    )
    checksum = generate_checksum(str(output))
    logger.info("bundle_checksum", checksum)
    logger.info("bundle_created")
