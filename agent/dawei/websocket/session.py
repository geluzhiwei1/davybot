# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""会话管理器

负责管理WebSocket会话的状态、数据和生命周期。
"""

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from dawei.storage import Storage

logger = logging.getLogger(__name__)


@dataclass
class SessionData:
    """会话数据"""

    id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str | None = None
    workspace_id: str | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        result = asdict(self)
        # 转换日期时间为ISO字符串
        result["created_at"] = self.created_at.isoformat()
        result["updated_at"] = self.updated_at.isoformat()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionData":
        """从字典创建"""
        # 转换ISO字符串为日期时间
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)

    def update_timestamp(self):
        """更新时间戳"""
        self.updated_at = datetime.now(timezone.utc)


class SessionManager:
    """会话管理器"""

    def __init__(
        self,
        storage: Storage,
        cleanup_interval: int = 300,
        session_timeout: int = 3600,
        sessions_dir: str = "sessions",
    ):
        """初始化会话管理器

        Args:
            storage: 存储接口实例
            cleanup_interval: 清理间隔（秒）
            session_timeout: 会话超时时间（秒）
            sessions_dir: 会话存储目录

        """
        self.storage = storage
        self.sessions: dict[str, SessionData] = {}
        self.session_locks: dict[str, asyncio.Lock] = {}
        self.cleanup_interval = cleanup_interval
        self.session_timeout = session_timeout
        self.session_listeners: list[Callable] = []
        self._cleanup_task: asyncio.Task | None = None
        self._is_running = False
        self.sessions_dir = sessions_dir

    async def start(self):
        """启动会话管理器"""
        if self._is_running:
            return

        self._is_running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("会话管理器已启动")

    async def stop(self):
        """停止会话管理器"""
        if not self._is_running:
            return

        self._is_running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                # Task cancellation - expected flow, no stack trace needed
                pass

        logger.info("会话管理器已停止")

    async def create_session(
        self,
        session_id: str,
        user_id: str | None = None,
        workspace_id: str | None = None,
        conversation_id: str | None = None,
        initial_data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SessionData:
        """创建新会话

        Args:
            session_id: 会话ID
            user_id: 用户ID
            workspace_id: 工作空间ID
            conversation_id: 对话ID
            initial_data: 初始数据
            metadata: 元数据

        Returns:
            创建的会话数据

        """
        async with self._get_session_lock(session_id):
            # 检查会话是否已存在
            if session_id in self.sessions:
                logger.warning(f"会话 {session_id} 已存在，返回现有会话")
                return self.sessions[session_id]

            # 创建新会话
            session_data = SessionData(
                id=session_id,
                user_id=user_id,
                workspace_id=workspace_id,
                conversation_id=conversation_id,
                data=initial_data or {},
                metadata=metadata or {},
            )

            self.sessions[session_id] = session_data

            # 通知监听器
            await self._notify_session_listeners("create", session_id, session_data)

            logger.info(f"已创建会话: {session_id}")
            return session_data

    async def get_session(self, session_id: str) -> SessionData | None:
        """获取会话

        Args:
            session_id: 会话ID

        Returns:
            会话数据，不存在返回None

        """
        async with self._get_session_lock(session_id):
            session_data = self.sessions.get(session_id)
            if session_data:
                # 更新访问时间
                session_data.update_timestamp()
            return session_data

    async def update_session(
        self,
        session_id: str,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
        conversation_id: str | None = None,
    ) -> bool:
        """更新会话

        Args:
            session_id: 会话ID
            data: 要更新的数据
            metadata: 要更新的元数据
            user_id: 用户ID
            workspace_id: 工作空间ID
            conversation_id: 对话ID

        Returns:
            更新是否成功

        """
        async with self._get_session_lock(session_id):
            if session_id not in self.sessions:
                logger.warning(f"尝试更新不存在的会话: {session_id}")
                return False

            session_data = self.sessions[session_id]

            # 更新字段
            if data is not None:
                session_data.data.update(data)
            if metadata is not None:
                session_data.metadata.update(metadata)
            if user_id is not None:
                session_data.user_id = user_id
            if workspace_id is not None:
                session_data.workspace_id = workspace_id
            if conversation_id is not None:
                session_data.conversation_id = conversation_id

            # 更新时间戳
            session_data.update_timestamp()

            # 通知监听器
            await self._notify_session_listeners("update", session_id, session_data)

            logger.debug(f"已更新会话: {session_id}")
            return True

    async def delete_session(self, session_id: str) -> bool:
        """删除会话

        Args:
            session_id: 会话ID

        Returns:
            删除是否成功

        """
        async with self._get_session_lock(session_id):
            if session_id not in self.sessions:
                logger.warning(f"尝试删除不存在的会话: {session_id}")
                return False

            session_data = self.sessions.pop(session_id)

            # 清理锁
            if session_id in self.session_locks:
                del self.session_locks[session_id]

            # 通知监听器
            await self._notify_session_listeners("delete", session_id, session_data)

            logger.info(f"已删除会话: {session_id}")
            return True

    async def get_session_data(self, session_id: str, key: str, default: Any = None) -> Any:
        """获取会话数据中的指定键值

        Args:
            session_id: 会话ID
            key: 数据键
            default: 默认值

        Returns:
            数据值

        """
        session_data = await self.get_session(session_id)
        if session_data:
            return session_data.data.get(key, default)
        return default

    async def set_session_data(self, session_id: str, key: str, value: Any) -> bool:
        """设置会话数据中的指定键值

        Args:
            session_id: 会话ID
            key: 数据键
            value: 数据值

        Returns:
            设置是否成功

        """
        return await self.update_session(session_id, data={key: value})

    async def get_session_metadata(self, session_id: str, key: str, default: Any = None) -> Any:
        """获取会话元数据中的指定键值

        Args:
            session_id: 会话ID
            key: 元数据键
            default: 默认值

        Returns:
            元数据值

        """
        session_data = await self.get_session(session_id)
        if session_data:
            return session_data.metadata.get(key, default)
        return default

    async def set_session_metadata(self, session_id: str, key: str, value: Any) -> bool:
        """设置会话元数据中的指定键值

        Args:
            session_id: 会话ID
            key: 元数据键
            value: 元数据值

        Returns:
            设置是否成功

        """
        return await self.update_session(session_id, metadata={key: value})

    async def get_sessions_by_user(self, user_id: str) -> list[SessionData]:
        """获取指定用户的所有会话

        Args:
            user_id: 用户ID

        Returns:
            会话列表

        """
        sessions = []
        for session_data in self.sessions.values():
            if session_data.user_id == user_id:
                sessions.append(session_data)
        return sessions

    async def get_sessions_by_workspace(self, workspace_id: str) -> list[SessionData]:
        """获取指定工作空间的所有会话

        Args:
            workspace_id: 工作空间ID

        Returns:
            会话列表

        """
        sessions = []
        for session_data in self.sessions.values():
            if session_data.workspace_id == workspace_id:
                sessions.append(session_data)
        return sessions

    async def get_all_sessions(self) -> list[SessionData]:
        """获取所有会话

        Returns:
            会话列表

        """
        return list(self.sessions.values())

    async def get_session_count(self) -> int:
        """获取会话总数

        Returns:
            会话总数

        """
        return len(self.sessions)

    async def cleanup_expired_sessions(self):
        """清理过期会话"""
        current_time = datetime.now(timezone.utc)

        for session_id, session_data in list(self.sessions.items()):
            # 确保updated_at是timezone-aware以便比较
            updated_at = session_data.updated_at
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)

            # 检查会话是否超时
            time_diff = current_time - updated_at
            if time_diff.total_seconds() > self.session_timeout:
                await self.delete_session(session_id)
                logger.info(f"已清理超时会话: {session_id}")

    def add_session_listener(self, listener: Callable):
        """添加会话事件监听器

        Args:
            listener: 监听器函数

        """
        self.session_listeners.append(listener)

    def remove_session_listener(self, listener: Callable):
        """移除会话事件监听器

        Args:
            listener: 监听器函数

        """
        if listener in self.session_listeners:
            self.session_listeners.remove(listener)

    async def _notify_session_listeners(
        self,
        event: str,
        session_id: str,
        session_data: SessionData,
    ):
        """通知会话监听器

        INTENTIONAL TOLERANCE: External user callbacks should never crash the system.
        One bad listener shouldn't break notification for all other listeners.
        """
        for listener in self.session_listeners:
            try:
                await listener(event, session_id, session_data)
            except (
                TypeError,
                AttributeError,
                RuntimeError,
                asyncio.CancelledError,
            ) as e:
                # Specific errors from user callbacks - log but continue notifying others
                logger.error(f"会话监听器执行失败: {e}", exc_info=True)
            except Exception as e:
                # Unexpected error from user callback - log but continue (graceful degradation)
                logger.critical(f"会话监听器出现未预期的异常: {e}", exc_info=True)

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """获取会话锁"""
        if session_id not in self.session_locks:
            self.session_locks[session_id] = asyncio.Lock()
        return self.session_locks[session_id]

    async def _cleanup_loop(self):
        """清理循环

        INTENTIONAL TOLERANCE: Background loop must never crash.
        One cleanup failure shouldn't stop the entire background task.
        """
        while self._is_running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self.cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except (OSError, PermissionError, KeyError, ValueError) as e:
                # Expected cleanup errors - log and continue loop
                logger.error(f"清理过期会话时出错: {e}", exc_info=True)
            except Exception as e:
                # Unexpected cleanup error - log but continue (graceful degradation)
                logger.critical(f"清理循环出现未预期的异常: {e}", exc_info=True)

    async def save_session_to_storage(self, session_id: str) -> bool:
        """保存会话到持久化存储

        Args:
            session_id: 会话ID

        Returns:
            保存是否成功

        Raises:
            ValueError: If session data is invalid
            OSError: If storage write fails
            PermissionError: If lacks write permissions

        """
        session_data = await self.get_session(session_id)
        if not session_data:
            logger.warning(f"尝试保存不存在的会话: {session_id}")
            return False

        try:
            # 确保会话目录存在
            await self.storage.create_directory(self.sessions_dir)

            # 构建文件路径
            session_file = f"{self.sessions_dir}/{session_id}.json"

            # 序列化会话数据为 JSON
            session_json = json.dumps(session_data.to_dict(), ensure_ascii=False, indent=2)

            # 写入存储
            await self.storage.write_file(session_file, session_json)

            logger.debug(f"成功保存会话到存储: {session_id}")
            return True
        except (TypeError, ValueError) as e:
            # Session data serialization error - fast fail
            logger.error(f"会话数据序列化失败 {session_id}: {e}", exc_info=True)
            raise ValueError(f"Invalid session data for {session_id}: {e}")
        except (OSError, PermissionError) as e:
            # Storage I/O error - fast fail
            logger.error(f"存储写入失败 {session_id}: {e}", exc_info=True)
            raise

    async def load_session_from_storage(self, session_id: str) -> SessionData | None:
        """从持久化存储加载会话

        Args:
            session_id: 会话ID

        Returns:
            加载的会话数据，失败返回None

        Raises:
            ValueError: If session data is invalid
            OSError: If storage read fails
            PermissionError: If lacks read permissions

        """
        try:
            # 构建文件路径
            session_file = f"{self.sessions_dir}/{session_id}.json"

            # 检查文件是否存在
            if not await self.storage.exists(session_file):
                logger.debug(f"会话文件不存在: {session_file}")
                return None

            # 从存储读取 JSON
            session_json = await self.storage.read_file(session_file)

            # 反序列化为会话数据
            session_dict = json.loads(session_json)
            session_data = SessionData.from_dict(session_dict)

            logger.debug(f"成功从存储加载会话: {session_id}")
            return session_data
        except json.JSONDecodeError as e:
            # Invalid JSON format - fast fail
            logger.error(f"解析会话 JSON 失败 {session_id}: {e}", exc_info=True)
            raise ValueError(f"Invalid session JSON for {session_id}: {e}")
        except (TypeError, ValueError) as e:
            # Session data validation error - fast fail
            logger.error(f"会话数据验证失败 {session_id}: {e}", exc_info=True)
            raise ValueError(f"Invalid session data for {session_id}: {e}")
        except (OSError, PermissionError) as e:
            # Storage I/O error - fast fail
            logger.error(f"存储读取失败 {session_id}: {e}", exc_info=True)
            raise
