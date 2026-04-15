# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

import json
from typing import List, Dict, Any, ClassVar

from pydantic import BaseModel, Field

from dawei.logg.logging import get_logger
from dawei.tools.custom_base_tool import CustomBaseTool
from dawei.tools.custom_tools.async_utils import run_async


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
    follow_up: List[str] = Field(
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

    def _run(self, question: str, follow_up: List[str]) -> str:
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
                "timestamp": asyncio.get_event_loop().time() if asyncio.get_event_loop() else None,
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

    def _run(self, result: str) -> str:
        """Present completion result with enhanced task management."""
        try:
            completion_result = {
                "type": "task_completion",
                "status": "completed",
                "result": result,
                "timestamp": asyncio.get_event_loop().time() if asyncio.get_event_loop() else None,
                "message": "Task completed successfully",
            }

            # 如果有 task_graph，更新任务状态
            if self.task_graph:
                asyncio.create_task(self._complete_task(result))

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

        # 获取根任务
        root_task = await self.task_graph.get_root_task()
        if root_task:
            await self.task_graph.update_task_status(root_task.task_id, TaskStatus.COMPLETED)
            self.logger.info(f"Task completed via AttemptCompletionTool: {root_task.task_id}")


# Switch Mode Tool
class SwitchModeInput(BaseModel):
    """Input for SwitchModeTool."""

    mode_slug: str = Field(
        ...,
        description="Slug of mode to switch to (e.g., 'orchestrator', 'pdca').",
    )
    reason: str | None = Field(None, description="Reason for switching modes.")


class SwitchModeTool(CustomBaseTool):
    """Tool for switching to different modes for specialized tasks."""

    name: ClassVar[str] = "switch_mode"
    description: ClassVar[str] = "Switches to a different PDCA mode for specialized tasks. Available modes are dynamically loaded from the workspace configuration (common modes: orchestrator, plan, do, check, act). If the specified mode is not found, returns the list of available modes."
    args_schema: ClassVar[type[BaseModel]] = SwitchModeInput

    def __init__(self, task_graph=None, workspace_root: str | None = None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)
        self.workspace_root = workspace_root
        # Lazy load available modes
        self._available_modes: dict[str, dict[str, Any]] | None = None

    def _load_available_modes(self) -> dict[str, dict[str, Any]]:
        """动态加载可用模式从 ModeManager"""
        if self._available_modes is not None:
            return self._available_modes

        try:
            from dawei.mode.mode_manager import ModeManager

            mode_manager = ModeManager(workspace_path=self.workspace_root)
            all_modes = mode_manager.get_all_modes()

            # 转换为工具所需的格式
            available_modes = {}
            for slug, mode_config in all_modes.items():
                # 从 groups 字段提取 capabilities
                capabilities = []
                if mode_config.groups:
                    for group in mode_config.groups:
                        if isinstance(group, str):
                            capabilities.append(group)
                        elif isinstance(group, dict):
                            capabilities.extend(group.get("tools", []))

                available_modes[slug] = {
                    "name": mode_config.name,
                    "description": mode_config.description or mode_config.when_to_use,
                    "capabilities": capabilities if capabilities else ["general"],
                    "role_definition": mode_config.role_definition,
                    "custom_instructions": mode_config.custom_instructions,
                    "source": mode_config.source,
                }

            self._available_modes = available_modes
            self.logger.info(f"Loaded {len(available_modes)} modes from ModeManager")
            return available_modes

        except Exception as e:
            self.logger.error(f"Failed to load modes from ModeManager: {e}", exc_info=True)
            # 返回空字典而不是硬编码的默认值
            return {}

    def _run(self, mode_slug: str, reason: str | None = None) -> str:
        """Switch to specified mode with enhanced task management."""
        try:
            # 动态加载可用模式
            available_modes = self._load_available_modes()

            # Check if mode exists
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

            result = {
                "type": "mode_switch",
                "from_mode": "current",  # Mock current mode
                "to_mode": mode_slug,
                "mode_name": mode_info["name"],
                "mode_description": mode_info["description"],
                "capabilities": mode_info["capabilities"],
                "role_definition": mode_info.get("role_definition", ""),
                "custom_instructions": mode_info.get("custom_instructions", ""),
                "source": mode_info.get("source", "unknown"),
                "reason": reason or "Mode switch requested",
                "status": "switched",
                "timestamp": asyncio.get_event_loop().time() if asyncio.get_event_loop() else None,
            }

            # 如果有 task_graph，更新任务模式
            if self.task_graph:
                asyncio.create_task(self._switch_mode(mode_slug, reason))

            self.logger.info(f"Mode switch requested to {mode_slug}")

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.exception("Error switching mode: ")
            return json.dumps(
                {"status": "error", "message": f"Error switching mode: {e!s}"},
                indent=2,
            )

    async def _switch_mode(self, mode_slug: str, reason: str | None = None):
        """异步切换模式（新架构）"""
        try:
            # 获取组件
            components = _import_task_graph_components()
            TaskContext = components["TaskContext"]

            # 获取根任务
            root_task = await self.task_graph.get_root_task()
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

                await self.task_graph.update_task_context(root_task.task_id, updated_context)
                self.logger.info(f"Mode switched to {mode_slug} for task {root_task.task_id}")
        except (AttributeError, ValueError, KeyError) as e:
            self.logger.error(f"Failed to switch mode: {e}", exc_info=True)
            raise  # Fast Fail: surface the error to caller


# New Task Tool
class NewTaskInput(BaseModel):
    """Input for NewTaskTool."""

    mode: str = Field(..., description="Slug of mode to start new task in.")
    message: str = Field(..., description="Initial user message or instructions for new task.")


class NewTaskTool(CustomBaseTool):
    """Tool for creating new subtasks in different modes."""

    name: ClassVar[str] = "new_task"
    description: ClassVar[str] = "Creates a new subtask in the specified mode with initial instructions. The subtask inherits the current task context (user, session, workspace). Returns the subtask creation status and initial todo list."
    args_schema: ClassVar[type[BaseModel]] = NewTaskInput

    def __init__(self, task_graph=None, workspace_root: str | None = None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)
        self.workspace_root = workspace_root
        # Lazy load available modes
        self._available_modes: dict[str, str] | None = None

    def _load_available_modes(self) -> dict[str, str]:
        """动态加载可用模式从 ModeManager"""
        if self._available_modes is not None:
            return self._available_modes

        try:
            from dawei.mode.mode_manager import ModeManager

            mode_manager = ModeManager(workspace_path=self.workspace_root)
            all_modes = mode_manager.get_all_modes()

            # 转换为简化的格式 {slug: name}
            available_modes = {slug: config.name for slug, config in all_modes.items()}

            self._available_modes = available_modes
            self.logger.info(f"Loaded {len(available_modes)} modes from ModeManager")
            return available_modes

        except Exception as e:
            self.logger.error(f"Failed to load modes from ModeManager: {e}", exc_info=True)
            # 返回空字典而不是硬编码的默认值
            return {}

    def _run(self, mode: str, message: str) -> str:
        """Create new task in specified mode with enhanced task management."""
        try:
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

            # 获取组件
            components = _import_task_graph_components()
            TodoItem = components["TodoItem"]
            TodoStatus = components["TodoStatus"]

            # Create initial TODO list for subtask
            initial_todos = [
                TodoItem(content=f"Start subtask in {mode} mode", status=TodoStatus.PENDING),
                TodoItem(content=f"Process: {message}", status=TodoStatus.PENDING),
            ]

            # 如果有 task_graph，创建子任务
            if self.task_graph:
                asyncio.create_task(self._create_subtask(mode, message, initial_todos))

            result = {
                "type": "new_task",
                "mode": mode,
                "mode_name": available_modes[mode],
                "message": message,
                "initial_todos": [todo.content for todo in initial_todos],
                "status": "created",
                "timestamp": asyncio.get_event_loop().time() if asyncio.get_event_loop() else None,
                "note": "Subtask creation initiated",
            }

            self.logger.info(f"New task creation requested in {mode} mode")

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.exception("Error creating new task: ")
            return json.dumps(
                {"status": "error", "message": f"Error creating new task: {e!s}"},
                indent=2,
            )

    async def _create_subtask(self, mode: str, message: str, initial_todos):
        """异步创建子任务（新架构）"""
        try:
            import uuid

            # 获取组件
            components = _import_task_graph_components()
            TaskData = components["TaskData"]
            TaskContext = components["TaskContext"]
            TaskStatus = components["TaskStatus"]
            TaskPriority = components["TaskPriority"]

            # 获取根任务
            root_task = await self.task_graph.get_root_task()
            if not root_task:
                self.logger.warning("No root task found for creating subtask")
                return

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
                task_id=str(uuid.uuid4()),
                description=message,
                mode=mode,
                status=TaskStatus.PENDING,
                context=subtask_context,
                todos=initial_todos,
                priority=TaskPriority.MEDIUM,
                metadata={
                    "parent_task_id": root_task.task_id,
                    "created_by": "NewTaskTool",
                },
            )

            # 创建子任务
            await self.task_graph.create_subtask(root_task.task_id, subtask_data)
            self.logger.info(f"Created subtask in {mode} mode under parent {root_task.task_id}")

        except (AttributeError, ValueError, KeyError) as e:
            self.logger.error(f"Failed to create subtask: {e}", exc_info=True)
            raise  # Fast Fail: surface the error to caller


