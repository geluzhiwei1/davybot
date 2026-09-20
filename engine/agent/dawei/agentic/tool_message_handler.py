# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工具消息处理器
负责处理流式消息中的工具调用相关逻辑
"""

import asyncio
import json
import traceback
from typing import List, Dict, Any

from dawei.agentic.errors import ToolExecutionError
from dawei.core.events import TaskEventType, emit_typed_event
from dawei.entity.lm_messages import AssistantMessage, ToolCall, ToolMessage
from dawei.entity.stream_message import CompleteMessage, StreamMessages
from dawei.logg.logging import get_logger


class ToolMessageHandle:
    """工具消息处理器类
    负责处理流式消息中的工具调用相关逻辑
    """

    def __init__(self, task_node, user_workspace, tool_call_service, event_bus, conversation=None):
        """初始化工具消息处理器

        Args:
            task_node: 任务节点实例
            user_workspace: 用户工作区实例
            tool_call_service: 工具调用服务接口实例
            event_bus: 事件总线接口实例
            conversation: 子任务独立会话（P2-7，None = 共享 workspace.current_conversation）

        """
        self.task_node = task_node
        self._user_workspace = user_workspace
        self._tool_call_service = tool_call_service
        self._event_bus = event_bus
        self._conversation = conversation  # P2-7: executor 持有的隔离会话
        self.logger = get_logger(__name__)

        # 【关键修复】attempt_completion 标志 - 用于在 execute_tool_call 时立即标记已完成
        self._has_attempt_completion: bool = False

        # 【关键修复】工具调用去重 - 防止重复执行相同的工具调用
        self._executed_tool_calls: set = set()

        # 截断标记:最近一轮 CompleteMessage 的 finish_reason == "length"
        # (输出被 max_tokens 掐断,常见于推理型模型思考耗尽预算),供 executor 重试判定
        self._last_round_truncated: bool = False

    @property
    def active_conversation(self):
        """P2-7：隔离会话优先，否则回落 workspace 指针"""
        return self._conversation or self._user_workspace.current_conversation

    def _check_task_tool_denied(self, function_name: str) -> str | None:
        """P3-1+：节点 metadata 的 tools_allowlist/denylist 运行时强制

        数据源 agent_profile.task_tool_filter_from_metadata，allowlist 优先于
        denylist。（mode-工具解耦 D4/D7：原提示词层裁剪
        user_workspace._apply_task_tool_filter_stage 已删除，本守卫成为节点级
        allow/deny 的唯一强制层。）守卫自身异常时放行并大声记日志
        (fail-open 只针对守卫代码缺陷，防御性兜底由 workspace allow/deny 承担)。

        Returns:
            拒绝原因（给 LLM 看的可读文本）或 None（放行）
        """
        try:
            from dawei.agentic.agent_profile import task_tool_filter_from_metadata

            meta = getattr(getattr(self.task_node, "data", None), "metadata", None)
            if not meta:
                return None
            tf = task_tool_filter_from_metadata(meta)
            if tf is None:
                return None
            allow = tf.get("allow")
            deny = tf.get("deny") or []
            if allow is not None and function_name not in allow:
                return (
                    f"Tool '{function_name}' is not in this subtask's tools_allowlist "
                    f"(allowed: {sorted(allow)}); use only the tools granted at dispatch"
                )
            if function_name in deny:
                return f"Tool '{function_name}' is denied by this subtask's tools_denylist (agent profile restriction)"
            return None
        except Exception:  # noqa: BLE001 — 守卫缺陷不砖死子任务
            self.logger.exception(f"Task tool filter check failed for {function_name}; allowing: ")
            return None

    @property
    def last_round_truncated(self) -> bool:
        """最近一轮 LLM 输出是否被 max_tokens 截断(finish_reason=length)"""
        return self._last_round_truncated

    async def handle_stream_messages(
        self,
        stream_message: StreamMessages,
    ) -> Dict[str, Any] | None:
        """处理完成消息，获取其中的 tool_calls 并执行

        Args:
            stream_message: 流式消息

        Returns:
            处理结果

        """
        # 只处理完成消息
        if isinstance(stream_message, CompleteMessage):
            # 截断检测:finish_reason=length 表示输出被 max_tokens 掐断,此轮结果不完整,
            # 由 executor 决定重试而非判完成(见 task_node_executor._should_continue_execution)
            self._last_round_truncated = str(getattr(stream_message, "finish_reason", "") or "") == "length"
            if self._last_round_truncated:
                self.logger.warning(
                    "LLM output truncated by max_tokens (finish_reason=length): "
                    f"content_len={len(str(stream_message.content or ''))}, "
                    f"tool_calls={len(getattr(stream_message, 'tool_calls', None) or [])}, "
                    f"usage={getattr(stream_message, 'usage', None)}"
                )
            final_content = stream_message.content
            # 【关键修复】内容为空但存在可见推理内容时，用推理内容兜底
            # （镜像 openai_compatible_api.complete() 的回退逻辑），
            # 避免最终消息因内容不可见被 Conversation.add_message 过滤丢弃
            if (
                not final_content or not str(final_content).strip()
            ) and not getattr(stream_message, "tool_calls", None):
                reasoning = getattr(stream_message, "reasoning_content", None)
                if reasoning and str(reasoning).strip():
                    final_content = str(reasoning)

            self.active_conversation.say(
                AssistantMessage(
                    content=final_content,
                    tool_calls=getattr(stream_message, "tool_calls", None),
                ),
            )

            # 获取工具调用列表
            tool_calls = getattr(stream_message, "tool_calls", [])

            if tool_calls:
                self.logger.debug(f"Processing {len(tool_calls)} tool calls from CompleteMessage")

                # 发送工具调用检测事件
                await emit_typed_event(
                    TaskEventType.TOOL_CALLS_DETECTED,
                    stream_message,
                    self._event_bus,
                    task_id=self.task_node.task_node_id,
                    source="stream_message",
                )

                # 处理每个工具调用
                for i, tool_call_obj in enumerate(tool_calls):
                    self.logger.debug(
                        f"Processing tool call {i + 1}/{len(tool_calls)}: {tool_call_obj.function.name}",
                    )

                    # 【关键修复】检查是否已执行过此工具调用，防止重复执行
                    tool_call_id = tool_call_obj.tool_call_id
                    if tool_call_id in self._executed_tool_calls:
                        self.logger.info(f"Tool call {tool_call_id} already executed, skipping")
                        continue

                    self._executed_tool_calls.add(tool_call_id)

                    # 如果是 attempt_completion 工具，设置标志、发送结果事件、然后返回
                    if tool_call_obj.function.name == "attempt_completion":
                        self._has_attempt_completion = True
                        self.logger.info(
                            "[ATTEMPT_COMPLETION] Detected in handle_stream_messages, set flag to True",
                        )

                        # 解析 attempt_completion 参数，提取 result 内容
                        try:
                            ac_arguments = json.loads(tool_call_obj.function.arguments)
                            ac_result_text = ac_arguments.get("result", "")
                        except (json.JSONDecodeError, TypeError):
                            ac_result_text = tool_call_obj.function.arguments or ""

                        # 构造工具执行结果（与 AttemptCompletionTool._run 返回格式一致）
                        ac_result = {
                            "type": "task_completion",
                            "status": "completed",
                            "result": ac_result_text,
                            "message": "Task completed successfully",
                        }
                        ac_message_content = json.dumps(ac_result, ensure_ascii=False)

                        # 添加 ToolMessage 到对话（持久化，供历史重载使用）
                        self.active_conversation.say(
                            ToolMessage(
                                content=ac_message_content,
                                tool_call_id=tool_call_obj.tool_call_id,
                            ),
                        )
                        self.logger.info(
                            f"[ATTEMPT_COMPLETION] Added ToolMessage to conversation, result length={len(ac_result_text)}",
                        )

                        # 发送工具调用进度事件（完成）
                        await emit_typed_event(
                            TaskEventType.TOOL_CALL_PROGRESS,
                            {
                                "tool_name": "attempt_completion",
                                "message": "工具执行完成",
                                "progress_percentage": 100,
                                "tool_call_id": tool_call_obj.tool_call_id,
                            },
                            self._event_bus,
                            task_id=self.task_node.task_node_id,
                            source="tool_execution",
                        )

                        # 发送工具调用结果事件（关键：让前端收到 attempt_completion 的 result 内容）
                        await emit_typed_event(
                            TaskEventType.TOOL_CALL_RESULT,
                            {
                                "tool_name": "attempt_completion",
                                "result": ac_result,
                                "is_error": False,
                                "tool_call_id": tool_call_obj.tool_call_id,
                            },
                            self._event_bus,
                            task_id=self.task_node.task_node_id,
                            source="tool_execution",
                        )
                        self.logger.info("[ATTEMPT_COMPLETION] Emitted TOOL_CALL_RESULT event with result content")

                        return None

                    # 直接执行工具调用
                    self.logger.info(
                        f"Executing tool call in real-time: {tool_call_obj.function.name}",
                    )
                    await self.execute_tool_call(tool_call_obj)

            else:
                self.logger.debug("No tool calls found in CompleteMessage")
        return None

    async def execute_tool_call(self, tool_call_obj: ToolCall) -> Any | Dict[str, str]:
        """执行完整的工具调用（从流式响应中检测到的）

        Args:
            tool_call_obj: 完整的工具调用对象

        Returns:
            工具执行结果

        """
        function_name = tool_call_obj.function.name
        arguments_str = tool_call_obj.function.arguments
        tool_call_id = tool_call_obj.tool_call_id

        self.logger.debug(
            f"Executing tool call: {function_name} with args: {arguments_str[:100]}...",
        )

        # P3-1+ 运行时工具面强制：节点级 tools_allowlist/denylist 此前只裁剪
        # 发给 LLM 的 schema(提示词层)——幻觉调用的被禁工具仍会真执行。
        # 这里是执行层 choke point：拒绝即返回可见错误(FAST FAIL 不 re-raise，
        # 镜像下方 JSONDecodeError 路径——错误 ToolMessage 必须紧跟 tool_calls)。
        # attempt_completion 不经此处(控制面在 handle_stream_messages)，不会被误禁。
        denial = self._check_task_tool_denied(function_name)
        if denial:
            error_result = {"error": denial, "tool_name": function_name, "denied_by": "task_tool_filter"}
            self.active_conversation.say(
                ToolMessage(
                    content=json.dumps(error_result, ensure_ascii=False),
                    tool_call_id=tool_call_obj.tool_call_id,
                ),
            )
            await emit_typed_event(
                TaskEventType.TOOL_CALL_START,
                {"tool_name": function_name, "tool_input": None, "tool_call_id": tool_call_id},
                self._event_bus,
                task_id=self.task_node.task_node_id,
                source="tool_execution",
            )
            await emit_typed_event(
                TaskEventType.TOOL_CALL_RESULT,
                {
                    "tool_name": function_name,
                    "result": error_result,
                    "is_error": True,
                    "tool_call_id": tool_call_id,
                },
                self._event_bus,
                task_id=self.task_node.task_node_id,
                source="tool_execution",
            )
            self.logger.warning(f"Tool call denied by task tool filter: {function_name} ({denial})")
            return error_result

        # 特殊处理 ask_followup_question
        if function_name == "ask_followup_question":
            return await self._handle_ask_followup_question(tool_call_obj, tool_call_id)

        # 工具执行前不添加消息到对话
        self.logger.debug(
            f"Tool call will be merged with content in CompleteMessage: function={function_name}, tool_call_id={tool_call_id}",
        )

        try:
            # 解析参数
            try:
                arguments = json.loads(arguments_str)

                # 🔧 格式转换：自动处理update_todo_list的字符串格式
                if function_name == "update_todo_list" and isinstance(arguments.get("todos"), str):
                    self.logger.info(
                        "Detected string format for update_todo_list, converting to array format",
                    )
                    # 将字符串转换为数组（按换行符分割）
                    lines = arguments["todos"].strip().split("\n")
                    arguments["todos"] = [line.strip() for line in lines if line.strip()]
                    self.logger.info(
                        f"Converted todos to array with {len(arguments['todos'])} items",
                    )

                self.logger.debug(
                    f"Parsed arguments for {function_name}: {type(arguments)} with {len(arguments) if isinstance(arguments, dict) else 'N/A'} items",
                )
            except json.JSONDecodeError as e:
                self.logger.error(
                    f"Failed to parse tool arguments for {function_name}: {e}",
                    exc_info=True,
                )
                self.logger.exception(f"Invalid arguments string: {arguments_str}")

                # 🆕 尝试修复常见的 LLM JSON 生成错误
                arguments = self._try_fix_malformed_json(arguments_str, function_name)
                if arguments:
                    self.logger.info(f"Successfully recovered malformed JSON for {function_name}")
                else:
                    # 修复失败，构建错误结果
                    error_result = {
                        "error": f"Invalid arguments: {e}",
                        "raw_arguments": arguments_str,
                    }

                    # 添加工具消息到对话历史（包含错误信息）
                    self.active_conversation.say(
                        ToolMessage(
                            content=json.dumps(error_result, ensure_ascii=False),
                            tool_call_id=tool_call_obj.tool_call_id,
                        ),
                    )

                    # 发送工具调用开始事件（失败）
                    await emit_typed_event(
                        TaskEventType.TOOL_CALL_START,
                        {
                            "tool_name": function_name,
                            "tool_input": {"raw_arguments": arguments_str},
                            "tool_call_id": tool_call_id,
                        },
                        self._event_bus,
                        task_id=self.task_node.task_node_id,
                        source="tool_execution",
                    )

                    # 发送工具调用结果事件（失败）
                    await emit_typed_event(
                        TaskEventType.TOOL_CALL_RESULT,
                        {
                            "tool_name": function_name,
                            "result": error_result,
                            "is_error": True,
                            "tool_call_id": tool_call_id,
                        },
                        self._event_bus,
                        task_id=self.task_node.task_node_id,
                        source="tool_execution",
                    )

                    # 发送错误事件
                    await emit_typed_event(
                        TaskEventType.ERROR_OCCURRED,
                        {
                            "error": f"Failed to parse tool arguments for {function_name}: {e}",
                            "details": {"raw_arguments": arguments_str},
                        },
                        self._event_bus,
                        task_id=self.task_node.task_node_id,
                        source="tool_execution",
                    )

                    # FAST FAIL：错误随返回值交付,不再 re-raise——
                    # JSONDecodeError 是 ValueError 子类,会被外层
                    # except (ToolExecutionError, ValueError, KeyError) 再次捕获
                    # 并追加第二条同 tool_call_id 的 ToolMessage,违反 OpenAI 协议
                    # (tool 消息必须紧跟带 tool_calls 的 assistant),下一轮 LLM 400。
                    return error_result

            # ✅ 只有JSON解析成功才会执行到这里
            # 创建任务上下文
            context = self._user_workspace.create_task_context()
            self.logger.debug(f"Created task context for tool execution: {type(context)}")

            # 发送工具调用开始事件
            await emit_typed_event(
                TaskEventType.TOOL_CALL_START,
                {
                    "tool_name": function_name,
                    "tool_input": arguments,
                    "tool_call_id": tool_call_id,
                },
                self._event_bus,
                task_id=self.task_node.task_node_id,
                source="tool_execution",
            )

            # 执行工具 - 保持原始context传递逻辑，同时传递task_id
            task_id = self.task_node.task_node_id
            self.logger.debug(f"Calling tool service to execute: {function_name} with task_id: {task_id}")
            result = await self._tool_call_service.execute_tool(function_name, arguments, context, task_id=task_id)
            self.logger.debug(
                f"Tool execution result type: {type(result)}, size: {len(str(result)) if result else 0}",
            )

            # ── U1 fix: Result bifurcation — detect GovernedResult envelope ──
            from dawei.tools.result_governance import GovernedResult

            governed = None
            if isinstance(result, dict) and isinstance(result.get("result"), GovernedResult):
                governed = result["result"]
            elif isinstance(result, GovernedResult):
                governed = result

            # 【A2UI集成】检查工具结果是否包含A2UI数据
            if isinstance(result, dict) and result.get("__a2ui__"):
                # 处理A2UI结果 - 通过WebSocket发送到前端
                await self._handle_a2ui_result(result, task_id=self.task_node.task_node_id)

            # 在工具执行后，添加工具消息到对话
            # U1 fix: if GovernedResult, use to_llm_content() for LLM + to_governance_meta() for persistence
            if governed is not None:
                message_content = governed.to_llm_content()
                governance_meta = governed.to_governance_meta()
            elif isinstance(result, dict) and result.get("__a2ui__"):
                message_content = result["message"]
                governance_meta = None
            else:
                message_content = json.dumps(result, ensure_ascii=False)
                governance_meta = None

            self.active_conversation.say(
                ToolMessage(
                    content=message_content,
                    tool_call_id=tool_call_obj.tool_call_id,
                    governance_meta=governance_meta,  # X1 fix: persist governance metadata
                ),
            )
            self.logger.info(
                f"Added tool message to conversation: function={function_name}, tool_call_id={tool_call_id}",
            )

            # 【关键修复】设置 attempt_completion 标志，用于 _should_continue_execution 检查
            if function_name == "attempt_completion":
                self._has_attempt_completion = True
                self.logger.info("Set _has_attempt_completion flag: True")

            # 发送工具调用进度事件（完成）
            await emit_typed_event(
                TaskEventType.TOOL_CALL_PROGRESS,
                {
                    "tool_name": function_name,
                    "message": "工具执行完成",
                    "progress_percentage": 100,
                    "tool_call_id": tool_call_id,
                },
                self._event_bus,
                task_id=self.task_node.task_node_id,
                source="tool_execution",
            )

            # 发送工具调用结果事件（成功）
            self.logger.info(
                f"[TOOL_EVENT] About to emit TOOL_CALL_RESULT event for tool={function_name}, task_id={self.task_node.task_node_id}, tool_call_id={tool_call_id}",
            )

            await emit_typed_event(
                TaskEventType.TOOL_CALL_RESULT,
                {
                    "tool_name": function_name,
                    # U1 fix: if GovernedResult, send event payload (data + _governance) to frontend
                    "result": governed.to_event_payload() if governed is not None else result,
                    "is_error": False,
                    "tool_call_id": tool_call_id,
                },
                self._event_bus,
                task_id=self.task_node.task_node_id,
                source="tool_execution",
            )

            self.logger.info(
                f"[TOOL_EVENT] Successfully emitted TOOL_CALL_RESULT event for tool={function_name}",
            )
            self.logger.info(f"Tool call executed in real-time: {function_name}")
            return result

        except asyncio.CancelledError:
            # 工具执行被取消
            self.logger.info(f"Tool execution cancelled: {function_name}")
            raise
        except (ToolExecutionError, ValueError, KeyError) as e:
            # 工具执行的业务错误 - 使用通用异常处理逻辑
            return await self._handle_tool_execution_error(
                function_name,
                tool_call_obj.tool_call_id,
                str(e),
                tool_call_id,
            )
        except Exception as e:
            # 未预期的工具执行错误
            return await self._handle_tool_execution_error_with_traceback(
                function_name,
                tool_call_obj.tool_call_id,
                e,
                tool_call_id,
            )

    async def _handle_tool_execution_error(
        self,
        function_name: str,
        tool_call_id: str,
        error_message: str,
        _original_tool_call_id: str,
    ) -> Dict[str, Any]:
        """通用的工具执行错误处理方法

        Args:
            function_name: 工具名称
            tool_call_id: 工具调用ID
            error_message: 错误消息
            original_tool_call_id: 原始工具调用ID（用于日志）

        Returns:
            错误结果字典

        """
        self.logger.error(
            f"Tool execution failed: {function_name} - {error_message}",
            exc_info=True,
        )

        # 构建错误结果
        error_result = {"error": error_message}

        # 添加工具消息到对话历史（包含错误信息）
        self.active_conversation.say(
            ToolMessage(
                content=json.dumps(error_result, ensure_ascii=False),
                tool_call_id=tool_call_id,
            ),
        )

        await emit_typed_event(
            TaskEventType.TOOL_CALL_RESULT,
            {
                "tool_name": function_name,
                "result": error_result,
                "is_error": True,
                "tool_call_id": tool_call_id,
            },
            self._event_bus,
            task_id=self.task_node.task_node_id,
            source="tool_execution",
        )
        return error_result

    async def _handle_tool_execution_error_with_traceback(
        self,
        function_name: str,
        tool_call_id: str,
        error: Exception,
        _original_tool_call_id: str,
    ) -> Dict[str, Any]:
        """通用的工具执行错误处理方法（包含 traceback）

        Args:
            function_name: 工具名称
            tool_call_id: 工具调用ID
            error: 错误异常对象
            original_tool_call_id: 原始工具调用ID（用于日志）

        Returns:
            错误结果字典

        """
        self.logger.error(f"Failed to execute tool call in real-time: {error}", exc_info=True)
        self.logger.error(f"Tool execution traceback: {traceback.format_exc()}")

        # 构建错误结果
        error_result = {"error": str(error), "traceback": traceback.format_exc()}

        # 添加工具消息到对话历史（包含错误信息）
        self.active_conversation.say(
            ToolMessage(
                content=json.dumps(error_result, ensure_ascii=False),
                tool_call_id=tool_call_id,
            ),
        )

        await emit_typed_event(
            TaskEventType.TOOL_CALL_RESULT,
            {
                "tool_name": function_name,
                "result": error_result,
                "is_error": True,
                "tool_call_id": tool_call_id,
            },
            self._event_bus,
            task_id=self.task_node.task_node_id,
            source="tool_execution",
        )

        await emit_typed_event(
            TaskEventType.ERROR_OCCURRED,
            {
                "error": f"Failed to execute tool call: {error}",
                "details": {
                    "tool_name": function_name,
                    "traceback": traceback.format_exc(),
                },
            },
            self._event_bus,
            task_id=self.task_node.task_node_id,
            source="tool_execution",
        )

        return error_result

    async def _handle_ask_followup_question(
        self,
        tool_call_obj: ToolCall,
        tool_call_id: str,
    ) -> Dict[str, Any]:
        """处理 ask_followup_question 工具调用

        Args:
            tool_call_obj: 工具调用对象
            tool_call_id: 工具调用ID

        Returns:
            工具执行结果

        """
        try:
            # 解析参数
            arguments_str = tool_call_obj.function.arguments
            arguments = json.loads(arguments_str)

            question = arguments.get("question", "")
            suggestions = arguments.get("follow_up", [])

            # 🔍 验证 suggestions 参数
            if not suggestions:
                self.logger.warning(
                    f"[FOLLOWUP_DEBUG] ⚠️ 'follow_up' parameter is missing or empty! "
                    f"This will cause 'suggestions 为空或未定义' error in frontend. "
                    f"Available keys in arguments: {list(arguments.keys())}"
                )
            elif len(suggestions) < 2:
                self.logger.warning(
                    f"[FOLLOWUP_DEBUG] ⚠️ 'follow_up' has only {len(suggestions)} suggestion(s). "
                    f"Expected 2-4 suggestions. This may cause display issues."
                )
            elif len(suggestions) > 4:
                self.logger.warning(
                    f"[FOLLOWUP_DEBUG] ⚠️ 'follow_up' has {len(suggestions)} suggestions. "
                    f"Expected 2-4 suggestions. Only first 4 will be used."
                )

            # 发送工具调用开始事件
            await emit_typed_event(
                TaskEventType.TOOL_CALL_START,
                {
                    "tool_name": "ask_followup_question",
                    "tool_input": arguments,
                    "tool_call_id": tool_call_id,
                },
                self._event_bus,
                task_id=self.task_node.task_node_id,
                source="tool_message_handler",
            )

            # 发送追问问题消息到前端
            try:
                from dawei.websocket.protocol import FollowupQuestionMessage
            except ImportError:
                self.logger.exception("Failed to import FollowupQuestionMessage: ")
                raise

            # 获取正确的 session_id（从任务上下文中）
            session_id = self.task_node.context.session_id if self.task_node.context else ""

            # 获取 conversation_id：前端 chat-store 严格按 conversation_id 路由消息，
            # FollowupQuestionMessage 必须带上它，否则追问事件会被前端丢弃、弹窗永不显示。
            conversation_id = ""
            if self.active_conversation:
                conversation_id = getattr(self.active_conversation, "id", "") or ""

            # 去除建议答案中的 <suggest> 标签
            cleaned_suggestions = []
            for suggestion in suggestions:
                # 移除 <suggest> 和 </suggest> 标签
                cleaned = suggestion.replace("<suggest>", "").replace("</suggest>", "").strip()
                cleaned_suggestions.append(cleaned)

            if not cleaned_suggestions:
                self.logger.error(
                    f"[FOLLOWUP_DEBUG] ❌ CRITICAL: cleaned_suggestions is empty! "
                    f"This WILL cause 'suggestions 为空或未定义' error in frontend! "
                    f"Original suggestions were: {suggestions}"
                )

            # 发送追问问题事件（在 event_data 中包含 session_id）
            await emit_typed_event(
                TaskEventType.FOLLOWUP_QUESTION,
                {
                    "session_id": session_id,  # 重要：在事件数据中包含 session_id
                    "conversation_id": conversation_id,  # 前端按此路由到对话（缺失会被丢弃）
                    "question": question,
                    "suggestions": cleaned_suggestions,  # 使用清理后的建议
                    "tool_call_id": tool_call_id,
                },
                self._event_bus,
                task_id=self.task_node.task_node_id,
                source="tool_message_handler",
            )

            # 暂停任务执行，等待用户响应
            self.logger.info(
                f"Task paused, waiting for user response to tool_call_id: {tool_call_id}",
            )

            # 创建一个Future来等待用户响应
            if not hasattr(self, "_pending_followup_responses"):
                self._pending_followup_responses = {}

            response_future = asyncio.Future()
            self._pending_followup_responses[tool_call_id] = response_future

            # 等待用户响应；超时由 AGENT_TIMEOUT_FOLLOWUP_QUESTION_TIMEOUT 配置，
            # 默认 -1 = 不限时，一直等用户点击发送（超时续跑曾导致任务被自动收尾）
            from dawei.config.settings import get_settings

            followup_timeout = get_settings().agent_timeout.followup_question_timeout
            try:
                if followup_timeout and followup_timeout > 0:
                    response = await asyncio.wait_for(response_future, timeout=followup_timeout)
                else:
                    response = await response_future
                self.logger.info(f"Received user response: {response[:50]}...")

                # 发送工具调用结果事件（成功）
                result = {
                    "type": "followup_response",
                    "question": question,
                    "user_response": response,
                    "status": "completed",
                }

                await emit_typed_event(
                    TaskEventType.TOOL_CALL_RESULT,
                    {
                        "tool_name": "ask_followup_question",
                        "result": result,
                        "is_error": False,
                        "tool_call_id": tool_call_id,
                    },
                    self._event_bus,
                    task_id=self.task_node.task_node_id,
                    source="tool_message_handler",
                )

                # 将用户回复作为 ToolMessage 添加到对话历史
                # 这样新一轮 LLM 调用时能看到用户的回答
                self.active_conversation.say(
                    ToolMessage(
                        content=json.dumps(result, ensure_ascii=False),
                        tool_call_id=tool_call_id,
                    ),
                )
                self.logger.info(
                    f"Added followup response ToolMessage to conversation: tool_call_id={tool_call_id}",
                )

                # 返回结果，告诉 LLM 用户的回答
                return result

            except TimeoutError:
                self.logger.exception(f"Followup question timeout for tool_call_id: {tool_call_id}")

                # 发送工具调用结果事件（超时）
                result = {
                    "type": "followup_response",
                    "question": question,
                    "user_response": "No response (timeout)",
                    "status": "timeout",
                }

                await emit_typed_event(
                    TaskEventType.TOOL_CALL_RESULT,
                    {
                        "tool_name": "ask_followup_question",
                        "result": result,
                        "is_error": True,
                        "tool_call_id": tool_call_id,
                    },
                    self._event_bus,
                    task_id=self.task_node.task_node_id,
                    source="tool_message_handler",
                )

                # 将超时结果也添加到对话历史
                self.active_conversation.say(
                    ToolMessage(
                        content=json.dumps(result, ensure_ascii=False),
                        tool_call_id=tool_call_id,
                    ),
                )

                return result
            finally:
                # 清理
                if tool_call_id in self._pending_followup_responses:
                    del self._pending_followup_responses[tool_call_id]

        except asyncio.CancelledError:
            self.logger.info("Followup question handling cancelled")

            # 发送工具调用结果事件（取消）
            try:
                await emit_typed_event(
                    TaskEventType.TOOL_CALL_RESULT,
                    {
                        "tool_name": "ask_followup_question",
                        "result": {"status": "cancelled"},
                        "is_error": True,
                        "tool_call_id": tool_call_id,
                    },
                    self._event_bus,
                    task_id=self.task_node.task_node_id,
                    source="tool_message_handler",
                )
            except Exception as event_error:
                # 记录事件发送失败，但不中断工具取消流程
                self.logger.error(
                    f"Failed to send tool cancellation event: {event_error}",
                    exc_info=True,
                    context={
                        "tool_call_id": tool_call_id,
                        "task_id": self.task_node.task_node_id,
                    },
                )
                # 不中断：工具取消已经完成，只是事件发送失败

            raise
        except Exception as e:
            self.logger.error(f"Error handling ask_followup_question: {e}", exc_info=True)

            # 发送工具调用结果事件（错误）
            try:
                result = {
                    "type": "followup_response",
                    "error": str(e),
                    "status": "error",
                }

                await emit_typed_event(
                    TaskEventType.TOOL_CALL_RESULT,
                    {
                        "tool_name": "ask_followup_question",
                        "result": result,
                        "is_error": True,
                        "tool_call_id": tool_call_id,
                    },
                    self._event_bus,
                    task_id=self.task_node.task_node_id,
                    source="tool_message_handler",
                )
            except Exception as event_error:
                # 记录事件发送失败，但不中断错误处理流程
                self.logger.error(
                    f"Failed to send tool error event: {event_error}",
                    exc_info=True,
                    context={
                        "tool_call_id": tool_call_id,
                        "task_id": self.task_node.task_node_id,
                    },
                )
                # 不中断：错误处理流程继续，返回结果

            return result

    async def handle_followup_response(self, tool_call_id: str, response: str) -> bool:
        """处理前端发来的追问回复

        Args:
            tool_call_id: 工具调用ID
            response: 用户回复

        Returns:
            是否成功处理

        """
        try:
            if hasattr(self, "_pending_followup_responses") and tool_call_id in self._pending_followup_responses:
                future = self._pending_followup_responses[tool_call_id]
                if not future.done():
                    future.set_result(response)
                    self.logger.info(f"Followup response set for tool_call_id: {tool_call_id}")
                    return True
                self.logger.warning(f"Future already done for tool_call_id: {tool_call_id}")
                return False
            self.logger.warning(f"No pending followup for tool_call_id: {tool_call_id}")
            return False

        except Exception as e:
            self.logger.error(
                f"Error handling followup response: {e}",
                exc_info=True,
                context={
                    "tool_call_id": tool_call_id,
                    "response_length": len(response),
                    "task_id": self.task_node.task_node_id,
                },
            )
            # 返回具体的错误信息，而不仅仅是 False
            return {"error": str(e), "tool_call_id": tool_call_id, "success": False}

    async def handle_followup_cancel(self, tool_call_id: str, reason: str) -> bool:
        """处理前端发来的追问取消

        Args:
            tool_call_id: 工具调用ID
            reason: 取消原因 (user_cancelled, timeout, skipped)

        Returns:
            是否成功处理

        """
        if hasattr(self, "_pending_followup_responses") and tool_call_id in self._pending_followup_responses:
            future = self._pending_followup_responses[tool_call_id]
            if not future.done():
                # 取消Future
                future.cancel()

                self.logger.info(
                    f"Followup cancelled for tool_call_id: {tool_call_id}, reason: {reason}",
                )

                # 发送工具调用结果事件（取消）
                try:
                    result = {
                        "type": "followup_response",
                        "reason": reason,
                        "user_response": f"Cancelled: {reason}",
                        "status": "cancelled",
                    }

                    await emit_typed_event(
                        TaskEventType.TOOL_CALL_RESULT,
                        {
                            "tool_name": "ask_followup_question",
                            "result": result,
                            "is_error": True,
                            "tool_call_id": tool_call_id,
                        },
                        self._event_bus,
                        task_id=self.task_node.task_node_id,
                        source="tool_message_handler",
                    )
                except Exception as event_error:
                    # 记录事件发送失败，但不中断取消流程
                    self.logger.error(
                        f"Failed to send followup cancel event: {event_error}",
                        exc_info=True,
                        context={
                            "tool_call_id": tool_call_id,
                            "task_id": self.task_node.task_node_id,
                        },
                    )
                    # 不中断：取消已经完成，只是事件发送失败

                # 清理资源
                del self._pending_followup_responses[tool_call_id]

                return True

            self.logger.warning(f"Future already done for tool_call_id: {tool_call_id}")
            return False

        self.logger.warning(f"No pending followup for tool_call_id: {tool_call_id}")
        return False

    def _try_fix_malformed_json(self, json_str: str, function_name: str) -> dict | None:
        """尝试修复常见的 LLM JSON 生成错误

        Args:
            json_str: 格式错误的 JSON 字符串
            function_name: 工具名称

        Returns:
            修复后的字典，如果无法修复则返回 None

        """
        import re

        try:
            # 针对特定的错误模式进行修复
            if function_name == "update_todo_list":
                # 修复模式: {"todos":[ ] item1, ] item2, ...}
                # 提取 todos 数组的内容
                todos_match = re.search(r'"todos"\s*:\s*\[\s*\]([^\]]+)\]', json_str)
                if todos_match:
                    # 提取所有待办事项
                    content = todos_match.group(1)
                    # 移除所有 ] 符号和前导逗号
                    items = []
                    for line in content.split(","):
                        # 清理每一行
                        cleaned = re.sub(r"\s*\]\s*", "", line.strip())
                        if cleaned:
                            items.append(cleaned)

                    if items:
                        return {"todos": items}

            # 通用修复：移除数组元素前的 ]
            fixed = re.sub(r"\]\s*,", ",", json_str)
            fixed = re.sub(r"\]\s+", " ", fixed)

            # 尝试解析修复后的 JSON
            return json.loads(fixed)

        except (json.JSONDecodeError, Exception) as e:
            self.logger.debug(f"Failed to fix malformed JSON: {e}")
            return None

    @property
    def has_attempt_completion(self) -> bool:
        """获取是否已执行 attempt_completion 工具的标志

        Returns:
            是否已执行 attempt_completion 工具

        """
        return self._has_attempt_completion

    async def _handle_a2ui_result(self, result: dict, task_id: str) -> None:
        """处理A2UI工具结果，通过WebSocket发送到前端

        Args:
            result: A2UI工具返回的结果字典，包含__a2ui__标记
            task_id: 任务ID

        """
        try:
            from dawei.websocket.protocol import A2UIServerEventMessage

            # 获取session_id
            session_id = self.task_node.context.session_id if self.task_node.context else ""

            # 提取A2UI数据
            a2ui_data = result.get("a2ui_data")
            if not a2ui_data:
                self.logger.warning("[A2UI] No a2ui_data found in result")
                return

            # 提取元数据
            messages = a2ui_data.get("messages", [])
            metadata = a2ui_data.get("metadata", {})

            # 发送A2UI服务器事件
            a2ui_message = A2UIServerEventMessage(
                messages=messages,
                metadata={
                    "title": result.get("title") or metadata.get("title"),
                    "description": result.get("description") or metadata.get("description"),
                    "interactive": True,
                    "layout": metadata.get("layout", "vertical"),
                },
                session_id=session_id,
            )

            # 通过WebSocket发送（使用现有的事件机制）
            # 发送特殊的A2UI事件
            await emit_typed_event(
                TaskEventType.A2UI_SURFACE_EVENT,
                {
                    "a2ui_message": a2ui_message.to_dict(),
                    "surface_id": result.get("surface_id"),
                    "surface_type": result.get("surface_type", "custom"),
                    "task_id": task_id,
                },
                self._event_bus,
                task_id=task_id,
                source="tool_message_handler",
            )

            self.logger.info(
                f"[A2UI] Sent surface update: surface_id={result.get('surface_id')}, session_id={session_id}",
            )

        except Exception as e:
            self.logger.error(f"[A2UI] Error handling A2UI result: {e}", exc_info=True)
