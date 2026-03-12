"""Localization helpers for ImmiDock."""

from __future__ import annotations

import locale
import os
from typing import Optional

MESSAGES_EN = {
    "binary_found": "%s found",
    "binary_missing": "%s not found",
    "docker_daemon_ok": "Docker daemon reachable",
    "docker_daemon_fail": "Docker daemon not reachable",
    "docker_permissions_ok": "Docker permissions OK",
    "docker_permissions_fail": "Docker permissions check failed",
    "docker_command_failed": "Docker command failed: %s",
    "disk_space_ok": "Disk space OK",
    "disk_space_low": "Low disk space",
    "estimate_unavailable": "Unable to estimate bundle size",
    "estimated_bundle_size": "Estimated bundle size: %s",
    "free_space": "Free space: %s",
    "doctor_ok": "All system checks passed",
    "command_started": "%s started",
    "command_finished": "%s finished (code %s)",
    "bundle_start": "Starting bundle creation",
    "bundle_created": "Bundle created successfully",
    "bundle_written": "Bundle written to %s",
    "archive_volume": "Archiving volume %s",
    "archiving_volumes": "Archiving volumes",
    "export_image": "Exporting Docker image %s",
    "exporting_images": "Exporting images",
    "creating_bundle": "Creating bundle %s",
    "bundle_checksum": "Bundle checksum: %s",
    "verify_checksum": "Verifying bundle checksum",
    "reading_bundle_stdin": "Reading bundle from stdin",
    "receiving_bundle": "Receiving bundle",
    "scan_volumes": "Scanning volumes...",
    "scan_images": "Scanning images...",
    "volumes_size": "Volumes size: %s",
    "images_size": "Images size: %s",
    "estimated_bundle_size": "Estimated bundle size: %s",
    "extract_bundle": "Extracting bundle",
    "resolve_networks": "Resolving network conflicts",
    "create_network": "Creating network %s",
    "create_container": "Creating container %s",
    "restoring_volumes": "Restoring volumes",
    "restore_volume": "Restoring volume %s",
    "loading_images": "Loading images",
    "load_image": "Loading image %s",
    "starting_containers": "Starting containers",
    "start_container": "Starting container %s",
    "migration_completed": "Migration completed",
    "migration_summary": "Migration Summary",
    "containers_restored": "Containers restored: %s",
    "volumes_restored": "Volumes restored: %s",
    "images_loaded": "Images loaded: %s",
    "networks_created": "Networks created: %s",
    "duration": "Duration: %s",
    "status": "Status: %s",
    "bundle_label": "Bundle",
    "size_label": "Size",
    "containers_label": "Containers",
    "volumes_label": "Volumes",
    "networks_label": "Networks",
    "images_label": "Images",
    "containers_header": "Containers",
    "container_entry": "- {name} | {image} | {ctype} | mounts: {mounts} | networks: {networks}",
    "streaming_bundle": "Streaming bundle to %s",
    "syncing_volume": "Syncing volume %s",
    "plan_title": "Migration Plan",
    "plan_containers": "Containers: %s",
    "plan_images": "Images: %s",
    "plan_volumes": "Volumes: %s",
    "plan_networks": "Networks: %s",
    "plan_volume_size": "Estimated Volume Size: %s",
    "plan_image_size": "Estimated Image Size: %s",
    "plan_containers_header": "Containers:",
    "plan_networks_header": "Networks:",
    "plan_item": "- %s",
    "conflict_detected": "Conflict detected:",
    "conflict_container": "Container %s already exists",
    "conflict_port": "Port %s already in use",
    "conflict_network": "Network %s already exists",
    "cleaning_temp": "Cleaning temporary files...",
    "removed_build": "Removed build directory.",
    "removed_restore": "Removed restore directory.",
    "1panel_detected": "Detected 1Panel installation",
    "1panel_syncing": "Syncing 1Panel applications",
    "1panel_sync_done": "1Panel app sync completed",
    "1panel_api_fallback": "API sync failed, trying CLI fallback",
    "1panel_cli_failed": "1Panel CLI sync failed",
    "1panel_cli_failed_detail": "1Panel CLI sync failed: %s",
    "1panel_not_detected": "1Panel not detected, skipping sync",
    "db_container_detected": "Database container detected: %s",
    "db_stop_warning": "For best consistency, stop database before backup.",
}

