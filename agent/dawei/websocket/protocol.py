# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""WebSocket消息协议定义

定义了WebSocket通信中使用的所有消息类型、验证器和序列化器。
整合了LLM消息模型和流式消息模型，支持多种消息类型和流式传输。
"""

import json
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timezone
from enum import StrEnum
from typing import Any, ClassVar, Literal, Union

from pydantic import BaseModel, Field, ValidationError, field_validator

# 导入相关实体模型
from dawei.entity.lm_messages import (
    ToolCall,
)
from dawei.entity.stream_message import (
    CompleteMessage,
    ContentMessage,
    ReasoningMessage,
    ToolCallMessage,
    UsageMessage,
)
from dawei.entity.stream_message import (
    ErrorMessage as StreamErrorMessage,
)


class MessageType(StrEnum):
    """WebSocket消息类型枚举，整合了LLM消息和流式消息类型

    优化说明：
    - 移除了冗余的 TASK_* 系列消息（TASK_START/PROGRESS/COMPLETE/ERROR）
    - 统一使用 TASK_NODE_* 系列进行任务图级别的细粒度状态追踪
    - 移除了未使用的 TOOL_MESSAGE（工具调用统一使用 TOOL_CALL_* 系列）
    - 移除了未使用的 CONNECTED（CONNECT 后端主动发送即可）
    - 保留 Agent 状态消息以实现完整的 Agent 可观测性
    """

    # ==================== 连接管理 ====================
    CONNECT = ("ws_connect",)
    CONNECTED = ("ws_connected",)
    DISCONNECT = ("ws_disconnect",)
    HEARTBEAT = ("ws_heartbeat",)

    # ==================== 基础消息通信 ====================
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    SYSTEM_MESSAGE = "system_message"

    # ==================== 任务节点管理（Task Graph级别）====================
    TASK_NODE_START = "task_node_start"  # 任务节点开始执行
    TASK_NODE_PROGRESS = "task_node_progress"  # 任务节点进度更新
    TASK_NODE_COMPLETE = "task_node_complete"  # 任务节点完成
    TASK_STATUS_UPDATE = "task_status_update"  # 任务状态更新
    TASK_GRAPH_UPDATE = "task_graph_update"  # 任务图更新

    # ==================== 流式消息（LLM输出流）====================
    STREAM_REASONING = "stream_reasoning"  # 流式推理内容（思考过程）
    STREAM_CONTENT = "stream_content"  # 流式内容输出
    STREAM_TOOL_CALL = "stream_tool_call"  # 流式工具调用
    STREAM_USAGE = "stream_usage"  # 流式Token使用统计
    STREAM_COMPLETE = "stream_complete"  # 流式完成
    STREAM_ERROR = "stream_error"  # 流式错误

    # ==================== 工具调用生命周期 ====================
    TOOL_CALL_START = "tool_call_start"  # 工具调用开始
    TOOL_CALL_PROGRESS = "tool_call_progress"  # 工具调用进度
    TOOL_CALL_RESULT = "tool_call_result"  # 工具调用结果

    # ==================== 用户交互 ====================
    FOLLOWUP_QUESTION = "followup_question"  # 后端向前端提问
    FOLLOWUP_RESPONSE = "followup_response"  # 前端向后端回复

    # ==================== LLM API 可观测性 ====================
    LLM_API_REQUEST = "llm_api_request"  # LLM API 请求开始
    LLM_API_RESPONSE = "llm_api_response"  # LLM API 响应中（流式）
    LLM_API_COMPLETE = "llm_api_complete"  # LLM API 调用完成
    LLM_API_ERROR = "llm_api_error"  # LLM API 调用错误

    # ==================== Agent 状态可观测性 ====================
    AGENT_START = "agent_start"  # Agent 开始执行
    AGENT_MODE_SWITCH = "agent_mode_switch"  # Agent 模式切换
    AGENT_THINKING = "agent_thinking"  # Agent 思考过程
    AGENT_COMPLETE = "agent_complete"  # Agent 完成执行
    AGENT_STOPPED = "agent_stopped"  # Agent 已停止

    # ==================== Agent 控制消息 ====================
    AGENT_STOP = "agent_stop"  # 停止 Agent 执行

    # ==================== 任务节点控制消息 ====================
    TASK_NODE_STOP = "task_node_stop"  # 停止任务节点

    # ==================== Agent 模式控制（====================
    MODE_SWITCH = "mode_switch"  # 切换 Agent 模式（plan/build）
    MODE_SWITCHED = "mode_switched"  # 模式切换完成确认
    TASK_NODE_STOPPED = "task_node_stopped"  # 任务节点已停止
    TODO_UPDATE = "todo_update"  # TODO列表更新

    # ==================== 上下文管理（====================
    CONTEXT_UPDATE = "context_update"  # 上下文使用更新

    # ==================== DaweiMem 记忆系统 ====================
    MEMORY_ENTRY_CREATED = "memory_entry_created"  # 新记忆创建
    MEMORY_ENTRY_RETRIEVED = "memory_entry_retrieved"  # 记忆被检索
    MEMORY_ENTRY_UPDATED = "memory_entry_updated"  # 记忆被更新
    MEMORY_ENTRY_EXPIRED = "memory_entry_expired"  # 记忆失效
    MEMORY_ENTRY_ARCHIVED = "memory_entry_archived"  # 记忆归档
    MEMORY_STATS = "memory_stats"  # 记忆统计

    CONTEXT_PAGE_LOADED = "context_page_loaded"  # 上下文页加载
    CONTEXT_PAGE_EVICTED = "context_page_evicted"  # 上下文页换出
    CONTEXT_PAGE_CREATED = "context_page_created"  # 上下文页创建

    MEMORY_CONSOLIDATION_STARTED = "memory_consolidation_started"
    MEMORY_CONSOLIDATION_COMPLETED = "memory_consolidation_completed"

    # ==================== PDCA 循环管理 ====================
    PDCA_CYCLE_START = "pdca_cycle_start"  # PDCA 循环开始
    PDCA_STATUS_UPDATE = "pdca_status_update"  # PDCA 状态更新
    PDCA_CYCLE_COMPLETE = "pdca_cycle_complete"  # PDCA 循环完成
    PDCA_PHASE_ADVANCE = "pdca_phase_advance"  # PDCA 阶段推进
    # ==================== 状态同步 ====================
    STATE_SYNC = "state_sync"  # 状态同步
    STATE_UPDATE = "state_update"  # 状态更新

    # ==================== 错误处理 ====================
    ERROR = "error"  # 通用错误消息
    WARNING = "warning"  # 警告消息

    # ==================== A2UI 消息 ====================
    A2UI_SERVER_EVENT = "a2ui_server_event"  # A2UI服务端事件（Server → Client）
    A2UI_USER_ACTION = "a2ui_user_action"  # A2UI用户操作（Client → Server）


class BaseWebSocketMessage(BaseModel, ABC):
    """WebSocket消息基类，整合了LLMMessage的功能"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="消息唯一标识")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="消息时间戳",
    )
    type: MessageType = Field(..., description="消息类型")
    session_id: str = Field(..., description="会话ID")
    user_message_id: str | None = Field(None, description="用户消息ID")
    task_node_id: str | None = Field(
        None,
        description="任务节点ID，表示是哪个task node发送出的消息（可选）",
    )

    class Config:
        use_enum_values = True
        extra = "forbid"  # 禁止额外字段，确保严格验证

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """将消息转换为字典格式"""

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseWebSocketMessage":
        """从字典创建消息实例"""

    def to_websocket_format(self) -> dict[str, Any]:
        """转换为WebSocket传输格式

        支持Pydantic v1和v2的序列化方法
        """
        # Pydantic v2使用model_dump(), v1使用dict()
        if hasattr(self, "model_dump"):
            # Pydantic v2
            return self.model_dump(exclude_none=True, mode="json")
        # Pydantic v1
        return self.dict(exclude_none=True)


