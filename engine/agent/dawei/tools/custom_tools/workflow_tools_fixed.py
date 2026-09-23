# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

import json
import re
import time
import unicodedata
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from dawei.logg.logging import get_logger
from dawei.tools.custom_base_tool import CustomBaseTool
from dawei.tools.custom_tools.async_utils import run_async

# 派发目标归一化键前缀长度（P1-3 重复派发熔断）：等价重派的 prompt 头部
# （目标描述）几乎总一致，prefix 截断使"同一目标"判定对尾部追加细节不敏感。
_DESC_PREFIX_LEN = 120


def _normalize_desc_key(message: str | None, prefix_len: int = _DESC_PREFIX_LEN) -> str:
    """去掉空白与全部 Unicode 标点后取前缀，作为"同目标"判定键。

    （mode-工具解耦 D6：原实现位于 tools/tool_group_hints.py，随该模块删除内联至此）
    （2026-09-20 TUI conv 9f2d4586 实证：等价重派仅差 1 个标点——"任务——" vs
     "任务："——即绕过旧的前缀熔断，Stage 0 重跑白烧 682k tokens。改为按
     Unicode 类别 P* 剥离所有标点（含全角/中文标点），markdown 强调符
     `*_>#-[]()` 亦属标点，行为兼容且更严。）
    """
    if not message:
        return ""
    stripped = "".join(ch for ch in str(message) if not ch.isspace() and not unicodedata.category(ch).startswith("P"))
    return stripped[:prefix_len]


# 派发身份归一窗口（C8）：比旧前缀熔断的 120 字更宽 —— 等价重派判定从
# "目标描述头部" 升级为 "mode+交付物+全量归一化指令"，误伤面更小。
_DISPATCH_IDENTITY_MSG_WINDOW = 400


def _dispatch_identity(
    mode: str,
    deliverable: str | None,
    item_identity: str | None = None,
    message: str | None = None,
) -> str:
    """派发身份（C8）：hash(mode + deliverable + item.identity)。

    - batch 项：显式 item.identity 充任身份分量（同 identity 重派熔断，
      不同 identity 互不误伤 —— N 项模板展开天然各自身份不同）
    - 单个 new_task：无 item.identity → 以归一化 message（400 字窗口）充任
    - 保留 1.79M tokens 事故防线：等价重派（同 mode/交付物/指令）身份相同
    """
    import hashlib

    ident = (item_identity or "").strip() or _normalize_desc_key(message, prefix_len=_DISPATCH_IDENTITY_MSG_WINDOW)
    key = f"{mode}\x1f{(deliverable or '').strip()}\x1f{ident}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _import_task_graph_components():
    """延迟导入 task_graph 组件以避免循环依赖"""
    from dawei.task_graph import (
        ContextStore,
        StateManager,
        TaskContext,
        TaskData,
        TaskGraph,
        TaskNode,
        TaskPriority,
        TaskStatus,
        TodoItem,
        TodoManager,
        TodoStatus,
    )

    return {
        "TodoItem": TodoItem,
        "TodoStatus": TodoStatus,
        "TaskStatus": TaskStatus,
        "TaskData": TaskData,
        "TaskContext": TaskContext,
        "TaskPriority": TaskPriority,
        "TaskGraph": TaskGraph,
        "TaskNode": TaskNode,
        "TodoManager": TodoManager,
        "StateManager": StateManager,
        "ContextStore": ContextStore,
    }


# Ask Follow-up Question Tool
class AskFollowupQuestionInput(BaseModel):
    """Input for AskFollowupQuestionTool."""

    question: str = Field(
        ...,
        description="Clear, specific question addressing information needed from the user.",
    )
    follow_up: list[str] = Field(
        ...,
        description="List of 2-4 suggested answers as plain strings. Each string is one suggested response the user can select.",
    )


class AskFollowupQuestionTool(CustomBaseTool):
    """Tool for asking follow-up questions to gather additional information."""

    name: ClassVar[str] = "ask_followup_question"
    description: ClassVar[str] = "Gets additional information from user with suggested answers."
    args_schema: ClassVar[type[BaseModel]] = AskFollowupQuestionInput

    def __init__(self, task_graph=None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)

    def _run(self, question: str, follow_up: list[str]) -> str:
        """Ask follow-up question with enhanced error handling."""
        try:
            # Validate follow-up suggestions
            if len(follow_up) < 2 or len(follow_up) > 4:
                return json.dumps(
                    {
                        "status": "error",
                        "message": "Follow-up suggestions must be between 2 and 4 items",
                    },
                    indent=2,
                )

            # Format question and suggestions
            formatted_suggestions = []
            for i, suggestion in enumerate(follow_up, 1):
                formatted_suggestions.append(f"{i}. {suggestion}")

            result = {
                "type": "followup_question",
                "question": question,
                "suggestions": follow_up,
                "formatted_output": f"\n❓ {question}\n\n" + "\n".join(formatted_suggestions),
                "status": "pending_response",
                # 【2026-09-12】worker 线程无事件循环，get_event_loop().time() 必崩 → time.time()
                "timestamp": time.time(),
            }

            # Log question for tracking
            self.logger.info(f"Follow-up question asked: {question[:50]}...")

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.exception("Error asking follow-up question: ")
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Error asking follow-up question: {e!s}",
                },
                indent=2,
            )


# Attempt Completion Tool
class AttemptCompletionInput(BaseModel):
    """Input for AttemptCompletionTool."""

    result: str = Field(..., description="Final result of task to present to user.")


class AttemptCompletionTool(CustomBaseTool):
    """Tool for presenting final results of a completed task."""

    name: ClassVar[str] = "attempt_completion"
    description: ClassVar[str] = "Signals that the current task is complete and presents final results to the user. The task status will be marked as completed. Use this when all work is done and no further tool calls are needed."
    args_schema: ClassVar[type[BaseModel]] = AttemptCompletionInput

    def __init__(self, task_graph=None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)

    async def _run(self, result: str) -> str:
        """Present completion result with enhanced task management.

        若存在未完成的子任务（PENDING/RUNNING/WAITING_FOR_TOOL），拒绝完成并
        提示 LLM 先等待/查询子任务，避免委派的子任务被提前终结。
        """
        try:
            # 【2026-09-12 执行期解析】构造期 task_graph=None 冻结，经 user_workspace 解析活实例
            task_graph = self._resolve_task_graph()

            # 检查是否存在未完成的子任务
            if task_graph:
                root_task = await task_graph.get_root_task()
                if root_task:
                    subtasks = await task_graph.get_subtasks(root_task.task_id)
                    unfinished = [st for st in subtasks if st.status.value in ("pending", "running", "waiting_for_tool", "paused")]
                    if unfinished:
                        pending_ids = [st.task_id for st in unfinished]
                        self.logger.info(
                            f"AttemptCompletion blocked: {len(unfinished)} unfinished subtasks: {pending_ids}",
                        )
                        return json.dumps(
                            {
                                "type": "task_completion",
                                "status": "blocked",
                                "message": f"Cannot complete task: {len(unfinished)} subtask(s) not finished.",
                                "unfinished_subtasks": [{"subtask_id": st.task_id, "status": st.status.value, "description": (st.data.description or "")[:200]} for st in unfinished],
                                "hint": "Wait for subtasks to finish (use get_task_status to poll), then attempt_completion again.",
                            },
                            indent=2,
                        )

            completion_result = {
                "type": "task_completion",
                "status": "completed",
                "result": result,
                # 【2026-09-12】worker 线程无事件循环 → time.time()
                "timestamp": time.time(),
                "message": "Task completed successfully",
            }

            # 如果有 task_graph，同步更新任务状态（新架构下 root 已在执行器流程中收尾，
            # 这里仅作幂等标记，失败不影响返回）
            if task_graph:
                try:
                    await self._complete_task(result)
                except Exception:  # noqa: BLE001 — 状态更新失败不应吞掉完成结果
                    self.logger.exception("Failed to update task status on completion: ")

            self.logger.info("Task completion attempted via AttemptCompletionTool")

            return json.dumps(completion_result, indent=2)

        except Exception as e:
            self.logger.exception("Error completing task: ")
            return json.dumps(
                {"status": "error", "message": f"Error completing task: {e!s}"},
                indent=2,
            )

    async def _complete_task(self, _result: str):
        """异步完成任务（新架构）"""
        # 获取组件
        components = _import_task_graph_components()
        TaskStatus = components["TaskStatus"]

        task_graph = self._resolve_task_graph()
        if not task_graph:
            return

        # 获取根任务
        root_task = await task_graph.get_root_task()
        if root_task:
            # 【单一事实源】result 写入节点（与 tool_message_handler 拦截路径同契约）
            try:
                if hasattr(task_graph, "set_task_result"):
                    await task_graph.set_task_result(root_task.task_id, _result)
            except Exception:  # noqa: BLE001 — 节点写失败不影响状态收尾
                self.logger.exception("Failed to record result on task node via AttemptCompletionTool: ")
            await task_graph.update_task_status(root_task.task_id, TaskStatus.COMPLETED)
            self.logger.info(f"Task completed via AttemptCompletionTool: {root_task.task_id}")


# P1-1 动态模式 schema：LLM 在派发/切换时即见当前 registry 的合法模式清单
# （slug + 一句话用途 + 工具组），不再盲猜（E2E 2026-09-18：orchestrator 6×
# 重复派发到无 research 组的模式）。刻意用「描述注入」而非硬 enum：schema 在
# ToolProvider 装载期固化，硬 enum 会在运行期装新模式/别名派发时误拒；描述
# 陈旧仅是提示降级，存在性校验仍在 _run 侧 FAST FAIL 并返回实时清单。
def _build_mode_hint_lines(
    workspace_root: str | None,
    *,
    delegable_only: bool = False,
    max_lines: int = 30,
) -> list[str]:
    """当前 registry 的模式清单行（schema 描述注入用；异常/空 → []）"""
    try:
        from dawei.mode.registry import get_registry

        registry = get_registry(workspace_root)
        modes = [m for m in registry.all() if not (delegable_only and not m.can_delegate)]
        lines: list[str] = []
        for mode in modes[:max_lines]:
            desc = (mode.description or mode.when_to_use or mode.name or "").strip()
            first_line = desc.splitlines()[0][:80] if desc else mode.name
            # mode-工具解耦（D3）：mode 无工具组语义，hint 仅展示人设描述
            lines.append(f"{mode.slug}: {first_line}")
        if len(modes) > max_lines:
            lines.append(f"... (+{len(modes) - max_lines} more modes)")
        return lines
    except Exception:  # noqa: BLE001 — registry 不可用回落静态描述
        get_logger(__name__).debug("mode hint lines unavailable, falling back to static schema", exc_info=True)
        return []


def _dynamic_mode_args_schema(
    base: type[BaseModel],
    field_name: str,
    prefix: str,
    workspace_root: str | None,
    *,
    delegable_only: bool = False,
) -> type[BaseModel]:
    """生成 field_name 描述注入实时模式清单的 schema 子类；失败原样返回 base。"""
    try:
        lines = _build_mode_hint_lines(workspace_root, delegable_only=delegable_only)
        if not lines:
            return base
        from pydantic import create_model

        hint = f"{prefix} Valid modes: {'; '.join(lines)}."
        return create_model(
            f"{base.__name__}Dynamic",
            __base__=base,
            **{field_name: (str, Field(..., description=hint))},
        )
    except Exception:  # noqa: BLE001 — 生成失败回落静态 schema
        get_logger(__name__).debug("dynamic mode schema generation failed, using static", exc_info=True)
        return base


# Switch Mode Tool
class SwitchModeInput(BaseModel):
    """Input for SwitchModeTool."""

    mode_slug: str = Field(
        ...,
        description=("Slug of mode to switch to (the live list of workspace modes is injected into this description at load time; unknown slugs return available_modes)."),
    )
    reason: str | None = Field(None, description="Reason for switching modes.")


