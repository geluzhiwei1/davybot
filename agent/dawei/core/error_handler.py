"""Unified error handling mechanism."""

import asyncio
import functools
import inspect
from collections.abc import Callable
from typing import Any

from .errors import (
    CheckpointError,
    CircuitBreakerError,
    ClassifiedError,
    ConfigurationError,
    ErrorCategory,
    ErrorContext,
    ErrorResult,
    ErrorSeverity,
    GeweiError,
    InfrastructureError,
    LLMError,
    ModeSwitchError,
    ModeValidationError,
    PermissionError,
    RecoveryResult,
    RecoveryStrategy,
    ResourceError,
    StateTransitionError,
    StorageError,
    TaskExecutionError,
    TaskNotFoundError,
    TaskStateError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolSecurityError,
    ValidationError,
    WebSocketError,
)


class ErrorRegistry:
    """Error type registry."""

    def __init__(self):
        self._error_mappings: dict[type[Exception], ErrorCategory] = {}
        self._severity_rules: dict[type[Exception], ErrorSeverity] = {}
        self._recovery_strategies: dict[type[Exception], RecoveryStrategy] = {}
        self._register_default_errors()

    def _register_default_errors(self):
        """Register default error type mappings."""
        # System-level errors
        self.register_error_type(
            ConfigurationError,
            ErrorCategory.SYSTEM,
            ErrorSeverity.HIGH,
            RecoveryStrategy.MANUAL_INTERVENTION,
        )
        self.register_error_type(
            ResourceError,
            ErrorCategory.SYSTEM,
            ErrorSeverity.MEDIUM,
            RecoveryStrategy.RETRY,
        )
        self.register_error_type(
            InfrastructureError,
            ErrorCategory.SYSTEM,
            ErrorSeverity.CRITICAL,
            RecoveryStrategy.MANUAL_INTERVENTION,
        )
        self.register_error_type(
            CheckpointError,
            ErrorCategory.SYSTEM,
            ErrorSeverity.MEDIUM,
            RecoveryStrategy.RETRY,
        )

        # Business logic errors
        self.register_error_type(
            TaskNotFoundError,
            ErrorCategory.BUSINESS,
            ErrorSeverity.MEDIUM,
            RecoveryStrategy.NONE,
        )
        self.register_error_type(
            TaskExecutionError,
            ErrorCategory.BUSINESS,
            ErrorSeverity.HIGH,
            RecoveryStrategy.RETRY,
        )
        self.register_error_type(
            TaskStateError,
            ErrorCategory.BUSINESS,
            ErrorSeverity.MEDIUM,
            RecoveryStrategy.NONE,
        )
        self.register_error_type(
            ToolNotFoundError,
            ErrorCategory.BUSINESS,
            ErrorSeverity.MEDIUM,
            RecoveryStrategy.NONE,
        )
        self.register_error_type(
            ToolExecutionError,
            ErrorCategory.BUSINESS,
            ErrorSeverity.HIGH,
            RecoveryStrategy.RETRY,
        )
        self.register_error_type(
            ToolSecurityError,
            ErrorCategory.BUSINESS,
            ErrorSeverity.HIGH,
            RecoveryStrategy.MANUAL_INTERVENTION,
        )
        self.register_error_type(
            ModeSwitchError,
            ErrorCategory.BUSINESS,
            ErrorSeverity.MEDIUM,
            RecoveryStrategy.FALLBACK,
        )
        self.register_error_type(
            ModeValidationError,
            ErrorCategory.BUSINESS,
            ErrorSeverity.LOW,
            RecoveryStrategy.NONE,
        )
        self.register_error_type(
            StateTransitionError,
            ErrorCategory.BUSINESS,
            ErrorSeverity.MEDIUM,
            RecoveryStrategy.NONE,
        )

        # Integration errors
        self.register_error_type(
            LLMError,
            ErrorCategory.INTEGRATION,
            ErrorSeverity.HIGH,
            RecoveryStrategy.RETRY,
        )
        self.register_error_type(
            WebSocketError,
            ErrorCategory.INTEGRATION,
            ErrorSeverity.MEDIUM,
            RecoveryStrategy.RETRY,
        )
        self.register_error_type(
            StorageError,
            ErrorCategory.INTEGRATION,
            ErrorSeverity.HIGH,
            RecoveryStrategy.RETRY,
        )
        self.register_error_type(
            CircuitBreakerError,
            ErrorCategory.INTEGRATION,
            ErrorSeverity.HIGH,
            RecoveryStrategy.CIRCUIT_BREAKER,
        )

        # User operation errors
        self.register_error_type(
            ValidationError,
            ErrorCategory.USER,
            ErrorSeverity.LOW,
            RecoveryStrategy.NONE,
        )
        self.register_error_type(
            PermissionError,
            ErrorCategory.USER,
            ErrorSeverity.MEDIUM,
            RecoveryStrategy.NONE,
        )

        # Common exceptions
        self.register_error_type(
            ValueError,
            ErrorCategory.USER,
            ErrorSeverity.LOW,
            RecoveryStrategy.NONE,
        )
        self.register_error_type(
            TypeError,
            ErrorCategory.USER,
            ErrorSeverity.LOW,
            RecoveryStrategy.NONE,
        )
        self.register_error_type(
            KeyError,
            ErrorCategory.BUSINESS,
            ErrorSeverity.MEDIUM,
            RecoveryStrategy.NONE,
        )
        self.register_error_type(
            ConnectionError,
            ErrorCategory.INTEGRATION,
            ErrorSeverity.HIGH,
            RecoveryStrategy.RETRY,
        )
        self.register_error_type(
            TimeoutError,
            ErrorCategory.INTEGRATION,
            ErrorSeverity.MEDIUM,
            RecoveryStrategy.RETRY,
        )

    def register_error_type(
        self,
        error_class: type[Exception],
        error_category: ErrorCategory,
        default_severity: ErrorSeverity,
        recovery_strategy: RecoveryStrategy,
    ):
        """Register error type."""
        self._error_mappings[error_class] = error_category
        self._severity_rules[error_class] = default_severity
        self._recovery_strategies[error_class] = recovery_strategy

    def get_error_category(self, error: Exception) -> ErrorCategory:
        """Get error category."""
        error_type = type(error)

        # Exact match
        if error_type in self._error_mappings:
            return self._error_mappings[error_type]

        # Inheritance match
        for registered_type, category in self._error_mappings.items():
            if issubclass(error_type, registered_type):
                return category

        # Default category
        if isinstance(error, GeweiError):
            return ErrorCategory.BUSINESS
        return ErrorCategory.SYSTEM

    def get_error_severity(self, error: Exception) -> ErrorSeverity:
        """Get error severity."""
        error_type = type(error)

        # Exact match
        if error_type in self._severity_rules:
            return self._severity_rules[error_type]

        # Inheritance match
        for registered_type, severity in self._severity_rules.items():
            if issubclass(error_type, registered_type):
                return severity

        # Default severity
        if isinstance(error, GeweiError):
            return ErrorSeverity.MEDIUM
        return ErrorSeverity.HIGH

    def get_recovery_strategy(self, error: Exception) -> RecoveryStrategy:
        """Get recovery strategy."""
        error_type = type(error)

        # Exact match
        if error_type in self._recovery_strategies:
            return self._recovery_strategies[error_type]

        # Inheritance match
        for registered_type, strategy in self._recovery_strategies.items():
            if issubclass(error_type, registered_type):
                return strategy

        # Default strategy
        return RecoveryStrategy.NONE


