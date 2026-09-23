# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Tool executor module - Refactored version.

Handles tool execution logic, error handling, and lifecycle management.
Implements IToolCallService interface for integration with the task system.
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from dawei.agentic.file_snapshot_manager import SnapshotStrategy
from dawei.async_task.task_manager import AsyncTaskManager
from dawei.async_task.types import AsyncTaskManagerConfig, RetryPolicy, TaskDefinition, TaskStatus
from dawei.core.error_handler import handle_errors
from dawei.core.errors import (
    PermissionError,
    ToolExecutionError,
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

# Tools that require snapshots (file write operations)
SNAPSHOT_TOOLS = {
    "write_text_file",
    "smart_text_edit",
    "insert_text_content",
}

# 安全策略解析失败去重键（fail-closed）：同一错误只 ERROR 一次防刷屏，
# 但每次调用仍然拒绝 —— 拒绝本身不因"已见过"而放松。
_POLICY_CHECK_FAILURES: set[str] = set()


class ToolExecutor(IToolCallService):
    """Tool executor with comprehensive execution management.

    Features:
    - Implements IToolCallService interface
    - Execution history tracking
    - Tool timeout management
    - Execution statistics
    - Parameter validation
    - Workspace-based security (allow/deny)
    """

    def __init__(
        self,
        tool_manager: ToolManager,
        user_workspace: Optional["UserWorkspace"] = None,
        agent=None,
        event_bus=None,
        default_timeout: float = 60.0,
        max_concurrent: int = 10,
    ):
        """Initialize tool executor.

        Args:
            tool_manager: ToolManager instance
            user_workspace: UserWorkspace instance (optional, for security checks)
            agent: Agent instance (optional, for mode checking)
            event_bus: Event bus instance for emitting tool events
            default_timeout: 默认工具超时秒数（来自工作区 config.tools.default_timeout，
                经 Config.tool_execution_timeout 桥接传入）

        """
        self.tool_manager = tool_manager
        self.user_workspace = user_workspace
        self._agent = agent
        self._event_bus = event_bus
        self.tools: dict[str, Tool] = {}
        self.logger = logging.getLogger(__name__)
        self._load_tools()

        # Execution tracking
        self._execution_history: list[dict[str, Any]] = []
        self._tool_timeouts: dict[str, int] = {}
        self._default_timeout = default_timeout

        # Task management：并发来自工作区 config.tools.max_concurrent_executions（默认 10，
        # 已与 AsyncTaskManagerConfig 对齐，桥接不改变既有并发行为）
        self._task_manager = AsyncTaskManager(
            AsyncTaskManagerConfig(max_concurrent_tasks=max_concurrent)
        )
        self._active_tool_tasks: dict[str, str] = {}

        # Note: Callbacks will be set up in async_initialize() method
        self._callbacks_initialized = False

    async def async_initialize(self) -> None:
        """Async initialization for task manager callbacks.

        This must be called after __init__ to properly set up async callbacks.
        """
        if not self._callbacks_initialized:
            # Set up task manager callbacks (only set_start_callback is async)
            await self._task_manager.set_start_callback(self._on_tool_task_start)
            self._task_manager.set_progress_callback(self._on_tool_task_progress)
            self._task_manager.set_state_change_callback(self._on_tool_task_state_change)
            self._task_manager.set_error_callback(self._on_tool_task_error)
            self._task_manager.set_completion_callback(self._on_tool_task_completion)
            self._callbacks_initialized = True
            self.logger.info("[TOOL_EXECUTOR] Task manager callbacks initialized")

    def inject_knowledge_base_id(self, knowledge_base_id: str | list[str]) -> None:
        """Inject knowledge base ID into all knowledge tools.

        This method is called by Agent during initialization to inject the
        knowledge base ID into all tools that require it.

        Args:
            knowledge_base_id: Knowledge base ID to inject (string or list of strings)

        """
        # Normalize to list always
        if isinstance(knowledge_base_id, str):
            knowledge_base_ids = [knowledge_base_id]
        else:
            knowledge_base_ids = knowledge_base_id

        injected_count = 0

        for tool_name, tool_instance in self.tools.items():
            # Check if tool has knowledge_base_ids attribute (list-based)
            if hasattr(tool_instance, "knowledge_base_ids"):
                tool_instance.knowledge_base_ids = knowledge_base_ids
                self.logger.debug(f"Injected knowledge_base_ids into {tool_name}: {knowledge_base_ids}")
                injected_count += 1

        if injected_count > 0:
            self.logger.info(f"Successfully injected knowledge_base_ids into {injected_count} tools")
        else:
            self.logger.debug("No knowledge tools found to inject knowledge_base_ids")

    def inject_agent(self, agent) -> None:
        """Inject agent reference into tools that need it (e.g., ShowCostTool).

        This method is called by Agent during initialization.

        Args:
            agent: Agent instance

        """
        injected_count = 0
        for tool_name, tool_instance in self.tools.items():
            if hasattr(tool_instance, "set_agent"):
                tool_instance.set_agent(agent)
                self.logger.debug(f"Injected agent into {tool_name}")
                injected_count += 1
        if injected_count > 0:
            self.logger.info(f"Successfully injected agent into {injected_count} tools")

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

    def _resolve_dynamic_mcp_tool(self, tool_name: str):
        """Late-bind dynamic MCP tools (``mcp__{server}__{tool}``).

        ``self.tools`` is a snapshot taken at init time; MCP servers
        auto-connect asynchronously afterwards, so a name can be visible to
        the LLM (llm_message_builder syncs schema dynamically) yet missing
        from this registry — the "schema visible, execution ToolNotFound"
        dead-end. Resolve against currently-connected servers and register
        on first use; failures fall through to ToolNotFoundError.
        """
        try:
            from .custom_base_tool import CustomBaseTool

            ws = self.user_workspace
            builder = getattr(ws, "_mcp_dynamic_tools", None)
            if builder is None:
                return None
            for item in builder():
                if isinstance(item, dict) and item.get("name") == tool_name:
                    tool_instance, resolved_name = self._extract_tool_info(item)
                    if tool_instance and resolved_name:
                        if isinstance(tool_instance, CustomBaseTool) and ws:
                            tool_instance.user_workspace = ws
                        self.tools[resolved_name] = tool_instance
                        self.logger.info(f"[TOOL_EXECUTOR] Late-bound MCP tool: {resolved_name}")
                        return tool_instance
        except Exception:  # noqa: BLE001 — 回退失败按原路径抛 ToolNotFoundError
            self.logger.exception(f"Late-bind MCP tool '{tool_name}' failed")
        return None

    def check_permission(self, tool_name: str, parameters: dict[str, Any] | None = None) -> bool:
        """Check if tool is allowed by workspace/security settings (mode-agnostic).

        Permission checks in priority order:
        1. Super mode bypass (DAWEI_SUPER_MODE=1)
        2. Denied tools - explicitly blocked by workspace settings
        3. Allowed tools - if allowlist is configured, only listed tools are permitted

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

        # User-level + workspace-merged tool policy (override-or-inherit).
        # Closes the §1.4 gap: a user-level deny now blocks even when the
        # workspace would otherwise allow. Reads never block execution on failure.
        try:
            from dawei.core.security_manager import security_manager

            tool_policy = security_manager.get_policy().tools
            if tool_name in tool_policy.denied_tools:
                self.logger.warning(
                    f"Tool '{tool_name}' denied by security policy (denied_tools)",
                )
                try:
                    from dawei.core.effective_policy import get_tool_risk
                    from dawei.core.security_auditor import security_auditor

                    security_auditor.log(
                        "security.tool.denied",
                        tool=tool_name,
                        reason="denied_tools",
                        risk=get_tool_risk(tool_name),
                    )
                except Exception as e:  # noqa: BLE001 — 审计失败不阻断拒绝路径,但必须可见
                    self.logger.warning(f"deny audit log failed for '{tool_name}': {e}")
                return False
            # 动态 mcp__ 名不可能预置在静态名单里;MCP 有专属闸门链
            # （security policy 的 mcp.allowed/denied_mcp_servers（call_tool 内
            # 生效）+ workspace always_allow_mcp + mode "mcp" 组）。静态
            # allowlist 对 mcp__ 放行,避免"schema 可见但执行被拒"的死局;
            # denied_tools 精确匹配仍对动态名生效（用户可按名封禁）。
            if tool_policy.allowed_tools and not tool_name.startswith("mcp__") and tool_name not in tool_policy.allowed_tools:
                self.logger.warning(
                    f"Tool '{tool_name}' not in security policy allowed_tools",
                )
                return False
        except Exception as e:  # noqa: BLE001 — fail-closed（FAST FAIL，2026-09-23 八跑教训）
            # 八跑事故：security.json containerRuntime="e2b" 未被 Literal 收录 →
            # get_policy() 每轮抛 ValidationError → 旧 fail-open 静默放行 53 次，
            # 安全层形同虚设。"配置非法"必须拒绝执行（宁可吵闹不可失守）；
            # 同一错误只 ERROR 一次防刷屏，拒绝不放松。修复路径见 ERROR 文案。
            _fail_key = f"{type(e).__name__}:{e}"
            if _fail_key not in _POLICY_CHECK_FAILURES:
                _POLICY_CHECK_FAILURES.add(_fail_key)
                self.logger.error(
                    f"Security tool policy check FAILED for '{tool_name}': {e}; DENYING all tools (fail-closed). "
                    "Fix the security config (e.g. ~/.normnomos/configs/*/security.json) — identical errors will not be re-logged.",
                )
            return False

        # Check workspace-level denied_tools (explicit deny takes precedence)
        if self.user_workspace is not None:
            from dawei.workspace.models import WorkspaceSettings

            # Access workspace settings - try several possible locations
            settings = None
            if hasattr(self.user_workspace, "settings") and isinstance(
                self.user_workspace.settings, WorkspaceSettings,
            ):
                settings = self.user_workspace.settings
            elif hasattr(self.user_workspace, "_settings") and isinstance(
                self.user_workspace._settings, WorkspaceSettings,
            ):
                settings = self.user_workspace._settings

            if settings is not None:
                # Check denied_tools first (explicit deny overrides all)
                if tool_name in settings.denied_tools:
                    self.logger.warning(
                        f"Tool '{tool_name}' denied by workspace settings (denied_tools)",
                    )
                    return False

                # Check allowed_tools (if non-empty, only listed tools are permitted).
                # mcp__ 豁免同上（security policy 段注释）:动态名由 MCP 专属
                # 闸门链治理（always_allow_mcp / mode mcp 组 / mcp server 名单）。
                if settings.allowed_tools and not tool_name.startswith("mcp__") and tool_name not in settings.allowed_tools:
                    self.logger.warning(
                        f"Tool '{tool_name}' not in workspace allowed_tools",
                    )
                    return False

        # mode-工具解耦（mode工具解耦方案.md D5）：mode 维度准入闸门整体退役。
        # 工具可用性 = 安装了什么；执行管控 = workspace allow/deny + sandbox 白名单。
        return True

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

        # File operation security check (read, write, edit, insert, search)
        if tool_name in {
            "read_file", "write_text_file", "list_files",
            "smart_text_edit", "insert_text_content", "search_files",
        }:
            # SaaS 沙箱模式 (2026-09-14 收尾): 沙箱可路由工具的执行点在
            # CubeSandbox MicroVM 内 (tool_runner 以 /workspace 为根, 硬隔离),
            # 宿主 is_path_allowed 无法判定沙箱侧路径语义 ('/', '/workspace/...'
            # 均合法) → 整体跳过宿主路径守卫; 非路由文件工具 (如 search_files,
            # 真正落宿主执行) 守卫保持不变。
            sandbox_routing = (
                os.environ.get("DAWEI_TOOL_EXECUTION_MODE", "") == "sandbox"
                and tool_name in ToolExecutor.SANDBOX_ROUTABLE_TOOLS
            )
            if sandbox_routing:
                return None
            for param_name, param_value in parameters.items():
                if "path" in param_name.lower() and isinstance(param_value, str) and not user_workspace.is_path_allowed(param_value):
                    raise ToolSecurityError(
                        tool_name,
                        f"Path '{param_value}' is not within allowed workspace",
                    )

        # Command execution security check
        elif tool_name in {"execute_command", "run_command", "shell_command"}:
            command = parameters.get("command", "")
            if command:
                denial_reason = user_workspace.command_denial_reason(command)
                if denial_reason:
                    raise ToolSecurityError(
                        tool_name, f"Command '{command}' is not allowed: {denial_reason}"
                    )

        return None

    # ========================================================================
    # IToolCallService Interface Implementation
    # ========================================================================

    async def execute_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        context: Any,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute tool with permission checks and snapshot creation.

        Args:
            tool_name: Tool name to execute
            parameters: Tool parameters
            context: Execution context
            task_id: Optional task ID for tracking

        Returns:
            Tool execution result

        Raises:
            PermissionError: If tool is not allowed in current mode

        """
        # 进入工具执行即确立本次安全上下文（contextvar，per-coroutine）：
        # 使本次 execute_tool 调用链上的深层 get_policy()（approval_gate / rate_limiter
        # 等）无需显式传参即可取到属于本执行的 (user_id, workspace)，且与并发其它
        # 工作区的执行互不干扰（消除 _current_* 全局指针竞态）。
        try:
            from dawei.core.security_manager import security_manager

            if self.user_workspace is not None:
                security_manager.set_context(
                    self.user_workspace.user_id, self.user_workspace.absolute_path
                )
        except Exception as e:
            self.logger.warning(f"set security context at execute_tool entry failed: {e}")

        # MarketingAgent 编队可观测性(E1 徽标):market 工具组被调用 → 当前子智能体
        # 进入 tool 态(仅 market-team mode 生效;失败不阻断工具执行)。
        if tool_name.startswith("market_"):
            try:
                from dawei.websocket.market_fleet import note_market_tool_call

                await note_market_tool_call(
                    getattr(self.user_workspace, "workspace_id", "") or "",
                    getattr(self._agent, "current_mode", None),
                    tool_name,
                )
            except Exception as e:  # noqa: BLE001
                self.logger.debug(f"market fleet note failed: {e}")

        # SocialAgent 编队可观测性(E1 徽标):social 工具组被调用 → 当前子智能体
        # 进入 tool 态(仅 social-team mode 生效;创作工坊 social-tools 会话不受影响)。
        if tool_name.startswith("social_"):
            try:
                from dawei.websocket.social_fleet import note_social_tool_call

                await note_social_tool_call(
                    getattr(self.user_workspace, "workspace_id", "") or "",
                    getattr(self._agent, "current_mode", None),
                    tool_name,
                )
            except Exception as e:  # noqa: BLE001
                self.logger.debug(f"social fleet note failed: {e}")

        # GeluResearch 编队可观测性(E1 徽标,镜像 social):research 工具组被调用 →
        # 当前子智能体进入 tool 态(仅 gelu-research-team mode 生效)。
        if tool_name.startswith("research_"):
            try:
                from dawei.websocket.research_fleet import note_research_tool_call

                await note_research_tool_call(
                    getattr(self.user_workspace, "workspace_id", "") or "",
                    getattr(self._agent, "current_mode", None),
                    tool_name,
                )
            except Exception as e:  # noqa: BLE001
                self.logger.debug(f"research fleet note failed: {e}")

        # Permission check for Plan mode
        _uid = self._audit_user_id()
        if not self.check_permission(tool_name):
            raise PermissionError(
                operation=f"execute_tool:{tool_name}",
                resource=f"tool:{tool_name}",
                user_id=_uid,
            )

        # Human-in-the-loop approval gate (P2.2). Default policy is disabled, so
        # this is a no-op until approval is turned on. Any internal gate error is
        # swallowed (allowing) so the gate can never break tool execution.
        try:
            from dawei.core.approval_gate import approval_gate

            if not await approval_gate.request_approval(tool_name, parameters, task_id=task_id):
                raise PermissionError(
                    operation=f"execute_tool:{tool_name}",
                    resource=f"tool:{tool_name}",
                    user_id=_uid,
                )
        except PermissionError:
            raise
        except Exception as e:
            self.logger.warning(f"Approval gate unavailable for '{tool_name}': {e}; allowing")

        # Tool rate limiting (域11). Default 0 = unlimited → no-op until configured.
        try:
            from dawei.core.tool_rate_limiter import tool_rate_limiter

            if not tool_rate_limiter.check_and_consume("tool"):
                try:
                    from dawei.core.security_auditor import security_auditor

                    security_auditor.log(
                        "security.rate_limited",
                        tool=tool_name,
                        reason="tool_calls_per_minute",
                    )
                except Exception as e:  # noqa: BLE001 — 审计失败不阻断拒绝路径,但必须可见
                    self.logger.warning(f"rate-limit audit log failed for '{tool_name}': {e}")
                raise PermissionError(
                    operation=f"execute_tool:{tool_name}",
                    resource=f"tool:{tool_name}",
                    user_id=_uid,
                )
        except PermissionError:
            raise
        except Exception as e:
            self.logger.warning(f"Rate limit check failed for '{tool_name}': {e}; allowing")

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

            # X4 fix: unpack GovernedResult for execution_record
            # execute_tool_internal returns {"success": True, "result": <GovernedResult or raw>}
            from dawei.tools.result_governance import GovernedResult

            inner = result.get("result") if isinstance(result, dict) else result
            if isinstance(inner, GovernedResult):
                execution_record.update(inner.to_history_record())
                execution_record.update(
                    {
                        "end_time": time.time(),
                        "status": "completed",
                        "duration": time.time() - start_time,
                    },
                )
            else:
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

        # 🔍 DEBUG: Log tool_input before emitting event
        import json

        self.logger.warning(f"[TOOL_INPUT_DEBUG] Before emitting TOOL_CALL_START: tool_name={tool_name}, tool_input={json.dumps(tool_input, ensure_ascii=False)}")

        self.logger.info(
            f"[TOOL_EXECUTOR] 🔧 Emitting TOOL_CALL_START event: tool_name={tool_name}, tool_call_id={tool_call_id}, task_id={task_id}",
        )

        await emit_typed_event(
            TaskEventType.TOOL_CALL_START,
            ToolCallStartData(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_call_id=tool_call_id,
                task_id=task_id,
            ),
            self._event_bus,  # 🔧 修复：添加 event_bus 参数
            task_id=task_id,
            source="tool_executor",
        )

        # Create tool execution task and submit to task manager
        tool_task_id = f"tool_task_{tool_call_id}"

        # Get tool-specific timeout, fall back to workspace default (config.tools.default_timeout)
        tool_timeout = self._tool_timeouts.get(tool_name, self._default_timeout)

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
            # Fix (2026-09-14 smoke #8): task_manager 超时抛裸 TimeoutError()，str() 为空，
            # 且异常对象本身 truthy → 曾输出 {"success": false, "error": ""} 误报。
            # 永远给出真实、非空的错误信息。
            raw_error = getattr(task_result, "error", None) if task_result else None
            if isinstance(raw_error, TimeoutError):
                error_msg = f"Tool execution timeout: {tool_name} (timeout: {tool_timeout}s)"
                if tool_name in ("new_task", "run_task"):
                    # 🔥 修复（2026-09-17）：超时不代表失败——子任务可能已创建/已在后台运行。
                    # 提示 agent 查询状态而不是盲目重试（重试会产生重复子任务）。
                    error_msg += ". The subtask may still have been created/started; check with get_task_status before retrying"
            else:
                error_msg = str(raw_error).strip() or f"Tool execution failed: {tool_name} ({type(raw_error).__name__})"
            return {"success": False, "error": error_msg}

        except TimeoutError:
            self.logger.exception(f"Tool execution timeout: {tool_name} after {tool_timeout}s")
            await self._task_manager.cancel_task(tool_task_id)
            timeout_error_msg = f"Tool execution timeout: {tool_name} (timeout: {tool_timeout}s)"
            if tool_name in ("new_task", "run_task"):
                timeout_error_msg += ". The subtask may still have been created/started; check with get_task_status before retrying"
            return {
                "success": False,
                "error": timeout_error_msg,
            }
        except Exception as e:
            self.logger.error(f"Tool execution task failed: {e}", exc_info=True)
            # 同上：裸异常 str() 可能为空，兜底为异常类名
            error_msg = str(e).strip() or f"Tool execution failed: {tool_name} ({type(e).__name__})"
            return {"success": False, "error": error_msg}
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

            # Validate tool_input type
            if not isinstance(tool_input, dict):
                raise ValidationError(
                    "tool_input",
                    tool_input,
                    "must be a dictionary with tool parameters",
                )

            # Get tool to check required parameters before execution
            tool = self.tools.get(tool_name)
            if not tool and tool_name.startswith("mcp__"):
                # MCP servers auto-connect after the init-time snapshot; resolve
                # dynamic mcp__ names against currently-connected servers.
                tool = self._resolve_dynamic_mcp_tool(tool_name)
            if not tool:
                raise ToolNotFoundError(tool_name)

            # Check for missing required parameters if tool has args_schema
            if isinstance(tool, CustomBaseTool) and hasattr(tool, "args_schema") and tool.args_schema:
                schema = tool.args_schema
                if hasattr(schema, "model_fields"):
                    # Get required fields
                    required_fields = [name for name, field in schema.model_fields.items() if field.is_required()]

                    # Only validate non-empty if there are required fields
                    if required_fields:
                        # Check if required fields are missing
                        missing_fields = [f for f in required_fields if f not in tool_input]
                        # Only raise error if there are actually missing fields
                        if missing_fields:
                            # Build helpful error message for LLM
                            field_descriptions = []
                            for field_name in required_fields:
                                field_info = schema.model_fields[field_name]
                                desc = field_info.description or ""
                                field_descriptions.append(f"  - {field_name}: {desc}")

                            error_msg = f"Tool '{tool_name}' missing required parameters: {', '.join(missing_fields)}\n\nRequired parameters:\n" + "\n".join(field_descriptions) + "\n\nPlease retry the tool call with all required parameters."
                            raise ValidationError(
                                "tool_input",
                                tool_input,
                                error_msg,
                            )

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
                self._event_bus,  # 🔧 修复：添加 event_bus 参数
                task_id=task_id,
                source="tool_executor",
            )

            # Check if tool is always available

            # Perform security checks
            if self.user_workspace:
                self._perform_external_security_check(tool_name, tool_input, self.user_workspace)

            # Tool was already fetched above during validation
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
                self._event_bus,  # 🔧 修复：添加 event_bus 参数
                task_id=task_id,
                source="tool_executor",
            )

            # ── Output governance: input-side check (D-class Echo) ──
            # Must be BEFORE tool.run() — blocks oversized content before writing
            from dawei.tools.result_governance import get_governor, get_policy

            _governor = get_governor()
            _policy = get_policy(tool_name)
            _input_block = _governor.check_input(tool_name, tool_input, _policy)
            if _input_block:
                self.logger.warning(f"Tool input blocked by governor: {tool_name}")
                increment_counter(
                    "tool_executor.input_blocked",
                    tags={"tool_name": tool_name, "reason": "content_too_large"},
                )
                return _input_block

            # Call tool's run method (handles parameter validation automatically)
            # P3 Path B: Route to sandbox when configured (with host fallback)
            # bug#5: 同步 run() 经 asyncio.to_thread 卸载到 worker 线程 —— 旧实现
            # 直接在事件循环线程调用，任何阻塞型同步工具（如 MCP 的
            # run_on_main_loop 有界等待）都会冻结整个服务（health 000）。
            if self._should_route_to_sandbox(executable_tool):
                try:
                    result = self._execute_tool_in_sandbox(
                        executable_tool, tool_input, tool_name,
                    )
                except Exception as sandbox_err:
                    from dawei.runtime import deployment_class  # 唯一合法 mode 读取点

                    if deployment_class() == "saas":
                        # SaaS 隔离 (fail-fast): 沙箱可路由工具执行失败不得静默回落宿主,
                        # 否则文件操作绕过 MicroVM 边界直接落宿主磁盘
                        raise
                    self.logger.warning(
                        f"[P3] Sandbox tool execution failed, "
                        f"falling back to host: {sandbox_err}",
                    )
                    result = await asyncio.to_thread(executable_tool.run, **tool_input)
            else:
                result = await asyncio.to_thread(executable_tool.run, **tool_input)

            # Check if result is a coroutine
            import inspect

            if inspect.iscoroutine(result):
                result = await result

            # ── Output governance: output-side兜底 (all tool types) ──
            # Governor returns GovernedResult envelope; never throws (M7 fix)
            _uid = ""
            _wid = ""
            if self.user_workspace:
                _uid = getattr(self.user_workspace, "user_id", "") or ""
                _wid = getattr(self.user_workspace, "workspace_id", "") or getattr(self.user_workspace, "absolute_path", "") or ""
            result = _governor.govern(
                tool_name,
                result,
                _policy,
                call_id=tool_call_id,
                user_id=_uid,
                workspace_id=_wid,
            )

            # 工具返回 "Error: ..." 字符串是本仓库约定的软失败格式（各工具
            # 无法抛异常穿透 run()）——不得再记为 success（2026-09-17 事故：
            # smart_text_edit 100% 失败但指标/日志全程显示成功）。
            _result_data = getattr(result, "data", result)
            if isinstance(_result_data, str) and _result_data.startswith("Error"):
                self.logger.warning(
                    f"Tool returned error: tool_name={tool_name}, "
                    f"result={_result_data[:200]}, component=tool_executor",
                )
                increment_counter(
                    "tool_executor.executions",
                    tags={"tool_name": tool_name, "status": "error"},
                )
            else:
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
        # 确立安全上下文：让 SecurityManager 按本次执行的 (user_id, workspace) 取配置，
        # 深层调用点（approval_gate / rate_limiter 等）无需显式传参即可拿到正确策略。
        try:
            from dawei.core.security_manager import security_manager

            security_manager.set_context(user_workspace.user_id, user_workspace.absolute_path)
        except Exception as e:
            self.logger.warning(f"set security context failed: {e}")
        self.tools.clear()
        self._load_tools()
        self.logger.info("User workspace set: component=tool_executor")

    def _audit_user_id(self) -> str:
        """获取当前执行用户 ID（用于审计/PermissionError）；未知时回落 'system'。"""
        try:
            ws = getattr(self, "user_workspace", None)
            if ws is not None:
                return getattr(ws, "user_id", "system") or "system"
        except Exception:
            pass
        return "system"

    # ========================================================================
    # P3 Path B: 工具调用远程化 — 沙箱路由
    # ========================================================================

    # 沙箱可路由的工具名集合 (白名单)
    # 仅包含纯计算/文件 I/O 类工具, 不含需要宿主资源的工具 (MCP/ACP/knowledge)
    # 2026-09-13 修复: 旧名单 write_file/edit_file/smart_file_edit 不是注册工具名
    # (tool_catalog.py 实际注册 write_text_file/smart_text_edit/insert_text_content),
    # 名字不匹配导致 _should_route_to_sandbox 恒 False, 文件工具全部回落宿主执行
    SANDBOX_ROUTABLE_TOOLS: frozenset[str] = frozenset({
        "read_file", "list_files", "write_text_file", "smart_text_edit",
        "insert_text_content", "docx_read_structured", "docx_edit", "docx_diff",
    })

    def _should_route_to_sandbox(self, tool: Any) -> bool:
        """判断工具是否应路由到沙箱执行 (P3 Path B)

        条件:
        1. 环境变量 DAWEI_TOOL_EXECUTION_MODE=sandbox
        2. 工具是 CustomBaseTool 实例
        3. 工具名在白名单中
        4. 有可用的工作区路径 (用于 TrustedContext)
        """
        mode = os.environ.get("DAWEI_TOOL_EXECUTION_MODE", "host")
        if mode != "sandbox":
            return False

        if not isinstance(tool, CustomBaseTool):
            return False

        tool_name = getattr(tool, "name", "")
        if tool_name not in self.SANDBOX_ROUTABLE_TOOLS:
            return False

        if not self.user_workspace:
            return False

        ws_path = getattr(self.user_workspace, "path", None) or \
                  getattr(self.user_workspace, "workspace_path", None)
        if not ws_path:
            return False

        return True

    def _execute_tool_in_sandbox(
        self,
        tool: Any,
        tool_input: dict[str, Any],
        tool_name: str,
    ) -> str:
        """在沙箱内执行工具 (P3 Path B)

        通过 SandboxFacade.execute_tool() 将工具调用发送到沙箱 MicroVM,
        在沙箱 Python 环境中执行 tool.run(**kwargs)。

        Args:
            tool: 工具实例 (CustomBaseTool)
            tool_input: 工具参数 (已解析)
            tool_name: 工具名称

        Returns:
            工具执行结果字符串

        Raises:
            RuntimeError: 沙箱执行失败
        """
        from dawei.core.security_manager import current_user_id
        from dawei.sandbox.base import from_user_workspace
        from dawei.sandbox.sandbox_facade import SandboxFacade

        # 构建 TrustedContext (user_id 用当前会话真实用户: provider 按
        # ctx.user_id 读 configs/<uid>/security.json 解析挂载模式/配额;
        # 伪造身份 'local'/'tool-executor' 无配置文件 → 恒走缺省 ro 挂载)
        ws_path = getattr(self.user_workspace, "path", None) or \
                  getattr(self.user_workspace, "workspace_path", None)
        ctx = from_user_workspace(current_user_id(), str(ws_path))

        # 获取工具类全限定路径
        tool_class = f"{tool.__class__.__module__}.{tool.__class__.__name__}"

        self.logger.info(
            f"[P3] Routing tool to sandbox: {tool_name} ({tool_class})",
        )

        return SandboxFacade.execute_tool(ctx, tool_class, tool_input)

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
                    self._event_bus,  # 🔧 修复：添加 event_bus 参数
                    task_id=task_progress.task_id,
                    source="tool_executor",
                )
        except Exception as e:
            self.logger.error(f"Error in tool task progress callback: {e}", exc_info=True)

    async def _on_tool_task_start(self, task_id: str, context):
        """Tool task start callback."""
        try:
            # Find corresponding tool call ID
            tool_call_id = None
            for tc_id, t_id in self._active_tool_tasks.items():
                if t_id == task_id:
                    tool_call_id = tc_id
                    break

            if tool_call_id:
                # Get tool name and input from task definition
                tool_name = "unknown"
                tool_input = {}

                # Try to get tool info from task definition
                task_def = None
                for tc_id, t_id in self._active_tool_tasks.items():
                    if t_id == task_id:
                        # Find the task definition in task manager
                        if hasattr(self, "_task_manager") and self._task_manager:
                            for tid, tdef in self._task_manager._tasks.items():
                                if tid == task_id:
                                    task_def = tdef
                                    break
                            break

                if task_def and hasattr(task_def, "parameters"):
                    tool_name = task_def.parameters.get("tool_name", "unknown")
                    tool_input = task_def.parameters.get("tool_input", {})

                # Emit tool call start event
                from dawei.core.events import TaskEventType, emit_typed_event
                from dawei.entity.tool_event_data import ToolCallStartData

                await emit_typed_event(
                    TaskEventType.TOOL_CALL_START,
                    ToolCallStartData(
                        tool_name=tool_name,
                        tool_input=tool_input,
                        tool_call_id=tool_call_id,
                        task_id=task_id,
                    ),
                    self._event_bus,  # 🔧 修复：添加 event_bus 参数
                    task_id=task_id,
                    source="tool_executor",
                )

                self.logger.info(
                    f"[TOOL_EXECUTOR] 🔧 Tool call started: tool_name={tool_name}, tool_call_id={tool_call_id}, task_id={task_id}",
                )
        except Exception as e:
            self.logger.error(f"Error in tool task start callback: {e}", exc_info=True)

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
                    self._event_bus,  # 🔧 修复：添加 event_bus 参数
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
                # 🔧 严格按照数据结构判断错误状态
                if task_result.is_success:
                    # Emit tool call result event (success)
                    from dawei.core.events import TaskEventType, emit_typed_event
                    from dawei.entity.tool_event_data import ToolCallResultData

                    await emit_typed_event(
                        TaskEventType.TOOL_CALL_RESULT,
                        ToolCallResultData(
                            tool_name=f"tool_{tool_call_id}",
                            result=task_result.result,
                            is_error=False,  # ← 任务成功，is_error 必须为 False
                            tool_call_id=tool_call_id,
                            task_id=task_result.task_id,
                            execution_time=task_result.execution_time,
                        ),
                        self._event_bus,  # 🔧 修复：添加 event_bus 参数
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
                strategy=SnapshotStrategy.AUTO,
            )

            if snapshot:
                self.logger.info(f"Created snapshot before {tool_name}: {file_path}")
                return True

            return False
        except (OSError, PermissionError) as e:
            # Fast Fail: 预期的存储/IO错误不应阻止工具执行
            self.logger.warning(f"Failed to create snapshot before {tool_name}: {e}", exc_info=True)
            return False
        except Exception as e:
            # Fast Fail: 关键错误应该快速失败并抛出
            self.logger.error(f"Unexpected error creating snapshot before {tool_name}: {e}", exc_info=True)
            raise type(e)(f"Critical snapshot creation failure for tool {tool_name}: {e}") from e
