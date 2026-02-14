# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""对话历史管理器 (重构版)

负责管理多个对话对象的生命周期，包括：
- 从持久化存储加载对话
- 对话的增删改查
- 对话的持久化存储

重构说明:
- 移除对 Storage 抽象层的依赖
- 直接使用 WorkspacePersistenceManager
- 简化代码结构,提高可维护性
"""

import logging
from pathlib import Path

from dawei.workspace.persistence_manager import WorkspacePersistenceManager

from .conversation import Conversation

logger = logging.getLogger(__name__)


class ConversationHistoryManager:
    """对话历史管理器 (重构版)

    持有0或多个Conversation对象，提供对话的CRUD操作
    使用 WorkspacePersistenceManager 进行统一的持久化管理
    """

    def __init__(self, workspace_path: str | None = None, history_dir: str | None = None):
        """初始化对话历史管理器

        Args:
            workspace_path: workspace根目录路径 (优先使用)
            history_dir: 历史目录路径 (向后兼容,将被弃用)

        Note:
            history_dir参数仅用于向后兼容,新代码应使用workspace_path

        """
        # 优先使用 workspace_path，如果没有则使用 history_dir
        if workspace_path is None and history_dir is None:
            raise ValueError("Either workspace_path or history_dir must be provided")

        # 如果只提供了 history_dir，需要从它推导出 workspace_path
        if workspace_path is None and history_dir is not None:
            # history_dir 通常是 workspace/chat-history 或类似路径
            # 我们需要向上查找 workspace 根目录
            history_path = Path(history_dir)
            # 假设 history_dir 是 workspace 的直接子目录
            workspace_path = str(history_path.parent)
            # 验证推导出的路径是否有效
            if not Path(workspace_path).exists():
                raise ValueError(
                    f"Invalid workspace path derived from history_dir: {workspace_path}",
                )

        self.workspace_path = workspace_path
        self.persistence_manager = WorkspacePersistenceManager(workspace_path)
        self._conversations: dict[str, Conversation] = {}  # 内存中的对话缓存
        self._loaded = False  # 是否已从磁盘加载

    async def build_from_dir(self, force_reload: bool = False) -> int:
        """从持久化存储加载对话

        Args:
            force_reload: 是否强制重新加载

        Returns:
            加载的对话数量

        """
        if self._loaded and not force_reload:
            return len(self._conversations)

        # 清空现有缓存
        self._conversations.clear()

        try:
            # 从持久化管理器加载所有对话
            conversations_data = await self.persistence_manager.list_conversations()

            loaded_count = 0
            for conv_data in conversations_data:
                try:
                    conversation = Conversation.from_dict(conv_data)
                    self._conversations[conversation.id] = conversation
                    loaded_count += 1
                except Exception as e:
                    logger.warning(f"Failed to load conversation: {e}")
                    continue

            self._loaded = True
            logger.info(f"Loaded {loaded_count} conversations from workspace")
            return loaded_count

        except Exception as e:
            logger.error(f"Failed to load conversations: {e}", exc_info=True)
            return 0

    async def list_all(self, include_empty: bool = False) -> list[Conversation]:
        """列出所有对话

        Args:
            include_empty: 是否包含空对话（无消息的对话）

        Returns:
            对话列表

        """
        if not self._loaded:
            await self.build_from_dir()

        conversations = list(self._conversations.values())

        if not include_empty:
            conversations = [c for c in conversations if c.message_count > 0]

        # 按更新时间排序(最新的在前)
        conversations.sort(key=lambda c: c.updated_at or c.created_at, reverse=True)

        return conversations

    async def get_by_id(self, conversation_id: str) -> Conversation | None:
        """根据ID获取对话

        Args:
            conversation_id: 对话ID (可以是纯UUID,也可以是timestamp_UUID格式)

        Returns:
            对话对象,如果不存在则返回None

        """
        if not self._loaded:
            await self.build_from_dir()

        # 处理两种ID格式:
        # 1. 纯UUID: "9d5e32db-13d7-493d-8315-0e135f8ebc2a"
        # 2. timestamp_UUID: "20251228184902_9d5e32db-13d7-493d-8315-0e135f8ebc2a"
        # 如果包含下划线,提取UUID部分
        lookup_id = conversation_id
        if "_" in conversation_id:
            parts = conversation_id.split("_", 1)
            if len(parts) > 1:
                lookup_id = parts[1]
                logger.debug(
                    f"Extracted UUID '{lookup_id}' from conversation ID '{conversation_id}'",
                )
            else:
                logger.warning(f"Invalid conversation ID format: {conversation_id}")
                return None

        return self._conversations.get(lookup_id)

    async def save_by_id(
        self,
        conversation_id: str,
        conversation: Conversation | None = None,
    ) -> bool:
        """保存对话

        Args:
            conversation_id: 对话ID
            conversation: 对话对象，如果为None则从缓存中获取

        Returns:
            是否保存成功

        """
        try:
            # 获取要保存的对话对象
            if conversation is None:
                conversation = self._conversations.get(conversation_id)
                if conversation is None:
                    logger.error(f"Conversation not found: {conversation_id}")
                    return False
            # 确保ID匹配
            elif conversation.id != conversation_id:
                logger.warning(
                    f"Updating conversation ID from {conversation.id} to {conversation_id}",
                )
                conversation.id = conversation_id

            # 转换为字典格式
            conversation_data = conversation.to_dict()

            # 使用持久化管理器保存
            success = await self.persistence_manager.save_conversation(
                conversation_id,
                conversation_data,
            )

            if success:
                # 更新内存缓存
                self._conversations[conversation_id] = conversation
                logger.info(
                    f"Saved conversation {conversation_id} with {conversation.message_count} messages",
                )
            else:
                logger.error(f"Failed to save conversation {conversation_id}")

            return success

        except Exception as e:
            logger.error(f"Error saving conversation {conversation_id}: {e}", exc_info=True)
            return False

    async def delete_by_id(self, conversation_id: str) -> bool:
        """删除对话

        Args:
            conversation_id: 对话ID (可以是纯UUID,也可以是timestamp_UUID格式)

        Returns:
            是否删除成功

        """
        try:
            # 处理两种ID格式 (与get_by_id相同逻辑)
            lookup_id = conversation_id
            if "_" in conversation_id:
                parts = conversation_id.split("_", 1)
                if len(parts) > 1:
                    lookup_id = parts[1]
                    logger.debug(
                        f"Extracted UUID '{lookup_id}' from conversation ID '{conversation_id}' for deletion",
                    )
                else:
                    logger.warning(
                        f"Invalid conversation ID format for deletion: {conversation_id}",
                    )
                    return False

            # 从持久化存储删除
            success = await self.persistence_manager.delete_conversation(lookup_id)

            if success:
                # 从内存缓存删除
                if lookup_id in self._conversations:
                    del self._conversations[lookup_id]
                logger.info(f"Deleted conversation {lookup_id}")
            else:
                logger.error(f"Failed to delete conversation {lookup_id}")

            return success

        except Exception as e:
            logger.error(f"Error deleting conversation {conversation_id}: {e}", exc_info=True)
            return False

    async def add_conversation(self, conversation: Conversation) -> bool:
        """添加新对话

        Args:
            conversation: 对话对象

        Returns:
            是否添加成功

        """
        return await self.save_by_id(conversation.id, conversation)

    async def update_conversation(self, conversation: Conversation) -> bool:
        """更新对话

        Args:
            conversation: 对话对象

        Returns:
            是否更新成功

        """
        return await self.save_by_id(conversation.id, conversation)

    def get_conversation_count(self) -> int:
        """获取对话数量

        Returns:
            对话数量

        """
        return len(self._conversations)

    async def cleanup(self) -> bool:
        """清理资源（WorkspaceContext销毁时调用）

        Returns:
            是否清理成功

        """
        try:
            # 清空内存缓存
            self._conversations.clear()
            self._loaded = False

            # 清理持久化管理器（如果它有cleanup方法）
            if hasattr(self.persistence_manager, "cleanup"):
                await self.persistence_manager.cleanup()

            logger.info("ConversationHistoryManager cleaned up successfully")
            return True

        except Exception as e:
            logger.error(f"Error cleaning up ConversationHistoryManager: {e}", exc_info=True)
            return False
