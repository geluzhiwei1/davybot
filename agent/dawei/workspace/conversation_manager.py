# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Workspace对话管理器

负责工作区的对话创建、加载、保存、删除和查询
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dawei.conversation.conversation import Conversation, create_conversation
from dawei.conversation.conversation_history_manager import ConversationHistoryManager
from dawei.workspace.exceptions import ConversationPersistenceError

if TYPE_CHECKING:
    from dawei.workspace.persistence_manager import WorkspacePersistenceManager


logger = logging.getLogger(__name__)


class WorkspaceConversationManager:
    """工作区对话管理器

    职责：
    - 初始化和管理对话历史管理器
    - 对话的创建、加载、保存、删除
    - 对话列表和搜索
    - 当前对话管理
    """

    def __init__(self, workspace_path: Path):
        """初始化对话管理器

        Args:
            workspace_path: 工作区路径

        """
        self.workspace_path = Path(workspace_path).resolve()
        self.absolute_path = str(self.workspace_path)

        # 对话历史管理器
        self.conversation_history_manager: ConversationHistoryManager | None = None

        # 持久化管理器（由外部注入）
        self.persistence_manager: WorkspacePersistenceManager | None = None

        # LLM提供者（由外部注入，用于获取当前配置）
        self.llm_provider = None

        # 当前对话
        self.current_conversation: Conversation | None = None

        logger.info(f"WorkspaceConversationManager created for: {self.absolute_path}")

    # ==================== 初始化方法 ====================

    async def initialize(self, persistence_manager=None, llm_provider=None):
        """初始化对话管理器

        Args:
            persistence_manager: 持久化管理器（可选）
            llm_provider: LLM提供者（可选）

        """
        self.persistence_manager = persistence_manager
        self.llm_provider = llm_provider

        # 初始化对话历史管理器
        logger.info("Initializing conversation history manager...")
        self.conversation_history_manager = ConversationHistoryManager(
            workspace_path=self.absolute_path,
        )

        # 从目录构建对话历史
        try:
            await self.conversation_history_manager.build_from_dir()
        except Exception as e:
            logger.warning(f"Failed to build conversation history from directory: {e}")
            # 创建一个空的对话历史管理器
            self.conversation_history_manager = ConversationHistoryManager(
                workspace_path=self.absolute_path,
            )

        # 如果没有当前对话，创建一个新的
        if self.current_conversation is None:
            current_llm_config = self._get_current_llm_config()
            self.current_conversation = create_conversation(
                title="新对话",
                agent_mode="orchestrator",  # 默认使用orchestrator模式
                llm_model=current_llm_config or "glm",
            )

        logger.info("Conversation management initialized successfully.")

    def _get_current_llm_config(self) -> str:
        """获取当前LLM配置名称"""
        if self.llm_provider:
            return self.llm_provider.get_current_config_name()
        return "glm"

    # ==================== 对话CRUD操作 ====================

    async def new_conversation(
        self,
        title: str = "新对话",
        agent_mode: str = "orchestrator",
    ) -> Conversation:
        """创建新对话并设置为当前对话

        Args:
            title: 对话标题
            agent_mode: 代理模式

        Returns:
            Conversation: 新创建的对话

        """
        # 保存当前对话到历史（如果有消息）
        if self.current_conversation and self.current_conversation.message_count > 0:
            try:
                await self.save_current_conversation()
            except ConversationPersistenceError as e:
                logger.warning(f"Failed to save current conversation before creating new: {e}")
                # 继续执行，不阻止创建新对话

        # 创建新对话
        current_llm_config = self._get_current_llm_config()
        self.current_conversation = create_conversation(
            title=title,
            agent_mode=agent_mode,
            llm_model=current_llm_config or "glm",
        )

        logger.info(f"Created new conversation: {title}")
        return self.current_conversation

    async def save_current_conversation(self) -> bool:
        """保存当前对话到历史 (使用持久化管理器)

        Returns:
            bool: 保存是否成功

        Raises:
            PersistenceError: 当持久化管理器不可用时
            ConversationPersistenceError: 当对话保存失败时

        """
        logger.info("[SAVE_CONVERSATION] Starting save for conversation")

        if not self.current_conversation:
            raise ConversationPersistenceError(
                "current_conversation is None",
                conversation_id="unknown",
            )

        if not self.conversation_history_manager:
            raise ConversationPersistenceError(
                "conversation_history_manager is None",
                conversation_id="unknown",
            )

        logger.info(
            f"[SAVE_CONVERSATION] Conversation details: id={self.current_conversation.id}, message_count={self.current_conversation.message_count}",
        )

        # 首先尝试使用持久化管理器保存
        if self.persistence_manager:
            # 将对话转换为字典格式
            conversation_dict = self._conversation_to_dict(self.current_conversation)

            success = await self.persistence_manager.save_conversation(
                self.current_conversation.id,
                conversation_dict,
            )

            if success:
                logger.info(
                    f"[SAVE_CONVERSATION] Successfully saved conversation via persistence manager: {self.current_conversation.id}",
                )
                return True
            logger.warning(
                "[SAVE_CONVERSATION] Persistence manager save failed, falling back to conversation_history_manager",
            )

        # 回退到对话历史管理器
        success = await self.conversation_history_manager.save_by_id(
            self.current_conversation.id,
            self.current_conversation,
        )

        if success:
            logger.info(
                f"[SAVE_CONVERSATION] Successfully saved conversation via history manager: {self.current_conversation.id}",
            )
        else:
            logger.error(
                f"[SAVE_CONVERSATION] Failed to save conversation: {self.current_conversation.id}",
            )

        return success

    async def load_conversation(self, conversation_id: str) -> bool:
        """加载指定对话作为当前对话

        Args:
            conversation_id: 对话ID

        Returns:
            bool: 加载是否成功

        Raises:
            ConversationPersistenceError: 当对话历史管理器不可用时
            ConversationPersistenceError: 当对话加载失败时

        """
        if not self.conversation_history_manager:
            raise ConversationPersistenceError(
                "conversation_history_manager is None",
                conversation_id=conversation_id,
            )

        # 先保存当前对话
        if self.current_conversation and self.current_conversation.message_count > 0:
            try:
                await self.save_current_conversation()
            except ConversationPersistenceError as e:
                logger.warning(f"Failed to save current conversation before loading: {e}")
                # 继续执行，不阻止加载新对话

        # 加载指定对话
        conversation = await self.conversation_history_manager.get_by_id(conversation_id)
        if conversation:
            self.current_conversation = conversation
            logger.info(f"Loaded conversation: {conversation_id}")
            return True
        raise ConversationPersistenceError(
            f"Conversation not found: {conversation_id}",
            conversation_id=conversation_id,
        )

    async def delete_conversation(self, conversation_id: str) -> bool:
        """删除指定对话

        Args:
            conversation_id: 对话ID

        Returns:
            bool: 删除是否成功

        Raises:
            ConversationPersistenceError: 当对话历史管理器不可用时
            ConversationPersistenceError: 当对话删除失败时

        """
        if not self.conversation_history_manager:
            raise ConversationPersistenceError(
                "conversation_history_manager is None",
                conversation_id=conversation_id,
            )

        success = await self.conversation_history_manager.delete_by_id(conversation_id)
        if success:
            # 如果删除的是当前对话，创建新对话
            if self.current_conversation and self.current_conversation.id == conversation_id:
                current_llm_config = self._get_current_llm_config()
                self.current_conversation = create_conversation(
                    title="新对话",
                    agent_mode="orchestrator",  # 使用orchestrator作为默认模式
                    llm_model=current_llm_config or "glm",
                )
            logger.info(f"Deleted conversation: {conversation_id}")
        else:
            raise ConversationPersistenceError(
                f"Failed to delete conversation: {conversation_id}",
                conversation_id=conversation_id,
            )

        return success

    # ==================== 对话查询方法 ====================

    async def get_conversation_list(self) -> list[Conversation]:
        """获取对话历史列表

        Returns:
            List[Conversation]: 对话列表

        Raises:
            ConversationPersistenceError: 当对话历史管理器不可用时

        """
        if not self.conversation_history_manager:
            raise ConversationPersistenceError(
                "conversation_history_manager is None",
                conversation_id="unknown",
            )

        return await self.conversation_history_manager.list_all()

    async def search_conversations(
        self,
        query: str,
        search_in_content: bool = False,
    ) -> list[Conversation]:
        """搜索对话

        Args:
            query: 搜索关键词
            search_in_content: 是否在消息内容中搜索

        Returns:
            List[Conversation]: 匹配的对话列表

        Raises:
            ConversationPersistenceError: 当对话历史管理器不可用时

        """
        if not self.conversation_history_manager:
            raise ConversationPersistenceError(
                "conversation_history_manager is None",
                conversation_id="unknown",
            )

        return await self.conversation_history_manager.search(
            query=query,
            search_in_content=search_in_content,
        )

    # ==================== 当前对话访问 ====================

    def get_current_conversation(self) -> Conversation | None:
        """获取当前对话

        Returns:
            当前对话对象，如果未初始化则返回None

        """
        return self.current_conversation

    # ==================== 辅助方法 ====================

    def _conversation_to_dict(self, conversation: Conversation) -> dict[str, Any]:
        """将对话对象转换为字典格式"""
        # 处理时间戳 - 确保是字符串格式
        created_at = conversation.created_at
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()
        elif created_at is None:
            created_at = datetime.now(timezone.utc).isoformat()

        updated_at = conversation.updated_at
        if isinstance(updated_at, datetime):
            updated_at = updated_at.isoformat()
        elif updated_at is None:
            updated_at = datetime.now(timezone.utc).isoformat()

        # 正确序列化消息 - 使用 pydantic 的 model_dump
        messages_data = []
        for msg in conversation.messages:
            # 使用 model_dump 而不是 to_dict,避免格式转换问题
            if hasattr(msg, "model_dump"):
                # Pydantic v2
                msg_dict = msg.model_dump(exclude_none=True)
            elif hasattr(msg, "dict"):
                # Pydantic v1
                msg_dict = msg.dict(exclude_none=True)
            else:
                # 回退到 to_dict
                msg_dict = msg.to_dict()

            # 确保 content 字段是字符串格式(处理OpenAI格式的content对象)
            if "content" in msg_dict and isinstance(msg_dict["content"], dict):
                # OpenAI格式: {"type": "text", "text": "..."}
                if msg_dict["content"].get("type") == "text":
                    msg_dict["content"] = msg_dict["content"].get("text", "")
                else:
                    # 其他类型,转为JSON字符串
                    msg_dict["content"] = json.dumps(msg_dict["content"])

            messages_data.append(msg_dict)

        return {
            "id": conversation.id,
            "title": conversation.title,
            "agent_mode": conversation.agent_mode,
            "llm_model": conversation.llm_model,
            "created_at": created_at,
            "updated_at": updated_at,
            "messages": messages_data,
            "message_count": conversation.message_count,
        }