MESSAGES_ZH = {
    "binary_found": "%s 已找到",
    "binary_missing": "%s 未找到",
    "docker_daemon_ok": "Docker 守护进程可用",
    "docker_daemon_fail": "Docker 守护进程不可用",
    "docker_permissions_ok": "Docker 权限检查通过",
    "docker_permissions_fail": "Docker 权限检查失败",
    "docker_command_failed": "Docker 命令失败：%s",
    "disk_space_ok": "磁盘空间充足",
    "disk_space_low": "磁盘空间不足",
    "estimate_unavailable": "无法估算迁移包大小",
    "estimated_bundle_size": "预计迁移包大小：%s",
    "free_space": "可用空间：%s",
    "doctor_ok": "系统检查全部通过",
    "command_started": "%s 开始",
    "command_finished": "%s 结束（代码 %s）",
    "bundle_start": "开始创建迁移包",
    "bundle_created": "迁移包创建成功",
    "bundle_written": "迁移包已写入 %s",
    "archive_volume": "正在打包数据卷 %s",
    "archiving_volumes": "正在打包数据卷",
    "export_image": "正在导出镜像 %s",
    "exporting_images": "正在导出镜像",
    "creating_bundle": "正在创建迁移包 %s",
    "bundle_checksum": "迁移包校验值：%s",
    "verify_checksum": "正在校验迁移包",
    "reading_bundle_stdin": "正在从标准输入读取迁移包",
    "receiving_bundle": "正在接收迁移包",
    "scan_volumes": "开始扫描数据卷...",
    "scan_images": "开始扫描镜像...",
    "volumes_size": "数据卷大小：%s",
    "images_size": "镜像大小：%s",
    "estimated_bundle_size": "预计迁移包大小：%s",
    "extract_bundle": "正在解压迁移包",
    "resolve_networks": "正在解决网络冲突",
    "create_network": "正在创建网络 %s",
    "create_container": "正在创建容器 %s",
    "restoring_volumes": "正在恢复数据卷",
    "restore_volume": "正在恢复数据卷 %s",
    "loading_images": "正在加载镜像",
    "load_image": "正在加载镜像 %s",
    "starting_containers": "正在启动容器",
    "start_container": "正在启动容器 %s",
    "migration_completed": "迁移完成",
    "migration_summary": "迁移摘要",
    "containers_restored": "已恢复容器：%s",
    "volumes_restored": "已恢复数据卷：%s",
    "images_loaded": "已加载镜像：%s",
    "networks_created": "已创建网络：%s",
    "duration": "耗时：%s",
    "status": "状态：%s",
    "bundle_label": "迁移包",
    "size_label": "大小",
    "containers_label": "容器",
    "volumes_label": "数据卷",
    "networks_label": "网络",
    "images_label": "镜像",
    "containers_header": "容器列表",
    "container_entry": "- {name} | {image} | {ctype} | 挂载: {mounts} | 网络: {networks}",
    "streaming_bundle": "正在传输迁移包到 %s",
    "syncing_volume": "正在同步数据卷 %s",
    "plan_title": "迁移计划",
    "plan_containers": "容器数量：%s",
    "plan_images": "镜像数量：%s",
    "plan_volumes": "数据卷数量：%s",
    "plan_networks": "网络数量：%s",
    "plan_volume_size": "预计数据卷大小：%s",
    "plan_image_size": "预计镜像大小：%s",
    "plan_containers_header": "容器列表：",
    "plan_networks_header": "网络列表：",
    "plan_item": "- %s",
    "conflict_detected": "检测到冲突：",
    "conflict_container": "容器 %s 已存在",
    "conflict_port": "端口 %s 已被占用",
    "conflict_network": "网络 %s 已存在",
    "cleaning_temp": "正在清理临时文件...",
    "removed_build": "已删除构建目录。",
    "removed_restore": "已删除恢复目录。",
    "1panel_detected": "检测到 1Panel",
    "1panel_syncing": "正在同步 1Panel 应用",
    "1panel_sync_done": "1Panel 应用同步完成",
    "1panel_api_fallback": "API 同步失败，尝试 CLI",
    "1panel_cli_failed": "1Panel CLI 同步失败",
    "1panel_cli_failed_detail": "1Panel CLI 同步失败：%s",
    "1panel_not_detected": "未检测到 1Panel，跳过同步",
    "db_container_detected": "检测到数据库容器：%s",
    "db_stop_warning": "为保证一致性，建议备份前先停止数据库。",
}

_SUPPORTED = {"en", "zh"}
_LANG: Optional[str] = None


def get_language(cli_lang: Optional[str] = None) -> str:
    """Resolve the active language using CLI, env, locale, or default."""
    if cli_lang in _SUPPORTED:
        return cli_lang

    env_lang = os.getenv("IMMIDOCK_LANG")
    if env_lang:
        env_lang = env_lang.lower()
        if env_lang in _SUPPORTED:
            return env_lang
        if env_lang.startswith("zh"):
            return "zh"

    locale_lang = ""
    try:
        locale_lang = locale.getdefaultlocale()[0] or ""
    except (TypeError, ValueError):
        locale_lang = ""
    if not locale_lang:
        try:
            locale_lang = locale.getlocale()[0] or ""
        except (TypeError, ValueError):
            locale_lang = ""

    if locale_lang.lower().startswith("zh"):
        return "zh"

    return "en"


def set_language(cli_lang: Optional[str]) -> str:
    """Set the active language for translations."""
    global _LANG
    _LANG = get_language(cli_lang)
    return _LANG


def translate(key: str) -> str:
    """Translate a message key based on the active language."""
    language = _LANG or get_language()
    messages = MESSAGES_ZH if language == "zh" else MESSAGES_EN
    return messages.get(key, key)