class SwitchModeTool(CustomBaseTool):
    """Tool for switching to different modes for specialized tasks."""

    name: ClassVar[str] = "switch_mode"
    # P1-1: 修正过时描述（旧文案提 "PDCA mode" 与 plan/do/check/act —— 这些
    # 不是 registry 中的 mode slug，误导 LLM 枚举不存在的模式）
    description: ClassVar[str] = "Switches to a different mode for the current session. Modes are dynamically loaded from the workspace mode registry (built-in: orchestrator, pdca; plus workspace custom modes). If the specified mode is not found, returns the list of available modes."
    args_schema: ClassVar[type[BaseModel]] = SwitchModeInput

    def __init__(self, task_graph=None, workspace_root: str | None = None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)
        self.workspace_root = workspace_root
        # Lazy load available modes
        self._available_modes: dict[str, dict[str, Any]] | None = None
        self._modes_registry = None  # 生成缓存时的 Registry 实例（invalidate 后自动重建）
        # P1-1: mode_slug 字段描述注入全量模式实时清单（切换目标对 LLM 可见）
        self.args_schema = _dynamic_mode_args_schema(SwitchModeInput, "mode_slug", "Slug of mode to switch to.", self.workspace_root)

    def _load_available_modes(self) -> dict[str, dict[str, Any]]:
        """动态加载可用模式（P6：经 ModeRegistry 单例，不再 ad-hoc ModeManager）"""
        try:
            from dawei.mode.registry import get_registry

            registry = get_registry(self.workspace_root)
            # Phase 4c：invalidate_registry 会替换单例对象 —— 同一性校验消除
            # 装后陈旧窗口（mode统一管理.md §7 验收 #7），实例缓存随新 Registry 重建
            if self._available_modes is not None and self._modes_registry is registry:
                return self._available_modes

            # 转换为工具所需的格式
            # （mode-工具解耦 D2/D3：groups/aliases 已退役，capabilities 恒 general）
            available_modes = {}
            for mode in registry.all():
                available_modes[mode.slug] = {
                    "name": mode.name,
                    "description": mode.description or mode.when_to_use,
                    "capabilities": ["general"],
                    "role_definition": mode.role_definition,
                    "custom_instructions": mode.custom_instructions,
                    "source": mode.source,
                    # v2 元数据（kind/priority/can_delegate 供路由建议与 new_task 校验）
                    "kind": mode.kind,
                    "priority": mode.priority,
                    "can_delegate": mode.can_delegate,
                }

            self._available_modes = available_modes
            self._modes_registry = registry
            self.logger.info(f"Loaded {len(available_modes)} modes from ModeRegistry")
            return available_modes

        except Exception as e:
            self.logger.error(f"Failed to load modes from ModeRegistry: {e}", exc_info=True)
            # 返回空字典而不是硬编码的默认值
            return {}

    def _run(self, mode_slug: str, reason: str | None = None) -> str:
        """Switch to specified mode with enhanced task management."""
        try:
            # 动态加载可用模式
            available_modes = self._load_available_modes()

            # Check if mode exists（mode-工具解耦 D2：别名归一已删除，
            # 幽灵/旧 slug 一律 not found + available 反馈）
            if mode_slug not in available_modes:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Mode '{mode_slug}' not found",
                        "available_modes": list(available_modes.keys()),
                    },
                    indent=2,
                )

            mode_info = available_modes[mode_slug]

            # 【关键修复 2026-09-11】旧实现两个致命缺陷：
            # 1) asyncio.get_event_loop()/asyncio.create_task() 在 tool_executor 的
            #    to_thread worker 线程里没有事件循环，直接抛
            #    "There is no current event loop in thread 'ThreadPoolExecutor-N'"，
            #    switch_mode 从未成功过 → 模式锁死，command 等工具组永远不可注入。
            # 2) 即使不崩溃也只 mock 返回 "switched"，从未写入真正驱动工具注入的
            #    user_workspace.workspace_info.user_ui_context.current_mode
            #    （llm_message_builder 每轮读取该状态计算 tools=）。
            # 修复：同步写入真实模式状态（mode property setter），异步善后经主 loop 调度。
            from_mode = None
            state_applied = False
            if self.user_workspace is not None:
                try:
                    from_mode = getattr(self.user_workspace, "mode", None)
                    # mode setter → workspace_info.user_ui_context.current_mode，
                    # 下一轮 LLM 请求的工具集/系统提示立即按新模式构建
                    self.user_workspace.mode = mode_slug
                    state_applied = True
                    # 【2026-09-14 串台修复】切换模式即作废旧模式的 Plan 工作流状态:
                    # llm_message_builder 每轮检查 user_workspace._plan_workflow,
                    # 不清掉的话 plan 阶段的任务清单会持续注入到其它业务模式的提示词
                    if getattr(self.user_workspace, "_plan_workflow", None) is not None:
                        self.user_workspace._plan_workflow = None
                        self.logger.info("switch_mode: cleared stale plan_workflow state")
                    self._schedule_on_main_loop(self._persist_mode(mode_slug))
                except Exception:
                    self.logger.exception("switch_mode: failed to update user_workspace.mode")
            else:
                self.logger.error(
                    "switch_mode: user_workspace not injected — mode state NOT updated",
                )

            # 如果有 task_graph，更新任务元数据（fire-and-forget，经主 loop 调度）
            # 【2026-09-12 执行期解析】_schedule_on_main_loop 已提升至 CustomBaseTool
            if self._resolve_task_graph():
                self._schedule_on_main_loop(self._switch_mode(mode_slug, reason))

            self.logger.info(
                f"Mode switch applied: {from_mode!r} -> {mode_slug!r} (state_applied={state_applied})",
            )

            result = {
                "type": "mode_switch",
                "from_mode": from_mode,
                "to_mode": mode_slug,
                "mode_name": mode_info["name"],
                "mode_description": mode_info["description"],
                "capabilities": mode_info["capabilities"],
                "role_definition": mode_info.get("role_definition", ""),
                "custom_instructions": mode_info.get("custom_instructions", ""),
                "source": mode_info.get("source", "unknown"),
                "reason": reason or "Mode switch requested",
                "status": "switched" if state_applied else "error",
                "mode_state_applied": state_applied,
                "note": ("Mode switched; the new toolset takes effect on the next LLM turn." if state_applied else "user_workspace unavailable: mode NOT switched. Ask the user to switch mode in the UI."),
                "timestamp": time.time(),
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.exception("Error switching mode: ")
            return json.dumps(
                {"status": "error", "message": f"Error switching mode: {e!s}"},
                indent=2,
            )

    # 【2026-09-12】_schedule_on_main_loop 已提升至 CustomBaseTool 基类
    # （UpdateTodoList 等其他同步工具同样需要 worker 线程安全的协程调度）。

    async def _persist_mode(self, mode_slug: str) -> None:
        """持久化 UI 上下文中的模式（失败仅记日志，不影响内存态切换）。"""
        try:
            if self.user_workspace is not None and hasattr(self.user_workspace, "update_ui_context"):
                await self.user_workspace.update_ui_context(current_mode=mode_slug)
        except Exception:
            self.logger.exception("switch_mode: failed to persist ui context")

    async def _switch_mode(self, mode_slug: str, reason: str | None = None):
        """异步切换模式（新架构）"""
        try:
            # 获取组件
            components = _import_task_graph_components()
            TaskContext = components["TaskContext"]

            task_graph = self._resolve_task_graph()
            if not task_graph:
                return

            # 获取根任务
            root_task = await task_graph.get_root_task()
            if root_task:
                # 更新任务上下文中的模式
                current_context = root_task.data.context
                updated_context = TaskContext(
                    user_id=current_context.user_id,
                    session_id=current_context.session_id,
                    message_id=current_context.message_id,
                    workspace_path=current_context.workspace_path,
                    parent_context=current_context.parent_context,
                    metadata=current_context.metadata,
                    task_files=current_context.task_files,
                    task_images=current_context.task_images,
                )

                # 更新模式信息到元数据
                updated_context.metadata["current_mode"] = mode_slug
                updated_context.metadata["mode_switch_reason"] = reason or "Mode switch requested"

                await task_graph.update_task_context(root_task.task_id, updated_context)
                self.logger.info(f"Mode switched to {mode_slug} for task {root_task.task_id}")
        except (AttributeError, ValueError, KeyError) as e:
            self.logger.error(f"Failed to switch mode: {e}", exc_info=True)
            raise  # Fast Fail: surface the error to caller


# New Task Tool
class NewTaskInput(BaseModel):
    """Input for NewTaskTool."""

    mode: str = Field(
        ...,
        description=("Slug of mode to start new task in (the live list of delegable modes with their tool groups is injected into this description at load time)."),
    )
    message: str = Field(
        ...,
        max_length=800,  # C2/R1: 单一交付物指令硬顶（巨子任务 schema 层拒死）
        description=("Initial instructions for the subtask. Must target ONE deliverable and be self-contained (goal, scope, key constraints) — but must NOT bundle N similar work items (e.g. 'review these 6 files') into one subtask; dispatch those as one subtask per item instead."),
    )
    acceptance: str = Field(
        ...,
        description=(
            "REQUIRED verifiable acceptance criteria for the subtask (验收标准). Must be decidable from the subtask's result alone, e.g. 'report contains all 7 sections', 'tests pass with 0 failures'. Echoed back in the subtask execution report so the parent can judge completed vs completed-but-not-accepted."
        ),
    )
    deliverable: str = Field(
        ...,
        max_length=200,
        description=("REQUIRED: the single deliverable of this subtask in one short sentence, e.g. '交付/审查报告/新加坡_劳动合同.md'. One subtask = one deliverable (one file / one jurisdiction / one decidable question). If the request names N similar deliverables, split into N subtasks instead."),
    )
    output_file: str | None = Field(
        None,
        max_length=500,
        description=("REQUIRED for report/review-type deliverables: workspace file path the subtask must WRITE the full deliverable to (e.g. '交付/审查报告/新加坡.md'). The subtask's chat reply then contains only a ≤500-char summary + this path — single-turn long generation gets killed by stream timeouts."),
    )
    agent: str = Field(
        "default",
        description="Agent profile name (default/worker/explorer or workspace .dawei/agents/*)",
    )
    context: str | None = Field(
        None,
        description="Optional extra context for the subtask (appended to metadata.context_note)",
    )
    timeout: float | None = Field(
        None,
        description="Optional wall-clock timeout in seconds for the subtask (P3-3). Exceeding it fails the subtask fast with the reason returned to the parent. None/0 = no limit.",
    )
    token_budget: int | None = Field(
        None,
        description="Optional token budget for the subtask (P3-3). Exceeding it fails the subtask fast with the reason returned to the parent. None/0 = no limit.",
    )
    tools: list[str] | None = Field(
        None,
        description=(
            "Optional minimal tool allowlist for the subtask (P2 工具集最小化). "
            "Give only the tools the subtask needs to satisfy acceptance "
            "(e.g. ['read_file','list_files'] for read-only research). Enforced both "
            "at prompt level (schema filtering) and at execution level (denied "
            "calls return a visible error). Overrides the agent profile's allow/deny."
        ),
    )


class NewTaskTool(CustomBaseTool):
    """Tool for creating new subtasks in different modes."""

    name: ClassVar[str] = "new_task"
    description: ClassVar[str] = (
        "Creates a new subtask and returns immediately (dispatch-and-return): the subtask is "
        "registered as PENDING and executed by the orchestration loop after the current task's "
        "executor finishes. One subtask = ONE deliverable (deliverable arg required): a single "
        "file / jurisdiction / decidable question — never bundle N similar work items into one "
        "subtask; dispatch one new_task per item instead. REQUIRED acceptance — verifiable "
        "criteria decidable from the subtask result alone. Report/review-type deliverables "
        "REQUIRE output_file: the full report is written to the file and the chat reply carries "
        "only a ≤500-char summary + path. A [Subtask Execution Report] with acceptance/cost per "
        "subtask is injected back into the conversation for you to judge completed vs not-accepted."
    )
    args_schema: ClassVar[type[BaseModel]] = NewTaskInput

    def __init__(self, task_graph=None, workspace_root: str | None = None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)
        self.workspace_root = workspace_root
        # Lazy load available modes
        self._available_modes: dict[str, str] | None = None
        self._modes_registry = None  # 生成缓存时的 Registry 实例（invalidate 后自动重建）
        # P1-1: mode 字段描述注入可委派模式实时清单（含各模式工具组）——
        # 父 LLM 派发时即见合法目标，不再盲猜（can_delegate=false 的 orchestrator
        # 等不出现在清单中，与 _run 侧拒绝口径一致）
        self.args_schema = _dynamic_mode_args_schema(NewTaskInput, "mode", "Slug of mode to start new task in.", self.workspace_root, delegable_only=True)

    def _load_available_modes(self) -> dict[str, str]:
        """动态加载可用模式（P6：经 ModeRegistry 单例，不再 ad-hoc ModeManager）"""
        try:
            from dawei.mode.registry import get_registry

            registry = get_registry(self.workspace_root)
            # Phase 4c：invalidate_registry 会替换单例对象 —— 同一性校验消除
            # 装后陈旧窗口（mode统一管理.md §7 验收 #7），实例缓存随新 Registry 重建
            if self._available_modes is not None and self._modes_registry is registry:
                return self._available_modes

            # 转换为简化的格式 {slug: name}
            available_modes = {mode.slug: mode.name for mode in registry.all()}

            self._available_modes = available_modes
            self._modes_registry = registry
            self.logger.info(f"Loaded {len(available_modes)} modes from ModeRegistry")
            return available_modes

        except Exception as e:
            self.logger.error(f"Failed to load modes from ModeRegistry: {e}", exc_info=True)
            # 返回空字典而不是硬编码的默认值
            return {}

    async def _run(
        self,
        mode: str,
        message: str,
        acceptance: str = "",
        deliverable: str = "",
        output_file: str | None = None,
        agent: str = "default",
        context: str | None = None,
        timeout: float | None = None,
        token_budget: int | None = None,
        tools: list[str] | None = None,
    ) -> str:
        """Create new task in specified mode with enhanced task management.

        同步确认式创建：await 子任务真正写入 task_graph 后才返回，
        返回结果包含真实创建状态与 subtask_id（失败对 LLM 可见）。
        """
        try:
            # P1b ⑦ 派发协议：验收标准必填且可判定 —— 没有它父 LLM 无法在报告
            # 回注时区分"完成"vs"完成但未达标"。fast-fail，对 LLM 可见。
            if not acceptance or not acceptance.strip():
                return json.dumps(
                    {
                        "status": "error",
                        "message": ("acceptance (验收标准) is required for new_task. Provide decidable criteria that can be verified from the subtask result alone, e.g. 'report contains all 7 sections', 'tests pass with 0 failures'."),
                        "hint": "Resend new_task with the acceptance argument. Subtask was NOT created.",
                    },
                    indent=2,
                )

            # C2/L1 粒度契约：deliverable 必填 —— 一个子任务 = 一个交付物。
            # 不先说清楚"交付什么"，粒度约束无从谈起。fast-fail，对 LLM 可见。
            if not deliverable or not deliverable.strip():
                return json.dumps(
                    {
                        "status": "error",
                        "message": ("deliverable is required for new_task: the single deliverable of this subtask in one short sentence (e.g. '交付/审查报告/新加坡_劳动合同.md'). One subtask = one deliverable; N similar deliverables must be split into N subtasks."),
                        "hint": "Resend new_task with the deliverable argument. Subtask was NOT created.",
                    },
                    indent=2,
                )

            # 【2026-09-12 执行期解析 — 根因修复】chat 路径的工具实例由
            # ToolManager 反射实例化（构造参数只有 workspace_root/user_id），
            # 构造期 task_graph 恒为 None 且永不回填；真正的 TaskGraph 由
            # Agent.create_with_default_engine 在工具创建之后挂到
            # user_workspace.task_graph（agent.py）。此前直接读 self.task_graph
            # 导致 new_task 必然失败 "No task graph available"（E2E 94b38bde）。
            task_graph = self._resolve_task_graph()

            # P3-0: 解析 Agent Profile（未知 agent 名 fast-fail，对 LLM 可见）
            from dawei.agentic.agent_profile import resolve as resolve_agent_profile

            profile = resolve_agent_profile(agent, workspace_root=self.workspace_root)

            # 动态加载可用模式
            available_modes = self._load_available_modes()

            # Check if mode exists
            if mode not in available_modes:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Mode '{mode}' not found",
                        "available_modes": list(available_modes.keys()),
                    },
                    indent=2,
                )

            # §7 验收 #5：can_delegate=false 的模式不可作为子任务目标 → 拒绝
            # （mode-工具解耦 D2：alias canonical 归一已删除，mode 存在性已由上方确认）
            try:
                from dawei.mode.registry import get_registry

                registry = get_registry(self.workspace_root)
                if not registry.can_delegate_to(mode):
                    return json.dumps(
                        {
                            "status": "error",
                            "message": (f"Mode '{mode}' cannot be delegated to (can_delegate=false)"),
                            "available_modes": sorted(m.slug for m in registry.all() if m.can_delegate),
                        },
                        indent=2,
                    )
            except Exception:
                # can_delegate 校验不可用不阻断创建（mode 存在性已由上方确认）
                self.logger.debug("can_delegate check unavailable", exc_info=True)

            # （mode-工具解耦 D6：派发期 mode/tool-group 预检已删除——mode 不再
            #   拦截工具，任何模式的子任务都可见已安装工具，无拦截反馈链）

            # 获取组件
            components = _import_task_graph_components()
            TodoItem = components["TodoItem"]
            TodoStatus = components["TodoStatus"]

            # Create initial TODO list for subtask
            initial_todos = [
                TodoItem(content=f"Start subtask in {mode} mode", status=TodoStatus.PENDING),
                TodoItem(content=f"Process: {message}", status=TodoStatus.PENDING),
            ]

            # 如果有 task_graph，同步创建子任务（等待真正写入图后才返回）
            subtask_id = None
            subtask_error = None
            if task_graph:
                from dawei.agentic.errors import (
                    DuplicateSubtaskError,
                    SubtaskBreadthLimitExceededError,
                    SubtaskGranularityError,
                )

                try:
                    subtask_id = await self._create_subtask(mode, message, initial_todos, profile=profile, context_note=context, timeout_seconds=timeout, token_budget=token_budget, acceptance_criteria=acceptance, tools=tools, deliverable=deliverable, output_file=output_file)
                except SubtaskGranularityError as gran_err:
                    # C3/L1 粒度硬闸 R1-R3：巨子任务创建层熔断 —— error + actionable
                    # 提示 → LLM 按提示拆分重派（与 DuplicateSubtaskError 同一模式，已验证有效）
                    _gdet = gran_err.details or {}
                    try:  # C15：粒度熔断指标（fire-and-forget）
                        from dawei.agentic.subtask_metrics import get_metrics

                        get_metrics().record_granularity_rejected(str(_gdet.get("rule") or "unknown"))
                    except Exception:  # noqa: BLE001 — 指标失败绝不影响主流程
                        pass
                    return json.dumps(
                        {
                            "type": "new_task",
                            "status": "error",
                            "error": "granularity_contract",
                            "rule": _gdet.get("rule"),
                            "evidence": _gdet.get("evidence"),
                            "message": (f"子任务粒度契约违规（{_gdet.get('rule')}）：{_gdet.get('evidence')}。一个子任务 = 一个交付物；N 件同类工作必须拆成 N 个子任务。"),
                            "hint": _gdet.get("hint"),
                        },
                        indent=2,
                    )
                except DuplicateSubtaskError as dup_err:
                    # P1-3 重复派发熔断：等价子任务已存在 → 拒绝 + 回指既有
                    # subtask_id，父 LLM 转 get_task_status 等待/复用，不再重派。
                    _det = dup_err.details or {}
                    return json.dumps(
                        {
                            "type": "new_task",
                            "status": "error",
                            "error": "duplicate_subtask",
                            "message": (f"同父下已存在等价子任务（status={_det.get('existing_status')}）：同一目标被重复派发已被熔断。"),
                            "existing_subtask_id": _det.get("existing_subtask_id"),
                            "hint": ("Do NOT re-dispatch the same goal. Use get_task_status on the existing subtask and wait for its report; if it already reported, reuse its result. If the goal genuinely changed, rewrite the message so the objective differs."),
                        },
                        indent=2,
                    )
                except SubtaskBreadthLimitExceededError as breadth_err:
                    # P1b ⑦ 广度闸（图谱层 SSOT 强制）：流控信号 → 可操作 error result。
                    # 携带活跃子任务 ID，父 LLM 可立即 get_task_status / abort_task。
                    _det = breadth_err.details or {}
                    return json.dumps(
                        {
                            "type": "new_task",
                            "status": "error",
                            "error": "breadth_limit",
                            "message": (f"同父活跃子任务已达上限 max_active_subtasks={_det.get('limit')}；当前活跃 {_det.get('active_count')} 个。"),
                            "active_subtasks": _det.get("active_subtask_ids", []),
                            "hint": ("Wait for existing subtasks to reach terminal states (get_task_status), or abort_task to free slots. Do NOT re-dispatch the same goal after CANCELLED."),
                        },
                        indent=2,
                    )
                except Exception as create_err:  # noqa: BLE001 — 创建失败必须对 LLM 可见
                    self.logger.exception("Subtask creation failed: ")
                    subtask_error = str(create_err)

            if subtask_error is not None:
                result = {
                    "type": "new_task",
                    "mode": mode,
                    "mode_name": available_modes[mode],
                    "message": message,
                    "status": "error",
                    "error": f"Failed to create subtask: {subtask_error}",
                    "hint": "Subtask was NOT created. You may retry, or handle the task yourself.",
                }
            elif task_graph is None:
                # FAST FAIL: no task graph attached (e.g. detached tool-execution
                # context) — a "created" result here would be a fabrication and
                # the orchestrator would report a subtask that never runs
                # (E2E 2026-09-03 gelu-research review-orchestrator dispatch).
                result = {
                    "type": "new_task",
                    "mode": mode,
                    "mode_name": available_modes[mode],
                    "message": message,
                    "status": "error",
                    "error": "No task graph available in this context; subtask was NOT created.",
                    "hint": "Handle the task yourself with your own tools, or tell the user dispatch is unavailable here.",
                }
            elif subtask_id is None:
                result = {
                    "type": "new_task",
                    "mode": mode,
                    "mode_name": available_modes[mode],
                    "message": message,
                    "status": "error",
                    "error": "No root task found for creating subtask",
                    "hint": "Subtask was NOT created. You may retry, or handle the task yourself.",
                }
            else:
                result = {
                    "type": "new_task",
                    "mode": mode,
                    "mode_name": available_modes[mode],
                    "message": message,
                    "subtask_id": subtask_id,
                    "agent": profile.name,  # §6.2: 前端子任务卡片渲染字段
                    "acceptance": acceptance,  # P1b ⑦: 回显验收标准（父 LLM 收报告时据此判定）
                    "deliverable": deliverable,  # C2/L1: 回显唯一交付物（前端卡片/status 渲染字段）
                    "conversation_id": None,  # 会话在子任务起跑时才分配（P2-7）；起跑后经 subtask_lifecycle 事件携带
                    "initial_todos": [todo.content for todo in initial_todos],
                    "status": "created",
                    "note": "Subtask created and registered in task graph. It will be executed after the current task's executor finishes. Use get_task_status to check its progress.",
                }

            self.logger.info(f"New task creation requested in {mode} mode")

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.exception("Error creating new task: ")
            return json.dumps(
                {"status": "error", "message": f"Error creating new task: {e!s}"},
                indent=2,
            )

    async def _create_subtask(
        self,
        mode: str,
        message: str,
        initial_todos,
        profile=None,
        context_note: str | None = None,
        timeout_seconds: float | None = None,
        token_budget: int | None = None,
        acceptance_criteria: str | None = None,
        tools: list[str] | None = None,
        deliverable: str | None = None,
        output_file: str | None = None,
        dispatch_identity: str | None = None,
        batch_id: str | None = None,
        item_identity: str | None = None,
    ) -> str | None:
        """异步创建子任务（新架构）

        Args:
            profile: 已解析的 AgentProfile（P3-0），None 时退回 default
            context_note: 工具调用的 context 参数，写入 metadata.context_note
            timeout_seconds: 子任务墙钟超时（P3-3，None/非正数 = 不限制）
            token_budget: 子任务 token 上限（P3-3，None/非正数 = 不限制）
            acceptance_criteria: 验收标准（P1b ⑦，new_task 路径必填；
                None = 内部调用/历史路径未提供，报告回注时不回显）
            tools: 最小工具面白名单（P2 工具集最小化）。None = 沿用 profile
                的裁剪配置；提供则覆盖 profile 的 allow/deny（调用参数 > profile
                文件，与 model/effort 同一优先序），提示词层裁剪 + 运行时强制
                双层生效
            deliverable: 本子任务唯一交付物（一句话）。写入 metadata.deliverable
            output_file: 长产物落盘路径（L4 输出契约）。写入 metadata.output_file，
                并把输出契约段自动注入 context_note（子任务首消息可见）
            dispatch_identity: 派发身份（C8）。None = 自动按
                hash(mode+deliverable+归一化message) 计算
            batch_id: 批次 id（C7）。非 None = new_task_batch 展开项：
                metadata 落 batch_id/item_identity，创建闸门按 batch 合法
                形态放行（硬顶由工具层 R5 把守）
            item_identity: 批次内工作项身份（C8 去重分量）

        Returns:
            创建成功的 subtask_id；无根任务时返回 None；失败时抛异常。
        """
        try:
            import uuid

            # 【2026-09-12 执行期解析】与 _run 同源，构造期 task_graph 可能冻结为 None
            task_graph = self._resolve_task_graph()
            if not task_graph:
                raise RuntimeError("No task graph available for creating subtask")

            # 获取组件
            components = _import_task_graph_components()
            TaskData = components["TaskData"]
            TaskContext = components["TaskContext"]
            TaskStatus = components["TaskStatus"]
            TaskPriority = components["TaskPriority"]

            # 获取根任务
            root_task = await task_graph.get_root_task()
            if not root_task:
                self.logger.warning("No root task found for creating subtask")
                return None

            # C6 钉死（事故：LLM 传 timeout:"600" 字符串，节点落库 null）：
            # 在唯一落库点把 timeout_seconds 强转 float —— schema 层校验与否都安全。
            if timeout_seconds is not None:
                timeout_seconds = float(timeout_seconds)

            # C3/L1 粒度硬闸 R1-R3（new_task / run_task 共用此入口）：
            # 事故根因是"单任务大小"维度零约束 —— 一份 message 涵盖 6 份文件 ×
            # 4 检查维度的巨子任务，死在最终轮单次 LLM 长生成被 300s 流超时
            # 杀死。宁可漏报不可误伤：R2 只拦"动词+数字+量词+文书名词"紧组合。
            from dawei.agentic.errors import SubtaskGranularityError
            from dawei.task_graph.granularity import (
                MAX_SUBTASK_MESSAGE_CHARS,
                acceptance_implies_plural,
                detect_plural_deliverables,
            )

            if message and len(message) > MAX_SUBTASK_MESSAGE_CHARS:
                raise SubtaskGranularityError(
                    rule="R1_message_too_long",
                    evidence=f"message {len(message)} chars > {MAX_SUBTASK_MESSAGE_CHARS}",
                    hint=("指令过长：精简为单一交付物的自包含指令（目标/范围/验收）；若确属 N 件同类工作，改用 new_task_batch(template, items=[每件一项]) 并行派发。"),
                )

            _plural_evidence = detect_plural_deliverables(message)
            if _plural_evidence:
                raise SubtaskGranularityError(
                    rule="R2_plural_deliverables",
                    evidence=_plural_evidence,
                    hint=("检测到 N 份同类文书工作被合并进一个子任务。一个子任务 = 一个交付物：改用 new_task_batch(template, items=[每份一项]) 并行派发，每个子任务只处理自己的那 1 份，各自产出独立报告文件。"),
                )

            _acc_evidence = acceptance_implies_plural(acceptance_criteria)
            if _acc_evidence:
                raise SubtaskGranularityError(
                    rule="R3_plural_acceptance",
                    evidence=_acc_evidence,
                    hint=("验收标准以'每份/逐份/全部N份'为对象，说明目标本身就是 N 份交付。改用 new_task_batch 并行派发（acceptance_template 按项展开），各写各的验收标准。"),
                )

            # P3-4: 创建时并发 fast-fail —— 统计图中未终结子任务数，超限直接拒绝
            # （对齐 Claude Code 超限 spawn 直接失败、不排队）
            def _agents_limits() -> tuple[int, int]:
                try:
                    from dawei.config.settings import get_settings

                    ae = get_settings().agent_execution
                    return ae.max_concurrent_subtasks, ae.max_subtask_depth
                except Exception:  # noqa: BLE001 — 配置不可用时退回保守默认
                    return 3, 3

            _max_concurrent, _max_depth = _agents_limits()
            _UNFINISHED = {
                TaskStatus.PENDING,
                TaskStatus.RUNNING,
                TaskStatus.WAITING_FOR_TOOL,
                TaskStatus.PAUSED,
                TaskStatus.INTERACTIVE,  # 2026-09-17 修漏计：追问等待同样占用在飞名额
            }
            all_tasks = await task_graph.get_all_tasks()
            unfinished = [t for t in all_tasks if getattr(t, "parent_id", None) is not None and getattr(t, "status", None) in _UNFINISHED]

            # P1-3 重复派发熔断（C8 身份改造）：同父下已存在同派发身份的
            # 未终结/已完成子任务 → 拒绝并回指既有 subtask_id。
            # 身份 = metadata.dispatch_identity = hash(mode+deliverable+item.identity)；
            # batch 展开项各自身份不同（item.identity 互异）→ 互不误伤。
            # 旧节点（无 dispatch_identity，历史会话恢复）回落 description
            # 归一化前缀比对。背景事故（E2E 2026-09-18 综述流水线）：编排器
            # 把等价的 arXiv 核验子任务重派 6 次，单子任务烧 1.79M tokens。
            # FAILED/ABORTED/CANCELLED 不算重复（显式重试合法）。
            from dawei.agentic.errors import DuplicateSubtaskError

            def _desc_text(desc) -> str:  # noqa: ANN001 — 兼容 str / TaskDescription / dict
                if isinstance(desc, dict):
                    return str(desc.get("text", "") or "")
                text = getattr(desc, "text", None)
                return str(text if text is not None else (desc or ""))

            _new_key = _normalize_desc_key(message)
            _new_identity = dispatch_identity or _dispatch_identity(mode, deliverable, item_identity, message)
            _dup_blocking = _UNFINISHED | {TaskStatus.COMPLETED}
            if _new_key:
                for t in all_tasks:
                    if getattr(t, "parent_id", None) != root_task.task_id:
                        continue
                    _t_status = getattr(t, "status", None)
                    if _t_status not in _dup_blocking:
                        continue
                    _t_meta = getattr(getattr(t, "data", None), "metadata", None) or {}
                    _t_identity = _t_meta.get("dispatch_identity")
                    if _t_identity is not None:
                        if _t_identity == _new_identity:
                            raise DuplicateSubtaskError(
                                parent_id=root_task.task_id,
                                existing_id=t.task_node_id,
                                existing_status=str(getattr(_t_status, "value", _t_status)),
                                desc_key=_new_identity,
                            )
                    elif _normalize_desc_key(_desc_text(getattr(t.data, "description", ""))) == _new_key:
                        raise DuplicateSubtaskError(
                            parent_id=root_task.task_id,
                            existing_id=t.task_node_id,
                            existing_status=str(getattr(_t_status, "value", _t_status)),
                            desc_key=_new_key[:40],
                        )

            # C9：batch 合法形态放行（单次硬顶由工具层 R5 max_batch_items 把守）；
            # 零散 new_task 无脑堆叠仍被拦。执行侧真并发由 max_parallel_tasks
            # 信号量限流排队（wave 机制），超出不失败。
            if not batch_id and len(unfinished) >= _max_concurrent:
                raise RuntimeError(f"并发子任务上限（max_concurrent_subtasks={_max_concurrent}）已达到：当前未终结子任务 {len(unfinished)} 个。请等待现有子任务完成后再派发，或先 abort 部分子任务。")

            # P3-5: 深度限制 —— 新子任务 depth = 父 depth + 1，达到上限拒绝派生
            _depth = int(getattr(root_task.data, "depth", 0) or 0) + 1
            if _depth >= _max_depth:
                raise RuntimeError(f"已达子任务派生深度上限（max_subtask_depth={_max_depth}）：到顶后请自行处理子步骤，不要再派生子任务。")

            # P3-0: Agent Profile 元数据（agent 名 / model / effort / 工具裁剪等）
            from dawei.agentic.agent_profile import resolve as resolve_agent_profile

            if profile is None:
                profile = resolve_agent_profile(
                    "default",
                    parent_task=root_task,
                    workspace_root=self.workspace_root,
                )
            profile_meta = profile.to_metadata()
            if context_note:
                profile_meta["context_note"] = context_note
            # C2/L1: 唯一交付物落 metadata（get_task_status / 前端子任务卡片渲染字段）
            if deliverable and deliverable.strip():
                profile_meta["deliverable"] = deliverable.strip()
            # L4 输出契约：长产物落盘路径 —— 除写 metadata 外，把契约段注入
            # context_note（拼进子任务首消息），子任务开工即知"全文写文件、
            # 对话只回 ≤500 字摘要 + 路径"（治本单轮长生成 300s 流超时）。
            if output_file and output_file.strip():
                _output_contract = f"输出契约：完整交付物必须写入工作区文件 {output_file.strip()}；对话回复仅返回 ≤500 字摘要 + 该文件路径，禁止在对话中输出全文（单轮长生成会被流超时杀死）。"
                _existing_note = profile_meta.get("context_note")
                profile_meta["context_note"] = f"{_existing_note}\n{_output_contract}" if _existing_note else _output_contract
                profile_meta["output_file"] = output_file.strip()
            # P2 工具集最小化：调用参数 tools > profile 文件的 allow/deny
            # （与 model/effort 同一优先序）；空列表视为未提供（防 LLM 传 [] 砖死子任务）
            if tools:
                profile_meta["tools_allowlist"] = list(tools)
                profile_meta.pop("tools_denylist", None)

            # P3-7 防再委派护栏（2026-09-21）：new_task 创建的子任务一律在
            # 运行时拒绝 new_task。根因：_create_subtask 恒以 root 为父，
            # 子任务内再调 new_task 只会在 root 下造出兄弟节点，深度护栏
            # （P3-5）对此不生效；tui-review 综述实测 Stage 6 因此派生 4 个
            # 变体、S16 重跑 2 轮，重复尝试烧掉 ~3.4M 累计输入 token。
            # 运行时强制点：tool_message_handler 的 tools_denylist 检查
            # （deny 优先于 allow，显式 tools 白名单也无法绕过）。
            profile_meta["tools_denylist"] = sorted(set(profile_meta.get("tools_denylist") or []) | {"new_task"})

            # 创建子任务数据
            subtask_context = TaskContext(
                user_id=root_task.data.context.user_id,
                session_id=root_task.data.context.session_id,
                message_id=root_task.data.context.message_id,
                workspace_path=root_task.data.context.workspace_path,
                parent_context=root_task.data.context.to_dict(),
                task_files=root_task.data.context.task_files,
                task_images=root_task.data.context.task_images,
            )

            subtask_data = TaskData(
                task_node_id=str(uuid.uuid4()),  # P0-4/F7: 字段名是 task_node_id（此前 task_id= 必然 TypeError）
                description=message,
                mode=mode,
                status=TaskStatus.PENDING,
                model=profile.model,  # P3-0b/F1: 按子任务模型路由（None=继承）
                reasoning_effort=profile.reasoning_effort,
                depth=_depth,  # P3-5: 父深度 + 1（root=0）
                timeout_seconds=timeout_seconds,  # P3-3: 墙钟超时
                token_budget=token_budget,  # P3-3: token 预算
                acceptance_criteria=acceptance_criteria,  # P1b ⑦: 验收标准（报告回注回显）
                context=subtask_context,
                todos=initial_todos,
                priority=TaskPriority.MEDIUM,
                metadata={
                    "parent_task_id": root_task.task_id,
                    "created_by": "NewTaskBatchTool" if batch_id else "NewTaskTool",
                    "dispatch_identity": _new_identity,
                    **({"batch_id": batch_id} if batch_id else {}),
                    **({"item_identity": item_identity} if item_identity else {}),
                    **profile_meta,
                },
            )

            # 创建子任务
            await task_graph.create_subtask(root_task.task_id, subtask_data)
            self.logger.info(f"Created subtask {subtask_data.task_node_id} in {mode} mode under parent {root_task.task_id}")

            # P3-6: created 生命周期事件（new_task / run_task 共用此单一入口）
            try:
                from dawei.agentic.subtask_events import emit_subtask_lifecycle

                await emit_subtask_lifecycle(
                    "created",
                    task_node_id=subtask_data.task_node_id,
                    parent_id=root_task.task_id,
                    agent=profile.name,
                    depth=_depth,
                    status="pending",
                )
            except Exception:  # noqa: BLE001 — 事件失败不影响创建
                self.logger.exception("Failed to emit subtask created event: ")

            return subtask_data.task_node_id

        except Exception as e:
            # Fast Fail: 所有异常向上抛，由调用方（_run）转成对 LLM 可见的错误结果
            self.logger.error(f"Failed to create subtask: {e}", exc_info=True)
            raise


