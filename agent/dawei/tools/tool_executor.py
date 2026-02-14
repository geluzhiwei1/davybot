# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Tool executor module - Refactored version.

Handles tool execution logic, error handling, and lifecycle management.
Implements IToolCallService interface for integration with the task system.
"""

import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from dawei.async_task.task_manager import AsyncTaskManager
from dawei.async_task.types import RetryPolicy, TaskDefinition, TaskStatus
from dawei.core.error_handler import handle_errors
from dawei.core.errors import (
    PermissionError,
    ToolNotFoundError,
    ToolSecurityError,
    ValidationError,
)
from dawei.core.metrics import increment_counter
from dawei.entity.tool_event_data import ToolCallStartData
from dawei.interfaces.tool_call_service import IToolCallService
from dawei.logg.logging import log_performance
from dawei.task_graph.task_node_data import TaskContext
from dawei.tools.custom_base_tool import CustomBaseTool

from .tool_manager import ToolManager

if TYPE_CHECKING:
    from dawei.entity.task_types import Tool


# ============================================================================
# Tool Permission Definitions
# ============================================================================

# Write operation tools (blocked in Plan mode)
WRITE_TOOLS = {
    "write_to_file",
    "apply_diff",
    "insert_content",
    "execute_command",
    "run_command",
    "browser_action",
    "create_task_graph",
    "add_task_node",
    "delete_task_node",
    "generate_todo_plan",
    "update_todo_list",
}

# Tools that require snapshots (file write operations)
SNAPSHOT_TOOLS = {
    "write_to_file",
    "apply_diff",
    "insert_content",
}


class ToolExecutor(IToolCallService):
    """Tool executor with comprehensive execution management.

    Features:
    - Implements IToolCallService interface
    - Execution history tracking
    - Tool timeout management
    - Execution statistics
    - Parameter validation
    - Workspace-based security
    - Mode-based permission control
    """

    def __init__(
        self,
        tool_manager: ToolManager,
        user_workspace: Optional["UserWorkspace"] = None,
        agent=None,
    ):
        """Initialize tool executor.

        Args:
            tool_manager: ToolManager instance
            user_workspace: UserWorkspace instance (optional, for security checks)
            agent: Agent instance (optional, for mode checking)

        """
        self.tool_manager = tool_manager
        self.user_workspace = user_workspace
        self._agent = agent
        self.tools: dict[str, Tool] = {}
        self.logger = logging.getLogger(__name__)
        self._load_tools()

        # Execution tracking
        self._execution_history: list[dict[str, Any]] = []
        self._tool_timeouts: dict[str, int] = {}

        # Task management
        self._task_manager = AsyncTaskManager()
        self._active_tool_tasks: dict[str, str] = {}

        # Set up task manager callbacks
        self._task_manager.set_progress_callback(self._on_tool_task_progress)
        self._task_manager.set_state_change_callback(self._on_tool_task_state_change)
        self._task_manager.set_error_callback(self._on_tool_task_error)
        self._task_manager.set_completion_callback(self._on_tool_task_completion)

    def _load_tools(self):
        """Load all tools from tool manager."""
        from .custom_base_tool import CustomBaseTool

        self.logger.info("[TOOL_EXECUTOR] Starting tool loading...")
        self.logger.info(
            f"[TOOL_EXECUTOR] User workspace available: {self.user_workspace is not None}",
        )

        tools_list = self.user_workspace.allowed_tools if self.user_workspace else self.tool_manager.load_tools()

        self.logger.info(f"[TOOL_EXECUTOR] Retrieved {len(tools_list)} tools from provider")

        for tool_item in tools_list:
            tool_instance, tool_name = self._extract_tool_info(tool_item)

            if tool_instance and tool_name:
                if isinstance(tool_instance, CustomBaseTool) and self.user_workspace:
                    tool_instance.user_workspace = self.user_workspace

                self.tools[tool_name] = tool_instance
                self.logger.info(f"[TOOL_EXECUTOR] Loaded tool: {tool_name}")
            elif tool_name:
                self.logger.warning(f"[TOOL_EXECUTOR] Invalid instance for tool '{tool_name}'")

        self.logger.info(f"[TOOL_EXECUTOR] Final loaded tools: {list(self.tools.keys())}")

    def _extract_tool_info(self, tool_item: Any) -> tuple[CustomBaseTool | None, str | None]:
        """Extract tool instance and name from various tool item formats.

        Args:
            tool_item: Tool item in various formats (CustomBaseTool, dict, etc.)

        Returns:
            Tuple of (tool_instance, tool_name)

        """
        from .custom_base_tool import CustomBaseTool

        if isinstance(tool_item, CustomBaseTool):
            return tool_item, tool_item.name

        if isinstance(tool_item, dict):
            tool_name = tool_item.get("name")
            original_tool = tool_item.get("original_tool")

            if isinstance(original_tool, CustomBaseTool):
                return original_tool, tool_name

            callable_tool = tool_item.get("callable")
            if isinstance(callable_tool, CustomBaseTool):
                return callable_tool, tool_name

        return None, None

    def check_permission(self, tool_name: str, parameters: dict[str, Any] | None = None) -> bool:
        """Check if tool is allowed in current Agent mode.

        Args:
            tool_name: Tool name to check
            parameters: Tool parameters (optional, for file-level whitelist checking)

        Returns:
            True if tool has permission, False otherwise

        """
        # SUPER MODE: Bypass all permission checks
        from dawei.core.super_mode import is_super_mode_enabled, log_security_bypass

        if is_super_mode_enabled():
            log_security_bypass("check_permission", f"tool={tool_name}")
            return True

        if self._agent is None:
            return True

        try:
            from dawei.agentic.agent_config import AgentMode

            current_mode = self._agent.config.mode
        except (AttributeError, ImportError):
            return True

        # Check if it's a write operation tool in Plan mode
        if current_mode == AgentMode.PLAN and tool_name in WRITE_TOOLS:
            # For file write tools, check if the file is in the whitelist
            if tool_name in ["write_to_file", "apply_diff", "insert_content"] and parameters and self._check_file_write_permission(parameters):
                return True  # File is in whitelist, allow editing

            # Not in whitelist or no parameters provided
            self.logger.warning(
                f"Tool '{tool_name}' is not allowed in PLAN mode (except for plan files in .dawei/plans/). Switch to BUILD mode to execute write operations.",
            )
            return False

        return True

    def _check_file_write_permission(self, parameters: dict[str, Any]) -> bool:
        """Check if file write is allowed based on whitelist (Plan mode).

        Args:
            parameters: Tool parameters containing file path

        Returns:
            True if file can be edited, False otherwise

        """
        import fnmatch

        # Extract file path from parameters
        file_path = None
        if "path" in parameters:
            file_path = parameters["path"]
        elif "file_path" in parameters:
            file_path = parameters["file_path"]
        elif "filename" in parameters:
            file_path = parameters["filename"]
        else:
            return False  # No file path found

        if not file_path:
            return False

        # Resolve to absolute path
        try:
            file_path_obj = Path(file_path).resolve()
        except (OSError, ValueError):
            return False

        # Get workspace path
        if not self.user_workspace:
            return False

        try:
            workspace = Path(self.user_workspace.workspace_info.absolute_path)
        except (AttributeError, TypeError):
            return False

        # Check if file is within workspace
        try:
            relative_path = file_path_obj.relative_to(workspace)
        except ValueError:
            # Outside workspace
            return False

        # Whitelist patterns for Plan mode
        allowed_patterns = [
            ".dawei/plans/*.md",  # Plan directory markdown files
            "*.md",  # All markdown files in workspace
        ]

        # Check if file matches any whitelist pattern
        for pattern in allowed_patterns:
            if fnmatch.fnmatch(str(relative_path), pattern):
                self.logger.info(
                    f"File '{relative_path}' is in Plan mode whitelist, allowing write operation",
                )
                return True

        # Not in whitelist
        self.logger.warning(
            f"File '{relative_path}' is not in Plan mode whitelist. Only .dawei/plans/*.md and *.md files can be edited in Plan mode.",
        )
        return False

    @staticmethod
    def _perform_external_security_check(
        tool_name: str,
        parameters: dict[str, Any],
        user_workspace,
    ) -> str | None:
        """Perform external security checks.

        Args:
            tool_name: Name of the tool being executed
            parameters: Tool parameters
            user_workspace: User workspace for security validation

        Raises:
            ToolSecurityError: If security check fails

        """
        # SUPER MODE: Bypass all security checks
        from dawei.core.super_mode import is_super_mode_enabled, log_security_bypass

        if is_super_mode_enabled():
            log_security_bypass("_perform_external_security_check", f"tool={tool_name}")
            return None

        if not user_workspace:
            return None

        # File operation security check
        if tool_name in ["read_file", "write_to_file", "list_files", "search_files"]:
            for param_name, param_value in parameters.items():
                if "path" in param_name.lower() and isinstance(param_value, str) and not user_workspace.is_path_allowed(param_value):
                    raise ToolSecurityError(
                        tool_name,
                        f"Path '{param_value}' is not within allowed workspace",
                    )

        # Command execution security check
        elif tool_name in ["execute_command", "run_command"]:
            command = parameters.get("command", "")
            if command and not user_workspace.is_command_allowed(command):
                raise ToolSecurityError(tool_name, f"Command '{command}' is not allowed")

        return None

    # ========================================================================
    # IToolCallService Interface Implementation
    # ========================================================================

    async def execute_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        context: Any,
    ) -> dict[str, Any]:
        """Execute tool with permission checks and snapshot creation.

        Args:
            tool_name: Tool name to execute
            parameters: Tool parameters
            context: Execution context

        Returns:
            Tool execution result

        Raises:
            PermissionError: If tool is not allowed in current mode

        """
        # Permission check for Plan mode
        if not self.check_permission(tool_name):
            raise PermissionError(
                operation=f"execute_tool:{tool_name}",
                resource=f"tool:{tool_name}",
                user_id="system",  # Will be updated when we have proper user context
            )

        # Create snapshot before write operations
        await self._create_snapshot_before_write(tool_name, parameters)

        # Track execution
        start_time = time.time()
        execution_record = {
            "tool_name": tool_name,
            "parameters": parameters,
            "start_time": start_time,
            "status": "started",
        }

        try:
            result = await self.execute_tool_internal(tool_name, parameters, context)

            # Record success
            execution_record.update(
                {
                    "result": result,
                    "end_time": time.time(),
                    "status": "completed",
                    "duration": time.time() - start_time,
                },
            )

            return result

        except (ToolExecutionError, ValidationError, PermissionError) as e:
            # Record failure for expected errors
            execution_record.update(
                {
                    "error": str(e),
                    "end_time": time.time(),
                    "status": "failed",
                    "duration": time.time() - start_time,
                },
            )
            self.logger.error(f"Tool execution failed: {tool_name} - {e}", exc_info=True)
            raise
        except Exception as e:
            # Record failure for unexpected errors
            execution_record.update(
                {
                    "error": str(e),
                    "end_time": time.time(),
                    "status": "failed",
                    "duration": time.time() - start_time,
                },
            )
            self.logger.error(f"Unexpected error executing tool {tool_name}: {e}", exc_info=True)
            raise

        finally:
            self._execution_history.append(execution_record)
            # Limit history size
            if len(self._execution_history) > 1000:
                self._execution_history = self._execution_history[-1000:]

    def list_available_tools(self) -> list[str]:
        """List all available tools.

        Returns:
            List of tool names

        """
        try:
            tool_names = list(self.tools.keys())
            self.logger.debug(f"Available tools: {tool_names}")
            return tool_names
        except (AttributeError, RuntimeError) as e:
            self.logger.error(f"Failed to list available tools: {e}", exc_info=True)
            return []

    def get_tool_schema(self, tool_name: str) -> dict[str, Any] | None:
        """Get tool schema.

        Args:
            tool_name: Tool name

        Returns:
            Tool schema dictionary or None

        """
        try:
            self.logger.debug(f"Getting schema for tool: {tool_name}")

            tool = self.tools.get(tool_name)
            if not tool:
                return None

            if hasattr(tool, "get_schema"):
                schema = tool.get_schema()
            elif hasattr(tool, "schema"):
                schema = tool.schema
            else:
                schema = None

            self.logger.debug(f"Retrieved schema for {tool_name}: {schema is not None}")
            return schema
        except Exception as e:
            self.logger.error(f"Failed to get tool schema for {tool_name}: {e}", exc_info=True)
            return None

    def register_tool(self, tool_name: str, tool_impl: Any) -> bool:
        """Register new tool.

        Args:
            tool_name: Tool name
            tool_impl: Tool implementation

        Returns:
            True if registration succeeded

        """
        try:
            self.logger.debug(f"Registering tool: {tool_name}")
            self.tools[tool_name] = tool_impl
            self.logger.info(f"Tool registered successfully: {tool_name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to register tool {tool_name}: {e}", exc_info=True)
            return False

    def unregister_tool(self, tool_name: str) -> bool:
        """Unregister tool.

        Args:
            tool_name: Tool name

        Returns:
            True if unregistration succeeded

        """
        try:
            self.logger.debug(f"Unregistering tool: {tool_name}")

            if tool_name in self.tools:
                del self.tools[tool_name]
                self.logger.info(f"Tool unregistered successfully: {tool_name}")
                return True
            self.logger.warning(f"Tool not found: {tool_name}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to unregister tool {tool_name}: {e}", exc_info=True)
            return False

    def validate_tool_parameters(
        self,
        tool_name: str,
        _parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate tool parameters.

        Args:
            tool_name: Tool name
            parameters: Parameter dictionary

        Returns:
            Validation result with 'valid' flag and 'errors' list

        """
        try:
            self.logger.debug(f"Validating parameters for tool: {tool_name}")

            schema = self.get_tool_schema(tool_name)
            if not schema:
                result = {"valid": True, "errors": []}
            else:
                # TODO: Implement JSON schema validation
                result = {"valid": True, "errors": []}

            self.logger.debug(f"Parameter validation result for {tool_name}: {result['valid']}")
            return result
        except Exception as e:
            self.logger.error(
                f"Failed to validate tool parameters for {tool_name}: {e}",
                exc_info=True,
            )
            return {"valid": False, "errors": [str(e)]}

    def get_tool_execution_history(self, tool_name: str | None = None) -> list[dict[str, Any]]:
        """Get tool execution history.

        Args:
            tool_name: Tool name (None for all tools)

        Returns:
            List of execution records

        """
        try:
            history = [record for record in self._execution_history if record["tool_name"] == tool_name] if tool_name else self._execution_history.copy()

            self.logger.debug(f"Retrieved execution history: {len(history)} records")
            return history
        except Exception as e:
            self.logger.error(f"Failed to get tool execution history: {e}", exc_info=True)
            return []

    def set_tool_timeout(self, tool_name: str, timeout: int) -> bool:
        """Set tool timeout.

        Args:
            tool_name: Tool name
            timeout: Timeout in seconds

        Returns:
            True if timeout was set successfully

        """
        try:
            self.logger.debug(f"Setting timeout for tool {tool_name}: {timeout}s")
            self._tool_timeouts[tool_name] = timeout
            self.logger.info(f"Tool timeout set successfully: {tool_name} -> {timeout}s")
            return True
        except Exception as e:
            self.logger.error(f"Failed to set tool timeout for {tool_name}: {e}", exc_info=True)
            return False

    # ========================================================================
    # Core Tool Execution Methods
    # ========================================================================

    @handle_errors(component="tool_executor", operation="execute_tool")
    @log_performance("tool_executor.execute_tool")
    async def execute_tool_internal(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: TaskContext = None,
    ) -> dict[str, Any]:
        """Execute the specified tool.

        Args:
            tool_name: Tool name
            tool_input: Tool input parameters
            context: Task context (optional)

        Returns:
            Dictionary with execution result:
            - success: bool - Whether execution succeeded
            - result: Any - Execution result (if successful)
            - error: str - Error message (if failed)

        """
        # Get task ID
        task_id = getattr(context, "task_id", "unknown") if context else "unknown"
        tool_call_id = f"{tool_name}_{int(time.time() * 1000)}"

        # Emit tool call start event
        from dawei.core.events import TaskEventType, emit_typed_event

        await emit_typed_event(
            TaskEventType.TOOL_CALL_START,
            ToolCallStartData(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_call_id=tool_call_id,
                task_id=task_id,
            ),
            task_id=task_id,
            source="tool_executor",
        )

        # Create tool execution task and submit to task manager
        tool_task_id = f"tool_task_{tool_call_id}"

        # Get tool-specific timeout, default to 60s
        tool_timeout = self._tool_timeouts.get(tool_name, 60.0)

        task_def = TaskDefinition(
            task_id=tool_task_id,
            name=f"ToolExecution-{tool_name}",
            description=f"Execute tool: {tool_name}",
            executor=self._execute_tool_with_tracking,
            parameters={
                "tool_name": tool_name,
                "tool_input": tool_input,
                "context": context,
                "tool_call_id": tool_call_id,
                "task_id": task_id,
            },
            timeout=tool_timeout,
            retry_policy=RetryPolicy(max_attempts=2, base_delay=0.5, max_delay=5.0),
        )

        # Map tool call ID to task ID
        self._active_tool_tasks[tool_call_id] = tool_task_id

        try:
            # Ensure task manager is running
            if not self._task_manager._is_running:
                await self._task_manager.start()
                self.logger.info("Task manager started for tool execution")

            # Submit task to manager
            await self._task_manager.submit_task(task_def)

            # Wait for task completion with buffer timeout
            wait_timeout = tool_timeout + 30  # Add 30s buffer
            task_result = await self._task_manager.wait_for_task(tool_task_id, timeout=wait_timeout)

            if task_result and task_result.is_success:
                return {"success": True, "result": task_result.result}
            error_msg = str(task_result.error) if task_result and hasattr(task_result, "error") and task_result.error else "Tool execution failed"
            return {"success": False, "error": error_msg}

        except TimeoutError:
            self.logger.exception(f"Tool execution timeout: {tool_name} after {tool_timeout}s")
            await self._task_manager.cancel_task(tool_task_id)
            return {
                "success": False,
                "error": f"Tool execution timeout: {tool_name} (timeout: {tool_timeout}s)",
            }
        except Exception as e:
            self.logger.error(f"Tool execution task failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            # Cleanup mapping
            self._active_tool_tasks.pop(tool_call_id, None)

    async def _execute_tool_with_tracking(
        self,
        parameters: dict[str, Any],
        _context: Any = None,
    ) -> Any:
        """Execute tool with tracking (adapter for AsyncTaskManager executor interface).

        Args:
            parameters: Task parameters containing tool_name, tool_input, context, etc.
            context: Task context

        Returns:
            Execution result

        """
        tool_name = parameters["tool_name"]
        tool_input = parameters["tool_input"]
        task_context = parameters["context"]
        tool_call_id = parameters["tool_call_id"]
        task_id = parameters["task_id"]

        # Force execution in workspace path
        # Remove cwd parameter if present to ensure all tools execute in workspace directory only
        if "cwd" in tool_input:
            self.logger.warning(
                f"[TOOL_EXECUTOR] Removed 'cwd' parameter from {tool_name} input. Tools must execute in workspace directory only.",
            )
            del tool_input["cwd"]

        # Save original working directory and switch to workspace directory
        from pathlib import Path

        original_cwd = None
        self.logger.info(
            f"[TOOL_EXECUTOR] user_workspace exists: {self.user_workspace is not None}",
        )
        if self.user_workspace:
            self.logger.info(
                f"[TOOL_EXECUTOR] has workspace_path attr: {hasattr(self.user_workspace, 'workspace_path')}",
            )
            if hasattr(self.user_workspace, "workspace_path"):
                workspace_path = self.user_workspace.workspace_path
                self.logger.info(f"[TOOL_EXECUTOR] workspace_path: {workspace_path}")
                self.logger.info(
                    f"[TOOL_EXECUTOR] workspace_path exists: {Path(workspace_path).exists() if workspace_path else False}",
                )
                if workspace_path and Path(workspace_path).exists():
                    original_cwd = os.getcwd()
                    os.chdir(str(workspace_path))
                    self.logger.info(
                        f"[TOOL_EXECUTOR] Changed working directory to workspace: {workspace_path}",
                    )

        try:
            # Validate input
            if not tool_name or not tool_name.strip():
                raise ValidationError("tool_name", tool_name, "must be non-empty string")

            # Emit validation progress event
            from dawei.core.events import TaskEventType, emit_typed_event
            from dawei.entity.tool_event_data import (
                ToolCallProgressData,
                ToolExecutionStatus,
            )

            await emit_typed_event(
                TaskEventType.TOOL_CALL_PROGRESS,
                ToolCallProgressData(
                    tool_name=tool_name,
                    status=ToolExecutionStatus.VALIDATING,
                    message="Validating tool parameters...",
                    tool_call_id=tool_call_id,
                    task_id=task_id,
                ),
                task_id=task_id,
                source="tool_executor",
            )

            # Check if tool is always available

            # Perform security checks
            if self.user_workspace:
                self._perform_external_security_check(tool_name, tool_input, self.user_workspace)

            # Find tool - raise exception instead of returning error
            tool = self.tools.get(tool_name)
            if not tool:
                raise ToolNotFoundError(tool_name)

            # Get actual executable tool instance
            executable_tool = tool

            # Use CustomBaseTool standard interface to execute tool
            # Set context if provided
            if task_context is not None:
                executable_tool.set_context(task_context)

                # Set user_workspace if tool is CustomBaseTool instance
                if isinstance(executable_tool, CustomBaseTool) and self.user_workspace:
                    executable_tool.user_workspace = self.user_workspace

            # Emit execution start event
            await emit_typed_event(
                TaskEventType.TOOL_CALL_PROGRESS,
                ToolCallProgressData(
                    tool_name=tool_name,
                    status=ToolExecutionStatus.EXECUTING,
                    message="Executing tool...",
                    tool_call_id=tool_call_id,
                    task_id=task_id,
                ),
                task_id=task_id,
                source="tool_executor",
            )

            # Call tool's run method (handles parameter validation automatically)
            result = executable_tool.run(**tool_input)

            # Check if result is a coroutine
            import inspect

            if inspect.iscoroutine(result):
                result = await result

            self.logger.info(
                f"Tool executed successfully: tool_name={tool_name}, component=tool_executor",
            )
            increment_counter(
                "tool_executor.executions",
                tags={"tool_name": tool_name, "status": "success"},
            )

            return result

        finally:
            # Restore original working directory
            if original_cwd is not None:
                os.chdir(original_cwd)
                self.logger.debug(f"[TOOL_EXECUTOR] Restored working directory to: {original_cwd}")

    @handle_errors(component="tool_executor", operation="set_user_workspace")
    async def set_user_workspace(self, user_workspace: "UserWorkspace"):
        """Set user workspace and reload tools.

        Args:
            user_workspace: UserWorkspace instance

        """
        self.user_workspace = user_workspace
        self.tools.clear()
        self._load_tools()
        self.logger.info("User workspace set: component=tool_executor")

    # ========================================================================
    # Task Manager Callbacks
    # ========================================================================

    async def start_task_manager(self):
        """Start task manager."""
        await self._task_manager.start()
        self.logger.info("Tool executor task manager started")

    async def stop_task_manager(self):
        """Stop task manager."""
        await self._task_manager.stop()
        self.logger.info("Tool executor task manager stopped")

    async def _on_tool_task_progress(self, task_progress):
        """Tool task progress callback."""
        try:
            # Find corresponding tool call ID
            tool_call_id = None
            for tc_id, t_id in self._active_tool_tasks.items():
                if t_id == task_progress.task_id:
                    tool_call_id = tc_id
                    break

            if tool_call_id:
                # Emit tool call progress event
                from dawei.core.events import TaskEventType, emit_typed_event
                from dawei.entity.tool_event_data import (
                    ToolCallProgressData,
                    ToolExecutionStatus,
                )

                await emit_typed_event(
                    TaskEventType.TOOL_CALL_PROGRESS,
                    ToolCallProgressData(
                        tool_name=f"tool_{tool_call_id}",
                        status=ToolExecutionStatus.EXECUTING,
                        message=task_progress.message,
                        progress_percentage=task_progress.progress,
                        tool_call_id=tool_call_id,
                        task_id=task_progress.task_id,
                    ),
                    task_id=task_progress.task_id,
                    source="tool_executor",
                )
        except Exception as e:
            self.logger.error(f"Error in tool task progress callback: {e}", exc_info=True)

    async def _on_tool_task_state_change(
        self,
        task_id: str,
        old_status: TaskStatus,
        new_status: TaskStatus,
    ):
        """Tool task state change callback."""
        try:
            # Find corresponding tool call ID
            tool_call_id = None
            for tc_id, t_id in self._active_tool_tasks.items():
                if t_id == task_id:
                    tool_call_id = tc_id
                    break

            if tool_call_id:
                self.logger.info(
                    f"Tool task {tool_call_id} state changed: {old_status.value} -> {new_status.value}",
                )
        except Exception as e:
            self.logger.error(f"Error in tool task state change callback: {e}", exc_info=True)

    async def _on_tool_task_error(self, task_error):
        """Tool task error callback."""
        try:
            # Find corresponding tool call ID
            tool_call_id = None
            for tc_id, t_id in self._active_tool_tasks.items():
                if t_id == task_error.task_id:
                    tool_call_id = tc_id
                    break

            if tool_call_id:
                # Emit tool call result event (error)
                from dawei.core.events import TaskEventType, emit_typed_event
                from dawei.entity.tool_event_data import ToolCallResultData

                await emit_typed_event(
                    TaskEventType.TOOL_CALL_RESULT,
                    ToolCallResultData(
                        tool_name=f"tool_{tool_call_id}",
                        result=task_error.error_message,
                        is_error=True,
                        tool_call_id=tool_call_id,
                        task_id=task_error.task_id,
                    ),
                    task_id=task_error.task_id,
                    source="tool_executor",
                )

                # Cleanup mapping
                self._active_tool_tasks.pop(tool_call_id, None)
        except Exception as e:
            self.logger.error(f"Error in tool task error callback: {e}", exc_info=True)

    async def _on_tool_task_completion(self, task_result):
        """Tool task completion callback."""
        try:
            # Find corresponding tool call ID
            tool_call_id = None
            for tc_id, t_id in self._active_tool_tasks.items():
                if t_id == task_result.task_id:
                    tool_call_id = tc_id
                    break

            if tool_call_id:
                if task_result.is_success:
                    # Emit tool call result event (success)
                    from dawei.core.events import TaskEventType, emit_typed_event
                    from dawei.entity.tool_event_data import ToolCallResultData

                    await emit_typed_event(
                        TaskEventType.TOOL_CALL_RESULT,
                        ToolCallResultData(
                            tool_name=f"tool_{tool_call_id}",
                            result=task_result.result,
                            is_error=False,
                            tool_call_id=tool_call_id,
                            task_id=task_result.task_id,
                            execution_time=task_result.execution_time,
                        ),
                        task_id=task_result.task_id,
                        source="tool_executor",
                    )

                # Cleanup mapping
                self._active_tool_tasks.pop(tool_call_id, None)
        except Exception as e:
            self.logger.error(f"Error in tool task completion callback: {e}", exc_info=True)

    # ========================================================================
    # Additional Methods from Adapter
    # ========================================================================

    def get_tool_timeout(self, tool_name: str) -> int | None:
        """Get tool timeout.

        Args:
            tool_name: Tool name

        Returns:
            Timeout in seconds or None

        """
        return self._tool_timeouts.get(tool_name)

    def get_all_tool_timeouts(self) -> dict[str, int]:
        """Get all tool timeouts.

        Returns:
            Dictionary of tool timeouts

        """
        return self._tool_timeouts.copy()

    def clear_execution_history(self, tool_name: str | None = None) -> bool:
        """Clear execution history.

        Args:
            tool_name: Tool name (None to clear all history)

        Returns:
            True if cleared successfully

        """
        try:
            if tool_name:
                original_count = len(self._execution_history)
                self._execution_history = [record for record in self._execution_history if record["tool_name"] != tool_name]
                cleared_count = original_count - len(self._execution_history)
                self.logger.info(f"Cleared {cleared_count} execution records for tool: {tool_name}")
            else:
                count = len(self._execution_history)
                self._execution_history.clear()
                self.logger.info(f"Cleared all {count} execution records")

            return True
        except Exception as e:
            self.logger.error(f"Failed to clear execution history: {e}", exc_info=True)
            return False

    def get_execution_statistics(self) -> dict[str, Any]:
        """Get execution statistics.

        Returns:
            Dictionary with execution statistics

        """
        try:
            total_executions = len(self._execution_history)
            successful_executions = len(
                [record for record in self._execution_history if record["status"] == "completed"],
            )
            failed_executions = len(
                [record for record in self._execution_history if record["status"] == "failed"],
            )

            # Calculate average duration
            completed_records = [record for record in self._execution_history if record["status"] == "completed" and "duration" in record]
            avg_duration = sum(record["duration"] for record in completed_records) / len(completed_records) if completed_records else 0

            # Per-tool statistics
            tool_stats: dict[str, dict[str, int]] = {}
            for record in self._execution_history:
                tool_name = record["tool_name"]
                if tool_name not in tool_stats:
                    tool_stats[tool_name] = {"total": 0, "successful": 0, "failed": 0}

                tool_stats[tool_name]["total"] += 1
                if record["status"] == "completed":
                    tool_stats[tool_name]["successful"] += 1
                elif record["status"] == "failed":
                    tool_stats[tool_name]["failed"] += 1

            return {
                "total_executions": total_executions,
                "successful_executions": successful_executions,
                "failed_executions": failed_executions,
                "success_rate": (successful_executions / total_executions if total_executions > 0 else 0),
                "average_duration": avg_duration,
                "tool_statistics": tool_stats,
                "available_tools": self.list_available_tools(),
                "configured_timeouts": len(self._tool_timeouts),
            }
        except Exception as e:
            self.logger.error(f"Failed to get execution statistics: {e}", exc_info=True)
            return {"error": str(e)}

    async def _create_snapshot_before_write(
        self,
        tool_name: str,
        parameters: dict[str, Any],
    ) -> bool:
        """Create file snapshot before write operations.

        Args:
            tool_name: Tool name
            parameters: Tool parameters

        Returns:
            True if snapshot was created successfully

        """
        # Skip if tool doesn't require snapshot
        if tool_name not in SNAPSHOT_TOOLS:
            return False

        # Check if agent has snapshot manager
        if not self._agent or not hasattr(self._agent, "file_snapshot_manager"):
            return False

        try:
            # Extract file path from parameters
            file_path = parameters.get("path")
            if not file_path:
                return False

            # Create snapshot
            snapshot = self._agent.file_snapshot_manager.create_snapshot(
                file_path=file_path,
                reason=f"before_{tool_name}",
                strategy="auto",
            )

            if snapshot:
                self.logger.info(f"Created snapshot before {tool_name}: {file_path}")
                return True

            return False
        except (OSError, IOError, PermissionError) as e:
            # Fast Fail: 预期的存储/IO错误不应阻止工具执行
            self.logger.warning(f"Failed to create snapshot before {tool_name}: {e}", exc_info=True)
            return False
        except Exception as e:
            # Fast Fail: 关键错误应该快速失败并抛出
            self.logger.error(f"Unexpected error creating snapshot before {tool_name}: {e}", exc_info=True)
            raise type(e)(
                f"Critical snapshot creation failure for tool {tool_name}: {e}"
            ) from e
