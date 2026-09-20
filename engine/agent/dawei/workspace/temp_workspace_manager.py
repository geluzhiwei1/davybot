# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""临时工作空间管理器

为定时任务和常规任务自动创建临时工作空间。
临时工作空间在任务完成后可被自动清理。
"""

import asyncio
import json
import logging
import shutil
import uuid
from datetime import datetime, timedelta
from dawei.core.datetime_compat import UTC
from pathlib import Path
from typing import Any, Dict

from dawei import get_dawei_home
from dawei.storage.storage_provider import StorageProvider
from dawei.workspace.models import WorkspaceLifecycle, WorkspaceType

logger = logging.getLogger(__name__)

# 全局锁：防止并发创建临时工作空间时 workspaces.json 读写竞争
_register_lock = asyncio.Lock()


class TempWorkspaceManager:
    """临时工作空间管理器

    临时工作空间目录: ~/.normnomos/temp_workspaces/{user_id}/{tenant_id}/{uuid}/
    在 workspaces.json 中标记 lifecycle=temporary + owner_user_id + tenant_id
    """

    TEMP_WORKSPACE_DIR_NAME = "temp_workspaces"

    def get_temp_workspace_base_dir(self) -> Path:
        """获取临时工作空间根目录"""
        base = get_dawei_home() / self.TEMP_WORKSPACE_DIR_NAME
        base.mkdir(parents=True, exist_ok=True)
        return base

    async def create_temp_workspace(
        self,
        name: str | None = None,
        display_name: str | None = None,
        workspace_type: str = WorkspaceType.SIMPLE_TASK.value,
        source_task_id: str | None = None,
        source_task_type: str | None = None,
        owner_user_id: str = "default_user",
        tenant_id: str = "personal",
    ) -> Dict[str, Any]:
        """创建一个临时工作空间

        Args:
            name: 工作区名称（如未提供则自动生成 "temp-{uuid[:8]}"）
            display_name: 显示名称（如未提供则用 "临时工作区"）
            workspace_type: 工作区来源类型（simple_task / scheduled_task）
            source_task_id: 触发创建的任务ID
            source_task_type: 触发创建的任务类型描述
            owner_user_id: 归属用户ID（物理隔离用）
            tenant_id: 租户ID（物理隔离用，个人身份为 "personal"）

        Returns:
            工作区信息字典 { id, name, display_name, lifecycle, workspace_type, path }
        """
        # 校验 workspace_type 必须是 WorkspaceType 枚举的有效成员
        try:
            WorkspaceType(workspace_type)
        except ValueError:
            raise ValueError(
                f"Invalid workspace_type: {workspace_type!r}. "
                f"Must be one of: {[t.value for t in WorkspaceType]}"
            )

        ws_id = str(uuid.uuid4())
        ws_name = name or f"temp-{ws_id[:8]}"
        ws_display_name = display_name or "临时工作区"

        # 创建目录（物理隔离：{user_id}/{tenant_id}/{uuid}/）
        base_dir = self.get_temp_workspace_base_dir()
        identity_dir = base_dir / owner_user_id / tenant_id
        identity_dir.mkdir(parents=True, exist_ok=True)
        ws_path = identity_dir / ws_id
        ws_path.mkdir(parents=True, exist_ok=True)

        # 创建 .dawei 目录结构
        dawei_dir = ws_path / ".dawei"
        dawei_dir.mkdir(parents=True, exist_ok=True)
        (dawei_dir / "chat-history").mkdir(exist_ok=True)
        (dawei_dir / "checkpoints").mkdir(exist_ok=True)
        (dawei_dir / "task_graphs").mkdir(exist_ok=True)

        now = datetime.now(UTC).isoformat()

        # 写入工作区级配置（不再使用 is_temporary）
        workspace_config = {
            "id": ws_id,
            "name": ws_name,
            "display_name": ws_display_name,
            "created_at": now,
            "workspace_type": workspace_type,
            "lifecycle": WorkspaceLifecycle.TEMPORARY.value,
            "source_task_id": source_task_id,
            "source_task_type": source_task_type,
            "last_accessed_at": now,
        }
        config_path = dawei_dir / "workspace.json"
        config_path.write_text(json.dumps(workspace_config, indent=2, ensure_ascii=False), encoding="utf-8")

        # 注册到系统级索引
        await self._register_in_system_index(
            ws_id, ws_name, ws_display_name, str(ws_path), workspace_type,
            owner_user_id=owner_user_id, tenant_id=tenant_id,
        )

        logger.info(f"[TEMP-WS] Created temp workspace: {ws_id} ({ws_display_name}) type={workspace_type} user={owner_user_id} tenant={tenant_id} at {ws_path}")

        return {
            "id": ws_id,
            "name": ws_name,
            "display_name": ws_display_name,
            "lifecycle": WorkspaceLifecycle.TEMPORARY.value,
            "workspace_type": workspace_type,
            "path": str(ws_path),
        }

    async def _register_in_system_index(
        self,
        workspace_id: str,
        name: str,
        display_name: str,
        path: str,
        workspace_type: str = WorkspaceType.SIMPLE_TASK.value,
        owner_user_id: str = "default_user",
        tenant_id: str = "personal",
    ):
        """在系统级索引 workspaces.json 中注册临时工作空间（使用 lifecycle + workspace_type + 身份隔离）"""
        async with _register_lock:
            system_storage = StorageProvider.get_system_storage()

            if await system_storage.exists("workspaces.json"):
                content = await system_storage.read_file("workspaces.json")
                data = json.loads(content)
            else:
                data = {"workspaces": []}

            data["workspaces"].append(
                {
                    "id": workspace_id,
                    "name": name,
                    "display_name": display_name,
                    "path": path,
                    "created_at": datetime.now(UTC).isoformat(),
                    "is_active": True,
                    "lifecycle": WorkspaceLifecycle.TEMPORARY.value,
                    "workspace_type": workspace_type,
                    "owner_user_id": owner_user_id,
                    "tenant_id": tenant_id,
                },
            )

            await system_storage.write_file(
                "workspaces.json",
                json.dumps(data, indent=2, ensure_ascii=False),
            )

            # 清除缓存并重新加载
            StorageProvider.clear_system_storage_cache()
            from dawei.workspace.workspace_manager import workspace_manager
            workspace_manager.reload()

    async def cleanup_orphaned_temp_workspaces(self) -> int:
        """清理无活跃任务的临时工作空间

        在 server startup 时调用。
        - 遍历 workspaces.json 索引中 lifecycle=temporary 的工作区
        - 检查工作区是否有活跃任务（定时任务 + 简单任务 + 任务图）
        - 无活跃任务则删除整个工作区目录并移除索引记录

        Returns:
            清理的临时工作空间数量
        """
        base_dir = self.get_temp_workspace_base_dir()
        cleaned = 0

        async with _register_lock:
            # 读取系统级索引
            system_storage = StorageProvider.get_system_storage()
            if not await system_storage.exists("workspaces.json"):
                return 0

            content = await system_storage.read_file("workspaces.json")
            data = json.loads(content)
            workspaces = data.get("workspaces", [])

            # 筛选 lifecycle=temporary 的工作区
            temp_workspaces = [
                ws for ws in workspaces
                if ws.get("lifecycle") == WorkspaceLifecycle.TEMPORARY.value
            ]

            # 构建磁盘上实际存在的 workspace 目录集合（三层：user/tenant/uuid）
            # key = workspace uuid（最后一级目录名）
            disk_paths = {}  # {uuid: full_path}
            if base_dir.exists():
                for user_dir in base_dir.iterdir():
                    if not user_dir.is_dir():
                        continue
                    for tenant_dir in user_dir.iterdir():
                        if not tenant_dir.is_dir():
                            continue
                        for ws_dir in tenant_dir.iterdir():
                            if ws_dir.is_dir() and (ws_dir / ".dawei").exists():
                                disk_paths[ws_dir.name] = ws_dir

            # 从索引中已知的 temp workspace
            indexed_ids = {ws["id"] for ws in temp_workspaces if ws.get("id")}

            # 处理索引中已注册的临时工作空间
            for ws in temp_workspaces:
                ws_id = ws["id"]
                ws_path = Path(ws["path"]) if ws.get("path") else base_dir / ws_id

                # 检查是否有活跃任务（三路检查）
                has_active_tasks = self._has_active_tasks_sync(ws_path)

                if not has_active_tasks:
                    # 删除目录
                    if ws_path.exists():
                        try:
                            shutil.rmtree(ws_path)
                            logger.info(f"[TEMP-WS] Cleaned up temp workspace dir: {ws_path}")
                        except OSError as e:
                            logger.warning(f"[TEMP-WS] Failed to remove {ws_path}: {e}")
                            continue

                    # 从索引中移除
                    data["workspaces"] = [w for w in data["workspaces"] if w["id"] != ws_id]
                    cleaned += 1
                    logger.info(f"[TEMP-WS] Removed temp workspace from index: {ws_id}")

            # 处理磁盘上存在但索引中缺失的孤儿目录
            orphan_ids = set(disk_paths.keys()) - indexed_ids
            for orphan_id in orphan_ids:
                orphan_path = disk_paths[orphan_id]
                try:
                    shutil.rmtree(orphan_path)
                    cleaned += 1
                    logger.info(f"[TEMP-WS] Cleaned up orphan temp workspace dir: {orphan_path}")
                except OSError as e:
                    logger.warning(f"[TEMP-WS] Failed to remove orphan {orphan_path}: {e}")

            if cleaned > 0:
                await system_storage.write_file(
                    "workspaces.json",
                    json.dumps(data, indent=2, ensure_ascii=False),
                )
                StorageProvider.clear_system_storage_cache()
                from dawei.workspace.workspace_manager import workspace_manager
                workspace_manager.reload()

        return cleaned

    def _has_active_tasks_sync(self, ws_path: Path) -> bool:
        """检查工作空间是否有活跃任务（同步版本，用于 cleanup）

        分维度检查，任一命中即返回 True：
        1. 定时任务: scheduled_tasks/ 下存在 pending/triggered 状态
        2. 简单任务: chat-history/ 下存在 24h 内更新的文件
        3. 任务图:   task_graphs/ 下存在文件
        """
        dawei_dir = ws_path / ".dawei"

        # 1. 定时任务活跃度
        scheduled_dir = dawei_dir / "scheduled_tasks"
        if scheduled_dir.exists():
            active_statuses = {"pending", "triggered"}
            for task_file in scheduled_dir.glob("*.json"):
                try:
                    data = json.loads(task_file.read_text(encoding="utf-8"))
                    if data.get("status") in active_statuses:
                        return True
                except (OSError, json.JSONDecodeError) as e:
                    logger.warning(f"[TEMP-WS] Failed to read task file {task_file}: {e}")
                    continue

        # 2. 简单任务活跃度（24h 内有对话更新）
        chat_dir = dawei_dir / "chat-history"
        if chat_dir.exists():
            cutoff = datetime.now(UTC) - timedelta(hours=24)
            for conv_file in chat_dir.glob("*.json"):
                try:
                    mtime = datetime.fromtimestamp(conv_file.stat().st_mtime, tz=UTC)
                    if mtime > cutoff:
                        return True
                except OSError:
                    continue

        # 3. 任务图活跃度（存在任何 task graph 文件）
        task_graphs_dir = dawei_dir / "task_graphs"
        if task_graphs_dir.exists() and any(task_graphs_dir.glob("*.json")):
            return True

        return False


# 全局单例
temp_workspace_manager = TempWorkspaceManager()