# Update Todo List Tool
class UpdateTodoListInput(BaseModel):
    """Input for UpdateTodoListTool."""

    todos: List[str] = Field(
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

    def _run(self, todos: List[str]) -> str:
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
                "updated_at": asyncio.get_event_loop().time() if asyncio.get_event_loop() else None,
            }

            # 如果有 TaskGraph，更新 TODO 列表
            if self.task_graph:
                asyncio.create_task(self._update_todos(parsed_todos))

            self.logger.info(f"TODO list update requested: {total} items")

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.exception("Error updating todo list: ")
            return json.dumps(
                {"status": "error", "message": f"Error updating todo list: {e!s}"},
                indent=2,
            )

    async def _update_todos(self, todos):
        """异步更新 TODO 列表（新架构）"""
        try:
            # 获取根任务
            root_task = await self.task_graph.get_root_task()
            if root_task:
                await self.task_graph.update_todos(root_task.task_id, todos)
                self.logger.info(
                    f"Updated TODO list for task {root_task.task_id}: {len(todos)} items",
                )

        except (AttributeError, ValueError, KeyError) as e:
            self.logger.error(f"Failed to update TODO list: {e}", exc_info=True)
            raise  # Fast Fail: surface the error to caller


# Get Task Status Tool
class GetTaskStatusInput(BaseModel):
    """Input for GetTaskStatusTool."""

    task_id: str | None = Field(None, description="Task ID to get status for (optional).")


