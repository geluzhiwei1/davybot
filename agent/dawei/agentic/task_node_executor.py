# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""任务执行引擎
负责任务的执行、消息处理和工具调用
"""

import asyncio
import time
from typing import Any

from dawei.agentic.agent_config import Config
from dawei.agentic.checkpoint_manager import (
    CheckpointType,
    IntelligentCheckpointManager,
)
from dawei.config import get_dawei_home
from dawei.core.errors import CheckpointError, LLMError
from dawei.core.events import TaskEventType, emit_typed_event
from dawei.entity.lm_messages import (
    AssistantMessage,
    LLMMessage,
    MessageRole,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from dawei.entity.stream_message import (
    CompleteMessage,
    ContentMessage,
    ErrorMessage,
    ReasoningMessage,
    StreamMessages,
    ToolCallMessage,
    UsageMessage,
)

# 使用内置的 asyncio.timeout (Python 3.11+)
from dawei.entity.task_types import TaskStatus
from dawei.interfaces import IEventBus, ILLMService, IMessageProcessor, IToolCallService
from dawei.logg.logging import get_logger
from dawei.task_graph.task_node import TaskNode
from dawei.task_graph.todo_models import TodoItem, TodoStatus
from dawei.workspace.user_workspace import UserWorkspace

from .tool_message_handler import ToolMessageHandle


class TaskNodeExecutionEngine:
    """任务执行引擎实现
    执行一个node,更新node的状态，todos
    """

    def __init__(
        self,
        task_node: TaskNode,
        user_workspace: UserWorkspace,
        message_processor: IMessageProcessor,
        llm_service: ILLMService,
        tool_call_service: IToolCallService,
        event_bus: IEventBus,
        config: Config,
        agent=None,  # 添加agent引用用于暂停检查
    ):
        """初始化任务执行引擎

        Args:
            task_node: 任务节点实例
            user_workspace: 用户工作区实例
            message_processor: 消息处理器接口实例
            llm_service: LLM 服务接口实例
            tool_call_service: 工具调用服务接口实例
            event_bus: 事件总线接口实例
            config: 统一配置实例
            agent: Agent实例（可选，用于暂停/恢复控制）

        """
        # 直接保存任务节点引用
        self.task_node = task_node
        self._agent = agent  # 保存agent引用

        # 保存其他依赖
        self._user_workspace = user_workspace
        self._message_processor = message_processor
        self._llm_service = llm_service
        self._tool_call_service = tool_call_service
        self._event_bus = event_bus
        self._config = config

        # 初始化其他属性
        self.logger = get_logger(__name__)
        self.execution_task: asyncio.Task | None = None
        self.last_checkpoint_time: float = 0.0
        self.last_cleanup_time: float = time.time()  # 添加清理时间戳

        # 初始化 IntelligentCheckpointManager（使用统一的 WorkspacePersistenceManager）
        self._checkpoint_manager = IntelligentCheckpointManager(
            workspace_path=self._user_workspace.absolute_path,
        )

        # 初始化工具消息处理器
        self._tool_message_handler = ToolMessageHandle(
            task_node=self.task_node,
            user_workspace=self._user_workspace,
            tool_call_service=self._tool_call_service,
            event_bus=self._event_bus,
        )

        # 【关键修复】消息ID追踪 - 为每个流式消息生成唯一ID
        self._current_message_id: str | None = None
        self._message_counter: int = 0

    async def create_task(
        self,
        description: str,
        mode: str = "",
        parent_task_id: str | None = None,
        todos: list[TodoItem] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """创建任务（更新当前任务节点的属性）

        Args:
            description: 任务描述
            mode: 任务模式
            parent_task_id: 父任务ID
            todos: 待办事项列表
            metadata: 任务元数据

        """
        # 更新当前任务节点的属性
        if description:
            self.task_node.update_description(description)
        if mode:
            self.task_node.update_mode(mode)
        if parent_task_id:
            self.task_node.set_parent(parent_task_id)
        if todos:
            self.task_node.data.todos = todos
        if metadata:
            for key, value in metadata.items():
                self.task_node.add_metadata(key, value)

    async def execute_task(self) -> Any | None:
        """执行当前任务节点

        注意: 任务本身没有时间限制,只有LLM请求有超时(通过 process_message 中的 llm_timeout 控制)。
        LLM 超时结合 stream_processor 中的 idle timeout 实现快速失败。

        Returns:
            执行结果

        """
        # 初始化检查点时间
        self.last_checkpoint_time = time.time()

        # 创建执行任务
        self.execution_task = asyncio.create_task(self._run_task_loop())

        result = None  # 初始化 result 变量，避免 CancelledError 时未定义
        try:
            # 任务本身没有超时限制,只通过 LLM 请求超时控制
            result = await self.execution_task
        except asyncio.CancelledError:
            # Task cancelled - log info but don't include stack trace (expected flow)
            self.logger.info(f"Task {self.task_node.task_node_id} was cancelled")
            # 保存检查点
            await self._save_checkpoint_on_pause()
        finally:
            # 清理
            self.execution_task = None

        return result

    async def _save_checkpoint_on_pause(self) -> None:
        """暂停时保存检查点"""
        self.logger.info(f"Saving checkpoint for task {self.task_node.task_node_id} on pause")

        # 保存当前状态到检查点
        task_node = self.task_node
        if task_node:
            state = {
                "task_node_id": task_node.task_node_id,
                "status": "paused",  # 标记为暂停状态
                "mode": task_node.mode,
                "todos": [todo.to_dict() for todo in task_node.data.todos],
                "timestamp": time.time(),
            }

            # 发送检查点创建事件
            await emit_typed_event(
                TaskEventType.CHECKPOINT_CREATED,
                {
                    "checkpoint_id": f"pause_checkpoint_{task_node.task_node_id}_{int(time.time())}",
                    "reason": "pause",
                    "state": state,
                },
                self._event_bus,
                task_id=task_node.task_node_id,
                source="pause",
            )

            self.logger.info(f"Checkpoint saved successfully for task {task_node.task_node_id}")

    async def pause_task(self) -> bool:
        """暂停任务执行

        立即取消正在运行的任务并保存检查点
        """
        if self.execution_task and not self.execution_task.done():
            self.logger.info(f"Cancelling task {self.task_node.task_node_id} for pause")
            self.execution_task.cancel()
            return True
        return False

    async def stream_message_to_event(self, stream_message: StreamMessages) -> None:
        """将流式消息转换为事件并通过事件总线发送
        注意：工具调用现在由 handle_stream_messages 方法处理 CompleteMessage 中的 tool_calls

        Args:
            stream_message: 流式消息

        """
        self.logger.debug(f"Converting stream message to event: {type(stream_message).__name__}")

        # 处理工具调用消息 - 跳过，现在工具调用在 CompleteMessage 中处理
        if isinstance(stream_message, ToolCallMessage):
            self.logger.debug(
                "Skipping tool call message in stream_message_to_event, tool calls will be processed in CompleteMessage",
            )
            return
        # 处理错误消息
        if isinstance(stream_message, ErrorMessage):
            await emit_typed_event(
                TaskEventType.ERROR_OCCURRED,
                stream_message,
                self._event_bus,
                task_id=self.task_node.task_node_id,
                source="stream_message",
            )
            return
        # 处理推理消息
        if isinstance(stream_message, ReasoningMessage):
            # 【关键修复】为新的消息流生成message_id
            if self._current_message_id is None:
                self._message_counter += 1

                # ✅ 优先使用LLM API返回的message_id，如果没有才生成
                if stream_message.id:
                    self._current_message_id = stream_message.id
                    self.logger.info(
                        f"[MESSAGE_ID] Using LLM API message_id: {self._current_message_id}",
                    )
                else:
                    # Fallback: 生成临时ID (向后兼容)
                    import uuid
                    self._current_message_id = f"msg_{self.task_node.task_node_id}_{self._message_counter}_{uuid.uuid4().hex[:8]}"
                    self.logger.warning(
                        f"[MESSAGE_ID] LLM API did not provide message_id, using generated: {self._current_message_id}",
                    )

            # 发送事件时附带message_id
            await emit_typed_event(
                TaskEventType.REASONING,
                {
                    "content": stream_message.content,
                    "message_id": self._current_message_id,
                },
                self._event_bus,
                task_id=self.task_node.task_node_id,
                source="stream_message",
            )
            return
        # 处理使用统计消息
        if isinstance(stream_message, UsageMessage):
            await emit_typed_event(
                TaskEventType.USAGE_RECEIVED,
                stream_message,
                self._event_bus,
                task_id=self.task_node.task_node_id,
                source="stream_message",
            )
            return
        # 处理完成消息
        if isinstance(stream_message, CompleteMessage):
            # 发送完成事件，包含message_id
            await emit_typed_event(
                TaskEventType.COMPLETE_RECEIVED,
                stream_message,
                self._event_bus,
                task_id=self.task_node.task_node_id,
                source="stream_message",
            )

            # 重置message_id，为下一条消息做准备
            self._current_message_id = None
            # 移除return语句，让工具调用能够被handle_stream_messages处理
            # return  # ❌ 删除这行，修复工具调用不处理的bug
        # 处理内容流消息（ContentMessage）
        if isinstance(stream_message, ContentMessage):
            # 【关键修复】为新的消息流生成message_id
            if self._current_message_id is None:
                self._message_counter += 1

                # ✅ 优先使用LLM API返回的message_id，如果没有才生成
                if stream_message.id:
                    self._current_message_id = stream_message.id
                    self.logger.info(
                        f"[MESSAGE_ID] Using LLM API message_id: {self._current_message_id}",
                    )
                else:
                    # Fallback: 生成临时ID (向后兼容)
                    import uuid
                    self._current_message_id = f"msg_{self.task_node.task_node_id}_{self._message_counter}_{uuid.uuid4().hex[:8]}"
                    self.logger.warning(
                        f"[MESSAGE_ID] LLM API did not provide message_id, using generated: {self._current_message_id}",
                    )

            # 内容消息直接处理，不需要缓冲器

            # 发送事件时附带message_id
            await emit_typed_event(
                TaskEventType.CONTENT_STREAM,
                {
                    "content": stream_message.content,
                    "message_id": self._current_message_id,
                },
                self._event_bus,
                task_id=self.task_node.task_node_id,
                source="stream_message",
            )
            return

    async def process_message(
        self,
        _timeout: float = 900.0,
        llm_timeout: float | None = None,
        tool_execution_timeout: float | None = None,
    ) -> Any | None:
        """处理消息，使用回调方式提高工具调用的实时性

        Args:
            message: 用户消息
            timeout: 总超时时间(秒),默认15分钟（向后兼容）
            llm_timeout: LLM调用超时(秒),None表示自动计算
            tool_execution_timeout: 工具执行超时(秒),None表示自动计算

        Returns:
            处理结果

        """
        # 🔧 FIX: 检查是否用户请求停止（在处理消息前）
        if self._agent and self._agent.is_stop_requested():
            self.logger.info(
                f"Task {self.task_node.task_node_id} stop requested, raising CancelledError to interrupt LLM",
            )
            raise asyncio.CancelledError("Stop requested by user")

        # 根据任务类型动态计算超时
        llm_timeout, tool_execution_timeout = self._get_timeout_for_task(
            llm_timeout=llm_timeout,
            tool_execution_timeout=tool_execution_timeout,
        )

        self._tool_message_handler._has_attempt_completion = False

        self._tool_message_handler._executed_tool_calls.clear()
        self.logger.info("Reset executed tool calls set for new task execution")

        # 构建API请求
        api_request = await self._message_processor.build_messages(
            user_workspace=self._user_workspace,
            capabilities=self._get_capabilities(),
        )

        if not self._llm_service.get_current_provider():
            # 使用 LLMProvider 获取模式特定的配置
            mode = self.task_node.mode or "plan"  # 默认使用 plan 模式
            mode_config = self._user_workspace.llm_manager.get_mode_config(mode)
            if mode_config:
                self._llm_service.set_provider(mode_config.name)

        # 转换消息格式 - 防御性检查
        raw_messages = api_request.get("messages", [])
        if not raw_messages:
            self.logger.warning("警告: 没有消息要处理")
            messages = []
        else:
            self.logger.info(f"开始转换 {len(raw_messages)} 条消息")
            try:
                converted_messages = []
                for i, msg_dict in enumerate(raw_messages):
                    if msg_dict is None:
                        self.logger.warning(f"消息 {i} 为 None,跳过")
                        continue
                    if isinstance(msg_dict, dict):
                        # 验证必要的 role 字段
                        if "role" not in msg_dict:
                            self.logger.error(f"消息 {i} 缺少 role 字段: {msg_dict}")
                            raise ValueError(f"消息 {i} 缺少 'role' 字段")

                        # 根据 role 选择正确的消息类
                        role = msg_dict.get("role")
                        if role == "system":
                            converted_messages.append(SystemMessage.from_openai_format(msg_dict))
                        elif role == "user":
                            converted_messages.append(UserMessage.from_openai_format(msg_dict))
                        elif role == "assistant":
                            converted_messages.append(AssistantMessage.from_openai_format(msg_dict))
                        elif role == "tool":
                            converted_messages.append(ToolMessage.from_openai_format(msg_dict))
                        else:
                            raise ValueError(f"消息 {i} 不支持的 role: {role}")
                    else:
                        # 非字典类型直接保留
                        converted_messages.append(msg_dict)
                        self.logger.debug(f"消息 {i} 保留原始类型: {type(msg_dict).__name__}")
                messages = converted_messages
            except Exception as e:
                self.logger.error(f"消息格式转换失败: {type(e).__name__}: {e}", exc_info=True)
                # 记录所有消息供调试
                for i, msg_dict in enumerate(raw_messages):
                    self.logger.exception(f"原始消息 {i}: type={type(msg_dict).__name__}, value={repr(msg_dict)[:200]}")
                raise

        async def stream_callback(stream_message: StreamMessages) -> None:
            """流式回调函数，处理工具消息和事件转换"""
            # 🔧 FIX: 在每个流式消息处理时检查停止标志
            if self._agent and self._agent.is_stop_requested():
                self.logger.info(
                    f"Task {self.task_node.task_node_id} stop requested during streaming, raising CancelledError",
                )
                raise asyncio.CancelledError("Stop requested by user during streaming")

            await self.stream_message_to_event(stream_message)
            if isinstance(stream_message, CompleteMessage):
                # 工具执行使用独立的超时控制
                try:
                    async with asyncio.timeout(tool_execution_timeout):
                        await self._tool_message_handler.handle_stream_messages(stream_message)
                except TimeoutError:
                    # Tool execution timeout - log but don't include stack trace (expected flow)
                    self.logger.exception(f"Tool execution timeout after {tool_execution_timeout}s")
                    # 工具执行超时不中断整个流程，继续保存checkpoint

        try:
            # LLM调用使用独立的超时控制
            async with asyncio.timeout(llm_timeout):
                await self._llm_service.create_message_with_callback(
                    messages,
                    callback=stream_callback,
                    tools=api_request.get("tools", []),
                )

            self.logger.info(
                f"Message processed successfully (LLM: {llm_timeout}s, Tools: {tool_execution_timeout}s)",
            )

        except TimeoutError:
            # LLM timeout - log but don't include stack trace (expected flow)
            self.logger.exception(f"LLM call timeout after {llm_timeout}s")
            await self._send_error_to_frontend(
                error_message=f"LLM调用超时（{llm_timeout:.0f}秒），请稍后重试或简化任务。",
                error_type="timeout",
                details={
                    "timeout": llm_timeout,
                    "suggestion": "简化任务内容或稍后重试",
                },
            )
            raise

        except LLMError as e:
            # LLM API error - log with stack trace for debugging
            error_str = str(e)
            self.logger.error(f"LLM API error: {error_str}", exc_info=True)

            # 检测429 rate limit错误
            if "429" in error_str or "rate_limit" in error_str.lower():
                self.logger.warning(f"Rate limit detected: {e}")
                await self._send_error_to_frontend(
                    error_message="API请求过于频繁，请稍后重试。建议等待60秒后点击重试按钮。",
                    error_type="rate_limit_exceeded",
                    details={
                        "error_code": "429",
                        "recoverable": True,
                        "retry_after": 60,
                        "suggestion": "等待60秒后重试",
                        "original_error": error_str[:500],  # 限制长度
                    },
                )
            else:
                # 其他LLM错误
                self.logger.exception("LLM API error: ")
                await self._send_error_to_frontend(
                    error_message=f"LLM API错误：{error_str[:200]}",
                    error_type="llm_api_error",
                    details={
                        "error": error_str[:500],
                        "recoverable": False,
                        "suggestion": "请检查API配置或联系管理员",
                    },
                )
            raise

        except asyncio.CancelledError:
            # 🔧 FIX: 用户请求停止 - 正常的停止流程,不是错误
            self.logger.info(f"Task {self.task_node.task_node_id} was cancelled due to stop request")
            # 设置任务状态为ABORTED
            self.task_node.update_status(TaskStatus.ABORTED)
            raise  # 重新抛出以让上层处理

        finally:
            # 保存 checkpoint
            await self._save_checkpoint()

    def _get_timeout_for_task(
        self,
        llm_timeout: float | None = None,
        tool_execution_timeout: float | None = None,
    ) -> tuple[float, float]:
        """根据任务类型动态计算超时时间

        Args:
            llm_timeout: 用户指定的LLM超时
            tool_execution_timeout: 用户指定的工具执行超时

        Returns:
            (llm_timeout, tool_execution_timeout) 元组

        """
        # 如果用户已明确指定，使用用户指定的值
        if llm_timeout is not None and tool_execution_timeout is not None:
            return llm_timeout, tool_execution_timeout

        # 获取任务描述（UserInputText对象转为字符串）
        task_description = ""
        if hasattr(self.task_node, "description"):
            desc = self.task_node.description
            if hasattr(desc, "content"):
                # UserInputText对象
                task_description = desc.content
            elif isinstance(desc, str):
                # 字符串
                task_description = desc
            else:
                # 其他类型，转为字符串
                task_description = str(desc)

        task_description = task_description.lower()
        # 安全获取 mode（可能为 None）
        mode = self.task_node.mode.lower() if self.task_node.mode else ""

        # 检测是否为大型内容生成任务
        is_large_generation = any(
            keyword in task_description
            for keyword in [
                "html",
                "生成html",
                "创建页面",
                "build page",
                "generate html",
                "前端",
                "frontend",
                "页面设计",
                "page design",
                "代码生成",
                "code generation",
                "大型",
                "large",
            ]
        )

        # 检测是否为复杂任务（包含多个步骤）
        is_complex_task = any(
            keyword in task_description
            for keyword in [
                "多个",
                "multi",
                "步骤",
                "steps",
                "流程",
                "workflow",
                "完整",
                "complete",
                "全部",
                "all",
                "全面",
                "comprehensive",
            ]
        )

        # 检测模式特定超时需求
        mode_multipliers = {
            "orchestrator": 1.5,  # 编排模式需要更长时间
            "architect": 1.2,  # 架构模式需要更多思考
            "code": 1.3,  # 代码生成可能较长
            "ask": 0.8,  # 问答模式相对快速
            "debug": 1.0,  # 调试模式标准时间
        }

        # 基础超时
        base_llm_timeout = 600.0  # 10分钟
        base_tool_timeout = 300.0  # 5分钟

        # 应用模式乘数
        mode_multiplier = mode_multipliers.get(mode, 1.0)

        # 根据任务类型调整
        if is_large_generation:
            # 大型内容生成任务：增加LLM超时，减少工具超时
            calculated_llm_timeout = min(
                base_llm_timeout * 1.5 * mode_multiplier,
                1800.0,
            )  # 最多30分钟
            calculated_tool_timeout = base_tool_timeout  # 保持标准工具超时
        elif is_complex_task:
            # 复杂任务：两者都增加
            calculated_llm_timeout = min(
                base_llm_timeout * 1.3 * mode_multiplier,
                1500.0,
            )  # 最多25分钟
            calculated_tool_timeout = min(
                base_tool_timeout * 1.5 * mode_multiplier,
                900.0,
            )  # 最多15分钟
        else:
            # 标准任务
            calculated_llm_timeout = base_llm_timeout * mode_multiplier
            calculated_tool_timeout = base_tool_timeout * mode_multiplier

        # 如果用户指定了其中一个，另一个自动计算
        if llm_timeout is not None:
            final_llm_timeout = llm_timeout
            # 工具超时约为LLM超时的50%
            final_tool_timeout = tool_execution_timeout or (llm_timeout * 0.5)
        elif tool_execution_timeout is not None:
            final_tool_timeout = tool_execution_timeout
            # LLM超时约为工具超时的2倍
            final_llm_timeout = llm_timeout or (tool_execution_timeout * 2.0)
        else:
            final_llm_timeout = calculated_llm_timeout
            final_tool_timeout = calculated_tool_timeout

        self.logger.info(
            f"Timeout configuration for task '{self.task_node.mode or 'unknown'}': LLM={final_llm_timeout:.0f}s, Tools={final_tool_timeout:.0f}s (is_large_generation={is_large_generation}, is_complex={is_complex_task})",
        )

        return final_llm_timeout, final_tool_timeout

    async def _save_checkpoint(self) -> None:
        """保存 checkpoint 到磁盘
        包含聊天消息历史、任务图状态和上下文信息
        """
        # 收集对话消息历史
        conversation_messages = []
        if self._user_workspace.current_conversation:
            for msg in self._user_workspace.current_conversation.messages:
                if hasattr(msg, "to_dict"):
                    conversation_messages.append(msg.to_dict())
                else:
                    conversation_messages.append(msg)

        # 收集任务图状态
        task_graph_data = {}
        if self._user_workspace.task_graph:
            task_graph_data = {
                "task_id": self._user_workspace.task_graph.task_node_id,
                "nodes": {},
            }
            all_tasks = await self._user_workspace.task_graph.get_all_tasks()
            for task in all_tasks:
                task_graph_data["nodes"][task.task_node_id] = {
                    "task_node_id": task.task_node_id,
                    "description": task.description,
                    "mode": task.mode,
                    "status": task.status.value,
                    "todos": [todo.to_dict() for todo in task.data.todos],
                    "parent_id": task.parent_id,
                    "child_ids": task.child_ids,
                }

        # 收集上下文信息
        context_data = {}
        if self._user_workspace.task_graph:
            all_tasks = await self._user_workspace.task_graph.get_all_tasks()
            for task in all_tasks:
                context = task.context.to_dict() if task.context else {}
                context_data[task.task_node_id] = context

        # 使用新的 IntelligentCheckpointManager 保存 checkpoint
        # 构建状态数据
        state = {
            "conversation_messages": conversation_messages,
            "task_graph_data": task_graph_data,
            "context_data": context_data,
            "metadata": {
                "task_node_id": self.task_node.task_node_id,
                "mode": self.task_node.mode,
                "message_count": len(conversation_messages),
            },
        }

        checkpoint_id = await self._checkpoint_manager.create_checkpoint(
            task_id=self.task_node.task_node_id,
            state=state,
            checkpoint_type=CheckpointType.AUTO,  # 使用自动检查点类型
            tags=["task_node", self.task_node.mode or "unknown"],
        )

        self.logger.info(f"Checkpoint saved: {checkpoint_id}")

        # 定期清理旧 checkpoint
        await self._cleanup_old_checkpoints()

        # 发送检查点创建事件
        await emit_typed_event(
            TaskEventType.CHECKPOINT_CREATED,
            {
                "checkpoint_id": checkpoint_id,
                # 使用全局 checkpoints 目录路径
                "checkpoint_path": f"{get_dawei_home()}/checkpoints/{checkpoint_id}",
                "message_count": len(conversation_messages),
                "task_count": len(task_graph_data.get("nodes", {})),
            },
            self._event_bus,
            task_id=self.task_node.task_node_id,
            source="task_node_executor",
        )

    async def _cleanup_old_checkpoints(self) -> None:
        """定期清理旧 checkpoint,防止磁盘空间耗尽

        注意：IntelligentCheckpointManager 会自动清理旧的检查点（在创建新检查点时），
        这里保留定时清理作为额外的保障措施。
        """
        try:
            current_time = time.time()
            # 每小时清理一次 (3600 秒)
            cleanup_interval = 3600.0

            if current_time - self.last_cleanup_time > cleanup_interval:
                self._checkpoint_manager.set_max_checkpoints(10)

                # 手动触发一次清理，通过列出和删除旧的检查点
                checkpoints = await self._checkpoint_manager.list_checkpoints(
                    task_id=self.task_node.task_node_id,
                )

                # 保留最新的10个，删除其余的
                if len(checkpoints) > 10:
                    for cp_metadata in checkpoints[10:]:
                        await self._checkpoint_manager.delete_checkpoint(cp_metadata.checkpoint_id)

                self.last_cleanup_time = current_time
        except (CheckpointError, OSError) as e:
            self.logger.error(f"Failed to cleanup old checkpoints: {e}", exc_info=True)
            raise  # Fast fail: re-raise cleanup errors

    async def _run_task_loop(self) -> None:
        """运行任务主循环
        持续执行直到任务状态为 COMPLETED 或 ABORTED
        实现多轮执行机制：与LLM持续交互，动态创建和维护task graph
        """
        iteration = 0
        max_iterations = 100  # 防止无限循环的安全限制

        while iteration < max_iterations:
            iteration += 1

            # 检查任务状态，如果已完成或中止则退出循环
            status = self.task_node.status
            if status in [TaskStatus.COMPLETED, TaskStatus.ABORTED]:
                self.logger.info(
                    f"Task {self.task_node.task_node_id} completed with status: {status.value}",
                )
                break

            # 🔧 FIX: 检查是否用户请求停止
            if self._agent and self._agent.is_stop_requested():
                self.logger.info(
                    f"Task {self.task_node.task_node_id} stop requested by user, setting status to ABORTED",
                )
                self.task_node.update_status(TaskStatus.ABORTED)
                break

            await self.process_message()

            if not await self._should_continue_execution():
                # 设置任务状态为COMPLETED，因为任务已正常完成
                if self.task_node.status not in [
                    TaskStatus.COMPLETED,
                    TaskStatus.ABORTED,
                ]:
                    self.logger.info(
                        f"Task {self.task_node.task_node_id} finished naturally, setting status to COMPLETED",
                    )
                    self.task_node.update_status(TaskStatus.COMPLETED)
                break

            # 短暂休眠避免忙等待
            await asyncio.sleep(0.05)

        if iteration >= max_iterations:
            self.logger.warning(f"Task {self.task_node.task_node_id} reached max iterations limit")
            self.task_node.update_status(TaskStatus.COMPLETED)

    async def _check_all_todos_completed(self) -> bool:
        """检查所有待办事项是否已完成

        Returns:
            True if all todos are completed, False otherwise

        """
        if not self.task_node.data.todos:
            return True  # 没有todos视为全部完成

        return all(todo.status == TodoStatus.COMPLETED for todo in self.task_node.data.todos)

    async def _has_pending_followup_responses(self) -> bool:
        """检查是否有未完成的followup响应

        Returns:
            True if there are pending followup responses, False otherwise

        """
        try:
            if hasattr(self, "_pending_followup_responses") and self._pending_followup_responses:
                # 检查是否还有未完成的future
                for _tool_call_id, future in self._pending_followup_responses.items():
                    if not future.done():
                        return True
            return False
        except (AttributeError, RuntimeError) as e:
            self.logger.error(f"Error checking pending followup responses: {e}", exc_info=True)
            # Fast fail: re-raise to avoid masking the error
            raise

    async def _should_continue_execution(self) -> bool:
        """判断是否应该继续执行（是否需要更多轮的LLM交互）

        Returns:
            True if should continue, False otherwise

        """
        if self._tool_message_handler.has_attempt_completion:
            self.logger.info("_has_attempt_completion flag is True, stopping execution")
            return False

        if self._user_workspace.current_conversation and self._user_workspace.current_conversation.messages:
            # 检查最近的消息
            recent_messages = self._user_workspace.current_conversation.messages[-1:]

            for msg in recent_messages:
                # 检查是否有工具调用
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        if hasattr(tool_call, "function") and tool_call.function.name == "attempt_completion":
                            self.logger.info(
                                "Found attempt_completion tool call, stopping execution",
                            )
                            return False  # 已经调用了attempt_completion，不再继续

                elif hasattr(msg, "role"):  # 是个assistant，但是没有tool call
                    if str(msg.role) == str(MessageRole.ASSISTANT):
                        # should complete ?
                        return False
            return True
        return None

    async def _execute_tool_call_todo(self, todo: TodoItem) -> None:
        """执行工具调用类型的TODO"""
        if not hasattr(todo, "metadata"):
            self.logger.warning(f"TODO {todo.title} missing metadata for tool call")
            return

        tool_name = todo.metadata.get("tool_name")
        tool_args = todo.metadata.get("tool_args", {})

        if not tool_name:
            self.logger.warning(f"TODO {todo.title} missing tool_name")
            return

        # 构造ToolCall对象并执行

        tool_call = ToolCall(id=todo.id, name=tool_name, parameters=tool_args)

        result = await self._tool_message_handler.execute_tool_call(tool_call)
        todo.metadata["result"] = result

    async def _create_subtask_todo(self, todo: TodoItem) -> None:
        """创建子任务类型的TODO"""
        if not hasattr(todo, "metadata"):
            self.logger.warning(f"TODO {todo.title} missing metadata for subtask")
            return

        import uuid

        from dawei.task_graph.task_node_data import TaskData

        subtask_id = str(uuid.uuid4())
        description = todo.metadata.get("description", todo.title)
        # 获取 mode，如果父任务 mode 为 None，使用默认值 "plan"
        parent_mode = self.task_node.mode or "plan"
        mode = todo.metadata.get("mode", parent_mode)

        task_data = TaskData(
            task_node_id=subtask_id,
            description=description,
            mode=mode,
            context=self._user_workspace.create_task_context(),
        )

        await self._user_workspace.task_graph.create_subtask(
            self.task_node.task_node_id,
            task_data,
        )

        todo.metadata["subtask_id"] = subtask_id
        self.logger.info(f"Created subtask {subtask_id} from TODO")

    async def _create_periodic_checkpoint(self) -> None:
        """定期创建检查点"""
        current_time = time.time()

        if current_time - self.last_checkpoint_time > self._config.checkpoint_interval:
            task_node = self.task_node
            if task_node:
                state = {
                    "task_node_id": task_node.task_node_id,
                    "status": task_node.status.value,
                    "mode": task_node.mode,
                    "todos": [todo.to_dict() for todo in task_node.data.todos],
                    "timestamp": current_time,
                }

                # 发送检查点创建事件
                await emit_typed_event(
                    TaskEventType.CHECKPOINT_CREATED,
                    {
                        "checkpoint_id": f"checkpoint_{task_node.task_node_id}_{int(current_time)}",
                        # 使用全局 checkpoints 目录路径
                        "checkpoint_path": f"{get_dawei_home()}/checkpoints/{task_node.task_node_id}",
                        "checkpoint_size": len(str(state)),
                    },
                    self._event_bus,
                    task_id=task_node.task_node_id,
                    source="periodic_checkpoint",
                )

                self.last_checkpoint_time = current_time

    def _get_capabilities(self) -> list[str]:
        """获取能力列表

        Returns:
            能力列表

        """
        capabilities = []
        if self._config.enable_skills:
            capabilities.append("Claude Skills integration is enabled")
        if self._config.enable_mcp:
            capabilities.append("MCP (Model Context Protocol) integration is enabled")
        return capabilities

    async def cancel_task_execution(self) -> bool:
        """取消任务执行

        Returns:
            是否成功取消

        """
        if self.execution_task and not self.execution_task.done():
            self.execution_task.cancel()
            self.execution_task = None
            self.logger.info(f"Task execution cancelled: {self.task_node.task_node_id}")
            return True
        return False

    async def is_task_executing(self) -> bool:
        """检查任务是否正在执行

        Returns:
            是否正在执行

        """
        return self.execution_task is not None and not self.execution_task.done()

    async def get_execution_status(self) -> dict[str, Any]:
        """获取执行状态

        Returns:
            执行状态信息

        """
        is_executing = await self.is_task_executing()
        last_checkpoint = self.last_checkpoint_time

        return {
            "task_node_id": self.task_node.task_node_id,
            "is_executing": is_executing,
            "last_checkpoint_time": last_checkpoint,
            "execution_time": time.time() - last_checkpoint if last_checkpoint > 0 else 0,
        }

    async def pause_task_execution(self) -> bool:
        """暂停任务执行

        Returns:
            是否成功暂停

        """
        # TODO: Implement task pause functionality
        # Currently, task pause is not fully implemented
        # This method is called by Agent.pause_task() but needs implementation
        self.logger.warning(
            f"pause_task_execution called for task {self.task_node.task_node_id} but not yet implemented",
        )
        return False

    async def resume_task_execution(self) -> bool:
        """恢复任务执行

        Returns:
            是否成功恢复

        """
        self.task_node.update_status(TaskStatus.RESUMABLE)
        await self.execute_task()

    async def get_current_mode(self) -> str:
        """获取当前模式

        Returns:
            当前模式

        """
        return self.task_node.mode or "plan"

    async def handle_followup_response(self, tool_call_id: str, response: str) -> bool:
        """处理前端发来的追问回复

        Args:
            tool_call_id: 工具调用ID
            response: 用户回复

        Returns:
            是否成功处理

        """
        return await self._tool_message_handler.handle_followup_response(tool_call_id, response)

    async def _send_error_to_frontend(
        self,
        error_message: str,
        error_type: str = "execution_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        """发送错误消息到前端

        Args:
            error_message: 错误消息
            error_type: 错误类型
            details: 错误详情

        """
        try:
            from dawei.core.events import TaskEventType, emit_typed_event

            # 构建错误详情
            error_details = details or {}
            error_details.update(
                {
                    "task_node_id": self.task_node.task_node_id,
                    "mode": self.task_node.mode,
                    "error_type": error_type,
                },
            )

            # 发送错误事件（会通过chat handler转发到前端）
            self.logger.info(
                f"[ERROR_TRACE] About to emit ERROR_OCCURRED event: error_type={error_type}, task_id={self.task_node.task_node_id}",
            )
            await emit_typed_event(
                TaskEventType.ERROR_OCCURRED,
                {
                    "error_type": error_type,
                    "message": error_message,
                    "details": error_details,
                },
                self._event_bus,
                task_id=self.task_node.task_node_id,
                source="task_node_executor",
            )

            self.logger.info(
                f"[ERROR_TRACE] Successfully emitted ERROR_OCCURRED event: {error_message[:100]}...",
            )

        except (OSError, ConnectionError, RuntimeError) as e:
            self.logger.error(f"Failed to send error to frontend: {e}", exc_info=True)
            # Fast fail: re-raise to avoid masking the original error
            raise