class ContextCollector:
    """Error context collector."""

    def __init__(self):
        self.collectors: list[Callable] = []

    async def collect(self, base_context: ErrorContext) -> dict[str, Any]:
        """Collect complete error context."""
        context_data = {
            "base_context": {
                "component": base_context.component,
                "operation": base_context.operation,
                "task_id": base_context.task_id,
                "user_id": base_context.user_id,
                "session_id": base_context.session_id,
                "trace_id": base_context.trace_id,
            },
            "additional_context": base_context.additional_context,
        }

        # Execute all collectors
        for collector in self.collectors:
            try:
                collected_data = await collector(base_context)
                if collected_data:
                    context_data.update(collected_data)
            except Exception as e:
                # Context collection failure should not affect error handling
                import logging

                logging.getLogger(__name__).warning(f"Context collector failed: {e}")

        return context_data

    def register_collector(self, collector: Callable):
        """Register context collector."""
        self.collectors.append(collector)


class RecoveryExecutor:
    """Recovery executor."""

    def __init__(self):
        self.retry_configs: dict[str, dict[str, Any]] = {
            "default": {
                "max_attempts": 3,
                "base_delay": 1.0,
                "max_delay": 60.0,
                "backoff_factor": 2.0,
            },
        }

    async def execute_recovery(
        self,
        error: ClassifiedError,
        context: ErrorContext,
        original_func: Callable | None = None,
        original_args: tuple | None = None,
        original_kwargs: dict[str, Any] | None = None,
    ) -> RecoveryResult:
        """Execute recovery strategy."""
        strategy = error.recovery_strategy

        if strategy == RecoveryStrategy.NONE:
            return RecoveryResult(success=False, strategy=strategy)

        if strategy == RecoveryStrategy.RETRY:
            return await self._execute_retry(
                error,
                context,
                original_func,
                original_args,
                original_kwargs,
            )

        if strategy == RecoveryStrategy.FALLBACK:
            return await self._execute_fallback(error, context)

        if strategy == RecoveryStrategy.CIRCUIT_BREAKER:
            return await self._execute_circuit_breaker(error, context)

        if strategy == RecoveryStrategy.MANUAL_INTERVENTION:
            return await self._execute_manual_intervention(error, context)

        return RecoveryResult(
            success=False,
            strategy=strategy,
            recovery_message="Unknown recovery strategy",
        )

    async def _execute_retry(
        self,
        error: ClassifiedError,
        context: ErrorContext,
        original_func: Callable | None = None,
        original_args: tuple | None = None,
        original_kwargs: dict[str, Any] | None = None,
    ) -> RecoveryResult:
        """Execute retry strategy."""
        if not original_func:
            return RecoveryResult(
                success=False,
                strategy=RecoveryStrategy.RETRY,
                recovery_message="No function to retry",
            )

        config = self.retry_configs.get("default", {})
        max_attempts = config.get("max_attempts", 3)
        base_delay = config.get("base_delay", 1.0)
        max_delay = config.get("max_delay", 60.0)
        backoff_factor = config.get("backoff_factor", 2.0)

        last_error = None

        for attempt in range(max_attempts):
            try:
                if inspect.iscoroutinefunction(original_func):
                    result = await original_func(*(original_args or ()), **(original_kwargs or {}))
                else:
                    result = original_func(*(original_args or ()), **(original_kwargs or {}))

                return RecoveryResult(
                    success=True,
                    strategy=RecoveryStrategy.RETRY,
                    retry_count=attempt + 1,
                    recovery_message=f"Retry succeeded after {attempt + 1} attempts",
                    fallback_value=result,
                )
            except Exception as e:
                last_error = e
                if attempt == max_attempts - 1:
                    break

                delay = min(base_delay * (backoff_factor**attempt), max_delay)
                await asyncio.sleep(delay)

        return RecoveryResult(
            success=False,
            strategy=RecoveryStrategy.RETRY,
            retry_count=max_attempts,
            recovery_message=f"Retry failed after {max_attempts} attempts: {last_error!s}",
        )

    async def _execute_fallback(
        self,
        error: ClassifiedError,
        context: ErrorContext,
    ) -> RecoveryResult:
        """Execute fallback strategy."""
        # Provide different fallback based on error type
        if isinstance(error.error, ToolExecutionError):
            return RecoveryResult(
                success=True,
                strategy=RecoveryStrategy.FALLBACK,
                fallback_value={"success": False, "error": str(error.error)},
                recovery_message="Tool execution failed, returning error response",
            )

        if isinstance(error.error, LLMError):
            return RecoveryResult(
                success=True,
                strategy=RecoveryStrategy.FALLBACK,
                fallback_value="I'm sorry, I'm currently experiencing issues with my language model. Please try again later.",
                recovery_message="LLM error, using fallback response",
            )

        return RecoveryResult(
            success=False,
            strategy=RecoveryStrategy.FALLBACK,
            recovery_message="No fallback available for this error type",
        )

    async def _execute_circuit_breaker(
        self,
        error: ClassifiedError,
        context: ErrorContext,
    ) -> RecoveryResult:
        """Execute circuit breaker strategy."""
        return RecoveryResult(
            success=False,
            strategy=RecoveryStrategy.CIRCUIT_BREAKER,
            recovery_message="Circuit breaker is open, service temporarily unavailable",
        )

    async def _execute_manual_intervention(
        self,
        error: ClassifiedError,
        context: ErrorContext,
    ) -> RecoveryResult:
        """Execute manual intervention strategy."""
        # Log errors requiring manual intervention
        import logging

        logger = logging.getLogger(__name__)
        logger.critical(
            f"Manual intervention required for {error.error.__class__.__name__}: {error.error}",
            extra={"error_details": error.to_dict(), "context": context.__dict__},
        )

        return RecoveryResult(
            success=False,
            strategy=RecoveryStrategy.MANUAL_INTERVENTION,
            recovery_message="Error requires manual intervention",
        )


