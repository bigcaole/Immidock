"""Remote migration support for ImmiDock."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

import docker
from docker.errors import DockerException
from jsonschema import validate

from immidock.core.auditor import generate_manifest
from immidock.core.bundler import build_bundle
from immidock.core.incremental import incremental_sync
from immidock.utils.i18n import translate
from immidock.utils.logger import setup_logger

try:  # pragma: no cover - optional dependency
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    tqdm = None


def _load_schema(schema_path: Path) -> Dict[str, Any]:
    """Load the manifest JSON schema from disk."""
    with schema_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _validate_manifest(manifest: Dict[str, Any], schema_path: Path) -> None:
    """Validate the manifest against the JSON schema."""
    schema = _load_schema(schema_path)
    validate(instance=manifest, schema=schema)


def _format_bytes(value: int) -> str:
    """Format a byte count into a human-readable string."""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{int(size)} B"


def _dir_size(path: Path) -> int:
    """Calculate total size of a directory tree."""
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            file_path = Path(root) / name
            try:
                total += file_path.stat().st_size
            except OSError:
                continue
    return total


def _estimate_volume_size(manifest: Dict[str, Any]) -> int:
    """Estimate volume size from manifest mount paths."""
    paths: set[str] = set()
    for container in manifest.get("containers", []):
        for mount in container.get("mounts", []):
            source = mount.get("source", "")
            if source:
                paths.add(source)

    total = 0
    for source in paths:
        path = Path(source)
        if not path.exists():
            continue
        if path.is_file():
            total += path.stat().st_size
        else:
            total += _dir_size(path)
    return total


def _estimate_image_size(manifest: Dict[str, Any], logger) -> int:
    """Estimate image size using Docker SDK."""
    try:
        client = docker.from_env()
    except DockerException as exc:
        logger.warning("Docker connection failed: %s", exc)
        return 0

    total = 0
    for image_ref in manifest.get("images", []):
        try:
            image = client.images.get(image_ref)
            total += int(image.attrs.get("Size", 0) or 0)
        except DockerException as exc:
            logger.warning("Unable to inspect image %s: %s", image_ref, exc)
    return total


def _print_plan(manifest: Dict[str, Any], volume_size: int, image_size: int) -> None:
    """Print a migration plan without executing changes."""
    containers = manifest.get("containers", [])
    networks = manifest.get("networks", [])
    volumes = manifest.get("volumes", [])
    images = manifest.get("images", [])

    print(translate("plan_title"))
    print()
    print(translate("plan_containers") % len(containers))
    print(translate("plan_images") % len(images))
    print(translate("plan_volumes") % len(volumes))
    print(translate("plan_networks") % len(networks))
    print()
    print(translate("plan_volume_size") % _format_bytes(volume_size))
    print(translate("plan_image_size") % _format_bytes(image_size))
    print()
    print(translate("plan_containers_header"))
    for container in containers:
        name = container.get("name", "")
        if name:
            print(translate("plan_item") % name)
    print()
    print(translate("plan_networks_header"))
    for network in networks:
        name = network.get("name", "")
        if name:
            print(translate("plan_item") % name)


def migrate_to_host(target: str, incremental: bool, plan: bool = False) -> None:
    """Run a pack operation and stream the bundle to a remote host via SSH."""
    logger = setup_logger()
    if not shutil.which("ssh"):
        raise RuntimeError("ssh client not found")

    manifest = generate_manifest()
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "manifest_schema.json"
    _validate_manifest(manifest, schema_path)

    if plan:
        volume_size = _estimate_volume_size(manifest)
        image_size = _estimate_image_size(manifest, logger)
        _print_plan(manifest, volume_size, image_size)
        return

    if incremental:
        incremental_sync(target, manifest)

    with tempfile.TemporaryDirectory() as tmpdir:
        bundle_path = Path(tmpdir) / "immidock_bundle.dsh"
        build_bundle(manifest, str(bundle_path), include_volumes=not incremental)

        bundle_size = bundle_path.stat().st_size
        logger.info("streaming_bundle", target)
        proc = subprocess.Popen(
            ["ssh", target, "immidock restore -"],
            stdin=subprocess.PIPE,
        )
        try:
            with bundle_path.open("rb") as handle:
                if proc.stdin is None:
                    raise RuntimeError("Failed to open SSH stdin")
                if tqdm:
                    with tqdm(
                        total=bundle_size,
                        desc=translate("streaming_bundle") % target,
                        unit="B",
                        unit_scale=True,
                    ) as progress:
                        while True:
                            chunk = handle.read(1024 * 1024)
                            if not chunk:
                                break
                            proc.stdin.write(chunk)
                            progress.update(len(chunk))
                else:
                    shutil.copyfileobj(handle, proc.stdin)
        except BrokenPipeError as exc:
            raise RuntimeError("SSH connection closed unexpectedly") from exc
        finally:
            if proc.stdin:
                proc.stdin.close()

        return_code = proc.wait()
        if return_code != 0:
            raise RuntimeError(f"SSH migration failed with code {return_code}")