# ==================== AbortTaskTool (P3-2: 子任务级联取消) ====================


class AbortTaskInput(BaseModel):
    """Input for AbortTaskTool."""

    subtask_id: str = Field(..., description="ID of the subtask to abort.")
    reason: str | None = Field(None, description="Why the subtask is being aborted (recorded in metadata).")


class AbortTaskTool(CustomBaseTool):
    """终止子任务工具（P3-2 abort 部分）。

    置目标子任务 ABORTED 并级联取消其整棵子树（父 ABORTED 传播子任务，不向上传播）。
    对已终结子任务幂等（如实回报终态，不改状态）。根任务不可经此工具终止。
    """

    name: ClassVar[str] = "abort_task"
    description: ClassVar[str] = "Aborts a subtask and all of its descendants (cascading cancellation). Idempotent on already-finished subtasks. The root task cannot be aborted via this tool. Use after new_task/run_task delegation when a subtask turns out to be unnecessary or wrong."
    args_schema: ClassVar[type[BaseModel]] = AbortTaskInput

    def __init__(self, task_graph=None, workspace_root: str | None = None):
        super().__init__()
        self.task_graph = task_graph
        self.workspace_root = workspace_root
        self.logger = get_logger(__name__)

    async def _run(self, subtask_id: str, reason: str | None = None) -> str:
        import json as _json
        from datetime import datetime

        from dawei.core.datetime_compat import UTC

        task_graph = self._resolve_task_graph()
        if not task_graph:
            return _json.dumps({"status": "error", "message": "task_graph unavailable"}, indent=2)

        components = self._import_task_graph_components()
        TaskStatus_ = components["TaskStatus"]
        terminal = {TaskStatus_.COMPLETED, TaskStatus_.FAILED, TaskStatus_.ABORTED, TaskStatus_.CANCELLED}
        active = {TaskStatus_.RUNNING, TaskStatus_.WAITING_FOR_TOOL, TaskStatus_.INTERACTIVE}

        node = await task_graph.get_task(subtask_id)
        if node is None:
            return _json.dumps(
                {"status": "error", "subtask_id": subtask_id, "message": "Subtask not found in graph"},
                indent=2,
            )

        if getattr(node, "parent_id", None) is None:
            return _json.dumps(
                {
                    "status": "error",
                    "subtask_id": subtask_id,
                    "message": "Refusing to abort the root task via abort_task; use the engine stop for the whole graph.",
                },
                indent=2,
            )

        current_status = getattr(node, "status", None)
        if current_status in terminal:
            # 幂等：如实回报终态
            return _json.dumps(
                {
                    "status": current_status.value,
                    "subtask_id": subtask_id,
                    "message": f"Subtask already in terminal state '{current_status.value}'; no change made.",
                },
                indent=2,
            )

        # 级联：BFS 收集整棵子树（防环：visited 集合）;
        # 运行中节点单独记录(finalize 后状态为终态,不能再按状态判定)
        to_abort: list[str] = []
        active_ids: list[str] = []
        visited: set[str] = set()
        queue = [subtask_id]
        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)
            n = await task_graph.get_task(nid)
            if n is None:
                continue
            st = getattr(n, "status", None)
            if st in terminal:
                continue  # 已终结的跳过（不改写历史终态）
            to_abort.append(nid)
            if st in active:
                active_ids.append(nid)
            queue.extend(getattr(n, "child_ids", []) or [])

        # P1a(2026-09-17):主动取消 → CANCELLED(父 LLM 禁止同目标重派,区别于系统中止 ABORTED);
        # finalize_task 保证 status+result 同笔写(不变量 3),先落状态后停执行,
        # 终态锁定压制 CancelledError 路径的 ABORTED 改写(先到先得)
        aborted = 0
        for nid in to_abort:
            per_reason = reason or "" if nid == subtask_id else f"(随父任务取消: {reason or ''})"
            # P2-B 补全:审计 metadata 级联子树逐节点写(此前仅目标节点),
            # 且先于 finalize 写——finalize 触发的 TASK_GRAPH_UPDATED 持久化
            # 会一并落盘审计键
            try:
                _n = await task_graph.get_task(nid)
                _meta = getattr(getattr(_n, "data", None), "metadata", None) if _n is not None else None
                if _meta is not None:
                    _meta["aborted_by"] = "AbortTaskTool" if nid == subtask_id else "AbortTaskTool(cascade)"
                    _meta["aborted_reason"] = per_reason
                    _meta["aborted_at"] = datetime.now(UTC).isoformat()
            except Exception:  # noqa: BLE001 — 元数据失败不影响主流程
                self.logger.exception(f"abort_task: failed to write audit metadata for {nid}")
            try:
                changed = await task_graph.finalize_task(nid, TaskStatus_.CANCELLED, f"(父任务取消: {per_reason})")
            except Exception:
                changed = await task_graph.update_task_status(nid, TaskStatus_.ABORTED)
            aborted += 1 if changed else 0
            # P3-6: aborted 生命周期事件（逐节点；工具直改状态不经 engine choke point，需在此补发）
            try:
                from dawei.agentic.subtask_events import emit_subtask_lifecycle

                n = await task_graph.get_task(nid)
                nd = getattr(n, "data", None) if n is not None else None
                await emit_subtask_lifecycle(
                    "aborted",
                    task_node_id=nid,
                    parent_id=getattr(n, "parent_id", None) if n is not None else None,
                    conversation_id=getattr(nd, "conversation_id", None) if nd is not None else None,
                    status="cancelled",
                    extra={"reason": reason or "", "by": "abort_task"},
                )
            except Exception:  # noqa: BLE001 — 事件失败不影响 abort 主流程
                self.logger.exception("abort_task: failed to emit subtask_aborted event: ")

        # 停止仍在运行的执行(⑥:状态与执行必须同步收敛,否则节点 CANCELLED 但执行还在烧钱)
        engine = self._resolve_execution_engine()
        if engine is not None:
            for nid in active_ids:
                try:
                    await engine.cancel_task_execution(nid)
                except Exception:  # noqa: BLE001 — 单节点取消失败不阻断其余
                    self.logger.exception(f"abort_task: engine cancel failed for {nid}: ")

        self.logger.info(f"abort_task: cancelled {aborted} node(s) under {subtask_id} (reason={reason!r})")
        return _json.dumps(
            {
                "status": "cancelled",
                "subtask_id": subtask_id,
                "cancelled_count": aborted,
                "cancelled_ids": to_abort,
                "reason": reason or "",
                "note": "cancelled = 主动取消,禁止同目标重派(区别于 aborted=系统中止)",
            },
            indent=2,
        )

    @staticmethod
    def _import_task_graph_components() -> dict:
        """延迟导入 TaskStatus（避免模块级循环依赖）"""
        from dawei.entity.task_types import TaskStatus

        return {"TaskStatus": TaskStatus}