class UserWebSocketMessage(BaseWebSocketMessage):
    """用户WebSocket消息，整合UserMessage"""

    type: MessageType = MessageType.USER_MESSAGE
    content: str = Field(..., description="用户消息内容")
    metadata: dict[str, Any] | None = Field(None, description="消息元数据")
    user_ui_context: dict[str, Any] | None = Field(None, description="用户UI上下文信息")

    @field_validator("content")
    @classmethod
    def validate_content(cls, v):
        if not v or not v.strip():
            raise ValueError("消息内容不能为空")
        return v.strip()

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserWebSocketMessage":
        """从字典创建实例"""
        return cls(**data)


class AssistantWebSocketMessage(BaseWebSocketMessage):
    """助手WebSocket消息，整合AssistantMessage"""

    type: MessageType = MessageType.ASSISTANT_MESSAGE
    content: str = Field(..., description="助手消息内容")
    task_id: str | None = Field(None, description="关联的任务ID")
    metadata: dict[str, Any] | None = Field(None, description="消息元数据")
    tool_calls: list[ToolCall] | None = Field(None, description="工具调用列表")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        result = self.to_websocket_format()
        if self.tool_calls:
            # 转换 tool_calls，将 tool_call_id 映射为 id
            tool_calls_dict = []
            for tool_call in self.tool_calls:
                tc_dict = tool_call.dict()
                tc_dict["id"] = tc_dict.pop("tool_call_id")
                tool_calls_dict.append(tc_dict)
            result["tool_calls"] = tool_calls_dict
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssistantWebSocketMessage":
        """从字典创建实例"""
        tool_calls = None
        if data.get("tool_calls"):
            # 从字典创建 ToolCall，将 id 映射为 tool_call_id
            tool_calls = []
            for tool_call_data in data["tool_calls"]:
                tool_call_data["tool_call_id"] = tool_call_data.pop("id")
                tool_calls.append(ToolCall(**tool_call_data))

        return cls(
            session_id=data["session_id"],
            content=data["content"],
            task_id=data.get("task_id"),
            metadata=data.get("metadata"),
            tool_calls=tool_calls,
        )

    @classmethod
    def from_stream_message(
        cls,
        stream_msg: ContentMessage | CompleteMessage,
        session_id: str,
        task_id: str,
    ) -> "AssistantWebSocketMessage":
        """从流式消息创建WebSocket消息"""
        # 根据流式消息类型获取内容
        content = ""
        if hasattr(stream_msg, "content"):
            content = stream_msg.content
        elif hasattr(stream_msg, "reasoning_content"):
            content = stream_msg.reasoning_content

        # 获取工具调用信息
        tool_calls = []
        if hasattr(stream_msg, "tool_calls") and stream_msg.tool_calls:
            tool_calls = stream_msg.tool_calls

        # 获取用户消息ID
        user_message_id = None
        if hasattr(stream_msg, "user_message_id"):
            user_message_id = stream_msg.user_message_id

        # 设置元数据，标记为流式消息
        metadata = {"is_chunk": True}

        return cls(
            session_id=session_id,
            content=content,
            task_id=task_id,
            user_message_id=user_message_id,
            metadata=metadata,
            tool_calls=tool_calls,
        )


class SystemWebSocketMessage(BaseWebSocketMessage):
    """系统WebSocket消息，整合SystemMessage"""

    type: MessageType = MessageType.SYSTEM_MESSAGE
    content: str = Field(..., description="系统消息内容")
    metadata: dict[str, Any] | None = Field(None, description="消息元数据")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SystemWebSocketMessage":
        """从字典创建实例"""
        return cls(**data)


class TaskStatusUpdateMessage(BaseWebSocketMessage):
    """任务状态更新消息"""

    type: MessageType = MessageType.TASK_STATUS_UPDATE
    task_id: str = Field(..., description="任务ID")
    graph_id: str = Field(..., description="任务图ID")
    old_status: str = Field(..., description="旧状态")
    new_status: str = Field(..., description="新状态")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="更新时间戳",
    )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskStatusUpdateMessage":
        """从字典创建实例"""
        return cls(**data)


class TaskGraphUpdateMessage(BaseWebSocketMessage):
    """任务图更新消息"""

    type: MessageType = MessageType.TASK_GRAPH_UPDATE
    graph_id: str = Field(..., description="任务图ID")
    update_type: str = Field(..., description="更新类型")
    data: dict[str, Any] = Field(..., description="更新数据")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="更新时间戳",
    )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskGraphUpdateMessage":
        """从字典创建实例"""
        return cls(**data)


class StreamReasoningMessage(BaseWebSocketMessage):
    """流式推理消息，整合ReasoningMessage"""

    type: MessageType = MessageType.STREAM_REASONING
    task_id: str = Field(..., description="任务ID")
    task_node_id: str | None = Field(None, description="任务节点ID")
    message_id: str | None = Field(None, description="消息ID，用于标识单个消息气泡")
    content: str = Field(..., description="推理内容")
    user_message_id: str | None = Field(None, description="用户消息ID")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StreamReasoningMessage":
        """从字典创建实例"""
        return cls(**data)

    @classmethod
    def from_stream_message(
        cls,
        stream_msg: ReasoningMessage,
        session_id: str,
        task_id: str,
    ) -> "StreamReasoningMessage":
        """从流式消息创建WebSocket消息"""
        return cls(
            session_id=session_id,
            task_id=task_id,
            message_id=stream_msg.id,  # ✅ Use LLM API's message_id
            content=stream_msg.content,
            user_message_id=stream_msg.user_message_id,
        )

    @classmethod
    def from_event_data(
        cls,
        event_data: dict[str, Any],
        session_id: str,
        task_id: str,
    ) -> "StreamReasoningMessage":
        """从事件数据创建消息"""
        return cls(
            session_id=session_id,
            task_id=task_id,
            task_node_id=event_data.get("task_node_id"),  # 🔧 添加 task_node_id
            message_id=event_data.get("message_id"),
            content=event_data.get("content", ""),
        )


class StreamContentMessage(BaseWebSocketMessage):
    """流式内容消息，整合ContentMessage"""

    type: MessageType = MessageType.STREAM_CONTENT
    task_id: str = Field(..., description="任务ID")
    task_node_id: str | None = Field(None, description="任务节点ID")
    message_id: str | None = Field(None, description="消息ID，用于标识单个消息气泡")
    content: str = Field(..., description="流式内容片段")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StreamContentMessage":
        """从字典创建实例"""
        return cls(**data)

    @classmethod
    def from_stream_message(
        cls,
        stream_msg: ContentMessage,
        session_id: str,
        task_id: str,
    ) -> "StreamContentMessage":
        """从流式消息创建WebSocket消息"""
        return cls(
            session_id=session_id,
            task_id=task_id,
            message_id=stream_msg.id,  # ✅ Use LLM API's message_id
            content=stream_msg.content,
            user_message_id=stream_msg.user_message_id,
        )

    @classmethod
    def from_event_data(
        cls,
        event_data: dict[str, Any],
        session_id: str,
        task_id: str,
    ) -> "StreamContentMessage":
        """从事件数据创建消息"""
        message_id = event_data.get("message_id")
        return cls(
            session_id=session_id,
            task_id=task_id,
            task_node_id=event_data.get("task_node_id"),  # 🔧 添加 task_node_id
            message_id=message_id,
            content=event_data.get("content", ""),
        )


class StreamToolCallMessage(BaseWebSocketMessage):
    """流式工具调用消息，整合ToolCallMessage"""

    type: MessageType = MessageType.STREAM_TOOL_CALL
    task_id: str = Field(..., description="任务ID")
    task_node_id: str | None = Field(None, description="任务节点ID")  # 🔧 新增：任务节点ID字段
    tool_call: ToolCall = Field(..., description="工具调用信息")
    all_tool_calls: list[ToolCall] = Field(default_factory=list, description="所有工具调用")
    user_message_id: str | None = Field(None, description="用户消息ID")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        result = self.to_websocket_format()

        # 直接使用 tool_call_id，不进行映射
        result["tool_call"] = self.tool_call.dict()
        result["all_tool_calls"] = [tool_call.dict() for tool_call in self.all_tool_calls]

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StreamToolCallMessage":
        """从字典创建实例"""
        tool_call = ToolCall(**data["tool_call"])
        all_tool_calls = [ToolCall(**tc) for tc in data.get("all_tool_calls", [])]

        return cls(
            session_id=data["session_id"],
            task_id=data["task_id"],
            tool_call=tool_call,
            all_tool_calls=all_tool_calls,
            user_message_id=data.get("user_message_id"),
        )

    @classmethod
    def from_stream_message(
        cls,
        stream_msg: ToolCallMessage,
        session_id: str,
        task_id: str,
        task_node_id: str | None = None,
    ) -> "StreamToolCallMessage":
        """从流式消息创建WebSocket消息"""
        return cls(
            session_id=session_id,
            task_id=task_id,
            task_node_id=task_node_id,  # 🔧 添加 task_node_id
            tool_call=stream_msg.tool_call,
            all_tool_calls=stream_msg.all_tool_calls,
            user_message_id=stream_msg.user_message_id,
        )


