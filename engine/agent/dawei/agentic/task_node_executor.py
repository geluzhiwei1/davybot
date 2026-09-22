# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""任务执行引擎
负责任务的执行、消息处理和工具调用
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Any

from dawei.core.datetime_compat import UTC

from dawei import get_dawei_home
from dawei.agentic.agent_config import Config
from dawei.agentic.checkpoint_manager import (
    CheckpointType,
    IntelligentCheckpointManager,
)
from dawei.core.errors import CheckpointError, LLMError
from dawei.core.events import TaskEventType, emit_typed_event
from dawei.core.exceptions import LLMContextOverflowError
from dawei.entity.lm_messages import (
    AssistantMessage,
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

# 使用内置的 asyncio.timeout (Python 3.12+)
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
        conversation=None,  # P2-7: 子任务独立会话（None = 共享 workspace.current_conversation）
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
            conversation: 子任务独立会话（可选，P2-7 flag on 时由引擎注入）

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

        # P2-7 会话隔离：executor 持有 conversation（非指针交换，并行子任务无竞态）
        self._conversation = conversation

        # P3-3 超时与预算：本 executor 生命周期内的用量计数与墙钟起点
        self._tokens_used: int = 0  # UsageMessage 实时累加（task_budget.extract_usage_total）
        self._loop_started_at: float | None = None  # 主循环墙钟起点（monotonic；None=未起跑）

        # 初始化其他属性
        self.logger = get_logger(__name__)
        self.execution_task: asyncio.Task | None = None
        self.last_checkpoint_time: float = 0.0
        self.last_cleanup_time: float = time.time()  # 添加清理时间戳

        # 用户停止事件：唤醒阻塞中的工具/追问等待（ask_followup_question 最长 5 分钟人机等待），
        # 否则 agent_stop 只能等工具超时后才真正生效（见 _execute_pending_tools 竞争逻辑）
        self._stop_event = asyncio.Event()

        # 初始化 IntelligentCheckpointManager（使用统一的 WorkspacePersistenceManager）
        self._checkpoint_manager = IntelligentCheckpointManager(
            workspace_path=self._user_workspace.absolute_path,
        )

        # 初始化工具消息处理器（透传隔离会话，P2-7）
        self._tool_message_handler = ToolMessageHandle(
            task_node=self.task_node,
            user_workspace=self._user_workspace,
            tool_call_service=self._tool_call_service,
            event_bus=self._event_bus,
            conversation=self._conversation,
        )

        # 【关键修复】消息ID追踪 - 为每个流式消息生成唯一ID
        self._current_message_id: str | None = None
        self._message_counter: int = 0

        # 截断重试计数:连续被 max_tokens 掐断(finish_reason=length)的轮数,超限 fast-fail
        self._consecutive_truncated_rounds: int = 0

    @property
    def active_conversation(self):
        """P2-7：隔离会话优先，未隔离（flag off / 根任务）回落 workspace 指针"""
        return self._conversation or self._user_workspace.current_conversation

    def request_stop(self) -> None:
        """请求停止当前任务节点执行（用户点击停止时由 TaskGraphExecutor.stop() 调用）。

        立即：
        1. 置停止事件 → _execute_pending_tools 中与工具执行竞争，即时中断
        2. 取消挂起的追问 Future → 唤醒 ask_followup_question 的人机等待
        """
        self._stop_event.set()
        futures = getattr(self._tool_message_handler, "_pending_followup_responses", None) or {}
        for _tool_call_id, future in list(futures.items()):
            if not future.done():
                future.cancel()

    @property
    def tokens_used(self) -> int:
        """P3-3：本任务累计消耗 token（UsageMessage 实时累加，token_budget 判定依据）"""
        return self._tokens_used

    def _record_usage(self, stream_message) -> None:
        """P3-3：累计 LLM 用量（UsageMessage.data 容错提取，失败不影响流处理）"""
        try:
            from dawei.agentic.task_budget import extract_usage_total

            self._tokens_used += extract_usage_total(getattr(stream_message, "data", None))
        except Exception:  # noqa: BLE001 — 计量失败绝不影响执行
            self.logger.exception("Failed to record token usage: ")

    def _check_budget_and_deadline(self) -> str | None:
        """P3-3：每轮主循环检查 token 预算与墙钟超时（受全局闸门控制）。

        全局闸门（2026-09-21）：AGENT_SUBTASK_TOKEN_BUDGET / AGENT_SUBTASK_TIMEOUT，
        -1 = 不限（默认：暂不限制预算；节点/LLM 声明的 timeout 如 1800s 对长任务
        太短，默认不启用 deadline 判定）。>0 时作为全局上限：节点声明值更小则取
        节点值，节点未声明则用全局值。

        Returns:
            超限时返回 task_completion 失败 JSON（build_budget_failure_result），
            由调用方注入会话并置 FAILED；未超限返回 None。
        """
        try:
            from dawei.agentic.task_budget import build_budget_failure_result, deadline_exceeded

            cfg_budget, cfg_timeout = -1, -1
            try:
                from dawei.config.settings import get_settings

                _ae = get_settings().agent_execution
                cfg_budget = int(getattr(_ae, "subtask_token_budget", -1))
                cfg_timeout = int(getattr(_ae, "subtask_timeout", -1))
            except Exception:  # noqa: BLE001 — 配置不可用时视为不限
                pass

            data = getattr(self.task_node, "data", None)

            # 有效预算 = 节点声明值为主；全局闸门 >0 时取 min(节点, 全局)、
            # 节点未声明时用全局值；全局 -1（默认）只关闭"全局兜底"，
            # 不吞掉节点自己的声明（首版实现 -1 时连节点值也跳过，
            # committed 测试 test_check_budget_and_deadline_branches 因此红）。
            budget = getattr(data, "token_budget", None)
            budget = float(budget) if isinstance(budget, (int, float)) and budget > 0 else None
            if cfg_budget > 0:
                budget = float(cfg_budget) if budget is None else min(budget, float(cfg_budget))
            if budget is not None and self._tokens_used >= budget:
                return build_budget_failure_result("token_budget", used=self._tokens_used, limit=int(budget))

            # 超时同语义：节点声明值为主，全局闸门 >0 时取 min
            timeout = getattr(data, "timeout_seconds", None)
            timeout = float(timeout) if isinstance(timeout, (int, float)) and timeout > 0 else None
            if cfg_timeout > 0:
                timeout = float(cfg_timeout) if timeout is None else min(timeout, float(cfg_timeout))
            if timeout is not None and deadline_exceeded(self._loop_started_at, timeout):
                used_s = int(time.monotonic() - self._loop_started_at) if self._loop_started_at is not None else 0
                return build_budget_failure_result("timeout", used=used_s, limit=int(timeout))
        except Exception:  # noqa: BLE001 — 检查失败不阻塞执行
            self.logger.exception("budget/deadline check failed: ")
        return None

    async def _fail_with_completion(self, failure_payload: str) -> None:
        """P3-3：超限失败 —— task_completion 失败 JSON 注入会话（父任务 summary 链路可见）+ 置 FAILED。

        FAST FAIL：不重试（重试只会再烧一遍预算/超时），原因即结果。
        失败原因同时写入 TaskNode.result（单一事实源），父任务从节点读。
        """
        import json as _json

        from dawei.entity.lm_messages import UserMessage

        conv = self.active_conversation
        if conv is not None:
            try:
                conv.say(UserMessage(content=failure_payload))
            except Exception:  # noqa: BLE001 — 注入失败不影响状态迁移
                self.logger.exception("Failed to inject budget-failure completion: ")

        # 【单一事实源】失败原因写入节点（从 payload 提取 result 字段，兼容非 JSON）
        _audit = ""
        try:
            try:
                parsed = _json.loads(failure_payload)
                reason = (parsed.get("result") if isinstance(parsed, dict) else None) or failure_payload
                # P2-C 预算审计:日志带上 used/limit(此前只有"超限"二字,排障无从对账)
                if isinstance(parsed, dict):
                    _audit = f" (kind={parsed.get('kind')}, used={parsed.get('used')}, limit={parsed.get('limit')})"
            except (ValueError, TypeError):
                reason = failure_payload
            task_graph = getattr(self._user_workspace, "task_graph", None)
            if task_graph is not None and hasattr(task_graph, "set_task_result"):
                await task_graph.set_task_result(self.task_node.task_node_id, reason)
        except Exception:  # noqa: BLE001 — 节点写失败不影响状态迁移
            self.logger.exception("Failed to record failure result on task node: ")

        self.task_node.update_status(TaskStatus.FAILED)
        self.logger.warning(f"Task {self.task_node.task_node_id} marked FAILED: budget/timeout exceeded{_audit}")

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

        # P1b ⑧ 记账：起跑时间写回 TaskData（首跳即定格；续跑/重试不重置）
        self._record_started_at()

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
            # P1b ⑧ 记账：终态时回写 tokens_used / completed_at（报告回显成本数据源）
            self._record_accounting_on_finish()
            # 清理
            self.execution_task = None

        return result

    def _record_started_at(self) -> None:
        """P1b ⑧：started_at 写回 TaskData（幂等：已有值不覆盖）"""
        try:
            data = getattr(self.task_node, "data", None)
            if data is not None and getattr(data, "started_at", None) is None:
                data.started_at = datetime.now(UTC)
        except Exception:  # noqa: BLE001 — 记账失败绝不影响执行
            self.logger.exception("Failed to record started_at: ")

    def _record_accounting_on_finish(self) -> None:
        """P1b ⑧：终态时回写 tokens_used / completed_at 到 TaskData

        非终态（编排续跑会再次调用 execute_task）不写 completed_at，
        避免中途 premature 时间戳覆盖最终完成时间。
        """
        try:
            data = getattr(self.task_node, "data", None)
            if data is None:
                return
            if self.task_node.status in (
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.ABORTED,
                TaskStatus.CANCELLED,
            ):
                data.tokens_used = self._tokens_used if self._tokens_used > 0 else None
                data.completed_at = datetime.now(UTC)
        except Exception:  # noqa: BLE001 — 记账失败绝不影响执行
            self.logger.exception("Failed to record accounting on finish: ")

    def reclaim_accounting_on_cancel(self, reason: str | None = None) -> bool:
        """P2-E 取消回收审计：取消路径强制回收已消耗 tokens

        引擎 cancel_task_execution 在拆除 executor 前调用。无论 CancelledError
        落点在 execute_task 内（finally 可跑但写在 finalize 持久化之后）还是外
        （重试退避/信号量等待/编排间隙——finally 根本不跑），已烧掉的 tokens
        都不允许静默丢失：
        - 节点已终态（调用方 finalize 先行）→ tokens_used/completed_at 补写
          TaskData（None 才写，不覆盖既有值），由调用方随补偿持久化事件落盘
        - 节点未终态（agent.abort_task 直连路径）→ 审计键 reclaimed_tokens/
          reclaimed_at 落 metadata，不碰状态字段

        Returns:
            是否写入了任何审计数据（调用方据此决定是否触发补偿持久化）
        """
        wrote = False
        try:
            data = getattr(self.task_node, "data", None)
            if data is None:
                return False
            meta = getattr(data, "metadata", None)
            if meta is not None:
                if self._tokens_used > 0:
                    meta.setdefault("reclaimed_tokens", self._tokens_used)
                    wrote = True
                meta.setdefault("reclaimed_at", datetime.now(UTC).isoformat())
                meta.setdefault("reclaimed_reason", reason or "")
                wrote = True
            if self.task_node.status in (
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.ABORTED,
                TaskStatus.CANCELLED,
            ):
                if self._tokens_used > 0 and data.tokens_used is None:
                    data.tokens_used = self._tokens_used
                    wrote = True
                if data.completed_at is None:
                    data.completed_at = datetime.now(UTC)
                    wrote = True
            return wrote
        except Exception:  # noqa: BLE001 — 回收失败绝不阻断取消主流程
            self.logger.exception("Failed to reclaim accounting on cancel: ")
            return wrote

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

    # 【P3 pause/resume 下架 2026-09-17】pause_task() 已移除（零调用者；
    # 若需中止执行请用 cancel_task_execution —— 检查点路径 _save_checkpoint
    # 由 CHECKPOINT_CREATED 事件继续覆盖，与 pause 语义无关）。

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
            self._record_usage(stream_message)  # P3-3: token 预算计量
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
        _no_tools: bool = False,
    ) -> Any | None:
        """处理消息，使用回调方式提高工具调用的实时性

        Args:
            message: 用户消息
            timeout: 总超时时间(秒),默认15分钟（向后兼容）
            llm_timeout: LLM调用超时(秒),None表示自动计算
            tool_execution_timeout: 工具执行超时(秒),None表示自动计算
            _no_tools: 如果为True，不向LLM传入任何工具（用于fallback强制纯文本回复）

        Returns:
            处理结果

        """
        # 🔧 FIX: 检查是否用户请求停止（在处理消息前）
        if self._agent and self._agent.is_stop_requested():
            self.logger.info(
                f"Task {self.task_node.task_node_id} stop requested, raising CancelledError to interrupt LLM",
            )
            raise asyncio.CancelledError("Stop requested by user")

        # 使用固定超时时间（默认值为原来的3倍）
        # 如果用户未指定，从 settings 读取 llm_call_timeout，默认 300s
        if llm_timeout is not None:
            final_llm_timeout = llm_timeout
        else:
            try:
                from dawei.config.settings import get_settings
                final_llm_timeout = get_settings().agent_timeout.llm_call_timeout
            except Exception:
                final_llm_timeout = 300.0  # 5分钟 fallback
        final_tool_timeout = tool_execution_timeout if tool_execution_timeout is not None else 900.0  # 15分钟

        # 流式空闲超时：LLM流在此时间内无任何数据则判定为卡死
        # 与总超时不同，只要流还在活跃发送数据就不会触发
        try:
            from dawei.config.settings import get_settings

            settings = get_settings()
            final_stream_idle_timeout = settings.agent_timeout.stream_idle_timeout
        except Exception:
            final_stream_idle_timeout = 120  # 默认120秒

        self.logger.info(
            f"Timeout configuration for task '{self.task_node.mode or 'unknown'}': "
            f"LLM={final_llm_timeout:.0f}s, StreamIdle={final_stream_idle_timeout:.0f}s, Tools={final_tool_timeout:.0f}s",
        )

        self._tool_message_handler._has_attempt_completion = False

        self._tool_message_handler._executed_tool_calls.clear()
        self.logger.info("Reset executed tool calls set for new task execution")

        # 🔧 FIX: 共享对话路径的子任务指令注入（P2-7 flag off 默认路径）。
        # 此前子任务与父任务共用 workspace.current_conversation 且从不注入指令 →
        # LLM 请求 = 父对话原样历史，两个后果：
        #   1) 子任务拿不到自己的任务描述（"subtask 复读父消息"事故根源）
        #   2) 历史以 assistant 结尾时 deepseek thinking 模式直接 400：
        #      "The `reasoning_content` in the thinking mode must be passed back to the API"
        # 对齐 create_subtask_conversation 的 §4.1 契约：父 → 子仅 message(+context)。
        if self._conversation is None and getattr(self.task_node, "parent_id", None):
            try:
                from dawei.agentic.subtask_conversation import _as_text
                from dawei.entity.lm_messages import UserMessage as _SubtaskUserMessage

                _conv = self.active_conversation
                _data = getattr(self.task_node, "data", None)
                _desc = _as_text(getattr(_data, "description", None))
                _marker = f"[subtask {self.task_node.task_node_id}]"
                _already = any(
                    _marker in str(getattr(_m, "content", "")) for _m in getattr(_conv, "messages", []) or []
                )
                if _conv is not None and _desc and not _already:
                    _meta = getattr(_data, "metadata", None) or {}
                    _parts = [f"{_marker} {_desc}"]
                    if _meta.get("context_note"):
                        _parts.append(f"\n[context] {_meta['context_note']}")
                    _conv.say(_SubtaskUserMessage(content="".join(_parts)))
                    self.logger.info(
                        f"Subtask instruction injected into shared conversation for {self.task_node.task_node_id}",
                    )
            except Exception:  # noqa: BLE001 — 注入失败不阻断执行（降级旧行为）
                self.logger.exception("Failed to inject subtask instruction into shared conversation: ")

        # 构建API请求（P2-7：隔离会话作为消息历史来源优先传入）
        api_request = await self._message_processor.build_messages(
            user_workspace=self._user_workspace,
            capabilities=self._get_capabilities(),
            conversation=self._conversation,
        )
        _n_msgs = len(api_request.get("messages", []))
        _n_tools = len(api_request.get("tools", []))
        self.logger.info(f"build_messages done: {_n_msgs} messages, {_n_tools} tools")
        if _n_tools == 0:
            # mode-工具解耦（方案 §4.1）：CORE_TOOLS 恒在使空列表结构性不可能；
            # tools=[] 意味着装配契约被破坏（fail-closed，立即失败而非裸吐 DSML）
            raise RuntimeError(
                "build_messages returned tools=[] — tool assembly contract broken "
                "(CORE_TOOLS must always be present; check tool_manager/session pool)"
            )

        if not self._llm_service.get_current_provider():
            # 使用 LLMProvider 获取模式特定的配置
            # P0-1: task mode 缺失时经 workspace.mode（ModeResolver 链）解析，
            # pdca 仅作最后防线（此前 `or "pdca"` 直接跳到最低优先级兜底）
            mode = self.task_node.mode or getattr(self._user_workspace, "mode", None) or "pdca"
            mode_config = self._user_workspace.llm_manager.get_mode_config(mode)
            if mode_config:
                self._llm_service.set_provider(mode_config.name)

        # P3-0b/F3: 按子任务模型路由 — TaskData.model/reasoning_effort 覆盖，
        # 请求结束后在下方 finally 中 clear_model_override() 还原（防污染共享 provider 状态）
        _model_override_applied = False
        if hasattr(self._llm_service, "set_model_override"):
            _task_model = getattr(self.task_node.data, "model", None)
            _task_effort = getattr(self.task_node.data, "reasoning_effort", None)
            if _task_model:
                _model_override_applied = self._llm_service.set_model_override(_task_model, _task_effort)

        # （P3-1 工具面 overlay 已随 mode-工具解耦 D7 退役：子任务 allow/deny
        #   仅由执行期守卫 tool_message_handler._check_task_tool_denied 强制）

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

        # 流活跃时间戳，用于空闲超时检测
        last_stream_activity = asyncio.get_event_loop().time()

        # 【B1 修复】待执行的工具完成消息。
        # 工具执行（含 ask_followup_question 的人机等待，最长 5 分钟）不再在流回调内同步执行，
        # 而是暂存到 pending_complete，待 LLM 流结束、空闲看门狗取消后再执行（见下方 _execute_pending_tools）。
        # 否则人机等待期间流无数据，会被 120s 空闲看门狗 cancel 掉 llm_task，
        # 进而误报为「LLM调用超时（300秒）」并触发任务级重试风暴。
        pending_complete: CompleteMessage | None = None

        async def stream_callback(stream_message: StreamMessages) -> None:
            """流式回调函数：转发流式事件；工具执行已延迟到流结束后（避免人机等待被看门狗误杀）"""
            nonlocal last_stream_activity, pending_complete
            last_stream_activity = asyncio.get_event_loop().time()

            # 🔧 FIX: 在每个流式消息处理时检查停止标志
            if self._agent and self._agent.is_stop_requested():
                self.logger.info(
                    f"Task {self.task_node.task_node_id} stop requested during streaming, raising CancelledError",
                )
                raise asyncio.CancelledError("Stop requested by user during streaming")

            await self.stream_message_to_event(stream_message)
            # 完成消息：只暂存，稍后在流结束、看门狗取消后统一执行工具
            if isinstance(stream_message, CompleteMessage):
                pending_complete = stream_message

        try:
            # 上下文溢出重试：最多重试1次，强制压缩后重试
            max_context_overflow_retries = 1
            for context_retry in range(max_context_overflow_retries + 1):
                try:
                    # 每轮重试前清空待执行工具，避免上一轮残留的 CompleteMessage 被误执行
                    pending_complete = None
                    # LLM调用：总超时 + 流空闲超时双重保护
                    # 总超时防止无限运行，流空闲超时检测流卡死
                    llm_task = asyncio.ensure_future(
                        self._llm_service.create_message_with_callback(
                            messages,
                            callback=stream_callback,
                            tools=[] if _no_tools else api_request.get("tools", []),
                        ),
                    )
                    try:
                        # 流空闲看门狗：监控流是否在发数据
                        idle_watchdog_cancelled = False
                        idle_error = None

                        async def _idle_watchdog() -> None:
                            nonlocal idle_error, idle_watchdog_cancelled
                            try:
                                while True:
                                    await asyncio.sleep(final_stream_idle_timeout)
                                    elapsed = asyncio.get_event_loop().time() - last_stream_activity
                                    if elapsed >= final_stream_idle_timeout:
                                        idle_error = TimeoutError(
                                            f"LLM stream idle for {elapsed:.0f}s (limit: {final_stream_idle_timeout}s)",
                                        )
                                        llm_task.cancel()  # noqa: B023
                                        return
                            except asyncio.CancelledError:
                                idle_watchdog_cancelled = True
                                raise

                        watchdog = asyncio.ensure_future(_idle_watchdog())
                        try:
                            await asyncio.wait_for(llm_task, timeout=final_llm_timeout)
                        except TimeoutError:
                            watchdog.cancel()
                            if idle_error:
                                # 流空闲超时触发
                                self.logger.warning(
                                    f"LLM stream idle timeout: {idle_error}",
                                )
                                raise TimeoutError(str(idle_error))
                            # 总超时触发
                            raise
                        except asyncio.CancelledError:
                            watchdog.cancel()
                            if idle_error:
                                raise TimeoutError(str(idle_error))
                            raise
                        finally:
                            if not watchdog.done():
                                watchdog.cancel()
                    finally:
                        if not llm_task.done():
                            llm_task.cancel()

                    # 【B1 修复】LLM 流已结束、空闲看门狗已取消，此处安全执行工具（含人机追问）。
                    # 此刻已脱离 120s 空闲看门狗与 300s LLM 总超时窗口，
                    # ask_followup_question 可安全等待用户回复（最长 5 分钟）。
                    # 工具/追问超时仅记日志、补一条 ToolMessage，不向上抛 TimeoutError，避免触发任务级重试。
                    if pending_complete is not None:
                        await self._execute_pending_tools(pending_complete, final_tool_timeout)
                        pending_complete = None

                    self.logger.info(
                        f"Message processed successfully (LLM: {final_llm_timeout}s, Tools: {final_tool_timeout}s)",
                    )
                    break  # 成功，退出重试循环

                except LLMContextOverflowError as e:
                    if context_retry >= max_context_overflow_retries:
                        # 已用完重试次数，报告错误
                        self.logger.error(
                            f"Context overflow persisted after compression retry, giving up: {e}",
                            exc_info=True,
                        )
                        await self._send_error_to_frontend(
                            error_message="对话上下文过长，即使压缩后仍超出模型限制。请开启新会话。",
                            error_type="context_overflow",
                            details={
                                "error": str(e)[:500],
                                "recoverable": False,
                                "suggestion": "请开启新会话",
                            },
                        )
                        raise

                    # 首次溢出：强制压缩对话并重试
                    self.logger.warning(
                        f"LLM context overflow detected (attempt {context_retry + 1}), "
                        f"forcing aggressive compression and retrying...",
                    )
                    try:
                        compressed = await self._force_compress_conversation()
                        if compressed:
                            # 用压缩后的消息重新构建请求
                            api_request = await self._message_processor.build_messages(
                                user_workspace=self._user_workspace,
                                capabilities=self._get_capabilities(),
                            )
                            raw_messages = api_request.get("messages", [])
                            converted_messages = []
                            for i, msg_dict in enumerate(raw_messages):
                                if msg_dict is None:
                                    continue
                                if isinstance(msg_dict, dict):
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
                                    converted_messages.append(msg_dict)
                            messages = converted_messages
                            self.logger.info(
                                f"Context compressed, retrying with {len(messages)} messages",
                            )
                        else:
                            self.logger.warning("Compression returned no changes, retrying anyway")
                    except Exception as compress_err:
                        self.logger.error(
                            f"Failed to compress conversation for overflow retry: {compress_err}",
                            exc_info=True,
                        )
                        raise

                except TimeoutError as e:
                    # 2026-09-14 (smoke #7 修复): 区分流空闲超时 vs LLM 总超时 ——
                    # 旧文案统一报 "LLM调用超时（300秒）", 但实际触发的是
                    # StreamIdle=120s 看门狗 (300s 是 LLM 总超时), 张冠李戴。
                    err_str = str(e)
                    is_stream_idle = "stream idle" in err_str.lower()
                    # 服务端自动重试余量: task_graph_excutor 会捕获这里抛出的
                    # TimeoutError 并指数退避重试 (smoke #7: attempt 1/3 失败
                    # → 2/3 成功完成, 但旧代码先把致命 error 发给了前端)
                    try:
                        can_retry = bool(self.task_node.data.can_retry())
                    except Exception:
                        can_retry = False

                    if is_stream_idle:
                        self.logger.warning(
                            f"LLM stream idle for {final_stream_idle_timeout:.0f}s "
                            f"(can_retry={can_retry}): {err_str}",
                        )
                    else:
                        self.logger.exception(f"LLM call timeout after {final_llm_timeout}s")

                    if can_retry:
                        # 瞬态超时 + 自动重试仍会进行 → 不发致命 error 给前端
                        # (前端收到 error 帧即终止会话, 而后台重试大概率成功);
                        # 重试耗尽时由 task_graph_excutor 统一发最终错误
                        raise

                    if is_stream_idle:
                        await self._send_error_to_frontend(
                            error_message=(
                                f"LLM流式响应空闲超时（{final_stream_idle_timeout:.0f}秒无输出，"
                                f"自动重试已用尽），请稍后重试或简化任务。"
                            ),
                            error_type="stream_idle_timeout",
                            details={
                                "stream_idle_timeout": final_stream_idle_timeout,
                                "recoverable": False,
                                "suggestion": "简化任务内容或稍后重试",
                                "original_error": err_str[:500],
                            },
                        )
                    else:
                        await self._send_error_to_frontend(
                            error_message=f"LLM调用总超时（{final_llm_timeout:.0f}秒，自动重试已用尽），请稍后重试或简化任务。",
                            error_type="timeout",
                            details={
                                "timeout": final_llm_timeout,
                                "recoverable": False,
                                "suggestion": "简化任务内容或稍后重试",
                            },
                        )
                    raise

                except LLMError as e:
                    # LLM API error - log with stack trace for debugging
                    error_str = str(e)
                    self.logger.error(f"LLM API error: {error_str}", exc_info=True)

                    # 🔧 FIX: 余额/配额类错误优先判定。zai 等供应商把「余额不足」(code 1113)
                    # 以 HTTP 429 下发,OpenAI 的 insufficient_quota 也是 429——这类错误重试
                    # 永远不会成功,必须 fast-fail,否则被下面 429 分支误判为限流让用户等 60s
                    # 死循环重试(2026-09-15 综述任务实证:429/1113 余额不足→"等待60秒重试")。
                    # 大小写不敏感（deepseek 网关 402 文案 "Insufficient credits" 首字母大写，
                    # 2026-09-16 00:01 实证：case-sensitive 匹配漏判为 llm_api_error）；
                    # HTTP 402 Payment Required 语义上即余额类，一并 fast-fail
                    _err_lower = error_str.lower()
                    balance_keywords = (
                        "余额不足",
                        "请充值",
                        "无可用资源包",
                        "http 402",
                        "insufficient balance",
                        "insufficient_balance",
                        "insufficient_quota",
                        "insufficient credits",
                    )
                    if any(kw in _err_lower for kw in balance_keywords):
                        self.logger.warning(f"Insufficient balance/quota detected: {e}")
                        await self._send_error_to_frontend(
                            error_message="API 账户余额不足，请联系管理员充值后重试。",
                            error_type="insufficient_balance",
                            details={
                                "error_code": "INSUFFICIENT_BALANCE",
                                "recoverable": False,
                                "suggestion": "联系管理员为所用模型/供应商充值",
                                "original_error": error_str[:500],
                            },
                        )
                    # 检测429 rate limit错误(真限流)
                    elif "429" in error_str or "rate_limit" in error_str.lower():
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
            # （P3-1 overlay 清除已随 D7 退役 — 不再设置即无须清除）
            # P3-0b: 还原子任务级模型覆盖（必须在 checkpoint 之前，保证下个任务路由正确）
            if _model_override_applied and hasattr(self._llm_service, "clear_model_override"):
                self._llm_service.clear_model_override()
            # P2-7: 隔离子会话按轮持久化（不切换 current_conversation 指针；
            # 失败只告警不中断 —— checkpoint 里已含消息快照兜底）
            if self._conversation is not None and hasattr(self._user_workspace, "save_subtask_conversation"):
                try:
                    await self._user_workspace.save_subtask_conversation(self._conversation)
                except Exception:  # noqa: BLE001
                    self.logger.exception("Failed to persist isolated subtask conversation: ")
            # 保存 checkpoint
            await self._save_checkpoint()

    async def _execute_pending_tools(
        self,
        complete_message: CompleteMessage,
        timeout: float,
    ) -> None:
        """在 LLM 流结束、空闲看门狗取消后执行工具调用（含人机追问）。

        将工具执行从流式回调中移出，使人机交互（ask_followup_question）不再处于
        120s 空闲看门狗 / 300s LLM 总超时窗口内——根治「LLM调用超时（300秒）」误报。
        追问等待默认不限时（AGENT_TIMEOUT_FOLLOWUP_QUESTION_TIMEOUT <= 0）时，
        本批工具执行同样豁免外层工具总超时，避免 900s 兜底把等人交互掐死。

        超时与参数解析错误只记日志、补一条 ToolMessage 供 LLM 下一轮重试，
        **不向上抛 TimeoutError**，避免触发 task_graph_excutor 的任务级重试风暴。
        用户主动停止产生的 CancelledError 正常向上抛，由任务循环处理。

        Args:
            complete_message: LLM 流的完成消息（含 tool_calls）
            timeout: 工具执行总超时（秒）；含不限时追问时置 0 = 不限时

        """
        # 人机追问不限时：本批含 ask_followup_question 且其超时配置 <= 0 时，
        # 豁免外层工具总超时（stop_wait 仍保证 agent_stop 即时中断）
        if any(
            getattr(tc.function, "name", "") == "ask_followup_question"
            for tc in getattr(complete_message, "tool_calls", []) or []
        ):
            try:
                from dawei.config.settings import get_settings

                _followup_timeout = get_settings().agent_timeout.followup_question_timeout
            except Exception:
                _followup_timeout = -1
            if not _followup_timeout or _followup_timeout <= 0:
                timeout = 0  # 不限时

        try:
            # 用户停止与工具执行竞争：停止时立即中断工具/追问等待，而不是等超时。
            # （agent_stop 设置的停止标志原本只在迭代间隙/流式 chunk 处检查，
            #   工具阶段（含 ask_followup_question 人机等待）完全不感知 → 停止"延迟到超时后"）
            stop_wait = asyncio.ensure_future(self._stop_event.wait())
            tool_task = asyncio.ensure_future(
                self._tool_message_handler.handle_stream_messages(complete_message),
            )
            try:
                if timeout and timeout > 0:
                    async with asyncio.timeout(timeout):
                        await asyncio.wait({tool_task, stop_wait}, return_when=asyncio.FIRST_COMPLETED)
                else:
                    await asyncio.wait({tool_task, stop_wait}, return_when=asyncio.FIRST_COMPLETED)

                if self._stop_event.is_set():
                    # 用户请求停止：取消工具执行，置 ABORTED 后正常返回，
                    # 由 _run_task_loop 顶部的状态检查统一收尾（与自然停止路径一致）
                    tool_task.cancel()
                    await asyncio.gather(tool_task, return_exceptions=True)
                    self.logger.info(
                        f"Task {self.task_node.task_node_id} stop requested during tool execution, aborted",
                    )
                    self.task_node.update_status(TaskStatus.ABORTED)
                    return

                # 正常完成：传播工具内部异常（保持原行为）
                tool_task.result()
            finally:
                stop_wait.cancel()
                if not tool_task.done():
                    tool_task.cancel()
        except TimeoutError:
            # 工具/追问执行超时：仅记日志，不中断流程，不触发任务级重试
            self.logger.exception(f"Tool execution timeout after {timeout}s")
        except (json.JSONDecodeError, RuntimeError, ValueError) as e:
            # 工具参数解析失败（通常因 SSE 流截断导致 JSON 不完整）
            self.logger.error(
                f"Tool execution failed (likely truncated stream): {type(e).__name__}: {e}",
            )
            # 将截断错误作为 tool result 返回给 LLM，使其能在下一轮自动重试
            truncated_tool_calls = getattr(complete_message, "tool_calls", [])
            for tc in truncated_tool_calls:
                self.active_conversation.say(
                    ToolMessage(
                        content=json.dumps(
                            {
                                "error": "Tool call was truncated due to output length limit. "
                                "Please split this operation into smaller calls "
                                "(e.g. use smart_text_edit instead of write_text_file for large files).",
                                "details": str(e)[:500],
                            },
                            ensure_ascii=False,
                        ),
                        tool_call_id=tc.tool_call_id,
                    ),
                )
        # 注：asyncio.CancelledError（用户停止）不被上面的 except 捕获，自然向上抛

    async def _save_checkpoint(self) -> None:
        """保存 checkpoint 到磁盘
        包含聊天消息历史、任务图状态和上下文信息
        """
        # 收集对话消息历史
        conversation_messages = []
        _conv = self.active_conversation
        if _conv:
            for msg in _conv.messages:
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
        # 从配置读取限制（可通过环境变量覆盖）
        from dawei.config.settings import get_settings

        _cfg = get_settings().agent_execution
        max_iterations = _cfg.task_max_iterations
        max_no_progress = _cfg.task_max_no_progress
        max_empty_tool_results = _cfg.task_max_empty_tool_results

        iteration = 0
        consecutive_no_progress = 0
        consecutive_empty_tools = 0  # 连续工具返回空结果计数
        prev_msg_count = -1
        self._loop_started_at = time.monotonic()  # P3-3: 墙钟超时判定起点

        while max_iterations < 0 or iteration < max_iterations:
            iteration += 1

            # 检查任务状态，如果已处终态则退出循环
            # （含 CANCELLED：用户终结节点后即使 engine cancel 错过不可中断点，
            #   循环轮询也能在下一轮退出，不再烧钱 —— P1a ⑥ 状态与执行同步收敛）
            status = self.task_node.status
            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ABORTED, TaskStatus.CANCELLED]:
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

            # P3-3: token 预算 / 墙钟超时检查（超限 → FAILED + 原因回传，fast-fail 不重试）
            _budget_failure = self._check_budget_and_deadline()
            if _budget_failure is not None:
                await self._fail_with_completion(_budget_failure)
                break

            await self.process_message()

            # 【防御性】检测连续无进展 — 如果 process_message 完成但消息数没有增加，
            # 说明 LLM 返回了空内容（静默失败）。
            current_msg_count = 0
            if self.active_conversation:
                current_msg_count = len(self.active_conversation.messages)
            if current_msg_count <= prev_msg_count:
                consecutive_no_progress += 1
                self.logger.warning(
                    f"No message progress (consecutive={consecutive_no_progress}/{max_no_progress}, "
                    f"msg_count={current_msg_count}, iteration={iteration})"
                )
                if consecutive_no_progress >= max_no_progress:
                    self.logger.error(
                        f"Aborting task loop: {consecutive_no_progress} consecutive iterations "
                        f"with no message progress (silent LLM failure)."
                    )
                    raise LLMError(
                        "openai",
                        "Task loop aborted: repeated empty LLM responses (silent provider failure).",
                    )
            else:
                consecutive_no_progress = 0
            prev_msg_count = current_msg_count

            # 【防御性】检测连续工具返回空结果 — Agent 反复搜索但每次都空手而归。
            # 这不是 LLM 静默失败（消息在增加），而是工具层面无数据，需单独计数。
            _this_round_empty = self._check_last_round_empty_tool_results()
            if _this_round_empty:
                consecutive_empty_tools += 1
                self.logger.warning(
                    f"Empty tool results detected (consecutive={consecutive_empty_tools}/{max_empty_tool_results}, "
                    f"iteration={iteration})"
                )
                if consecutive_empty_tools >= max_empty_tool_results:
                    self.logger.warning(
                        f"Task {self.task_node.task_node_id}: {consecutive_empty_tools} consecutive rounds "
                        f"with empty tool results — generating fallback reply instead of continuing."
                    )
                    await self._generate_max_iteration_fallback()
                    self.task_node.update_status(TaskStatus.COMPLETED)
                    break
            else:
                consecutive_empty_tools = 0

            if not await self._should_continue_execution():
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

        if max_iterations >= 0 and iteration >= max_iterations:
            self.logger.warning(f"Task {self.task_node.task_node_id} reached max iterations limit ({max_iterations})")
            # 兜底：让 LLM 基于已有信息生成最终回复，而非静默结束
            await self._generate_max_iteration_fallback()
            self.task_node.update_status(TaskStatus.COMPLETED)

    def _check_last_round_empty_tool_results(self) -> bool:
        """检查最近一轮工具调用是否全部返回空结果。

        判定条件：最近的消息中存在 tool 结果消息，且这些消息的内容全部包含
        "No ... found" / "0 results" / "empty" 等空结果标志。
        如果本轮没有任何工具调用（纯 assistant 消息），返回 False。
        """
        if not self.active_conversation:
            return False
        messages = self.active_conversation.messages
        if not messages:
            return False

        # 从末尾向前扫描，收集本轮的 tool result 消息
        # 遇到 assistant 消息（含 tool_calls）时停止
        tool_results: list[str] = []
        for msg in reversed(messages):
            role = str(getattr(msg, "role", ""))
            if role == str(MessageRole.ASSISTANT):
                # 如果这条 assistant 有 tool_calls，说明它发起工具调用 — 停止回溯
                if getattr(msg, "tool_calls", None):
                    break
                # 纯 assistant 消息（无工具调用）— 不是工具结果轮，返回 False
                return False
            if role == str(MessageRole.TOOL) or getattr(msg, "tool_call_id", None):
                content = str(getattr(msg, "content", ""))
                tool_results.append(content)

        if not tool_results:
            return False

        # 所有工具结果都为空才算"空结果轮"
        _EMPTY_MARKERS = (
            "no legal documents found",
            "no relevant information found",
            "0 documents",
            "no results",
            "not found",
            "no matching",
            "未找到",
            "暂无",
            "图谱中未找到",
            "无分面数据",
            "无分析数据",
            "无版本",
        )
        return all(any(m in r.lower() for m in _EMPTY_MARKERS) for r in tool_results)

    async def _generate_max_iteration_fallback(self) -> None:
        """达到迭代上限或连续空结果时，让 LLM 基于已有上下文生成最终回复。

        向对话追加一条 system 指令，要求 LLM 总结已知信息并告知用户限制，
        然后执行最后一轮 process_message（不带工具，强制纯文本回复）。
        """
        try:
            fallback_prompt = (
                "你已经达到了工具调用的最大次数限制。请根据到目前为止收集到的所有信息，"
                "向用户提供一个尽可能完整的回复。如果你已经找到了部分有用的信息，请整理并呈现。"
                "如果信息不足，请坦诚告知用户目前的发现，并建议他们可以尝试的替代方案（如换一种检索方式、"
                "提供更具体的关键词等）。不要再调用任何工具。"
            )
            if self.active_conversation:
                from dawei.entity.lm_messages import SystemMessage

                self.active_conversation.messages.append(
                    SystemMessage(content=fallback_prompt),
                )
            # _no_tools=True: 不传工具给LLM，强制纯文本输出，避免LLM继续调工具导致结果无法呈现
            await self.process_message(_no_tools=True)
        except Exception as e:
            self.logger.error(f"Fallback reply generation failed: {e}", exc_info=True)
            # 兜底兜底：如果LLM调用也失败了，至少发一条文本事件到前端
            try:
                fallback_text = (
                    "抱歉，任务在执行过程中达到了工具调用上限，"
                    "且生成总结回复时遇到了问题。请尝试简化任务或重新提问。"
                )
                await emit_typed_event(
                    TaskEventType.CONTENT_STREAM,
                    {
                        "content": fallback_text,
                        "message_id": f"fallback_{self.task_node.task_node_id}",
                    },
                    self._event_bus,
                    task_id=self.task_node.task_node_id,
                    source="fallback",
                )
            except Exception:
                pass  # 最后兜底也失败，只能记日志

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

        if self.active_conversation and self.active_conversation.messages:
            # 检查最近的消息
            recent_messages = self.active_conversation.messages[-1:]

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
                        # 【截断保护】finish_reason=length 且无工具调用 → 输出被 max_tokens
                        # 掐断(常见于推理型模型思考耗尽预算),不是自然完成:
                        # 重试让模型基于已截断消息继续;连续 3 次仍截断则 fast-fail。
                        if getattr(self._tool_message_handler, "last_round_truncated", False):
                            self._consecutive_truncated_rounds += 1
                            if self._consecutive_truncated_rounds >= 3:
                                raise LLMError(
                                    "openai",
                                    "LLM output truncated by max_tokens (finish_reason=length) for 3 consecutive rounds; "
                                    "aborting task instead of silently marking it COMPLETED.",
                                )
                            self.logger.warning(
                                f"Task {self.task_node.task_node_id}: LLM output truncated by max_tokens "
                                f"(round {self._consecutive_truncated_rounds}/3), retrying to let the model continue",
                            )
                            return True
                        self._consecutive_truncated_rounds = 0
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
        # P0-1: 父任务 mode 缺失时经 workspace.mode（ModeResolver 链）解析，pdca 仅最后防线
        parent_mode = self.task_node.mode or getattr(self._user_workspace, "mode", None) or "pdca"
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

    # 【P3 pause/resume 下架 2026-09-17】pause_task_execution/resume_task_execution
    # 死 stub 已移除：前者只 log+return False（TODO 从未落地），后者签名与
    # 调用方不兼容且会置 RESUMABLE 后盲目重跑（返回 None 违反 -> bool 契约）。
    # websocket 协议无 TaskNodePause/Resume 消息，无任何可达调用路径。
    # 重新引入必须先落协议消息 + 引擎真实现（docs/子任务组织管理交互方案.md §P3）。

    async def get_current_mode(self) -> str:
        """获取当前模式

        Returns:
            当前模式

        """
        # P0-1: task mode 缺失时经 workspace.mode（ModeResolver 链）解析，pdca 仅最后防线
        return self.task_node.mode or getattr(self._user_workspace, "mode", None) or "pdca"

    async def handle_followup_response(self, tool_call_id: str, response: str) -> bool:
        """处理前端发来的追问回复

        Args:
            tool_call_id: 工具调用ID
            response: 用户回复

        Returns:
            是否成功处理

        """
        return await self._tool_message_handler.handle_followup_response(tool_call_id, response)

    async def handle_followup_cancel(self, tool_call_id: str, reason: str) -> bool:
        """处理前端发来的追问取消

        Args:
            tool_call_id: 工具调用ID
            reason: 取消原因

        Returns:
            是否成功处理

        """
        return await self._tool_message_handler.handle_followup_cancel(tool_call_id, reason)

    async def _force_compress_conversation(self) -> bool:
        """强制压缩当前对话以应对上下文溢出。

        直接裁剪 current_conversation.messages，仅保留最近的消息和关键消息，
        确保下次 build_messages() 构建出更短的上下文。

        Returns:
            True 如果成功压缩了消息（有消息被移除），False 如果没有变化
        """
        from dawei.agentic.conversation_compressor import ConversationCompressor

        conversation = self.active_conversation
        if not conversation or not conversation.messages:
            self.logger.warning("No conversation to compress")
            return False

        messages = conversation.messages
        if len(messages) <= 5:
            self.logger.warning(f"Conversation too short ({len(messages)} msgs) to compress further")
            return False

        # 将消息转为 dict 用于压缩器分析
        msg_dicts = []
        for msg in messages:
            if hasattr(msg, "to_dict"):
                msg_dicts.append(msg.to_dict())
            elif isinstance(msg, dict):
                msg_dicts.append(msg)
            else:
                msg_dicts.append({"role": getattr(msg, "role", "unknown"), "content": str(getattr(msg, "content", ""))})

        # 使用压缩器识别关键消息
        compressor = ConversationCompressor(preserve_recent=10)
        key_indices, metadata_list = compressor.identify_key_messages(msg_dicts)

        # 激进策略：只保留最近10条 + 关键消息
        preserve_count = 10
        kept_indices = set()

        # 保留最近的消息
        for idx in range(max(0, len(messages) - preserve_count), len(messages)):
            kept_indices.add(idx)

        # 保留关键消息（仅保留最近的 preserve_count 范围之外的）
        for idx in sorted(key_indices):
            if idx not in kept_indices:
                kept_indices.add(idx)

        original_count = len(messages)

        if len(kept_indices) >= original_count:
            self.logger.warning("Compression would keep all messages, skipping")
            return False

        # 生成被裁剪消息的简要摘要
        removed_messages = [msg_dicts[i] for i in range(original_count) if i not in kept_indices]
        summary_parts = []
        for m in removed_messages:
            role = m.get("role", "?")
            content = str(m.get("content", ""))
            if content:
                summary_parts.append(f"[{role}] {content[:200]}")
        summary_text = "\n".join(summary_parts[-20:])  # 最多保留20条摘要

        # 裁剪对话消息
        new_messages = [messages[i] for i in sorted(kept_indices)]
        conversation.messages = new_messages

        # 注入压缩摘要作为系统消息，让 LLM 知道历史被压缩了
        from dawei.entity.lm_messages import SystemMessage

        summary_msg = SystemMessage(
            content=(
                f"[Context Overflow Recovery] "
                f"Conversation was compressed from {original_count} to {len(new_messages)} messages "
                f"due to context window limit. Summary of removed messages:\n{summary_text}"
            ),
        )
        conversation.messages.insert(0, summary_msg)

        self.logger.info(
            f"Forced conversation compression: {original_count} -> {len(new_messages) + 1} messages",
        )
        return True

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
