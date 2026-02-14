# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Fine-grained exception types following Fast Fail principle.

Avoids generic Exception catching for better error handling.
"""

from typing import Any


class BaseError(Exception):
    """Base class for all custom exceptions."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


# Validation Errors
class ValidationError(BaseError):
    """Input validation failed."""

    def __init__(self, field_name: str, value: Any, reason: str):
        super().__init__(
            f"Validation failed for '{field_name}': {reason}",
            {"field": field_name, "value": value},
        )
        self.field_name = field_name
        self.value = value


class InvalidInputError(ValidationError):
    """Invalid input."""


class MissingRequiredFieldError(ValidationError):
    """Missing required field."""


class InvalidParameterError(ValidationError):
    """Invalid parameter."""


# Configuration Errors
class ConfigurationError(BaseError):
    """Configuration error."""


class MissingConfigurationError(ConfigurationError):
    """Missing configuration."""


class InvalidConfigurationError(ConfigurationError):
    """Invalid configuration."""


# State Errors
class StateError(BaseError):
    """State error."""


class InvalidStateError(StateError):
    """Invalid state."""


class StateTransitionError(StateError):
    """State transition error."""


# Resource Errors
class ResourceError(BaseError):
    """Resource error."""


class NotFoundError(ResourceError):
    """Resource not found."""


class AlreadyExistsError(ResourceError):
    """Resource already exists."""


class FileOperationError(ResourceError):
    """File operation error."""


# Permission Errors
class PermissionError(BaseError):
    """Permission error."""


class UnauthorizedError(PermissionError):
    """Unauthorized."""


class ForbiddenError(PermissionError):
    """Forbidden."""


# Execution Errors
class ExecutionError(BaseError):
    """Execution error."""


class TaskExecutionError(ExecutionError):
    """Task execution error."""


class ToolExecutionError(ExecutionError):
    """Tool execution error."""


class CommandExecutionError(ExecutionError):
    """Command execution error."""


# Communication Errors
class CommunicationError(BaseError):
    """Communication error."""


class WebSocketError(CommunicationError):
    """WebSocket error."""


class SessionNotFoundError(CommunicationError):
    """Session not found."""


class InvalidSessionError(CommunicationError):
    """Invalid session."""


# Agent Errors
class AgentError(BaseError):
    """Agent error."""


class AgentInitializationError(AgentError):
    """Agent initialization error."""


class AgentExecutionError(AgentError):
    """Agent execution error."""


class AgentNotFoundError(AgentError):
    """Agent not found."""


# LLM Errors
class LLMError(BaseError):
    """LLM error."""


class LLMConnectionError(LLMError):
    """LLM connection error."""


class LLMTimeoutError(LLMError):
    """LLM timeout error."""


class LLMRateLimitError(LLMError):
    """LLM rate limit error."""


class LLMResponseError(LLMError):
    """LLM response error."""


# Workspace Errors
class WorkspaceError(BaseError):
    """Workspace error."""


class WorkspaceNotFoundError(WorkspaceError):
    """Workspace not found."""


class WorkspaceInitializationError(WorkspaceError):
    """Workspace initialization error."""


# Checkpoint Errors
class CheckpointError(BaseError):
    """Checkpoint error."""


class CheckpointNotFoundError(CheckpointError):
    """Checkpoint not found."""


class CheckpointRestoreError(CheckpointError):
    """Checkpoint restore error."""


# Task Graph Errors
class TaskGraphError(BaseError):
    """Task graph error."""


class TaskNotFoundError(TaskGraphError):
    """Task not found."""


class CycleDetectedError(TaskGraphError):
    """Cycle detected."""


# Tool Errors
class ToolError(BaseError):
    """Tool error."""


class ToolNotFoundError(ToolError):
    """Tool not found."""


class ToolSecurityError(ToolError):
    """Tool security error."""


class ToolTimeoutError(ToolError):
    """Tool timeout."""


# Sandbox Errors
class SandboxError(BaseError):
    """Sandbox error."""


class DockerConnectionError(SandboxError):
    """Docker connection error."""


class ResourceLimitError(SandboxError):
    """Resource limit error."""


class SandboxTimeoutError(SandboxError):
    """Sandbox timeout error."""


class SandboxSecurityError(SandboxError):
    """Sandbox security error."""


# Circuit Breaker Errors
class CircuitBreakerError(BaseError):
    """Circuit breaker error."""


class CircuitBreakerOpenError(CircuitBreakerError):
    """Circuit breaker is open."""