# ==================== RunTaskTool (阻塞式委派, Claude Code Task 模式) ====================

# 活动执行引擎注册表（2026-09-12 由模块级单全局改造）：
# TaskGraphExecutionEngine 初始化时注册自身。主解析路径已改为
# user_workspace.execution_engine（agent.py 挂载，天然按工作区隔离，
# 见 CustomBaseTool._resolve_execution_engine）——本注册表仅作兜底：
#   _ACTIVE_EXECUTION_ENGINES: workspace_id -> engine（多工作区并存正确）
#   _ACTIVE_EXECUTION_ENGINE:  最后注册者（无工作区上下文调用方兜底，
#                              如 subtask_events._resolve_engine；多并发
#                              工作区时语义"最新"，属可接受降级）
_ACTIVE_EXECUTION_ENGINES: dict[str, Any] = {}
_ACTIVE_EXECUTION_ENGINE = None


def _engine_workspace_id(engine) -> str | None:
    """从 engine 的 user_workspace 提取稳定注册键（workspace_id）"""
    ws = getattr(engine, "_user_workspace", None)
    if ws is None:
        return None
    ws_id = getattr(ws, "workspace_id", None)
    if ws_id:
        return str(ws_id)
    info = getattr(ws, "workspace_info", None)
    return str(info.id) if info is not None and getattr(info, "id", None) else None