class StreamUsageMessage(BaseWebSocketMessage):
    """流式使用统计消息，整合UsageMessage"""

    type: MessageType = MessageType.STREAM_USAGE
    task_id: str = Field(..., description="任务ID")
    task_node_id: str | None = Field(None, description="任务节点ID")
    data: dict[str, Any] = Field(..., description="使用统计数据")
    user_message_id: str | None = Field(None, description="用户消息ID")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StreamUsageMessage":
        """从字典创建实例"""
        return cls(**data)

    @classmethod
    def from_stream_message(
        cls,
        stream_msg: UsageMessage,
        session_id: str,
        task_id: str,
    ) -> "StreamUsageMessage":
        """从流式消息创建WebSocket消息"""
        return cls(
            session_id=session_id,
            task_id=task_id,
            data=stream_msg.data,
            user_message_id=stream_msg.user_message_id,
        )

    @classmethod
    def from_event_data(
        cls,
        event_data: dict[str, Any],
        session_id: str,
        task_id: str,
    ) -> "StreamUsageMessage":
        """从事件数据创建消息"""
        return cls(
            session_id=session_id,
            task_id=task_id,
            task_node_id=event_data.get("task_node_id"),  # 🔧 添加 task_node_id
            data=event_data.get("data", {}),
            user_message_id=event_data.get("user_message_id"),
        )


class StreamCompleteMessage(BaseWebSocketMessage):
    """流式完成消息，整合CompleteMessage"""

    type: MessageType = MessageType.STREAM_COMPLETE
    task_id: str = Field(..., description="任务ID")
    task_node_id: str | None = Field(None, description="任务节点ID")
    message_id: str | None = Field(None, description="消息ID，用于标识单个消息气泡")
    reasoning_content: str | None = Field(None, description="推理内容")
    content: str | None = Field(None, description="完成内容")
    tool_calls: list[ToolCall] = Field(default_factory=list, description="工具调用列表")
    finish_reason: str | None = Field(None, description="完成原因")
    usage: dict[str, Any] | None = Field(None, description="使用统计")
    user_message_id: str | None = Field(None, description="用户消息ID")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        result = self.to_websocket_format()
        if self.tool_calls:
            # 转换 tool_calls，将 tool_call_id 映射为 id
            tool_calls_dict = []
            for tool_call in self.tool_calls:
                tc_dict = tool_call.dict()
                tc_dict["id"] = tc_dict.pop("tool_call_id")
                tool_calls_dict.append(tc_dict)
            result["tool_calls"] = tool_calls_dict
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StreamCompleteMessage":
        """从字典创建实例"""
        tool_calls = []
        if data.get("tool_calls"):
            # 直接使用 tool_call_id，不进行映射
            for tc_data in data["tool_calls"]:
                tool_calls.append(ToolCall(**tc_data))

        return cls(
            session_id=data["session_id"],
            task_id=data["task_id"],
            message_id=data.get("message_id"),
            reasoning_content=data.get("reasoning_content"),
            content=data.get("content"),
            tool_calls=tool_calls,
            finish_reason=data.get("finish_reason"),
            usage=data.get("usage"),
            user_message_id=data.get("user_message_id"),
        )

    @classmethod
    def from_stream_message(
        cls,
        stream_msg: CompleteMessage,
        session_id: str,
        task_id: str,
    ) -> "StreamCompleteMessage":
        """从流式消息创建WebSocket消息"""
        return cls(
            session_id=session_id,
            task_id=task_id,
            message_id=None,  # Will be provided by event data
            reasoning_content=stream_msg.reasoning_content,
            content=stream_msg.content,
            tool_calls=stream_msg.tool_calls,
            finish_reason=stream_msg.finish_reason,
            usage=stream_msg.usage,
            user_message_id=stream_msg.user_message_id,
        )

    @classmethod
    def from_event_data(
        cls,
        event_data: dict[str, Any],
        session_id: str,
        task_id: str,
    ) -> "StreamCompleteMessage":
        """从事件数据创建消息"""
        return cls(
            session_id=session_id,
            task_id=task_id,
            task_node_id=event_data.get("task_node_id"),  # 🔧 添加 task_node_id
            message_id=event_data.get("message_id"),
            reasoning_content=event_data.get("reasoning_content"),
            content=event_data.get("content"),
            tool_calls=[],  # Tool calls handled separately
            finish_reason=event_data.get("finish_reason"),
            usage=event_data.get("usage"),
        )


class StreamErrorMessage(BaseWebSocketMessage):
    """流式错误消息，整合StreamErrorMessage"""

    type: MessageType = MessageType.STREAM_ERROR
    task_id: str = Field(..., description="任务ID")
    task_node_id: str | None = Field(None, description="任务节点ID")
    error: str = Field(..., description="错误信息")
    details: dict[str, Any] | None = Field(None, description="错误详情")
    user_message_id: str | None = Field(None, description="用户消息ID")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StreamErrorMessage":
        """从字典创建实例"""
        return cls(**data)

    @classmethod
    def from_stream_message(
        cls,
        stream_msg: StreamErrorMessage | dict[str, Any],
        session_id: str,
        task_id: str,
        task_node_id: str | None = None,
    ) -> "StreamErrorMessage":
        """从流式消息创建WebSocket消息"""
        # 处理 stream_msg 可能是字典的情况
        if isinstance(stream_msg, dict):
            error = stream_msg.get("error", "未知错误")
            details = stream_msg.get("details")
            user_message_id = stream_msg.get("user_message_id")
        else:
            # 处理 stream_msg 是 ErrorMessage 实例的情况
            error = stream_msg.error
            details = stream_msg.details
            user_message_id = stream_msg.user_message_id

        return cls(
            session_id=session_id,
            task_id=task_id,
            task_node_id=task_node_id,  # 🔧 添加 task_node_id
            error=error,
            details=details,
            user_message_id=user_message_id,
        )


class FollowupQuestionMessage(BaseWebSocketMessage):
    """后端向前端发送的追问问题消息"""

    type: MessageType = MessageType.FOLLOWUP_QUESTION
    task_id: str = Field(..., description="任务ID")
    question: str = Field(..., description="问题内容")
    suggestions: list[str] = Field(default_factory=list, description="建议答案列表")
    tool_call_id: str = Field(..., description="工具调用ID，用于响应对应")
    user_message_id: str | None = Field(None, description="用户消息ID")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FollowupQuestionMessage":
        """从字典创建实例"""
        return cls(**data)


class FollowupResponseMessage(BaseWebSocketMessage):
    """前端向后端发送的追问回复消息"""

    type: MessageType = MessageType.FOLLOWUP_RESPONSE
    task_id: str = Field(..., description="任务ID")
    tool_call_id: str = Field(..., description="工具调用ID")
    response: str = Field(..., description="用户回复内容")
    user_message_id: str | None = Field(None, description="用户消息ID")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FollowupResponseMessage":
        """从字典创建实例"""
        return cls(**data)


class ToolCallStartMessage(BaseWebSocketMessage):
    """工具调用开始消息"""

    type: MessageType = MessageType.TOOL_CALL_START
    task_id: str = Field(..., description="任务ID")
    tool_name: str = Field(..., description="工具名称")
    tool_input: dict[str, Any] = Field(..., description="工具输入参数")
    tool_call_id: str | None = Field(None, description="工具调用ID")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolCallStartMessage":
        """从字典创建实例"""
        return cls(**data)


