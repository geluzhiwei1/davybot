# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""WebSocket消息协议定义

定义了WebSocket通信中使用的所有消息类型、验证器和序列化器。
整合了LLM消息模型和流式消息模型，支持多种消息类型和流式传输。
"""

import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from dawei.core.datetime_compat import UTC
from enum import Enum


class StrEnum(str, Enum):
    """String enum for Python 3.10 compatibility"""

    pass


from typing import List, Dict, Any, ClassVar, Literal, Union

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
    CONVERSATION_INFO = "conversation_info"  # 会话信息(包含conversation_id)

    # ==================== 任务节点管理（Task Graph级别）====================
    TASK_NODE_START = "task_node_start"  # 任务节点开始执行
    TASK_NODE_PROGRESS = "task_node_progress"  # 任务节点进度更新
    TASK_NODE_COMPLETE = "task_node_complete"  # 任务节点完成
    TASK_STATUS_UPDATE = "task_status_update"  # 任务状态更新
    TASK_GRAPH_UPDATE = "task_graph_update"  # 任务图更新
    SUBTASK_LIFECYCLE = "subtask_lifecycle"  # 子任务生命周期事件（created/started/completed/failed/aborted/steered）
    SUBTASK_PROGRESS = "subtask_progress"  # 子任务 todo 步级进度事件（C25，纯 UI 态不进会话历史）

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
    FOLLOWUP_CANCEL = "followup_cancel"  # 前端取消追问

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
    AGENT_STATUS_UPDATE = "agent_status_update"  # Agent 状态更新（含退化信息、trace信息等）
    MARKET_AGENT_STATUS = "market_agent_status"  # MarketingAgent 编队子智能体状态（E1 徽标驱动）
    SOCIAL_AGENT_STATUS = "social_agent_status"  # SocialAgent 编队子智能体状态（E1 徽标驱动，镜像 market）
    RESEARCH_AGENT_STATUS = "research_agent_status"  # GeluResearch 编队子智能体状态（E1 徽标驱动，镜像 market/social）
    AGENT_SPAN = "agent_span"  # Agent 执行追踪 Span（全链路可观测）

    # ==================== Agent 间通信 (Phase 4: multi-agent messaging) ====================
    INTER_AGENT_MESSAGE = "inter_agent_message"  # Agent 间消息传递

    # ==================== Agent 控制消息 ====================
    AGENT_STOP = "agent_stop"  # 停止 Agent 执行

    # ==================== 会话控制消息 ====================
    RESET_CONVERSATION = "reset_conversation"  # 重置会话（清空消息 + 新建对话）

    # ==================== 任务节点控制消息 ====================
    TASK_NODE_STOP = "task_node_stop"  # 停止任务节点

    # ==================== Agent 模式控制（====================
    MODE_SWITCH = "mode_switch"  # 切换 Agent 模式（plan/build）
    MODE_SWITCHED = "mode_switched"  # 模式切换完成确认
    TASK_NODE_STOPPED = "task_node_stopped"  # 任务节点已停止
    TODO_UPDATE = "todo_update"  # TODO列表更新
    TOOL_APPROVAL_REQUEST = "tool_approval_request"  # 后端→前端：工具执行前请求人工确认（P2.2）
    TOOL_APPROVAL_RESPONSE = "tool_approval_response"  # 前端→后端：人工确认回复

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
    conversation_id: str | None = Field(None, description="会话ID，用于前端路由消息到正确的对话")
    user_message_id: str | None = Field(None, description="用户消息ID")
    task_node_id: str | None = Field(
        None,
        description="任务节点ID，表示是哪个task node发送出的消息（可选）",
    )

    class Config:
        use_enum_values = True
        extra = "forbid"  # 禁止额外字段，确保严格验证

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """将消息转换为字典格式"""

    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseWebSocketMessage":
        """从字典创建消息实例"""

    def to_websocket_format(self) -> Dict[str, Any]:
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
    metadata: Dict[str, Any] | None = Field(None, description="消息元数据")
    user_ui_context: Dict[str, Any] | None = Field(None, description="用户UI上下文信息")
    knowledge_base_ids: List[str] | None = Field(None, description="选中的知识库ID列表")
    # P3 定向插话（F7）：目标子任务节点 ID。None = 广播式镜像到全部运行中
    # 隔离子任务（P1a 语义）；非空 = 只注入该节点，其余子任务不牵连。
    target_subtask_id: str | None = Field(None, description="定向插话：目标子任务节点ID；None=广播")

    @field_validator("content")
    @classmethod
    def validate_content(cls, v):
        if not v or not v.strip():
            raise ValueError("消息内容不能为空")
        return v.strip()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserWebSocketMessage":
        """从字典创建实例"""
        return cls(**data)


class AssistantWebSocketMessage(BaseWebSocketMessage):
    """助手WebSocket消息，整合AssistantMessage"""

    type: MessageType = MessageType.ASSISTANT_MESSAGE
    content: str = Field(..., description="助手消息内容")
    task_id: str | None = Field(None, description="关联的任务ID")
    metadata: Dict[str, Any] | None = Field(None, description="消息元数据")
    tool_calls: List[ToolCall] | None = Field(None, description="工具调用列表")

    def to_dict(self) -> Dict[str, Any]:
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
    def from_dict(cls, data: Dict[str, Any]) -> "AssistantWebSocketMessage":
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
    metadata: Dict[str, Any] | None = Field(None, description="消息元数据")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SystemWebSocketMessage":
        """从字典创建实例"""
        return cls(**data)


class ConversationInfoMessage(BaseWebSocketMessage):
    """会话信息消息,用于向前端同步conversation_id"""

    type: MessageType = MessageType.CONVERSATION_INFO
    conversation_id: str = Field(..., description="会话ID")
    title: str | None = Field(None, description="会话标题")
    created_at: str | None = Field(None, description="创建时间(ISO格式)")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationInfoMessage":
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

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskStatusUpdateMessage":
        """从字典创建实例"""
        return cls(**data)


class TaskGraphUpdateMessage(BaseWebSocketMessage):
    """任务图更新消息"""

    type: MessageType = MessageType.TASK_GRAPH_UPDATE
    graph_id: str = Field(..., description="任务图ID")
    update_type: str = Field(..., description="更新类型")
    data: Dict[str, Any] = Field(..., description="更新数据")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="更新时间戳",
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskGraphUpdateMessage":
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

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StreamReasoningMessage":
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
        event_data: Dict[str, Any],
        session_id: str,
        task_id: str,
        conversation_id: str | None = None,
    ) -> "StreamReasoningMessage":
        """从事件数据创建消息"""
        return cls(
            session_id=session_id,
            task_id=task_id,
            task_node_id=event_data.get("task_node_id"),  # 🔧 添加 task_node_id
            message_id=event_data.get("message_id"),
            content=event_data.get("content", ""),
            conversation_id=conversation_id,
        )


class StreamContentMessage(BaseWebSocketMessage):
    """流式内容消息，整合ContentMessage"""

    type: MessageType = MessageType.STREAM_CONTENT
    task_id: str = Field(..., description="任务ID")
    task_node_id: str | None = Field(None, description="任务节点ID")
    message_id: str | None = Field(None, description="消息ID，用于标识单个消息气泡")
    content: str = Field(..., description="流式内容片段")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StreamContentMessage":
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
        event_data: Dict[str, Any],
        session_id: str,
        task_id: str,
        conversation_id: str | None = None,
    ) -> "StreamContentMessage":
        """从事件数据创建消息"""
        message_id = event_data.get("message_id")
        return cls(
            session_id=session_id,
            task_id=task_id,
            task_node_id=event_data.get("task_node_id"),  # 🔧 添加 task_node_id
            message_id=message_id,
            content=event_data.get("content", ""),
            conversation_id=conversation_id,
        )


class StreamToolCallMessage(BaseWebSocketMessage):
    """流式工具调用消息，整合ToolCallMessage"""

    type: MessageType = MessageType.STREAM_TOOL_CALL
    task_id: str = Field(..., description="任务ID")
    task_node_id: str | None = Field(None, description="任务节点ID")  # 🔧 新增：任务节点ID字段
    tool_call: ToolCall = Field(..., description="工具调用信息")
    all_tool_calls: List[ToolCall] = Field(default_factory=list, description="所有工具调用")
    user_message_id: str | None = Field(None, description="用户消息ID")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = self.to_websocket_format()

        # 直接使用 tool_call_id，不进行映射
        result["tool_call"] = self.tool_call.dict()
        result["all_tool_calls"] = [tool_call.dict() for tool_call in self.all_tool_calls]

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StreamToolCallMessage":
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
    data: Dict[str, Any] = Field(..., description="使用统计数据")
    user_message_id: str | None = Field(None, description="用户消息ID")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StreamUsageMessage":
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
        event_data: Dict[str, Any],
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
    tool_calls: List[ToolCall] = Field(default_factory=list, description="工具调用列表")
    finish_reason: str | None = Field(None, description="完成原因")
    usage: Dict[str, Any] | None = Field(None, description="使用统计")
    user_message_id: str | None = Field(None, description="用户消息ID")
    conversation_id: str | None = Field(None, description="会话ID")

    def to_dict(self) -> Dict[str, Any]:
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
    def from_dict(cls, data: Dict[str, Any]) -> "StreamCompleteMessage":
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
            conversation_id=data.get("conversation_id"),
        )

    @classmethod
    def from_stream_message(
        cls,
        stream_msg: CompleteMessage,
        session_id: str,
        task_id: str,
        conversation_id: str | None = None,
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
            conversation_id=conversation_id,
        )

    @classmethod
    def from_event_data(
        cls,
        event_data: Dict[str, Any],
        session_id: str,
        task_id: str,
        conversation_id: str | None = None,
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
            conversation_id=conversation_id,
        )


class StreamErrorMessage(BaseWebSocketMessage):
    """流式错误消息，整合StreamErrorMessage"""

    type: MessageType = MessageType.STREAM_ERROR
    task_id: str = Field(..., description="任务ID")
    task_node_id: str | None = Field(None, description="任务节点ID")
    error: str = Field(..., description="错误信息")
    details: Dict[str, Any] | None = Field(None, description="错误详情")
    user_message_id: str | None = Field(None, description="用户消息ID")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StreamErrorMessage":
        """从字典创建实例"""
        return cls(**data)

    @classmethod
    def from_stream_message(
        cls,
        stream_msg: StreamErrorMessage | Dict[str, Any],
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
    suggestions: List[str] = Field(default_factory=list, description="建议答案列表")
    tool_call_id: str = Field(..., description="工具调用ID，用于响应对应")
    user_message_id: str | None = Field(None, description="用户消息ID")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FollowupQuestionMessage":
        """从字典创建实例"""
        return cls(**data)


class FollowupResponseMessage(BaseWebSocketMessage):
    """前端向后端发送的追问回复消息"""

    type: MessageType = MessageType.FOLLOWUP_RESPONSE
    task_id: str = Field(..., description="任务ID")
    tool_call_id: str = Field(..., description="工具调用ID")
    response: str = Field(..., description="用户回复内容")
    user_message_id: str | None = Field(None, description="用户消息ID")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FollowupResponseMessage":
        """从字典创建实例"""
        return cls(**data)


class FollowupCancelMessage(BaseWebSocketMessage):
    """前端向后端发送的追问取消消息"""

    type: MessageType = MessageType.FOLLOWUP_CANCEL
    task_id: str = Field(..., description="任务ID")
    tool_call_id: str = Field(..., description="工具调用ID")
    reason: Literal["user_cancelled", "timeout", "skipped"] = Field(default="user_cancelled", description="取消原因")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FollowupCancelMessage":
        """从字典创建实例"""
        return cls(**data)


class ToolApprovalRequestMessage(BaseWebSocketMessage):
    """后端→前端：工具执行前请求人工确认（P2.2 审批工作流）"""

    type: MessageType = MessageType.TOOL_APPROVAL_REQUEST
    request_id: str = Field(..., description="审批请求唯一ID，用于响应对应")
    task_id: str | None = Field(None, description="任务ID")
    tool_name: str = Field(..., description="待确认工具名")
    risk: str = Field(..., description="风险等级 low/medium/high/critical")
    tool_input: Dict[str, Any] = Field(default_factory=dict, description="工具输入参数（已脱敏）")
    timeout_seconds: float = Field(default=120.0, description="等待确认超时秒数")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolApprovalRequestMessage":
        """从字典创建实例"""
        return cls(**data)


class ToolApprovalResponseMessage(BaseWebSocketMessage):
    """前端→后端：人工确认回复（批准/拒绝）"""

    type: MessageType = MessageType.TOOL_APPROVAL_RESPONSE
    request_id: str = Field(..., description="对应审批请求ID")
    approved: bool = Field(..., description="是否批准执行")
    reason: str | None = Field(None, description="拒绝原因")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolApprovalResponseMessage":
        """从字典创建实例"""
        return cls(**data)


class ToolCallStartMessage(BaseWebSocketMessage):
    """工具调用开始消息"""

    type: MessageType = MessageType.TOOL_CALL_START
    task_id: str = Field(..., description="任务ID")
    tool_name: str = Field(..., description="工具名称")
    tool_input: Dict[str, Any] = Field(..., description="工具输入参数")
    tool_call_id: str | None = Field(None, description="工具调用ID")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolCallStartMessage":
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

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolCallProgressMessage":
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
    performance_metrics: Dict[str, Any] | None = Field(None, description="性能指标")
    workspace_id: str | None = Field(None, description="工作区ID")
    governance: Dict[str, Any] | None = Field(None, description="输出治理元数据（截断/快照信息）")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolCallResultMessage":
        """从字典创建实例"""
        return cls(**data)


class ErrorMessage(BaseWebSocketMessage):
    """错误消息"""

    type: MessageType = MessageType.ERROR
    code: str = Field(..., description="错误代码")
    message: str = Field(..., description="错误消息")
    details: Dict[str, Any] | None = Field(None, description="错误详情")
    recoverable: bool = Field(True, description="是否可恢复")
    conversation_id: str | None = Field(None, description="会话ID，前端按此路由消息")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ErrorMessage":
        """从字典创建实例"""
        return cls(**data)


class WarningMessage(BaseWebSocketMessage):
    """警告消息"""

    type: MessageType = MessageType.WARNING
    code: str = Field(..., description="警告代码")
    message: str = Field(..., description="警告消息")
    details: Dict[str, Any] | None = Field(None, description="警告详情")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WarningMessage":
        """从字典创建实例"""
        return cls(**data)


class HeartbeatMessage(BaseWebSocketMessage):
    """心跳消息

    心跳是轻量级保活消息，对 session_id 和 timestamp 宽容处理：
    - session_id 可缺省（前端可能在 ws_connected 回来之前就发心跳）
    - timestamp 接受 int（毫秒）或 str（ISO 格式）
    """

    type: MessageType = MessageType.HEARTBEAT
    session_id: str = Field(default="", description="会话ID（心跳允许为空）")
    timestamp: str | int = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="消息时间戳（接受 int 或 ISO str）",
    )
    message: str | None = Field(None, description="心跳消息内容")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HeartbeatMessage":
        """从字典创建实例"""
        return cls(**data)


class StateSyncMessage(BaseWebSocketMessage):
    """状态同步消息"""

    type: MessageType = MessageType.STATE_SYNC
    data: Dict[str, Any] = Field(..., description="同步数据")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateSyncMessage":
        """从字典创建实例"""
        return cls(**data)


class StateUpdateMessage(BaseWebSocketMessage):
    """状态更新消息"""

    type: MessageType = MessageType.STATE_UPDATE
    data: Dict[str, Any] = Field(..., description="更新数据")
    path: str | None = Field(None, description="更新路径")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateUpdateMessage":
        """从字典创建实例"""
        return cls(**data)


class ConnectMessage(BaseWebSocketMessage):
    """连接消息"""

    type: MessageType = MessageType.CONNECT
    message: str = Field("连接已建立", description="连接消息")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConnectMessage":
        """从字典创建实例"""
        return cls(**data)


class DisconnectMessage(BaseWebSocketMessage):
    """断开连接消息"""

    type: MessageType = MessageType.DISCONNECT
    reason: str | None = Field(None, description="断开原因")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DisconnectMessage":
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
    metadata: Dict[str, Any] | None = Field(None, description="其他元数据")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMApiRequestMessage":
        """从字典创建实例"""
        return cls(**data)


class LLMApiResponseMessage(BaseWebSocketMessage):
    """LLM API 响应消息（流式）"""

    type: MessageType = MessageType.LLM_API_RESPONSE
    task_id: str = Field(..., description="任务ID")
    response_type: str = Field(..., description="响应类型 (reasoning, content, tool_call, usage)")
    content: str | None = Field(None, description="响应内容")
    data: Dict[str, Any] | None = Field(None, description="响应数据（用于tool_call等复杂类型）")
    is_streaming: bool = Field(True, description="是否为流式响应")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMApiResponseMessage":
        """从字典创建实例"""
        return cls(**data)


class LLMApiCompleteMessage(BaseWebSocketMessage):
    """LLM API 调用完成消息"""

    type: MessageType = MessageType.LLM_API_COMPLETE
    task_id: str = Field(..., description="任务ID")
    provider: str = Field(..., description="LLM提供商")
    model: str = Field(..., description="模型名称")
    finish_reason: str | None = Field(None, description="完成原因 (stop, length, tool_calls等)")
    usage: Dict[str, Any] | None = Field(None, description="Token使用统计")
    duration_ms: int | None = Field(None, description="请求耗时（毫秒）")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMApiCompleteMessage":
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
    details: Dict[str, Any] | None = Field(None, description="错误详情")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMApiErrorMessage":
        """从字典创建实例"""
        return cls(**data)


class AgentStartMessage(BaseWebSocketMessage):
    """Agent 开始执行消息"""

    type: MessageType = MessageType.AGENT_START
    task_id: str = Field(..., description="任务ID")
    agent_mode: str = Field(..., description="Agent模式 ")
    user_message: str = Field(..., description="用户原始消息")
    workspace_id: str = Field(..., description="工作区ID")
    metadata: Dict[str, Any] | None = Field(None, description="其他元数据")
    degraded_features: Dict[str, Any] | None = Field(None, description="退化的功能及原因（如 memory 初始化失败）")
    trace_id: str | None = Field(None, description="全链路追踪 trace_id")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentStartMessage":
        """从字典创建实例"""
        return cls(**data)


class AgentSpanMessage(BaseWebSocketMessage):
    """Agent 执行追踪 Span — 全链路可观测性"""

    type: MessageType = MessageType.AGENT_SPAN
    workspace_id: str | None = Field(None, description="工作区ID（用于前端路由追踪数据）")
    trace_id: str = Field(..., description="全链路 trace_id")
    span_id: str = Field(..., description="Span ID")
    parent_span_id: str | None = Field(None, description="父 Span ID")
    span_name: str = Field(..., description="Span 名称（如 plan/do/check/act/llm_call/tool_call）")
    phase: str | None = Field(None, description="所属阶段（plan/do/check/act）")
    start_time: str = Field(..., description="开始时间 ISO")
    end_time: str | None = Field(None, description="结束时间 ISO")
    duration_ms: int | None = Field(None, description="耗时（毫秒）")
    status: str = Field("running", description="Span 状态: running/success/error")
    input_summary: str | None = Field(None, description="输入摘要（截断）")
    output_summary: str | None = Field(None, description="输出摘要（截断）")
    metadata: Dict[str, Any] | None = Field(None, description="额外元数据")

    def to_dict(self) -> Dict[str, Any]:
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentSpanMessage":
        return cls(**data)


class AgentStatusUpdateMessage(BaseWebSocketMessage):
    """Agent 状态更新（含退化信息）"""

    type: MessageType = MessageType.AGENT_STATUS_UPDATE
    task_id: str | None = Field(None, description="任务ID")
    degraded_features: Dict[str, Any] = Field(default_factory=dict, description="退化的功能及原因")
    memory_ready: bool | None = Field(None, description="记忆系统是否已就绪")
    trace_id: str | None = Field(None, description="当前 trace_id")

    def to_dict(self) -> Dict[str, Any]:
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentStatusUpdateMessage":
        return cls(**data)


class InterAgentMessage(BaseWebSocketMessage):
    """Agent 间消息传递 (Phase 4: 多Agent协作通信)

    Agent A 发送消息给 Agent B，例如 "审核完毕，请生成报告"。
    前端可折叠/展开多 Agent 对话。
    """

    type: MessageType = MessageType.INTER_AGENT_MESSAGE
    task_id: str = Field(..., description="任务ID")
    from_agent_id: str = Field(..., description="发送方 Agent ID")
    to_agent_id: str = Field(..., description="接收方 Agent ID")
    content: str = Field(..., description="消息内容")
    message_type: str = Field("task_handoff", description="消息类型: task_handoff/query/approval/info")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="附加元数据")

    def to_dict(self) -> Dict[str, Any]:
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InterAgentMessage":
        return cls(**data)


class AgentModeSwitchMessage(BaseWebSocketMessage):
    """Agent 模式切换消息"""

    type: MessageType = MessageType.AGENT_MODE_SWITCH
    task_id: str = Field(..., description="任务ID")
    old_mode: str = Field(..., description="旧模式")
    new_mode: str = Field(..., description="新模式")
    reason: str = Field(..., description="切换原因")
    metadata: Dict[str, Any] | None = Field(None, description="其他元数据")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentModeSwitchMessage":
        """从字典创建实例"""
        return cls(**data)


class AgentThinkingMessage(BaseWebSocketMessage):
    """Agent 思考过程消息"""

    type: MessageType = MessageType.AGENT_THINKING
    task_id: str = Field(..., description="任务ID")
    thinking_content: str = Field(..., description="思考内容")
    step_id: str | None = Field(None, description="思考步骤ID")
    is_complete: bool = Field(False, description="是否完成")
    metadata: Dict[str, Any] | None = Field(None, description="其他元数据")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentThinkingMessage":
        """从字典创建实例"""
        return cls(**data)


class AgentCompleteMessage(BaseWebSocketMessage):
    """Agent 完成执行消息"""

    type: MessageType = MessageType.AGENT_COMPLETE
    task_id: str = Field(..., description="任务ID")
    result_summary: str = Field(..., description="结果摘要")
    total_duration_ms: int = Field(..., description="总耗时（毫秒）")
    tasks_completed: int = Field(0, description="完成任务数")
    tools_used: List[str] = Field(default_factory=list, description="使用的工具列表")
    conversation_id: str | None = Field(None, description="会话ID（用于新建会话时返回给前端）")
    metadata: Dict[str, Any] | None = Field(None, description="其他元数据")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentCompleteMessage":
        """从字典创建实例"""
        return cls(**data)


class MarketAgentStatusMessage(BaseWebSocketMessage):
    """MarketingAgent 编队子智能体状态消息(E1 徽标驱动,设计 project/MarkkeAgent-prd.md §11.2)。

    前端契约(monitoring-ws.ts case "market_agent_status"):
      { type, data: { expert_id, status, last_action? } }
    status ∈ idle|online|thinking|tool;expert_id 与 market-team modes.yaml slug 对齐
    (mkt-orchestrator / mkt-*-scout 等 §4.8 新 slug)。
    真实可观测状态:tool(market 工具被调用)/idle(chat 任务结束);thinking/online
    由前端 DEV 演示模拟(无 LLM 流级钩子,不伪造)。
    """

    type: MessageType = MessageType.MARKET_AGENT_STATUS
    expert_id: str = Field(..., description="子智能体 mode slug(mkt-orchestrator / mkt-* 等)")
    status: str = Field("idle", description="idle | online | thinking | tool")
    last_action: str | None = Field(None, description="最近动作(如工具名)")
    # 前端(monitoring-ws.ts)按 msg.data 读取(与 task_node_* 同款契约)——
    # 平铺字段与 data 双写,兼容两种消费方式。
    data: Dict[str, Any] | None = Field(None, description="同平铺字段的 dict 形式({expert_id,status,last_action})")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarketAgentStatusMessage":
        """从字典创建实例"""
        return cls(**data)


class SocialAgentStatusMessage(BaseWebSocketMessage):
    """SocialAgent 编队子智能体状态消息(E1 徽标驱动,镜像 MarketAgentStatusMessage)。

    前端契约(monitoring-ws.ts case "social_agent_status"):
      { type, data: { expert_id, status, last_action? } }
    status ∈ idle|online|thinking|tool;expert_id 与 social-team modes.yaml slug 对齐
    (soc-orchestrator / soc-* 等 §4.8 新 slug)。
    真实可观测状态:tool(social 工具被调用)/idle(chat 任务结束);thinking/online
    由前端 DEV 演示模拟(无 LLM 流级钩子,不伪造)。
    """

    type: MessageType = MessageType.SOCIAL_AGENT_STATUS
    expert_id: str = Field(..., description="子智能体 mode slug(soc-orchestrator / soc-* 等)")
    status: str = Field("idle", description="idle | online | thinking | tool")
    last_action: str | None = Field(None, description="最近动作(如工具名)")
    # 前端(monitoring-ws.ts)按 msg.data 读取(与 task_node_* 同款契约)——
    # 平铺字段与 data 双写,兼容两种消费方式。
    data: Dict[str, Any] | None = Field(None, description="同平铺字段的 dict 形式({expert_id,status,last_action})")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SocialAgentStatusMessage":
        """从字典创建实例"""
        return cls(**data)


class ResearchAgentStatusMessage(BaseWebSocketMessage):
    """GeluResearch 编队子智能体状态消息(E1 徽标驱动,镜像 SocialAgentStatusMessage)。

    前端契约(monitoring-ws.ts case "research_agent_status"):
      { type, data: { expert_id, status, last_action? } }
    status ∈ idle|online|thinking|tool;expert_id 与 gelu-research-team modes.yaml slug
    对齐(paper-orchestrator / peer-review / quality-gate / quality-assurance /
    submission-expert / data-steward-expert,编队成员表= research_fleet.RESEARCH_TEAM_MODES)。
    真实可观测状态:tool(research 工具被调用)/idle(chat 任务结束);thinking/online
    由前端 DEV 演示模拟(无 LLM 流级钩子,不伪造)。
    """

    type: MessageType = MessageType.RESEARCH_AGENT_STATUS
    expert_id: str = Field(..., description="子智能体 mode slug(submission-expert / peer-review 等)")
    status: str = Field("idle", description="idle | online | thinking | tool")
    last_action: str | None = Field(None, description="最近动作(如工具名)")
    # 前端(monitoring-ws.ts)按 msg.data 读取(与 task_node_* 同款契约)——
    # 平铺字段与 data 双写,兼容两种消费方式。
    data: Dict[str, Any] | None = Field(None, description="同平铺字段的 dict 形式({expert_id,status,last_action})")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchAgentStatusMessage":
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

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentStopMessage":
        """从字典创建实例"""
        return cls(**data)


class AgentStoppedMessage(BaseWebSocketMessage):
    """Agent 已停止状态通知（后端 -> 前端）

    注意：type 必须是 AGENT_STOPPED（"agent_stopped"），与请求消息
    AgentStopMessage（type=AGENT_STOP）区分开，否则前端无法把"停止确认"
    当作独立的收尾事件来路由（会与请求消息同名而被误判/忽略）。
    """

    type: MessageType = MessageType.AGENT_STOPPED
    task_id: str = Field(..., description="任务ID")
    conversation_id: str | None = Field(
        None,
        description="会话ID（前端按 conversation_id 路由收尾，缺失则回退 task_id）",
    )
    stopped_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="停止时间",
    )
    result_summary: str = Field(..., description="停止时的结果摘要")
    partial: bool = Field(True, description="是否为部分完成（未完全执行）")
    metadata: Dict[str, Any] | None = Field(None, description="其他元数据")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentStoppedMessage":
        """从字典创建实例"""
        return cls(**data)


class TaskNodeStartMessage(BaseWebSocketMessage):
    """任务节点开始执行消息"""

    type: MessageType = MessageType.TASK_NODE_START
    task_id: str = Field(..., description="任务ID")
    task_node_id: str = Field(..., description="节点ID")
    node_type: str = Field(..., description="节点类型")
    description: str = Field(..., description="节点描述")
    metadata: Dict[str, Any] | None = Field(None, description="其他元数据")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskNodeStartMessage":
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
    data: Dict[str, Any] | None = Field(None, description="进度数据")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskNodeProgressMessage":
        """从字典创建实例"""
        return cls(**data)


class TaskNodeCompleteMessage(BaseWebSocketMessage):
    """任务节点完成消息"""

    type: MessageType = MessageType.TASK_NODE_COMPLETE
    task_id: str = Field(..., description="任务ID")
    task_node_id: str = Field(..., description="节点ID")
    result: Any | None = Field(None, description="执行结果")
    duration_ms: int = Field(..., description="耗时（毫秒）")
    metadata: Dict[str, Any] | None = Field(None, description="其他元数据")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskNodeCompleteMessage":
        """从字典创建实例"""
        return cls(**data)


class SubtaskLifecycleMessage(BaseWebSocketMessage):
    """子任务生命周期事件消息（§6.2 UI 协议：P3-6 事件 → 前端任务树增量更新）"""

    type: MessageType = MessageType.SUBTASK_LIFECYCLE
    task_id: str = Field(..., description="根/父任务ID")
    subtask_id: str = Field(..., description="子任务节点ID")
    event: str = Field(..., description="生命周期事件名: created/started/completed/failed/aborted/steered")
    status: str | None = Field(None, description="事件时子任务状态")
    parent_id: str | None = Field(None, description="父任务ID")
    agent: str | None = Field(None, description="Agent Profile 名")
    depth: int | None = Field(None, description="派生深度（root=0）")
    metadata: Dict[str, Any] | None = Field(None, description="附加字段（reason/resumed 等）")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubtaskLifecycleMessage":
        """从字典创建实例"""
        return cls(**data)


class SubtaskProgressMessage(BaseWebSocketMessage):
    """子任务 todo 步级进度消息（C25/§3.8：纯 UI 态，不进任何会话历史）

    诚实语义：只报已发生的状态变化（todos 快照），不预测"即将完成"。
    """

    type: MessageType = MessageType.SUBTASK_PROGRESS
    task_id: str = Field(..., description="父任务ID")
    subtask_id: str = Field(..., description="子任务节点ID")
    parent_id: str | None = Field(None, description="父任务ID")
    batch_id: str | None = Field(None, description="批量派发组ID（new_task_batch 展开）")
    item_identity: str | None = Field(None, description="批量条目身份")
    todos: Dict[str, Any] = Field(..., description="todo 步级摘要: {total, completed, current(≤40字)}")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubtaskProgressMessage":
        """从字典创建实例"""
        return cls(**data)


class TodoUpdateMessage(BaseWebSocketMessage):
    """TODO列表更新消息"""

    type: MessageType = MessageType.TODO_UPDATE
    task_node_id: str = Field(..., description="任务节点ID")
    todos: List[Dict[str, Any]] = Field(..., description="TODO列表")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TodoUpdateMessage":
        """从字典创建实例"""
        return cls(**data)


# ==================== 任务节点控制消息 ====================


class TaskNodeStopMessage(BaseWebSocketMessage):
    """停止任务节点消息（前端→后端）"""

    type: MessageType = MessageType.TASK_NODE_STOP
    task_node_id: str = Field(..., description="任务节点ID")
    reason: str | None = Field(None, description="停止原因")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskNodeStopMessage":
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

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskNodeStoppedMessage":
        """从字典创建实例"""
        return cls(**data)


class ModeSwitchMessage(BaseWebSocketMessage):
    """Agent 模式切换消息（前端→后端）

    支持 PDCA 循环模式和传统模式切换
    """

    type: MessageType = MessageType.MODE_SWITCH
    mode: str = Field(..., description="目标模式: orchestrator, pdca")

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v):
        """验证模式名称

        支持的模式:
        - orchestrator: 智能协调者模式（默认）
        - pdca: PDCA 持续改进模式（Plan-Do-Check-Act 自管理循环）
        """
        valid_modes = ["orchestrator", "pdca"]
        if v not in valid_modes:
            raise ValueError(f"Invalid mode: '{v}'. Valid modes: {', '.join(valid_modes)}")
        return v

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModeSwitchMessage":
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

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModeSwitchedMessage":
        """从字典创建实例"""
        return cls(**data)


class ContextUpdateMessage(BaseWebSocketMessage):
    """上下文使用更新消息（后端→前端）"""

    type: MessageType = MessageType.CONTEXT_UPDATE
    stats: Dict[str, Any] = Field(..., description="上下文统计信息")
    warnings: List[str] = Field(default_factory=list, description="警告信息")
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextUpdateMessage":
        """从字典创建实例"""
        return cls(**data)


class PDACycleStartMessage(BaseWebSocketMessage):
    """PDCA 循环开始消息（后端→前端）"""

    type: MessageType = MessageType.PDCA_CYCLE_START
    cycle_id: str = Field(..., description="PDCA 循环 ID")
    domain: str = Field(..., description="任务领域")
    task_description: str = Field(..., description="任务描述")
    task_goals: List[str] = Field(default_factory=list, description="任务目标")
    success_criteria: List[str] = Field(default_factory=list, description="成功标准")
    start_time: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="开始时间",
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PDACycleStartMessage":
        """从字典创建实例"""
        return cls(**data)


class PDCAStatusUpdateMessage(BaseWebSocketMessage):
    """PDCA 状态更新消息（后端→前端）"""

    type: MessageType = MessageType.PDCA_STATUS_UPDATE
    cycle_id: str = Field(..., description="PDCA 循环 ID")
    current_phase: str = Field(..., description="当前阶段 (plan/do/check/act)")
    phases: Dict[str, str] = Field(
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

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PDCAStatusUpdateMessage":
        """从字典创建实例"""
        return cls(**data)


class PDCAPhaseAdvanceMessage(BaseWebSocketMessage):
    """PDCA 阶段推进消息（后端→前端）"""

    type: MessageType = MessageType.PDCA_PHASE_ADVANCE
    cycle_id: str = Field(..., description="PDCA 循环 ID")
    from_phase: str = Field(..., description="源阶段")
    to_phase: str = Field(..., description="目标阶段")
    reason: str = Field(..., description="推进原因")
    phase_data: Dict[str, Any] | None = Field(None, description="阶段数据")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="推进时间",
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PDCAPhaseAdvanceMessage":
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
    next_steps: List[str] | None = Field(None, description="后续步骤")
    start_time: str = Field(..., description="开始时间")
    end_time: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="结束时间",
    )
    duration_seconds: float | None = Field(None, description="总耗时（秒）")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PDACycleCompleteMessage":
        """从字典创建实例"""
        return cls(**data)


# ==================== A2UI 消息类 ====================


class A2UIServerEventMessage(BaseWebSocketMessage):
    """A2UI服务端事件消息（Server → Client）

    用于向前端发送A2UI组件更新、数据模型更新等事件
    """

    type: MessageType = MessageType.A2UI_SERVER_EVENT
    messages: List[Dict[str, Any]] = Field(
        ...,
        description="A2UI消息列表，每个消息包含beginRendering/surfaceUpdate/dataModelUpdate/deleteSurface之一",
    )
    metadata: Dict[str, Any] | None = Field(None, description="可选的元数据（标题、描述等）")
    session_id: str | None = Field(None, description="会话ID")
    task_node_id: str | None = Field(None, description="任务节点ID")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "A2UIServerEventMessage":
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
    context: Dict[str, Any] | None = Field(None, description="操作上下文数据")
    session_id: str | None = Field(None, description="会话ID")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.to_websocket_format()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "A2UIUserActionMessage":
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
    SubtaskLifecycleMessage,
    TodoUpdateMessage,
    # 任务节点控制
    TaskNodeStopMessage,
    TaskNodeStoppedMessage,
    # Agent 模式控制（
    ModeSwitchMessage,
    ModeSwitchedMessage,
    # 上下文管理（
    ContextUpdateMessage,
    # 会话信息
    ConversationInfoMessage,
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
    FollowupCancelMessage,
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
    _message_class_map: ClassVar[Dict[str, type[BaseWebSocketMessage]]] = {
        # 基础消息通信
        MessageType.USER_MESSAGE: UserWebSocketMessage,
        MessageType.ASSISTANT_MESSAGE: AssistantWebSocketMessage,
        MessageType.SYSTEM_MESSAGE: SystemWebSocketMessage,
        MessageType.CONVERSATION_INFO: ConversationInfoMessage,
        # 任务节点管理
        MessageType.TASK_NODE_START: TaskNodeStartMessage,
        MessageType.TASK_NODE_PROGRESS: TaskNodeProgressMessage,
        MessageType.TASK_NODE_COMPLETE: TaskNodeCompleteMessage,
        MessageType.TASK_STATUS_UPDATE: TaskStatusUpdateMessage,
        MessageType.TASK_GRAPH_UPDATE: TaskGraphUpdateMessage,
        MessageType.SUBTASK_LIFECYCLE: SubtaskLifecycleMessage,
        MessageType.SUBTASK_PROGRESS: SubtaskProgressMessage,
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
        MessageType.FOLLOWUP_CANCEL: FollowupCancelMessage,
        MessageType.TOOL_APPROVAL_REQUEST: ToolApprovalRequestMessage,
        MessageType.TOOL_APPROVAL_RESPONSE: ToolApprovalResponseMessage,
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
        MessageType.MARKET_AGENT_STATUS: MarketAgentStatusMessage,
        MessageType.SOCIAL_AGENT_STATUS: SocialAgentStatusMessage,
        MessageType.RESEARCH_AGENT_STATUS: ResearchAgentStatusMessage,
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
    def validate(cls, data: Dict[str, Any]) -> BaseWebSocketMessage | None:
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

        # ── 前端兼容预处理 ──────────────────────────────────────────
        # 前端 (davybot-app) 发送的消息可能与后端模型存在差异：
        #   1. timestamp: 前端发 int 毫秒，后端期望 ISO str
        #   2. session_id: 前端可能不传，后端部分模型要求必填
        #   3. 额外字段: 前端可能传 workspace_id/conversation_id/data 等
        #      后端模型有 extra="forbid"，不接受未定义字段
        data = cls._preprocess_frontend_message(data, message_class)

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
    def _preprocess_frontend_message(
        cls,
        data: Dict[str, Any],
        message_class: type[BaseWebSocketMessage],
    ) -> Dict[str, Any]:
        """预处理前端发来的消息，兼容前后端协议差异。

        处理项：
        1. timestamp: int(毫秒) → str(ISO 8601)
        2. session_id: 缺失时设为空字符串（心跳等轻量消息可省略）
        3. 额外字段: 移除后端模型不认识的字段（extra="forbid"），
           将有价值的字段（conversation_id, workspace_id, data）保留到 metadata。
        """
        data = dict(data)  # shallow copy, 不修改原始数据

        # 1. 修正 timestamp 类型
        ts = data.get("timestamp")
        if isinstance(ts, (int, float)):
            data["timestamp"] = datetime.fromtimestamp(ts / 1000, tz=UTC).isoformat()

        # 2. 补全 session_id
        if "session_id" not in data or data.get("session_id") is None:
            data["session_id"] = ""

        # 3. 收集需要移除的额外字段，有价值的信息保留到 metadata
        model_fields = set(message_class.model_fields.keys())
        # BaseWebSocketMessage 的字段也算已知
        model_fields.update(BaseWebSocketMessage.model_fields.keys())

        extras = {k: data.pop(k) for k in list(data.keys()) if k not in model_fields}
        if extras:
            # Only inject metadata if the target message class accepts it
            # (HeartbeatMessage etc. use extra="forbid" and don't have metadata)
            has_metadata_field = "metadata" in model_fields
            if has_metadata_field:
                metadata = data.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                    data["metadata"] = metadata
                # 将前端传的关键字段映射到 handler 期望的格式
                if "workspace_id" in extras:
                    metadata["workspaceId"] = extras.pop("workspace_id")
                if "conversation_id" in extras:
                    metadata["conversationId"] = extras.pop("conversation_id")
                if "data" in extras:
                    # 前端传的 data 包含 mode/model/expert_id 等配置
                    frontend_data = extras.pop("data")
                    metadata["frontend_data"] = frontend_data
                    # 提取 model 和 auth_token 到 metadata，供 _configure_llm_provider 使用
                    if isinstance(frontend_data, dict):
                        model_id = frontend_data.get("model")
                        if model_id:
                            metadata["requestedModel"] = model_id
                            metadata["current_llm_id"] = model_id
                        auth_token = frontend_data.get("auth_token")
                        if auth_token:
                            metadata["auth_token"] = auth_token
                # 其余额外字段也保留
                if extras:
                    metadata["frontend_extra"] = extras

        return data

    @classmethod
    def get_message_class(cls, message_type: str) -> type[BaseWebSocketMessage] | None:
        """根据消息类型获取对应的消息类"""
        return cls._message_class_map.get(message_type)

    @classmethod
    def validate_user_message(cls, data: Dict[str, Any]) -> bool:
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
    def validate_assistant_message(cls, data: Dict[str, Any]) -> bool:
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
    def validate_task_node_progress_message(cls, data: Dict[str, Any]) -> bool:
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
    def validate_error_message(cls, data: Dict[str, Any]) -> bool:
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
        details: ClassVar[Dict[str, Any] | None] = None,
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
        data: Dict[str, Any] | None = None,
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
        metadata: Dict[str, Any] | None = None,
    ) -> UserWebSocketMessage:
        """创建用户消息"""
        return UserWebSocketMessage(session_id=session_id, content=content, metadata=metadata)

    @staticmethod
    def create_assistant_message(
        session_id: str,
        content: str,
        task_id: str | None = None,
        metadata: Dict[str, Any] | None = None,
        tool_calls: List[ToolCall] | None = None,
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
    data: Dict[str, Any] = Field(..., description="事件数据")
    session_id: str | None = Field(None, description="会话ID")
    timestamp: str | None = Field(None, description="时间戳")

    class Config:
        extra = "allow"  # 允许额外字段


class EventMessageSerializer:
    """事件消息序列化器"""

    @staticmethod
    def serialize(event: str, data: Dict[str, Any], session_id: str | None = None) -> str:
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
    keywords: List[str]
    metadata: Dict[str, Any]

    class Config:
        extra = "allow"


class MemoryCreatedMessage(BaseWebSocketMessage):
    """记忆创建消息"""

    type: Literal[MessageType.MEMORY_ENTRY_CREATED] = Field(
        default=MessageType.MEMORY_ENTRY_CREATED,
    )
    data: MemoryEntryMessage = Field(..., description="创建的记忆条目")

    def to_dict(self) -> Dict[str, Any]:
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
    data: Dict[str, Any] = Field(..., description="检索数据，包含memory_id和access_count")

    def to_dict(self) -> Dict[str, Any]:
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
    data: Dict[str, Any] = Field(..., description="记忆统计数据")

    def to_dict(self) -> Dict[str, Any]:
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

    def to_dict(self) -> Dict[str, Any]:
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
    def serialize_memory_created(session_id: str, memory: Dict[str, Any]) -> str:
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
    def serialize_memory_stats(session_id: str, stats: Dict[str, Any]) -> str:
        """序列化记忆统计事件"""
        message = MemoryStatsMessage(session_id=session_id, data=stats)
        return json.dumps(message.to_dict())

    @staticmethod
    def serialize_context_page_loaded(session_id: str, page: Dict[str, Any]) -> str:
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
    "FollowupCancelMessage",
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
    "AgentSpanMessage",
    "AgentStatusUpdateMessage",
    "InterAgentMessage",
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
    "SubtaskLifecycleMessage",
    "SubtaskProgressMessage",
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
