"""CLI entrypoint for ImmiDock."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import docker
from docker.errors import DockerException
from jsonschema import ValidationError, validate

from dockshifter.core.auditor import generate_manifest
from dockshifter.core.bundler import build_bundle
from dockshifter.core.remote import migrate_to_host
from dockshifter.core.restorer import restore_bundle
from dockshifter.utils.i18n import set_language, translate
from dockshifter.utils.logger import setup_logger
from dockshifter.utils.system import check_binary_exists
from dockshifter.version import __version__


def _load_schema(schema_path: Path) -> Dict[str, Any]:
    """Load the manifest JSON schema from disk."""
    with schema_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _validate_manifest(manifest: Dict[str, Any], schema_path: Path) -> None:
    """Validate the manifest against the JSON schema."""
    schema = _load_schema(schema_path)
    validate(instance=manifest, schema=schema)


def _schema_path() -> Path:
    """Return the path to the manifest JSON schema."""
    return Path(__file__).resolve().parents[1] / "schemas" / "manifest_schema.json"


def _extract_lang_arg(argv: list[str]) -> tuple[Optional[str], list[str]]:
    """Extract --lang from argv, allowing it to appear after subcommands."""
    cleaned: list[str] = []
    lang: Optional[str] = None
    iterator = iter(range(len(argv)))
    skip_next = False
    for idx in iterator:
        if skip_next:
            skip_next = False
            continue
        arg = argv[idx]
        if arg == "--lang":
            if idx + 1 < len(argv):
                lang = argv[idx + 1]
                skip_next = True
            continue
        if arg.startswith("--lang="):
            lang = arg.split("=", 1)[1]
            continue
        cleaned.append(arg)
    return lang, cleaned


def _resolve_manifest_path(target: Path) -> Path:
    """Resolve where manifest.json should be read or written."""
    if target.suffix:
        return target.with_name("manifest.json")
    return target / "manifest.json"


def _format_bytes(value: int) -> str:
    """Format a byte count into a human-readable string."""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{int(size)} B"


def _directory_size(path: Path) -> int:
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
    paths = set()
    for container in manifest.get("containers", []):
        for mount in container.get("mounts", []):
            source = mount.get("source", "")
            if source:
                paths.add(os.path.realpath(source))

    total = 0
    for source in paths:
        path = Path(source)
        if not path.exists():
            continue
        if path.is_file():
            total += path.stat().st_size
        else:
            total += _directory_size(path)
    return total


def _estimate_image_size(manifest: Dict[str, Any], logger) -> int:
    """Estimate total image size for manifest images."""
    try:
        client = docker.from_env()
    except DockerException as exc:
        logger.warning("docker_connection_failed", exc)
        return 0

    total = 0
    for image_ref in manifest.get("images", []):
        try:
            image = client.images.get(image_ref)
            total += int(image.attrs.get("Size", 0) or 0)
        except DockerException as exc:
            logger.warning("unable_inspect_image", image_ref, exc)
    return total


def _load_manifest_from_bundle(bundle: Path) -> Tuple[Dict[str, Any], int]:
    """Load manifest.json from a bundle file or directory and return its size."""
    if bundle.is_file():
        size = bundle.stat().st_size
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                ["tar", "-xf", str(bundle), "-C", tmpdir, "manifest.json"],
                check=True,
            )
            manifest_path = Path(tmpdir) / "manifest.json"
            with manifest_path.open("r", encoding="utf-8") as handle:
                return json.load(handle), size
    manifest_path = _resolve_manifest_path(bundle)
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    size = _directory_size(bundle) if bundle.is_dir() else 0
    return manifest, size


def _estimate_bundle_size(logger) -> Optional[int]:
    """Estimate bundle size based on Docker images and mount paths."""
    try:
        client = docker.from_env()
    except DockerException as exc:
        logger.error("docker_connection_failed", exc)
        return None

    total = 0
    image_sizes = 0
    try:
        for image in client.images.list():
            image_sizes += int(image.attrs.get("Size", 0) or 0)
    except DockerException as exc:
        logger.warning("unable_inspect_images", exc)

    mount_paths = set()
    try:
        for container in client.containers.list(all=True):
            for mount in container.attrs.get("Mounts", []):
                mount_type = mount.get("Type")
                if mount_type == "bind":
                    source = mount.get("Source")
                    if source:
                        mount_paths.add(os.path.realpath(source))
                elif mount_type == "volume":
                    name = mount.get("Name") or mount.get("Source")
                    if name:
                        try:
                            volume = client.volumes.get(name)
                            mountpoint = volume.attrs.get("Mountpoint")
                            if mountpoint:
                                mount_paths.add(mountpoint)
                        except DockerException:
                            continue
    except DockerException as exc:
        logger.warning("unable_inspect_container_mounts", exc)

    for path in mount_paths:
        path_obj = Path(path)
        if not path_obj.exists():
            continue
        if path_obj.is_file():
            total += path_obj.stat().st_size
        else:
            total += _directory_size(path_obj)

    return total + image_sizes


def _doctor_command(logger) -> int:
    """Run pre-migration diagnostics for ImmiDock."""
    status = 0

    for binary in ["tar", "zstd", "docker", "rsync", "ssh"]:
        if check_binary_exists(binary):
            logger.info("binary_found", binary)
        else:
            logger.error("binary_missing", binary)
            status = 1

    if check_binary_exists("docker"):
        version_result = subprocess.run(
            ["docker", "version"],
            check=False,
            capture_output=True,
            text=True,
        )
        if version_result.returncode == 0:
            logger.info("docker_daemon_ok")
        else:
            logger.error("docker_daemon_fail")
            if version_result.stderr:
                logger.error("docker_command_failed", version_result.stderr.strip())
            status = 1

        ps_result = subprocess.run(
            ["docker", "ps"],
            check=False,
            capture_output=True,
            text=True,
        )
        if ps_result.returncode == 0:
            logger.info("docker_permissions_ok")
        else:
            logger.error("docker_permissions_fail")
            if ps_result.stderr:
                logger.error("docker_command_failed", ps_result.stderr.strip())
            status = 1

    estimate = _estimate_bundle_size(logger)
    if estimate is not None:
        usage = shutil.disk_usage(Path.cwd())
        required = estimate * 2
        if usage.free < required:
            logger.warning("disk_space_low")
        else:
            logger.info("disk_space_ok")
        logger.info("estimated_bundle_size", _format_bytes(estimate))
        logger.info("free_space", _format_bytes(usage.free))
    else:
        logger.warning("estimate_unavailable")

    if status == 0:
        logger.info("doctor_ok")

    return status


def _pack_command(output_path: Path, logger, beginner: bool) -> int:
    """Run the pack command workflow."""
    if beginner:
        logger.info("beginner_mode_on")
        logger.info("beginner_pack_intro")
    try:
        manifest = generate_manifest()
    except DockerException as exc:
        logger.error("docker_connection_failed", exc)
        return 1
    except Exception as exc:
        logger.error("failed_generate_manifest", exc)
        return 1
    if beginner:
        logger.info("beginner_pack_manifest")
    try:
        _validate_manifest(manifest, _schema_path())
    except ValidationError as exc:
        logger.error("manifest_validation_failed", exc.message)
        return 1

    try:
        if beginner:
            logger.info("beginner_pack_bundle")
        logger.info("scan_volumes")
        volume_size = _estimate_volume_size(manifest)
        logger.info("volumes_size", _format_bytes(volume_size))
        logger.info("scan_images")
        image_size = _estimate_image_size(manifest, logger)
        logger.info("images_size", _format_bytes(image_size))
        logger.info("estimated_bundle_size", _format_bytes(volume_size + image_size))
        build_bundle(manifest, str(output_path))
    except Exception as exc:
        logger.error("bundling_failed", exc)
        return 1

    logger.info("bundle_written", output_path)
    return 0


def _inspect_command(input_path: Path, logger) -> int:
    """Inspect an ImmiDock manifest and print a summary."""
    if not input_path.exists():
        logger.error("bundle_not_found", input_path)
        return 1

    try:
        manifest, bundle_size = _load_manifest_from_bundle(input_path)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        logger.error("failed_read_bundle", exc)
        return 1

    containers = manifest.get("containers", [])
    networks = manifest.get("networks", [])
    volumes = manifest.get("volumes", [])
    images = manifest.get("images", [])

    print(f"{translate('bundle_label')}: {input_path}")
    if bundle_size:
        print(f"{translate('size_label')}: {_format_bytes(bundle_size)}")
    print(f"{translate('containers_label')}: {len(containers)}")
    print(f"{translate('volumes_label')}: {len(volumes)}")
    print(f"{translate('networks_label')}: {len(networks)}")
    print(f"{translate('images_label')}: {len(images)}")
    print(f"\n{translate('containers_header')}")
    for container in containers:
        name = container.get("name", "")
        image = container.get("image", "")
        ctype = container.get("type", "")
        mount_count = len(container.get("mounts", []))
        network_count = len(container.get("networks", []))
        line = translate("container_entry").format(
            name=name,
            image=image,
            ctype=ctype,
            mounts=mount_count,
            networks=network_count,
        )
        print(line)

    return 0


def _restore_command(
    bundle_path: Path,
    dry_run: bool,
    skip_1panel_sync: bool,
    plan: bool,
    logger,
    beginner: bool,
) -> int:
    """Restore an ImmiDock bundle onto the local host."""
    if beginner:
        logger.info("beginner_mode_on")
        logger.info("beginner_restore_intro")
        logger.info("beginner_restore_volumes")
        logger.info("beginner_restore_images")
        logger.info("beginner_restore_containers")
    try:
        restore_bundle(
            str(bundle_path),
            dry_run=dry_run,
            skip_1panel_sync=skip_1panel_sync,
            plan=plan,
        )
    except ValidationError as exc:
        logger.error("manifest_validation_failed", exc.message)
        return 1
    except Exception as exc:
        logger.error("restore_failed", exc)
        return 1
    return 0


def _migrate_command(
    target: str, incremental: bool, plan: bool, logger, beginner: bool
) -> int:
    """Migrate an ImmiDock bundle to a remote host via SSH."""
    if beginner:
        logger.info("beginner_mode_on")
        logger.info("beginner_migrate_intro")
        logger.info("beginner_migrate_transfer")
        logger.info("beginner_migrate_restore")
    try:
        migrate_to_host(target, incremental, plan=plan)
    except Exception as exc:
        logger.error("migration_failed", exc)
        return 1
    return 0


def _clean_command(logger) -> int:
    """Clean temporary build and restore directories."""
    logger.info("cleaning_temp")
    build_dir = Path(".immidock_build")
    restore_dir = Path(".immidock_restore")
    if build_dir.exists():
        shutil.rmtree(build_dir)
        logger.info("removed_build")
    if restore_dir.exists():
        shutil.rmtree(restore_dir)
        logger.info("removed_restore")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="immidock",
        description="ImmiDock Docker Migration Tool",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--lang",
        choices=["en", "zh"],
        help="Language for CLI output (en or zh)",
    )
    parser.add_argument(
        "--beginner",
        action="store_true",
        help="Show beginner-friendly step explanations",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    pack_parser = subparsers.add_parser("pack", help="Capture a host manifest")
    pack_parser.add_argument(
        "--output",
        required=True,
        help="Target bundle path (manifest.json will be written alongside)",
    )

    inspect_parser = subparsers.add_parser("inspect", help="Inspect a manifest bundle")
    inspect_parser.add_argument("input", help="Path to an ImmiDock bundle")

    restore_parser = subparsers.add_parser("restore", help="Restore an ImmiDock bundle")
    restore_parser.add_argument("input", help="Path to an ImmiDock bundle")
    restore_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the restore plan without executing changes",
    )
    restore_parser.add_argument(
        "--skip-1panel-sync",
        action="store_true",
        help="Skip 1Panel application synchronization",
    )
    restore_parser.add_argument(
        "--plan",
        action="store_true",
        help="Print a migration preview without executing changes",
    )

    migrate_parser = subparsers.add_parser("migrate", help="Migrate to a remote host via SSH")
    migrate_parser.add_argument("target", help="SSH target (example: root@host)")
    migrate_parser.add_argument(
        "--incremental",
        action="store_true",
        help="Use rsync to transfer only changed files",
    )
    migrate_parser.add_argument(
        "--plan",
        action="store_true",
        help="Print a migration preview without executing changes",
    )

    subparsers.add_parser("doctor", help="Run pre-migration diagnostics")
    subparsers.add_parser("clean", help="Remove temporary build files")

    return parser


def main() -> int:
    """CLI main entrypoint."""
    parser = _build_parser()
    lang_override, cleaned_argv = _extract_lang_arg(sys.argv[1:])
    args = parser.parse_args(cleaned_argv)
    set_language(lang_override or args.lang)
    logger = setup_logger()
    logger.info("command_started", args.command)

    if args.command == "pack":
        result = _pack_command(Path(args.output), logger, args.beginner)
    elif args.command == "inspect":
        result = _inspect_command(Path(args.input), logger)
    elif args.command == "restore":
        result = _restore_command(
            Path(args.input),
            args.dry_run,
            args.skip_1panel_sync,
            args.plan,
            logger,
            args.beginner,
        )
    elif args.command == "migrate":
        result = _migrate_command(
            args.target, args.incremental, args.plan, logger, args.beginner
        )
    elif args.command == "doctor":
        result = _doctor_command(logger)
    elif args.command == "clean":
        result = _clean_command(logger)
    else:
        logger.error("unknown_command")
        result = 1

    logger.info("command_finished", args.command, result)
    return result


if __name__ == "__main__":
    sys.exit(main())