class ToolCallProgressMessage(BaseWebSocketMessage):
    """工具调用进度消息"""

    type: MessageType = MessageType.TOOL_CALL_PROGRESS
    task_id: str = Field(..., description="任务ID")
    tool_name: str = Field(..., description="工具名称")
    message: str = Field(..., description="进度消息")
    progress_percentage: int | None = Field(None, ge=0, le=100, description="进度百分比")
    tool_call_id: str | None = Field(None, description="工具调用ID")
    status: str | None = Field(None, description="执行状态")
    current_step: str | None = Field(None, description="当前步骤")
    total_steps: int | None = Field(None, ge=0, description="总步骤数")
    current_step_index: int | None = Field(None, ge=0, description="当前步骤索引")
    estimated_remaining_time: float | None = Field(None, description="预计剩余时间（秒）")
    stream_output: str | None = Field(None, description="流式输出内容（实时显示）")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolCallProgressMessage":
        """从字典创建实例"""
        return cls(**data)


class ToolCallResultMessage(BaseWebSocketMessage):
    """工具调用结果消息"""

    type: MessageType = MessageType.TOOL_CALL_RESULT
    task_id: str = Field(..., description="任务ID")
    tool_name: str = Field(..., description="工具名称")
    result: Any = Field(..., description="工具执行结果")
    is_error: bool = Field(False, description="是否为错误结果")
    tool_call_id: str | None = Field(None, description="工具调用ID")
    error_message: str | None = Field(None, description="错误消息")
    error_code: str | None = Field(None, description="错误代码")
    execution_time: float | None = Field(None, description="执行时间（毫秒）")
    performance_metrics: dict[str, Any] | None = Field(None, description="性能指标")
    workspace_id: str | None = Field(None, description="工作区ID")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolCallResultMessage":
        """从字典创建实例"""
        return cls(**data)


class ErrorMessage(BaseWebSocketMessage):
    """错误消息"""

    type: MessageType = MessageType.ERROR
    code: str = Field(..., description="错误代码")
    message: str = Field(..., description="错误消息")
    details: dict[str, Any] | None = Field(None, description="错误详情")
    recoverable: bool = Field(True, description="是否可恢复")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ErrorMessage":
        """从字典创建实例"""
        return cls(**data)


class WarningMessage(BaseWebSocketMessage):
    """警告消息"""

    type: MessageType = MessageType.WARNING
    code: str = Field(..., description="警告代码")
    message: str = Field(..., description="警告消息")
    details: dict[str, Any] | None = Field(None, description="警告详情")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WarningMessage":
        """从字典创建实例"""
        return cls(**data)


class HeartbeatMessage(BaseWebSocketMessage):
    """心跳消息"""

    type: MessageType = MessageType.HEARTBEAT
    message: str | None = Field(None, description="心跳消息内容")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HeartbeatMessage":
        """从字典创建实例"""
        return cls(**data)


class StateSyncMessage(BaseWebSocketMessage):
    """状态同步消息"""

    type: MessageType = MessageType.STATE_SYNC
    data: dict[str, Any] = Field(..., description="同步数据")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StateSyncMessage":
        """从字典创建实例"""
        return cls(**data)


class StateUpdateMessage(BaseWebSocketMessage):
    """状态更新消息"""

    type: MessageType = MessageType.STATE_UPDATE
    data: dict[str, Any] = Field(..., description="更新数据")
    path: str | None = Field(None, description="更新路径")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StateUpdateMessage":
        """从字典创建实例"""
        return cls(**data)


class ConnectMessage(BaseWebSocketMessage):
    """连接消息"""

    type: MessageType = MessageType.CONNECT
    message: str = Field("连接已建立", description="连接消息")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConnectMessage":
        """从字典创建实例"""
        return cls(**data)


class DisconnectMessage(BaseWebSocketMessage):
    """断开连接消息"""

    type: MessageType = MessageType.DISCONNECT
    reason: str | None = Field(None, description="断开原因")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DisconnectMessage":
        """从字典创建实例"""
        return cls(**data)


class LLMApiRequestMessage(BaseWebSocketMessage):
    """LLM API 请求开始消息"""

    type: MessageType = MessageType.LLM_API_REQUEST
    task_id: str = Field(..., description="任务ID")
    provider: str = Field(..., description="LLM提供商 (openai, deepseek, ollama等)")
    model: str = Field(..., description="模型名称")
    request_type: str = Field(default="chat", description="请求类型 (chat, completion等)")
    input_tokens: int | None = Field(None, description="输入token数量")
    metadata: dict[str, Any] | None = Field(None, description="其他元数据")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LLMApiRequestMessage":
        """从字典创建实例"""
        return cls(**data)


class LLMApiResponseMessage(BaseWebSocketMessage):
    """LLM API 响应消息（流式）"""

    type: MessageType = MessageType.LLM_API_RESPONSE
    task_id: str = Field(..., description="任务ID")
    response_type: str = Field(..., description="响应类型 (reasoning, content, tool_call, usage)")
    content: str | None = Field(None, description="响应内容")
    data: dict[str, Any] | None = Field(None, description="响应数据（用于tool_call等复杂类型）")
    is_streaming: bool = Field(True, description="是否为流式响应")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LLMApiResponseMessage":
        """从字典创建实例"""
        return cls(**data)


class LLMApiCompleteMessage(BaseWebSocketMessage):
    """LLM API 调用完成消息"""

    type: MessageType = MessageType.LLM_API_COMPLETE
    task_id: str = Field(..., description="任务ID")
    provider: str = Field(..., description="LLM提供商")
    model: str = Field(..., description="模型名称")
    finish_reason: str | None = Field(None, description="完成原因 (stop, length, tool_calls等)")
    usage: dict[str, Any] | None = Field(None, description="Token使用统计")
    duration_ms: int | None = Field(None, description="请求耗时（毫秒）")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LLMApiCompleteMessage":
        """从字典创建实例"""
        return cls(**data)


class LLMApiErrorMessage(BaseWebSocketMessage):
    """LLM API 调用错误消息"""

    type: MessageType = MessageType.LLM_API_ERROR
    task_id: str = Field(..., description="任务ID")
    provider: str = Field(..., description="LLM提供商")
    model: str = Field(..., description="模型名称")
    error_code: str = Field(..., description="错误代码")
    error_message: str = Field(..., description="错误消息")
    is_retryable: bool = Field(False, description="是否可重试")
    details: dict[str, Any] | None = Field(None, description="错误详情")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LLMApiErrorMessage":
        """从字典创建实例"""
        return cls(**data)


class AgentStartMessage(BaseWebSocketMessage):
    """Agent 开始执行消息"""

    type: MessageType = MessageType.AGENT_START
    task_id: str = Field(..., description="任务ID")
    agent_mode: str = Field(..., description="Agent模式 (architect, code, ask, debug, plan)")
    user_message: str = Field(..., description="用户原始消息")
    workspace_id: str = Field(..., description="工作区ID")
    metadata: dict[str, Any] | None = Field(None, description="其他元数据")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentStartMessage":
        """从字典创建实例"""
        return cls(**data)


class AgentModeSwitchMessage(BaseWebSocketMessage):
    """Agent 模式切换消息"""

    type: MessageType = MessageType.AGENT_MODE_SWITCH
    task_id: str = Field(..., description="任务ID")
    old_mode: str = Field(..., description="旧模式")
    new_mode: str = Field(..., description="新模式")
    reason: str = Field(..., description="切换原因")
    metadata: dict[str, Any] | None = Field(None, description="其他元数据")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentModeSwitchMessage":
        """从字典创建实例"""
        return cls(**data)


class AgentThinkingMessage(BaseWebSocketMessage):
    """Agent 思考过程消息"""

    type: MessageType = MessageType.AGENT_THINKING
    task_id: str = Field(..., description="任务ID")
    thinking_content: str = Field(..., description="思考内容")
    step_id: str | None = Field(None, description="思考步骤ID")
    is_complete: bool = Field(False, description="是否完成")
    metadata: dict[str, Any] | None = Field(None, description="其他元数据")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentThinkingMessage":
        """从字典创建实例"""
        return cls(**data)


