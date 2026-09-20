# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""任务图模块
新架构的任务管理组件，提供职责分离、类型安全和统一管理
"""

from typing import Optional

from dawei.entity.task_types import TaskStatus

# 核心管理器
from .managers import (
    ContextStore,
    StateManager,
    StateValidator,
    StatusUpdate,
    TodoManager,
    TodoUpdate,
)

# 核心类
from .task_graph import TaskGraph
from .task_node import TaskNode

# 基础数据模型
from .task_node_data import (
    StateTransition,
    TaskContext,
    TaskData,
    TaskPriority,
    ValidationResult,
)
from .task_validator import TaskValidator
from .todo_models import TodoItem, TodoStatus

__all__ = [
    # 新架构核心组件
    "TaskData",
    "TaskContext",
    "TaskPriority",
    "TaskNode",
    "StateTransition",
    "ValidationResult",
    # 管理器
    "TodoManager",
    "TodoUpdate",
    "StateManager",
    "StateValidator",
    "StatusUpdate",
    "ContextStore",
    # 核心类
    "TaskGraph",
    "TaskValidator",
    # TODO相关
    "TodoStatus",
    "TodoItem",
    # 便捷函数
    "create_task_graph",
    "create_task_with_context",
]

# 版本信息
__version__ = "2.0.0"
__architecture__ = "new"

# # 便捷工厂函数
# def create_task_graph(task_id: str, event_bus) -> TaskGraph:
#     """创建任务图实例"""
#     return TaskGraph(task_id, event_bus)

# def create_task_with_context(
#     task_id: str,
#     description: str,
#     mode: str,
#     user_id: str,
#     session_id: str,
#     message_id: str,
#     event_bus,
#     parent_task_id: Optional[str] = None,
#     **kwargs
# ) -> TaskGraph:
#     """创建带上下文的任务图实例"""
#     task_graph = TaskGraph(task_id, event_bus)

#     # 创建任务上下文
#     context = TaskContext(
#         user_id=user_id,
#         session_id=session_id,
#         message_id=message_id,
#         **kwargs
#     )

#     # 创建任务数据
#     task_data = TaskData(
#         task_id=task_id,
#         description=description,
#         mode=mode,
#         context=context,
#         **kwargs
#     )

#     # 异步创建任务（需要在异步上下文中调用）
#     import asyncio
#     if asyncio.get_event_loop().is_running():
#         # 如果已经在事件循环中，创建任务
#         asyncio.create_task(
#             task_graph.create_root_task(task_data) if not parent_task_id
#             else task_graph.create_subtask(parent_task_id, task_data)
#         )
#     else:
#         # 如果不在事件循环中，直接运行
#         if parent_task_id:
#             asyncio.run(task_graph.create_subtask(parent_task_id, task_data))
#         else:
#             asyncio.run(task_graph.create_root_task(task_data))

#     return task_graph
