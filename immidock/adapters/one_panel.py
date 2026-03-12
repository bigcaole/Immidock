"""1Panel adapter for ImmiDock."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from immidock.utils.logger import setup_logger

SYNC_ENDPOINT = "http://127.0.0.1:10086/api/v1/apps/sync"


def _post_sync_request(logger) -> bool:
    """Attempt to sync 1Panel apps via HTTP API."""
    try:
        import requests
    except ImportError:
        logger.warning("requests not installed; skipping API sync")
        return False

    logger.info("1panel_syncing")
    try:
        response = requests.post(SYNC_ENDPOINT, timeout=10)
    except requests.RequestException as exc:
        logger.warning("API sync failed: %s", exc)
        return False

    if 200 <= response.status_code < 300:
        logger.info("1panel_sync_done")
        return True

    logger.warning("API sync failed with status %s", response.status_code)
    return False


def _cli_sync(logger) -> bool:
    """Attempt to sync 1Panel apps via CLI."""
    logger.warning("1panel_api_fallback")
    result = subprocess.run(
        ["1panel", "app", "sync"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        logger.info("1panel_sync_done")
        return True

    stderr = result.stderr.strip()
    if stderr:
        logger.warning("1panel_cli_failed_detail", stderr)
    else:
        logger.warning("1panel_cli_failed")
    return False


def sync_apps() -> bool:
    """Synchronize 1Panel apps using API with CLI fallback."""
    logger = setup_logger()
    if not Path("/opt/1panel").exists():
        logger.warning("1panel_not_detected")
        return False

    logger.info("1panel_detected")
    if _post_sync_request(logger):
        return True
    return _cli_sync(logger)
