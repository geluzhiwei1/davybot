# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timezone
from enum import StrEnum
from typing import Any, Union

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    """消息角色枚举"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ContentType(StrEnum):
    """内容类型枚举"""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"


class TextContent(BaseModel):
    """文本内容"""

    type: ContentType = ContentType.TEXT
    text: str = Field(..., description="文本内容")


class ImageContent(BaseModel):
    """图片内容"""

    type: ContentType = ContentType.IMAGE
    image: str = Field(..., description="图片URL或base64数据")
    detail: str | None = Field("auto", description="图片详细程度: low, high, auto")


class AudioContent(BaseModel):
    """音频内容"""

    type: ContentType = ContentType.AUDIO
    audio: str = Field(..., description="音频URL或base64数据")
    format: str | None = Field(None, description="音频格式")


class VideoContent(BaseModel):
    """视频内容"""

    type: ContentType = ContentType.VIDEO
    video: str = Field(..., description="视频URL或base64数据")
    format: str | None = Field(None, description="视频格式")


class FileContent(BaseModel):
    """文件内容"""

    type: ContentType = ContentType.FILE
    file: str = Field(..., description="文件URL或base64数据")
    filename: str | None = Field(None, description="文件名")
    mime_type: str | None = Field(None, description="MIME类型")


# 内容联合类型
ContentBlock = Union[TextContent, ImageContent, AudioContent, VideoContent, FileContent]


class FunctionCall(BaseModel):
    """函数调用信息"""

    name: str = Field(..., description="函数名称")
    arguments: str = Field(..., description="函数参数,JSON字符串")


class ToolCall(BaseModel):
    """工具调用信息"""

    tool_call_id: str = Field(..., description="工具调用ID")
    type: str = Field(default="function", description="调用类型")
    function: FunctionCall = Field(..., description="函数调用信息")


class BaseLLMMessage(BaseModel, ABC):
    """LLM消息基类,定义所有消息类型的通用接口"""

    id: str | None = Field(None, description="消息唯一标识符(可选)")
    role: MessageRole = Field(..., description="消息角色")
    content: str | list[ContentBlock] | None = Field(
        None,
        description="消息内容,支持文本或多模态内容",
    )
    name: str | None = Field(None, description="发送者名称(可选)")
    tool_call_id: str | None = Field(None, description="工具调用ID(仅tool消息使用)")
    tool_calls: list[ToolCall] | None = Field(
        None,
        description="工具调用列表(仅assistant消息使用)",
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="消息创建时间戳")

    class Config:
        use_enum_values = True
        arbitrary_types_allowed = True

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """将消息转换为字典格式,便于API调用"""

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseLLMMessage":
        """从字典创建消息实例"""

    def to_openai_format(self) -> dict[str, Any]:
        """转换为 OpenAI API 兼容格式"""
        result = {
            "role": self.role.value if hasattr(self.role, "value") else str(self.role),
            "timestamp": self.timestamp.isoformat(),
        }

        # ✅ 添加id字段 (用于前端Markdown切换等UI功能)
        if self.id:
            result["id"] = self.id

        # 处理内容
        if isinstance(self.content, str):
            result["content"] = self.content
        elif isinstance(self.content, list):
            result["content"] = [block.dict() for block in self.content]

        # 添加可选字段
        if self.name:
            result["name"] = self.name
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            # 转换为 OpenAI 格式,将 tool_call_id 映射为 id
            tool_calls_openai = []
            for tool_call in self.tool_calls:
                tool_call_dict = tool_call.dict()
                # 将 tool_call_id 映射为 id 以兼容 OpenAI 格式
                tool_call_dict["id"] = tool_call_dict.pop("tool_call_id")
                tool_calls_openai.append(tool_call_dict)
            result["tool_calls"] = tool_calls_openai

        return result

    @classmethod
    def from_openai_format(cls, data: dict[str, Any]) -> "BaseLLMMessage":
        """从 OpenAI 格式创建消息实例"""
        # 验证输入数据
        if not isinstance(data, dict):
            raise ValueError(f"消息数据必须是字典类型,收到的类型: {type(data).__name__}")

        role_value = data.get("role")
        if role_value is None:
            raise ValueError("消息缺少 'role' 字段")

        try:
            role = MessageRole(role_value)
        except ValueError:
            raise ValueError(f"不支持的消息角色: {role_value}")

        # ✅ 提取id字段 (传递给子类)
        message_id = data.get("id")

        # 根据角色创建相应的消息类型
        if role == MessageRole.USER:
            return UserMessage.from_openai_format(data, message_id=message_id)
        if role == MessageRole.ASSISTANT:
            return AssistantMessage.from_openai_format(data, message_id=message_id)
        if role == MessageRole.SYSTEM:
            return SystemMessage.from_openai_format(data, message_id=message_id)
        if role == MessageRole.TOOL:
            return ToolMessage.from_openai_format(data, message_id=message_id)
        raise ValueError(f"不支持的消息角色: {role}")


class SystemMessage(BaseLLMMessage):
    """系统消息"""

    role: MessageRole = MessageRole.SYSTEM

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_openai_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SystemMessage":
        """从字典创建实例"""
        return cls.from_openai_format(data)

    @classmethod
    def from_openai_format(cls, data: dict[str, Any], message_id: str | None = None) -> "SystemMessage":
        """从 OpenAI 格式创建实例"""
        content = data.get("content", "")

        # 处理时间戳
        timestamp = datetime.now(UTC)
        if "timestamp" in data:
            try:
                if isinstance(data["timestamp"], str):
                    timestamp = datetime.fromisoformat(data["timestamp"])
            except (ValueError, TypeError):
                pass  # 使用默认时间

        return cls(
            id=message_id,  # ✅ 添加id参数
            role=MessageRole.SYSTEM,
            content=content,
            name=data.get("name"),
            timestamp=timestamp,
        )


class UserMessage(BaseLLMMessage):
    """用户消息"""

    role: MessageRole = MessageRole.USER

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_openai_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserMessage":
        """从字典创建实例"""
        return cls.from_openai_format(data)

    @classmethod
    def from_openai_format(cls, data: dict[str, Any], message_id: str | None = None) -> "UserMessage":
        """从 OpenAI 格式创建实例"""
        content = data.get("content", "")

        # 处理时间戳
        timestamp = datetime.now(UTC)
        if "timestamp" in data:
            try:
                if isinstance(data["timestamp"], str):
                    timestamp = datetime.fromisoformat(data["timestamp"])
            except (ValueError, TypeError):
                pass  # 使用默认时间

        # 如果内容是字符串,保持原样
        if isinstance(content, str):
            return cls(
                id=message_id,  # ✅ 添加id参数
                role=MessageRole.USER,
                content=content,
                name=data.get("name"),
                timestamp=timestamp,
            )

        # 如果内容是列表,转换为 ContentBlock 对象
        if isinstance(content, list):
            content_blocks = []
            for item in content:
                content_type = item.get("type")
                if content_type == "text":
                    content_blocks.append(TextContent(text=item.get("text", "")))
                elif content_type == "image":
                    content_blocks.append(
                        ImageContent(
                            image=item.get("image", ""),
                            detail=item.get("detail", "auto"),
                        ),
                    )
                elif content_type == "audio":
                    content_blocks.append(
                        AudioContent(audio=item.get("audio", ""), format=item.get("format")),
                    )
                elif content_type == "video":
                    content_blocks.append(
                        VideoContent(video=item.get("video", ""), format=item.get("format")),
                    )
                elif content_type == "file":
                    content_blocks.append(
                        FileContent(
                            file=item.get("file", ""),
                            filename=item.get("filename"),
                            mime_type=item.get("mime_type"),
                        ),
                    )

            return cls(
                id=message_id,  # ✅ 添加id参数
                role=MessageRole.USER,
                content=content_blocks,
                name=data.get("name"),
                timestamp=timestamp,
            )
        return None


class AssistantMessage(BaseLLMMessage):
    """助手消息"""

    role: MessageRole = MessageRole.ASSISTANT

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_openai_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssistantMessage":
        """从字典创建实例"""
        return cls.from_openai_format(data)

    @classmethod
    def from_openai_format(cls, data: dict[str, Any], message_id: str | None = None) -> "AssistantMessage":
        """从 OpenAI 格式创建实例"""
        content = data.get("content", "")

        # 确保content不是None(空字符串是有效的,特别是对于有tool_calls的消息)
        if content is None:
            content = ""

        # 处理时间戳
        timestamp = datetime.now(UTC)
        if "timestamp" in data:
            try:
                if isinstance(data["timestamp"], str):
                    timestamp = datetime.fromisoformat(data["timestamp"])
            except (ValueError, TypeError):
                pass  # 使用默认时间

        # 处理工具调用
        tool_calls = None
        if data.get("tool_calls"):
            tool_calls = []
            for tool_call_data in data.get("tool_calls"):
                function_data = tool_call_data.get("function", {})
                # 支持 OpenAI 格式 (id) 和内部格式 (tool_call_id)
                call_id = tool_call_data.get("id") or tool_call_data.get("tool_call_id", "")
                tool_calls.append(
                    ToolCall(
                        tool_call_id=call_id,
                        type=tool_call_data.get("type", "function"),
                        function=FunctionCall(
                            name=function_data.get("name", ""),
                            arguments=function_data.get("arguments", "{}"),
                        ),
                    ),
                )

        return cls(
            id=message_id,  # ✅ 添加id参数
            role=MessageRole.ASSISTANT,
            content=content,
            tool_calls=tool_calls,
            timestamp=timestamp,
        )


class ToolMessage(BaseLLMMessage):
    """工具消息"""

    role: MessageRole = MessageRole.TOOL

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return self.to_openai_format()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolMessage":
        """从字典创建实例"""
        return cls.from_openai_format(data)

    @classmethod
    def from_openai_format(cls, data: dict[str, Any], message_id: str | None = None) -> "ToolMessage":
        """从 OpenAI 格式创建实例"""
        # 处理时间戳
        timestamp = datetime.now(UTC)
        if "timestamp" in data:
            try:
                if isinstance(data["timestamp"], str):
                    timestamp = datetime.fromisoformat(data["timestamp"])
            except (ValueError, TypeError):
                pass  # 使用默认时间

        return cls(
            id=message_id,  # ✅ 添加id参数
            role=MessageRole.TOOL,
            content=data.get("content", ""),
            tool_call_id=data.get("tool_call_id", ""),
            name=data.get("name"),
            timestamp=timestamp,
        )


# LLM消息联合类型
LLMMessage = Union[SystemMessage, UserMessage, AssistantMessage, ToolMessage]


class ChatGeneration(BaseModel):
    """聊天生成结果类,封装单次生成的信息"""

    message: AssistantMessage = Field(..., description="生成的AI消息")
    generation_info: dict[str, Any] | None = Field(None, description="生成信息")
    text: str | None = Field(None, description="生成的文本内容")
    finish_reason: str | None = Field(None, description="完成原因")
    index: int = Field(default=0, description="生成结果的索引")

    def __init__(self, **data):
        super().__init__(**data)
        # 如果没有提供text,从message中提取
        if self.text is None and self.message:
            self.text = self.message.content

    @property
    def content(self) -> str:
        """获取消息内容"""
        return self.message.content if self.message else ""

    @classmethod
    def from_text(cls, text: str, **kwargs) -> "ChatGeneration":
        """从文本创建生成结果的便捷方法

        Args:
            text: 生成的文本内容
            **kwargs: 其他参数

        Returns:
            ChatGeneration实例

        """
        message = AssistantMessage(content=text)
        return cls(message=message, text=text, **kwargs)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatGeneration":
        """从字典创建实例"""
        message_data = data.get("message", {})
        message = AssistantMessage.from_dict(message_data) if message_data else None

        return cls(
            message=message,
            generation_info=data.get("generation_info"),
            text=data.get("text"),
            finish_reason=data.get("finish_reason"),
            index=data.get("index", 0),
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "message": self.message.to_dict() if self.message else None,
            "generation_info": self.generation_info,
            "text": self.text,
            "finish_reason": self.finish_reason,
            "index": self.index,
        }


class ChatResult(BaseModel):
    """聊天结果类,封装完整的聊天响应"""

    generations: list[ChatGeneration] = Field(..., description="生成结果列表")
    llm_output: dict[str, Any] | None = Field(None, description="LLM输出信息")
    usage: dict[str, Any] | None = Field(None, description="使用统计信息")
    response_metadata: dict[str, Any] | None = Field(None, description="响应元数据")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="创建时间")

    def __init__(self, **data):
        super().__init__(**data)
        # 确保generations不为空
        if not self.generations:
            self.generations = []

    @property
    def text(self) -> str:
        """获取第一个生成结果的文本"""
        return self.generations[0].text if self.generations else ""

    @property
    def first_generation(self) -> ChatGeneration | None:
        """获取第一个生成结果"""
        return self.generations[0] if self.generations else None

    @classmethod
    def from_text(cls, text: str, **kwargs) -> "ChatResult":
        """从文本创建聊天结果的便捷方法

        Args:
            text: 生成的文本内容
            **kwargs: 其他参数

        Returns:
            ChatResult实例

        """
        generation = ChatGeneration.from_text(text)
        return cls(generations=[generation], **kwargs)

    @classmethod
    def from_texts(cls, texts: list[str], **kwargs) -> "ChatResult":
        """从文本列表创建聊天结果的便捷方法

        Args:
            texts: 生成的文本内容列表
            **kwargs: 其他参数

        Returns:
            ChatResult实例

        """
        generations = [ChatGeneration.from_text(text, index=i) for i, text in enumerate(texts)]
        return cls(generations=generations, **kwargs)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatResult":
        """从字典创建实例"""
        generations_data = data.get("generations", [])
        generations = [ChatGeneration.from_dict(gen_data) for gen_data in generations_data]

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return cls(
            generations=generations,
            llm_output=data.get("llm_output"),
            usage=data.get("usage"),
            response_metadata=data.get("response_metadata"),
            created_at=created_at or datetime.now(UTC),
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "generations": [gen.to_dict() for gen in self.generations],
            "llm_output": self.llm_output,
            "usage": self.usage,
            "response_metadata": self.response_metadata,
            "created_at": self.created_at.isoformat(),
        }

    def add_generation(self, generation: ChatGeneration) -> None:
        """添加生成结果"""
        generation.index = len(self.generations)
        self.generations.append(generation)

    def get_generation_by_index(self, index: int) -> ChatGeneration | None:
        """根据索引获取生成结果"""
        for gen in self.generations:
            if gen.index == index:
                return gen
        return None

    def get_all_texts(self) -> list[str]:
        """获取所有生成结果的文本"""
        return [gen.text for gen in self.generations if gen.text]


class LLMResult(BaseModel):
    """LLM结果类,封装更详细的LLM调用信息"""

    results: list[ChatResult] = Field(..., description="聊天结果列表")
    llm_output: dict[str, Any] | None = Field(None, description="LLM输出信息")
    usage: dict[str, Any] | None = Field(None, description="使用统计信息")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="创建时间")

    @property
    def first_result(self) -> ChatResult | None:
        """获取第一个聊天结果"""
        return self.results[0] if self.results else None

    @property
    def text(self) -> str:
        """获取第一个结果的第一个生成文本"""
        if self.first_result and self.first_result.first_generation:
            return self.first_result.first_generation.text
        return ""

    @classmethod
    def from_text(cls, text: str, **kwargs) -> "LLMResult":
        """从文本创建LLM结果的便捷方法"""
        chat_result = ChatResult.from_text(text)
        return cls(results=[chat_result], **kwargs)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LLMResult":
        """从字典创建实例"""
        results_data = data.get("results", [])
        results = [ChatResult.from_dict(result_data) for result_data in results_data]

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return cls(
            results=results,
            llm_output=data.get("llm_output"),
            usage=data.get("usage"),
            created_at=created_at or datetime.now(UTC),
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "results": [result.to_dict() for result in self.results],
            "llm_output": self.llm_output,
            "usage": self.usage,
            "created_at": self.created_at.isoformat(),
        }

    def add_result(self, result: ChatResult) -> None:
        """添加聊天结果"""
        self.results.append(result)


class ToolParameterProperty(BaseModel):
    """工具参数属性"""

    type: str = Field(..., description="参数类型")
    description: str | None = Field(None, description="参数描述")
    enum: list[str] | None = Field(None, description="枚举值列表")
    minimum: int | float | None = Field(None, description="最小值")
    maximum: int | float | None = Field(None, description="最大值")
    items: dict[str, Any] | None = Field(None, description="数组项类型定义")


class ToolParameters(BaseModel):
    """工具参数定义"""

    type: str = Field(default="object", description="参数类型,通常是 object")
    properties: dict[str, ToolParameterProperty] = Field(
        default_factory=dict,
        description="参数属性定义",
    )
    required: list[str] | None = Field(None, description="必需参数列表")


class ToolFunction(BaseModel):
    """工具函数定义"""

    name: str = Field(..., description="函数名称")
    description: str = Field(..., description="函数描述")
    parameters: ToolParameters = Field(..., description="函数参数定义")


class ToolDescriptor(BaseModel):
    """工具描述符"""

    type: str = Field(default="function", description="工具类型")
    function: ToolFunction = Field(..., description="函数定义")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolDescriptor":
        """从字典创建工具描述符"""
        function_data = data.get("function", {})

        # 处理参数
        parameters_data = function_data.get("parameters", {})
        properties_data = parameters_data.get("properties", {})

        # 转换属性定义
        properties = {}
        for prop_name, prop_data in properties_data.items():
            properties[prop_name] = ToolParameterProperty(**prop_data)

        # 创建参数对象
        parameters = ToolParameters(
            type=parameters_data.get("type", "object"),
            properties=properties,
            required=parameters_data.get("required"),
        )

        # 创建函数对象
        function = ToolFunction(
            name=function_data.get("name", ""),
            description=function_data.get("description", ""),
            parameters=parameters,
        )

        return cls(type=data.get("type", "function"), function=function)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        # 转换参数
        properties = {}
        for prop_name, prop_obj in self.function.parameters.properties.items():
            prop_dict = prop_obj.dict(exclude_none=True)
            properties[prop_name] = prop_dict

        parameters = {"type": self.function.parameters.type, "properties": properties}

        if self.function.parameters.required:
            parameters["required"] = self.function.parameters.required

        # 转换函数
        function = {
            "name": self.function.name,
            "description": self.function.description,
            "parameters": parameters,
        }

        # 转换工具描述符
        return {"type": self.type, "function": function}


class ToolsList(BaseModel):
    """工具列表"""

    tools: list[ToolDescriptor] = Field(default_factory=list, description="工具描述符列表")

    @classmethod
    def from_dict(cls, data: list[dict[str, Any]]) -> "ToolsList":
        """从字典列表创建工具列表"""
        tools = [ToolDescriptor.from_dict(tool_data) for tool_data in data]
        return cls(tools=tools)

    def to_dict(self) -> list[dict[str, Any]]:
        """转换为字典列表格式"""
        return [tool.to_dict() for tool in self.tools]

    def add_tool(self, tool: ToolDescriptor) -> None:
        """添加工具"""
        self.tools.append(tool)

    def get_tool_by_name(self, name: str) -> ToolDescriptor | None:
        """根据名称获取工具"""
        for tool in self.tools:
            if tool.function.name == name:
                return tool
        return None
