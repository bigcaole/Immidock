"""Docker network management for ImmiDock."""

from __future__ import annotations

import copy
import ipaddress
from typing import Any, Dict, Iterable, Optional, Set

import docker
from docker.errors import DockerException

from dockshifter.utils.logger import setup_logger


def _collect_existing_subnets(client: docker.DockerClient, logger) -> Set[ipaddress._BaseNetwork]:
    """Collect subnets already in use on the target host."""
    used_subnets: Set[ipaddress._BaseNetwork] = set()
    for network in client.networks.list():
        attrs = network.attrs or {}
        ipam = attrs.get("IPAM", {}) or {}
        for config in ipam.get("Config", []) or []:
            subnet = config.get("Subnet")
            if not subnet:
                continue
            try:
                used_subnets.add(ipaddress.ip_network(subnet, strict=False))
            except ValueError:
                logger.warning("invalid_subnet_host", subnet)
    return used_subnets


def _next_network(network: ipaddress._BaseNetwork) -> Optional[ipaddress._BaseNetwork]:
    """Return the next adjacent network with the same prefix length."""
    next_address = int(network.network_address) + network.num_addresses
    max_address = (1 << network.max_prefixlen) - 1
    if next_address > max_address:
        return None
    return ipaddress.ip_network((next_address, network.prefixlen), strict=False)


def _default_gateway(network: ipaddress._BaseNetwork) -> str:
    """Choose a default gateway inside the network."""
    if network.num_addresses >= 2:
        return str(ipaddress.ip_address(int(network.network_address) + 1))
    return str(network.network_address)


def _conflicts(candidate: ipaddress._BaseNetwork, used: Iterable[ipaddress._BaseNetwork]) -> bool:
    """Return True if candidate overlaps any used subnet."""
    return any(candidate.overlaps(existing) for existing in used)


def resolve_network_conflicts(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve subnet conflicts and return a corrected manifest copy."""
    logger = setup_logger()
    updated_manifest = copy.deepcopy(manifest)

    try:
        client = docker.from_env()
    except DockerException as exc:
        logger.error("docker_connection_failed", exc)
        raise

    used_subnets = _collect_existing_subnets(client, logger)

    for network in updated_manifest.get("networks", []):
        subnet = network.get("subnet")
        if not subnet:
            continue
        try:
            candidate = ipaddress.ip_network(subnet, strict=False)
        except ValueError:
            logger.warning("invalid_subnet_manifest", subnet)
            continue

        original = candidate
        while _conflicts(candidate, used_subnets):
            next_candidate = _next_network(candidate)
            if not next_candidate:
                raise RuntimeError(f"No available subnet for {network.get('name', '')}")
            candidate = next_candidate

        if candidate != original:
            logger.warning(
                "Subnet conflict for network %s: %s -> %s",
                network.get("name", ""),
                original,
                candidate,
            )
            network["subnet"] = str(candidate)
            if network.get("gateway"):
                network["gateway"] = _default_gateway(candidate)

        used_subnets.add(candidate)

    return updated_manifest
