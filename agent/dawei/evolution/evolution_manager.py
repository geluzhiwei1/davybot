# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Evolution Cycle Manager

管理单个Evolution Cycle的PDCA执行，支持pause/resume/abort操作。

融合架构（详见 docs/design.md Section 15）：
- Evolution模块：调度 + 持久化 + 链式传递
- TaskGraph：任务跟踪 + 进度可视化 + WebSocket事件
- 内置Mode System：行为定义 + 工具权限（plan只读, do可编辑, check无edit）

每个evolution cycle创建一个TaskGraph（root + 4个phase子任务节点），
每个phase使用对应的内置mode（plan/do/check/act）而非全部orchestrator。
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from dawei.core.datetime_compat import UTC
from dawei.evolution.evolution_lock import EvolutionLock
from dawei.evolution.evolution_storage import EvolutionStorage
from dawei.evolution.exceptions import EvolutionError, EvolutionPhaseError, EvolutionStateError
from dawei.evolution.prompts import EvolutionPromptBuilder
from dawei.entity.task_types import TaskStatus

logger = logging.getLogger(__name__)

# Phase → built-in mode mapping
PHASE_MODE_MAP = {
    "plan": "plan",
    "do": "do",
    "check": "check",
    "act": "act",
}


class EvolutionCycleManager:
    """Evolution Cycle管理器

    负责管理单个workspace的evolution cycle执行，包括：
    - 启动新cycle（创建TaskGraph骨架）
    - 执行PDCA phases（plan → do → check → act），每个phase使用对应内置mode
    - 支持pause/resume/abort操作
    - Phase失败重试机制
    - Metadata状态管理
    - TaskGraph状态同步

    Attributes:
        workspace: UserWorkspace实例
        lock: EvolutionLock实例
        storage: EvolutionStorage实例
        _abort_event: asyncio.Event用于abort信号
        _task_graphs: cycle_id → TaskGraph映射

    """

    PHASES = ("plan", "do", "check", "act")
    MAX_RETRIES = 3

    def __init__(self, workspace):
        """初始化EvolutionCycleManager

        Args:
            workspace: UserWorkspace实例

        """
        from dawei.workspace.user_workspace import UserWorkspace

        if not isinstance(workspace, UserWorkspace):
            raise EvolutionError(f"workspace must be UserWorkspace, got {type(workspace)}")

        self.workspace = workspace
        self.lock = EvolutionLock(workspace)
        self.storage = EvolutionStorage(workspace)
        self._abort_event = asyncio.Event()
        self._task_graphs: dict[str, object] = {}

        logger.debug(f"[EVOLUTION_MANAGER] Initialized for workspace {workspace.workspace_id}")

    async def start_cycle(self) -> str:
        """启动新的evolution cycle

        此方法会立即返回cycle_id，实际PDCA执行在后台异步进行。
        启动时会创建TaskGraph骨架（root + 4个phase子任务节点）。

        Returns:
            str: 新创建的cycle_id

        Raises:
            EvolutionAlreadyRunningError: 当已有cycle在运行时

        """
        # 尝试获取锁（非阻塞）
        acquired = await self.lock.acquire()
        if not acquired:
            from dawei.evolution.exceptions import EvolutionAlreadyRunningError

            raise EvolutionAlreadyRunningError(f"Cannot start new cycle: evolution already running for workspace {self.workspace.workspace_id}")

        try:
            # 生成cycle_id
            cycle_id = await self._generate_cycle_id()

            # 创建cycle目录
            await self.storage.create_cycle_directory(cycle_id)

            # 获取上一个cycle ID
            prev_cycle_id = await self.storage.get_latest_completed_cycle_id()

            # 创建TaskGraph骨架（root + 4 phase子任务节点）
            task_graph = await self._create_cycle_task_graph(cycle_id, prev_cycle_id)
            self._task_graphs[cycle_id] = task_graph

            # 初始化metadata
            metadata = self._init_metadata(cycle_id, prev_cycle_id)
            metadata["context"]["task_graph_id"] = f"evolution-{cycle_id}"
            await self.storage.save_metadata(cycle_id, metadata)

            # 异步执行phases（不阻塞API响应）
            asyncio.create_task(self._run_phases(cycle_id, prev_cycle_id, task_graph), name=f"evolution-{cycle_id}")

            logger.info(f"[EVOLUTION_MANAGER] Started cycle {cycle_id} for workspace {self.workspace.workspace_id} (with TaskGraph)")

            return cycle_id

        except Exception as e:
            # 启动失败，释放锁
            await self.lock.release()
            logger.error(f"[EVOLUTION_MANAGER] Failed to start cycle: {e}", exc_info=True)
            raise EvolutionError(f"Failed to start evolution cycle: {e}") from e

    async def _create_cycle_task_graph(self, cycle_id: str, prev_cycle_id: str | None):
        """创建TaskGraph骨架：root + 4个phase子任务节点

        Args:
            cycle_id: 当前cycle ID
            prev_cycle_id: 上一个cycle ID（可选）

        Returns:
            TaskGraph实例

        """
        from dawei.task_graph import TaskGraph
        from dawei.task_graph.task_node_data import TaskData

        task_graph_id = f"evolution-{cycle_id}"

        # 获取或创建event_bus（TaskGraph requires non-None event_bus）
        event_bus = getattr(self.workspace, "event_bus", None)
        if event_bus is None:
            from dawei.core.events import SimpleEventBus

            event_bus = SimpleEventBus()
            logger.info(f"[EVOLUTION_MANAGER] Created own SimpleEventBus for TaskGraph {task_graph_id}")

        task_graph = TaskGraph(task_id=task_graph_id, event_bus=event_bus)

        # Use workspace context factory to ensure required IDs are populated
        root_context = self.workspace.create_task_context()
        root_context.metadata["evolution_cycle_id"] = cycle_id
        root_context.metadata["trigger_reason"] = "manual"

        # 创建root task
        root_data = TaskData(
            task_node_id=task_graph_id,
            description=f"Evolution Cycle {cycle_id}",
            mode="orchestrator",
            status=TaskStatus.RUNNING,
            context=root_context,
        )
        await task_graph.create_root_task(root_data)

        # 创建4个phase子任务节点
        for phase in self.PHASES:
            phase_node_id = f"evolution-{cycle_id}-{phase}"
            phase_context = self.workspace.create_task_context()
            phase_context.parent_context = root_data.context.to_dict()
            phase_context.metadata["evolution_cycle_id"] = cycle_id
            phase_context.metadata["phase"] = phase
            phase_data = TaskData(
                task_node_id=phase_node_id,
                description=f"Evolution {cycle_id} - {phase.upper()}",
                mode=PHASE_MODE_MAP[phase],  # plan/do/check/act
                status=TaskStatus.PENDING,
                context=phase_context,
            )
            await task_graph.create_subtask(parent_id=task_graph_id, task_data=phase_data)

        logger.info(f"[EVOLUTION_MANAGER] Created TaskGraph {task_graph_id} with 4 phase nodes")
        return task_graph

    async def _run_phases(self, cycle_id: str, prev_cycle_id: str | None, task_graph):
        """顺序执行四个PDCA phases

        每个phase使用对应的内置mode，并通过TaskGraph跟踪进度。

        Args:
            cycle_id: 当前cycle ID
            prev_cycle_id: 上一个cycle ID（可选）
            task_graph: TaskGraph实例

        """
        try:
            # 依次执行每个phase
            for phase in self.PHASES:
                # 检查abort信号
                if self._abort_event.is_set():
                    logger.info(f"[EVOLUTION_MANAGER] Abort signal received, stopping cycle {cycle_id}")
                    break

                # 检查是否被暂停（等待resume）
                await self._wait_if_paused(cycle_id)

                # 再次检查abort信号（可能在暂停期间被设置）
                if self._abort_event.is_set():
                    logger.info(f"[EVOLUTION_MANAGER] Abort signal received during pause, stopping cycle {cycle_id}")
                    break

                # 执行phase（带重试），使用对应内置mode
                await self._run_phase_with_retry(cycle_id, prev_cycle_id, phase, task_graph)

            else:
                # 所有phase成功完成
                await self._complete_cycle(cycle_id)
                # 标记TaskGraph root为完成
                await task_graph.update_task_status(f"evolution-{cycle_id}", TaskStatus.COMPLETED)
                return

            # 被abort退出循环
            await self._mark_aborted(cycle_id)
            # 标记TaskGraph root为中止
            await task_graph.update_task_status(f"evolution-{cycle_id}", TaskStatus.ABORTED)

        except Exception as e:
            logger.exception(f"[EVOLUTION_MANAGER] Cycle {cycle_id} failed: {e}")
            await self._mark_failed(cycle_id, str(e))
            try:
                await task_graph.update_task_status(f"evolution-{cycle_id}", TaskStatus.FAILED)
            except Exception:
                pass  # TaskGraph更新失败不影响主流程

        finally:
            # 释放锁
            await self.lock.release()
            # 清理TaskGraph引用
            self._task_graphs.pop(cycle_id, None)

    async def _run_phase_with_retry(self, cycle_id: str, prev_cycle_id: str | None, phase: str, task_graph):
        """执行单个phase，带重试机制

        Args:
            cycle_id: 当前cycle ID
            prev_cycle_id: 上一个cycle ID
            phase: Phase名称
            task_graph: TaskGraph实例

        Raises:
            EvolutionPhaseError: 当phase在所有重试后仍然失败时

        """
        for attempt in range(self.MAX_RETRIES):
            try:
                await self._execute_phase(cycle_id, prev_cycle_id, phase, task_graph)
                return  # 成功，退出重试循环

            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    # 还有重试机会
                    wait_time = 2**attempt  # 指数退避: 1s, 2s, 4s
                    logger.warning(f"[EVOLUTION_MANAGER] Phase {phase} attempt {attempt + 1}/{self.MAX_RETRIES} failed for cycle {cycle_id}: {e}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    # 最后一次重试也失败
                    logger.exception(f"[EVOLUTION_MANAGER] Phase {phase} failed after {self.MAX_RETRIES} attempts for cycle {cycle_id}: {e}")
                    raise EvolutionPhaseError(f"Phase {phase} failed after {self.MAX_RETRIES} attempts: {e}") from e

    async def _execute_phase(self, cycle_id: str, prev_cycle_id: str | None, phase: str, task_graph):
        """执行单个phase

        融合架构：
        1. 更新metadata + TaskGraph状态
        2. 加载phase输入文件
        3. 设置workspace mode为对应内置mode（plan/do/check/act）
        4. 注入evolution上下文（轻量，不替代内置mode的roleDefinition）
        5. 运行Agent（内置mode系统控制工具权限）
        6. 保存输出 + 更新TaskGraph + metadata

        Args:
            cycle_id: 当前cycle ID
            prev_cycle_id: 上一个cycle ID
            phase: Phase名称
            task_graph: TaskGraph实例

        """
        phase_node_id = f"evolution-{cycle_id}-{phase}"
        agent_mode = PHASE_MODE_MAP[phase]

        logger.info(f"[EVOLUTION_MANAGER] Executing phase {phase.upper()} for cycle {cycle_id} (mode={agent_mode})")

        # 1. 更新metadata + TaskGraph：phase in_progress
        await self._update_phase_status(cycle_id, phase, "in_progress")
        await task_graph.update_task_status(phase_node_id, TaskStatus.RUNNING)

        # 2. 加载phase输入文件
        inputs = await self._load_phase_inputs(cycle_id, prev_cycle_id, phase)

        # 3. 设置workspace mode为对应内置mode
        self.workspace.mode = agent_mode

        # 4. 构建evolution上下文（轻量注入，内置mode的roleDefinition处理行为定义）
        prompt_builder = EvolutionPromptBuilder()
        context = prompt_builder.build(phase, inputs, cycle_id, prev_cycle_id)

        # 5. 运行Agent（create_with_default_engine已经完成初始化）
        from dawei.agentic.agent import Agent
        from dawei.entity.user_input_message import UserInputText

        user_input = UserInputText(text=context)

        agent = await Agent.create_with_default_engine(self.workspace)
        await agent.process_message(user_input)

        # 6. 获取输出（从 conversation 中提取 assistant 的最后回复）
        output_content = ""
        if (
            hasattr(agent, "user_workspace")
            and hasattr(agent.user_workspace, "current_conversation")
            and agent.user_workspace.current_conversation
            and hasattr(agent.user_workspace.current_conversation, "messages")
        ):
            messages = agent.user_workspace.current_conversation.messages
            # 获取最后一条 assistant 消息的内容
            for msg in reversed(messages):
                if hasattr(msg, "role") and msg.role == "assistant":
                    if hasattr(msg, "content"):
                        output_content = msg.content
                    elif hasattr(msg, "text"):
                        output_content = msg.text
                    break

        # 如果没有找到内容，使用默认提示
        if not output_content:
            output_content = f"Phase {phase} completed. Check conversation history for details."

        await self.storage.save_phase_output(cycle_id, phase, output_content)
        await task_graph.update_task_status(phase_node_id, TaskStatus.COMPLETED)
        await self._update_phase_status(cycle_id, phase, "completed")

        # 7. 清理Agent（不清理workspace，workspace需要跨phase复用）
        try:
            # 清理agent内部资源，但保留workspace
            await agent.execution_engine.cleanup()
            task_graph = getattr(agent.execution_engine, "task_graph", None)
            if task_graph and hasattr(task_graph, "cleanup"):
                await task_graph.cleanup()
            agent._initialized = False
        except Exception:
            pass  # cleanup失败不影响主流程

        logger.info(f"[EVOLUTION_MANAGER] Phase {phase.upper()} completed for cycle {cycle_id} (mode={agent_mode})")

    async def pause_cycle(self, cycle_id: str):
        """请求暂停cycle（在当前phase结束后生效）

        Args:
            cycle_id: Cycle ID

        Raises:
            EvolutionStateError: 当cycle状态不允许暂停时

        """
        metadata = await self.storage.load_metadata(cycle_id)

        if metadata["status"] != "running":
            raise EvolutionStateError(f"Cannot pause cycle {cycle_id}: current status is {metadata['status']}, not 'running'")

        # 更新metadata状态
        metadata["status"] = "paused"
        metadata["paused_at"] = datetime.now(UTC).isoformat()
        metadata["context"]["pause_count"] = metadata["context"].get("pause_count", 0) + 1

        await self.storage.save_metadata(cycle_id, metadata)

        logger.info(f"[EVOLUTION_MANAGER] Cycle {cycle_id} pause requested (will take effect at phase boundary)")

    async def resume_cycle(self, cycle_id: str):
        """恢复暂停的cycle

        Args:
            cycle_id: Cycle ID

        Raises:
            EvolutionStateError: 当cycle状态不允许恢复时

        """
        metadata = await self.storage.load_metadata(cycle_id)

        if metadata["status"] != "paused":
            raise EvolutionStateError(f"Cannot resume cycle {cycle_id}: current status is {metadata['status']}, not 'paused'")

        # 更新metadata状态
        metadata["status"] = "running"
        metadata["context"]["resume_count"] = metadata["context"].get("resume_count", 0) + 1

        await self.storage.save_metadata(cycle_id, metadata)

        logger.info(f"[EVOLUTION_MANAGER] Cycle {cycle_id} resumed")

    async def abort_cycle(self, cycle_id: str, reason: str = ""):
        """中止cycle（在当前phase结束后或下次phase边界生效）

        Args:
            cycle_id: Cycle ID
            reason: 中止原因（可选）

        Raises:
            EvolutionStateError: 当cycle状态不允许中止时

        """
        metadata = await self.storage.load_metadata(cycle_id)

        if metadata["status"] not in ("running", "paused"):
            raise EvolutionStateError(f"Cannot abort cycle {cycle_id}: current status is {metadata['status']}")

        # 设置abort事件
        self._abort_event.set()

        logger.info(f"[EVOLUTION_MANAGER] Abort signal set for cycle {cycle_id}" + (f": {reason}" if reason else ""))

    def get_task_graph(self, cycle_id: str):
        """获取cycle关联的TaskGraph

        Args:
            cycle_id: Cycle ID

        Returns:
            TaskGraph实例或None

        """
        return self._task_graphs.get(cycle_id)

    async def _wait_if_paused(self, cycle_id: str):
        """在phase边界等待，直到resume或abort

        Args:
            cycle_id: Cycle ID

        """
        while True:
            metadata = await self.storage.load_metadata(cycle_id)

            # 检查是否被暂停
            if metadata["status"] != "paused":
                return

            # 检查abort信号
            if self._abort_event.is_set():
                return

            # 等待2秒后重新检查
            await asyncio.sleep(2)

    async def _load_phase_inputs(self, cycle_id: str, prev_cycle_id: str | None, phase: str) -> dict:
        """加载phase输入文件

        Args:
            cycle_id: 当前cycle ID
            prev_cycle_id: 上一个cycle ID
            phase: Phase名称

        Returns:
            dict: 输入数据字典

        """
        workspace_md = await self.storage.load_workspace_md()
        prev_action = ""
        if prev_cycle_id:
            prev_action = await self.storage.load_phase_output(prev_cycle_id, "action")

        inputs = {"workspace_md": workspace_md, "prev_action": prev_action, "prev_cycle_id": prev_cycle_id}

        if phase == "plan":
            # PLAN phase inputs: dao.md + prev/action.md
            pass  # inputs已经包含所需数据

        elif phase == "do":
            # DO phase inputs: plan.md
            plan = await self.storage.load_phase_output(cycle_id, "plan")
            inputs["plan"] = plan

        elif phase == "check":
            # CHECK phase inputs: dao.md + prev/action.md + plan.md + do.md
            plan = await self.storage.load_phase_output(cycle_id, "plan")
            do = await self.storage.load_phase_output(cycle_id, "do")
            inputs.update({"plan": plan, "do": do})

        elif phase == "act":
            # ACT phase inputs: dao.md + plan.md + do.md + check.md
            plan = await self.storage.load_phase_output(cycle_id, "plan")
            do = await self.storage.load_phase_output(cycle_id, "do")
            check = await self.storage.load_phase_output(cycle_id, "check")
            inputs.update({"plan": plan, "do": do, "check": check})

        return inputs

    async def _update_phase_status(self, cycle_id: str, phase: str, status: str, conversation_id: str | None = None):
        """更新metadata中phase的状态

        Args:
            cycle_id: Cycle ID
            phase: Phase名称
            status: 状态（in_progress, completed）
            conversation_id: Conversation ID（可选）

        """
        metadata = await self.storage.load_metadata(cycle_id)

        now = datetime.now(UTC).isoformat()

        if status == "in_progress":
            metadata["current_phase"] = phase
            metadata["phases"][phase]["status"] = "in_progress"
            metadata["phases"][phase]["started_at"] = now
        elif status == "completed":
            metadata["phases"][phase]["status"] = "completed"
            metadata["phases"][phase]["completed_at"] = now
            if conversation_id:
                metadata["phases"][phase]["conversation_id"] = conversation_id

        await self.storage.save_metadata(cycle_id, metadata)

    async def _complete_cycle(self, cycle_id: str):
        """标记cycle为完成

        Args:
            cycle_id: Cycle ID

        """
        metadata = await self.storage.load_metadata(cycle_id)

        metadata["status"] = "completed"
        metadata["completed_at"] = datetime.now(UTC).isoformat()
        metadata["current_phase"] = None

        await self.storage.save_metadata(cycle_id, metadata)

        logger.info(f"[EVOLUTION_MANAGER] Cycle {cycle_id} completed successfully")

    async def _mark_aborted(self, cycle_id: str):
        """标记cycle为已中止

        Args:
            cycle_id: Cycle ID

        """
        metadata = await self.storage.load_metadata(cycle_id)

        metadata["status"] = "aborted"
        metadata["aborted_at"] = datetime.now(UTC).isoformat()
        metadata["current_phase"] = None

        await self.storage.save_metadata(cycle_id, metadata)

        logger.info(f"[EVOLUTION_MANAGER] Cycle {cycle_id} aborted")

    async def _mark_failed(self, cycle_id: str, error_message: str):
        """标记cycle为失败

        Args:
            cycle_id: Cycle ID
            error_message: 错误信息

        """
        metadata = await self.storage.load_metadata(cycle_id)

        metadata["status"] = "failed"
        metadata["completed_at"] = datetime.now(UTC).isoformat()
        metadata["current_phase"] = None
        metadata["abort_reason"] = error_message

        await self.storage.save_metadata(cycle_id, metadata)

        logger.error(f"[EVOLUTION_MANAGER] Cycle {cycle_id} failed: {error_message}")

    def _init_metadata(self, cycle_id: str, prev_cycle_id: str | None) -> dict:
        """初始化cycle metadata

        Args:
            cycle_id: Cycle ID
            prev_cycle_id: 上一个cycle ID

        Returns:
            dict: 初始化的metadata

        """
        now = datetime.now(UTC).isoformat()

        return {
            "cycle_id": cycle_id,
            "workspace_id": self.workspace.workspace_id,
            "status": "running",
            "current_phase": None,
            "started_at": now,
            "completed_at": None,
            "paused_at": None,
            "aborted_at": None,
            "abort_reason": None,
            "phases": {
                "plan": {
                    "status": "pending",
                    "conversation_id": None,
                    "started_at": None,
                    "completed_at": None,
                    "output_file": "plan.md",
                },
                "do": {
                    "status": "pending",
                    "conversation_id": None,
                    "started_at": None,
                    "completed_at": None,
                    "output_file": "do.md",
                },
                "check": {
                    "status": "pending",
                    "conversation_id": None,
                    "started_at": None,
                    "completed_at": None,
                    "output_file": "check.md",
                },
                "act": {
                    "status": "pending",
                    "conversation_id": None,
                    "started_at": None,
                    "completed_at": None,
                    "output_file": "action.md",
                },
            },
            "context": {
                "previous_cycle_id": prev_cycle_id,
                "trigger_reason": "manual",
                "goals": [],
                "pause_count": 0,
                "resume_count": 0,
            },
        }

    async def _generate_cycle_id(self) -> str:
        """生成新的cycle ID

        Returns:
            str: 格式为 "001", "002", ... 的cycle ID

        """
        # 获取所有已有的cycles
        cycles = await self.storage.get_all_cycles()

        if not cycles:
            return "001"

        # 从最后一个cycle ID递增
        last_cycle_id = cycles[-1].get("cycle_id", "000")
        try:
            last_num = int(last_cycle_id)
            new_num = last_num + 1
            return f"{new_num:03d}"
        except (ValueError, TypeError):
            # 如果无法解析，使用当前cycle数量+1
            return f"{len(cycles) + 1:03d}"
