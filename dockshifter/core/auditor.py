"""Docker host auditor for ImmiDock."""

from __future__ import annotations

import os
import platform
import socket
from typing import Any, Dict, List, Optional, Set

import docker
from docker.errors import DockerException

from dockshifter.utils.logger import setup_logger


def _safe_stat(path: str, logger) -> Optional[os.stat_result]:
    """Return os.stat results for a path, or None if unavailable."""
    try:
        return os.stat(path)
    except FileNotFoundError:
        logger.warning("mount_source_not_found", path)
    except PermissionError:
        logger.warning("permission_denied_stat", path)
    except OSError as exc:
        logger.warning("failed_stat_mount", path, exc)
    return None


def _get_image_ref(container) -> str:
    """Select a stable image reference for a container."""
    if container.image.tags:
        return container.image.tags[0]
    attrs = container.attrs or {}
    config = attrs.get("Config", {})
    image = config.get("Image")
    if image:
        return image
    return container.image.id


def _get_image_digest(container) -> str:
    """Return the first repo digest if available."""
    repo_digests = container.image.attrs.get("RepoDigests", [])
    return repo_digests[0] if repo_digests else ""


def _is_1panel_mount(path: str) -> bool:
    """Return True if a mount path belongs to 1Panel apps."""
    return path.startswith("/opt/1panel/apps")


def _collect_mounts(container, client, logger) -> List[Dict[str, Any]]:
    """Collect mount metadata for a container."""
    mounts: List[Dict[str, Any]] = []
    for mount in container.attrs.get("Mounts", []):
        mount_type = mount.get("Type")
        if mount_type == "tmpfs":
            continue

        destination = mount.get("Destination", "")
        if mount_type == "bind":
            source_raw = mount.get("Source", "")
            source = os.path.realpath(source_raw) if source_raw else ""
            entry: Dict[str, Any] = {
                "type": "bind",
                "source": source,
                "destination": destination,
            }
            if source:
                stat_result = _safe_stat(source, logger)
                if stat_result:
                    entry["uid"] = stat_result.st_uid
                    entry["gid"] = stat_result.st_gid
                    entry["mode"] = oct(stat_result.st_mode & 0o777)
            mounts.append(entry)
        elif mount_type == "volume":
            volume_name = mount.get("Name") or mount.get("Source", "")
            mountpoint = ""
            if volume_name:
                try:
                    volume = client.volumes.get(volume_name)
                    mountpoint = volume.attrs.get("Mountpoint", "")
                except DockerException as exc:
                    logger.warning("failed_inspect_volume", volume_name, exc)
            source = mountpoint or mount.get("Source", "")
            entry = {
                "type": "volume",
                "source": source,
                "destination": destination,
            }
            mounts.append(entry)
    return mounts


def generate_manifest() -> Dict[str, Any]:
    """Generate a ImmiDock manifest from the current Docker host."""
    logger = setup_logger()
    try:
        client = docker.from_env()
    except DockerException as exc:
        logger.error("docker_connection_failed", exc)
        raise

    try:
        version_info = client.version()
        containers = client.containers.list(all=True)
        networks = client.networks.list()
        volumes = client.volumes.list()
    except DockerException as exc:
        logger.error("docker_query_failed", exc)
        raise

    image_set: Set[str] = set()
    container_entries: List[Dict[str, Any]] = []
    db_keywords = ("mysql", "postgres", "mariadb", "mongo", "redis")

    for container in containers:
        mounts = _collect_mounts(container, client, logger)
        container_type = "native_docker"
        for mount in mounts:
            if mount.get("type") == "bind" and _is_1panel_mount(mount.get("source", "")):
                container_type = "1panel_app"
                break

        image_ref = _get_image_ref(container)
        image_digest = _get_image_digest(container)
        image_set.add(image_ref)

        networks_map = container.attrs.get("NetworkSettings", {}).get("Networks", {})
        network_names = list(networks_map.keys())

        created = container.attrs.get("Created", "")

        entry: Dict[str, Any] = {
            "name": container.name,
            "id": container.id,
            "type": container_type,
            "image": image_ref,
            "created": created,
            "inspect": container.attrs,
            "mounts": mounts,
            "networks": network_names,
        }

        if image_digest:
            entry["image_digest"] = image_digest

        container_entries.append(entry)

        image_name = image_ref.lower()
        if container.status == "running" and any(keyword in image_name for keyword in db_keywords):
            logger.warning("db_container_detected", container.name)
            logger.warning("db_stop_warning")

    network_entries: List[Dict[str, Any]] = []
    for network in networks:
        attrs = network.attrs or {}
        entry = {
            "name": network.name,
            "driver": attrs.get("Driver", ""),
        }
        ipam_config = (attrs.get("IPAM", {}) or {}).get("Config", [])
        if ipam_config:
            entry_subnet = ipam_config[0].get("Subnet")
            entry_gateway = ipam_config[0].get("Gateway")
            if entry_subnet:
                entry["subnet"] = entry_subnet
            if entry_gateway:
                entry["gateway"] = entry_gateway
        network_entries.append(entry)

    volume_entries: List[Dict[str, Any]] = []
    for volume in volumes:
        attrs = volume.attrs or {}
        entry = {
            "name": volume.name,
        }
        driver = attrs.get("Driver")
        mountpoint = attrs.get("Mountpoint")
        if driver:
            entry["driver"] = driver
        if mountpoint:
            entry["mountpoint"] = mountpoint
        volume_entries.append(entry)

    manifest = {
        "manifest_version": "1.0",
        "source_env": {
            "hostname": socket.gethostname(),
            "os": platform.system(),
            "kernel": platform.release(),
            "architecture": platform.machine(),
            "docker_version": version_info.get("Version", ""),
        },
        "containers": container_entries,
        "networks": network_entries,
        "volumes": volume_entries,
        "images": sorted(image_set),
    }

    return manifest