class AgentCompleteMessage(BaseWebSocketMessage):
    """Agent 完成执行消息"""

    type: MessageType = MessageType.AGENT_COMPLETE
    task_id: str = Field(..., description="任务ID")
    result_summary: str = Field(..., description="结果摘要")
    total_duration_ms: int = Field(..., description="总耗时（毫秒）")
    tasks_completed: int = Field(0, description="完成任务数")
    tools_used: list[str] = Field(default_factory=list, description="使用的工具列表")
    metadata: dict[str, Any] | None = Field(None, description="其他元数据")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentCompleteMessage":
        """从字典创建实例"""
        return cls(**data)


class AgentStopMessage(BaseWebSocketMessage):
    """Agent 停止控制消息（前端 -> 后端）"""

    type: MessageType = MessageType.AGENT_STOP
    task_id: str = Field(..., description="任务ID")
    reason: str | None = Field(None, description="停止原因")
    force: bool = Field(False, description="是否强制停止")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="停止时间",
    )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentStopMessage":
        """从字典创建实例"""
        return cls(**data)


class AgentStoppedMessage(BaseWebSocketMessage):
    """Agent 已停止状态通知（后端 -> 前端）"""

    type: MessageType = MessageType.AGENT_STOP  # 使用相同的消息类型
    task_id: str = Field(..., description="任务ID")
    stopped_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="停止时间",
    )
    result_summary: str = Field(..., description="停止时的结果摘要")
    partial: bool = Field(True, description="是否为部分完成（未完全执行）")
    metadata: dict[str, Any] | None = Field(None, description="其他元数据")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentStoppedMessage":
        """从字典创建实例"""
        return cls(**data)


class TaskNodeStartMessage(BaseWebSocketMessage):
    """任务节点开始执行消息"""

    type: MessageType = MessageType.TASK_NODE_START
    task_id: str = Field(..., description="任务ID")
    task_node_id: str = Field(..., description="节点ID")
    node_type: str = Field(..., description="节点类型")
    description: str = Field(..., description="节点描述")
    metadata: dict[str, Any] | None = Field(None, description="其他元数据")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskNodeStartMessage":
        """从字典创建实例"""
        return cls(**data)


class TaskNodeProgressMessage(BaseWebSocketMessage):
    """任务节点进度消息"""

    type: MessageType = MessageType.TASK_NODE_PROGRESS
    task_id: str = Field(..., description="任务ID")
    task_node_id: str = Field(..., description="节点ID")
    progress: int = Field(..., ge=0, le=100, description="进度百分比")
    status: str = Field(..., description="状态")
    message: str = Field(..., description="进度消息")
    data: dict[str, Any] | None = Field(None, description="进度数据")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskNodeProgressMessage":
        """从字典创建实例"""
        return cls(**data)


class TaskNodeCompleteMessage(BaseWebSocketMessage):
    """任务节点完成消息"""

    type: MessageType = MessageType.TASK_NODE_COMPLETE
    task_id: str = Field(..., description="任务ID")
    task_node_id: str = Field(..., description="节点ID")
    result: Any | None = Field(None, description="执行结果")
    duration_ms: int = Field(..., description="耗时（毫秒）")
    metadata: dict[str, Any] | None = Field(None, description="其他元数据")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskNodeCompleteMessage":
        """从字典创建实例"""
        return cls(**data)


class TodoUpdateMessage(BaseWebSocketMessage):
    """TODO列表更新消息"""

    type: MessageType = MessageType.TODO_UPDATE
    task_node_id: str = Field(..., description="任务节点ID")
    todos: list[dict[str, Any]] = Field(..., description="TODO列表")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TodoUpdateMessage":
        """从字典创建实例"""
        return cls(**data)


# ==================== 任务节点控制消息 ====================


class TaskNodeStopMessage(BaseWebSocketMessage):
    """停止任务节点消息（前端→后端）"""

    type: MessageType = MessageType.TASK_NODE_STOP
    task_node_id: str = Field(..., description="任务节点ID")
    reason: str | None = Field(None, description="停止原因")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskNodeStopMessage":
        """从字典创建实例"""
        return cls(**data)


class TaskNodeStoppedMessage(BaseWebSocketMessage):
    """任务节点已停止消息（后端→前端）"""

    type: MessageType = MessageType.TASK_NODE_STOPPED
    task_node_id: str = Field(..., description="任务节点ID")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="停止时间",
    )
    reason: str | None = Field(None, description="停止原因")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskNodeStoppedMessage":
        """从字典创建实例"""
        return cls(**data)


class ModeSwitchMessage(BaseWebSocketMessage):
    """Agent 模式切换消息（前端→后端）

    支持 PDCA 循环模式和传统模式切换
    """

    type: MessageType = MessageType.MODE_SWITCH
    mode: str = Field(..., description="目标模式: orchestrator, plan, do, check, act, 或 build")

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v):
        """验证模式名称

        支持的 PDCA 模式:
        - orchestrator: 智能协调者模式（默认）
        - plan: 规划阶段
        - do: 执行阶段
        - check: 检查阶段
        - act: 改进阶段
        - build: 完整循环模式（向后兼容）
        """
        valid_modes = ["orchestrator", "plan", "do", "check", "act", "build"]
        if v not in valid_modes:
            raise ValueError(f"Invalid mode: '{v}'. Valid modes: {', '.join(valid_modes)}")
        return v

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModeSwitchMessage":
        """从字典创建实例"""
        return cls(**data)


class ModeSwitchedMessage(BaseWebSocketMessage):
    """Agent 模式切换完成消息（后端→前端）"""

    type: MessageType = MessageType.MODE_SWITCHED
    previous_mode: str = Field(..., description="切换前的模式")
    current_mode: str = Field(..., description="当前模式")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="切换时间",
    )
    message: str = Field(..., description="切换消息")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModeSwitchedMessage":
        """从字典创建实例"""
        return cls(**data)


class ContextUpdateMessage(BaseWebSocketMessage):
    """上下文使用更新消息（后端→前端）"""

    type: MessageType = MessageType.CONTEXT_UPDATE
    stats: dict[str, Any] = Field(..., description="上下文统计信息")
    warnings: list[str] = Field(default_factory=list, description="警告信息")
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextUpdateMessage":
        """从字典创建实例"""
        return cls(**data)


class PDACycleStartMessage(BaseWebSocketMessage):
    """PDCA 循环开始消息（后端→前端）"""

    type: MessageType = MessageType.PDCA_CYCLE_START
    cycle_id: str = Field(..., description="PDCA 循环 ID")
    domain: str = Field(..., description="任务领域")
    task_description: str = Field(..., description="任务描述")
    task_goals: list[str] = Field(default_factory=list, description="任务目标")
    success_criteria: list[str] = Field(default_factory=list, description="成功标准")
    start_time: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="开始时间",
    )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PDACycleStartMessage":
        """从字典创建实例"""
        return cls(**data)


class PDCAStatusUpdateMessage(BaseWebSocketMessage):
    """PDCA 状态更新消息（后端→前端）"""

    type: MessageType = MessageType.PDCA_STATUS_UPDATE
    cycle_id: str = Field(..., description="PDCA 循环 ID")
    current_phase: str = Field(..., description="当前阶段 (plan/do/check/act)")
    phases: dict[str, str] = Field(
        ...,
        description="各阶段状态: {'plan': 'pending'|'in_progress'|'completed', ...}",
    )
    completion: float = Field(..., ge=0, le=100, description="完成度 (0-100)")
    cycle_count: int = Field(..., ge=1, description="循环次数")
    current_phase_description: str | None = Field(None, description="当前阶段描述")
    estimated_remaining_time: float | None = Field(None, description="预计剩余时间（秒）")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="更新时间",
    )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PDCAStatusUpdateMessage":
        """从字典创建实例"""
        return cls(**data)


