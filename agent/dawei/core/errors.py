# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""核心错误处理模块
实现架构设计文档中定义的错误分类体系
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorSeverity(Enum):
    """错误严重程度"""

    CRITICAL = "critical"  # 系统级故障，需要立即处理
    HIGH = "high"  # 严重影响功能，需要尽快处理
    MEDIUM = "medium"  # 部分功能受影响，可以稍后处理
    LOW = "low"  # 轻微影响，记录即可
    INFO = "info"  # 信息性错误，仅用于记录


class ErrorCategory(Enum):
    """错误分类"""

    SYSTEM = "system"  # 系统级错误
    BUSINESS = "business"  # 业务逻辑错误
    INTEGRATION = "integration"  # 集成错误
    USER = "user"  # 用户操作错误


class RecoveryStrategy(Enum):
    """错误恢复策略"""

    NONE = "none"  # 不进行恢复
    RETRY = "retry"  # 重试
    FALLBACK = "fallback"  # 降级处理
    CIRCUIT_BREAKER = "circuit_breaker"  # 熔断
    MANUAL_INTERVENTION = "manual_intervention"  # 人工干预


@dataclass
class ErrorContext:
    """错误上下文"""

    component: str
    operation: str | None = None
    task_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    args: tuple = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    additional_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClassifiedError:
    """分类后的错误"""

    error: Exception
    category: ErrorCategory
    severity: ErrorSeverity
    recovery_strategy: RecoveryStrategy
    context: ErrorContext
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "error_type": self.error.__class__.__name__,
            "error_message": str(self.error),
            "category": self.category.value,
            "severity": self.severity.value,
            "recovery_strategy": self.recovery_strategy.value,
            "context": {
                "component": self.context.component,
                "operation": self.context.operation,
                "task_id": self.context.task_id,
                "user_id": self.context.user_id,
                "session_id": self.context.session_id,
                "trace_id": self.context.trace_id,
                "additional_context": self.context.additional_context,
            },
            "timestamp": self.timestamp,
        }


@dataclass
class RecoveryResult:
    """恢复结果"""

    success: bool
    strategy: RecoveryStrategy
    fallback_value: Any | None = None
    retry_count: int = 0
    recovery_message: str | None = None
    additional_info: dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorResult:
    """错误处理结果"""

    error: ClassifiedError
    context: ErrorContext
    recovery_result: RecoveryResult


# 基础错误类层次结构
class GeweiError(Exception):
    """基础错误类"""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details,
            "timestamp": self.timestamp,
        }


# 系统级错误
class SystemError(GeweiError):
    """系统级错误"""


class ConfigurationError(SystemError):
    """配置错误"""

    def __init__(self, message: str, config_key: str | None = None):
        super().__init__(
            f"Configuration error: {message}",
            error_code="CONFIGURATION_ERROR",
            details={"config_key": config_key},
        )


class ResourceError(SystemError):
    """资源错误"""

    def __init__(self, resource_type: str, resource_id: str, reason: str):
        super().__init__(
            f"Resource error for {resource_type}:{resource_id} - {reason}",
            error_code="RESOURCE_ERROR",
            details={
                "resource_type": resource_type,
                "resource_id": resource_id,
                "reason": reason,
            },
        )


class InfrastructureError(SystemError):
    """基础设施错误"""

    def __init__(self, component: str, reason: str):
        super().__init__(
            f"Infrastructure error in {component}: {reason}",
            error_code="INFRASTRUCTURE_ERROR",
            details={"component": component, "reason": reason},
        )


# 业务逻辑错误
class BusinessError(GeweiError):
    """业务逻辑错误"""


class TaskError(BusinessError):
    """任务相关错误"""


class TaskNotFoundError(TaskError):
    """任务未找到错误"""

    def __init__(self, task_id: str):
        super().__init__(
            f"Task not found: {task_id}",
            error_code="TASK_NOT_FOUND",
            details={"task_id": task_id},
        )


class TaskExecutionError(TaskError):
    """任务执行错误"""

    def __init__(self, task_id: str, reason: str):
        super().__init__(
            f"Task execution failed: {task_id} - {reason}",
            error_code="TASK_EXECUTION_ERROR",
            details={"task_id": task_id, "reason": reason},
        )


class TaskStateError(TaskError):
    """任务状态错误"""

    def __init__(self, task_id: str, current_state: str, expected_state: str):
        super().__init__(
            f"Task {task_id} is in {current_state}, expected {expected_state}",
            error_code="TASK_STATE_ERROR",
            details={
                "task_id": task_id,
                "current_state": current_state,
                "expected_state": expected_state,
            },
        )


