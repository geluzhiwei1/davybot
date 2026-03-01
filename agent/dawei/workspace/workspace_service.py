# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工作区服务（每个 workspace_id 一个单例）

设计原则：
1. 每个 workspace_id 对应一个 WorkspaceContext
2. WorkspaceContext 管理共享资源（工具、持久化、配置）
3. UserWorkspace 引用 WorkspaceContext，持有请求级状态
4. 使用引用计数自动清理未使用的上下文
"""

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import ClassVar

from dawei.llm_api.llm_provider import LLMProvider
from dawei.task_graph.persistence_manager import TaskGraphPersistenceManager
from dawei.tools.tool_manager import ToolManager

from .persistence_manager import WorkspacePersistenceManager
from .user_workspace import WorkspaceSettings

logger = logging.getLogger(__name__)


class WorkspaceContext:
    """工作区上下文（每个 workspace_id 一个单例）

    职责：
    - 管理共享资源（工具、LLM、持久化服务）
    - 生命周期由引用计数管理
    - 线程安全（使用 asyncio.Lock）

    共享资源：
    - tool_manager: 工具管理器（4层配置加载）
    - llm_manager: LLM 提供者（模型切换）
    - persistence_manager: 持久化管理器（文件读写）
    - task_graph_persistence_manager: TaskGraph 自动保存服务
    - workspace_settings: 工作区配置
    - conversation_history_manager: 对话历史管理器
    """

    def __init__(self, workspace_path: str):
        self.workspace_path = Path(workspace_path).resolve()
        self.absolute_path = str(self.workspace_path)
        self.workspace_id = self.absolute_path  # 使用路径作为唯一标识

        # 共享资源（延迟初始化）
        self.tool_manager: ToolManager | None = None
        self.mcp_tool_manager = None
        self.llm_manager: LLMProvider | None = None
        self.workspace_settings: WorkspaceSettings | None = None
        self.conversation_history_manager = None
        self.task_graph_persistence_manager: TaskGraphPersistenceManager | None = None
        self.persistence_manager: WorkspacePersistenceManager | None = None

        # 生命周期管理
        self._initialized = False
        self._ref_count = 0  # 引用计数
        self._lock = asyncio.Lock()

        logger.debug(f"WorkspaceContext created: {self.workspace_id}")

    @classmethod
    def get_id_from_path(cls, workspace_path: str) -> str:
        """从路径获取 workspace_id"""
        return str(Path(workspace_path).resolve())

    async def initialize(self):
        """初始化共享资源（只执行一次）

        线程安全：使用 asyncio.Lock 保证只初始化一次
        """
        async with self._lock:
            if self._initialized:
                return

            logger.info(f"Initializing WorkspaceContext: {self.workspace_id}")

            try:
                # 1. 初始化持久化管理器
                self.persistence_manager = WorkspacePersistenceManager(self.absolute_path)
                logger.info(f"  ✓ PersistenceManager initialized: {self.absolute_path}")

                # 2. 初始化工具管理器（4层配置加载）
                self.tool_manager = ToolManager(workspace_path=self.absolute_path)
                # 注意：不需要显式加载配置，ToolManager 会自动加载
                logger.info("  ✓ ToolManager initialized")

                # 3. 初始化 LLM 管理器
                self.llm_manager = LLMProvider(workspace_path=self.absolute_path)
                # LLMProvider 在 __init__ 中自动加载配置
                logger.info("  ✓ LLMManager initialized")

                # 4. 初始化 TaskGraph 持久化管理器（关键修复点）
                self.task_graph_persistence_manager = TaskGraphPersistenceManager(
                    workspace_path=self.absolute_path,
                    event_bus=None,  # CORE_EVENT_BUS removed
                    debounce_seconds=1.0,
                )
                await self.task_graph_persistence_manager.start()
                logger.info("  ✓ TaskGraphPersistenceManager started")

                # 5. 加载工作区配置
                self.workspace_settings = await self._load_settings()
                logger.info("  ✓ WorkspaceSettings loaded")

                # 6. 初始化对话历史管理器
                from dawei.conversation.conversation_history_manager import (
                    ConversationHistoryManager,
                )

                self.conversation_history_manager = ConversationHistoryManager(
                    workspace_path=self.absolute_path,
                )
                logger.info("  ✓ ConversationHistoryManager initialized")

                self._initialized = True
                logger.info(f"✓ WorkspaceContext fully initialized: {self.workspace_id}")

            except Exception as e:
                logger.error(
                    f"Failed to initialize WorkspaceContext {self.workspace_id}: {e}",
                    exc_info=True,
                )
                # 清理已初始化的资源
                await self._cleanup_partial()
                raise

    async def _load_settings(self) -> WorkspaceSettings | None:
        """加载工作区配置"""
        try:
            # ✅ 修复：使用 ResourceType 枚举而不是字符串
            from dawei.workspace.persistence_manager import ResourceType

            settings_data = await self.persistence_manager.load_resource(
                ResourceType.WORKSPACE_SETTINGS,
                "settings"
            )
            if settings_data:
                return WorkspaceSettings.from_dict(settings_data)
        except Exception as e:
            logger.warning(f"Failed to load workspace settings: {e}")
        return WorkspaceSettings()

    async def retain(self):
        """增加引用计数"""
        self._ref_count += 1
        logger.debug(f"WorkspaceContext {self.workspace_id} ref_count: {self._ref_count}")
        return self

    async def release(self):
        """减少引用计数，当计数为0时清理资源

        这是解决资源泄漏的关键方法！
        """
        self._ref_count -= 1
        logger.debug(f"WorkspaceContext {self.workspace_id} ref_count: {self._ref_count}")

        if self._ref_count <= 0:
            logger.info(f"WorkspaceContext {self.workspace_id} has no references, cleaning up...")
            await self._cleanup()

    async def _cleanup(self):
        """清理共享资源（解决资源泄漏的关键）"""
        logger.info(f"Cleaning up WorkspaceContext: {self.workspace_id}")

        try:
            # 1. ⭐ 停止 TaskGraph 持久化管理器（关键修复！）
            if self.task_graph_persistence_manager:
                try:
                    await self.task_graph_persistence_manager.stop()
                    logger.info(f"  ✓ TaskGraphPersistenceManager stopped: {self.workspace_id}")
                except Exception:
                    logger.exception("  ✗ Error stopping TaskGraphPersistenceManager: ")

            # 2. 清理对话历史管理器
            if self.conversation_history_manager:
                try:
                    await self.conversation_history_manager.cleanup()
                    logger.info("  ✓ ConversationHistoryManager stopped")
                except Exception:
                    logger.exception("  ✗ Error stopping ConversationHistoryManager: ")

            # 3. 清理 LLM 管理器
            if self.llm_manager:
                try:
                    await self.llm_manager.cleanup()
                    logger.info("  ✓ LLMManager stopped")
                except Exception:
                    logger.exception("  ✗ Error stopping LLMManager: ")

            # 4. 清理工具管理器
            if self.tool_manager:
                try:
                    await self.tool_manager.cleanup()
                    logger.info("  ✓ ToolManager stopped")
                except Exception:
                    logger.exception("  ✗ Error stopping ToolManager: ")

            # 注意：不要设置 self._initialized = False
            # 因为 context 仍然存在，可以被重新激活（新的ref_count）
            logger.info(f"✓ WorkspaceContext cleaned up: {self.workspace_id}")

        except Exception as e:
            logger.error(f"Error during WorkspaceContext cleanup: {e}", exc_info=True)

    async def _cleanup_partial(self):
        """清理部分初始化的资源（初始化失败时调用）"""
        if self.task_graph_persistence_manager:
            with contextlib.suppress(Exception):
                await self.task_graph_persistence_manager.stop()

    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized

    @property
    def ref_count(self) -> int:
        """获取引用计数"""
        return self._ref_count

    def __repr__(self) -> str:
        return f"WorkspaceContext(id={self.workspace_id}, refs={self._ref_count}, initialized={self._initialized})"


class WorkspaceService:
    """工作区服务（全局单例，管理多个 WorkspaceContext）

    职责：
    - 为每个 workspace_id 维护一个 WorkspaceContext
    - 提供获取和释放上下文的接口
    - 使用弱引用字典自动清理

    使用方式：
        # 获取上下文
        context = await WorkspaceService.get_context("/path/to/workspace")

        # 使用上下文
        tool_manager = context.tool_manager

        # 释放上下文（引用计数-1）
        await context.release()
    """

    # 类变量：所有工作区上下文（使用强引用保持活跃）
    _contexts: ClassVar[dict[str, WorkspaceContext]] = {}
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    @classmethod
    async def get_context(cls, workspace_path: str) -> WorkspaceContext:
        """获取工作区上下文（每个 workspace_id 一个单例）

        Args:
            workspace_path: 工作区路径

        Returns:
            WorkspaceContext: 工作区上下文（引用计数+1）

        Example:
            >>> context = await WorkspaceService.get_context("/path/to/workspace")
            >>> # 使用 context.tool_manager, context.llm_manager 等
            >>> await context.release()  # 使用完毕后释放
        """
        workspace_id = WorkspaceContext.get_id_from_path(workspace_path)

        # 检查是否已存在
        logger.debug(f"get_context() called for {workspace_id}")
        logger.debug(f"  Existing contexts: {list(cls._contexts.keys())}")

        if workspace_id in cls._contexts:
            context = cls._contexts[workspace_id]
            logger.debug(f"  Found existing context: {context}")
            logger.debug(f"  is_initialized: {context.is_initialized()}")
            if context is not None and context.is_initialized():
                await context.retain()
                logger.debug(f"Reusing existing WorkspaceContext: {workspace_id} (refs={context.ref_count})")
                return context
            logger.debug("  Context exists but not initialized, will create new")
        else:
            logger.debug("  Context not found in dict, will create new")

        # 创建新实例（双重检查锁）
        async with cls._lock:
            # 再次检查（可能在等待锁时已被其他协程创建）
            if workspace_id in cls._contexts:
                context = cls._contexts[workspace_id]
                if context is not None and context.is_initialized():
                    await context.retain()
                    logger.debug(f"Reusing existing WorkspaceContext (after lock): {workspace_id}")
                    return context

            # 创建并初始化新上下文
            logger.info(f"Creating new WorkspaceContext: {workspace_id}")
            context = WorkspaceContext(workspace_path)
            await context.initialize()

            # 保存到弱引用字典
            cls._contexts[workspace_id] = context
            await context.retain()  # 初始引用计数

            logger.info(f"✓ New WorkspaceContext registered: {workspace_id} (refs={context.ref_count})")
            return context

    @classmethod
    async def remove_context(cls, workspace_id: str):
        """强制移除工作区上下文（谨慎使用）

        用于工作区删除等场景

        Args:
            workspace_id: 工作区ID
        """
        async with cls._lock:
            if workspace_id in cls._contexts:
                context = cls._contexts[workspace_id]
                if context:
                    await context._cleanup()
                del cls._contexts[workspace_id]
                logger.info(f"WorkspaceContext removed: {workspace_id}")

    @classmethod
    def get_all_contexts(cls) -> dict[str, WorkspaceContext]:
        """获取所有活跃的工作区上下文（用于监控）"""
        return dict(cls._contexts)

    @classmethod
    async def cleanup_all(cls):
        """清理所有工作区上下文（应用关闭时调用）"""
        logger.info("Cleaning up all WorkspaceContexts...")
        for _workspace_id, context in list(cls._contexts.items()):
            if context:
                await context._cleanup()
        cls._contexts.clear()
        logger.info("All WorkspaceContexts cleaned up")
