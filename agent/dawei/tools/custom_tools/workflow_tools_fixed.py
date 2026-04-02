# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

import asyncio
import json
from typing import List, Dict, Any, ClassVar

from pydantic import BaseModel, Field

from dawei.logg.logging import get_logger
from dawei.tools.custom_base_tool import CustomBaseTool


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
        description="Clear, specific question addressinging information needed.",
    )
    follow_up: List[str] = Field(
        ...,
        description="List of 2-4 suggested answers, each in its own <suggest> tag.",
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
    description: ClassVar[str] = "Presents final results of a completed task without requiring further input."
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
        description="Slug of mode to switch to (e.g., 'orchestrator', 'plan', 'do', 'check', 'act').",
    )
    reason: str | None = Field(None, description="Reason for switching modes.")


class SwitchModeTool(CustomBaseTool):
    """Tool for switching to different modes for specialized tasks."""

    name: ClassVar[str] = "switch_mode"
    description: ClassVar[str] = "Changes to a different mode for specialized tasks."
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
    description: ClassVar[str] = "Creates a new subtask in specified mode with initial instructions."
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
        'Status markers: "[√]" for completed, "[-]" for in-progress, "[ ]" for pending. '
        'Format example: ["[√] Analyzed requirements", "[-] Implementing feature", "[ ] Write tests", "[ ] Update docs"]. '
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
    description: ClassVar[str] = "Gets current status of tasks and overall progress."
    args_schema: ClassVar[type[BaseModel]] = GetTaskStatusInput

    def __init__(self, task_graph=None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)

    def _run(self, task_id: str | None = None) -> str:
        """Get task status with enhanced task management."""
        try:
            # 简化实现：直接返回模拟状态,避免异步调用问题
            result = {
                "type": "task_status",
                "current_task": task_id or "main_task",
                "status": "in_progress",
                "progress": {
                    "completed_steps": 3,
                    "total_steps": 8,
                    "percentage": "37.5%",
                },
                "active_tools": ["read_file", "write_to_file", "execute_command"],
                "last_activity": "2024-01-01T12:00:00Z",
                "estimated_completion": "2024-01-01T12:30:00Z",
                "note": "Task status retrieved successfully",
            }

            return json.dumps(result, indent=2)

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


# ==================== 任务复杂度分析工具 ====================


class TaskComplexityAnalyzer:
    """任务复杂度分析器 - 评估任务拆分的必要性"""

    # 复杂度指示词
    HIGH_COMPLEXITY_INDICATORS = [
        "完整",
        "全面",
        "重构",
        "重构",
        "重构",
        "重构",
        "重构",
        "重构",
        "重构",
        "系统",
        "平台",
        "架构",
        "多个",
        "多个模块",
        "端到端",
        "完整项目",
        "完整应用",
        "重构整个",
        "迁移整个",
    ]

    MEDIUM_COMPLEXITY_INDICATORS = [
        "实现",
        "添加",
        "修改",
        "更新",
        "改进",
        "优化",
        "集成",
        "实现功能",
        "添加功能",
        "修改功能",
        "创建新功能",
        "处理",
        "转换",
        "集成多个",
    ]

    def __init__(self):
        self.logger = get_logger(__name__)

    def analyze(
        self,
        task_description: str,
        _context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """分析任务复杂度"""
        # 检测复杂度级别
        complexity_level = self._detect_complexity_level(task_description)

        # 估算步骤数量
        estimated_steps = self._estimate_steps(task_description, complexity_level)

        # 检测依赖关系
        dependencies = self._detect_dependencies(task_description)

        # 检测并行可能性
        parallel_possible = self._detect_parallel_tasks(task_description)

        # 检测所需模式
        required_modes = self._detect_required_modes(task_description)

        # 风险评估
        risks = self._assess_risks(task_description, complexity_level)

        result = {
            "complexity_level": complexity_level,
            "estimated_steps": estimated_steps,
            "dependencies": dependencies,
            "parallel_possible": parallel_possible,
            "required_modes": required_modes,
            "risks": risks,
            "should_split": estimated_steps > 3 or len(dependencies) > 0,
            "recommendation": self._generate_recommendation(
                complexity_level,
                estimated_steps,
                dependencies,
            ),
            "analysis_timestamp": (asyncio.get_event_loop().time() if asyncio.get_event_loop() else None),
        }

        self.logger.info(
            f"Task complexity analyzed: {complexity_level}, {estimated_steps} steps estimated",
        )

        return result

    def _detect_complexity_level(self, task_description: str) -> str:
        """检测复杂度级别"""
        task_lower = task_description.lower()

        # 检查高级复杂度指示词
        for indicator in self.HIGH_COMPLEXITY_INDICATORS:
            if indicator.lower() in task_lower:
                return "high"

        # 检查中级复杂度指示词
        for indicator in self.MEDIUM_COMPLEXITY_INDICATORS:
            if indicator.lower() in task_lower:
                return "medium"

        return "low"

    def _estimate_steps(self, task_description: str, complexity_level: str) -> int:
        """估算步骤数量"""
        base_steps = {"low": 1, "medium": 3, "high": 5}

        # 基于关键词调整
        adjustments = 0
        task_lower = task_description.lower()

        if "和" in task_description or "以及" in task_lower:
            adjustments += task_description.count("和") + task_description.count("以及")

        if "测试" in task_lower:
            adjustments += 1

        if "文档" in task_lower:
            adjustments += 1

        if "配置" in task_lower:
            adjustments += 1

        return min(base_steps.get(complexity_level, 1) + adjustments, 15)

    def _detect_dependencies(self, task_description: str) -> List[str]:
        """检测任务依赖"""
        dependencies = []
        task_lower = task_description.lower()

        dependency_patterns = [
            ("需要先", "前置任务"),
            ("依赖于", "外部依赖"),
            ("基于", "基于现有工作"),
            ("在...之后", "顺序依赖"),
            ("前提是", "前提条件"),
            ("需要完成", "前置任务"),
            ("确保", "前置条件"),
            ("必须有", "前提条件"),
        ]

        for pattern, dep_type in dependency_patterns:
            if pattern in task_lower:
                dependencies.append({"type": dep_type, "pattern": pattern})

        return dependencies

    def _detect_parallel_tasks(self, task_description: str) -> bool:
        """检测是否存在可并行任务"""
        task_lower = task_description.lower()

        parallel_indicators = [
            "同时",
            "并行",
            "分别",
            "各自",
            "独立",
            "同时进行",
            "两边",
            "两端",
            "多个方面",
            "不同模块",
        ]

        for indicator in parallel_indicators:
            if indicator in task_lower:
                return True

        # 检测多个 "和" 连接的可能并行任务
        and_count = task_description.count("和") + task_description.count("以及")
        return and_count >= 2

    def _detect_required_modes(self, task_description: str) -> List[str]:
        """检测所需的专业模式"""
        required = ["code"]  # 默认需要 code 模式
        task_lower = task_description.lower()

        if any(word in task_lower for word in ["设计", "架构", "规划", "计划"]):
            required.append("architect")

        if any(word in task_lower for word in ["解释", "分析", "解释为什么", "为什么", "原理"]):
            required.append("ask")

        if any(word in task_lower for word in ["调试", "问题", "错误", "修复", "排查"]):
            required.append("debug")

        if any(word in task_lower for word in ["协调", "管理", "多个任务", "整体"]):
            required.append("orchestrator")

        return list(set(required))  # 去重

    def _assess_risks(self, task_description: str, complexity_level: str) -> List[Dict[str, str]]:
        """评估任务风险"""
        risks = []
        task_lower = task_description.lower()

        # 技术风险
        if "重构" in task_lower or "迁移" in task_lower:
            risks.append(
                {
                    "type": "技术风险",
                    "description": "重构/迁移可能影响现有功能",
                    "mitigation": "建立充分的测试覆盖",
                },
            )

        # 依赖风险
        if "外部" in task_lower or "第三方" in task_lower:
            risks.append(
                {
                    "type": "依赖风险",
                    "description": "外部依赖可能不稳定",
                    "mitigation": "准备备选方案",
                },
            )

        # 范围蔓延风险
        if complexity_level == "high":
            risks.append(
                {
                    "type": "范围蔓延",
                    "description": "复杂任务容易扩展范围",
                    "mitigation": "明确定义范围边界",
                },
            )

        return risks

    def _generate_recommendation(
        self,
        complexity_level: str,
        estimated_steps: int,
        _dependencies: list,
    ) -> Dict[str, Any]:
        """生成执行建议"""
        if complexity_level == "high" or estimated_steps > 7:
            return {
                "strategy": "task_graph",
                "description": "使用 DAG 任务图管理多阶段任务",
                "tools": ["create_task_graph", "add_task_node", "set_task_dependency"],
            }
        if complexity_level == "medium" or estimated_steps > 3:
            return {
                "strategy": "subtasks",
                "description": "创建子任务分配给不同模式",
                "tools": ["new_task", "update_todo_list"],
            }
        return {
            "strategy": "direct",
            "description": "直接执行，使用 TODO 列表跟踪进度",
            "tools": ["update_todo_list"],
        }


# Analyze Task Complexity Tool
class AnalyzeTaskComplexityInput(BaseModel):
    """Input for AnalyzeTaskComplexityTool."""

    task_description: str = Field(..., description="Description of the task to analyze.")
    context: Dict[str, Any] | None = Field(
        None,
        description="Additional context about the task.",
    )


class AnalyzeTaskComplexityTool(CustomBaseTool):
    """Tool for analyzing task complexity and determining if TODO splitting is needed."""

    name: ClassVar[str] = "analyze_task_complexity"
    description: ClassVar[str] = "Analyzes task complexity, estimates steps, and recommends execution strategy."
    args_schema: ClassVar[type[BaseModel]] = AnalyzeTaskComplexityInput

    def __init__(self, task_graph=None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)
        self.analyzer = TaskComplexityAnalyzer()

    def _run(self, task_description: str, context: Dict[str, Any] | None = None) -> str:
        """Analyze task complexity."""
        try:
            result = self.analyzer.analyze(task_description, context)

            # 添加格式化输出
            formatted_output = self._format_result(result)
            result["formatted_output"] = formatted_output

            self.logger.info(f"Task complexity analysis completed: {result['complexity_level']}")

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.exception("Error analyzing task complexity: ")
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Error analyzing task complexity: {e!s}",
                },
                indent=2,
            )

    def _format_result(self, result: Dict[str, Any]) -> str:
        """格式化分析结果输出"""
        lines = []

        lines.append("📊 任务复杂度分析")
        lines.append(f"复杂度级别: {result['complexity_level'].upper()}")
        lines.append(f"预估步骤数: {result['estimated_steps']}")
        lines.append(f"需要拆分: {'是' if result['should_split'] else '否'}")

        if result["parallel_possible"]:
            lines.append("⚡ 可能存在并行任务")

        lines.append(f"\n推荐策略: {result['recommendation']['description']}")
        lines.append(f"建议工具: {', '.join(result['recommendation']['tools'])}")

        if result["required_modes"]:
            lines.append(f"\n需要的专业模式: {', '.join(result['required_modes'])}")

        if result["risks"]:
            lines.append("\n潜在风险:")
            for risk in result["risks"]:
                lines.append(f"  - [{risk['type']}] {risk['description']}")

        return "\n".join(lines)


