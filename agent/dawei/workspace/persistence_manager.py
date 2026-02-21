"""Workspace Persistence Manager

统一的workspace持久化管理器,负责管理所有workspace元素的持久化:
- Conversations (对话历史)
- Task Graphs (任务图)
- Task Nodes (任务节点)
- Checkpoints (检查点)
- Workspace Settings (工作区设置)
- Workspace Metadata (工作区元数据)

Design Principles:
1. 统一的目录结构: 所有持久化数据使用一致的命名和存储方式
2. 原子性操作: 使用临时文件+重命名保证写入原子性
3. 一致的文件命名: {timestamp}_{id}.{ext} 或 {id}.{ext}
4. 向后兼容: 支持读取旧格式数据
5. 线程安全: 使用文件锁保证并发安全
"""

import asyncio
import contextlib
import json
import logging
import os
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

import aiofiles


class WorkspacePersistenceError(Exception):
    """Workspace持久化相关错误"""


logger = logging.getLogger(__name__)


class DateTimeEncoder(json.JSONEncoder):
    """自定义 JSON 编码器，用于处理 datetime、date 和 dataclass 对象"""

    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if is_dataclass(obj):
            return asdict(obj)
        return super().default(obj)


class ResourceLock:
    """资源锁，用于防止并发保存同一个资源"""

    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def acquire(self, resource_key: str):
        """获取资源锁"""
        async with self._global_lock:
            if resource_key not in self._locks:
                self._locks[resource_key] = asyncio.Lock()
            return self._locks[resource_key]

    async def cleanup(self):
        """清理未使用的锁"""
        async with self._global_lock:
            # 清理所有锁
            self._locks.clear()


class ResourceType(Enum):
    """资源类型枚举"""

    CONVERSATION = "conversation"
    TASK_GRAPH = "task_graph"
    TASK_NODE = "task_node"
    CHECKPOINT = "checkpoint"
    WORKSPACE_SETTINGS = "workspace_settings"
    WORKSPACE_INFO = "workspace_info"
    SCHEDULED_TASK = "scheduled_task"


T = TypeVar("T")