class ErrorHandler:
    """Unified error handler."""

    def __init__(self):
        self.error_registry = ErrorRegistry()
        self.context_collector = ContextCollector()
        self.recovery_executor = RecoveryExecutor()

    async def handle_error(
        self,
        error: Exception,
        context: ErrorContext,
        original_func: Callable | None = None,
        original_args: tuple | None = None,
        original_kwargs: dict[str, Any] | None = None,
    ) -> ErrorResult:
        """Handle error core method."""
        # 1. Error classification and severity assessment
        classified_error = ClassifiedError(
            error=error,
            category=self.error_registry.get_error_category(error),
            severity=self.error_registry.get_error_severity(error),
            recovery_strategy=self.error_registry.get_recovery_strategy(error),
            context=context,
        )

        # 2. Collect error context
        await self.context_collector.collect(context)

        # 3. Execute recovery strategy
        recovery_result = await self.recovery_executor.execute_recovery(
            classified_error,
            context,
            original_func,
            original_args,
            original_kwargs,
        )

        return ErrorResult(error=classified_error, context=context, recovery_result=recovery_result)

    def classify_error(self, error: Exception, context: ErrorContext) -> ClassifiedError:
        """Classify error."""
        return ClassifiedError(
            error=error,
            category=self.error_registry.get_error_category(error),
            severity=self.error_registry.get_error_severity(error),
            recovery_strategy=self.error_registry.get_recovery_strategy(error),
            context=context,
        )