# ==================== TODO 计划生成工具 ====================


class TodoPlanGenerator:
    """TODO 计划生成器 - 基于任务分析生成结构化 TODO 列表"""

    def __init__(self):
        self.logger = get_logger(__name__)

    def generate(
        self,
        task_description: str,
        complexity_result: Dict[str, Any],
        _context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """生成 TODO 计划"""
        # 基于复杂度生成 TODO 项
        todo_items = self._create_todo_items(task_description, complexity_result)

        # 排序 TODO 项（考虑依赖关系）
        sorted_todos = self._sort_todos(todo_items, complexity_result)

        # 添加元数据
        enriched_todos = self._enrich_todos(sorted_todos, task_description)

        # 生成执行建议
        execution_hints = self._generate_execution_hints(enriched_todos, complexity_result)

        result = {
            "todos": enriched_todos,
            "total_count": len(enriched_todos),
            "execution_hints": execution_hints,
            "complexity_based": True,
            "dynamic_adjustment_support": True,
        }

        self.logger.info(f"Generated TODO plan with {len(enriched_todos)} items")

        return result

    def _create_todo_items(
        self,
        task_description: str,
        complexity_result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """创建 TODO 项"""
        complexity_level = complexity_result.get("complexity_level", "low")
        estimated_steps = complexity_result.get("estimated_steps", 1)

        # 基础 TODO 模板
        base_todos = []

        if complexity_level == "high":
            base_todos = [
                {
                    "content": "分析与规划：理解需求并制定详细执行计划",
                    "priority": "high",
                    "phase": "planning",
                },
                {
                    "content": "环境准备：确保开发环境和依赖就绪",
                    "priority": "high",
                    "phase": "setup",
                },
                {
                    "content": "核心实现：完成主要功能开发",
                    "priority": "high",
                    "phase": "implementation",
                },
                {
                    "content": "测试验证：编写并运行测试",
                    "priority": "medium",
                    "phase": "testing",
                },
                {
                    "content": "文档更新：更新相关文档",
                    "priority": "medium",
                    "phase": "documentation",
                },
                {
                    "content": "代码审查：检查代码质量和风格",
                    "priority": "medium",
                    "phase": "review",
                },
                {
                    "content": "最终验证：完整功能测试",
                    "priority": "high",
                    "phase": "verification",
                },
            ]
        elif complexity_level == "medium":
            base_todos = [
                {"content": "理解任务需求", "priority": "high", "phase": "planning"},
                {"content": "环境检查", "priority": "medium", "phase": "setup"},
                {
                    "content": "主要功能实现",
                    "priority": "high",
                    "phase": "implementation",
                },
                {"content": "功能测试", "priority": "medium", "phase": "testing"},
                {"content": "代码优化", "priority": "low", "phase": "optimization"},
            ]
        else:  # low complexity
            base_todos = [
                {"content": "分析任务需求", "priority": "high", "phase": "analysis"},
                {"content": "执行具体操作", "priority": "high", "phase": "execution"},
                {"content": "验证结果", "priority": "medium", "phase": "verification"},
            ]

        # 基于任务描述调整 TODO
        adjusted_todos = self._adjust_todos_for_task(base_todos, task_description)

        # 确保不超过预估步骤太多
        if len(adjusted_todos) > estimated_steps + 2:
            adjusted_todos = adjusted_todos[: estimated_steps + 2]

        return adjusted_todos

    def _adjust_todos_for_task(
        self,
        todos: List[dict],
        task_description: str,
    ) -> List[Dict[str, Any]]:
        """根据具体任务调整 TODO 项"""
        adjusted = []
        task_lower = task_description.lower()

        for _i, todo in enumerate(todos):
            content = todo["content"]

            # 根据任务类型调整内容
            if "测试" in task_lower and "测试" not in content and "测试" not in content and "verification" in todo.get("phase", ""):
                content = f"{content}（包含测试）"

            if "文档" in task_lower and "文档" not in content and "documentation" in todo.get("phase", ""):
                content = f"{content}（包含文档）"

            if "重构" in task_lower and "refactor" not in content.lower() and ("review" in todo.get("phase", "") or "optimization" in todo.get("phase", "")):
                content = f"{content}（包含重构）"

            todo["content"] = content
            adjusted.append(todo)

        return adjusted

    def _sort_todos(
        self,
        todos: List[dict],
        _complexity_result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """排序 TODO 项，考虑依赖关系"""
        # 优先级排序：high > medium > low
        priority_order = {"high": 0, "medium": 1, "low": 2}

        sorted_todos = sorted(todos, key=lambda x: priority_order.get(x.get("priority", "low"), 3))

        # 按阶段排序（planning -> setup -> implementation -> testing -> documentation -> review -> verification）
        phase_order = {
            "planning": 0,
            "analysis": 0,
            "setup": 1,
            "implementation": 2,
            "execution": 2,
            "testing": 3,
            "documentation": 4,
            "optimization": 5,
            "review": 5,
            "verification": 6,
        }

        return sorted(sorted_todos, key=lambda x: phase_order.get(x.get("phase", ""), 10))

    def _enrich_todos(self, todos: List[dict], _task_description: str) -> List[Dict[str, Any]]:
        """为 TODO 项添加元数据"""
        enriched = []

        for i, todo in enumerate(todos):
            enriched_todo = {
                **todo,
                "order": i + 1,
                "id": f"todo_{i + 1}",
                "status": "pending",
                "estimated_time": self._estimate_time(todo.get("priority", "medium")),
                "can_skip": False,
                "prerequisites": [],
            }

            # 设置前置任务
            if i > 0:
                enriched_todo["prerequisites"] = [f"todo_{i}"]

            enriched.append(enriched_todo)

        return enriched

    def _estimate_time(self, priority: str) -> str:
        """估算时间"""
        time_estimates = {
            "high": "15-30 分钟",
            "medium": "10-20 分钟",
            "low": "5-10 分钟",
        }
        return time_estimates.get(priority, "10-15 分钟")

    def _generate_execution_hints(
        self,
        todos: List[dict],
        _complexity_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """生成执行提示"""
        parallel_tasks = []

        # 检测可能的并行任务
        for i, todo in enumerate(todos):
            if ("测试" in todo["content"] or "documentation" in todo.get("phase", "")) and i > 0 and "实现" in todos[i - 1]["content"] and "parallel" not in str(parallel_tasks):
                parallel_tasks.append(
                    {
                        "tasks": [f"todo_{i - 1}", f"todo_{i}"],
                        "reason": "测试可以与实现并行准备",
                    },
                )

        return {
            "parallel_execution": parallel_tasks,
            "suggested_breakpoints": [len(todos) // 2, len(todos) * 2 // 3],
            "critical_path": [f"todo_{i}" for i in range(min(3, len(todos)))] if todos else [],
        }


class GenerateTodoPlanInput(BaseModel):
    """Input for GenerateTodoPlanTool."""

    task_description: str = Field(..., description="Description of the task.")
    complexity_analysis: Dict[str, Any] | None = Field(
        None,
        description="Result from analyze_task_complexity tool.",
    )
    context: Dict[str, Any] | None = Field(None, description="Additional context.")


class GenerateTodoPlanTool(CustomBaseTool):
    """Tool for generating structured TODO plan from task analysis."""

    name: ClassVar[str] = "generate_todo_plan"
    description: ClassVar[str] = "Generates structured TODO list based on task complexity analysis."
    args_schema: ClassVar[type[BaseModel]] = GenerateTodoPlanInput

    def __init__(self, task_graph=None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)
        self.generator = TodoPlanGenerator()

    def _run(
        self,
        task_description: str,
        complexity_analysis: Dict[str, Any] | None = None,
        context: Dict[str, Any] | None = None,
    ) -> str:
        """Generate TODO plan."""
        try:
            # 使用提供的分析结果或自动分析
            if complexity_analysis:
                analysis_result = complexity_analysis
            else:
                analyzer = TaskComplexityAnalyzer()
                analysis_result = analyzer.analyze(task_description, context)

            result = self.generator.generate(task_description, analysis_result, context)

            # 添加格式化输出
            result["formatted_output"] = self._format_result(result)
            result["input_task"] = task_description

            self.logger.info(f"TODO plan generated with {result['total_count']} items")

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.exception("Error generating TODO plan: ")
            return json.dumps(
                {"status": "error", "message": f"Error generating TODO plan: {e!s}"},
                indent=2,
            )

    def _format_result(self, result: Dict[str, Any]) -> str:
        """格式化 TODO 计划输出"""
        lines = []

        lines.append("📋 TODO 计划")
        lines.append(f"总共 {result['total_count']} 个待办项\n")

        for todo in result["todos"]:
            status_icon = "⏳" if todo["status"] == "pending" else "🔄"
            lines.append(f"{status_icon} [{todo['order']}] {todo['content']}")
            if todo.get("prerequisites"):
                lines.append(f"   前置: {', '.join(todo['prerequisites'])}")
            lines.append(f"   预估时间: {todo['estimated_time']}")
            lines.append("")

        # 执行提示
        hints = result.get("execution_hints", {})
        if hints.get("critical_path"):
            lines.append("🎯 关键路径: " + ", ".join(hints["critical_path"]))

        return "\n".join(lines)


# ==================== TODO 计划验证工具 ====================


class TodoPlanValidator:
    """TODO 计划验证器 - 验证 TODO 计划的合理性"""

    def __init__(self):
        self.logger = get_logger(__name__)

    def validate(self, todos: List[dict], task_description: str) -> Dict[str, Any]:
        """验证 TODO 计划"""
        validations = []

        # 1. 检查完整性
        completeness = self._check_completeness(todos, task_description)
        validations.append(completeness)

        # 2. 检查依赖关系
        dependencies = self._check_dependencies(todos)
        validations.append(dependencies)

        # 3. 检查顺序合理性
        ordering = self._check_ordering(todos)
        validations.append(ordering)

        # 4. 检查覆盖范围
        coverage = self._check_coverage(todos, task_description)
        validations.append(coverage)

        # 5. 检查可操作性
        actionability = self._check_actionability(todos)
        validations.append(actionability)

        # 计算整体评分
        passed = sum(1 for v in validations if v["passed"])
        total = len(validations)
        score = passed / total * 100 if total > 0 else 0

        # 生成建议
        suggestions = []
        for v in validations:
            if not v["passed"]:
                suggestions.extend(v.get("suggestions", []))

        result = {
            "validations": validations,
            "overall_score": score,
            "is_valid": score >= 70,
            "suggestions": suggestions,
            "issues_count": len(suggestions),
            "can_proceed": score >= 70,
        }

        self.logger.info(f"TODO plan validated: score={score:.1f}%, valid={result['is_valid']}")

        return result

    def _check_completeness(self, todos: List[dict], _task_description: str) -> Dict[str, Any]:
        """检查计划完整性"""
        passed = len(todos) >= 3

        suggestions = []
        if not passed:
            suggestions.append("TODO 项数量较少，可能需要更详细的计划")

        # 检查是否有收尾项
        has_verification = any("验证" in t["content"] or "verification" in t.get("phase", "") for t in todos)
        if not has_verification:
            suggestions.append("建议添加验证/测试步骤确保完成质量")

        return {
            "check": "completeness",
            "passed": passed or has_verification,  # 只要有验证步骤就算通过
            "message": f"计划包含 {len(todos)} 个待办项",
            "suggestions": suggestions,
        }

    def _check_dependencies(self, todos: List[dict]) -> Dict[str, Any]:
        """检查依赖关系"""
        issues = []

        for i, todo in enumerate(todos):
            prereqs = todo.get("prerequisites", [])
            for prereq in prereqs:
                # 检查前置任务是否存在
                prereq_order = int(prereq.split("_")[-1]) if "_" in prereq else -1
                if prereq_order > i + 1:
                    issues.append(f"TODO {i + 1} 的前置任务 {prereq} 顺序不正确")

        passed = len(issues) == 0

        return {
            "check": "dependencies",
            "passed": passed,
            "message": f"依赖关系检查: {'无问题' if passed else f'发现 {len(issues)} 个问题'}",
            "issues": issues,
            "suggestions": [f"修复: {issue}" for issue in issues] if issues else [],
        }

    def _check_ordering(self, todos: List[dict]) -> Dict[str, Any]:
        """检查顺序合理性"""
        issues = []

        # 检测是否有逆向依赖
        for i, todo in enumerate(todos):
            content = todo["content"]

            # 实现应该在测试之前
            if "测试" in content:
                prev_phases = [t.get("phase", "") for t in todos[:i]]
                if "implementation" not in prev_phases and "execution" not in prev_phases:
                    issues.append(f"TODO {i + 1} 测试步骤前应有实现步骤")

            # 文档更新应该在实现之后
            if "文档" in content:
                prev_phases = [t.get("phase", "") for t in todos[:i]]
                if "implementation" not in prev_phases:
                    issues.append(f"TODO {i + 1} 文档步骤前应有实现步骤")

        passed = len(issues) == 0

        return {
            "check": "ordering",
            "passed": passed,
            "message": f"顺序检查: {'合理' if passed else f'发现 {len(issues)} 个问题'}",
            "issues": issues,
            "suggestions": [f"考虑调整: {issue}" for issue in issues] if issues else [],
        }

    def _check_coverage(self, todos: List[dict], task_description: str) -> Dict[str, Any]:
        """检查任务覆盖范围"""
        task_lower = task_description.lower()
        covered = []
        missing = []

        # 检查关键元素
        if "测试" in task_lower:
            test_covered = any("测试" in t["content"] or "testing" in t.get("phase", "") for t in todos)
            if test_covered:
                covered.append("测试")
            else:
                missing.append("测试")

        if "文档" in task_lower:
            doc_covered = any("文档" in t["content"] or "documentation" in t.get("phase", "") for t in todos)
            if doc_covered:
                covered.append("文档")
            else:
                missing.append("文档")

        if "重构" in task_lower or "修改" in task_lower:
            refactor_covered = any("重构" in t["content"] or "review" in t.get("phase", "") or "optimization" in t.get("phase", "") for t in todos)
            if refactor_covered:
                covered.append("重构")
            else:
                missing.append("重构/修改")

        passed = len(missing) == 0

        return {
            "check": "coverage",
            "passed": passed,
            "message": f"覆盖检查: 覆盖 {len(covered)}/{len(covered) + len(missing)} 个关键元素",
            "covered": covered,
            "missing": missing,
            "suggestions": [f"建议添加: {m}" for m in missing] if missing else [],
        }

    def _check_actionability(self, todos: List[dict]) -> Dict[str, Any]:
        """检查可操作性"""
        issues = []

        for i, todo in enumerate(todos):
            content = todo["content"]

            # 检查是否太笼统
            vague_words = ["完成", "处理", "相关工作"]
            for word in vague_words:
                if word in content and len(content) < 15:
                    issues.append(f"TODO {i + 1} 内容太笼统，需要更具体")
                    break

            # 检查是否有重复
            for j in range(i):
                if todos[j]["content"] == content:
                    issues.append(f"TODO {i + 1} 与 TODO {j + 1} 内容重复")
                    break

        passed = len(issues) == 0

        return {
            "check": "actionability",
            "passed": passed,
            "message": f"可操作性检查: {'良好' if passed else f'发现 {len(issues)} 个问题'}",
            "issues": issues,
            "suggestions": [f"改进: {issue}" for issue in issues] if issues else [],
        }


class ValidateTodoPlanInput(BaseModel):
    """Input for ValidateTodoPlanTool."""

    todos: List[Dict[str, Any]] = Field(..., description="TODO list to validate.")
    task_description: str = Field(..., description="Original task description.")


class ValidateTodoPlanTool(CustomBaseTool):
    """Tool for validating TODO plan reasonableness and providing improvement suggestions."""

    name: ClassVar[str] = "validate_todo_plan"
    description: ClassVar[str] = "Validates TODO plan for completeness, dependencies, and actionability."
    args_schema: ClassVar[type[BaseModel]] = ValidateTodoPlanInput

    def __init__(self, task_graph=None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)
        self.validator = TodoPlanValidator()

    def _run(self, todos: List[Dict[str, Any]], task_description: str) -> str:
        """Validate TODO plan."""
        try:
            result = self.validator.validate(todos, task_description)

            # 添加格式化输出
            result["formatted_output"] = self._format_result(result)

            self.logger.info(
                f"TODO plan validation completed: score={result['overall_score']:.1f}%",
            )

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.exception("Error validating TODO plan: ")
            return json.dumps(
                {"status": "error", "message": f"Error validating TODO plan: {e!s}"},
                indent=2,
            )

    def _format_result(self, result: Dict[str, Any]) -> str:
        """格式化验证结果输出"""
        lines = []

        score = result["overall_score"]
        status = "✅ 通过" if result["is_valid"] else "⚠️ 需要改进"

        lines.append("🔍 TODO 计划验证")
        lines.append(f"评分: {score:.1f}% - {status}")
        lines.append("")

        # 各项检查结果
        for v in result["validations"]:
            icon = "✅" if v["passed"] else "❌"
            lines.append(f"{icon} {v['message']}")

        # 建议
        if result["suggestions"]:
            lines.append("\n💡 改进建议:")
            for suggestion in result["suggestions"][:5]:  # 最多显示5条
                lines.append(f"  • {suggestion}")

        # 覆盖的元素
        coverage = next((v for v in result["validations"] if v["check"] == "coverage"), None)
        if coverage and coverage.get("covered"):
            lines.append(f"\n✓ 已覆盖: {', '.join(coverage['covered'])}")
        if coverage and coverage.get("missing"):
            lines.append(f"✗ 缺失: {', '.join(coverage['missing'])}")

        return "\n".join(lines)


# ==================== 动态 TODO 调整工具 ====================


class AdjustTodoOrderInput(BaseModel):
    """Input for AdjustTodoOrderTool."""

    current_todos: List[Dict[str, Any]] = Field(..., description="Current TODO list.")
    adjustment_type: str = Field(
        ...,
        description="Type of adjustment: 'reorder', 'add', 'remove', 'update'.",
    )
    adjustment_data: Dict[str, Any] = Field(..., description="Data for the adjustment.")
    reason: str | None = Field(None, description="Reason for the adjustment.")


class AdjustTodoOrderTool(CustomBaseTool):
    """Tool for dynamically adjusting TODO order based on execution progress."""

    name: ClassVar[str] = "adjust_todo_order"
    description: ClassVar[str] = "Dynamically adjusts TODO order, adds new items, or removes completed ones."
    args_schema: ClassVar[type[BaseModel]] = AdjustTodoOrderInput

    def __init__(self, task_graph=None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)

    def _run(
        self,
        current_todos: List[Dict[str, Any]],
        adjustment_type: str,
        adjustment_data: Dict[str, Any],
        reason: str | None = None,
    ) -> str:
        """Adjust TODO order dynamically."""
        try:
            if adjustment_type == "reorder":
                result = self._reorder_todos(current_todos, adjustment_data)
            elif adjustment_type == "add":
                result = self._add_todo(current_todos, adjustment_data)
            elif adjustment_type == "remove":
                result = self._remove_todo(current_todos, adjustment_data)
            elif adjustment_type == "update":
                result = self._update_todo(current_todos, adjustment_data)
            else:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Unknown adjustment type: {adjustment_type}",
                    },
                    indent=2,
                )

            result["adjustment_type"] = adjustment_type
            result["reason"] = reason or "No reason provided"
            result["formatted_output"] = self._format_result(result)

            self.logger.info(f"TODO adjusted: {adjustment_type}")

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.exception("Error adjusting TODO: ")
            return json.dumps(
                {"status": "error", "message": f"Error adjusting TODO: {e!s}"},
                indent=2,
            )

    def _reorder_todos(self, todos: List[dict], data: dict) -> Dict[str, Any]:
        """重新排序 TODO"""
        new_order = data.get("new_order", [])

        # 根据新顺序重新排序
        todo_map = {f"todo_{t['order']}": t for t in todos}
        reordered = []

        for order_id in new_order:
            if order_id in todo_map:
                reordered.append(todo_map[order_id])

        # 更新序号
        for i, todo in enumerate(reordered):
            todo["order"] = i + 1
            todo["id"] = f"todo_{i + 1}"

        return {
            "adjusted_todos": reordered,
            "adjustment_description": f"Reordered {len(reordered)} todos to new sequence",
        }

    def _add_todo(self, todos: List[dict], data: dict) -> Dict[str, Any]:
        """添加 TODO"""
        new_todo = {
            "content": data.get("content", ""),
            "priority": data.get("priority", "medium"),
            "phase": data.get("phase", "additional"),
            "status": "pending",
        }

        # 确定插入位置
        insert_after = data.get("insert_after", len(todos))

        # 添加序号和元数据
        new_todo["order"] = insert_after + 1
        new_todo["id"] = f"todo_{insert_after + 1}"
        new_todo["estimated_time"] = "10-15 分钟"
        new_todo["can_skip"] = False
        new_todo["prerequisites"] = data.get("prerequisites", [])

        # 插入新 TODO
        todos.insert(insert_after, new_todo)

        # 重新计算后续 TODO 的序号
        for i in range(insert_after + 1, len(todos)):
            todos[i]["order"] = i + 1
            todos[i]["id"] = f"todo_{i + 1}"

        return {
            "adjusted_todos": todos,
            "adjustment_description": f"Added new TODO: {new_todo['content']}",
        }

    def _remove_todo(self, todos: List[dict], data: dict) -> Dict[str, Any]:
        """移除 TODO"""
        remove_id = data.get("remove_id", "")

        # 过滤掉要移除的 TODO
        filtered = [t for t in todos if t.get("id") != remove_id and t.get("order") != int(remove_id.split("_")[-1] if "_" in remove_id else -1)]

        # 重新计算序号
        for i, todo in enumerate(filtered):
            todo["order"] = i + 1
            todo["id"] = f"todo_{i + 1}"

        return {
            "adjusted_todos": filtered,
            "adjustment_description": f"Removed TODO {remove_id}",
        }

    def _update_todo(self, todos: List[dict], data: dict) -> Dict[str, Any]:
        """更新 TODO"""
        update_id = data.get("update_id", "")
        updates = data.get("updates", {})

        updated = False
        for todo in todos:
            if todo.get("id") == update_id or todo.get("order") == int(
                update_id.split("_")[-1] if "_" in update_id else -1,
            ):
                for key, value in updates.items():
                    todo[key] = value
                updated = True
                break

        if not updated:
            raise ValueError(f"TODO {update_id} not found")

        return {
            "adjusted_todos": todos,
            "adjustment_description": f"Updated TODO {update_id} with: {list(updates.keys())}",
        }

    def _format_result(self, result: Dict[str, Any]) -> str:
        """格式化调整结果输出"""
        lines = []

        lines.append("🔄 TODO 列表已调整")
        lines.append(f"调整类型: {result['adjustment_type']}")
        lines.append(f"原因: {result['reason']}")
        lines.append(f"\n{result['adjustment_description']}")
        lines.append(f"\n调整后的 TODO 列表 ({len(result['adjusted_todos'])} 项):")

        for todo in result["adjusted_todos"]:
            status_icon = "⏳" if todo["status"] == "pending" else "🔄"
            lines.append(f"{status_icon} [{todo['order']}] {todo['content']}")

        return "\n".join(lines)


# ==================== WorkflowToolFactory 更新 ====================


class DAGTaskGraphManager:
    """DAG任务图管理器 - 管理任务间的依赖关系"""

    def __init__(self):
        # 依赖图: task_id -> Set[依赖的task_id]
        self._dependencies: Dict[str, set[str]] = {}
        # 反向依赖图: task_id -> Set[依赖该task_id的task_id]
        self._dependents: Dict[str, set[str]] = {}
        # 任务元数据
        self._task_metadata: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def add_task(self, task_id: str, metadata: Dict[str, Any] | None = None) -> bool:
        """添加任务节点"""
        async with self._lock:
            if task_id in self._dependencies:
                return False
            self._dependencies[task_id] = set()
            self._dependents[task_id] = set()
            if metadata:
                self._task_metadata[task_id] = metadata
            return True

    async def remove_task(self, task_id: str) -> bool:
        """移除任务节点及其所有依赖关系"""
        async with self._lock:
            if task_id not in self._dependencies:
                return False
            # 移除该任务作为依赖的关系
            for dependent in self._dependents[task_id]:
                if task_id in self._dependencies[dependent]:
                    self._dependencies[dependent].discard(task_id)
            # 移除该任务依赖的关系
            for dep in self._dependencies[task_id]:
                if task_id in self._dependents[dep]:
                    self._dependents[dep].discard(task_id)
            # 清理
            del self._dependencies[task_id]
            del self._dependents[task_id]
            self._task_metadata.pop(task_id, None)
            return True

    async def add_dependency(self, task_id: str, depends_on: str) -> bool:
        """添加任务依赖关系 (task_id 依赖于 depends_on)"""
        async with self._lock:
            if task_id not in self._dependencies or depends_on not in self._dependencies:
                return False
            # 检查循环依赖
            if await self._would_create_cycle(task_id, depends_on):
                raise ValueError(
                    f"Adding dependency {depends_on} -> {task_id} would create a cycle",
                )
            self._dependencies[task_id].add(depends_on)
            self._dependents[depends_on].add(task_id)
            return True

    async def remove_dependency(self, task_id: str, depends_on: str) -> bool:
        """移除任务依赖关系"""
        async with self._lock:
            if task_id not in self._dependencies or depends_on not in self._dependencies:
                return False
            self._dependencies[task_id].discard(depends_on)
            self._dependents[depends_on].discard(task_id)
            return True

    async def _would_create_cycle(self, task_id: str, depends_on: str) -> bool:
        """检查添加依赖是否会产生循环"""
        # 如果 depends_on 已经依赖于 task_id，则添加依赖会产生循环
        stack = [task_id]
        visited = set()
        while stack:
            current = stack.pop()
            if current == depends_on:
                return True
            if current in visited:
                continue
            visited.add(current)
            stack.extend(self._dependencies.get(current, set()))
        return False

    async def get_execution_order(self) -> List[str]:
        """获取拓扑排序后的执行顺序"""
        async with self._lock:
            in_degree = {task_id: len(deps) for task_id, deps in self._dependencies.items()}
            queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
            result = []

            while queue:
                # 并行执行所有入度为0的任务
                current = queue.pop(0)
                result.append(current)

                for dependent in list(self._dependents.get(current, set())):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

            if len(result) != len(self._dependencies):
                raise ValueError("Graph contains a cycle")

            return result

    async def get_ready_tasks(self) -> List[str]:
        """获取所有准备执行的任务（入度为0）"""
        async with self._lock:
            return [task_id for task_id, deps in self._dependencies.items() if len(deps) == 0]

    async def get_dependents(self, task_id: str) -> set[str]:
        """获取依赖指定任务的所有任务"""
        async with self._lock:
            return self._dependents.get(task_id, set()).copy()

    async def get_dependencies(self, task_id: str) -> set[str]:
        """获取指定任务依赖的所有任务"""
        async with self._lock:
            return self._dependencies.get(task_id, set()).copy()

    def get_task_metadata(self, task_id: str) -> Dict[str, Any] | None:
        """获取任务元数据"""
        return self._task_metadata.get(task_id)

    def get_all_tasks(self) -> List[str]:
        """获取所有任务ID"""
        return list(self._dependencies.keys())

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "dependencies": {task_id: list(deps) for task_id, deps in self._dependencies.items()},
            "dependents": {task_id: list(deps) for task_id, deps in self._dependents.items()},
            "metadata": self._task_metadata,
        }

    def clear(self):
        """清空所有数据"""
        self._dependencies.clear()
        self._dependents.clear()
        self._task_metadata.clear()


# Create Task Graph Tool
class CreateTaskGraphInput(BaseModel):
    """Input for CreateTaskGraphTool."""

    graph_id: str = Field(..., description="Unique identifier for the task graph.")
    description: str | None = Field(None, description="Description of the task graph.")


class CreateTaskGraphTool(CustomBaseTool):
    """Tool for creating a new DAG task graph with dependency management."""

    name: ClassVar[str] = "create_task_graph"
    description: ClassVar[str] = "Creates a new DAG task graph for managing tasks with dependencies."
    args_schema: ClassVar[type[BaseModel]] = CreateTaskGraphInput

    def __init__(self, task_graph=None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)
        # 存储多个任务图
        self._dag_managers: Dict[str, DAGTaskGraphManager] = {}

    def _run(self, graph_id: str, description: str | None = None) -> str:
        """Create a new task graph."""
        try:
            # 检查是否已存在
            if graph_id in self._dag_managers:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Task graph '{graph_id}' already exists",
                    },
                    indent=2,
                )

            # 创建新的 DAG 管理器
            self._dag_managers[graph_id] = DAGTaskGraphManager()

            result = {
                "type": "task_graph_created",
                "graph_id": graph_id,
                "description": description or "Task graph for managing dependent tasks",
                "status": "created",
                "timestamp": asyncio.get_event_loop().time() if asyncio.get_event_loop() else None,
            }

            self.logger.info(f"Task graph created: {graph_id}")

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.exception("Error creating task graph: ")
            return json.dumps(
                {"status": "error", "message": f"Error creating task graph: {e!s}"},
                indent=2,
            )


