# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Event Forwarding Handler

处理 Agent 事件转发到 WebSocket 客户端
将所有任务事件转换为 WebSocket 消息并发送给前端
"""

import time
from collections.abc import Callable
from typing import Any

from dawei.agentic.agent import Agent
from dawei.core import local_context
from dawei.core.events import CORE_EVENT_BUS, TaskEventType
from dawei.logg.logging import get_logger
from dawei.websocket.protocol import (
    A2UIServerEventMessage,
    AgentCompleteMessage,
    FollowupQuestionMessage,
    LLMApiCompleteMessage,
    LLMApiRequestMessage,
    PDCAPhaseAdvanceMessage,
    PDCAStatusUpdateMessage,
    StreamCompleteMessage,
    StreamContentMessage,
    StreamReasoningMessage,
    StreamToolCallMessage,
    StreamUsageMessage,
    SystemWebSocketMessage,
    TaskNodeCompleteMessage,
    TaskNodeProgressMessage,
    ToolCallProgressMessage,
    ToolCallResultMessage,
    ToolCallStartMessage,
)

logger = get_logger(__name__)


class EventForwardingHandler:
    """事件转发处理器

    将 Agent 事件总线的事件转换为 WebSocket 消息并转发给前端：
    - 订阅 Agent 事件总线的所有事件
    - 处理任务完成、错误、进度等事件
    - 处理 LLM API 调用事件
    - 处理工具调用事件
    - 处理 PDCA 循环事件
    - 错误处理和日志记录
    """

    def __init__(self, send_message_callback: Callable):
        """初始化事件转发处理器

        Args:
            send_message_callback: 发送消息的回调函数

        """
        self._send_message = send_message_callback

    async def setup_event_forwarding(
        self,
        agent: Agent,
        session_id: str,
        task_id: str,
        pdca_phase_callback: Callable | None = None,
    ) -> dict[str, str]:
        """为 Agent 设置事件监听器，将任务事件转发到 WebSocket 客户端

        Args:
            agent: Agent 实例
            session_id: 会话 ID
            task_id: 任务 ID
            pdca_phase_callback: PDCA 阶段完成回调（可选）

        Returns:
            dict: 事件处理器 ID 映射 {event_type_value: handler_id}

        """
        # LLM API 状态追踪
        llm_api_active = False
        current_llm_provider = None
        current_llm_model = None
        llm_request_start_time = None

        async def event_handler(event):
            """事件处理器函数 - 处理所有任务事件"""
            nonlocal llm_api_active, current_llm_provider, current_llm_model, llm_request_start_time

            # 初始化 workspace_id，确保在所有代码路径中都已定义
            workspace_id = None

            # 直接访问强类型 TaskEvent 对象的属性
            event_type = event.event_type
            event_data = event.data

            # 调试日志
            if event_type == TaskEventType.ERROR_OCCURRED:
                logger.info(
                    f"[ERROR_TRACE] Chat handler received ERROR_OCCURRED event: event_id={event.event_id}, task_id={task_id}",
                )

            user_message_id = local_context.get_message_id()

            # 获取事件类型枚举
            if isinstance(event_type, str):
                try:
                    event_type_enum = TaskEventType(event_type)
                except ValueError:
                    logger.error(f"未知的事件类型: {event_type}", exc_info=True)
                    return
            else:
                event_type_enum = event_type

            logger.debug(f"任务 {task_id} 事件: {event_type_enum}")

            message_to_send = None
            llm_api_message = None

            try:
                # 处理任务完成事件
                if event_type_enum == TaskEventType.TASK_COMPLETED:
                    await self._handle_task_completed(event_data, session_id, task_id, pdca_phase_callback)

                # 处理任务错误事件
                elif event_type_enum == TaskEventType.TASK_ERROR:
                    message_to_send = await self._handle_task_error(event_data, session_id, task_id)

                # 处理错误发生事件
                elif event_type_enum == TaskEventType.ERROR_OCCURRED:
                    message_to_send = await self._handle_error_occurred(event_data, session_id, task_id)

                # 处理使用统计事件
                elif event_type_enum == TaskEventType.USAGE_RECEIVED:
                    message_to_send, llm_api_message = await self._handle_usage_received(
                        event_data,
                        session_id,
                        task_id,
                        user_message_id,
                        llm_api_active,
                        llm_request_start_time,
                        current_llm_provider,
                        current_llm_model,
                    )
                    if llm_api_message:
                        llm_api_active = False

                # 处理完成接收事件
                elif event_type_enum == TaskEventType.COMPLETE_RECEIVED:
                    message_to_send, llm_api_message = await self._handle_complete_received(
                        event_data,
                        session_id,
                        task_id,
                        user_message_id,
                        llm_api_active,
                        llm_request_start_time,
                        current_llm_provider,
                        current_llm_model,
                    )
                    if llm_api_message:
                        llm_api_active = False

                # 处理内容流事件
                elif event_type_enum == TaskEventType.CONTENT_STREAM:
                    message_to_send, llm_api_message, llm_api_active, llm_request_start_time = await self._handle_content_stream(
                        event_data,
                        agent,
                        session_id,
                        task_id,
                        llm_api_active,
                        llm_request_start_time,
                        current_llm_provider,
                        current_llm_model,
                        workspace_id,
                    )

                # 处理推理事件
                elif event_type_enum == TaskEventType.REASONING:
                    message_to_send = await self._handle_reasoning(event_data, session_id, task_id)

                # 处理工具调用检测事件
                elif event_type_enum == TaskEventType.TOOL_CALLS_DETECTED:
                    await self._handle_tool_calls_detected(event_data, session_id, task_id, user_message_id, self._send_message)

                # 处理工具调用开始事件
                elif event_type_enum == TaskEventType.TOOL_CALL_START:
                    message_to_send = await self._handle_tool_call_start(event_data, session_id, task_id)

                # 处理工具调用进度事件
                elif event_type_enum == TaskEventType.TOOL_CALL_PROGRESS:
                    message_to_send = await self._handle_tool_call_progress(event_data, session_id, task_id)

                # 处理工具调用结果事件
                elif event_type_enum == TaskEventType.TOOL_CALL_RESULT:
                    message_to_send = await self._handle_tool_call_result(event_data, session_id, task_id, workspace_id)

                # 处理检查点创建事件
                elif event_type_enum == TaskEventType.CHECKPOINT_CREATED:
                    message_to_send = await self._handle_checkpoint_created(event_data, session_id, task_id)

                # 处理状态变更事件
                elif event_type_enum == TaskEventType.STATE_CHANGED:
                    message_to_send = await self._handle_state_changed(event_data, session_id, task_id)

                # 处理追问问题事件
                elif event_type_enum == TaskEventType.FOLLOWUP_QUESTION:
                    message_to_send = await self._handle_followup_question(event_data, session_id, task_id, user_message_id)

                # 处理 A2UI UI 组件事件
                elif event_type_enum == TaskEventType.A2UI_SURFACE_EVENT:
                    message_to_send = await self._handle_a2ui_surface_event(event_data, session_id, task_id, user_message_id)

                # 发送消息
                if message_to_send:
                    message_to_send.user_message_id = user_message_id
                    await self._send_message(session_id, message_to_send)

                # 发送 LLM API 状态消息
                if llm_api_message:
                    await self._send_message(session_id, llm_api_message)

            except Exception as e:
                logger.error(f"处理任务事件 {event_type_enum} 时出错: {e}", exc_info=True)

        # 订阅所有事件
        event_types_to_forward = [
            TaskEventType.TASK_COMPLETED,
            TaskEventType.TASK_ERROR,
            TaskEventType.ERROR_OCCURRED,
            TaskEventType.USAGE_RECEIVED,
            TaskEventType.COMPLETE_RECEIVED,
            TaskEventType.CONTENT_STREAM,
            TaskEventType.REASONING,
            TaskEventType.TOOL_CALLS_DETECTED,
            TaskEventType.TOOL_CALL_START,
            TaskEventType.TOOL_CALL_PROGRESS,
            TaskEventType.TOOL_CALL_RESULT,
            TaskEventType.CHECKPOINT_CREATED,
            TaskEventType.STATE_CHANGED,
            TaskEventType.FOLLOWUP_QUESTION,
            TaskEventType.A2UI_SURFACE_EVENT,
        ]

        # 获取 Agent 的事件总线
        event_bus = agent.event_bus

        # 注册事件处理器到 Agent 事件总线
        handler_ids = {}
        for event_type in event_types_to_forward:
            try:
                handler_id = event_bus.add_handler(event_type, event_handler)
                handler_ids[event_type.value] = handler_id
                logger.debug(
                    f"[EVENT_HANDLER] Registered handler {handler_id} for event {event_type.value} (task: {task_id})",
                )
            except Exception as e:
                logger.error(f"订阅事件 {event_type} 时出错: {e}", exc_info=True)

        # 额外订阅全局事件总线的 TOOL_CALL_START 事件
        # 因为 tool_executor 通过全局事件总线发送 TOOL_CALL_START，需要单独订阅
        try:
            global_tool_start_handler_id = CORE_EVENT_BUS.add_handler(
                TaskEventType.TOOL_CALL_START,
                event_handler
            )
            handler_ids[TaskEventType.TOOL_CALL_START.value] = global_tool_start_handler_id
            logger.info(
                f"[EVENT_HANDLER] ✅ Subscribed to global CORE_EVENT_BUS for TOOL_CALL_START (handler: {global_tool_start_handler_id}, task: {task_id})"
            )
        except Exception as e:
            logger.error(f"订阅全局TOOL_CALL_START事件时出错: {e}", exc_info=True)

        logger.info(
            f"[EVENT_HANDLER] ✅ Successfully registered {len(handler_ids)} event handlers for task {task_id}",
        )
        return handler_ids

    # ==================== 事件处理方法 ====================

    async def _handle_task_completed(self, event_data, session_id: str, task_id: str, pdca_phase_callback):
        """处理任务完成事件"""
        result_content = event_data.result if hasattr(event_data, "result") and event_data.result else "任务已完成。"

        logger.info(
            f"[CHAT_HANDLER] 📦 任务完成: task_id={task_id}, 发送 AGENT_COMPLETE 消息",
        )

        # PDCA: 检查是否有 PDCA 扩展，并发送阶段推进消息
        if pdca_phase_callback:
            await pdca_phase_callback(session_id, task_id)

        # 发送 AGENT_COMPLETE 消息
        total_duration_ms = 60000  # 默认 60 秒

        agent_complete_message = AgentCompleteMessage(
            session_id=session_id,
            task_id=task_id,
            result_summary=result_content[:200] if result_content else "任务已完成",
            total_duration_ms=total_duration_ms,
            tasks_completed=1,
            tools_used=[],
            metadata={},
        )
        await self._send_message(session_id, agent_complete_message)
        logger.info("[CHAT_HANDLER] ✅ AGENT_COMPLETE 消息已发送")

        # 发送任务完成消息
        message_to_send = TaskNodeCompleteMessage(
            session_id=session_id,
            task_id=task_id,
            task_node_id=task_id,
            result={"response": result_content},
            duration_ms=0,
        )
        await self._send_message(session_id, message_to_send)

    async def _handle_task_error(self, event_data, session_id: str, task_id: str):
        """处理任务错误事件"""
        return SystemWebSocketMessage(
            session_id=session_id,
            code=(event_data.error_code if hasattr(event_data, "error_code") else "TASK_ERROR"),
            message=(event_data.error_message if hasattr(event_data, "error_message") else "未知错误"),
            recoverable=(event_data.recoverable if hasattr(event_data, "recoverable") else False),
            details={"task_id": task_id},
        )

    async def _handle_error_occurred(self, event_data, session_id: str, task_id: str):
        """处理错误发生事件"""
        from dawei.websocket.protocol import ErrorMessage

        error_type = event_data.get("error_type", "unknown") if isinstance(event_data, dict) else "unknown"
        error_message = event_data.get("message", "未知错误") if isinstance(event_data, dict) else "未知错误"
        error_details = event_data.get("details", {}) if isinstance(event_data, dict) else {}

        logger.info(
            f"[ERROR_TRACE] Creating ErrorMessage: error_type={error_type}, error_message={error_message[:100]}...",
        )

        return ErrorMessage(
            session_id=session_id,
            code=error_type.upper(),
            message=error_message,
            recoverable=False,
            details={"task_id": task_id, **error_details},
        )

    async def _handle_usage_received(self, event_data, session_id: str, task_id: str, user_message_id: str, llm_api_active: bool, llm_request_start_time, current_llm_provider, current_llm_model):
        """处理使用统计事件"""
        message_to_send = StreamUsageMessage.from_stream_message(
            event_data,
            session_id=session_id,
            task_id=task_id,
        )
        message_to_send.user_message_id = user_message_id

        llm_api_message = None
        if llm_api_active:
            duration_ms = int((time.time() - llm_request_start_time) * 1000) if llm_request_start_time else None
            llm_api_message = LLMApiCompleteMessage(
                session_id=session_id,
                task_id=task_id,
                provider=current_llm_provider or "unknown",
                model=current_llm_model or "unknown",
                usage=event_data.data if hasattr(event_data, "data") else None,
                duration_ms=duration_ms,
            )

        return message_to_send, llm_api_message

    async def _handle_complete_received(self, event_data, session_id: str, task_id: str, user_message_id: str, llm_api_active: bool, llm_request_start_time, current_llm_provider, current_llm_model):
        """处理完成接收事件"""
        message_to_send = StreamCompleteMessage.from_stream_message(
            event_data,
            session_id=session_id,
            task_id=task_id,
        )
        message_to_send.user_message_id = user_message_id

        llm_api_message = None
        if llm_api_active:
            duration_ms = int((time.time() - llm_request_start_time) * 1000) if llm_request_start_time else None
            llm_api_message = LLMApiCompleteMessage(
                session_id=session_id,
                task_id=task_id,
                provider=current_llm_provider or "unknown",
                model=current_llm_model or "unknown",
                finish_reason=(event_data.finish_reason if hasattr(event_data, "finish_reason") else None),
                usage=event_data.usage if hasattr(event_data, "usage") else None,
                duration_ms=duration_ms,
            )

        return message_to_send, llm_api_message

    async def _handle_content_stream(self, event_data, agent, session_id: str, task_id: str, llm_api_active: bool, llm_request_start_time, current_llm_provider, current_llm_model, workspace_id):
        """处理内容流事件"""
        llm_api_message = None

        # 如果是第一个内容块，发送 LLM API 请求开始消息
        if not llm_api_active:
            llm_api_active = True
            llm_request_start_time = event.timestamp

            # 从 agent 获取 LLM 提供商信息
            try:
                if hasattr(agent, "execution_engine") and hasattr(agent.execution_engine, "_llm_service"):
                    llm_service = agent.execution_engine._llm_service
                    current_config = llm_service.get_current_config()

                    if current_config and hasattr(current_config, "config"):
                        config = current_config.config
                        provider = getattr(config, "apiProvider", None) or getattr(config, "provider", "unknown")
                        model = getattr(config, "model_id", None) or getattr(config, "openAiModelId", None) or "unknown"

                        current_llm_provider = provider
                        current_llm_model = model
            except Exception as e:
                logger.error(f"[CHAT_HANDLER] Error extracting LLM config info: {e}", exc_info=True)

            llm_api_message = LLMApiRequestMessage(
                session_id=session_id,
                task_id=task_id,
                provider=current_llm_provider,
                model=current_llm_model,
                request_type="chat",
            )

        # 构建流式内容消息
        message_to_send = StreamContentMessage.from_event_data(
            event_data,
            session_id=session_id,
            task_id=task_id,
        )

        return message_to_send, llm_api_message, llm_api_active, llm_request_start_time

    async def _handle_reasoning(self, event_data, session_id: str, task_id: str):
        """处理推理事件"""
        assistant = {
            "content": event_data.get("content", ""),
            "message_id": event_data.get("message_id"),
        }
        return StreamReasoningMessage.from_event_data(
            assistant,
            session_id=session_id,
            task_id=task_id,
        )

    async def _handle_tool_calls_detected(self, event_data, session_id: str, task_id: str, user_message_id: str, send_callback):
        """处理工具调用检测事件"""
        tool_calls = event_data.all_tool_calls if hasattr(event_data, "all_tool_calls") else []
        if tool_calls:
            for tool_call in tool_calls:
                if hasattr(tool_call, "function"):
                    message_to_send = StreamToolCallMessage(
                        session_id=session_id,
                        task_id=task_id,
                        tool_call=tool_call,
                        all_tool_calls=tool_calls,
                        user_message_id=user_message_id,
                    )
                    await send_callback(session_id, message_to_send)

    async def _handle_tool_call_start(self, event_data, session_id: str, task_id: str):
        """处理工具调用开始事件"""
        logger.info(f"[EVENT_FORWARDING] 🔧 Handling TOOL_CALL_START event: tool_name={event_data.tool_name if hasattr(event_data, 'tool_name') else 'unknown'}, session_id={session_id}, task_id={task_id}")

        return ToolCallStartMessage(
            session_id=session_id,
            task_id=task_id,
            tool_name=event_data.tool_name if hasattr(event_data, "tool_name") else "",
            tool_input=(event_data.tool_input if hasattr(event_data, "tool_input") else {}),
            tool_call_id=getattr(event_data, "tool_call_id", None),
        )

    async def _handle_tool_call_progress(self, event_data, session_id: str, task_id: str):
        """处理工具调用进度事件"""
        getattr(event_data, "status", None)
        message = getattr(event_data, "message", "")
        progress_percentage = getattr(event_data, "progress_percentage", None)
        current_step = getattr(event_data, "current_step", None)
        total_steps = getattr(event_data, "total_steps", None)
        current_step_index = getattr(event_data, "current_step_index", None)

        # 构建详细的消息内容
        if current_step and total_steps:
            message = f"{message} ({current_step_index + 1}/{total_steps}: {current_step})" if current_step_index is not None else f"{message} ({current_step})"

        return ToolCallProgressMessage(
            session_id=session_id,
            task_id=task_id,
            tool_name=event_data.tool_name if hasattr(event_data, "tool_name") else "",
            message=message,
            progress_percentage=progress_percentage,
            tool_call_id=getattr(event_data, "tool_call_id", None),
        )

    async def _handle_tool_call_result(self, event_data, session_id: str, task_id: str, workspace_id):
        """处理工具调用结果事件"""
        logger.info("[CHAT_HANDLER] 🔧 Processing TOOL_CALL_RESULT event")

        result = event_data.get("result", "") if isinstance(event_data, dict) else getattr(event_data, "result", "")
        is_error = event_data.get("is_error", False) if isinstance(event_data, dict) else getattr(event_data, "is_error", False)
        error_message = event_data.get("error_message") if isinstance(event_data, dict) else getattr(event_data, "error_message", None)
        execution_time = event_data.get("execution_time") if isinstance(event_data, dict) else getattr(event_data, "execution_time", None)
        tool_name = event_data.get("tool_name", "") if isinstance(event_data, dict) else (getattr(event_data, "tool_name", "") if hasattr(event_data, "tool_name") else "")
        tool_call_id = event_data.get("tool_call_id") if isinstance(event_data, dict) else getattr(event_data, "tool_call_id", None)

        # 如果是错误，使用错误消息作为结果
        if is_error and error_message:
            result = error_message

        # 如果有执行时间，添加到结果中
        if execution_time is not None and not is_error:
            if isinstance(result, dict):
                result["_execution_time"] = f"{execution_time:.2f}s"
            else:
                result = f"{result}\n\n执行时间: {execution_time:.2f}s"

        logger.info(
            f"[CHAT_HANDLER] 🔧 Creating ToolCallResultMessage: tool_name={tool_name}, tool_call_id={tool_call_id}",
        )

        return ToolCallResultMessage(
            session_id=session_id,
            task_id=task_id,
            tool_name=tool_name,
            result=result,
            is_error=is_error,
            tool_call_id=tool_call_id,
            workspace_id=workspace_id,
        )

    async def _handle_checkpoint_created(self, event_data, session_id: str, task_id: str):
        """处理检查点创建事件"""
        return TaskNodeProgressMessage(
            session_id=session_id,
            task_id=task_id,
            task_node_id=task_id,
            progress=50,
            status="executing",
            message=f"检查点已创建: {event_data.checkpoint_id if hasattr(event_data, 'checkpoint_id') else ''}",
            data={
                "checkpoint_id": (event_data.checkpoint_id if hasattr(event_data, "checkpoint_id") else ""),
                "checkpoint_path": (event_data.checkpoint_path if hasattr(event_data, "checkpoint_path") else ""),
                "checkpoint_size": (event_data.checkpoint_size if hasattr(event_data, "checkpoint_size") else 0),
            },
        )

    async def _handle_state_changed(self, event_data, session_id: str, task_id: str):
        """处理状态变更事件"""
        return TaskNodeProgressMessage(
            session_id=session_id,
            task_id=task_id,
            task_node_id=task_id,
            progress=20,
            status="state_change",
            message=f"任务状态变更为: {event_data.new_state if hasattr(event_data, 'new_state') else ''}",
            data=(event_data.get_event_data() if hasattr(event_data, "get_event_data") else {}),
        )

    async def _handle_followup_question(self, event_data, session_id: str, task_id: str, user_message_id: str):
        """处理追问问题事件"""
        event_session_id = event_data.get("session_id", session_id)

        return FollowupQuestionMessage(
            session_id=event_session_id,
            task_id=task_id,
            question=event_data.get("question", ""),
            suggestions=event_data.get("suggestions", []),
            tool_call_id=event_data.get("tool_call_id", ""),
            user_message_id=user_message_id,
        )

    async def _handle_a2ui_surface_event(self, event_data, session_id: str, task_id: str, user_message_id: str):
        """处理 A2UI UI 组件事件"""
        a2ui_message = event_data.get("a2ui_message", {})
        event_data.get("surface_id", "")

        return A2UIServerEventMessage(
            messages=a2ui_message.get("messages", []),
            metadata=a2ui_message.get("metadata", {}),
            session_id=session_id,
            user_message_id=user_message_id,
        )
