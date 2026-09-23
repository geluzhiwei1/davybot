# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""任务图核心管理类
新架构中的核心组件，协调各个管理器
"""

import asyncio
import uuid
from datetime import datetime, timezone
from dawei.core.datetime_compat import UTC
from typing import List, Dict, Any

from dawei.agentic.errors import (
    StateTransitionError,
    SubtaskBreadthLimitExceededError,
    TaskExecutionError,
    TaskNotFoundError,
    ValidationError,
)
from dawei.core.error_handler import handle_errors
from dawei.entity.task_types import TaskStatus, TaskSummary
from dawei.logg.logging import get_logger, log_performance

from .task_node import TaskNode
from .task_node_data import TaskContext, TaskData, TaskPriority
from .task_validator import TaskValidator
from .todo_models import TodoItem


# 延迟导入以避免循环导入
def get_emit_typed_event():
    """获取 emit_typed_event 函数的延迟导入"""
    from dawei.core.events import emit_typed_event

    return emit_typed_event


def get_TaskStartedEvent():
    """获取 TaskEventType 的延迟导入"""
    from dawei.core.events import TaskEventType

    return TaskEventType.TASK_STARTED


def get_TaskCompletedEvent():
    """获取 TaskEventType 的延迟导入"""
    from dawei.core.events import TaskEventType

    return TaskEventType.TASK_COMPLETED


def get_CheckpointCreatedEvent():
    """获取 TaskEventType 的延迟导入"""
    from dawei.core.events import TaskEventType

    return TaskEventType.CHECKPOINT_CREATED


def get_CheckpointRestoredEvent():
    """获取 TaskEventType 的延迟导入"""
    from dawei.core.events import TaskEventType

    return TaskEventType.CHECKPOINT_RESTORED


class TaskGraph:
    """任务图核心管理类"""

    def __init__(self, task_id: str, event_bus=None, workspace_id: str | None = None):
        # 验证输入
        if not task_id or not task_id.strip():
            raise ValidationError("task_id", task_id, "must be non-empty string")

        self.task_node_id = task_id
        self.workspace_id: str | None = workspace_id  # 用于 broadcast 按 workspace 过滤
        self.logger = get_logger(__name__)

        self._event_bus = event_bus

        # 核心组件
        self._root_node: TaskNode | None = None
        self._nodes: Dict[str, TaskNode] = {}
        # 延迟导入管理器以避免循环导入
        from .managers import ContextStore, StateManager, TodoManager

        # 现在可以安全地访问 self.event_bus (property getter)
        self._todo_manager = TodoManager(event_bus=self.event_bus)
        self._state_manager = StateManager(event_bus=self.event_bus)
        self._context_store = ContextStore()
        self._validator = TaskValidator()

        # 锁
        self._lock = asyncio.Lock()

        # 🔧 修复内存泄漏：追踪事件处理器ID以便后续清理
        self._handler_ids: List[str] = []

        if self._event_bus is None:
            raise ValueError("event_bus is required for TaskGraph initialization")

        self._setup_event_listeners()

    @property
    def event_bus(self):
        """获取 event_bus"""
        return self._event_bus

    @event_bus.setter
    def event_bus(self, value):
        """设置 event_bus，同时更新 managers 的 event_bus"""
        self._event_bus = value

        # 更新 managers 的 event_bus
        if hasattr(self, "_todo_manager") and self._todo_manager is not None:
            self._todo_manager.event_bus = value
        if hasattr(self, "_state_manager") and self._state_manager is not None:
            self._state_manager.event_bus = value

    def _setup_event_listeners(self):
        """设置事件监听器（纯强类型）"""
        from dawei.core.events import TaskEventType

        # 监听状态变化事件，并追踪handler ID以便清理
        # 🔧 修复：保存handler ID以便后续清理
        handler_id = self.event_bus.add_handler(TaskEventType.STATE_CHANGED, self._on_status_changed)
        self._handler_ids.append((TaskEventType.STATE_CHANGED, handler_id))

        handler_id = self.event_bus.add_handler(TaskEventType.TODOS_UPDATED, self._on_todos_updated)
        self._handler_ids.append((TaskEventType.TODOS_UPDATED, handler_id))

        handler_id = self.event_bus.add_handler(TaskEventType.CONTEXT_UPDATED, self._on_context_updated)
        self._handler_ids.append((TaskEventType.CONTEXT_UPDATED, handler_id))

        self.logger.debug(f"Registered {len(self._handler_ids)} event handlers for TaskGraph {self.task_node_id}")

    async def _on_status_changed(self, event: Any):
        """状态变化事件处理"""
        # 处理强类型事件数据
        data = event.data.get_event_data() if hasattr(event, "data") and hasattr(event.data, "get_event_data") else event.data if hasattr(event, "data") else {}

        task_id = data.get("task_id")
        new_status = data.get("new_state")

        if task_id in self._nodes:
            node = self._nodes[task_id]
            if new_status:  # Only update if new_status is not None
                old_status = node.status
                node.update_status(TaskStatus(new_status))
                self.logger.info(f"Updated node {task_id} status to {new_status}")

                # ✅ 自动更新关联的 TODO
                await self._auto_update_todos(
                    task_id=task_id,
                    _old_status=old_status,
                    new_status=TaskStatus(new_status),
                )

    def _map_task_status_to_todo_status(self, task_status: TaskStatus):
        """映射 TaskNode 状态到 TODO 状态

        Args:
            task_status: TaskNode 状态

        Returns:
            TodoStatus: 对应的 TODO 状态

        """
        from .todo_models import TodoStatus

        mapping = {
            TaskStatus.PENDING: TodoStatus.PENDING,
            TaskStatus.RUNNING: TodoStatus.IN_PROGRESS,
            TaskStatus.COMPLETED: TodoStatus.COMPLETED,
            TaskStatus.FAILED: TodoStatus.PENDING,  # 失败后可以重试
            TaskStatus.ABORTED: TodoStatus.PENDING,  # 中止后可以重试
            TaskStatus.PAUSED: TodoStatus.PENDING,
        }
        return mapping.get(task_status, TodoStatus.PENDING)

    async def _auto_update_todos(
        self,
        task_id: str,
        _old_status: TaskStatus,
        new_status: TaskStatus,
    ):
        """自动更新 TODO 状态

        当 TaskNode 状态变更时，自动更新关联的 TODO 状态。

        Args:
            task_id: 任务 ID
            old_status: 旧状态
            new_status: 新状态

        """
        try:
            # 1. 查找关联的 TODO
            todos = await self._todo_manager.get_todos(task_id)
            matching_todos = [todo for todo in todos if todo.task_node_id == task_id and todo.auto_update]

            if not matching_todos:
                self.logger.debug(f"No auto-update TODO found for task {task_id}")
                return

            # 2. 根据 TaskNode 状态映射 TODO 状态
            todo_status = self._map_task_status_to_todo_status(new_status)

            # 3. 更新所有匹配的 TODO
            for todo in matching_todos:
                old_todo_status = todo.status
                await self._todo_manager.update_todo_status(
                    task_id=task_id,
                    todo_id=todo.id,
                    new_status=todo_status,
                    source="system_auto",
                    auto_progress=False,  # 避免循环触发
                )

                self.logger.info(
                    f"Auto-updated TODO '{todo.content}' for task {task_id}: {old_todo_status.value} → {todo_status.value}",
                )

        except Exception as e:
            # Event callback: don't let auto-update failure stop the event loop
            # This is intentional degradation
            self.logger.error(f"Failed to auto-update todos for task {task_id}: {e}", exc_info=True)

    async def _on_todos_updated(self, event: Any):
        """TODO更新事件处理"""
        # 处理强类型事件数据
        data = event.data.get_event_data() if hasattr(event, "data") and hasattr(event.data, "get_event_data") else event.data if hasattr(event, "data") else {}

        task_id = data.get("task_id")
        todos = data.get("new_todos", [])

        if task_id in self._nodes:
            node = self._nodes[task_id]
            # 转换TODO数据
            todo_items = [TodoItem.from_dict(todo_data) for todo_data in todos]
            node.update_data(todos=todo_items)
            self.logger.info(f"Updated node {task_id} todos: {len(todo_items)} items")

    async def _on_context_updated(self, event_data: Dict[str, Any]):
        """上下文更新事件处理"""
        task_id = event_data.get("task_id")

        if task_id in self._nodes:
            # 上下文更新会通过ContextStore处理
            self.logger.debug(f"Context updated for task {task_id}")

    # ==================== 资源清理 ====================

    def cleanup(self):
        """清理事件处理器，防止内存泄漏

        在TaskGraph不再使用时应调用此方法，从事件总线中移除所有已注册的处理器。

        ⚠️ 重要：此方法必须手动调用，否则会导致内存泄漏！
        """
        if not hasattr(self, "_handler_ids") or not self._handler_ids:
            return

        from dawei.core.events import TaskEventType

        removed_count = 0
        failed_count = 0

        # 反向遍历，安全移除
        for event_type, handler_id in reversed(self._handler_ids):
            try:
                success = self.event_bus.remove_handler(event_type, handler_id)
                if success:
                    removed_count += 1
                else:
                    failed_count += 1
                    self.logger.warning(f"Failed to remove handler {handler_id} for {event_type.value}")
            except Exception as e:
                failed_count += 1
                self.logger.error(f"Error removing handler {handler_id}: {e}", exc_info=True)

        # 清空追踪列表
        self._handler_ids.clear()

        self.logger.info(f"Cleaned up {removed_count} event handlers for TaskGraph {self.task_node_id}" + (f" ({failed_count} failed)" if failed_count > 0 else ""))

    def __del__(self):
        """析构函数 - 作为最后防线尝试清理处理器

        ⚠️ 注意：不要依赖此方法进行清理，应该显式调用 cleanup()
        因为：
        1. Python不保证__del__何时被调用
        2. 循环引用可能阻止对象被垃圾回收
        3. 在__del__中访问self.event_bus可能不安全
        """
        try:
            if hasattr(self, "_handler_ids") and self._handler_ids and hasattr(self, "logger"):
                self.logger.warning(f"TaskGraph {self.task_node_id} is being garbage collected without explicit cleanup(). This may indicate a memory leak. Consider calling cleanup() when the TaskGraph is no longer needed.")
                # 尝试清理，但不保证成功
                # self.cleanup()  # 注释掉，因为在__del__中访问event_bus可能不安全
        except Exception:
            # 在__del__中忽略所有错误，避免程序崩溃
            pass

    # ==================== 任务节点管理 ====================

    @handle_errors(component="task_graph", operation="create_root_task")
    @log_performance("task_graph.create_root_task")
    async def create_root_task(self, task_data: TaskData) -> TaskNode:
        """创建根任务"""
        async with self._lock:
            # 验证任务数据 - 直接抛出异常而不是记录错误
            validation_result = self._validator.validate_task_data(task_data)
            if not validation_result.is_valid:
                raise ValidationError(
                    "task_data",
                    str(task_data),
                    f"Validation failed: {validation_result.errors}",
                )

            # 创建根节点
            # 注意：显式传递 todos 等参数，避免依赖 **kwargs
            root_node = TaskNode.create_root(
                task_node_id=task_data.task_node_id,
                description=task_data.description,
                mode=task_data.mode,
                status=task_data.status,
                priority=task_data.priority,
                context=task_data.context,
                todos=task_data.todos,
                metadata=task_data.metadata,
            )

            self._root_node = root_node
            self._nodes[task_data.task_node_id] = root_node

            # 初始化各个管理器
            await self._state_manager.update_status(
                task_data.task_node_id,
                task_data.status,
                "Root task created",
            )
            # 注意：不启用 auto_progress，TODO 由 TaskNode 状态变化自动更新
            await self._todo_manager.update_todos(
                task_data.task_node_id,
                task_data.todos,
                auto_progress=False,
            )
            await self._context_store.update_context(task_data.task_node_id, task_data.context)

        # 🔥 修复（2026-09-17 new_task 60s 超时事故）：事件必须在图谱锁外发送。
        # 事件总线会内联 await 全部 handler；生产环境的 TASK_GRAPH_UPDATED handler
        # （chat.py 即时持久化 → save_task_graph → get_all_tasks）需要重新获取图谱锁，
        # 与"持锁 emit"形成循环等待 → 死锁。参照 Claude Code 子任务模式：发射路径必须廉价且无死锁。
        from dawei.core.events import TaskEventType

        emit_typed_event = get_emit_typed_event()
        await emit_typed_event(
            TaskEventType.TASK_STARTED,  # event_type
            {  # data
                "task_name": task_data.task_node_id,
                "task_description": task_data.description,
                "mode": task_data.mode,
                "type": "root_task",
            },
            self.event_bus,  # 🔧 修复：添加 event_bus 参数
            task_id=task_data.task_node_id,
            source="task_graph",
        )

        # 🔥 新增：发送 TaskGraph 创建事件，触发持久化
        await emit_typed_event(
            TaskEventType.TASK_GRAPH_CREATED,  # positional event_type
            {  # positional data
                "task_graph_id": self.task_node_id,
                "root_task_id": task_data.task_node_id,
                "mode": task_data.mode,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            self.event_bus,  # positional event_bus
            task_id=self.task_node_id,
            source="task_graph_persistence",
        )

        self.logger.info(
            f"Root task created - task_id: {task_data.task_node_id}, mode: {task_data.mode}",
        )

        return root_node

    @handle_errors(component="task_graph", operation="create_subtask")
    @log_performance("task_graph.create_subtask")
    async def create_subtask(self, parent_id: str, task_data: TaskData) -> TaskNode:
        """创建子任务"""
        async with self._lock:
            # 验证父任务存在 - 直接抛出异常
            if parent_id not in self._nodes:
                raise TaskNotFoundError(parent_id)

            # 验证任务数据 - 直接抛出异常
            validation_result = self._validator.validate_task_data(task_data)
            if not validation_result.is_valid:
                raise ValidationError(
                    "task_data",
                    str(task_data),
                    f"Validation failed: {validation_result.errors}",
                )

            # 自主执行策略（域9）：限制子任务嵌套深度（沿父链向上计数）。
            # 策略读取异常被吞（放行），不破坏既有子任务创建流程。
            try:
                from dawei.core.security_manager import security_manager

                max_depth = security_manager.get_policy().autonomy.max_subtask_depth
                parent_depth = 0
                ancestor_id = parent_id
                while ancestor_id and ancestor_id in self._nodes:
                    parent_depth += 1
                    ancestor_id = getattr(self._nodes[ancestor_id], "parent_id", None)
                if parent_depth + 1 > max_depth:  # 新子节点深度将超限
                    try:
                        from dawei.core.security_auditor import security_auditor

                        security_auditor.log(
                            "security.autonomy.denied",
                            reason="max_subtask_depth",
                            depth=parent_depth + 1,
                            max=max_depth,
                            parent_id=parent_id,
                        )
                    except Exception:
                        pass
                    raise PermissionError(
                        f"Subtask depth {parent_depth + 1} exceeds max_subtask_depth {max_depth}"
                    )
            except PermissionError:
                raise
            except Exception as e:
                self.logger.warning(f"Autonomy depth check failed: {e}; allowing")

            # P1b ⑦ 广度上限（2026-09-17 补全）：同父活跃（非终态，含 interactive——
            # 追问等待同样占用"在飞"名额，漏计会旁路闸门）子任务数 ≤
            # agent_execution.max_active_subtasks。结构不变量，锁内原子判定：
            # 工具层预检只是友好 fast-path，批量并行派发的并发竞态（检查与挂接
            # 之间让出锁）由此处兜底。
            # C9（2026-09-23）batch 合法形态放行：new_task_batch 展开的节点带
            # metadata.batch_id —— 正确的批量并行不该被广度闸惩罚（token 防线
            # 已移到每子任务预算 + dispatch_identity 去重），单次硬顶由工具层
            # R5 max_batch_items（默认 16）把守。
            parent_node = self._nodes[parent_id]
            _is_batch_item = bool((getattr(task_data, "metadata", None) or {}).get("batch_id"))
            try:
                from dawei.config.settings import get_settings

                max_active = int(get_settings().agent_execution.max_active_subtasks)
            except Exception:  # noqa: BLE001 — 配置不可用退回保守默认，不阻断主流程
                max_active = 3
            _BREADTH_ACTIVE = {
                TaskStatus.PENDING,
                TaskStatus.RUNNING,
                TaskStatus.WAITING_FOR_TOOL,
                TaskStatus.PAUSED,
                TaskStatus.INTERACTIVE,
            }
            active_ids = [
                cid
                for cid in (parent_node.child_ids or [])
                if cid in self._nodes and self._nodes[cid].status in _BREADTH_ACTIVE
            ]
            if len(active_ids) >= max_active and not _is_batch_item:
                try:
                    from dawei.agentic.subtask_metrics import get_metrics

                    get_metrics().record_breadth_rejected()
                except Exception:  # noqa: BLE001 — 埋点失败不影响拒绝路径
                    pass
                raise SubtaskBreadthLimitExceededError(parent_id, active_ids, max_active)

            # §8 重派率埋点：同父已终结子节点存在同目标（strip 精确匹配，零误报——
            # 阈值 <1% 的度量不能用宽松匹配）→ 计一次同参数重派，标签=前次终态
            # （CANCELLED 即违反不变量 6"禁止同目标重派"的直接证据）。
            # 只计数不阻断：合法重做（用户明确要求）与违规重派的判别是提示词层职责。
            try:
                goal = str(task_data.description or "").strip()
                if goal:
                    _TERMINAL_BREADTH = {
                        TaskStatus.COMPLETED,
                        TaskStatus.FAILED,
                        TaskStatus.ABORTED,
                        TaskStatus.CANCELLED,
                    }
                    for cid in parent_node.child_ids or []:
                        sibling = self._nodes.get(cid)
                        if sibling is None or sibling.status not in _TERMINAL_BREADTH:
                            continue
                        if str(getattr(sibling.data, "description", "") or "").strip() == goal:
                            from dawei.agentic.subtask_metrics import get_metrics

                            get_metrics().record_redispatch(sibling.status.value)
                            break
            except Exception:  # noqa: BLE001 — 埋点失败不影响创建
                pass

            # 创建子节点
            # 注意：显式传递 todos 等参数，避免依赖 **kwargs
            child_node = TaskNode.create_child(
                task_node_id=task_data.task_node_id,
                description=task_data.description,
                mode=task_data.mode,
                parent_id=parent_id,
                status=task_data.status,
                priority=task_data.priority,
                context=task_data.context,
                todos=task_data.todos,
                metadata=task_data.metadata,
            )

            self._nodes[task_data.task_node_id] = child_node

            # 更新父节点的子节点列表（parent_node 已在广度闸块取到）
            parent_node.add_child(task_data.task_node_id)

            # §8 创建计数（重派率分母）
            try:
                from dawei.agentic.subtask_metrics import get_metrics

                get_metrics().record_creation()
            except Exception:  # noqa: BLE001 — 埋点失败不影响创建
                pass

            # 继承父任务上下文
            await self._context_store.inherit_context(parent_id, task_data.task_node_id)

            # 初始化各个管理器
            await self._state_manager.update_status(
                task_data.task_node_id,
                task_data.status,
                f"Subtask created under {parent_id}",
            )
            # 注意：不启用 auto_progress，TODO 由 TaskNode 状态变化自动更新
            await self._todo_manager.update_todos(
                task_data.task_node_id,
                task_data.todos,
                auto_progress=False,
            )
            await self._context_store.update_context(task_data.task_node_id, task_data.context)

        # 🔥 修复（2026-09-17 new_task 60s 超时事故）：事件必须在图谱锁外发送。
        # 事件总线内联 await 全部 handler；生产 TASK_GRAPH_UPDATED handler
        # （chat.py:2490 → user_workspace.save_task_graph → get_all_tasks）
        # 会重新获取图谱锁 → 循环等待 → 死锁（工具层 60s 强杀，子任务"疑似超时"实则已建）。
        from dawei.core.events import TaskEventType

        emit_typed_event = get_emit_typed_event()
        await emit_typed_event(
            TaskEventType.TASK_STARTED,  # positional event_type
            {  # positional data
                "task_name": task_data.task_node_id,
                "task_description": task_data.description,
                "mode": task_data.mode,
                "type": "subtask",
                "parent_id": parent_id,
            },
            self.event_bus,  # positional event_bus
            task_id=task_data.task_node_id,
            source="task_graph",
        )

        # 🔥 新增：发送 TaskGraph 更新事件，触发持久化
        await emit_typed_event(
            TaskEventType.TASK_GRAPH_UPDATED,  # positional event_type
            {  # positional data
                "task_graph_id": self.task_node_id,
                "added_node_id": task_data.task_node_id,
                "parent_id": parent_id,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            self.event_bus,  # positional event_bus
            task_id=self.task_node_id,
            source="task_graph_persistence",
        )

        # C12：task_graph_update(node_added) 广播（新前端 task-store.applyGraphUpdate
        # 数据源；data 契约 = {task_id, status, ...节点属性}）
        from dawei.websocket.protocol import TaskGraphUpdateMessage

        await self._ws_broadcast(
            TaskGraphUpdateMessage(
                session_id="",
                graph_id=self.task_node_id,
                update_type="node_added",
                data={
                    "task_id": task_data.task_node_id,
                    "status": task_data.status.value if hasattr(task_data.status, "value") else str(task_data.status),
                    "parent_id": parent_id,
                    "description": str(task_data.description or "")[:200],
                    "mode": task_data.mode,
                },
            ),
        )

        self.logger.info(
            f"Subtask created - task_id: {task_data.task_node_id}, parent_id: {parent_id}, mode: {task_data.mode}",
        )

        return child_node

    async def get_task(self, task_id: str) -> TaskNode | None:
        """获取任务节点"""
        try:
            async with self._lock:
                return self._nodes.get(task_id)
        except Exception as e:
            # Query operation: return None on error (intentional degradation)
            # This allows caller to handle missing tasks gracefully
            self.logger.error(f"Failed to get task {task_id}: {e}", exc_info=True)
            return None

    async def get_root_task(self) -> TaskNode | None:
        """获取根任务"""
        try:
            async with self._lock:
                return self._root_node
        except Exception as e:
            # Query operation: return None on error (intentional degradation)
            self.logger.error(f"Failed to get root task: {e}", exc_info=True)
            return None

    async def get_subtasks(self, parent_id: str) -> List[TaskNode]:
        """获取子任务列表"""
        try:
            async with self._lock:
                parent_node = self._nodes.get(parent_id)
                if not parent_node:
                    return []

                subtasks = []
                for child_id in parent_node.child_ids:
                    if child_id in self._nodes:
                        subtasks.append(self._nodes[child_id])

                return subtasks
        except Exception as e:
            self.logger.error(f"Failed to get subtasks for {parent_id}: {e}", exc_info=True)
            return []

    async def get_all_tasks(self) -> List[TaskNode]:
        """获取所有任务节点"""
        try:
            async with self._lock:
                return list(self._nodes.values())
        except Exception as e:
            self.logger.error(f"Failed to get all tasks: {e}", exc_info=True)
            return []

    # ==================== 任务操作 ====================

    async def _ws_broadcast(self, msg) -> None:
        """C12：WS 广播辅助（fire-and-forget，异常吞掉只记日志）

        TUI 模式 websocket_server 为 None → 跳过；workspace_id 缺失时由
        broadcast 层按会话路由。
        """
        try:
            from dawei.websocket.ws_server import websocket_server

            if websocket_server is None:
                return
            await websocket_server.websocket_manager.broadcast(msg, workspace_id=self.workspace_id)
        except Exception as e:  # noqa: BLE001 — 广播失败不影响图谱主流程
            self.logger.warning(f"WS broadcast failed ({type(msg).__name__}): {e}")

    @handle_errors(component="task_graph", operation="update_task_status")
    @log_performance("task_graph.update_task_status")
    async def update_task_status(self, task_id: str, status: TaskStatus) -> bool:
        """更新任务状态"""
        # 验证状态转换 - 直接抛出异常而不是返回False
        current_status = await self._state_manager.get_status(task_id)
        if current_status:
            validation_result = self._validator.validate_status_transition(current_status, status)
            if not validation_result.is_valid:
                raise StateTransitionError(
                    current_status.value,
                    status.value,
                    f"Invalid transition: {validation_result.errors}",
                )

        # 更新状态
        success = await self._state_manager.update_status(
            task_id,
            status,
            "Status update requested",
        )
        if success and task_id in self._nodes:
            old_status = self._nodes[task_id].status
            self._nodes[task_id].update_status(status)

            # ✅ 直接调用自动更新 TODO
            await self._auto_update_todos(task_id=task_id, _old_status=old_status, new_status=status)

            # 🔥 新增：发送 TaskGraph 更新事件，触发持久化
            from dawei.core.events import TaskEventType

            emit_typed_event = get_emit_typed_event()
            await emit_typed_event(
                TaskEventType.TASK_GRAPH_UPDATED,  # positional event_type
                {  # positional data
                    "task_graph_id": self.task_node_id,
                    "updated_node_id": task_id,
                    "old_status": old_status.value if old_status else None,
                    "new_status": status.value,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                self.event_bus,  # positional event_bus
                task_id=self.task_node_id,
                source="task_graph_persistence",
            )

            # 🔌 WebSocket 广播：将节点状态变更推送到前端
            try:
                from dawei.websocket.ws_server import websocket_server

                if websocket_server is not None:
                    from dawei.websocket.protocol import (
                        TaskNodeStartMessage,
                        TaskNodeProgressMessage,
                        TaskNodeCompleteMessage,
                    )

                    node = self._nodes.get(task_id)
                    raw_desc = node.description if node else task_id
                    # 根任务的 description 可能是 UserInputText 对象(非字符串)、
                    # data.mode 可能为 None——不防御会让 TaskNodeStartMessage 的
                    # pydantic 校验失败,task_node_start 事件永远发不出去
                    # (demo 日志 2026-08-25 起实证)。取 content 文本,回退 str()。
                    node_name = (
                        raw_desc
                        if isinstance(raw_desc, str)
                        else (str(getattr(raw_desc, "content", "") or raw_desc)[:200] or task_id)
                    )
                    raw_type = node.data.mode if node else "task"
                    node_type = raw_type if isinstance(raw_type, str) else "task"

                    if status.value in ("running", "in_progress"):
                        ws_msg = TaskNodeStartMessage(
                            session_id="",
                            task_id=self.task_node_id,
                            task_node_id=task_id,
                            node_type=node_type,
                            description=node_name,
                            metadata={
                                "old_status": old_status.value if old_status else None,
                                "new_status": status.value,
                                "timestamp": datetime.now(UTC).isoformat(),
                            },
                        )
                    elif status.value in ("completed", "failed", "cancelled", "aborted"):
                        # P2-C: result 回填自 data.result SSOT——预算耗尽([token_budget_exceeded])
                        # 等失败原因此前恒 None,前端只看到"失败"看不到为什么。
                        # aborted 纳入 Complete 分支(此前落 Progress 分支,前端无终态卡片)。
                        node_result = None
                        if node is not None and node.data is not None:
                            node_result = getattr(node.data, "result", None)
                        ws_msg = TaskNodeCompleteMessage(
                            session_id="",
                            task_id=self.task_node_id,
                            task_node_id=task_id,
                            result=node_result,
                            duration_ms=0,
                            metadata={
                                "old_status": old_status.value if old_status else None,
                                "new_status": status.value,
                                "node_name": node_name,
                                "timestamp": datetime.now(UTC).isoformat(),
                            },
                        )
                    else:
                        ws_msg = TaskNodeProgressMessage(
                            session_id="",
                            task_id=self.task_node_id,
                            task_node_id=task_id,
                            progress=50,
                            status=status.value,
                            message=f"Node {node_name} → {status.value}",
                        )

                    await websocket_server.websocket_manager.broadcast(ws_msg, workspace_id=self.workspace_id)
            except Exception as ws_err:
                self.logger.warning(f"WS broadcast failed for node {task_id}: {ws_err}")

            # C12：task_status_update 广播（新前端 task-store.markNodeStatus 数据源；
            # 新 app 不处理 task_node_start/complete，运行/终态变迁全靠本消息）
            from dawei.websocket.protocol import TaskStatusUpdateMessage

            await self._ws_broadcast(
                TaskStatusUpdateMessage(
                    session_id="",
                    task_id=task_id,
                    graph_id=self.task_node_id,
                    old_status=old_status.value if old_status else "none",
                    new_status=status.value,
                ),
            )

        self.logger.info(
            f"Task status updated - task_id: {task_id}, from: {current_status.value if current_status else None}, to: {status.value}",
        )
        # increment_counter("task_graph.status_updates", tags={
        #     "from_status": current_status.value if current_status else "none",
        #     "to_status": status.value
        # })
        # set_gauge("task_graph.total_tasks", len(self._nodes))

        return success

    # 终态集合(含 2026-09-17 拆分的 CANCELLED)
    _TERMINAL_STATUSES = frozenset(
        {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ABORTED, TaskStatus.CANCELLED},
    )

    async def emit_graph_updated(self, node_id: str, reason: str = "manual") -> None:
        """仅触发 TASK_GRAPH_UPDATED 持久化事件（不改状态/不广播）

        P2-E 取消回收审计：取消路径的记账回收(reclaim_accounting_on_cancel)发生
        在 finalize 的持久化事件之后，需要一次补偿持久化把 tokens_used/审计键
        落盘——否则已回收的记账只存在于内存，进程重启即丢。
        """
        emit_typed_event = get_emit_typed_event()
        from dawei.core.events import TaskEventType

        await emit_typed_event(
            TaskEventType.TASK_GRAPH_UPDATED,
            {
                "task_graph_id": self.task_node_id,
                "updated_node_id": node_id,
                "reason": reason,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            self.event_bus,
            task_id=self.task_node_id,
            source="task_graph_persistence",
        )

    async def finalize_task(self, task_id: str, status: TaskStatus, result: str | None = None) -> bool:
        """终态 finalize(P1a 不变量 3:status 与 result 同笔写,docs/子任务组织管理交互方案.md)

        - 幂等:已终态节点不做任何变更(返回 False)
        - 先写 result 再转 status:报告回注只认终态,保证读到 result
        - result 为空时按 status 写默认文案(防崩溃路径空 result → 占位符 → 父盲目重试)
        - 不覆盖已有非空 result(attempt_completion 先到先得,取消竞态不吞结果)

        Args:
            task_id: 任务节点 ID
            status: 目标终态(COMPLETED/FAILED/ABORTED/CANCELLED)
            result: 终态结果文本(None → 默认文案)

        Returns:
            是否发生了状态变更
        """
        default_results = {
            TaskStatus.CANCELLED: "(任务被取消)",
            TaskStatus.ABORTED: "(任务被系统中止)",
            TaskStatus.FAILED: "(任务失败,无错误详情)",
            TaskStatus.COMPLETED: "(任务完成,无显式结果)",
        }
        node = await self.get_task(task_id)
        if node is None:
            self.logger.warning(f"finalize_task: task not found - task_id: {task_id}")
            return False
        if node.status in self._TERMINAL_STATUSES:
            self.logger.info(
                f"finalize_task: already terminal ({node.status.value}) - task_id: {task_id}, no change",
            )
            return False

        final_text = result if result else default_results.get(status, "(已终结)")
        # 先写 result(状态仍是运行中,报告不会中途读到无 result 的终态)
        try:
            if node.data is not None and not getattr(node.data, "result", None):
                node.data.result = final_text
        except Exception as e:  # noqa: BLE001 — result 写失败不阻断状态收敛
            self.logger.warning(f"finalize_task: failed to write result for {task_id}: {e}")

        try:
            return await self.update_task_status(task_id, status)
        except Exception as e:  # noqa: BLE001 — 状态机拒绝(如 WAITING_FOR_TOOL)由调用方决定是否重试
            self.logger.warning(f"finalize_task: status transition rejected for {task_id} -> {status.value}: {e}")
            return False

    async def set_task_result(self, task_id: str, result: str) -> bool:
        """写入任务终态结果(P1a ④/P1b ⑧ 结果 SSOT 的正式 API)

        此前 attempt_completion(task_node_executor 预算超限路径)通过 hasattr 探测
        调用本方法,但实现从未存在 → 两个调用点静默 no-op,result 只存在于
        未声明动态属性且 to_dict 不序列化,持久化/重载即丢失。

        语义(与 finalize_task 的 result 分支一致):
        - 节点不存在 / data 缺失 → False
        - 已有非空 result → False(先到先得,不覆盖:取消竞态不吞正常结果)
        - 否则写入 result + updated_at → True

        Args:
            task_id: 任务节点 ID
            result: 终态结果文本(空串视为未写,拒绝)

        Returns:
            是否发生了写入
        """
        if not result:
            return False
        node = await self.get_task(task_id)
        if node is None:
            self.logger.warning(f"set_task_result: task not found - task_id: {task_id}")
            return False
        if node.data is None:
            self.logger.warning(f"set_task_result: task has no data - task_id: {task_id}")
            return False
        if getattr(node.data, "result", None):
            self.logger.info(
                f"set_task_result: non-empty result already present - task_id: {task_id}, keeping first writer",
            )
            return False
        node.data.result = result
        node.data.updated_at = datetime.now(UTC)
        self.logger.info(f"set_task_result: result written ({len(result)} chars) - task_id: {task_id}")
        return True

    async def reset_task_for_rerun(self, task_id: str, reason: str | None = None) -> bool:
        """原位重置任务节点供重跑(P2-D,docs/子任务组织管理交互方案.md §6 重跑)

        前置:节点必须处于 COMPLETED/FAILED/ABORTED(RUNNING/CANCELLED 拒绝——
        运行中重跑 = 先终结再重跑;用户 CANCELLED 语义先到先得,不做隐式复活)。

        语义(先到先得与重跑的冲突在此消解):
        1. stash:旧 result/tokens_used/completed_at 归档到 metadata.prev_*
           (审计可追溯,报告生成器只读 data.result 不会读到旧值)
        2. clear:result/tokens_used/completed_at/started_at 清空——
           set_task_result/finalize_task 均为"不覆盖已有非空 result",
           不清空则第二次执行的 result 会被第一次的残值吞掉
        3. reset:retry_count=0,状态经状态机转 PENDING(双验证表已为此放开
           COMPLETED/FAILED→PENDING,本方法是唯一合法调用方语义)

        Args:
            task_id: 任务节点 ID
            reason: 重跑原因(写入 metadata.rerun_reason 审计)

        Returns:
            是否成功重置为 PENDING
        """
        node = await self.get_task(task_id)
        if node is None:
            self.logger.warning(f"reset_task_for_rerun: task not found - task_id: {task_id}")
            return False

        if node.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ABORTED):
            self.logger.warning(
                f"reset_task_for_rerun: status {node.status.value} not rerunnable "
                f"(need terminal COMPLETED/FAILED/ABORTED) - task_id: {task_id}",
            )
            return False

        data = node.data
        meta = getattr(data, "metadata", None)
        if data is not None and meta is not None:
            # 1. stash 旧值(审计追溯,不丢历史)
            if getattr(data, "result", None):
                meta["prev_result"] = data.result
            if getattr(data, "tokens_used", None) is not None:
                meta["prev_tokens_used"] = data.tokens_used
            if getattr(data, "completed_at", None):
                meta["prev_completed_at"] = (
                    data.completed_at.isoformat() if hasattr(data.completed_at, "isoformat") else str(data.completed_at)
                )
            meta["rerun_reason"] = reason or ""
            meta["rerun_at"] = datetime.now(UTC).isoformat()
            # 2. clear——先到先得的锁必须由重置原语显式解开
            data.result = None
            data.tokens_used = None
            data.completed_at = None
            data.started_at = None
            if hasattr(data, "retry_count"):
                data.retry_count = 0
            data.updated_at = datetime.now(UTC)

        # 3. 经状态机转 PENDING(触发校验/事件/持久化,不走旁路)
        try:
            return await self.update_task_status(task_id, TaskStatus.PENDING)
        except Exception as e:  # noqa: BLE001 — 状态机拒绝时保留原终态,FAST FAIL 给调用方
            self.logger.warning(f"reset_task_for_rerun: transition rejected for {task_id}: {e}")
            return False

    @handle_errors(component="task_graph", operation="update_task_context")
    @log_performance("task_graph.update_task_context")
    async def update_task_context(self, task_id: str, context: TaskContext) -> bool:
        """更新任务上下文"""
        # 验证上下文 - 直接抛出异常而不是返回False
        validation_result = self._validator.validate_context(context)
        if not validation_result.is_valid:
            raise ValidationError(
                "context",
                str(context),
                f"Validation failed: {validation_result.errors}",
            )

        # 更新上下文
        success = await self._context_store.update_context(task_id, context)
        if success and task_id in self._nodes:
            self._nodes[task_id].update_data(context=context)

        self.logger.info(f"Task context updated - task_id: {task_id}")
        # increment_counter("task_graph.context_updates", tags={
        #     "task_id": task_id
        # })

        return success

    @handle_errors(component="task_graph", operation="delete_task")
    @log_performance("task_graph.delete_task")
    async def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        async with self._lock:
            # 验证任务存在 - 直接抛出异常而不是返回False
            if task_id not in self._nodes:
                raise TaskNotFoundError(task_id)

            node = self._nodes[task_id]

            # 不能删除有子任务的任务 - 直接抛出异常
            if node.has_children():
                raise TaskExecutionError(task_id, "Cannot delete task with children")

            # 从父节点中移除
            if node.has_parent():
                parent_node = self._nodes[node.parent_id]
                parent_node.remove_child(task_id)

            # 删除节点
            del self._nodes[task_id]

            # 清理管理器中的数据
            await self._todo_manager.update_todos(task_id, [])
            await self._context_store.clear_context(task_id)
            # 状态管理器保留历史记录，不删除

        # 🔥 修复：事件在图谱锁外发送（handler 可能重新获取图谱锁，锁内 emit 会死锁）
        from dawei.core.events import TaskEventType

        emit_typed_event = get_emit_typed_event()
        await emit_typed_event(
            TaskEventType.TASK_COMPLETED,  # positional event_type
            {  # positional data
                "result": {"deleted": True, "task_id": task_id},
                "duration": 0.0,
                "success": True,
                "task_id": task_id,
                "source": "task_graph",
            },
            self.event_bus,  # positional event_bus
        )

        # C12：task_graph_update(node_removed) 广播（新前端 task-store.applyGraphUpdate）
        from dawei.websocket.protocol import TaskGraphUpdateMessage

        await self._ws_broadcast(
            TaskGraphUpdateMessage(
                session_id="",
                graph_id=self.task_node_id,
                update_type="node_removed",
                data={"task_id": task_id},
            ),
        )

        self.logger.info(f"Task deleted - task_id: {task_id}")

        return True

    # ==================== TODO 管理 ====================

    async def update_todos(self, task_id: str, todos: List[TodoItem]) -> bool:
        """更新任务的TODO列表"""
        try:
            # 注意：这里不启用 auto_progress，避免创建时自动激活 TODO
            # TODO 的自动激活由 TaskNode 状态变化触发
            success = await self._todo_manager.update_todos(task_id, todos, auto_progress=False)
            if success and task_id in self._nodes:
                self._nodes[task_id].update_data(todos=todos)
            return success
        except Exception as e:
            # Management operation: return False on error (intentional degradation)
            # This allows caller to handle update failures gracefully
            self.logger.error(f"Failed to update todos: {e}", exc_info=True)
            return False

    async def get_todos(self, task_id: str) -> List[TodoItem]:
        """获取任务的TODO列表"""
        try:
            return await self._todo_manager.get_todos(task_id)
        except Exception as e:
            # Query operation: return empty list on error (intentional degradation)
            self.logger.error(f"Failed to get todos: {e}", exc_info=True)
            return []

    async def add_todo(self, task_id: str, todo: TodoItem) -> bool:
        """添加TODO项"""
        try:
            success = await self._todo_manager.add_todo(task_id, todo)
            if success:
                todos = await self._todo_manager.get_todos(task_id)
                if task_id in self._nodes:
                    self._nodes[task_id].update_data(todos=todos)
            return success
        except Exception as e:
            # Management operation: return False on error (intentional degradation)
            self.logger.error(f"Failed to add todo: {e}", exc_info=True)
            return False

    async def update_todo_status(self, task_id: str, todo_id: str, status: TodoItem) -> bool:
        """更新TODO项状态"""
        try:
            success = await self._todo_manager.update_todo_status(task_id, todo_id, status)
            if success:
                todos = await self._todo_manager.get_todos(task_id)
                if task_id in self._nodes:
                    self._nodes[task_id].update_data(todos=todos)
            return success
        except Exception as e:
            # Management operation: return False on error (intentional degradation)
            self.logger.error(f"Failed to update todo status: {e}", exc_info=True)
            return False

    # ==================== 状态查询 ====================

    async def get_task_status(self, task_id: str) -> TaskStatus | None:
        """获取任务状态"""
        try:
            return await self._state_manager.get_status(task_id)
        except Exception as e:
            # Query operation: return None on error (intentional degradation)
            self.logger.error(f"Failed to get task status: {e}", exc_info=True)
            return None

    async def get_task_hierarchy(self) -> Dict[str, Any]:
        """获取任务层级结构"""
        try:
            async with self._lock:
                if not self._root_node:
                    return {}

                return {
                    "root_id": self._root_node.task_node_id,
                    "total_tasks": len(self._nodes),
                    "tree": self._build_tree(self._root_node.task_node_id),
                }

        except Exception as e:
            # Query operation: return empty dict on error (intentional degradation)
            self.logger.error(f"Failed to get task hierarchy: {e}", exc_info=True)
            return {}

    def _build_tree(self, task_id: str) -> Dict[str, Any]:
        """构建任务树"""
        node = self._nodes.get(task_id)
        if not node:
            return {}

        tree = {
            "task_node_id": node.task_node_id,
            "description": node.description,
            "status": node.status.value,
            "mode": node.mode,
            "children": [],
        }

        for child_id in node.child_ids:
            child_tree = self._build_tree(child_id)
            if child_tree:
                tree["children"].append(child_tree)

        return tree

    # ==================== 持久化 ====================

    async def save_checkpoint(self) -> str:
        """保存检查点"""
        try:
            checkpoint_id = str(uuid.uuid4())

            # 收集所有数据
            checkpoint_data = {
                "checkpoint_id": checkpoint_id,
                "task_graph_id": self.task_node_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "nodes": {task_id: node.to_dict() for task_id, node in self._nodes.items()},
                "root_node_id": self._root_node.task_node_id if self._root_node else None,
                "states": await self._state_manager.get_all_states(),
                "contexts": await self._context_store.get_all_contexts(),
            }

            # 发送检查点事件
            from dawei.core.events import TaskEventType

            emit_typed_event = get_emit_typed_event()
            await emit_typed_event(
                TaskEventType.CHECKPOINT_CREATED,  # positional event_type
                {  # positional data
                    "checkpoint_id": checkpoint_id,
                    "checkpoint_path": f"/checkpoints/{checkpoint_id}",
                    "checkpoint_size": len(str(checkpoint_data)),
                    "task_id": self.task_node_id,
                    "source": "task_graph",
                },
                self.event_bus,  # positional event_bus
            )

            self.logger.info(f"Created checkpoint: {checkpoint_id}")
            return checkpoint_id

        except Exception as e:
            self.logger.error(f"Failed to save checkpoint: {e}", exc_info=True)
            raise

    async def restore_from_checkpoint(self, checkpoint_data: Dict[str, Any]) -> bool:
        """从检查点恢复"""
        try:
            async with self._lock:
                # 清理当前状态
                self._nodes.clear()
                self._root_node = None

                # 恢复节点
                nodes_data = checkpoint_data.get("nodes", {})
                for task_id, node_data in nodes_data.items():
                    node = TaskNode.from_dict(node_data)
                    self._nodes[task_id] = node

                # 恢复根节点
                root_node_id = checkpoint_data.get("root_node_id")
                if root_node_id and root_node_id in self._nodes:
                    self._root_node = self._nodes[root_node_id]

                # 恢复状态
                states = checkpoint_data.get("states", {})
                for task_id, status_data in states.items():
                    status = TaskStatus(status_data.get("value", "pending")) if isinstance(status_data, dict) else TaskStatus(status_data)
                    # 直接设置状态以绕过状态转换验证（恢复场景）
                    self._state_manager._states[task_id] = status

                # 恢复上下文
                contexts = checkpoint_data.get("contexts", {})
                for task_id, context_dict in contexts.items():
                    context = TaskContext.from_dict(context_dict) if isinstance(context_dict, dict) else context_dict
                    await self._context_store.update_context(task_id, context)

            # 🔥 修复：事件在图谱锁外发送（handler 可能重新获取图谱锁，锁内 emit 会死锁）
            from dawei.core.events import TaskEventType

            emit_typed_event = get_emit_typed_event()
            await emit_typed_event(
                TaskEventType.CHECKPOINT_RESTORED,  # positional event_type
                {  # positional data
                    "checkpoint_id": checkpoint_data.get("checkpoint_id", "unknown"),
                    "checkpoint_path": f"/checkpoints/{checkpoint_data.get('checkpoint_id', 'unknown')}",
                    "restore_time": 0.0,
                    "task_id": self.task_node_id,
                    "source": "task_graph",
                },
                self.event_bus,  # positional event_bus
            )

            self.logger.info(f"Restored from checkpoint for task graph: {self.task_node_id}")
            return True

        except Exception as e:
            # Recovery operation: return False on error (intentional degradation)
            # Checkpoint restoration failure should be handled by caller
            self.logger.error(f"Failed to restore from checkpoint: {e}", exc_info=True)
            return False

    # ==================== 统计信息 ====================

    async def get_statistics(self) -> Dict[str, Any]:
        """获取任务图统计信息"""
        try:
            # 基本统计
            total_tasks = len(self._nodes)
            root_tasks = sum(1 for node in self._nodes.values() if node.is_root())
            leaf_tasks = sum(1 for node in self._nodes.values() if not node.has_children())

            # 状态统计
            state_stats = await self._state_manager.get_state_statistics()

            # TODO统计
            todo_stats = {}
            for task_id in self._nodes:
                stats = await self._todo_manager.get_todo_statistics(task_id)
                todo_stats[task_id] = stats

            return {
                "task_graph_id": self.task_node_id,
                "total_tasks": total_tasks,
                "root_tasks": root_tasks,
                "leaf_tasks": leaf_tasks,
                "state_statistics": state_stats,
                "todo_statistics": todo_stats,
                "hierarchy": await self.get_task_hierarchy(),
            }
        except Exception as e:
            # Query operation: return empty dict on error (intentional degradation)
            self.logger.error(f"Failed to get statistics: {e}", exc_info=True)
            return {}

    # ==================== 新增方法 ====================

    async def create_task(
        self,
        task_id: str,
        description: str,
        mode: str,
        parent_task_id: str | None = None,
        status: TaskStatus = TaskStatus.PENDING,
        context: TaskContext | None = None,
        todos: List[TodoItem] | None = None,
        priority: TaskPriority | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> TaskNode:
        """创建任务的统一接口

        Args:
            task_id: 任务ID
            description: 任务描述
            mode: 任务模式
            parent_task_id: 父任务ID（可选）
            status: 任务状态
            context: 任务上下文
            todos: TODO列表
            priority: 任务优先级
            metadata: 元数据

        Returns:
            TaskNode: 创建的任务节点

        """
        try:
            # 创建任务数据
            task_data = TaskData(
                task_id=task_id,
                description=description,
                mode=mode,
                status=status,
                context=context or TaskContext(user_id="", session_id="", message_id=""),
                todos=todos or [],
                priority=priority or TaskPriority.MEDIUM,
                metadata=metadata or {},
            )

            # 创建任务节点
            if parent_task_id:
                # 子任务
                return await self.create_subtask(parent_task_id, task_data)
            # 根任务
            return await self.create_root_task(task_data)

        except Exception as e:
            self.logger.error(f"Failed to create task: {e}", exc_info=True)
            raise

    async def get_task_info(self, task_id: str) -> Dict[str, Any] | None:
        """获取任务的完整信息

        Args:
            task_id: 任务ID

        Returns:
            Dict[str, Any]: 任务信息字典，如果任务不存在则返回None

        """
        try:
            task_node = await self.get_task(task_id)
            if not task_node:
                return None

            # 获取TODO列表
            todos = await self.get_todos(task_id)

            # 获取状态历史
            state_history = await self._state_manager.get_state_history(task_id)

            # 构建任务信息
            return {
                "task_id": task_node.task_node_id,
                "description": task_node.description,
                "mode": task_node.mode,
                "status": task_node.status.value,
                "priority": (task_node.priority.value if hasattr(task_node, "priority") and task_node.priority else "medium"),
                "context": task_node.context.to_dict() if task_node.context else {},
                "todos": [todo.to_dict() for todo in todos],
                "parent_id": task_node.parent_id,
                "child_ids": task_node.child_ids,
                "metadata": task_node.metadata,
                "created_at": (task_node.created_at.isoformat() if hasattr(task_node, "created_at") and task_node.created_at else None),
                "updated_at": (task_node.updated_at.isoformat() if hasattr(task_node, "updated_at") and task_node.updated_at else None),
                "state_history": [transition.to_dict() for transition in state_history],
            }

        except Exception as e:
            # Query operation: return None on error (intentional degradation)
            self.logger.error(f"Failed to get task info for {task_id}: {e}", exc_info=True)
            return None

    async def get_task_summary(self, task_id: str) -> TaskSummary | None:
        """获取任务摘要

        Args:
            task_id: 任务ID

        Returns:
            TaskSummary: 任务摘要，如果任务不存在则返回None

        """
        try:
            task_node = await self.get_task(task_id)
            if not task_node:
                return None

            # 获取状态历史
            state_history = await self._state_manager.get_state_history(task_id)

            # 计算子任务数量
            subtasks_created = len(task_node.child_ids) if task_node.child_ids else 0

            # 获取TODO统计
            await self._todo_manager.get_todo_statistics(task_id)

            return TaskSummary(
                task_id=task_id,
                instance_id=task_node.metadata.get("instance_id", ""),
                initial_mode=task_node.mode,
                final_mode=task_node.mode,
                mode_transitions=len(state_history),
                skill_calls=0,  # Skill call statistics to be implemented
                mcp_requests=0,  # MCP request statistics to be implemented
                subtasks_created=subtasks_created,
                tool_usage={},  # Tool usage statistics to be implemented
                token_usage={},  # Token usage statistics to be implemented
            )

        except Exception as e:
            # Query operation: return None on error (intentional degradation)
            self.logger.error(f"Failed to get task summary for {task_id}: {e}", exc_info=True)
            return None

    async def get_task_statistics(self, task_id: str) -> Dict[str, Any] | None:
        """获取任务统计信息

        Args:
            task_id: 任务ID

        Returns:
            Dict[str, Any]: 任务统计信息，如果任务不存在则返回None

        """
        try:
            task_node = await self.get_task(task_id)
            if not task_node:
                return None

            # 获取状态历史
            state_history = await self._state_manager.get_state_history(task_id)

            # 获取TODO统计
            todo_stats = await self._todo_manager.get_todo_statistics(task_id)

            # 获取上下文信息
            context = await self._context_store.get_context(task_id)

            return {
                "task_id": task_id,
                "status": task_node.status.value,
                "mode": task_node.mode,
                "priority": (task_node.priority.value if hasattr(task_node, "priority") and task_node.priority else "medium"),
                "parent_id": task_node.parent_id,
                "child_count": len(task_node.child_ids) if task_node.child_ids else 0,
                "created_at": (task_node.created_at.isoformat() if hasattr(task_node, "created_at") and task_node.created_at else None),
                "updated_at": (task_node.updated_at.isoformat() if hasattr(task_node, "updated_at") and task_node.updated_at else None),
                "state_transitions": len(state_history),
                "todo_statistics": todo_stats,
                "context": context.to_dict() if context else {},
                "metadata": task_node.metadata,
            }

        except Exception as e:
            # Query operation: return None on error (intentional degradation)
            self.logger.error(f"Failed to get task statistics for {task_id}: {e}", exc_info=True)
            return None
