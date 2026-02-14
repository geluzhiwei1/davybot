# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""TODO 列表管理器
新架构中专门负责 TODO 列表管理的组件
"""

import asyncio
from dataclasses import dataclass
from typing import Any

from dawei.core.errors import TaskNotFoundError, ValidationError
from dawei.logg.logging import get_logger
from dawei.task_graph.task_node_data import ValidationResult
from dawei.task_graph.todo_models import TodoItem, TodoStatus


# 延迟导入以避免循环导入
def get_emit_typed_event():
    """获取 emit_typed_event 函数的延迟导入"""
    from dawei.core.events import emit_typed_event

    return emit_typed_event


def get_TaskEventType():
    """获取 TaskEventType 的延迟导入"""
    from dawei.core.events import TaskEventType

    return TaskEventType


@dataclass
class TodoUpdate:
    """TODO 更新操作"""

    task_id: str
    todo_id: str | None = None
    action: str = ""  # add, update, remove, batch_update
    todo_data: dict[str, Any] | None = None
    todos: list[TodoItem] | None = None
    new_status: TodoStatus | None = None


class TodoManager:
    """TODO 列表管理器"""

    def __init__(self, event_bus=None):
        # 使用延迟导入避免循环导入
        self.event_bus = event_bus
        self._todo_lists: dict[str, list[TodoItem]] = {}
        self._lock = asyncio.Lock()
        self.logger = get_logger(__name__)

    async def update_todos(
        self,
        task_id: str,
        todos: list[TodoItem],
        source: str = "user",
        auto_progress: bool = True,
    ) -> bool:
        """更新任务的 TODO 列表

        Args:
            task_id: 任务 ID
            todos: TODO 列表
            source: 来源标识
            auto_progress: 是否自动确保只有一个 IN_PROGRESS（默认 True）

        Returns:
            是否更新成功

        """
        try:
            async with self._lock:
                # 验证 TODO 列表
                validation_result = self.validate_todos(todos)
                if not validation_result.is_valid:
                    self.logger.error(
                        f"TODO validation failed for task {task_id}: {validation_result.errors}",
                    )
                    return False

                old_todos = self._todo_lists.get(task_id, []).copy()

                # ✅ 自动确保只有一个 IN_PROGRESS
                if auto_progress:
                    todos = await self._ensure_single_in_progress(todos)

                # 更新 TODO 列表
                self._todo_lists[task_id] = todos.copy()

                # 发送事件
                emit_typed_event = get_emit_typed_event()
                taskeventtype = get_TaskEventType()
                await emit_typed_event(
                    taskeventtype.TASK_STARTED,
                    {
                        "task_name": f"todos_updated_{task_id}",
                        "task_description": f"Updated TODO list for task {task_id}",
                        "metadata": {
                            "old_todos": [todo.to_dict() for todo in old_todos],
                            "new_todos": [todo.to_dict() for todo in todos],
                            "source": source,
                            "todo_count": len(todos),
                            "auto_progress_enabled": auto_progress,
                        },
                        "task_id": task_id,
                    },
                    task_id=task_id,
                    source="todo_manager",
                )

                self.logger.info(
                    f"Updated TODO list for task {task_id} with {len(todos)} items (auto_progress={auto_progress})",
                )
                return True

        except (ValidationError, KeyError, AttributeError):
            self.logger.exception("Failed to update todos for task {task_id}: ")
            return False

    async def add_todo(self, task_id: str, todo: TodoItem, source: str = "system") -> bool:
        """添加单个 TODO 项"""
        try:
            async with self._lock:
                # 验证 TODO 项
                validation_result = self.validate_todo_item(todo)
                if not validation_result.is_valid:
                    self.logger.error(
                        f"TODO validation failed for task {task_id}: {validation_result.errors}",
                    )
                    return False

                if task_id not in self._todo_lists:
                    self._todo_lists[task_id] = []

                self._todo_lists[task_id].append(todo)

                # 发送事件
                emit_typed_event = get_emit_typed_event()
                taskeventtype = get_TaskEventType()
                await emit_typed_event(
                    taskeventtype.TASK_STARTED,
                    {
                        "task_name": f"todo_added_{todo.id}",
                        "task_description": f"Added TODO item {todo.id} to task {task_id}",
                        "metadata": {"todo": todo.to_dict(), "source": source},
                        "task_id": task_id,
                    },
                    task_id=task_id,
                    source="todo_manager",
                )

                self.logger.info(f"Added TODO item {todo.id} to task {task_id}")
                return True

        except (ValidationError, KeyError, AttributeError):
            self.logger.exception("Failed to add todo to task {task_id}: ")
            return False

    async def update_todo_status(
        self,
        task_id: str,
        todo_id: str,
        new_status: TodoStatus,
        source: str = "system",
        auto_progress: bool = True,
    ) -> bool:
        """更新 TODO 项状态

        Args:
            task_id: 任务 ID
            todo_id: TODO 项 ID
            new_status: 新状态
            source: 来源标识
            auto_progress: 是否自动推进到下一个 TODO（默认 True）

        Returns:
            是否更新成功

        """
        try:
            async with self._lock:
                if task_id not in self._todo_lists:
                    self.logger.warning(f"Task {task_id} not found in todo lists")
                    return False

                for todo in self._todo_lists[task_id]:
                    if todo.id == todo_id:
                        old_status = todo.status
                        todo.status = new_status
                        todo.update_timestamp()

                        # 发送事件
                        emit_typed_event = get_emit_typed_event()
                        taskeventtype = get_TaskEventType()
                        await emit_typed_event(
                            taskeventtype.TASK_STARTED,
                            {
                                "task_name": f"todo_status_updated_{todo_id}",
                                "task_description": f"Updated TODO {todo_id} status from {old_status.value} to {new_status.value}",
                                "metadata": {
                                    "todo_id": todo_id,
                                    "old_status": old_status.value,
                                    "new_status": new_status.value,
                                    "source": source,
                                    "auto_progress_enabled": auto_progress,
                                },
                                "task_id": task_id,
                            },
                            task_id=task_id,
                            source="todo_manager",
                        )

                        self.logger.info(
                            f"Updated TODO {todo_id} status from {old_status.value} to {new_status.value}",
                        )

                        # ✅ 自动推进：如果 TODO 完成且启用了自动推进，激活下一个
                        if auto_progress and new_status == TodoStatus.COMPLETED:
                            await self._auto_activate_next_todo(task_id, todo_id)

                        return True

                self.logger.warning(f"TODO item {todo_id} not found in task {task_id}")
                return False

        except (ValidationError, KeyError, AttributeError):
            self.logger.exception("Failed to update todo status for task {task_id}: ")
            return False

    async def remove_todo(self, task_id: str, todo_id: str, source: str = "system") -> bool:
        """移除 TODO 项"""
        try:
            async with self._lock:
                if task_id not in self._todo_lists:
                    self.logger.warning(f"Task {task_id} not found in todo lists")
                    return False

                for i, todo in enumerate(self._todo_lists[task_id]):
                    if todo.id == todo_id:
                        removed_todo = self._todo_lists[task_id].pop(i)

                        # 发送事件
                        emit_typed_event = get_emit_typed_event()
                        taskeventtype = get_TaskEventType()
                        await emit_typed_event(
                            taskeventtype.TASK_STARTED,
                            {
                                "task_name": f"todo_removed_{todo_id}",
                                "task_description": f"Removed TODO item {todo_id} from task {task_id}",
                                "metadata": {
                                    "todo": removed_todo.to_dict(),
                                    "source": source,
                                },
                                "task_id": task_id,
                            },
                            task_id=task_id,
                            source="todo_manager",
                        )

                        self.logger.info(f"Removed TODO item {todo_id} from task {task_id}")
                        return True

                self.logger.warning(f"TODO item {todo_id} not found in task {task_id}")
                return False

        except (KeyError, TaskNotFoundError):
            self.logger.exception("Failed to remove todo from task {task_id}: ")
            return False

    async def batch_update_todos(self, updates: list[TodoUpdate], source: str = "system") -> bool:
        """批量更新 TODO 列表"""
        try:
            async with self._lock:
                results = []

                for update in updates:
                    if update.action == "add" and update.todo_data:
                        todo = TodoItem.from_dict(update.todo_data)
                        result = await self.add_todo(update.task_id, todo, source)
                        results.append(result)

                    elif update.action == "update_status" and update.todo_id and update.new_status:
                        result = await self.update_todo_status(
                            update.task_id,
                            update.todo_id,
                            update.new_status,
                            source,
                        )
                        results.append(result)

                    elif update.action == "remove" and update.todo_id:
                        result = await self.remove_todo(update.task_id, update.todo_id, source)
                        results.append(result)

                    elif update.action == "batch_update" and update.todos:
                        result = await self.update_todos(update.task_id, update.todos, source)
                        results.append(result)

                    else:
                        self.logger.warning(f"Invalid todo update: {update}")
                        results.append(False)

                # 发送批量更新事件 - 为每个更新发送单独的事件
                emit_typed_event = get_emit_typed_event()
                taskeventtype = get_TaskEventType()
                for i, update in enumerate(updates):
                    if results[i]:  # 只为成功的更新发送事件
                        await emit_typed_event(
                            taskeventtype.TASK_STARTED,
                            {
                                "task_name": f"todo_batch_update_{update.action}_{update.task_id}",
                                "task_description": f"Batch TODO update: {update.action} for task {update.task_id}",
                                "metadata": {
                                    "update": update.__dict__,
                                    "source": source,
                                    "batch_index": i,
                                },
                                "task_id": update.task_id,
                            },
                            task_id=update.task_id,
                            source="todo_manager",
                        )

                success_count = sum(results)
                self.logger.info(f"Batch updated todos: {success_count}/{len(updates)} successful")
                return success_count == len(updates)

        except (ValidationError, KeyError, AttributeError):
            self.logger.exception("Failed to batch update todos: ")
            return False

    async def get_todos(self, task_id: str) -> list[TodoItem]:
        """获取任务的 TODO 列表"""
        try:
            async with self._lock:
                return self._todo_lists.get(task_id, []).copy()
        except (KeyError, AttributeError):
            self.logger.exception("Failed to get todos for task {task_id}: ")
            return []

    def validate_todos(self, todos: list[TodoItem]) -> ValidationResult:
        """验证 TODO 列表"""
        result = ValidationResult(is_valid=True)

        if not todos:
            result.add_warning("TODO list is empty")
            return result

        # 检查重复ID
        todo_ids = [todo.id for todo in todos]
        if len(todo_ids) != len(set(todo_ids)):
            result.add_error("Duplicate TODO item IDs found")

        # 检查每个TODO项
        for todo in todos:
            todo_result = self.validate_todo_item(todo)
            if not todo_result.is_valid:
                result.errors.extend(todo_result.errors)
            result.warnings.extend(todo_result.warnings)

        return result

    def validate_todo_item(self, todo: TodoItem) -> ValidationResult:
        """验证单个 TODO 项"""
        result = ValidationResult(is_valid=True)

        # 检查ID
        if not todo.id or not todo.id.strip():
            result.add_error("TODO item ID is required")

        # 检查内容
        if not todo.content or not todo.content.strip():
            result.add_error("TODO item content is required")
        elif len(todo.content) > 500:
            result.add_warning("TODO item content is very long (>500 characters)")

        # 检查状态
        if not isinstance(todo.status, TodoStatus):
            result.add_error("Invalid TODO status")

        return result

    async def get_todo_statistics(self, task_id: str) -> dict[str, Any]:
        """获取 TODO 统计信息"""
        try:
            todos = await self.get_todos(task_id)

            stats = {
                "total": len(todos),
                "pending": 0,
                "in_progress": 0,
                "completed": 0,
                "completion_rate": 0.0,
            }

            for todo in todos:
                if todo.status == TodoStatus.PENDING:
                    stats["pending"] += 1
                elif todo.status == TodoStatus.IN_PROGRESS:
                    stats["in_progress"] += 1
                elif todo.status == TodoStatus.COMPLETED:
                    stats["completed"] += 1

            if stats["total"] > 0:
                stats["completion_rate"] = (stats["completed"] / stats["total"]) * 100

            return stats

        except (KeyError, AttributeError):
            self.logger.exception("Failed to get todo statistics for task {task_id}: ")
            return {
                "total": 0,
                "pending": 0,
                "in_progress": 0,
                "completed": 0,
                "completion_rate": 0.0,
            }

    async def save_todos(self, task_id: str) -> dict[str, Any]:
        """保存 TODO 列表到持久化存储"""
        try:
            todos = await self.get_todos(task_id)
            return {
                "task_id": task_id,
                "todos": [todo.to_dict() for todo in todos],
                "timestamp": asyncio.get_event_loop().time(),
            }
        except (ValidationError, KeyError, AttributeError, TypeError):
            self.logger.exception("Failed to save todos for task {task_id}: ")
            return {}

    async def load_todos(self, task_id: str, data: dict[str, Any]) -> bool:
        """从持久化存储加载 TODO 列表"""
        try:
            if not data or "todos" not in data:
                return False

            todos = [TodoItem.from_dict(todo_data) for todo_data in data["todos"]]
            return await self.update_todos(task_id, todos, "persistence")

        except (ValidationError, KeyError, AttributeError, TypeError):
            self.logger.exception("Failed to load todos for task {task_id}: ")
            return False

    async def _ensure_single_in_progress(self, todos: list[TodoItem]) -> list[TodoItem]:
        """确保同时只有一个 TODO 是 IN_PROGRESS

        Args:
            todos: TODO 列表（会被修改）

        Returns:
            修改后的 TODO 列表

        Logic:
            - 如果没有 IN_PROGRESS，但有 PENDING，激活第一个 PENDING
            - 如果有多个 IN_PROGRESS，保留第一个，其他改为 PENDING
            - 否则保持不变

        """
        try:
            # 统计各状态的数量
            in_progress_items = [t for t in todos if t.status == TodoStatus.IN_PROGRESS]
            pending_items = [t for t in todos if t.status == TodoStatus.PENDING]

            # 场景 1: 没有 IN_PROGRESS，但有 PENDING → 激活第一个
            if len(in_progress_items) == 0 and len(pending_items) > 0:
                first_pending = pending_items[0]
                first_pending.status = TodoStatus.IN_PROGRESS
                first_pending.update_timestamp()
                self.logger.info(f"Auto-activated TODO '{first_pending.content}' to IN_PROGRESS")

            # 场景 2: 多个 IN_PROGRESS → 保留第一个，其他改为 PENDING
            elif len(in_progress_items) > 1:
                # 跳过第一个，将其他改为 PENDING
                for todo in in_progress_items[1:]:
                    todo.status = TodoStatus.PENDING
                    todo.update_timestamp()
                    self.logger.info(f"Changed TODO '{todo.content}' from IN_PROGRESS to PENDING")

            return todos

        except (AttributeError, IndexError):
            self.logger.exception("Failed to ensure single IN_PROGRESS: ")
            return todos

    async def _auto_activate_next_todo(
        self,
        task_id: str,
        completed_todo_id: str,
    ) -> TodoItem | None:
        """自动激活下一个待处理的 TODO

        当一个 TODO 完成后，自动激活下一个 PENDING 状态的 TODO。

        Args:
            task_id: 任务 ID
            completed_todo_id: 刚完成的 TODO ID

        Returns:
            被激活的 TODO，如果没有则返回 None

        """
        try:
            todos = await self.get_todos(task_id)

            # 找到刚完成的 TODO 的索引
            completed_index = -1
            for i, todo in enumerate(todos):
                if todo.id == completed_todo_id:
                    completed_index = i
                    break

            if completed_index == -1:
                self.logger.warning(f"Completed TODO {completed_todo_id} not found")
                return None

            # 查找下一个 PENDING 的 TODO
            next_todo = None
            for i in range(completed_index + 1, len(todos)):
                if todos[i].status == TodoStatus.PENDING:
                    next_todo = todos[i]
                    break

            if not next_todo:
                self.logger.info(f"No pending TODO found after {completed_todo_id}")
                return None

            # 激活下一个 TODO
            old_status = next_todo.status
            next_todo.status = TodoStatus.IN_PROGRESS
            next_todo.update_timestamp()

            # 发送自动激活事件
            emit_typed_event = get_emit_typed_event()
            taskeventtype = get_TaskEventType()
            await emit_typed_event(
                taskeventtype.TASK_STARTED,
                {
                    "task_name": f"auto_activated_todo_{next_todo.id}",
                    "task_description": f"Auto-activated next TODO: {next_todo.content}",
                    "metadata": {
                        "todo_id": next_todo.id,
                        "old_status": old_status.value,
                        "new_status": TodoStatus.IN_PROGRESS.value,
                        "previous_todo_id": completed_todo_id,
                        "source": "system_auto",
                    },
                    "task_id": task_id,
                },
                task_id=task_id,
                source="todo_manager",
            )

            self.logger.info(
                f"✅ Auto-activated next TODO '{next_todo.content}' (after {completed_todo_id}) to IN_PROGRESS",
            )

            return next_todo

        except (KeyError, AttributeError, IndexError):
            self.logger.exception("Failed to auto-activate next TODO: ")
            return None