def set_active_execution_engine(engine) -> None:
    """注册当前活动的 TaskGraphExecutionEngine（供 run_task 内联执行子任务）"""
    global _ACTIVE_EXECUTION_ENGINE
    _ACTIVE_EXECUTION_ENGINE = engine
    ws_id = _engine_workspace_id(engine)
    if ws_id:
        if engine is None:
            _ACTIVE_EXECUTION_ENGINES.pop(ws_id, None)
        else:
            _ACTIVE_EXECUTION_ENGINES[ws_id] = engine


def get_active_execution_engine(workspace_id: str | None = None):
    """获取活动的 TaskGraphExecutionEngine（可能为 None）。

    Args:
        workspace_id: 指定时按工作区精确取（多会话安全）；
                      缺省回落最后注册者（兼容旧行为/单测 monkeypatch）。
    """
    if workspace_id:
        engine = _ACTIVE_EXECUTION_ENGINES.get(str(workspace_id))
        if engine is not None:
            return engine
    return _ACTIVE_EXECUTION_ENGINE


class RunTaskInput(BaseModel):
    """Input for RunTaskTool."""

    mode: str = Field(..., description="Mode slug to run the subtask in (e.g., 'labor-compliance').")
    message: str = Field(
        ...,
        description="Detailed, self-contained task description for the subtask. Must include all necessary context (goal, constraints, expected deliverables) because the subtask only sees this message.",
    )
    agent: str = Field(
        "default",
        description="Agent profile name (default/worker/explorer or workspace .dawei/agents/*)",
    )
    context: str | None = Field(
        None,
        description="Optional extra context for the subtask (appended to metadata.context_note)",
    )
    timeout: float | None = Field(
        None,
        description="Optional wall-clock timeout in seconds for the subtask (P3-3). Exceeding it fails the subtask fast with the reason returned as the tool result. None/0 = no limit.",
    )
    token_budget: int | None = Field(
        None,
        description="Optional token budget for the subtask (P3-3). Exceeding it fails the subtask fast with the reason returned as the tool result. None/0 = no limit.",
    )


