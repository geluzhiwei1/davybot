# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from dawei.entity.lm_messages import (
    AssistantMessage,
    LLMMessage,
    MessageRole,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from dawei.logg.logging import get_logger

logger = get_logger(__name__)


class Conversation(BaseModel):
    """代表一次与LLM的多轮对话

    核心功能：
    - 管理对话的基本信息（ID、标题、时间戳等）
    - 存储和管理消息列表
    - 提供JSON序列化和反序列化功能
    - 支持消息的添加和查询
    """

    # 基本信息
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="对话唯一标识符")
    title: str = Field(default="新对话", description="对话标题")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="创建时间")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="更新时间")

    # 对话配置
    agent_mode: str | None = Field(None, description="代理模式")
    llm_model: str | None = Field(None, description="使用的LLM模型")

    # 消息相关
    messages: list[LLMMessage] = Field(default_factory=list, description="消息列表")
    message_count: int = Field(default=0, description="消息数量")

    # 额外元数据
    metadata: dict[str, Any] = Field(default_factory=dict, description="额外的元数据")

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **data):
        super().__init__(**data)
        # 确保message_count与messages列表长度一致
        self.message_count = len(self.messages)

    @property
    def last_message(self) -> LLMMessage | None:
        """获取最后一条消息"""
        return self.messages[-1] if self.messages else None

    @property
    def first_message(self) -> LLMMessage | None:
        """获取第一条消息"""
        return self.messages[0] if self.messages else None

    @property
    def user_messages(self) -> list[UserMessage]:
        """获取所有用户消息"""
        return [msg for msg in self.messages if isinstance(msg, UserMessage)]

    @property
    def assistant_messages(self) -> list[AssistantMessage]:
        """获取所有助手消息"""
        return [msg for msg in self.messages if isinstance(msg, AssistantMessage)]

    @property
    def system_messages(self) -> list[SystemMessage]:
        """获取所有系统消息"""
        return [msg for msg in self.messages if isinstance(msg, SystemMessage)]

    @property
    def tool_messages(self) -> list[ToolMessage]:
        """获取所有工具消息"""
        return [msg for msg in self.messages if isinstance(msg, ToolMessage)]

    def _is_content_invisible(self, content: Any) -> bool:
        """检查内容是否全部为不可见字符

        Args:
            content: 要检查的内容（字符串或列表）

        Returns:
            True 如果内容全部为不可见字符或为空，False 否则

        """
        if content is None:
            return True

        # 处理字符串类型
        if isinstance(content, str):
            # 移除所有空白字符（包括空格、制表符、换行符、零宽字符等）
            # 匹配：空白字符、零宽字符、不可见控制字符
            cleaned = re.sub(
                r"[\s\u200B-\u200D\u2060\uFEFF\u00AD\u034F\u180E\u2000-\u200A\u2028\u2029]",
                "",
                content,
            )
            return len(cleaned) == 0

        # 处理列表类型（多模态内容）
        if isinstance(content, list):
            if len(content) == 0:
                return True
            # 检查列表中是否有可见内容
            for item in content:
                # 处理 Pydantic 模型（如 TextContent）
                if hasattr(item, "text") and isinstance(item.text, str):
                    cleaned = re.sub(
                        r"[\s\u200B-\u200D\u2060\uFEFF\u00AD\u034F\u180E\u2000-\u200A\u2028\u2029]",
                        "",
                        item.text,
                    )
                    if len(cleaned) > 0:
                        return False
                # 处理字典类型
                elif isinstance(item, dict):
                    # 检查 text 字段
                    if "text" in item and isinstance(item["text"], str):
                        cleaned = re.sub(
                            r"[\s\u200B-\u200D\u2060\uFEFF\u00AD\u034F\u180E\u2000-\u200A\u2028\u2029]",
                            "",
                            item["text"],
                        )
                        if len(cleaned) > 0:
                            return False
                    # 检查其他可能有内容的字段
                    for value in item.values():
                        if isinstance(value, str):
                            cleaned = re.sub(
                                r"[\s\u200B-\u200D\u2060\uFEFF\u00AD\u034F\u180E\u2000-\u200A\u2028\u2029]",
                                "",
                                value,
                            )
                            if len(cleaned) > 0:
                                return False
                # 处理字符串类型
                elif isinstance(item, str):
                    cleaned = re.sub(
                        r"[\s\u200B-\u200D\u2060\uFEFF\u00AD\u034F\u180E\u2000-\u200A\u2028\u2029]",
                        "",
                        item,
                    )
                    if len(cleaned) > 0:
                        return False
            return True

        # 其他类型视为可见
        return False

    def add_message(self, message: LLMMessage) -> None:
        """添加新消息到对话中

        Args:
            message: 要添加的消息对象

        """
        # 【关键修复】检查消息是否应该被添加
        # 1. ToolMessage 总是应该被添加（通过 tool_call_id 标识）
        # 2. 有 tool_calls 的消息应该被添加（即使内容为空）
        is_tool_message = isinstance(message, ToolMessage)
        has_tool_calls = hasattr(message, "tool_calls") and message.tool_calls

        # 检查消息内容是否全部为不可见字符
        if hasattr(message, "content") and self._is_content_invisible(message.content):
            # 如果是工具消息或有工具调用，则仍然添加
            if not is_tool_message and not has_tool_calls:
                # 跳过添加不可见消息，不记录日志以避免污染输出
                return

        self.messages.append(message)
        self.message_count = len(self.messages)
        self.updated_at = datetime.now(timezone.utc)

        # 如果这是第一条用户消息，可以自动生成标题
        if len(self.messages) == 1 and isinstance(message, UserMessage) and self.title == "新对话":
            # 取前30个字符作为标题
            content = message.content if isinstance(message.content, str) else str(message.content)
            self.title = content[:30] + "..." if len(content) > 30 else content

    def say(self, message: LLMMessage) -> LLMMessage:
        """添加消息到对话的通用方法

        Args:
            message: LLM消息对象 (UserMessage, AssistantMessage, SystemMessage, ToolMessage)

        Returns:
            添加的消息对象

        """
        self.add_message(message)
        return message

    def get_message_by_index(self, index: int) -> LLMMessage | None:
        """根据索引获取消息

        Args:
            index: 消息索引

        Returns:
            消息对象或None

        """
        if 0 <= index < len(self.messages):
            return self.messages[index]
        return None

    def get_messages_by_role(self, role: MessageRole) -> list[LLMMessage]:
        """根据角色获取消息

        Args:
            role: 消息角色

        Returns:
            符合条件的消息列表

        """
        role_map = {
            MessageRole.USER: UserMessage,
            MessageRole.ASSISTANT: AssistantMessage,
            MessageRole.SYSTEM: SystemMessage,
            MessageRole.TOOL: ToolMessage,
        }

        target_class = role_map.get(role)
        if target_class:
            return [msg for msg in self.messages if isinstance(msg, target_class)]
        return []

    def get_recent_messages(self, count: int = 10) -> list[LLMMessage]:
        """获取最近的消息

        Args:
            count: 获取的消息数量

        Returns:
            最近的消息列表

        """
        return self.messages[-count:] if count > 0 else []

    def clear_messages(self) -> None:
        """清空所有消息"""
        self.messages.clear()
        self.message_count = 0
        self.updated_at = datetime.now(timezone.utc)

    def to_json(self, indent: int | None = None) -> str:
        """将对话转换为JSON字符串

        Args:
            indent: JSON缩进级别

        Returns:
            JSON字符串

        """
        # 转换消息为字典格式
        messages_data = []
        for msg in self.messages:
            # 检查消息是否有to_dict方法
            if hasattr(msg, "to_dict") and callable(msg.to_dict):
                msg_dict = msg.to_dict()
            # 如果消息是字典类型，直接使用
            elif isinstance(msg, dict):
                msg_dict = msg.copy()
            else:
                # 创建基本的消息字典
                msg_dict = {
                    "content": str(msg.content) if hasattr(msg, "content") else str(msg),
                    "type": getattr(msg, "type", "unknown"),
                    "additional_kwargs": getattr(msg, "additional_kwargs", {}),
                }

            # 添加时间戳和ID（如果消息没有的话）
            if "timestamp" not in msg_dict:
                msg_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
            if "id" not in msg_dict:
                msg_dict["id"] = str(uuid.uuid4())
            messages_data.append(msg_dict)

        # 构建完整的对话数据
        conversation_data = {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "message_count": self.message_count,
            "agent_mode": self.agent_mode,
            "llm_model": self.llm_model,
            "messages": messages_data,
            "metadata": self.metadata,
        }

        return json.dumps(conversation_data, ensure_ascii=False, indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> "Conversation":
        """从JSON字符串创建对话对象

        Args:
            json_str: JSON字符串

        Returns:
            Conversation对象

        """
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Conversation":
        """从字典创建对话对象

        Args:
            data: 对话数据字典

        Returns:
            Conversation对象

        """

        def parse_datetime(dt_str: str) -> datetime:
            """解析日期时间字符串，支持多种格式"""
            if not dt_str:
                return datetime.now(timezone.utc)

            # 处理带'Z'后缀的ISO格式
            if dt_str.endswith("Z"):
                return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            return datetime.fromisoformat(dt_str)

        # 解析时间戳
        created_at = parse_datetime(data.get("created_at"))
        updated_at = parse_datetime(data.get("updated_at"))

        # 确保updated_at不早于created_at
        updated_at = max(updated_at, created_at)

        # 解析消息列表
        messages = []
        messages_data = data.get("messages", [])
        for msg_data in messages_data:
            message = cls._parse_message_from_dict(msg_data)
            if message:
                messages.append(message)

        # 创建对话对象
        conversation = cls(
            id=data.get("id", str(uuid.uuid4())),
            title=data.get("title", "新对话"),
            created_at=created_at,
            updated_at=updated_at,
            agent_mode=data.get("agent_mode"),
            llm_model=data.get("llm_model"),
            messages=messages,
            metadata=data.get("metadata", {}),
        )

        # 确保message_count正确
        conversation.message_count = len(messages)

        return conversation

    @staticmethod
    def _parse_message_from_dict(msg_data: dict[str, Any]) -> LLMMessage | None:
        """从字典解析消息对象

        Args:
            msg_data: 消息数据字典

        Returns:
            消息对象或None

        """
        # 根据role或type字段确定消息类型
        role = msg_data.get("role") or msg_data.get("type", "")

        # 映射角色到消息类型
        if role in {"user", "human"}:
            return UserMessage.from_dict(msg_data)
        if role in {"assistant", "ai"}:
            return AssistantMessage.from_dict(msg_data)
        if role == "system":
            return SystemMessage.from_dict(msg_data)
        if role == "tool":
            return ToolMessage.from_dict(msg_data)
        # 对于未知角色，记录警告并创建后备UserMessage
        logger.warning(f"未知消息角色: {role}, 使用UserMessage作为后备")
        return UserMessage(
            content=msg_data.get("content", ""),
            additional_kwargs=msg_data.get("additional_kwargs", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """将对话转换为字典格式

        Returns:
            对话数据字典

        """
        # 转换消息为字典格式
        messages_data = []
        for msg in self.messages:
            msg_dict = msg.to_dict()
            # 添加时间戳和ID（如果消息没有的话）
            if "timestamp" not in msg_dict:
                msg_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
            if "id" not in msg_dict:
                msg_dict["id"] = str(uuid.uuid4())
            messages_data.append(msg_dict)

        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "message_count": self.message_count,
            "agent_mode": self.agent_mode,
            "llm_model": self.llm_model,
            "messages": messages_data,
            "metadata": self.metadata,
        }

    def get_conversation_summary(self) -> dict[str, Any]:
        """获取对话摘要信息

        Returns:
            对话摘要字典

        """
        user_msg_count = len(self.user_messages)
        assistant_msg_count = len(self.assistant_messages)
        system_msg_count = len(self.system_messages)
        tool_msg_count = len(self.tool_messages)

        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "message_count": self.message_count,
            "agent_mode": self.agent_mode,
            "llm_model": self.llm_model,
            "message_breakdown": {
                "user": user_msg_count,
                "assistant": assistant_msg_count,
                "system": system_msg_count,
                "tool": tool_msg_count,
            },
            "duration_minutes": (self.updated_at - self.created_at).total_seconds() / 60,
        }

    def __str__(self) -> str:
        """字符串表示"""
        return f"Conversation(id={self.id}, title={self.title}, messages={self.message_count})"

    def __repr__(self) -> str:
        """详细字符串表示"""
        return f"Conversation(id={self.id}, title='{self.title}', created_at={self.created_at.isoformat()}, message_count={self.message_count}, agent_mode={self.agent_mode}, llm_model={self.llm_model})"


# 便捷函数
def create_conversation(title: str = "新对话", **kwargs) -> Conversation:
    """创建新对话的便捷函数

    Args:
        title: 对话标题
        **kwargs: 其他参数

    Returns:
        Conversation对象

    """
    return Conversation(title=title, **kwargs)


def load_conversation_from_file(file_path: str) -> Conversation:
    """从文件加载对话

    Args:
        file_path: 文件路径

    Returns:
        Conversation对象

    """
    with Path(file_path).open(encoding="utf-8") as f:
        return Conversation.from_json(f.read())


def save_conversation_to_file(conversation: Conversation, file_path: str, indent: int = 2) -> None:
    """保存对话到文件

    Args:
        conversation: 对话对象
        file_path: 文件路径
        indent: JSON缩进级别

    """
    with file_path.open("w", encoding="utf-8") as f:
        f.write(conversation.to_json(indent=indent))
