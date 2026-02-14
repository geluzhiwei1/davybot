# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""流式消息处理模块
提供统一的流式响应处理接口，支持多种LLM提供商的流式数据解析
"""

import json
import logging
import time
import uuid
from enum import Enum
from typing import Any, Union

from pydantic import BaseModel, Field

from .lm_messages import ToolCall

logger = logging.getLogger(__name__)


class StreamMessageType(Enum):
    """流式消息类型枚举"""

    REASONING = "reasoning"
    CONTENT = "content"
    TOOL_CALL = "tool_call"
    USAGE = "usage"
    COMPLETE = "complete"
    ERROR = "error"


class BaseStreamMessage(BaseModel):
    """流式消息基类"""

    type: StreamMessageType
    timestamp: float = Field(default_factory=time.time)
    user_message_id: str | None = Field(default="")
    # chunk fields
    id: str | None = Field(default=None)
    created: int | None = Field(default=None)
    object: str | None = Field(default=None)
    model: str | None = Field(default=None)

    class Config:
        use_enum_values = True


class ReasoningMessage(BaseStreamMessage):
    """推理过程消息"""

    type: StreamMessageType = StreamMessageType.REASONING
    content: str


class ContentMessage(BaseStreamMessage):
    """内容消息"""

    type: StreamMessageType = StreamMessageType.CONTENT
    content: str


class ToolCallMessage(BaseStreamMessage):
    """工具调用消息"""

    type: StreamMessageType = StreamMessageType.TOOL_CALL
    tool_call: ToolCall
    all_tool_calls: list[ToolCall]


class UsageMessage(BaseStreamMessage):
    """使用统计消息"""

    type: StreamMessageType = StreamMessageType.USAGE
    data: dict[str, Any]


class CompleteMessage(BaseStreamMessage):
    """完成消息"""

    type: StreamMessageType = StreamMessageType.COMPLETE
    reasoning_content: str | None = None
    content: str | None = None
    tool_calls: list[ToolCall] = []
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None


class ErrorMessage(BaseStreamMessage):
    """错误消息"""

    type: StreamMessageType = StreamMessageType.ERROR
    error: str
    details: dict[str, Any] | None = None


# Union 类型，包含所有流式消息类型
StreamMessages = Union[
    ReasoningMessage,
    ContentMessage,
    ToolCallMessage,
    UsageMessage,
    CompleteMessage,
    ErrorMessage,
]


class BaseObject(BaseModel):
    """OpenAI对象基类，保持向后兼容"""


class ModelResponseBase(BaseObject):
    """模型响应基类，保持向后兼容"""

    id: str
    created: int
    model: str | None = None
    object: str
    system_fingerprint: str | None = None
    _hidden_params: dict = {}
    _response_headers: dict | None = None


class TopLogprob(BaseObject):
    """Top logprob，保持向后兼容"""

    token: str
    bytes: list[int] | None = None
    logprob: float


class ChatCompletionTokenLogprob(BaseObject):
    """Chat completion token logprob，保持向后兼容"""

    token: str
    bytes: list[int] | None = None
    logprob: float
    top_logprobs: list[TopLogprob]

    def __contains__(self, key):
        return hasattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __getitem__(self, key):
        return getattr(self, key)


class ChoiceLogprobs(BaseObject):
    """Choice logprobs，保持向后兼容"""

    content: list[ChatCompletionTokenLogprob] | None = None

    def __contains__(self, key):
        return hasattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __getitem__(self, key):
        return getattr(self, key)


class Function(BaseObject):
    """Function，保持向后兼容"""

    arguments: str
    name: str | None = None

    def __init__(
        self,
        arguments: dict | str | None = None,
        name: str | None = None,
        **params,
    ):
        if arguments is None:
            if params.get("parameters") is not None and isinstance(
                params["parameters"],
                dict,
            ):
                arguments = json.dumps(params["parameters"])
                params.pop("parameters")
            else:
                arguments = ""
        elif isinstance(arguments, dict):
            arguments = json.dumps(arguments)
        else:
            arguments = arguments

        name = name

        # Build a dictionary with structure your BaseModel expects
        data = {"arguments": arguments, "name": name}

        super().__init__(**data)

    def __contains__(self, key):
        return hasattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)


class ChatCompletionDeltaToolCall(BaseObject):
    """Chat completion delta tool call，保持向后兼容"""

    id: str | None = None
    function: Function
    type: str | None = None
    index: int

    def __contains__(self, key):
        return hasattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)


class ChatCompletionMessageToolCall(BaseObject):
    """Chat completion message tool call，保持向后兼容"""

    def __init__(
        self,
        function: dict | Function,
        id: str | None = None,
        type: str | None = None,
        **params,
    ):
        super().__init__(**params)
        if isinstance(function, dict):
            self.function = Function(**function)
        else:
            self.function = function

        if id is not None:
            self.id = id
        else:
            self.id = f"{uuid.uuid4()}"

        if type is not None:
            self.type = type
        else:
            self.type = "function"

    def __contains__(self, key):
        return hasattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)


class Delta(BaseObject):
    """Delta，保持向后兼容"""

    content: str | None = None
    role: str | None = None
    function_call: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    reasoning_content: str | None = None


class StreamingChoices(BaseObject):
    """Streaming choices，保持向后兼容"""

    def __init__(
        self,
        finish_reason=None,
        index=0,
        delta=None,
        logprobs=None,
        enhancements=None,
        **params,
    ):
        # Fix Perplexity return both delta and message cause OpenWebUI repect text
        params.pop("message", None)
        super().__init__(**params)
        if finish_reason:
            self.finish_reason = map_finish_reason(finish_reason)
        else:
            self.finish_reason = None
        self.index = index
        if delta is not None:
            if isinstance(delta, Delta):
                self.delta = delta
            elif isinstance(delta, dict):
                self.delta = Delta(**delta)
        else:
            self.delta = Delta()
        if enhancements is not None:
            self.enhancements = enhancements

        if logprobs is not None and isinstance(logprobs, dict):
            self.logprobs = ChoiceLogprobs(**logprobs)
        else:
            self.logprobs = logprobs

    def __contains__(self, key):
        return hasattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)


class StreamingChatCompletionChunk(BaseObject):
    """Streaming chat completion chunk，保持向后兼容"""

    def __init__(self, **kwargs):
        new_choices = []
        for choice in kwargs["choices"]:
            new_choice = StreamingChoices(**choice).model_dump()
            new_choices.append(new_choice)
        kwargs["choices"] = new_choices

        super().__init__(**kwargs)


class Usage(BaseObject):
    """Usage，保持向后兼容"""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ModelResponseStream(ModelResponseBase):
    """Model response stream，保持向后兼容"""

    choices: list[StreamingChoices]
    provider_specific_fields: dict[str, Any] | None = Field(default=None)

    def __init__(
        self,
        choices: list[StreamingChoices] | StreamingChoices | dict | BaseModel | None = None,
        id: str | None = None,
        created: int | None = None,
        provider_specific_fields: dict[str, Any] | None = None,
        **kwargs,
    ):
        if choices is not None and isinstance(choices, list):
            new_choices = []
            for choice in choices:
                _new_choice = None
                if isinstance(choice, StreamingChoices):
                    _new_choice = choice
                elif isinstance(choice, dict):
                    _new_choice = StreamingChoices(**choice)
                elif isinstance(choice, BaseModel):
                    _new_choice = StreamingChoices(**choice.model_dump())
                new_choices.append(_new_choice)
            kwargs["choices"] = new_choices
        else:
            kwargs["choices"] = [StreamingChoices()]

        id = _generate_id() if id is None else id
        created = int(time.time()) if created is None else created

        if "usage" in kwargs and kwargs["usage"] is not None and isinstance(kwargs["usage"], dict):
            kwargs["usage"] = Usage(**kwargs["usage"])

        kwargs["id"] = id
        kwargs["created"] = created
        kwargs["object"] = "chat.completion.chunk"
        kwargs["provider_specific_fields"] = provider_specific_fields

        super().__init__(**kwargs)

    def __contains__(self, key):
        return hasattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __getitem__(self, key):
        return getattr(self, key)

    def json(self, **_kwargs):  # type: ignore
        try:
            return self.model_dump()
        except Exception:
            # if using pydantic v1
            return self.dict()


# 辅助函数
def map_finish_reason(finish_reason: str) -> str:
    """映射完成原因"""
    mapping = {
        "stop_sequence": "stop",
        "length": "length",
        "tool_calls": "tool_calls",
        "content_filter": "content_filter",
        "function_call": "function_call",
    }
    return mapping.get(finish_reason, finish_reason)


def _generate_id() -> str:
    """生成唯一ID"""
    return f"chatcmpl-{uuid.uuid4().hex[:8]}"


# 导出主要类和函数
__all__ = [
    # 新的流式处理架构
    "StreamMessageType",
    "BaseStreamMessage",
    "ReasoningMessage",
    "ContentMessage",
    "ToolCallMessage",
    "UsageMessage",
    "CompleteMessage",
    "ErrorMessage",
    "StreamMessages",
    # 向后兼容的类
    "BaseObject",
    "ModelResponseBase",
    "TopLogprob",
    "ChatCompletionTokenLogprob",
    "ChoiceLogprobs",
    "Function",
    "ChatCompletionDeltaToolCall",
    "ChatCompletionMessageToolCall",
    "StreamingChoices",
    "StreamingChatCompletionChunk",
    "ModelResponseStream",
]