class RunTaskTool(CustomBaseTool):
    """阻塞式子任务委派工具（对应 Claude Code 的 Task/subagent 模式）。

    与 new_task（异步批量委派）不同，run_task 会同步执行子任务并等待其完成，
    把子任务结果作为 tool_result 直接返回给父任务。适用于"派一步等一步"的
    紧凑委派场景。
    """

    name: ClassVar[str] = "run_task"
    description: ClassVar[str] = "Runs a subtask in the specified mode and BLOCKS until it finishes, returning its result directly. Use for step-by-step delegation where you need the result before continuing. For batch/background delegation use new_task instead."
    args_schema: ClassVar[type[BaseModel]] = RunTaskInput

    def __init__(self, task_graph=None, workspace_root: str | None = None):
        super().__init__()
        self.task_graph = task_graph
        self.workspace_root = workspace_root
        self.logger = get_logger(__name__)

    async def _run(
        self,
        mode: str,
        message: str,
        agent: str = "default",
        context: str | None = None,
        timeout: float | None = None,
        token_budget: int | None = None,
    ) -> str:
        """同步执行子任务并返回结果"""
        import json as _json

        # P3-0: 解析 Agent Profile（未知 agent 名 fast-fail，对 LLM 可见）
        from dawei.agentic.agent_profile import resolve as resolve_agent_profile
        from dawei.agentic.errors import SubtaskGranularityError

        try:
            profile = resolve_agent_profile(agent, workspace_root=self.workspace_root)
        except ValueError as e:
            return _json.dumps({"status": "error", "message": str(e)}, indent=2)

        # 复用 NewTaskTool 的模式校验与创建逻辑
        # 【2026-09-12 单一事实源】临时实例必须继承本工具的运行期上下文（user_workspace），
        # 否则 creator 内部 _resolve_task_graph() 解析不到工作区挂载的 task_graph。
        creator = NewTaskTool(self.task_graph, self.workspace_root)
        creator.user_workspace = self.user_workspace
        available_modes = creator._load_available_modes()
        if mode not in available_modes:
            return _json.dumps(
                {"status": "error", "message": f"Mode '{mode}' not found", "available_modes": list(available_modes.keys())},
                indent=2,
            )

        # 【2026-09-12 执行期解析】task_graph/engine 均从 user_workspace 解析（多工作区隔离），
        # 模块级注册表仅作无工作区上下文时的兜底。
        task_graph = self._resolve_task_graph()
        engine = self._resolve_execution_engine()
        if not engine or not task_graph:
            return _json.dumps(
                {
                    "status": "error",
                    "message": "Execution engine unavailable; inline subtask execution not possible. Use new_task instead.",
                },
                indent=2,
            )

        components = _import_task_graph_components()
        TodoItem = components["TodoItem"]
        TodoStatus = components["TodoStatus"]

        initial_todos = [
            TodoItem(content=f"Start subtask in {mode} mode", status=TodoStatus.PENDING),
            TodoItem(content=f"Process: {message}", status=TodoStatus.PENDING),
        ]

        # 1) 同步创建子任务（写入图后才继续）
        try:
            subtask_id = await creator._create_subtask(mode, message, initial_todos, profile=profile, context_note=context, timeout_seconds=timeout, token_budget=token_budget)
        except SubtaskGranularityError as gran_err:
            # C3/L1 粒度硬闸与 new_task 同源（run_task 也只该派单件工作）：
            # 结构化 error + hint，LLM 按提示拆分重派，而非裸异常串。
            _gdet = gran_err.details or {}
            try:  # C15：粒度熔断指标（fire-and-forget）
                from dawei.agentic.subtask_metrics import get_metrics

                get_metrics().record_granularity_rejected(str(_gdet.get("rule") or "unknown"))
            except Exception:  # noqa: BLE001 — 指标失败绝不影响主流程
                pass
            return _json.dumps(
                {
                    "type": "run_task",
                    "status": "error",
                    "error": "granularity_contract",
                    "rule": _gdet.get("rule"),
                    "evidence": _gdet.get("evidence"),
                    "message": (f"子任务粒度契约违规（{_gdet.get('rule')}）：{_gdet.get('evidence')}。一个子任务 = 一个交付物；run_task 只用于单件工作，N 件同类工作请拆成 N 个子任务分别派发。"),
                    "hint": _gdet.get("hint"),
                },
                indent=2,
            )
        except Exception as e:  # noqa: BLE001 — 失败必须对 LLM 可见
            self.logger.exception("run_task: subtask creation failed: ")
            return _json.dumps({"status": "error", "message": f"Failed to create subtask: {e!s}"}, indent=2)
        if subtask_id is None:
            return _json.dumps({"status": "error", "message": "No root task found for creating subtask"}, indent=2)

        # 2) 内联执行（阻塞至子任务终态；引擎对已 COMPLETED 节点幂等跳过）
        node = await task_graph.get_task(subtask_id)
        if node is None:
            return _json.dumps({"status": "error", "message": f"Subtask {subtask_id} disappeared from graph"}, indent=2)

        self.logger.info(f"run_task: executing subtask {subtask_id} ({mode}) inline")
        try:
            final_status = await engine._execute_task_graph_recursive(node)
        except Exception as e:  # noqa: BLE001
            self.logger.exception(f"run_task: subtask {subtask_id} execution failed: ")
            return _json.dumps(
                {"status": "error", "subtask_id": subtask_id, "message": f"Subtask execution error: {e!s}"},
                indent=2,
            )

        # 3) 提取子任务结果：节点 result 优先（单一事实源，执行收尾时写入）；
        #    缺失时回落旧链路（隔离会话定向提取 → 共享对话反向扫描），兼容历史会话
        result_text = "(无显式完成结果)"
        refreshed = await task_graph.get_task(subtask_id)
        if refreshed is not None:
            node = refreshed
        node_result = getattr(getattr(node, "data", None), "result", None)
        if node_result:
            result_text = str(node_result)[:2000]
        else:
            try:
                from dawei.agentic.subtask_conversation import extract_task_completion, select_result_conversation

                conversation = select_result_conversation(engine, subtask_id)
                result_text = extract_task_completion(conversation)
            except Exception:  # noqa: BLE001
                self.logger.exception("run_task: failed to extract subtask result: ")

        # P3-7: 子任务结果作为 tool_result 返回父代理前，中和伪造系统标签
        from dawei.agentic.injection_guard import sanitize_output

        _safe = sanitize_output(result_text)
        if _safe != result_text:
            self.logger.warning(f"Injection guard: sanitized forged system tags in run_task result (subtask {subtask_id})")
            result_text = _safe

        return _json.dumps(
            {
                "type": "run_task",
                "status": "completed" if final_status.value == "completed" else final_status.value,
                "subtask_id": subtask_id,
                "conversation_id": getattr(getattr(node, "data", None), "conversation_id", None),  # §6.2: 前端子任务卡片/线程抽屉字段
                "agent": (getattr(getattr(node, "data", None), "metadata", None) or {}).get("agent"),
                "mode": mode,
                "result": result_text,
            },
            indent=2,
        )


# ==================== NewTaskBatchTool (C7: L2 批量并行原语) ====================


class BatchItem(BaseModel):
    """new_task_batch 的单个工作项：identity 必填且同批互异，其余字段自由。

    自由字段供 template 占位符引用（{item.path} / {item.report_path} / ...），
    pydantic extra="allow" 下可作属性访问。
    """

    model_config = ConfigDict(extra="allow")

    identity: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description=("Unique identity of this work item within the batch (the file / jurisdiction / entity it covers). Dedup key component: re-dispatching the same identity is blocked, different identities never collide."),
    )


class NewTaskBatchInput(BaseModel):
    """Input for NewTaskBatchTool."""

    mode: str = Field(..., description="Mode slug for ALL expanded subtasks (must be delegable).")
    template: str = Field(
        ...,
        max_length=600,
        description=("Instruction template, ONE deliverable per item, using {item.<field>} placeholders (e.g. {item.path}, {item.report_path}) or bare {item}. Each item is expanded into its own self-contained subtask message. Escape literal braces as {{ }}."),
    )
    items: list[BatchItem] = Field(
        ...,
        min_length=1,
        description=("Work items; each becomes ONE parallel subtask. Every item MUST carry a unique non-empty 'identity' plus whatever fields the templates reference. Max 16 items."),
    )
    acceptance_template: str = Field(
        ...,
        description=("Acceptance criteria template per item, decidable from that item's result alone (e.g. 'report for {item.identity} covers all 7 sections')."),
    )
    deliverable_template: str = Field(
        ...,
        max_length=300,
        description=("Single-deliverable template per item, one short sentence (e.g. '交付/审查报告/{item.identity}.md')."),
    )
    output_file_template: str | None = Field(
        None,
        max_length=500,
        description=("Optional per-item output file template. REQUIRED for report/review-type deliverables: full artifact to file, chat reply only ≤500-char summary + path."),
    )
    agent: str = Field("default", description="Agent profile name applied to all items.")
    context: str | None = Field(None, description="Optional extra context appended to every item's metadata.context_note.")
    timeout: float | None = Field(None, description="Optional wall-clock timeout in seconds applied to every item.")
    token_budget: int | None = Field(None, description="Optional token budget applied to every item.")
    tools: list[str] | None = Field(None, description="Optional minimal tool allowlist applied to every item.")