class ToolError(BusinessError):
    """工具相关错误"""


class ToolNotFoundError(ToolError):
    """工具未找到错误"""

    def __init__(self, tool_name: str):
        super().__init__(
            f"Tool not found: {tool_name}",
            error_code="TOOL_NOT_FOUND",
            details={"tool_name": tool_name},
        )


class ToolExecutionError(ToolError):
    """工具执行错误"""

    def __init__(self, tool_name: str, reason: str):
        super().__init__(
            f"Tool execution failed: {tool_name} - {reason}",
            error_code="TOOL_EXECUTION_ERROR",
            details={"tool_name": tool_name, "reason": reason},
        )


class ToolSecurityError(ToolError):
    """工具安全错误"""

    def __init__(self, tool_name: str, security_issue: str):
        super().__init__(
            f"Tool security violation: {tool_name} - {security_issue}",
            error_code="TOOL_SECURITY_ERROR",
            details={"tool_name": tool_name, "security_issue": security_issue},
        )


class ModeError(BusinessError):
    """模式相关错误"""


class ModeSwitchError(ModeError):
    """模式切换错误"""

    def __init__(self, from_mode: str, to_mode: str, reason: str):
        super().__init__(
            f"Mode switch failed from {from_mode} to {to_mode}: {reason}",
            error_code="MODE_SWITCH_ERROR",
            details={"from_mode": from_mode, "to_mode": to_mode, "reason": reason},
        )


class ModeValidationError(ModeError):
    """模式验证错误"""

    def __init__(self, mode: str, validation_error: str):
        super().__init__(
            f"Mode validation failed for {mode}: {validation_error}",
            error_code="MODE_VALIDATION_ERROR",
            details={"mode": mode, "validation_error": validation_error},
        )


# 集成错误
class IntegrationError(GeweiError):
    """集成错误"""


class LLMError(IntegrationError):
    """LLM调用错误"""

    def __init__(self, provider: str, reason: str):
        super().__init__(
            f"LLM error from {provider}: {reason}",
            error_code="LLM_ERROR",
            details={"provider": provider, "reason": reason},
        )


class WebSocketError(IntegrationError):
    """WebSocket错误"""

    def __init__(self, operation: str, reason: str):
        super().__init__(
            f"WebSocket error during {operation}: {reason}",
            error_code="WEBSOCKET_ERROR",
            details={"operation": operation, "reason": reason},
        )


class StorageError(IntegrationError):
    """存储错误"""

    def __init__(self, operation: str, resource: str, reason: str):
        super().__init__(
            f"Storage error during {operation} on {resource}: {reason}",
            error_code="STORAGE_ERROR",
            details={"operation": operation, "resource": resource, "reason": reason},
        )


# 用户操作错误
class UserError(GeweiError):
    """用户操作错误"""


class ValidationError(UserError):
    """验证错误"""

    def __init__(self, field: str, value: str, constraint: str):
        super().__init__(
            f"Validation failed for {field}: {value} (constraint: {constraint})",
            error_code="VALIDATION_ERROR",
            details={"field": field, "value": value, "constraint": constraint},
        )


class PermissionError(UserError):
    """权限错误"""

    def __init__(self, operation: str, resource: str, user_id: str):
        super().__init__(
            f"Permission denied for {operation} on {resource} by user {user_id}",
            error_code="PERMISSION_ERROR",
            details={"operation": operation, "resource": resource, "user_id": user_id},
        )


# 状态转换错误
class StateTransitionError(BusinessError):
    """状态转换错误"""

    def __init__(self, from_state: str, to_state: str, reason: str):
        super().__init__(
            f"Invalid state transition from {from_state} to {to_state}: {reason}",
            error_code="STATE_TRANSITION_ERROR",
            details={"from_state": from_state, "to_state": to_state, "reason": reason},
        )


# 检查点错误
class CheckpointError(SystemError):
    """检查点错误"""

    def __init__(self, checkpoint_id: str, reason: str):
        super().__init__(
            f"Checkpoint error: {checkpoint_id} - {reason}",
            error_code="CHECKPOINT_ERROR",
            details={"checkpoint_id": checkpoint_id, "reason": reason},
        )


# 熔断器错误
class CircuitBreakerError(IntegrationError):
    """熔断器错误"""

    def __init__(self, service: str, reason: str):
        super().__init__(
            f"Circuit breaker open for {service}: {reason}",
            error_code="CIRCUIT_BREAKER_ERROR",
            details={"service": service, "reason": reason},
        )