class PDCAPhaseAdvanceMessage(BaseWebSocketMessage):
    """PDCA 阶段推进消息（后端→前端）"""

    type: MessageType = MessageType.PDCA_PHASE_ADVANCE
    cycle_id: str = Field(..., description="PDCA 循环 ID")
    from_phase: str = Field(..., description="源阶段")
    to_phase: str = Field(..., description="目标阶段")
    reason: str = Field(..., description="推进原因")
    phase_data: dict[str, Any] | None = Field(None, description="阶段数据")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="推进时间",
    )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PDCAPhaseAdvanceMessage":
        """从字典创建实例"""
        return cls(**data)


class PDACycleCompleteMessage(BaseWebSocketMessage):
    """PDCA 循环完成消息（后端→前端）"""

    type: MessageType = MessageType.PDCA_CYCLE_COMPLETE
    cycle_id: str = Field(..., description="PDCA 循环 ID")
    domain: str = Field(..., description="任务领域")
    total_cycles: int = Field(..., description="总循环次数")
    completion: float = Field(..., ge=0, le=100, description="最终完成度")
    result_summary: str = Field(..., description="结果摘要")
    lessons_learned: str | None = Field(None, description="经验教训")
    next_steps: list[str] | None = Field(None, description="后续步骤")
    start_time: str = Field(..., description="开始时间")
    end_time: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="结束时间",
    )
    duration_seconds: float | None = Field(None, description="总耗时（秒）")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PDACycleCompleteMessage":
        """从字典创建实例"""
        return cls(**data)


# ==================== A2UI 消息类 ====================


class A2UIServerEventMessage(BaseWebSocketMessage):
    """A2UI服务端事件消息（Server → Client）

    用于向前端发送A2UI组件更新、数据模型更新等事件
    """

    type: MessageType = MessageType.A2UI_SERVER_EVENT
    messages: list[dict[str, Any]] = Field(
        ...,
        description="A2UI消息列表，每个消息包含beginRendering/surfaceUpdate/dataModelUpdate/deleteSurface之一",
    )
    metadata: dict[str, Any] | None = Field(None, description="可选的元数据（标题、描述等）")
    session_id: str | None = Field(None, description="会话ID")
    task_node_id: str | None = Field(None, description="任务节点ID")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "A2UIServerEventMessage":
        """从字典创建实例"""
        return cls(**data)


class A2UIUserActionMessage(BaseWebSocketMessage):
    """A2UI用户操作消息（Client → Server）

    用于从前端向后端发送用户在A2UI组件上的操作
    """

    type: MessageType = MessageType.A2UI_USER_ACTION
    surface_id: str = Field(..., description="Surface ID")
    component_id: str = Field(..., description="触发操作的组件ID")
    action_name: str = Field(..., description="操作名称（如button的action.name）")
    timestamp: str = Field(..., description="操作时间戳")
    context: dict[str, Any] | None = Field(None, description="操作上下文数据")
    session_id: str | None = Field(None, description="会话ID")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "A2UIUserActionMessage":
        """从字典创建实例"""
        return cls(**data)


# 消息类型联合（优化后）
WebSocketMessage = Union[
    # 基础消息通信
    UserWebSocketMessage,
    AssistantWebSocketMessage,
    SystemWebSocketMessage,
    # 任务节点管理
    TaskNodeStartMessage,
    TaskNodeProgressMessage,
    TaskNodeCompleteMessage,
    TaskStatusUpdateMessage,
    TaskGraphUpdateMessage,
    TodoUpdateMessage,
    # 任务节点控制
    TaskNodeStopMessage,
    TaskNodeStoppedMessage,
    # Agent 模式控制（
    ModeSwitchMessage,
    ModeSwitchedMessage,
    # 上下文管理（
    ContextUpdateMessage,
    # PDCA 循环管理
    PDACycleStartMessage,
    PDCAStatusUpdateMessage,
    PDCAPhaseAdvanceMessage,
    PDACycleCompleteMessage,
    # 流式消息
    StreamReasoningMessage,
    StreamContentMessage,
    StreamToolCallMessage,
    StreamUsageMessage,
    StreamCompleteMessage,
    StreamErrorMessage,
    # 工具调用生命周期
    ToolCallStartMessage,
    ToolCallProgressMessage,
    ToolCallResultMessage,
    # 用户交互
    FollowupQuestionMessage,
    FollowupResponseMessage,
    # LLM API 可观测性
    LLMApiRequestMessage,
    LLMApiResponseMessage,
    LLMApiCompleteMessage,
    LLMApiErrorMessage,
    # Agent 状态可观测性
    AgentStartMessage,
    AgentModeSwitchMessage,
    AgentThinkingMessage,
    AgentCompleteMessage,
    # 状态同步
    StateSyncMessage,
    StateUpdateMessage,
    # 连接管理
    ConnectMessage,
    DisconnectMessage,
    HeartbeatMessage,
    # 错误处理
    ErrorMessage,
    WarningMessage,
    # A2UI
    A2UIServerEventMessage,
    A2UIUserActionMessage,
]