class GetTaskStatusTool(CustomBaseTool):
    """Tool for getting current task status and progress."""

    name: ClassVar[str] = "get_task_status"
    description: ClassVar[str] = "Gets the current status of the task hierarchy and overall progress. Returns task graph structure, completion statistics, and status of all subtasks."
    args_schema: ClassVar[type[BaseModel]] = GetTaskStatusInput

    def __init__(self, task_graph=None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)

    def _run(self, task_id: str | None = None) -> str:
        """Get task status with enhanced task management."""
        try:
            if not self.task_graph:
                return json.dumps(
                    {
                        "status": "error",
                        "message": "Task graph not available. Task status tracking requires an active task graph.",
                    },
                    indent=2,
                )

            result = run_async(self._get_real_status(task_id))
            return result

        except Exception as e:
            self.logger.exception("Error getting task status: ")
            return json.dumps(
                {"status": "error", "message": f"Error getting task status: {e!s}"},
                indent=2,
            )

    async def _get_real_status(self, task_id: str | None = None) -> str:
        """获取真实任务状态（新架构）"""
        try:
            # 获取任务层级结构
            hierarchy = await self.task_graph.get_task_hierarchy()

            # 获取统计信息
            stats = await self.task_graph.get_statistics()

            # 构建结果
            result = {
                "type": "task_status",
                "task_graph_id": self.task_graph.task_node_id,
                "hierarchy": hierarchy,
                "statistics": stats,
                "requested_task_id": task_id,
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.exception("Failed to get real status: ")
            return json.dumps(
                {"status": "error", "message": f"Error getting task status: {e!s}"},
                indent=2,
            )


# ==================== WorkflowToolFactory ====================


class WorkflowToolFactory:
    """工作流工具工厂"""

    def __init__(self, task_graph=None, workspace_root: str | None = None):
        self.task_graph = task_graph
        self.workspace_root = workspace_root
        self.logger = get_logger(__name__)

    def create_tools(self) -> List[CustomBaseTool]:
        """创建所有工作流工具"""
        tools = [
            AskFollowupQuestionTool(self.task_graph),
            AttemptCompletionTool(self.task_graph),
            SwitchModeTool(self.task_graph, self.workspace_root),
            NewTaskTool(self.task_graph, self.workspace_root),
            UpdateTodoListTool(self.task_graph),
            GetTaskStatusTool(self.task_graph),
        ]

        self.logger.info(
            f"Created {len(tools)} workflow tools with {'new' if self.task_graph else 'legacy'} architecture",
        )
        return tools

    def get_tool(self, tool_name: str) -> CustomBaseTool | None:
        """根据名称获取工具"""
        tools = self.create_tools()
        for tool in tools:
            if tool.name == tool_name:
                return tool
        return None


# 便捷函数
def create_workflow_tools(task_graph=None, workspace_root: str | None = None) -> list[CustomBaseTool]:
    """创建工作流工具的便捷函数"""
    factory = WorkflowToolFactory(task_graph, workspace_root)
    return factory.create_tools()


def create_workflow_tool(tool_name: str, task_graph=None, workspace_root: str | None = None) -> CustomBaseTool | None:
    """创建单个工作流工具的便捷函数"""
    factory = WorkflowToolFactory(task_graph, workspace_root)
    return factory.get_tool(tool_name)