class NewTaskBatchTool(CustomBaseTool):
    """批量并行委派工具（C7/L2）：一个模板 + 清单，一次展开 N 个同构子任务。

    为什么是独立工具而不是 N 个 new_task：LLM 偷懒把 N 件同类工作塞一个
    子任务（事故实证）；N 个 new_task 会撞广度闸且 message 前缀雷同导致
    去重误伤。展开后的节点就是普通子任务节点 —— 编排循环、wave、依赖
    闸门、报告回注全部复用现有机制（KISS，无新执行路径）。
    """

    name: ClassVar[str] = "new_task_batch"
    description: ClassVar[str] = (
        "Expands ONE template over a list of items into N parallel subtasks (one deliverable "
        "per item) and returns immediately. MANDATORY for N>=2 homogeneous work items (N "
        "files / jurisdictions / entities): never merge them into one subtask, and never "
        "write N separate new_task calls. Each item needs a unique 'identity'; templates use "
        "{item.<field>} placeholders. Max 16 items; granularity contract applies per item."
    )
    args_schema: ClassVar[type[BaseModel]] = NewTaskBatchInput

    def __init__(self, task_graph=None, workspace_root: str | None = None):
        super().__init__()
        self.task_graph = task_graph
        self.workspace_root = workspace_root
        self.logger = get_logger(__name__)

    @staticmethod
    def _fmt(tpl: str, item: BatchItem) -> str:
        """模板展开：{item.<field>} / {item}；未知占位符抛 KeyError/AttributeError（对 LLM 可见）"""
        return tpl.format(item=item)

    async def _run(
        self,
        mode: str,
        template: str,
        items: list[BatchItem],
        acceptance_template: str,
        deliverable_template: str,
        output_file_template: str | None = None,
        agent: str = "default",
        context: str | None = None,
        timeout: float | None = None,
        token_budget: int | None = None,
        tools: list[str] | None = None,
    ) -> str:
        import json as _json
        import uuid as _uuid

        from dawei.agentic.errors import DuplicateSubtaskError, SubtaskGranularityError

        # ---------- R5：条目硬顶 / identity 唯一性（fast-fail，对 LLM 可见）----------
        try:
            from dawei.config.settings import get_settings

            _max_items = int(get_settings().agent_execution.max_batch_items)
        except Exception:  # noqa: BLE001 — 配置不可用退回保守默认
            _max_items = 16
        if not items:
            return _json.dumps(
                {"type": "new_task_batch", "status": "error", "error": "empty_items", "message": "items must contain at least 1 item."},
                indent=2,
            )
        if len(items) > _max_items:
            return _json.dumps(
                {
                    "type": "new_task_batch",
                    "status": "error",
                    "error": "batch_limit",
                    "message": f"items {len(items)} exceed max_batch_items={_max_items}.",
                    "hint": f"Split into multiple batches of at most {_max_items} items each, or narrow the scope.",
                },
                indent=2,
            )
        _seen: dict[str, int] = {}
        for idx, it in enumerate(items):
            if not str(it.identity).strip():
                return _json.dumps(
                    {
                        "type": "new_task_batch",
                        "status": "error",
                        "error": "invalid_identity",
                        "message": f"items[{idx}].identity is empty; every item needs a unique non-empty identity.",
                    },
                    indent=2,
                )
            if it.identity in _seen:
                return _json.dumps(
                    {
                        "type": "new_task_batch",
                        "status": "error",
                        "error": "duplicate_identity",
                        "message": f"identity '{it.identity}' appears more than once (items[{_seen[it.identity]}] and items[{idx}]).",
                        "hint": "Identities must be unique within a batch — they are the dedup key for re-dispatch.",
                    },
                    indent=2,
                )
            _seen[it.identity] = idx

        # ---------- 上下文解析（与 RunTaskTool 同模式：临时实例继承运行期上下文）----------
        task_graph = self._resolve_task_graph()
        if not task_graph:
            return _json.dumps(
                {
                    "type": "new_task_batch",
                    "status": "error",
                    "message": "No task graph available in this context; batch dispatch is NOT possible. Use new_task or handle items yourself.",
                },
                indent=2,
            )

        try:
            from dawei.agentic.agent_profile import resolve as resolve_agent_profile

            profile = resolve_agent_profile(agent, workspace_root=self.workspace_root)
        except ValueError as e:
            return _json.dumps({"type": "new_task_batch", "status": "error", "message": str(e)}, indent=2)

        creator = NewTaskTool(self.task_graph, self.workspace_root)
        creator.user_workspace = self.user_workspace
        available_modes = creator._load_available_modes()
        if mode not in available_modes:
            return _json.dumps(
                {
                    "type": "new_task_batch",
                    "status": "error",
                    "message": f"Mode '{mode}' not found",
                    "available_modes": list(available_modes.keys()),
                },
                indent=2,
            )
        try:
            from dawei.mode.registry import get_registry

            if not get_registry(self.workspace_root).can_delegate_to(mode):
                return _json.dumps(
                    {
                        "type": "new_task_batch",
                        "status": "error",
                        "message": f"Mode '{mode}' cannot be delegated to (can_delegate=false)",
                    },
                    indent=2,
                )
        except Exception:  # noqa: BLE001 — can_delegate 校验不可用不阻断（mode 存在性已确认）
            self.logger.debug("can_delegate check unavailable for new_task_batch", exc_info=True)

        components = _import_task_graph_components()
        TodoItem = components["TodoItem"]
        TodoStatus = components["TodoStatus"]

        batch_id = _uuid.uuid4().hex[:12]
        dispatch_results: list[dict] = []
        created_ids: list[str] = []

        for item in items:
            # 模板展开（未知占位符 = 模板与 items 字段不匹配 → 逐项 error，不炸整批）
            try:
                message = self._fmt(template, item)
                acceptance = self._fmt(acceptance_template, item)
                deliverable = self._fmt(deliverable_template, item)
                output_file = self._fmt(output_file_template, item) if output_file_template else None
            except (KeyError, AttributeError, IndexError, ValueError) as e:
                dispatch_results.append(
                    {
                        "identity": item.identity,
                        "status": "error",
                        "error": "template_placeholder",
                        "message": f"template references a field this item does not have: {e}",
                    },
                )
                continue

            initial_todos = [
                TodoItem(content=f"Start subtask in {mode} mode", status=TodoStatus.PENDING),
                TodoItem(content=f"Process: {message}", status=TodoStatus.PENDING),
            ]
            try:
                subtask_id = await creator._create_subtask(
                    mode,
                    message,
                    initial_todos,
                    profile=profile,
                    context_note=context,
                    timeout_seconds=timeout,
                    token_budget=token_budget,
                    acceptance_criteria=acceptance,
                    tools=tools,
                    deliverable=deliverable,
                    output_file=output_file,
                    batch_id=batch_id,
                    item_identity=item.identity,
                )
                dispatch_results.append({"identity": item.identity, "status": "created", "subtask_id": subtask_id})
                if subtask_id:
                    created_ids.append(subtask_id)
            except SubtaskGranularityError as gran_err:
                _gdet = gran_err.details or {}
                try:  # C15：粒度熔断指标（fire-and-forget）
                    from dawei.agentic.subtask_metrics import get_metrics

                    get_metrics().record_granularity_rejected(str(_gdet.get("rule") or "unknown"))
                except Exception:  # noqa: BLE001 — 指标失败绝不影响主流程
                    pass
                dispatch_results.append(
                    {
                        "identity": item.identity,
                        "status": "error",
                        "error": "granularity_contract",
                        "rule": _gdet.get("rule"),
                        "evidence": _gdet.get("evidence"),
                        "hint": _gdet.get("hint"),
                    },
                )
            except DuplicateSubtaskError as dup_err:
                _det = dup_err.details or {}
                dispatch_results.append(
                    {
                        "identity": item.identity,
                        "status": "duplicate",
                        "existing_subtask_id": _det.get("existing_subtask_id"),
                        "hint": "Same goal already dispatched (same identity); wait for its report or reuse its result instead of re-dispatching.",
                    },
                )
            except Exception as e:  # noqa: BLE001 — 单项失败对 LLM 可见，不炸整批
                self.logger.exception(f"new_task_batch: item '{item.identity}' creation failed: ")
                dispatch_results.append({"identity": item.identity, "status": "error", "message": str(e)})

        _ok = len(created_ids)
        try:  # C15：批量派发指标（fire-and-forget，逐项结果分布）
            from dawei.agentic.subtask_metrics import get_metrics

            get_metrics().record_batch_dispatch(
                items=len(items),
                created=_ok,
                duplicate=sum(1 for r in dispatch_results if r.get("status") == "duplicate"),
                error=sum(1 for r in dispatch_results if r.get("status") == "error"),
            )
        except Exception:  # noqa: BLE001 — 指标失败绝不影响主流程
            pass
        self.logger.info(
            f"new_task_batch: batch {batch_id} dispatched {_ok}/{len(items)} items in {mode} mode",
        )
        return _json.dumps(
            {
                "type": "new_task_batch",
                "batch_id": batch_id,
                "mode": mode,
                "status": "dispatched" if _ok else "error",
                "created_count": _ok,
                "results": dispatch_results,
                "note": ("Items are ordinary parallel subtasks; reports are injected back when they finish. Duplicates were skipped (see results); errored items may be re-dispatched individually after fixing the reported reason."),
            },
            indent=2,
        )


# ==================== MessageTaskTool (P3-2 steer / P3-8 续跑) ====================


class MessageTaskInput(BaseModel):
    """Input for MessageTaskTool."""

    subtask_id: str = Field(..., description="Target subtask id (the task_node_id returned by new_task/run_task).")
    message: str = Field(
        ...,
        description="Steering instruction for the subtask. Must be self-contained: the subtask agent sees only this text as the new directive (plus its own conversation history).",
    )


class MessageTaskTool(CustomBaseTool):
    """向子任务发送中途指令（P3-2 steer / P3-8 续跑）。

    - RUNNING: 注入 [steer] UserMessage 到该子任务会话（下一轮 LLM 调用即见）
    - PENDING: 追加到任务描述（尚未起跑，无需会话注入）
    - COMPLETED: 续跑 —— 状态重置 PENDING + retry_count 清零，复用原会话（历史保留）并注入新指令
    - FAILED/ABORTED/根任务/未知 id: 拒绝（终态不可 steer，根任务走主对话）
    """

    name: ClassVar[str] = "message_task"
    description: ClassVar[str] = (
        "Sends a mid-flight steering message to a subtask created by new_task/run_task. "
        "RUNNING subtask: the message is injected into its conversation and takes effect on the next LLM round. "
        "PENDING subtask: appended to its description before it starts. "
        "COMPLETED subtask: resumes it with the new instruction (history preserved, retry counter reset). "
        "FAILED/ABORTED subtasks and the root task cannot be messaged via this tool."
    )
    args_schema: ClassVar[type[BaseModel]] = MessageTaskInput

    def __init__(self, task_graph=None, workspace_root: str | None = None):
        super().__init__()
        self.task_graph = task_graph
        self.workspace_root = workspace_root
        self.logger = get_logger(__name__)

    async def _run(self, subtask_id: str, message: str) -> str:
        import json as _json

        from dawei.entity.lm_messages import UserMessage
        from dawei.entity.task_types import TaskStatus

        def _err(msg: str) -> str:
            return _json.dumps({"status": "error", "subtask_id": subtask_id, "message": msg}, indent=2)

        task_graph = self._resolve_task_graph()
        if not task_graph:
            return _err("task_graph unavailable")

        node = await task_graph.get_task(subtask_id)
        if node is None:
            return _err("Subtask not found in graph")

        if getattr(node, "parent_id", None) is None:
            return _err("Refusing to message the root task; talk to the main conversation instead.")

        status = getattr(node, "status", None)
        data = getattr(node, "data", None)

        # 1) PENDING：尚未起跑 → 追加到描述（不改状态）
        if status == TaskStatus.PENDING:
            try:
                base = getattr(data, "description", "") or ""
                if not isinstance(base, str):
                    base = str(getattr(base, "content", base))
                data.description = f"{base}\n[steer] {message}"
            except Exception:  # noqa: BLE001 — 描述写失败对 LLM 可见即可
                self.logger.exception("message_task: failed to append steering message to description: ")
                return _err("Failed to append steering message to subtask description")
            await self._emit_steered(node, status="pending")
            return _json.dumps(
                {"status": "steered", "subtask_id": subtask_id, "delivery": "description", "message": message},
                indent=2,
            )

        # 2) RUNNING / COMPLETED：注入会话（COMPLETED 额外重置 PENDING + 清零重试计数 = 续跑）
        if status in (TaskStatus.RUNNING, TaskStatus.COMPLETED):
            conversation = self._resolve_conversation(subtask_id)
            if conversation is None:
                return _err(
                    f"No conversation available for subtask {subtask_id}; steering requires the subtask executor to be alive (isolation flag on) or a resumed conversation.",
                )
            conversation.say(UserMessage(content=f"[steer] {message}"))
            if status == TaskStatus.COMPLETED:
                # P2-D 续跑 = 原位重跑：统一经 reset_task_for_rerun（stash 旧 result 到
                # metadata.prev_* + 清空 + retry 清零 + 状态机 PENDING）。此前手动
                # COMPLETED→PENDING 一直被状态机拒绝（COMPLETED 曾锁终态），且不清
                # result 会让第二次执行的 result 被第一次残值吞掉（先到先得）。
                reset_ok = await task_graph.reset_task_for_rerun(
                    subtask_id,
                    reason=f"message_task resume: {message[:100]}",
                )
                if not reset_ok:
                    return _err("Failed to reset subtask for resume (rerun reset rejected); terminal state unchanged.")
                await self._emit_steered(node, status="pending", extra={"resumed": True})
                return _json.dumps(
                    {"status": "resumed", "subtask_id": subtask_id, "delivery": "conversation", "message": message},
                    indent=2,
                )
            await self._emit_steered(node, status="running")
            return _json.dumps(
                {"status": "steered", "subtask_id": subtask_id, "delivery": "conversation", "message": message},
                indent=2,
            )

        # 3) 终态：FAILED / ABORTED 等 → 拒绝
        return _err(f"Subtask is in terminal state '{getattr(status, 'value', status)}'; only RUNNING/PENDING/COMPLETED subtasks can be messaged (COMPLETED resumes).")

    def _resolve_conversation(self, subtask_id: str):
        """定位子任务会话：隔离会话优先，回落共享对话"""
        from dawei.agentic.subtask_conversation import select_result_conversation

        engine = self._resolve_execution_engine()
        return select_result_conversation(engine, subtask_id) if engine else None

    async def _emit_steered(self, node, status: str, extra: dict | None = None) -> None:
        """P3-6: steered 生命周期事件（fire-and-forget）"""
        try:
            from dawei.agentic.subtask_events import emit_subtask_lifecycle

            data = getattr(node, "data", None)
            await emit_subtask_lifecycle(
                "steered",
                task_node_id=getattr(node, "task_node_id", ""),
                parent_id=getattr(node, "parent_id", None),
                conversation_id=getattr(data, "conversation_id", None) if data is not None else None,
                status=status,
                extra=extra,
            )
        except Exception:  # noqa: BLE001 — 事件失败不影响主流程
            self.logger.exception("message_task: failed to emit subtask_steered event: ")