class MessageValidator:
    """消息验证器，支持所有WebSocket消息类型"""

    # 消息类型映射表（优化后）
    _message_class_map: ClassVar[dict[str, type[BaseWebSocketMessage]]] = {
        # 基础消息通信
        MessageType.USER_MESSAGE: UserWebSocketMessage,
        MessageType.ASSISTANT_MESSAGE: AssistantWebSocketMessage,
        MessageType.SYSTEM_MESSAGE: SystemWebSocketMessage,
        # 任务节点管理
        MessageType.TASK_NODE_START: TaskNodeStartMessage,
        MessageType.TASK_NODE_PROGRESS: TaskNodeProgressMessage,
        MessageType.TASK_NODE_COMPLETE: TaskNodeCompleteMessage,
        MessageType.TASK_STATUS_UPDATE: TaskStatusUpdateMessage,
        MessageType.TASK_GRAPH_UPDATE: TaskGraphUpdateMessage,
        # 流式消息
        MessageType.STREAM_REASONING: StreamReasoningMessage,
        MessageType.STREAM_CONTENT: StreamContentMessage,
        MessageType.STREAM_TOOL_CALL: StreamToolCallMessage,
        MessageType.STREAM_USAGE: StreamUsageMessage,
        MessageType.STREAM_COMPLETE: StreamCompleteMessage,
        MessageType.STREAM_ERROR: StreamErrorMessage,
        # 工具调用生命周期
        MessageType.TOOL_CALL_START: ToolCallStartMessage,
        MessageType.TOOL_CALL_PROGRESS: ToolCallProgressMessage,
        MessageType.TOOL_CALL_RESULT: ToolCallResultMessage,
        # 用户交互
        MessageType.FOLLOWUP_QUESTION: FollowupQuestionMessage,
        MessageType.FOLLOWUP_RESPONSE: FollowupResponseMessage,
        # LLM API 可观测性
        MessageType.LLM_API_REQUEST: LLMApiRequestMessage,
        MessageType.LLM_API_RESPONSE: LLMApiResponseMessage,
        MessageType.LLM_API_COMPLETE: LLMApiCompleteMessage,
        MessageType.LLM_API_ERROR: LLMApiErrorMessage,
        # Agent 状态可观测性
        MessageType.AGENT_START: AgentStartMessage,
        MessageType.AGENT_MODE_SWITCH: AgentModeSwitchMessage,
        MessageType.AGENT_THINKING: AgentThinkingMessage,
        MessageType.AGENT_COMPLETE: AgentCompleteMessage,
        # Agent 控制消息
        MessageType.AGENT_STOP: AgentStopMessage,
        # Agent 模式控制（
        MessageType.MODE_SWITCH: ModeSwitchMessage,
        MessageType.MODE_SWITCHED: ModeSwitchedMessage,
        # 上下文管理（
        MessageType.CONTEXT_UPDATE: ContextUpdateMessage,
        # PDCA 循环管理
        MessageType.PDCA_CYCLE_START: PDACycleStartMessage,
        MessageType.PDCA_STATUS_UPDATE: PDCAStatusUpdateMessage,
        MessageType.PDCA_PHASE_ADVANCE: PDCAPhaseAdvanceMessage,
        MessageType.PDCA_CYCLE_COMPLETE: PDACycleCompleteMessage,
        # 状态同步
        MessageType.STATE_SYNC: StateSyncMessage,
        MessageType.STATE_UPDATE: StateUpdateMessage,
        # 连接管理
        MessageType.CONNECT: ConnectMessage,
        MessageType.DISCONNECT: DisconnectMessage,
        MessageType.HEARTBEAT: HeartbeatMessage,
        # 错误处理
        MessageType.ERROR: ErrorMessage,
        MessageType.WARNING: WarningMessage,
    }

    @classmethod
    def validate(cls, data: dict[str, Any]) -> BaseWebSocketMessage | None:
        """验证消息数据并创建相应的消息对象

        Args:
            data: 待验证的消息数据

        Returns:
            验证通过的消息对象，验证失败返回None

        Raises:
            ValueError: 当消息类型无效或不受支持时
            ValidationError: 当消息数据验证失败时

        """
        # Fast Fail: 检查输入数据
        if not data or not isinstance(data, dict):
            raise ValueError("消息数据必须是非空的字典")

        # Fast Fail: 验证消息类型
        message_type = data.get("type")
        if message_type is None:
            raise ValueError("消息类型 'type' 字段是必需的")

        if not isinstance(message_type, str) or message_type not in MessageType._value2member_map_:
            raise ValueError(f"无效的消息类型: '{message_type}'")

        # Fast Fail: 获取对应的消息类
        message_class = cls._message_class_map.get(message_type)
        if not message_class:
            raise ValueError(f"不支持的消息类型: '{message_type}'")

        # Fast Fail: 创建消息对象，自动进行pydantic验证
        try:
            return message_class.from_dict(data)
        except ValidationError as e:
            # 重新抛出带有更详细信息的验证错误
            raise ValidationError.from_exception_data(
                title=f"消息验证失败 for type '{message_type}'",
                line_errors=e.errors(),
            )
        except Exception as e:
            # Fast Fail: 其他错误直接抛出
            raise ValueError(f"消息对象创建失败 (type={message_type}): {e!s}")

    @classmethod
    def get_message_class(cls, message_type: str) -> type[BaseWebSocketMessage] | None:
        """根据消息类型获取对应的消息类"""
        return cls._message_class_map.get(message_type)

    @classmethod
    def validate_user_message(cls, data: dict[str, Any]) -> bool:
        """验证用户消息"""
        try:
            message = cls.validate(data)
            return isinstance(message, UserWebSocketMessage)
        except (ValidationError, ValueError, TypeError) as e:
            # Fast Fail: 预期的验证错误应该快速失败
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"User message validation failed: {e}", exc_info=True)
            raise  # Fast Fail: 直接抛出而不是静默返回False
        except Exception as e:
            # Fast Fail: 未预期的错误应该快速失败
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Unexpected error validating user message: {e}", exc_info=True)
            raise  # Fast Fail

    @classmethod
    def validate_assistant_message(cls, data: dict[str, Any]) -> bool:
        """验证助手消息"""
        try:
            message = cls.validate(data)
            return isinstance(message, AssistantWebSocketMessage)
        except (ValidationError, ValueError, TypeError) as e:
            # Fast Fail: 预期的验证错误应该快速失败
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Assistant message validation failed: {e}", exc_info=True)
            raise  # Fast Fail: 直接抛出而不是静默返回False
        except Exception as e:
            # Fast Fail: 未预期的错误应该快速失败
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Unexpected error validating assistant message: {e}", exc_info=True)
            raise  # Fast Fail

    @classmethod
    def validate_task_node_progress_message(cls, data: dict[str, Any]) -> bool:
        """验证任务节点进度消息"""
        try:
            message = cls.validate(data)
            return isinstance(message, TaskNodeProgressMessage)
        except (ValidationError, ValueError, TypeError) as e:
            # Fast Fail: 预期的验证错误应该快速失败
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Task node progress message validation failed: {e}", exc_info=True)
            raise  # Fast Fail: 直接抛出而不是静默返回False
        except Exception as e:
            # Fast Fail: 未预期的错误应该快速失败
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"Unexpected error validating task node progress message: {e}",
                exc_info=True,
            )
            raise  # Fast Fail

    @classmethod
    def validate_error_message(cls, data: dict[str, Any]) -> bool:
        """验证错误消息"""
        try:
            message = cls.validate(data)
            return isinstance(message, ErrorMessage)
        except (ValidationError, ValueError, TypeError) as e:
            # Fast Fail: 预期的验证错误应该快速失败
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error message validation failed: {e}", exc_info=True)
            raise  # Fast Fail: 直接抛出而不是静默返回False
        except Exception as e:
            # Fast Fail: 未预期的错误应该快速失败
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Unexpected error validating error message: {e}", exc_info=True)
            raise  # Fast Fail


class MessageSerializer:
    """消息序列化器，支持所有WebSocket消息类型"""

    @staticmethod
    def serialize(message: BaseWebSocketMessage) -> str:
        """序列化消息为JSON字符串

        Args:
            message: 待序列化的消息对象

        Returns:
            JSON字符串

        Raises:
            ValueError: 当序列化失败时

        """
        # Fast Fail: 确保枚举值被正确序列化为字符串
        try:
            message_dict = message.to_dict()
            return json.dumps(message_dict, ensure_ascii=False, separators=(",", ":"))
        except Exception as e:
            # Fast Fail: 序列化失败直接抛出
            raise ValueError(f"消息序列化失败: {e!s}")

    @staticmethod
    def deserialize(data: str) -> BaseWebSocketMessage | None:
        """反序列化JSON字符串为消息对象

        Args:
            data: JSON字符串

        Returns:
            消息对象，失败返回None

        Raises:
            ValueError: 当JSON解析失败或消息验证失败时

        """
        # Fast Fail: JSON解析失败直接抛出
        try:
            message_data = json.loads(data)
            return MessageValidator.validate(message_data)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON解析失败: {e!s}")
        except Exception:
            # Fast Fail: 验证错误等会被重新抛出
            raise

    @staticmethod
    def deserialize_with_validation(
        data: str,
        expected_type: ClassVar[MessageType | None] = None,
    ) -> BaseWebSocketMessage | None:
        """反序列化JSON字符串为消息对象，并进行类型验证

        Args:
            data: JSON字符串
            expected_type: 期望的消息类型

        Returns:
            消息对象，验证失败返回None

        """
        # Fast Fail: 预期的反序列化错误应该快速失败
        try:
            message = MessageSerializer.deserialize(data)
            if not message:
                return None

            if expected_type and message.type != expected_type:
                return None

            return message
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as e:
            # Fast Fail: 预期的反序列化错误应该快速失败
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Message deserialization failed: {e}", exc_info=True)
            raise  # Fast Fail: 直接抛出而不是静默返回None
        except Exception as e:
            # Fast Fail: 未预期的错误应该快速失败
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Unexpected error deserializing message: {e}", exc_info=True)
            raise  # Fast Fail: 直接抛出而不是静默返回None

    @staticmethod
    def create_error_message(
        session_id: str,
        code: str,
        message: str,
        details: ClassVar[dict[str, Any] | None] = None,
        recoverable: ClassVar[bool] = True,
    ) -> ErrorMessage:
        """创建错误消息"""
        return ErrorMessage(
            session_id=session_id,
            code=code,
            message=message,
            details=details,
            recoverable=recoverable,
        )

    @staticmethod
    def create_heartbeat_message(session_id: str, message: str = "pong") -> HeartbeatMessage:
        """创建心跳消息"""
        return HeartbeatMessage(session_id=session_id, message=message)

    @staticmethod
    def create_task_node_progress_message(
        session_id: str,
        task_id: str,
        task_node_id: str,
        progress: int,
        status: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> "TaskNodeProgressMessage":
        """创建任务节点进度消息"""
        return TaskNodeProgressMessage(
            session_id=session_id,
            task_id=task_id,
            task_node_id=task_node_id,
            progress=progress,
            status=status,
            message=message,
            data=data,
        )

    @staticmethod
    def create_user_message(
        session_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> UserWebSocketMessage:
        """创建用户消息"""
        return UserWebSocketMessage(session_id=session_id, content=content, metadata=metadata)

    @staticmethod
    def create_assistant_message(
        session_id: str,
        content: str,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tool_calls: list[ToolCall] | None = None,
    ) -> AssistantWebSocketMessage:
        """创建助手消息"""
        return AssistantWebSocketMessage(
            session_id=session_id,
            content=content,
            task_id=task_id,
            metadata=metadata,
            tool_calls=tool_calls,
        )


# 标准化事件消息格式
class StandardizedEventMessage(BaseModel):
    """标准化的事件消息格式"""

    event: str = Field(..., description="事件类型")
    data: dict[str, Any] = Field(..., description="事件数据")
    session_id: str | None = Field(None, description="会话ID")
    timestamp: str | None = Field(None, description="时间戳")

    class Config:
        extra = "allow"  # 允许额外字段


class EventMessageSerializer:
    """事件消息序列化器"""

    @staticmethod
    def serialize(event: str, data: dict[str, Any], session_id: str | None = None) -> str:
        """序列化事件消息

        Args:
            event: 事件类型
            data: 事件数据
            session_id: 会话ID

        Returns:
            JSON字符串

        """
        message = StandardizedEventMessage(
            event=event,
            data=data,
            session_id=session_id,
            timestamp=datetime.now(UTC).isoformat(),
        )
        return message.json()

    @staticmethod
    def create_task_event_message(event: str, task_id: str, session_id: str, **kwargs) -> str:
        """创建任务事件消息

        Args:
            event: 事件类型
            task_id: 任务ID
            session_id: 会话ID
            **kwargs: 其他事件数据

        Returns:
            JSON字符串

        """
        data = {"task_id": task_id, "timestamp": datetime.now(UTC).isoformat(), **kwargs}

        return EventMessageSerializer.serialize(event, data, session_id)


# ============================================================================
# DaweiMem 记忆系统消息类
# ============================================================================


class MemoryEntryMessage(BaseModel):
    """记忆条目消息"""

    id: str
    subject: str
    predicate: str
    object: str
    valid_start: str
    valid_end: str | None
    confidence: float
    energy: float
    access_count: int
    memory_type: str
    keywords: list[str]
    metadata: dict[str, Any]

    class Config:
        extra = "allow"


class MemoryCreatedMessage(BaseWebSocketMessage):
    """记忆创建消息"""

    type: Literal[MessageType.MEMORY_ENTRY_CREATED] = Field(
        default=MessageType.MEMORY_ENTRY_CREATED,
    )
    data: MemoryEntryMessage = Field(..., description="创建的记忆条目")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "data": self.data.dict(),
        }


class MemoryRetrievedMessage(BaseWebSocketMessage):
    """记忆检索消息"""

    type: Literal[MessageType.MEMORY_ENTRY_RETRIEVED] = Field(
        default=MessageType.MEMORY_ENTRY_RETRIEVED,
    )
    data: dict[str, Any] = Field(..., description="检索数据，包含memory_id和access_count")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "data": self.data,
        }


