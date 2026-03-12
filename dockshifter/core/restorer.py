"""Restore operations for ImmiDock."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple

import docker
from docker.errors import DockerException
from docker.types import IPAMConfig, IPAMPool, Mount
from jsonschema import validate

from dockshifter.adapters.one_panel import sync_apps
from dockshifter.core.network_mgr import resolve_network_conflicts
from dockshifter.utils.checksum import verify_checksum
from dockshifter.utils.i18n import translate
from dockshifter.utils.logger import setup_logger

try:  # pragma: no cover - optional dependency
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    tqdm = None


def _print_plan(message: str) -> None:
    """Print a dry-run plan entry."""
    print(f"[PLAN] {message}")


def _progress(items: List[Path], desc: str, unit: str):
    """Return an iterable wrapped with tqdm if available."""
    if tqdm:
        return tqdm(items, desc=desc, unit=unit)
    return items


def _format_duration(seconds: float) -> str:
    """Format a duration in seconds into a friendly string."""
    minutes, secs = divmod(int(seconds), 60)
    if minutes:
        return f"{minutes}m{secs}s"
    return f"{secs}s"


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
    """Calculate the size of a directory tree."""
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            file_path = Path(root) / name
            try:
                total += file_path.stat().st_size
            except OSError:
                continue
    return total


def _print_plan_summary(manifest: Dict[str, Any], volume_size: int, image_size: int) -> None:
    """Print a migration plan summary without executing changes."""
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


def _stage_bundle(bundle_path: str, logger) -> Tuple[Path, bool]:
    """Stage the bundle locally, optionally reading from stdin."""
    if bundle_path != "-":
        return Path(bundle_path), False

    logger.info("reading_bundle_stdin")
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".dsh")
    temp_path = Path(temp_file.name)
    try:
        source = sys.stdin.buffer
        if tqdm:
            with tqdm(desc=translate("receiving_bundle"), unit="B", unit_scale=True) as progress:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    temp_file.write(chunk)
                    progress.update(len(chunk))
        else:
            shutil.copyfileobj(source, temp_file)
    finally:
        temp_file.close()
    return temp_path, True


def _load_schema(schema_path: Path) -> Dict[str, Any]:
    """Load the manifest JSON schema from disk."""
    with schema_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _validate_manifest(manifest: Dict[str, Any], schema_path: Path) -> None:
    """Validate the manifest against the JSON schema."""
    schema = _load_schema(schema_path)
    validate(instance=manifest, schema=schema)


def _run_docker_cli(args: List[str]) -> str:
    """Run a docker CLI command and return stdout."""
    result = subprocess.run(
        ["docker"] + args,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error = result.stderr.strip() or "unknown error"
        raise RuntimeError(f"Docker command failed: docker {' '.join(args)}\nError: {error}")
    return result.stdout


def _collect_existing_containers() -> Set[str]:
    """Collect existing container names using docker CLI."""
    output = _run_docker_cli(["ps", "-a", "--format", "{{.Names}}"])
    return {line.strip() for line in output.splitlines() if line.strip()}


def _collect_existing_networks() -> Set[str]:
    """Collect existing network names using docker CLI."""
    output = _run_docker_cli(["network", "ls", "--format", "{{.Name}}"])
    return {line.strip() for line in output.splitlines() if line.strip()}


def _collect_existing_ports() -> Set[str]:
    """Collect host ports in use by running containers using docker CLI."""
    output = _run_docker_cli(["ps", "--format", "{{.ID}}"])
    ids = [line.strip() for line in output.splitlines() if line.strip()]
    if not ids:
        return set()

    inspect_output = _run_docker_cli(["inspect"] + ids)
    try:
        inspect_data = json.loads(inspect_output)
    except json.JSONDecodeError:
        return set()

    ports: Set[str] = set()
    for entry in inspect_data:
        port_map = (entry.get("NetworkSettings", {}) or {}).get("Ports", {}) or {}
        for bindings in port_map.values():
            if not bindings:
                continue
            for host in bindings:
                host_port = host.get("HostPort")
                if host_port:
                    ports.add(str(host_port))
    return ports


def _collect_manifest_ports(manifest: Dict[str, Any]) -> Set[str]:
    """Collect host ports from the manifest."""
    ports: Set[str] = set()
    for container in manifest.get("containers", []):
        inspect = container.get("inspect", {}) or {}
        port_map = (inspect.get("NetworkSettings", {}) or {}).get("Ports", {}) or {}
        for bindings in port_map.values():
            if not bindings:
                continue
            for host in bindings:
                host_port = host.get("HostPort")
                if host_port:
                    ports.add(str(host_port))
    return ports


def _check_restore_conflicts(manifest: Dict[str, Any], logger) -> None:
    """Check for conflicts before restoring."""
    conflicts: List[str] = []
    existing_containers = _collect_existing_containers()
    existing_ports = _collect_existing_ports()
    existing_networks = _collect_existing_networks()

    for container in manifest.get("containers", []):
        name = container.get("name")
        if name and name in existing_containers:
            conflicts.append(translate("conflict_container") % name)

    manifest_ports = _collect_manifest_ports(manifest)
    for port in sorted(manifest_ports):
        if port in existing_ports:
            conflicts.append(translate("conflict_port") % port)

    for network in manifest.get("networks", []):
        name = network.get("name")
        if name and name not in {"bridge", "host", "none"} and name in existing_networks:
            conflicts.append(translate("conflict_network") % name)

    if conflicts:
        logger.error("conflict_detected")
        for item in conflicts:
            logger.error(item)
        raise RuntimeError("Restore conflicts detected")


def _extract_bundle(bundle_path: Path, restore_dir: Path, logger, dry_run: bool) -> None:
    """Extract the bundle into the restore directory."""
    if restore_dir.exists():
        shutil.rmtree(restore_dir)
    restore_dir.mkdir(parents=True, exist_ok=True)

    logger.info("extract_bundle")
    if dry_run:
        _print_plan(f"Extract bundle {bundle_path}")
    subprocess.run(["tar", "-xf", str(bundle_path), "-C", str(restore_dir)], check=True)


def _warn_existing_paths(manifest: Dict[str, Any], logger) -> None:
    """Warn if target paths already exist on the host."""
    seen: set[str] = set()
    for container in manifest.get("containers", []):
        for mount in container.get("mounts", []):
            source = mount.get("source", "")
            if not source or source in seen:
                continue
            seen.add(source)
            path = Path(source)
            if path.exists():
                logger.warning("Volume path already exists: %s", path)


def _collect_1panel_app_dirs(manifest: Dict[str, Any]) -> Set[Path]:
    """Collect 1Panel application directories from the manifest."""
    app_dirs: Set[Path] = set()
    root = Path("/opt/1panel/apps")
    for container in manifest.get("containers", []):
        if container.get("type") != "1panel_app":
            continue
        container_name = container.get("name")
        mounts = container.get("mounts", [])
        for mount in mounts:
            source = mount.get("source", "")
            if not source:
                continue
            source_path = Path(source)
            if not source_path.is_absolute():
                continue
            parts = source_path.parts
            root_parts = root.parts
            if parts[: len(root_parts)] != root_parts:
                continue
            if len(parts) > len(root_parts):
                app_name = parts[len(root_parts)]
                app_dirs.add(root / app_name)
        if container_name:
            app_dirs.add(root / container_name)
    return app_dirs


def _ensure_1panel_dirs(manifest: Dict[str, Any], logger, dry_run: bool) -> None:
    """Ensure 1Panel application directories exist."""
    if not Path("/opt/1panel").exists():
        logger.warning("1Panel not detected, skipping app directory verification")
        return
    for app_dir in sorted(_collect_1panel_app_dirs(manifest)):
        if dry_run:
            _print_plan(f"Ensure 1Panel app directory {app_dir}")
            continue
        app_dir.mkdir(parents=True, exist_ok=True)


def _restore_volume(archive_path: Path, logger, dry_run: bool) -> bool:
    """Restore a volume archive using zstd and tar."""
    logger.info("restore_volume", archive_path)
    if dry_run:
        _print_plan(f"Restore volume {archive_path}")
        return True

    zstd_proc = subprocess.Popen(
        ["zstd", "-d", "-c", str(archive_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        tar_proc = subprocess.run(
            ["tar", "-xpf", "-", "-C", "/"],
            stdin=zstd_proc.stdout,
            check=False,
        )
    finally:
        if zstd_proc.stdout:
            zstd_proc.stdout.close()

    zstd_stderr = zstd_proc.stderr.read().decode("utf-8", errors="ignore") if zstd_proc.stderr else ""
    zstd_proc.stderr.close() if zstd_proc.stderr else None
    zstd_code = zstd_proc.wait()

    if zstd_code != 0:
        raise RuntimeError(f"zstd failed for {archive_path}: {zstd_stderr.strip()}")
    if tar_proc.returncode != 0:
        raise RuntimeError(f"tar failed for {archive_path} (code {tar_proc.returncode})")
    return True


def _load_image(image_path: Path, logger, dry_run: bool) -> bool:
    """Load a Docker image archive."""
    logger.info("load_image", image_path)
    if dry_run:
        _print_plan(f"Load image {image_path}")
        return True
    result = subprocess.run(
        ["docker", "load", "-i", str(image_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Docker load failed for {image_path}: {result.stderr.strip()}")
    return True


def _parse_created(value: str) -> datetime:
    """Parse Docker created timestamp into a datetime."""
    if not value:
        return datetime.fromtimestamp(0)
    cleaned = value.rstrip("Z")
    if "." in cleaned:
        base, frac = cleaned.split(".", 1)
        frac = frac[:6].ljust(6, "0")
        cleaned = f"{base}.{frac}"
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return datetime.fromtimestamp(0)


def _build_ports(ports: Dict[str, Any]) -> Dict[str, Any]:
    """Convert docker inspect ports into docker SDK ports mapping."""
    mapping: Dict[str, Any] = {}
    for container_port, bindings in ports.items():
        if not bindings:
            continue
        if len(bindings) == 1:
            host = bindings[0]
            host_ip = host.get("HostIp")
            host_port = host.get("HostPort")
            if host_ip and host_port:
                mapping[container_port] = (host_ip, int(host_port))
            elif host_port:
                mapping[container_port] = int(host_port)
        else:
            entries = []
            for host in bindings:
                host_ip = host.get("HostIp")
                host_port = host.get("HostPort")
                if host_ip and host_port:
                    entries.append((host_ip, int(host_port)))
                elif host_port:
                    entries.append(int(host_port))
            if entries:
                mapping[container_port] = entries
    return mapping


def _build_mounts(mounts: Iterable[Dict[str, Any]]) -> List[Mount]:
    """Convert docker inspect mounts into docker SDK Mount objects."""
    result: List[Mount] = []
    for mount in mounts:
        mount_type = mount.get("Type")
        if mount_type == "tmpfs":
            continue
        if mount_type not in {"bind", "volume"}:
            continue
        source = mount.get("Source", "")
        target = mount.get("Destination", "")
        if mount_type == "volume":
            name = mount.get("Name") or source
            if not name:
                continue
            source = name
        if not source or not target:
            continue
        read_only = not mount.get("RW", True)
        result.append(Mount(target=target, source=source, type=mount_type, read_only=read_only))
    return result


def _create_networks(
    client: docker.DockerClient, manifest: Dict[str, Any], logger, dry_run: bool
) -> int:
    """Create Docker networks from the manifest."""
    existing_names = {net.name for net in client.networks.list()}
    created_count = 0
    for network in manifest.get("networks", []):
        name = network.get("name")
        if not name:
            continue
        if name in {"bridge", "host", "none"}:
            continue
        if name in existing_names:
            logger.warning("Network already exists: %s", name)
            continue
        subnet = network.get("subnet")
        gateway = network.get("gateway")
        driver = network.get("driver") or "bridge"
        logger.info("create_network", name)
        if dry_run:
            _print_plan(f"Create network {name}")
            created_count += 1
            continue
        ipam = None
        if subnet:
            pool = IPAMPool(subnet=subnet, gateway=gateway)
            ipam = IPAMConfig(pool_configs=[pool])
        client.networks.create(name=name, driver=driver, ipam=ipam)
        created_count += 1
    return created_count


def _create_containers(
    client: docker.DockerClient,
    manifest: Dict[str, Any],
    logger,
    dry_run: bool,
) -> Dict[str, docker.models.containers.Container]:
    """Create containers without starting them."""
    created: Dict[str, docker.models.containers.Container] = {}
    for container in manifest.get("containers", []):
        name = container.get("name")
        inspect = container.get("inspect", {}) or {}
        config = inspect.get("Config", {}) or {}
        network_names = container.get("networks", [])
        image = container.get("image") or config.get("Image")
        if not image or not name:
            logger.warning("Skipping container with missing image or name")
            continue
        logger.info("create_container", name)
        if dry_run:
            _print_plan(f"Create container {name}")
            continue

        ports = _build_ports((inspect.get("NetworkSettings", {}) or {}).get("Ports", {}) or {})
        mounts = _build_mounts(inspect.get("Mounts", []) or [])
        kwargs = {
            "image": image,
            "name": name,
            "environment": config.get("Env") or [],
            "ports": ports or None,
            "mounts": mounts or None,
            "command": config.get("Cmd"),
            "entrypoint": config.get("Entrypoint"),
            "working_dir": config.get("WorkingDir"),
            "labels": config.get("Labels"),
            "detach": True,
        }
        if network_names:
            kwargs["network"] = network_names[0]
        container_obj = client.containers.create(**kwargs)
        created[name] = container_obj

        for network in network_names[1:]:
            try:
                client.networks.get(network).connect(container_obj)
            except DockerException as exc:
                logger.warning("Failed to connect %s to network %s: %s", name, network, exc)

    return created


def _start_containers(
    created: Dict[str, docker.models.containers.Container],
    manifest: Dict[str, Any],
    logger,
    dry_run: bool,
) -> None:
    """Start containers in dependency order."""
    entries = manifest.get("containers", [])
    ordered = sorted(entries, key=lambda entry: _parse_created(entry.get("created", "")))
    for entry in ordered:
        name = entry.get("name")
        if not name:
            continue
        if dry_run:
            _print_plan(f"Start container {name}")
            continue
        container_obj = created.get(name)
        if not container_obj:
            continue
        logger.info("start_container", name)
        container_obj.start()


def restore_bundle(
    bundle_path: str, dry_run: bool, skip_1panel_sync: bool, plan: bool = False
) -> None:
    """Restore a ImmiDock bundle onto the local Docker host."""
    logger = setup_logger()
    restore_dir = Path(".immidock_restore")
    bundle, cleanup_bundle = _stage_bundle(bundle_path, logger)
    if not bundle.exists():
        raise FileNotFoundError(f"Bundle not found: {bundle}")

    if plan:
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["tar", "-xf", str(bundle), "-C", tmpdir], check=True)
            manifest_path = Path(tmpdir) / "manifest.json"
            if not manifest_path.exists():
                raise FileNotFoundError("manifest.json not found in bundle")
            with manifest_path.open("r", encoding="utf-8") as handle:
                manifest = json.load(handle)
            volume_size = 0
            image_size = 0
            volumes_dir = Path(tmpdir) / "volumes"
            images_dir = Path(tmpdir) / "images"
            if volumes_dir.exists():
                volume_size = _dir_size(volumes_dir)
            if images_dir.exists():
                image_size = _dir_size(images_dir)
        _print_plan_summary(manifest, volume_size, image_size)
        if cleanup_bundle:
            try:
                bundle.unlink()
            except OSError:
                logger.warning("Failed to remove temporary bundle %s", bundle)
        return

    checksum_path = Path(f"{bundle}.sha256")
    if checksum_path.exists():
        logger.info("verify_checksum")
        if not verify_checksum(str(bundle)):
            raise RuntimeError("Bundle checksum verification failed")

    start_time = time.monotonic()
    _extract_bundle(bundle, restore_dir, logger, dry_run)

    manifest_path = restore_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found at {manifest_path}")
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "manifest_schema.json"
    _validate_manifest(manifest, schema_path)

    logger.info("resolve_networks")
    manifest = resolve_network_conflicts(manifest)

    try:
        client = docker.from_env()
    except DockerException as exc:
        logger.error("Docker connection failed: %s", exc)
        raise

    _check_restore_conflicts(manifest, logger)

    _warn_existing_paths(manifest, logger)

    networks_created = _create_networks(client, manifest, logger, dry_run)

    volumes_dir = restore_dir / "volumes"
    volumes_restored = 0
    if volumes_dir.exists():
        logger.info("restoring_volumes")
        archives = sorted(volumes_dir.glob("*.tar.zst"))
        for archive in _progress(archives, desc=translate("restoring_volumes"), unit="vol"):
            if _restore_volume(archive, logger, dry_run):
                volumes_restored += 1

    images_dir = restore_dir / "images"
    images_loaded = 0
    if images_dir.exists():
        logger.info("loading_images")
        image_archives = sorted(images_dir.glob("*.tar"))
        for image_archive in _progress(
            image_archives, desc=translate("loading_images"), unit="img"
        ):
            if _load_image(image_archive, logger, dry_run):
                images_loaded += 1

    created = _create_containers(client, manifest, logger, dry_run)
    if created or dry_run:
        logger.info("starting_containers")
    _start_containers(created, manifest, logger, dry_run)

    duration = _format_duration(time.monotonic() - start_time)
    container_total = len(manifest.get("containers", [])) if dry_run else len(created)
    print(translate("migration_summary"))
    print("------------------------")
    print(translate("containers_restored") % container_total)
    print(translate("volumes_restored") % volumes_restored)
    print(translate("images_loaded") % images_loaded)
    print(translate("networks_created") % networks_created)
    print(translate("duration") % duration)
    print(translate("status") % "SUCCESS")
    print(translate("migration_completed"))

    has_1panel = any(
        container.get("type") == "1panel_app" for container in manifest.get("containers", [])
    )
    if has_1panel and not skip_1panel_sync:
        _ensure_1panel_dirs(manifest, logger, dry_run)
        if dry_run:
            _print_plan("Sync 1Panel applications")
        else:
            sync_apps()

    if cleanup_bundle:
        try:
            bundle.unlink()
        except OSError:
            logger.warning("Failed to remove temporary bundle %s", bundle)