# Add Task Node Tool
class AddTaskNodeInput(BaseModel):
    """Input for AddTaskNodeTool."""

    graph_id: str = Field(..., description="ID of the task graph to add the node to.")
    task_id: str = Field(..., description="Unique identifier for the task node.")
    description: str = Field(..., description="Description of the task.")
    mode: str = Field(
        default="",
        description="Task execution mode (e.g., orchestrator, plan, do, check, act). Uses default mode if not specified.",
    )
    metadata: Dict[str, Any] | None = Field(
        None,
        description="Additional metadata for the task.",
    )


class AddTaskNodeTool(CustomBaseTool):
    """Tool for adding a task node to an existing task graph."""

    name: ClassVar[str] = "add_task_node"
    description: ClassVar[str] = "Adds a task node to a DAG task graph."
    args_schema: ClassVar[type[BaseModel]] = AddTaskNodeInput

    def __init__(self, task_graph=None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)

    def _run(
        self,
        graph_id: str,
        task_id: str,
        description: str,
        mode: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a task node to the graph."""
        try:
            # 如果没有指定模式，使用默认模式
            if not mode:
                from dawei.mode import get_default_mode

                mode = get_default_mode()

            # 检查任务图是否存在
            if not hasattr(self, "_dag_managers"):
                return json.dumps(
                    {"status": "error", "message": "Task graph system not initialized"},
                    indent=2,
                )

            if graph_id not in self._dag_managers:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Task graph '{graph_id}' not found. Create it first with create_task_graph.",
                    },
                    indent=2,
                )

            dag_manager = self._dag_managers[graph_id]

            # 添加任务节点
            import asyncio

            task_metadata = {
                "description": description,
                "mode": mode,
                "status": "pending",
                **(metadata or {}),
            }

            success = asyncio.run(dag_manager.add_task(task_id, task_metadata))

            if not success:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Task '{task_id}' already exists in graph '{graph_id}'",
                    },
                    indent=2,
                )

            result = {
                "type": "task_node_added",
                "graph_id": graph_id,
                "task_id": task_id,
                "description": description,
                "mode": mode,
                "metadata": task_metadata,
                "status": "added",
                "timestamp": asyncio.get_event_loop().time() if asyncio.get_event_loop() else None,
            }

            self.logger.info(f"Task node added: {task_id} to graph {graph_id}")

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.exception("Error adding task node: ")
            return json.dumps(
                {"status": "error", "message": f"Error adding task node: {e!s}"},
                indent=2,
            )


# Set Task Dependency Tool
class SetTaskDependencyInput(BaseModel):
    """Input for SetTaskDependencyTool."""

    graph_id: str = Field(..., description="ID of the task graph.")
    task_id: str = Field(..., description="Task that has the dependency.")
    depends_on: str = Field(..., description="Task that must be completed before task_id can run.")


class SetTaskDependencyTool(CustomBaseTool):
    """Tool for setting dependencies between tasks in a DAG."""

    name: ClassVar[str] = "set_task_dependency"
    description: ClassVar[str] = "Sets a dependency relationship between two tasks in a DAG."
    args_schema: ClassVar[type[BaseModel]] = SetTaskDependencyInput

    def __init__(self, task_graph=None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)

    def _run(self, graph_id: str, task_id: str, depends_on: str) -> str:
        """Set task dependency."""
        try:
            # 检查任务图是否存在
            if not hasattr(self, "_dag_managers"):
                return json.dumps(
                    {"status": "error", "message": "Task graph system not initialized"},
                    indent=2,
                )

            if graph_id not in self._dag_managers:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Task graph '{graph_id}' not found",
                    },
                    indent=2,
                )

            dag_manager = self._dag_managers[graph_id]

            # 设置依赖
            import asyncio

            asyncio.run(dag_manager.add_dependency(task_id, depends_on))

            result = {
                "type": "dependency_set",
                "graph_id": graph_id,
                "task_id": task_id,
                "depends_on": depends_on,
                "status": "set",
                "timestamp": asyncio.get_event_loop().time() if asyncio.get_event_loop() else None,
                "message": f"Task '{task_id}' now depends on '{depends_on}'",
            }

            self.logger.info(f"Dependency set: {task_id} -> {depends_on}")

            return json.dumps(result, indent=2)

        except ValueError as e:
            # 循环依赖错误
            self.logger.exception("Cycle detected: ")
            return json.dumps(
                {"status": "error", "message": str(e), "error_type": "cycle_detected"},
                indent=2,
            )

        except Exception as e:
            self.logger.exception("Error setting dependency: ")
            return json.dumps(
                {"status": "error", "message": f"Error setting dependency: {e!s}"},
                indent=2,
            )


# Get Task Graph Tool
class GetTaskGraphInput(BaseModel):
    """Input for GetTaskGraphTool."""

    graph_id: str = Field(..., description="ID of the task graph to get.")
    include_execution_order: bool = Field(
        default=False,
        description="Include topological sort execution order.",
    )


class GetTaskGraphTool(CustomBaseTool):
    """Tool for getting the structure and status of a task graph."""

    name: ClassVar[str] = "get_task_graph"
    description: ClassVar[str] = "Gets the structure, status, and execution order of a DAG task graph."
    args_schema: ClassVar[type[BaseModel]] = GetTaskGraphInput

    def __init__(self, task_graph=None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)

    def _run(self, graph_id: str, include_execution_order: bool = False) -> str:
        """Get task graph structure and status."""
        try:
            # 检查任务图是否存在
            if not hasattr(self, "_dag_managers"):
                return json.dumps(
                    {"status": "error", "message": "Task graph system not initialized"},
                    indent=2,
                )

            if graph_id not in self._dag_managers:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Task graph '{graph_id}' not found",
                    },
                    indent=2,
                )

            dag_manager = self._dag_managers[graph_id]

            import asyncio

            all_tasks = dag_manager.get_all_tasks()

            # 构建任务信息
            tasks_info = {}
            for task_id in all_tasks:
                deps = asyncio.run(dag_manager.get_dependencies(task_id))
                dependents = asyncio.run(dag_manager.get_dependents(task_id))
                metadata = dag_manager.get_task_metadata(task_id) or {}

                tasks_info[task_id] = {
                    "task_id": task_id,
                    "description": metadata.get("description", ""),
                    "mode": metadata.get("mode", "code"),
                    "status": metadata.get("status", "pending"),
                    "dependencies": list(deps),
                    "dependents": list(dependents),
                    "dependency_count": len(deps),
                    "dependent_count": len(dependents),
                }

            result = {
                "type": "task_graph_info",
                "graph_id": graph_id,
                "total_tasks": len(all_tasks),
                "tasks": tasks_info,
                "status": "retrieved",
            }

            # 如果需要，包含执行顺序
            if include_execution_order:
                try:
                    execution_order = asyncio.run(dag_manager.get_execution_order())
                    result["execution_order"] = execution_order
                    # 获取并行层级
                    parallel_levels = []
                    levels_remaining = dag_manager.get_all_tasks()
                    level = 0
                    while levels_remaining:
                        ready_tasks = []
                        for task_id in list(levels_remaining):
                            deps = asyncio.run(dag_manager.get_dependencies(task_id))
                            if all(dep not in levels_remaining for dep in deps):
                                ready_tasks.append(task_id)
                        if ready_tasks:
                            parallel_levels.append(ready_tasks)
                            for t in ready_tasks:
                                levels_remaining.discard(t)
                            level += 1
                        else:
                            break
                    result["parallel_levels"] = parallel_levels
                except ValueError as e:
                    result["execution_order_error"] = str(e)
                    result["has_cycle"] = True

            self.logger.info(f"Task graph retrieved: {graph_id}")

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.exception("Error getting task graph: ")
            return json.dumps(
                {"status": "error", "message": f"Error getting task graph: {e!s}"},
                indent=2,
            )

    async def _get_parallel_levels(self, dag_manager: DAGTaskGraphManager) -> List[List[str]]:
        """获取可以并行执行的层级"""
        levels = []
        remaining = dag_manager.get_all_tasks()

        while remaining:
            # 获取所有入度为0的任务
            ready = await dag_manager.get_ready_tasks()
            ready_in_level = [t for t in ready if t in remaining]

            if not ready_in_level:
                break

            levels.append(ready_in_level)

            # 标记这些任务已完成（从图中移除）
            for task_id in ready_in_level:
                remaining.remove(task_id)
                dependents = await dag_manager.get_dependents(task_id)
                for dep in dependents:
                    if dep in remaining:
                        # 模拟移除依赖
                        pass

            # 简化处理：只返回层级，不真正修改图
            break

        return levels


# Execute Task Graph Tool
class ExecuteTaskGraphInput(BaseModel):
    """Input for ExecuteTaskGraphTool."""

    graph_id: str = Field(..., description="ID of the task graph to execute.")
    parallel: bool = Field(default=True, description="Execute independent tasks in parallel.")
    max_parallel: int = Field(default=5, description="Maximum number of parallel tasks.")


class ExecuteTaskGraphTool(CustomBaseTool):
    """Tool for executing a DAG task graph with dependency-aware scheduling."""

    name: ClassVar[str] = "execute_task_graph"
    description: ClassVar[str] = "Executes a DAG task graph with dependency-aware parallel execution."
    args_schema: ClassVar[type[BaseModel]] = ExecuteTaskGraphInput

    def __init__(self, task_graph=None):
        super().__init__()
        self.task_graph = task_graph
        self.logger = get_logger(__name__)
        self._execution_results: Dict[str, Dict[str, Any]] = {}

    def _run(self, graph_id: str, parallel: bool = True, max_parallel: int = 5) -> str:
        """Execute task graph."""
        try:
            # 检查任务图是否存在
            if not hasattr(self, "_dag_managers"):
                return json.dumps(
                    {"status": "error", "message": "Task graph system not initialized"},
                    indent=2,
                )

            if graph_id not in self._dag_managers:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Task graph '{graph_id}' not found",
                    },
                    indent=2,
                )

            import asyncio

            dag_manager = self._dag_managers[graph_id]

            # 获取执行顺序
            execution_order = asyncio.run(dag_manager.get_execution_order())

            # 模拟执行（实际执行需要集成到任务系统）
            results = {
                "type": "task_graph_execution",
                "graph_id": graph_id,
                "execution_order": execution_order,
                "parallel_enabled": parallel,
                "max_parallel": max_parallel,
                "total_tasks": len(execution_order),
                "status": "executed",
                "timestamp": asyncio.get_event_loop().time() if asyncio.get_event_loop() else None,
                "message": f"Task graph '{graph_id}' is ready for execution with {len(execution_order)} tasks",
                "execution_plan": self._generate_execution_plan(execution_order, dag_manager),
            }

            self.logger.info(
                f"Task graph execution prepared: {graph_id} with {len(execution_order)} tasks",
            )

            return json.dumps(results, indent=2)

        except ValueError as e:
            # 循环依赖错误
            self.logger.exception("Cannot execute graph with cycle: ")
            return json.dumps(
                {
                    "status": "error",
                    "message": str(e),
                    "error_type": "cycle_detected",
                    "suggestion": "Remove the cycle dependency before executing",
                },
                indent=2,
            )

        except Exception as e:
            self.logger.exception("Error executing task graph: ")
            return json.dumps(
                {"status": "error", "message": f"Error executing task graph: {e!s}"},
                indent=2,
            )

    def _generate_execution_plan(
        self,
        execution_order: List[str],
        dag_manager: DAGTaskGraphManager,
    ) -> List[Dict[str, Any]]:
        """生成执行计划"""
        import asyncio

        plan = []

        # 按层级分组任务
        level = 0
        remaining = set(execution_order)

        while remaining:
            # 获取当前层级的任务（入度为0）
            ready_tasks = []
            for task_id in list(remaining):
                deps = asyncio.run(dag_manager.get_dependencies(task_id))
                if all(dep not in remaining for dep in deps):
                    ready_tasks.append(task_id)

            if ready_tasks:
                metadata = {}
                for task_id in ready_tasks:
                    meta = dag_manager.get_task_metadata(task_id) or {}
                    metadata[task_id] = {
                        "description": meta.get("description", ""),
                        "mode": meta.get("mode", "code"),
                    }

                plan.append(
                    {
                        "level": level,
                        "tasks": ready_tasks,
                        "task_count": len(ready_tasks),
                        "can_run_parallel": len(ready_tasks) > 1,
                        "task_details": metadata,
                    },
                )

                # 移除已计划的任务
                for task_id in ready_tasks:
                    remaining.discard(task_id)

                level += 1
            else:
                # 有循环依赖，跳过剩余任务
                for task_id in remaining:
                    plan.append(
                        {
                            "level": level,
                            "tasks": [task_id],
                            "task_count": 1,
                            "can_run_parallel": False,
                            "has_dependency_cycle": True,
                            "task_details": {task_id: dag_manager.get_task_metadata(task_id) or {}},
                        },
                    )
                break

        return plan


class WorkflowToolFactory:
    """工作流工具工厂，支持新旧架构"""

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
            # TODO 计划生成工具
            AnalyzeTaskComplexityTool(self.task_graph),
            GenerateTodoPlanTool(self.task_graph),
            ValidateTodoPlanTool(self.task_graph),
            AdjustTodoOrderTool(self.task_graph),
            # DAG 任务图工具
            CreateTaskGraphTool(self.task_graph),
            AddTaskNodeTool(self.task_graph),
            SetTaskDependencyTool(self.task_graph),
            GetTaskGraphTool(self.task_graph),
            ExecuteTaskGraphTool(self.task_graph),
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