# Update Todo List Tool
class UpdateTodoListInput(BaseModel):
    """Input for UpdateTodoListTool."""

    todos: list[str] = Field(
        ...,
        description="List of todo items as an array of strings. Each item must include a status marker and description. "
        'Status markers: "[x]" for completed, "[-]" for in-progress, "[ ]" for pending. '
        'Format example: ["[x] Analyzed requirements", "[-] Implementing feature", "[ ] Write tests", "[ ] Update docs"]. '
        "IMPORTANT: This must be a valid JSON array of strings, not plain text. Each todo item should be a separate string element in the array.",
    )


class UpdateTodoListTool(CustomBaseTool):
    """Tool for updating todo list with task progress."""

    name: ClassVar[str] = "update_todo_list"
    description: ClassVar[str] = "Updates todo list with current task status and progress."
    args_schema: ClassVar[type[BaseModel]] = UpdateTodoListInput

    def __init__(self, task_graph=None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)

    def _run(self, todos: list[str]) -> str:
        """Update todo list with enhanced task management."""
        try:
            # 获取组件
            components = _import_task_graph_components()
            TodoItem = components["TodoItem"]
            TodoStatus = components["TodoStatus"]

            # 解析 TODO 列表
            parsed_todos = []
            for todo_str in todos:
                status = TodoStatus.PENDING
                content = todo_str.strip()

                if todo_str.startswith("[x] "):
                    status = TodoStatus.COMPLETED
                    content = todo_str[4:].strip()
                elif todo_str.startswith("[-] "):
                    status = TodoStatus.IN_PROGRESS
                    content = todo_str[4:].strip()
                elif todo_str.startswith("[ ] "):
                    status = TodoStatus.PENDING
                    content = todo_str[4:].strip()

                parsed_todos.append(TodoItem(content=content, status=status))

            # 统计信息
            pending = sum(1 for todo in parsed_todos if todo.status == TodoStatus.PENDING)
            completed = sum(1 for todo in parsed_todos if todo.status == TodoStatus.COMPLETED)
            in_progress = sum(1 for todo in parsed_todos if todo.status == TodoStatus.IN_PROGRESS)
            total = len(parsed_todos)

            result = {
                "type": "todo_update",
                "todos": todos,
                "summary": {
                    "total": total,
                    "pending": pending,
                    "completed": completed,
                    "in_progress": in_progress,
                    "completion_rate": f"{(completed / total * 100):.1f}%" if total > 0 else "0%",
                },
                "status": "updated",
                # 【2026-09-12】worker 线程无事件循环，get_event_loop().time() 必崩 → time.time()
                "updated_at": time.time(),
            }

            # 如果有 TaskGraph，更新 TODO 列表
            # 【2026-09-12】worker 线程无事件循环，asyncio.create_task 必崩 → 经主 loop 调度
            if self._resolve_task_graph():
                # C25：在 worker 线程内捕获子任务上下文（context 随 to_thread 复制
                # 到本线程，但 _schedule_on_main_loop 在主 loop 的独立 Task 中执行，
                # 不携带本线程 context）→ 必须显式传参。
                from dawei.agentic.subtask_events import get_current_subtask

                subtask_info = get_current_subtask()
                self._schedule_on_main_loop(self._update_todos(parsed_todos, subtask_info))

            self.logger.info(f"TODO list update requested: {total} items")

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.exception("Error updating todo list: ")
            return json.dumps(
                {"status": "error", "message": f"Error updating todo list: {e!s}"},
                indent=2,
            )

    async def _update_todos(self, todos, subtask_info: dict | None = None):
        """异步更新 TODO 列表（新架构）

        C25：subtask_info 非空（子任务上下文中调用）时，额外发射
        subtask_progress 步级事件（EventBus + WS 双通道，纯 UI 态）。
        """
        try:
            task_graph = self._resolve_task_graph()
            if not task_graph:
                return

            # 获取根任务
            root_task = await task_graph.get_root_task()
            if root_task:
                await task_graph.update_todos(root_task.task_id, todos)
                self.logger.info(
                    f"Updated TODO list for task {root_task.task_id}: {len(todos)} items",
                )

            # C25：子任务 todo 步级进度事件（去重后 fire-and-forget）
            if subtask_info and subtask_info.get("subtask_id"):
                from dawei.agentic.subtask_events import emit_subtask_progress

                await emit_subtask_progress(
                    subtask_id=subtask_info["subtask_id"],
                    parent_id=subtask_info.get("parent_id"),
                    batch_id=subtask_info.get("batch_id"),
                    item_identity=subtask_info.get("item_identity"),
                    todos=list(todos),
                )

        except (AttributeError, ValueError, KeyError) as e:
            self.logger.error(f"Failed to update TODO list: {e}", exc_info=True)
            raise  # Fast Fail: surface the error to caller


# Get Task Status Tool
class GetTaskStatusInput(BaseModel):
    """Input for GetTaskStatusTool."""

    task_id: str | None = Field(None, description="Task ID to get status for (optional).")
    include_subtasks: bool = Field(
        True,
        description="Include a compact per-subtask array (status/todos/result/tokens) for orchestration reads (default true).",
    )


class GetTaskStatusTool(CustomBaseTool):
    """Tool for getting current task status and progress."""

    name: ClassVar[str] = "get_task_status"
    description: ClassVar[str] = "Gets the current status of the task hierarchy and overall progress. Returns task graph structure, completion statistics, and status of all subtasks."
    args_schema: ClassVar[type[BaseModel]] = GetTaskStatusInput

    def __init__(self, task_graph=None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)

    def _run(self, task_id: str | None = None, include_subtasks: bool = True) -> str:
        """Get task status with enhanced task management."""
        try:
            if not self._resolve_task_graph():
                return json.dumps(
                    {
                        "status": "error",
                        "message": "Task graph not available. Task status tracking requires an active task graph.",
                    },
                    indent=2,
                )

            return run_async(self._get_real_status(task_id, include_subtasks))

        except Exception as e:
            self.logger.exception("Error getting task status: ")
            return json.dumps(
                {"status": "error", "message": f"Error getting task status: {e!s}"},
                indent=2,
            )

    async def _get_real_status(self, task_id: str | None = None, include_subtasks: bool = True) -> str:
        """获取真实任务状态（新架构）"""
        try:
            task_graph = self._resolve_task_graph()
            if not task_graph:
                return json.dumps({"status": "error", "message": "Task graph not available."}, indent=2)

            # 获取任务层级结构
            hierarchy = await task_graph.get_task_hierarchy()

            # 获取统计信息
            stats = await task_graph.get_statistics()

            # 构建结果
            result = {
                "type": "task_status",
                "task_graph_id": task_graph.task_node_id,
                "hierarchy": hierarchy,
                "statistics": stats,
                "requested_task_id": task_id,
            }

            # C11：紧凑子任务数组（编排者一眼判读"谁在跑/谁完了/花了多少"）。
            # hierarchy/statistics 键保持原样不动 —— 新增键纯增量，向后兼容。
            if include_subtasks:
                result["subtasks"] = await self._collect_subtask_briefs(task_graph)

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.exception("Failed to get real status: ")
            return json.dumps(
                {"status": "error", "message": f"Error getting task status: {e!s}"},
                indent=2,
            )

    async def _collect_subtask_briefs(self, task_graph) -> list[dict]:
        """C11：收集全部子任务节点的紧凑摘要

        每项：task_node_id/parent_id/status/description(≤80)/
        todos{total,completed}/result(≤120)/tokens_used，可选 batch_id/
        item_identity（new_task_batch 派发时写入 metadata）。读取失败降级
        空数组（查询语义，FAST FAIL 交给上层调用方判读）。
        """
        try:
            nodes = await task_graph.get_all_tasks()
        except Exception:  # noqa: BLE001 — 查询失败降级空数组
            self.logger.exception("Failed to collect subtask briefs: ")
            return []

        briefs: list[dict] = []
        for node in nodes:
            parent_id = getattr(node, "parent_id", None)
            if not parent_id:
                continue  # 根任务不在子任务列表
            data = getattr(node, "data", None)
            meta = dict(getattr(data, "metadata", None) or {})
            total = completed = 0
            try:
                todos = await task_graph.get_todos(node.task_node_id)
                total = len(todos)
                completed = sum(1 for t in todos if getattr(getattr(t, "status", None), "value", "") == "completed")
            except Exception:  # noqa: BLE001 — todos 读取失败只影响摘要字段
                pass
            brief = {
                "task_node_id": node.task_node_id,
                "parent_id": parent_id,
                "status": node.status.value if hasattr(node.status, "value") else str(node.status),
                "description": str(getattr(data, "description", "") or "")[:80],
                "todos": {"total": total, "completed": completed},
                "result": (str(getattr(data, "result", None) or "")[:120] or None),
                "tokens_used": getattr(data, "tokens_used", None),
            }
            if meta.get("batch_id"):
                brief["batch_id"] = str(meta["batch_id"])
            if meta.get("item_identity"):
                brief["item_identity"] = str(meta["item_identity"])[:40]
            briefs.append(brief)
        return briefs


# C11: Wait Tasks Tool —— 编排者阻塞等待一批子任务到达终态
class WaitTasksInput(BaseModel):
    """Input for WaitTasksTool."""

    task_ids: list[str] = Field(
        ...,
        min_length=1,
        description="Task node IDs to wait for (task_node_id values returned by new_task/new_task_batch).",
    )
    timeout_seconds: int = Field(
        45,
        ge=1,
        le=300,
        description="Max seconds to wait before returning current statuses with timed_out=true (default 45; keep below the tool-layer timeout).",
    )


class WaitTasksTool(CustomBaseTool):
    """Tool for waiting until a set of subtasks reach a terminal status."""

    name: ClassVar[str] = "wait_tasks"
    description: ClassVar[str] = (
        "Waits until all given subtasks reach a terminal status (completed/failed/aborted/cancelled), "
        "then returns each task's final status. Use for orchestration: dispatch subtasks via new_task/new_task_batch, "
        "then call this once to block until the batch finishes instead of polling get_task_status in a loop. "
        "On timeout it returns current statuses with timed_out=true (never raises)."
    )
    args_schema: ClassVar[type[BaseModel]] = WaitTasksInput

    def __init__(self, task_graph=None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)

    def _run(self, task_ids: list[str], timeout_seconds: int = 45) -> str:
        try:
            if not self._resolve_task_graph():
                return json.dumps({"status": "error", "message": "Task graph not available."}, indent=2)
            return run_async(self._wait_for_tasks(task_ids, timeout_seconds))
        except Exception as e:
            self.logger.exception("Error waiting for tasks: ")
            return json.dumps({"status": "error", "message": f"Error waiting for tasks: {e!s}"}, indent=2)

    async def _wait_for_tasks(self, task_ids: list[str], timeout_seconds: int) -> str:
        """轮询等待所有任务到达终态（terminal 集合与 TaskGraph._TERMINAL_STATUSES 对齐）"""
        import asyncio as _asyncio

        task_graph = self._resolve_task_graph()
        terminal = {"completed", "failed", "aborted", "cancelled"}
        deadline = time.monotonic() + timeout_seconds
        statuses: dict[str, str] = {}
        while True:
            statuses = {}
            for tid in task_ids:
                st = await task_graph.get_task_status(tid)
                statuses[tid] = st.value if st is not None else "unknown"
            all_terminal = all(s in terminal for s in statuses.values())
            if all_terminal or time.monotonic() >= deadline:
                return json.dumps(
                    {
                        "type": "wait_tasks",
                        "timed_out": not all_terminal,
                        "results": [{"task_id": tid, "status": statuses[tid], "terminal": statuses[tid] in terminal} for tid in task_ids],
                    },
                    indent=2,
                )
            await _asyncio.sleep(min(1.0, deadline - time.monotonic()))


# ==================== WorkflowToolFactory（已删除 2026-09-12） ====================
# 生产路径工具面由 ToolManager 反射扫描注册（tool_provider.py），
# 工厂仅为测试遗留且引用过时构造签名 —— 运行期 task_graph/engine 一律经
# CustomBaseTool._resolve_task_graph()/_resolve_execution_engine() 执行期解析。
