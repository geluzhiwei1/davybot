# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""任务图核心管理类
新架构中的核心组件，协调各个管理器
"""

import asyncio
import uuid
from datetime import UTC, datetime, timezone
from typing import Any

from dawei.agentic.errors import (
    StateTransitionError,
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

    def __init__(self, task_id: str, event_bus=None):
        # 验证输入
        if not task_id or not task_id.strip():
            raise ValidationError("task_id", task_id, "must be non-empty string")

        self.task_node_id = task_id
        # 使用延迟导入避免循环导入
        self.event_bus = event_bus
        self.logger = get_logger(__name__)

        # 核心组件
        self._root_node: TaskNode | None = None
        self._nodes: dict[str, TaskNode] = {}
        # 延迟导入管理器以避免循环导入
        from .managers import ContextStore, StateManager, TodoManager

        self._todo_manager = TodoManager(event_bus=self.event_bus)
        self._state_manager = StateManager(event_bus=self.event_bus)
        self._context_store = ContextStore()
        self._validator = TaskValidator()

        # 锁
        self._lock = asyncio.Lock()

        # 设置事件监听
        self._setup_event_listeners()

    def _setup_event_listeners(self):
        """设置事件监听器（纯强类型）"""
        from dawei.core.events import TaskEventType

        # 监听状态变化事件
        self.event_bus.add_handler(TaskEventType.STATE_CHANGED, self._on_status_changed)
        self.event_bus.add_handler(TaskEventType.TODOS_UPDATED, self._on_todos_updated)
        self.event_bus.add_handler(TaskEventType.CONTEXT_UPDATED, self._on_context_updated)

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

    async def _on_context_updated(self, event_data: dict[str, Any]):
        """上下文更新事件处理"""
        task_id = event_data.get("task_id")

        if task_id in self._nodes:
            # 上下文更新会通过ContextStore处理
            self.logger.debug(f"Context updated for task {task_id}")

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

            # 发送事件
            from dawei.core.events import TaskEventType

            emit_typed_event = get_emit_typed_event()
            await emit_typed_event(
                event_type=TaskEventType.TASK_STARTED,
                data={
                    "task_name": task_data.task_node_id,
                    "task_description": task_data.description,
                    "mode": task_data.mode,
                    "type": "root_task",
                },
                task_id=task_data.task_node_id,
                source="task_graph",
            )

            # 🔥 新增：发送 TaskGraph 创建事件，触发持久化
            await emit_typed_event(
                event_type=TaskEventType.TASK_GRAPH_CREATED,
                data={
                    "task_graph_id": self.task_node_id,
                    "root_task_id": task_data.task_node_id,
                    "mode": task_data.mode,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                task_id=self.task_node_id,
                source="task_graph_persistence",
            )

            self.logger.info(
                f"Root task created - task_id: {task_data.task_node_id}, mode: {task_data.mode}",
            )
            # increment_counter("task_graph.root_tasks_created", tags={
            #     "mode": task_data.mode
            # })
            # set_gauge("task_graph.total_tasks", len(self._nodes))

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

            # 更新父节点的子节点列表
            parent_node = self._nodes[parent_id]
            parent_node.add_child(task_data.task_node_id)

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

            # 发送事件
            from dawei.core.events import TaskEventType

            emit_typed_event = get_emit_typed_event()
            await emit_typed_event(
                event_type=TaskEventType.TASK_STARTED,
                data={
                    "task_name": task_data.task_node_id,
                    "task_description": task_data.description,
                    "mode": task_data.mode,
                    "type": "subtask",
                    "parent_id": parent_id,
                },
                task_id=task_data.task_node_id,
                source="task_graph",
            )

            # 🔥 新增：发送 TaskGraph 更新事件，触发持久化
            await emit_typed_event(
                event_type=TaskEventType.TASK_GRAPH_UPDATED,
                data={
                    "task_graph_id": self.task_node_id,
                    "added_node_id": task_data.task_node_id,
                    "parent_id": parent_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                task_id=self.task_node_id,
                source="task_graph_persistence",
            )

            self.logger.info(
                f"Subtask created - task_id: {task_data.task_node_id}, parent_id: {parent_id}, mode: {task_data.mode}",
            )
            # increment_counter("task_graph.subtasks_created", tags={
            #     "parent_mode": self._nodes[parent_id].mode if parent_id in self._nodes else "unknown"
            # })
            # set_gauge("task_graph.total_tasks", len(self._nodes))

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

    async def get_subtasks(self, parent_id: str) -> list[TaskNode]:
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

    async def get_all_tasks(self) -> list[TaskNode]:
        """获取所有任务节点"""
        try:
            async with self._lock:
                return list(self._nodes.values())
        except Exception as e:
            self.logger.error(f"Failed to get all tasks: {e}", exc_info=True)
            return []

    # ==================== 任务操作 ====================

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
                event_type=TaskEventType.TASK_GRAPH_UPDATED,
                data={
                    "task_graph_id": self.task_node_id,
                    "updated_node_id": task_id,
                    "old_status": old_status.value if old_status else None,
                    "new_status": status.value,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                task_id=self.task_node_id,
                source="task_graph_persistence",
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

            # 发送事件
            from dawei.core.events import TaskEventType

            emit_typed_event = get_emit_typed_event()
            await emit_typed_event(
                event_type=TaskEventType.TASK_COMPLETED,
                data={
                    "result": {"deleted": True, "task_id": task_id},
                    "duration": 0.0,
                    "success": True,
                    "task_id": task_id,
                    "source": "task_graph",
                },
            )

            self.logger.info(f"Task deleted - task_id: {task_id}")
            # increment_counter("task_graph.tasks_deleted", tags={})
            # set_gauge("task_graph.total_tasks", len(self._nodes))

            return True

    # ==================== TODO 管理 ====================

    async def update_todos(self, task_id: str, todos: list[TodoItem]) -> bool:
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

    async def get_todos(self, task_id: str) -> list[TodoItem]:
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

    async def get_task_hierarchy(self) -> dict[str, Any]:
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

    def _build_tree(self, task_id: str) -> dict[str, Any]:
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
                event_type=TaskEventType.CHECKPOINT_CREATED,
                data={
                    "checkpoint_id": checkpoint_id,
                    "checkpoint_path": f"/checkpoints/{checkpoint_id}",
                    "checkpoint_size": len(str(checkpoint_data)),
                    "task_id": self.task_node_id,
                    "source": "task_graph",
                },
            )

            self.logger.info(f"Created checkpoint: {checkpoint_id}")
            return checkpoint_id

        except Exception as e:
            self.logger.error(f"Failed to save checkpoint: {e}", exc_info=True)
            raise

    async def restore_from_checkpoint(self, checkpoint_data: dict[str, Any]) -> bool:
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

                # 发送恢复事件
                from dawei.core.events import TaskEventType

                emit_typed_event = get_emit_typed_event()
                await emit_typed_event(
                    event_type=TaskEventType.CHECKPOINT_RESTORED,
                    data={
                        "checkpoint_id": checkpoint_data.get("checkpoint_id", "unknown"),
                        "checkpoint_path": f"/checkpoints/{checkpoint_data.get('checkpoint_id', 'unknown')}",
                        "restore_time": 0.0,
                        "task_id": self.task_node_id,
                        "source": "task_graph",
                    },
                )

                self.logger.info(f"Restored from checkpoint for task graph: {self.task_node_id}")
                return True

        except Exception as e:
            # Recovery operation: return False on error (intentional degradation)
            # Checkpoint restoration failure should be handled by caller
            self.logger.error(f"Failed to restore from checkpoint: {e}", exc_info=True)
            return False

    # ==================== 统计信息 ====================

    async def get_statistics(self) -> dict[str, Any]:
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
        todos: list[TodoItem] | None = None,
        priority: TaskPriority | None = None,
        metadata: dict[str, Any] | None = None,
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

    async def get_task_info(self, task_id: str) -> dict[str, Any] | None:
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
                skill_calls=0,  # TODO: 实现技能调用统计
                mcp_requests=0,  # TODO: 实现MCP请求统计
                subtasks_created=subtasks_created,
                tool_usage={},  # TODO: 实现工具使用统计
                token_usage={},  # TODO: 实现token使用统计
            )

        except Exception as e:
            # Query operation: return None on error (intentional degradation)
            self.logger.error(f"Failed to get task summary for {task_id}: {e}", exc_info=True)
            return None

    async def get_task_statistics(self, task_id: str) -> dict[str, Any] | None:
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