# Global error handler instance
_global_error_handler: ErrorHandler | None = None


def get_error_handler() -> ErrorHandler:
    """Get global error handler instance."""
    global _global_error_handler
    if _global_error_handler is None:
        _global_error_handler = ErrorHandler()
    return _global_error_handler


def handle_errors(component: str, operation: str = None):
    """Unified error handling decorator."""

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                error_context = ErrorContext(
                    component=component,
                    operation=operation or func.__name__,
                    args=args,
                    kwargs=kwargs,
                )

                error_handler = get_error_handler()
                result = await error_handler.handle_error(e, error_context, func, args, kwargs)

                if not result.recovery_result.success:
                    # Ensure raised exception is BaseException subclass
                    if isinstance(result.error.error, BaseException):
                        raise result.error.error
                    # If not standard exception, wrap as RuntimeError
                    raise RuntimeError(str(result.error.error))

                return result.recovery_result.fallback_value

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Check if in async context
                try:
                    asyncio.get_running_loop()
                    # In async context, re-raise original exception without handling
                    raise
                except RuntimeError:
                    # Not in async context, safe to handle error
                    pass

                error_context = ErrorContext(
                    component=component,
                    operation=operation or func.__name__,
                    args=args,
                    kwargs=kwargs,
                )

                # Sync version error handling
                error_handler = get_error_handler()
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        error_handler.handle_error(e, error_context, func, args, kwargs),
                    )
                finally:
                    loop.close()

                if not result.recovery_result.success:
                    raise result.error

                return result.recovery_result.fallback_value

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator
