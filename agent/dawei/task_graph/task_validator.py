# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""任务验证器
新架构中提供统一的数据验证机制
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from dawei.entity.task_types import TaskStatus
from dawei.entity.user_input_message import UserInputText
from dawei.logg.logging import get_logger

from .task_node import TaskNode
from .task_node_data import TaskContext, TaskData, ValidationResult
from .todo_models import TodoItem, TodoStatus


class ValidationRule(ABC):
    """验证规则基类"""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description

    @abstractmethod
    def validate(self, data: Any) -> ValidationResult:
        """执行验证"""


class TaskDataValidationRule(ValidationRule):
    """任务数据验证规则"""

    def __init__(self):
        super().__init__("task_data_validation", "Validates task data fields")

    def validate(self, task_data: TaskData) -> ValidationResult:
        """验证任务数据"""
        result = ValidationResult(is_valid=True)

        # 检查任务ID
        if not task_data.task_node_id or not task_data.task_node_id.strip():
            result.add_error("Task ID is required")
        elif len(task_data.task_node_id) > 100:
            result.add_error("Task ID is too long (max 100 characters)")

        # 检查任务描述
        description_text = ""
        if isinstance(task_data.description, UserInputText):
            description_text = task_data.description.text or ""
        elif isinstance(task_data.description, str):
            description_text = task_data.description
        else:
            result.add_error("Task description must be a string or UserInputText object")

        if not description_text or not description_text.strip():
            result.add_error("Task description is required")
        elif len(description_text) > 2000:
            result.add_error("Task description is too long (max 2000 characters)")
        elif len(description_text) < 10:
            result.add_warning("Task description is very short (less than 10 characters)")

        # 检查模式
        if not task_data.mode or not task_data.mode.strip():
            result.add_error("Task mode is required")

        # 检查状态
        if not isinstance(task_data.status, TaskStatus):
            result.add_error("Invalid task status")

        # 检查优先级
        if not hasattr(task_data, "priority") or task_data.priority is None:
            result.add_warning("Task priority not set")

        # 检查上下文
        if not task_data.context:
            result.add_error("Task context is required")
        else:
            context_result = self._validate_context(task_data.context)
            if not context_result.is_valid:
                result.errors.extend(context_result.errors)
            result.warnings.extend(context_result.warnings)

        # 检查TODO列表
        if task_data.todos is None:
            result.add_error("TODO list cannot be None")
        else:
            todo_result = self._validate_todo_list(task_data.todos)
            if not todo_result.is_valid:
                result.errors.extend(todo_result.errors)
            result.warnings.extend(todo_result.warnings)

        return result

    def _validate_context(self, context: TaskContext) -> ValidationResult:
        """验证上下文"""
        result = ValidationResult(is_valid=True)

        if not context.user_id or not context.user_id.strip():
            result.add_error("Context user ID is required")

        if not context.session_id or not context.session_id.strip():
            result.add_error("Context session ID is required")

        if not context.message_id or not context.message_id.strip():
            result.add_error("Context message ID is required")

        return result

    def _validate_todo_list(self, todos: list[TodoItem]) -> ValidationResult:
        """验证TODO列表"""
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
            todo_result = self._validate_todo_item(todo)
            if not todo_result.is_valid:
                result.errors.extend(todo_result.errors)
            result.warnings.extend(todo_result.warnings)

        return result

    def _validate_todo_item(self, todo: TodoItem) -> ValidationResult:
        """验证单个TODO项"""
        result = ValidationResult(is_valid=True)

        if not todo.id or not todo.id.strip():
            result.add_error("TODO item ID is required")

        if not todo.content or not todo.content.strip():
            result.add_error("TODO item content is required")
        elif len(todo.content) > 500:
            result.add_warning("TODO item content is very long (>500 characters)")

        if not isinstance(todo.status, TodoStatus):
            result.add_error("Invalid TODO status")

        return result


class TaskNodeValidationRule(ValidationRule):
    """任务节点验证规则"""

    def __init__(self):
        super().__init__("task_node_validation", "Validates task node structure")

    def validate(self, task_node: TaskNode) -> ValidationResult:
        """验证任务节点"""
        result = ValidationResult(is_valid=True)

        # 检查基础属性
        if not task_node.task_node_id or not task_node.task_node_id.strip():
            result.add_error("Task node ID is required")

        if not task_node.data:
            result.add_error("Task node data is required")
        else:
            # 验证任务数据
            data_rule = TaskDataValidationRule()
            data_result = data_rule.validate(task_node.data)
            if not data_result.is_valid:
                result.errors.extend(data_result.errors)
            result.warnings.extend(data_result.warnings)

        # 检查ID一致性
        if task_node.data and task_node.task_node_id != task_node.data.task_id:
            result.add_error("Task node ID and data task ID mismatch")

        # 检查循环依赖
        if task_node.parent_id == task_node.task_node_id:
            result.add_error("Task node cannot be its own parent")

        if task_node.task_node_id in task_node.child_ids:
            result.add_error("Task node cannot be its own child")

        return result


class StatusTransitionValidationRule(ValidationRule):
    """状态转换验证规则"""

    def __init__(self):
        super().__init__("status_transition_validation", "Validates status transitions")

        # 定义允许的状态转换
        self.valid_transitions = {
            TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.ABORTED},
            TaskStatus.RUNNING: {
                TaskStatus.PAUSED,
                TaskStatus.COMPLETED,
                TaskStatus.ABORTED,
                TaskStatus.FAILED,
            },
            TaskStatus.PAUSED: {TaskStatus.RUNNING, TaskStatus.ABORTED},
            TaskStatus.COMPLETED: set(),
            TaskStatus.ABORTED: {TaskStatus.PENDING, TaskStatus.RUNNING},
        }

    def validate(self, transition_data: dict[str, Any]) -> ValidationResult:
        """验证状态转换"""
        result = ValidationResult(is_valid=True)

        from_status = transition_data.get("from_status")
        to_status = transition_data.get("to_status")

        if not from_status or not to_status:
            result.add_error("Both from_status and to_status are required")
            return result

        if not isinstance(from_status, TaskStatus) or not isinstance(to_status, TaskStatus):
            result.add_error("Status must be TaskStatus enum")
            return result

        # 相同状态不需要转换
        if from_status == to_status:
            result.add_warning(f"No status change needed: {from_status.value}")
            return result

        # 检查是否为有效转换
        valid_targets = self.valid_transitions.get(from_status, set())
        if to_status not in valid_targets:
            result.add_error(
                f"Invalid status transition: {from_status.value} -> {to_status.value}. Valid targets: {[s.value for s in valid_targets]}",
            )

        return result


class TaskValidator:
    """任务验证器"""

    def __init__(self):
        self._rules: list[ValidationRule] = []
        self.logger = get_logger(__name__)
        self._setup_default_rules()

    def _setup_default_rules(self):
        """设置默认验证规则"""
        self._rules = [
            TaskDataValidationRule(),
            TaskNodeValidationRule(),
            StatusTransitionValidationRule(),
        ]

    def validate_task_data(self, task_data: TaskData) -> ValidationResult:
        """验证任务数据"""
        result = ValidationResult(is_valid=True)

        for rule in self._rules:
            if isinstance(rule, TaskDataValidationRule):
                rule_result = rule.validate(task_data)
                if not rule_result.is_valid:
                    result.errors.extend(rule_result.errors)
                result.warnings.extend(rule_result.warnings)

        self.logger.debug(
            f"Task data validation: {len(result.errors)} errors, {len(result.warnings)} warnings",
        )
        return result

    def validate_todo_item(self, todo: TodoItem) -> ValidationResult:
        """验证TODO项"""
        rule = TaskDataValidationRule()
        result = rule._validate_todo_item(todo)

        self.logger.debug(
            f"TODO item validation: {len(result.errors)} errors, {len(result.warnings)} warnings",
        )
        return result

    def validate_status_transition(
        self,
        from_status: TaskStatus,
        to_status: TaskStatus,
    ) -> ValidationResult:
        """验证状态转换"""
        transition_data = {"from_status": from_status, "to_status": to_status}

        for rule in self._rules:
            if isinstance(rule, StatusTransitionValidationRule):
                result = rule.validate(transition_data)
                self.logger.debug(
                    f"Status transition validation: {len(result.errors)} errors, {len(result.warnings)} warnings",
                )
                return result

        # 如果没有找到规则，返回默认结果
        return ValidationResult(is_valid=True)

    def validate_context(self, context: TaskContext) -> ValidationResult:
        """验证上下文"""
        rule = TaskDataValidationRule()
        result = rule._validate_context(context)

        self.logger.debug(
            f"Context validation: {len(result.errors)} errors, {len(result.warnings)} warnings",
        )
        return result

    def validate_task_node(self, task_node: TaskNode) -> ValidationResult:
        """验证任务节点"""
        result = ValidationResult(is_valid=True)

        for rule in self._rules:
            if isinstance(rule, TaskNodeValidationRule):
                rule_result = rule.validate(task_node)
                if not rule_result.is_valid:
                    result.errors.extend(rule_result.errors)
                result.warnings.extend(rule_result.warnings)

        self.logger.debug(
            f"Task node validation: {len(result.errors)} errors, {len(result.warnings)} warnings",
        )
        return result

    def add_rule(self, rule: ValidationRule) -> None:
        """添加验证规则"""
        self._rules.append(rule)
        self.logger.info(f"Added validation rule: {rule.name}")

    def remove_rule(self, rule_name: str) -> bool:
        """移除验证规则"""
        for i, rule in enumerate(self._rules):
            if rule.name == rule_name:
                removed_rule = self._rules.pop(i)
                self.logger.info(f"Removed validation rule: {removed_rule.name}")
                return True

        self.logger.warning(f"Validation rule not found: {rule_name}")
        return False

    def get_rules(self) -> list[str]:
        """获取所有规则名称"""
        return [rule.name for rule in self._rules]

    def validate_with_custom_rule(
        self,
        data: Any,
        rule_name: str,
        validator_func: Callable[[Any], ValidationResult],
    ) -> ValidationResult:
        """使用自定义规则验证"""
        result = validator_func(data)
        self.logger.debug(
            f"Custom rule '{rule_name}' validation: {len(result.errors)} errors, {len(result.warnings)} warnings",
        )
        return result