class MemoryStatsMessage(BaseWebSocketMessage):
    """记忆统计消息"""

    type: Literal[MessageType.MEMORY_STATS] = Field(default=MessageType.MEMORY_STATS)
    data: dict[str, Any] = Field(..., description="记忆统计数据")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "data": self.data,
        }


class ContextPageMessage(BaseModel):
    """上下文页消息"""

    page_id: str
    session_id: str
    summary: str
    tokens: int
    access_count: int
    source_type: str
    created_at: str

    class Config:
        extra = "allow"


class ContextPageLoadedMessage(BaseWebSocketMessage):
    """上下文页加载消息"""

    type: Literal[MessageType.CONTEXT_PAGE_LOADED] = Field(default=MessageType.CONTEXT_PAGE_LOADED)
    data: ContextPageMessage = Field(..., description="加载的上下文页")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "data": self.data.dict(),
        }


class MemoryEventSerializer:
    """记忆事件序列化器"""

    @staticmethod
    def serialize_memory_created(session_id: str, memory: dict[str, Any]) -> str:
        """序列化记忆创建事件"""
        message = MemoryCreatedMessage(session_id=session_id, data=MemoryEntryMessage(**memory))
        return json.dumps(message.to_dict())

    @staticmethod
    def serialize_memory_retrieved(session_id: str, memory_id: str, access_count: int) -> str:
        """序列化记忆检索事件"""
        message = MemoryRetrievedMessage(
            session_id=session_id,
            data={"memory_id": memory_id, "access_count": access_count},
        )
        return json.dumps(message.to_dict())

    @staticmethod
    def serialize_memory_stats(session_id: str, stats: dict[str, Any]) -> str:
        """序列化记忆统计事件"""
        message = MemoryStatsMessage(session_id=session_id, data=stats)
        return json.dumps(message.to_dict())

    @staticmethod
    def serialize_context_page_loaded(session_id: str, page: dict[str, Any]) -> str:
        """序列化上下文页加载事件"""
        message = ContextPageLoadedMessage(session_id=session_id, data=ContextPageMessage(**page))
        return json.dumps(message.to_dict())


# 协议版本管理
class ProtocolVersion:
    """协议版本管理"""

    CURRENT_VERSION = "1.0.0"
    SUPPORTED_VERSIONS = ["1.0.0"]

    @classmethod
    def is_version_supported(cls, version: str) -> bool:
        """检查版本是否受支持"""
        return version in cls.SUPPORTED_VERSIONS

    @classmethod
    def get_version_compatibility(cls, version: str) -> str:
        """获取版本兼容性"""
        if version == cls.CURRENT_VERSION:
            return "compatible"
        if version in cls.SUPPORTED_VERSIONS:
            return "deprecated"
        return "unsupported"


# 导出主要类和函数（优化后）
__all__ = [
    # 枚举类型
    "MessageType",
    # 基础消息类
    "BaseWebSocketMessage",
    # 具体消息类
    "UserWebSocketMessage",
    "AssistantWebSocketMessage",
    "SystemWebSocketMessage",
    # 移除: ToolWebSocketMessage (使用 TOOL_CALL_* 代替)
    # 移除: TaskStartMessage (使用 TASK_NODE_START 代替)
    # 移除: TaskProgressMessage (使用 TASK_NODE_PROGRESS 代替)
    # 移除: TaskCompleteMessage (使用 TASK_NODE_COMPLETE 代替)
    # 移除: TaskErrorMessage (使用 ERROR 代替)
    "TaskStatusUpdateMessage",
    "TaskGraphUpdateMessage",
    "StreamReasoningMessage",
    "StreamContentMessage",
    "StreamToolCallMessage",
    "StreamUsageMessage",
    "StreamCompleteMessage",
    "StreamErrorMessage",
    "ToolCallStartMessage",
    "ToolCallProgressMessage",
    "ToolCallResultMessage",
    "FollowupQuestionMessage",
    "FollowupResponseMessage",
    "ErrorMessage",
    "WarningMessage",
    "HeartbeatMessage",
    "StateSyncMessage",
    "StateUpdateMessage",
    "ConnectMessage",
    "DisconnectMessage",
    "LLMApiRequestMessage",
    "LLMApiResponseMessage",
    "LLMApiCompleteMessage",
    "LLMApiErrorMessage",
    "AgentStartMessage",
    "AgentModeSwitchMessage",
    "AgentThinkingMessage",
    "AgentCompleteMessage",
    "ModeSwitchMessage",
    "ModeSwitchedMessage",
    "ContextUpdateMessage",
    "PDACycleStartMessage",
    "PDCAStatusUpdateMessage",
    "PDCAPhaseAdvanceMessage",
    "PDACycleCompleteMessage",
    "TaskNodeStartMessage",
    "TaskNodeProgressMessage",
    "TaskNodeCompleteMessage",
    # 联合类型
    "WebSocketMessage",
    # 验证和序列化
    "MessageValidator",
    "MessageSerializer",
    # 事件消息
    "StandardizedEventMessage",
    "EventMessageSerializer",
    # 版本管理
    "ProtocolVersion",
]