class WorkspacePersistenceManager:
    """Workspace持久化管理器

    负责统一管理workspace中所有资源的持久化操作。
    采用目录结构:
    .dawei/
    ├── conversations/          # 对话历史
    ├── task_graphs/           # 任务图
    ├── task_nodes/            # 任务节点状态
    ├── checkpoints/           # 检查点
    ├── workspace.json         # 工作区设置
    └── metadata.json          # 工作区元数据
    """

    def __init__(self, workspace_path: str):
        """初始化持久化管理器

        Args:
            workspace_path: workspace根目录

        """
        from dawei.config import get_dawei_home

        self.workspace_path = Path(workspace_path)
        self.persistence_dir = self.workspace_path / ".dawei"
        self.lock_dir = self.persistence_dir / ".locks"

        # 全局目录（在 DAWEI_HOME 下）
        dawei_home = Path(get_dawei_home())
        self.checkpoints_dir = dawei_home / "checkpoints"
        self.sessions_dir = dawei_home / "sessions"  # 全局会话目录

        # 工作区特定目录（在 workspace/.dawei 下）
        self.task_graphs_dir = self.persistence_dir / "task_graphs"
        self.task_nodes_dir = self.persistence_dir / "task_nodes"
        self.scheduled_tasks_dir = self.persistence_dir / "scheduled_tasks"
        # 向后兼容：保留 conversations_dir 指向工作区级别（旧数据）
        self.conversations_dir = self.persistence_dir / "conversations"

        # 资源锁，防止并发保存
        self._resource_lock = ResourceLock()

        # 确保目录存在
        self._ensure_directories()

    def _ensure_directories(self):
        """确保所有必要的目录存在"""
        # 全局目录（DAWEI_HOME）
        global_dirs = [
            self.checkpoints_dir,
            self.sessions_dir,
        ]

        # 工作区特定目录
        workspace_dirs = [
            self.persistence_dir,
            self.lock_dir,
            self.task_graphs_dir,
            self.task_nodes_dir,
            self.conversations_dir,  # 向后兼容
        ]

        # 创建所有目录
        all_dirs = global_dirs + workspace_dirs
        for directory in all_dirs:
            directory.mkdir(parents=True, exist_ok=True)

        # 确保scheduled_tasks目录存在
        self.scheduled_tasks_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"[PERSISTENCE] Workspace persistence directories initialized",
            extra={
                "global_dirs": [str(d) for d in global_dirs],
                "workspace_dir": str(self.persistence_dir),
            },
        )

    # ==================== 通用持久化方法 ====================

    async def save_resource(
        self,
        resource_type: ResourceType,
        resource_id: str,
        data: dict[str, Any],
        timestamp: str | None = None,
        use_timestamp: bool = False,
    ) -> bool:
        """保存资源到文件

        Args:
            resource_type: 资源类型
            resource_id: 资源ID
            data: 要保存的数据 (dict)
            timestamp: 可选的时间戳
            use_timestamp: 是否在文件名中使用时间戳

        Returns:
            是否保存成功

        """
        # 获取资源锁，防止并发保存
        resource_key = f"{resource_type.value}:{resource_id}"
        lock = await self._resource_lock.acquire(resource_key)

        async with lock:
            try:
                # 确定保存目录
                resource_dir = self._get_resource_dir(resource_type)

                # 生成文件名
                if use_timestamp:
                    ts = timestamp or datetime.now(UTC).strftime("%Y%m%d%H%M%S")
                    filename = f"{ts}_{resource_id}.json"
                else:
                    filename = f"{resource_id}.json"

                file_path = resource_dir / filename

                # 确保目标目录存在
                resource_dir.mkdir(parents=True, exist_ok=True)

                # 原子性写入: 先写临时文件,再重命名
                temp_path = file_path.with_suffix(".tmp")

                logger.debug(f"[PERSISTENCE] Writing to temp file: {temp_path}")

                # 写入临时文件 - Fast Fail 原则
                try:
                    # 使用同步写入以避免 aiofiles 的潜在竞争条件
                    # aiofiles 在某些情况下可能不会立即创建文件
                    with temp_path.open("w", encoding="utf-8") as f:
                        # 使用自定义编码器处理 datetime 对象
                        content = json.dumps(
                            data,
                            indent=2,
                            ensure_ascii=False,
                            cls=DateTimeEncoder,
                        )
                        f.write(content)
                        f.flush()  # 确保数据写入磁盘
                        os.fsync(f.fileno())  # 强制同步到磁盘
                except (OSError, TypeError) as write_error:
                    logger.error(
                        f"[PERSISTENCE] Failed to write temp file {temp_path}: {write_error}",
                        exc_info=True,
                    )
                    raise WorkspacePersistenceError(
                        f"Failed to write temp file {temp_path}: {write_error}",
                    )

                # 验证临时文件存在
                if not temp_path.exists():
                    logger.error(f"[PERSISTENCE] Temp file {temp_path} does not exist after write!")
                    raise FileNotFoundError(f"Temp file {temp_path} was not created")

                logger.debug(
                    f"[PERSISTENCE] Temp file created successfully: {temp_path}, size: {temp_path.stat().st_size} bytes",
                )

                # 原子性重命名 - Windows 兼容处理
                # Windows 可能会因为文件被锁定而失败，需要重试或使用备用策略
                max_retries = 5
                retry_delay = 0.05  # 50ms
                last_error = None

                for attempt in range(max_retries):
                    try:
                        temp_path.replace(file_path)
                        logger.debug(f"[PERSISTENCE] Renamed {temp_path} to {file_path}")
                        break  # 成功，退出重试循环
                    except (OSError, PermissionError) as rename_error:
                        last_error = rename_error
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"[PERSISTENCE] Retry {attempt + 1}/{max_retries}: Failed to rename {temp_path} to {file_path}: {rename_error}",
                            )
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2  # 指数退避
                        else:
                            # 最后一次重试失败，尝试备用策略
                            logger.exception(
                                f"[PERSISTENCE] All retries failed for {temp_path} -> {file_path}, trying fallback strategy",
                            )

                            # 备用策略：先删除目标文件，再移动
                            try:
                                if file_path.exists():
                                    # Windows: 如果目标文件存在，尝试先删除
                                    file_path.unlink()
                                    logger.debug(f"[PERSISTENCE] Deleted target file {file_path}")

                                # 再次尝试重命名
                                temp_path.replace(file_path)
                                logger.debug(
                                    f"[PERSISTENCE] Renamed {temp_path} to {file_path} using fallback strategy",
                                )
                                break  # 成功，退出重试循环
                            except (OSError, PermissionError) as fallback_error:
                                logger.error(
                                    f"[PERSISTENCE] Fallback strategy also failed: {fallback_error}",
                                    exc_info=True,
                                )
                                # 清理临时文件
                                if temp_path.exists():
                                    with contextlib.suppress(OSError):
                                        temp_path.unlink()
                                raise WorkspacePersistenceError(
                                    f"Failed to rename {temp_path} to {file_path} after all retries and fallback: {last_error}",
                                )

                logger.debug(
                    f"[PERSISTENCE] Saved {resource_type.value} {resource_id} to {file_path}",
                )
                return True

            except WorkspacePersistenceError:
                # 已经记录了详细错误，直接向上抛出
                raise
            except Exception as e:
                logger.error(
                    f"[PERSISTENCE] Unexpected error saving {resource_type.value} {resource_id}: {e}",
                    exc_info=True,
                )
                raise WorkspacePersistenceError(
                    f"Unexpected error saving {resource_type.value} {resource_id}: {e}",
                )

    async def load_resource(
        self,
        resource_type: ResourceType,
        resource_id: str,
    ) -> dict[str, Any] | None:
        """从文件加载资源

        Args:
            resource_type: 资源类型
            resource_id: 资源ID

        Returns:
            资源数据,如果不存在则返回None

        """
        try:
            resource_dir = self._get_resource_dir(resource_type)

            # 尝试加载带时间戳的文件
            files = list(resource_dir.glob(f"*_{resource_id}.json"))
            if files:
                # 选择最新的文件
                file_path = max(files, key=lambda p: p.stat().st_mtime)
            else:
                # 尝试加载不带时间戳的文件
                file_path = resource_dir / f"{resource_id}.json"
                if not file_path.exists():
                    return None

            async with aiofiles.open(file_path, encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)

            logger.debug(
                f"[PERSISTENCE] Loaded {resource_type.value} {resource_id} from {file_path}",
            )
            return data

        except OSError as file_error:
            logger.error(
                f"[PERSISTENCE] File read error for {resource_type.value} {resource_id}: {file_error}",
                exc_info=True,
            )
            return None
        except json.JSONDecodeError as json_error:
            logger.error(
                f"[PERSISTENCE] JSON decode error for {resource_type.value} {resource_id}: {json_error}",
                exc_info=True,
            )
            return None

    async def list_resources(
        self,
        resource_type: ResourceType,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """列出指定类型的所有资源

        Args:
            resource_type: 资源类型
            limit: 最多返回的资源数量

        Returns:
            资源列表

        """
        try:
            resource_dir = self._get_resource_dir(resource_type)
            files = list(resource_dir.glob("*.json"))

            resources = []
            for file_path in files:
                try:
                    async with aiofiles.open(file_path, encoding="utf-8") as f:
                        content = await f.read()
                        data = json.loads(content)
                        resources.append(data)

                        if limit and len(resources) >= limit:
                            break
                except OSError as file_error:
                    logger.warning(f"[PERSISTENCE] File read error for {file_path}: {file_error}")
                    continue
                except json.JSONDecodeError as json_error:
                    logger.warning(f"[PERSISTENCE] JSON decode error for {file_path}: {json_error}")
                    continue

            # 按更新时间排序(最新的在前)
            resources.sort(key=lambda r: r.get("updated_at", ""), reverse=True)

            return resources

        except WorkspacePersistenceError:
            # 已经记录了详细错误，直接向上抛出
            raise
        except Exception as e:
            logger.error(
                f"[PERSISTENCE] Unexpected error listing {resource_type.value}: {e}",
                exc_info=True,
            )
            raise WorkspacePersistenceError(f"Unexpected error listing {resource_type.value}: {e}")

    async def delete_resource(self, resource_type: ResourceType, resource_id: str) -> bool:
        """删除资源

        Args:
            resource_type: 资源类型
            resource_id: 资源ID

        Returns:
            是否删除成功

        """
        try:
            resource_dir = self._get_resource_dir(resource_type)

            # 删除所有匹配的文件(包括带时间戳的)
            files = list(resource_dir.glob(f"*_{resource_id}.json")) + list(
                resource_dir.glob(f"{resource_id}.json"),
            )

            for file_path in files:
                try:
                    file_path.unlink()
                except OSError as delete_error:
                    logger.error(
                        f"[PERSISTENCE] Failed to delete file {file_path}: {delete_error}",
                        exc_info=True,
                    )
                    continue

            logger.debug(f"[PERSISTENCE] Deleted {resource_type.value} {resource_id}")
            return True

        except WorkspacePersistenceError:
            # 已经记录了详细错误，直接向上抛出
            raise
        except Exception as e:
            logger.error(
                f"[PERSISTENCE] Unexpected error deleting {resource_type.value} {resource_id}: {e}",
                exc_info=True,
            )
            raise WorkspacePersistenceError(
                f"Unexpected error deleting {resource_type.value} {resource_id}: {e}",
            )

    def _get_resource_dir(self, resource_type: ResourceType) -> Path:
        """获取资源类型对应的目录"""
        dir_map = {
            ResourceType.CONVERSATION: self.conversations_dir,  # 使用工作区 conversations 目录
            ResourceType.TASK_GRAPH: self.task_graphs_dir,
            ResourceType.TASK_NODE: self.task_nodes_dir,
            ResourceType.CHECKPOINT: self.checkpoints_dir,  # 使用全局 checkpoints 目录
            ResourceType.WORKSPACE_SETTINGS: self.persistence_dir,
            ResourceType.WORKSPACE_INFO: self.persistence_dir,
            ResourceType.SCHEDULED_TASK: self.scheduled_tasks_dir,
        }
        return dir_map[resource_type]

    # ==================== Conversation 专用方法 ====================

    async def save_conversation(
        self,
        conversation_id: str,
        conversation_data: dict[str, Any],
    ) -> bool:
        """保存对话

        Args:
            conversation_id: 对话ID
            conversation_data: 对话数据

        Returns:
            是否保存成功

        """
        # 使用创建时间戳,确保同一对话多次保存使用相同文件名
        created_at = conversation_data.get("created_at")
        if created_at:
            try:
                timestamp = datetime.fromisoformat(created_at).strftime("%Y%m%d%H%M%S")
            except (ValueError, TypeError) as date_error:
                logger.exception(
                    f"[PERSISTENCE] Invalid date format in created_at: {created_at}, error: {date_error}",
                )
                timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        else:
            timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")

        return await self.save_resource(
            ResourceType.CONVERSATION,
            conversation_id,
            conversation_data,
            timestamp=timestamp,
            use_timestamp=False,  # 改为 False，不使用时间戳前缀
        )

    async def load_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        """加载对话"""
        return await self.load_resource(ResourceType.CONVERSATION, conversation_id)

    async def list_conversations(self, limit: int | None = None) -> list[dict[str, Any]]:
        """列出所有对话"""
        return await self.list_resources(ResourceType.CONVERSATION, limit)

    async def delete_conversation(self, conversation_id: str) -> bool:
        """删除对话"""
        return await self.delete_resource(ResourceType.CONVERSATION, conversation_id)

    # ==================== Task Graph 专用方法 ====================

    async def save_task_graph(self, graph_id: str, graph_data: dict[str, Any]) -> bool:
        """保存任务图"""
        return await self.save_resource(
            ResourceType.TASK_GRAPH,
            graph_id,
            graph_data,
            use_timestamp=False,
        )

    async def load_task_graph(self, graph_id: str) -> dict[str, Any] | None:
        """加载任务图"""
        return await self.load_resource(ResourceType.TASK_GRAPH, graph_id)

    async def list_task_graphs(self, limit: int | None = None) -> list[dict[str, Any]]:
        """列出所有任务图"""
        return await self.list_resources(ResourceType.TASK_GRAPH, limit)

    async def delete_task_graph(self, graph_id: str) -> bool:
        """删除任务图"""
        return await self.delete_resource(ResourceType.TASK_GRAPH, graph_id)

    # ==================== Checkpoint 专用方法 ====================

    async def save_checkpoint(self, checkpoint_id: str, checkpoint_data: dict[str, Any]) -> bool:
        """保存检查点"""
        return await self.save_resource(
            ResourceType.CHECKPOINT,
            checkpoint_id,
            checkpoint_data,
            use_timestamp=False,
        )

    async def load_checkpoint(self, checkpoint_id: str) -> dict[str, Any] | None:
        """加载检查点"""
        return await self.load_resource(ResourceType.CHECKPOINT, checkpoint_id)

    async def list_checkpoints(self, limit: int | None = None) -> list[dict[str, Any]]:
        """列出所有检查点"""
        return await self.list_resources(ResourceType.CHECKPOINT, limit)

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """删除检查点"""
        return await self.delete_resource(ResourceType.CHECKPOINT, checkpoint_id)

    # ==================== Workspace Settings 专用方法 ====================

    async def save_workspace_settings(self, settings: dict[str, Any]) -> bool:
        """保存workspace设置"""
        return await self.save_resource(
            ResourceType.WORKSPACE_SETTINGS,
            "workspace",
            settings,
            use_timestamp=False,
        )

    async def load_workspace_settings(self) -> dict[str, Any] | None:
        """加载workspace设置"""
        return await self.load_resource(ResourceType.WORKSPACE_SETTINGS, "workspace")
