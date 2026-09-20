# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Effective (merged) security policy — the typed result of merging the
user-level defaults with workspace-level overrides.

Merge semantics: override-or-inherit (NOT tighten-only)
-------------------------------------------------------
DESIGN DECISION (2026-06-16, supersedes the earlier "monotonic tighten-only"
draft): the user level supplies **default values only**; **workspaces may
freely override any field in either direction**. There is no "workspace can
only tighten" constraint.

The single merge rule, applied to every field of every domain:

    effective = workspace_value if workspace_value is present else user_default

  - scalars / booleans : workspace value wins when present; else user default
  - lists               : workspace list **replaces** the user list when the
                          workspace provides one (even an empty list); else the
                          user-level list is inherited
  - absent workspace key: inherit the user-level value unchanged

Consequences:
  - ``allow_workspace_override_*`` gates become no-ops (workspaces configure
    freely). They are retained on the user-level model for backward
    compatibility but treated as always-allow.
  - There is no "tighten-only" validation to reject a loosening override — PUT
    only performs schema validation.

Why this module exists
----------------------
``SecurityManager._merge()`` historically returned a bare ``dict`` consumed by
every execution layer. As the security model expands from 2 domains (command +
sandbox) to 12, a bare dict becomes brittle (typo'd keys silently fall back to
defaults, no single place documents the merged shape). This module defines the
typed ``EffectiveSecurityPolicy`` that all enforcement layers SHOULD read via
``security_manager.get_policy()``. The legacy ``get_settings()`` dict is
retained as a back-compat shim derived from this.

Phase 1 scope: command + sandbox (wrapped from the existing ``_merge()`` dict).
New domains (tools, filesystem, network, mcp, llm, content, autonomy, approval,
rate_limit) are added incrementally, each merged with override-or-inherit.
"""

from __future__ import annotations

from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

__all__ = [
    "EffectiveCommandPolicy",
    "EffectiveSandboxPolicy",
    "EffectiveToolPolicy",
    "EffectiveApprovalPolicy",
    "EffectiveMCPPolicy",
    "EffectiveAutonomyPolicy",
    "EffectiveRateLimitPolicy",
    "EffectiveFilesystemPolicy",
    "EffectiveNetworkPolicy",
    "EffectiveLLMPolicy",
    "EffectiveContentPolicy",
    "EffectiveSecurityPolicy",
    "TOOL_RISK_LEVELS",
    "WorkspaceSecurityOverride",
    "get_tool_risk",
    "merge_override",
    "merge_override_list",
    "risk_at_least",
]

# ==================== tool risk matrix (domain 3) ====================

#: Ordered risk levels, low → critical.
RISK_ORDER: tuple[str, ...] = ("low", "medium", "high", "critical")

#: Curated tool_name → risk level, derived from the attack-surface review (§1.3).
#: Tools absent here default to "medium".
TOOL_RISK_LEVELS: dict[str, str] = {
    # critical — arbitrary shell / arbitrary subprocess via MCP
    "execute_command": "critical",
    "use_mcp_tool": "critical",
    "connect_mcp_server": "critical",
    # high — destructive writes / shell / external process / scheduling
    "write_text_file": "high",
    "smart_text_edit": "high",
    "insert_text_content": "high",
    "shell_command": "high",
    "timer": "high",
    "call_acp_agent": "high",
    "docx_edit": "high",
    # medium — reads / subtasks / mode switch / external lookups
    "read_file": "medium",
    "access_mcp_resource": "medium",
    "new_task": "medium",
    "switch_mode": "medium",
    "docx_read_structured": "medium",
    "docx_diff": "medium",
    "query_user_knowledge_base": "medium",
    "search_user_knowledge_base": "medium",
    "search_legal_knowledge": "medium",
    "get_legal_document": "medium",
    "ask_legal_question": "medium",
    "run_slash_command": "medium",
    # low — informational / state / read-only listing
    "list_files": "low",
    "list_mcp_servers": "low",
    "disconnect_mcp_server": "low",
    "list_skills": "low",
    "search_skills": "low",
    "get_skill": "low",
    "list_skill_resources": "low",
    "read_skill_resource": "low",
    "update_todo_list": "low",
    "ask_followup_question": "low",
    "attempt_completion": "low",
    "get_task_status": "low",
    "show_cost": "low",
}

#: Default risk for tools not listed in TOOL_RISK_LEVELS.
DEFAULT_TOOL_RISK = "medium"


def get_tool_risk(tool_name: str) -> str:
    """Return the risk level for a tool (defaults to medium if unknown)."""
    return TOOL_RISK_LEVELS.get(tool_name, DEFAULT_TOOL_RISK)


def risk_at_least(level: str, threshold: str) -> bool:
    """True when ``level`` is at least as severe as ``threshold``."""
    try:
        return RISK_ORDER.index(level) >= RISK_ORDER.index(threshold)
    except ValueError:
        return False


# ==================== generic merge helpers ====================


def merge_override(user_default: Any, ws_value: Any) -> Any:
    """Override-or-inherit for a scalar/boolean field.

    The workspace value wins whenever it is present (not ``None``); otherwise
    the user-level default is inherited. Workspaces configure freely — there is
    no clamping in either direction.
    """
    return ws_value if ws_value is not None else user_default


def merge_override_list(
    user_default: Iterable[Any] | None,
    ws_value: Iterable[Any] | None,
) -> list[Any]:
    """Override-or-inherit for a list field.

    A workspace-provided list (including an empty one) **replaces** the
    user-level list. A missing key (``None``) inherits the user-level list.
    """
    if ws_value is None:
        return list(user_default or [])
    return list(ws_value)


# ==================== effective domain models (Phase 1) ====================


class EffectiveCommandPolicy(BaseModel):
    """Merged command-execution security (workspace overrides user defaults).

    allowed_sources: 命令允许列表的来源。"system"=系统白名单, "custom"=自定义列表。
    有效允许列表 = UNION("system" in sources ? 系统白名单 : ∅) ∪ ("custom" in sources ? custom_allowed_commands : ∅)
    denied 始终优先。
    """

    enable_command_whitelist: bool = True
    allowed_sources: list[str] = Field(default_factory=lambda: ["system"])
    custom_allowed_commands: list[str] = Field(default_factory=list)
    custom_denied_commands: list[str] = Field(default_factory=list)
    allow_shell_commands: bool = False
    allow_background_commands: bool = False
    allow_pipe_commands: bool = False
    command_execution_timeout: int = 30


class EffectiveSandboxPolicy(BaseModel):
    """Merged container-sandbox security (workspace overrides user defaults)."""

    enable_sandbox: bool = False
    container_runtime: Literal["docker", "podman", "auto"] = "auto"
    drop_all_capabilities: bool = True
    no_new_privileges: bool = True
    sandbox_disable_network: bool = True


class EffectiveToolPolicy(BaseModel):
    """Merged tool permissions + risk-gate threshold (override-or-inherit)."""

    #: Empty list = all tools allowed (inherit). Non-empty = only these permitted.
    allowed_tools: list[str] = Field(default_factory=list)
    #: Tools always blocked (deny wins over allow).
    denied_tools: list[str] = Field(default_factory=list)
    #: Risk level at/above which execution requires human approval (P2.2 gate).
    #: "critical" = effectively off until the approval channel is wired.
    require_approval_risk: Literal["low", "medium", "high", "critical", "never"] = "critical"


class EffectiveApprovalPolicy(BaseModel):
    """Merged human-in-the-loop approval policy (override-or-inherit).

    Default ``enabled=False`` keeps the gate inert (auto-allow) until the WS
    approval channel is wired (P2.2) — a safe, zero-behavior-change rollout.
    """

    enabled: bool = False
    #: Tools at/above this risk require confirmation before execution.
    required_for_risk: Literal["low", "medium", "high", "critical", "never"] = "critical"
    #: Tools always requiring approval regardless of risk.
    always_require_approval_tools: list[str] = Field(default_factory=list)
    #: Seconds to wait for a user decision before auto-denying.
    approval_timeout_seconds: float = 120.0
    #: Behavior when approval is required but no interactive channel is connected.
    #: "allow" = functional (headless/scheduled tasks proceed); "deny" = fail-closed.
    no_channel_behavior: Literal["allow", "deny"] = "allow"


class EffectiveMCPPolicy(BaseModel):
    """MCP server allow/deny policy (override-or-inherit).

    MCP tools are already ``critical`` risk (covered by the approval gate at the
    ToolExecutor level); this policy gates WHICH MCP servers may be called.
    """

    #: Empty = all configured servers allowed. Non-empty = only these permitted.
    allowed_mcp_servers: list[str] = Field(default_factory=list)
    #: Servers always blocked.
    denied_mcp_servers: list[str] = Field(default_factory=list)


class EffectiveAutonomyPolicy(BaseModel):
    """Autonomous / scheduled execution policy (override-or-inherit).

    Gates how deeply an agent may recurse into subtasks and whether it may
    self-schedule future runs (which spawn a full Agent with all tools).
    """

    #: Whether scheduled (timer/cron) tasks may create a full Agent at all.
    allow_scheduled_tasks: bool = True
    #: Whether recurring (cron) schedules are permitted (riskier than one-shot).
    allow_cron: bool = False
    #: Maximum TaskGraph nesting depth (root = 1). Subtasks beyond this are denied.
    max_subtask_depth: int = 5


class EffectiveRateLimitPolicy(BaseModel):
    """Per-minute rate limits (override-or-inherit).

    Default ``0`` means unlimited — opt-in caps to stop runaway agents.
    """

    #: Max tool executions per minute (sliding window). 0 = unlimited.
    tool_calls_per_minute: int = 0


class EffectiveFilesystemPolicy(BaseModel):
    """Filesystem access policy (override-or-inherit).

    ``blocked_paths`` is an additional user-configurable denylist of resolved
    path PREFIXES enforced at the central ``UserWorkspace.is_path_allowed``
    gate (so every file tool inherits it). Matching is case-insensitive prefix.
    Default empty = no extra restriction (existing path_security still applies).
    """

    #: Resolved path prefixes always denied (case-insensitive). e.g. ~/.ssh,
    #: the security config dir, etc.
    blocked_paths: list[str] = Field(default_factory=list)


class EffectiveNetworkPolicy(BaseModel):
    """出站网络访问策略（override-or-inherit）。空 = 不额外限制。"""

    allowed_hosts: list[str] = Field(default_factory=list)
    blocked_hosts: list[str] = Field(default_factory=list)


class EffectiveLLMPolicy(BaseModel):
    """LLM 模型与成本策略（override-or-inherit）。"""

    allowed_models: list[str] = Field(default_factory=list)
    blocked_models: list[str] = Field(default_factory=list)
    daily_cost_cap: float = 0.0  # 0 = 不限


class EffectiveContentPolicy(BaseModel):
    """内容安全策略（override-or-inherit）。"""

    blocked_patterns: list[str] = Field(default_factory=list)
    prompt_injection_defense: bool = True


class EffectiveSecurityPolicy(BaseModel):
    """The typed, merged security policy — single source of truth for enforcement.

    Phase 1 populates ``command`` + ``sandbox``. The remaining domains are added
    in P2-P3 as additional fields; ``get_policy()`` consumers keep working
    because every field has a default.
    """

    command: EffectiveCommandPolicy = Field(default_factory=EffectiveCommandPolicy)
    sandbox: EffectiveSandboxPolicy = Field(default_factory=EffectiveSandboxPolicy)
    # P2-P3 (TODO):
    tools: EffectiveToolPolicy = Field(default_factory=EffectiveToolPolicy)
    approval: EffectiveApprovalPolicy = Field(default_factory=EffectiveApprovalPolicy)
    mcp: EffectiveMCPPolicy = Field(default_factory=EffectiveMCPPolicy)
    autonomy: EffectiveAutonomyPolicy = Field(default_factory=EffectiveAutonomyPolicy)
    rate_limit: EffectiveRateLimitPolicy = Field(default_factory=EffectiveRateLimitPolicy)
    filesystem: EffectiveFilesystemPolicy = Field(default_factory=EffectiveFilesystemPolicy)
    network: EffectiveNetworkPolicy = Field(default_factory=EffectiveNetworkPolicy)
    llm: EffectiveLLMPolicy = Field(default_factory=EffectiveLLMPolicy)
    content: EffectiveContentPolicy = Field(default_factory=EffectiveContentPolicy)

    @classmethod
    def from_merged_dict(cls, merged: dict[str, Any]) -> "EffectiveSecurityPolicy":
        """Build from the legacy ``SecurityManager._merge()`` dict shape.

        Allows a zero-risk, additive rollout: the existing merge logic is reused
        verbatim and only wrapped in typed models here.
        """
        command = EffectiveCommandPolicy(
            enable_command_whitelist=merged.get("enable_command_whitelist", True),
            allowed_sources=list(merged.get("allowed_sources", ["system"])),
            custom_allowed_commands=list(merged.get("custom_allowed_commands", [])),
            custom_denied_commands=list(merged.get("custom_denied_commands", [])),
            allow_shell_commands=merged.get("allow_shell_commands", False),
            allow_background_commands=merged.get("allow_background_commands", False),
            allow_pipe_commands=merged.get("allow_pipe_commands", False),
            command_execution_timeout=merged.get("command_execution_timeout", 30),
        )
        sandbox = EffectiveSandboxPolicy(
            enable_sandbox=merged.get("enable_sandbox", False),
            container_runtime=merged.get("container_runtime", "auto"),
            drop_all_capabilities=merged.get("drop_all_capabilities", True),
            no_new_privileges=merged.get("no_new_privileges", True),
            sandbox_disable_network=merged.get("sandbox_disable_network", True),
        )
        tools = EffectiveToolPolicy(
            allowed_tools=list(merged.get("allowed_tools", [])),
            denied_tools=list(merged.get("denied_tools", [])),
            require_approval_risk=merged.get("require_approval_risk", "critical"),
        )
        approval = EffectiveApprovalPolicy(
            enabled=merged.get("approval_enabled", False),
            required_for_risk=merged.get("approval_required_for_risk", "critical"),
            always_require_approval_tools=list(
                merged.get("approval_always_require", [])
            ),
            approval_timeout_seconds=merged.get("approval_timeout_seconds", 120),
            no_channel_behavior=merged.get("approval_no_channel_behavior", "allow"),
        )
        mcp = EffectiveMCPPolicy(
            allowed_mcp_servers=list(merged.get("allowed_mcp_servers", [])),
            denied_mcp_servers=list(merged.get("denied_mcp_servers", [])),
        )
        autonomy = EffectiveAutonomyPolicy(
            allow_scheduled_tasks=merged.get("allow_scheduled_tasks", True),
            allow_cron=merged.get("allow_cron", False),
            max_subtask_depth=merged.get("max_subtask_depth", 5),
        )
        rate_limit = EffectiveRateLimitPolicy(
            tool_calls_per_minute=merged.get("tool_calls_per_minute", 0),
        )
        filesystem = EffectiveFilesystemPolicy(
            blocked_paths=list(merged.get("blocked_paths", [])),
        )
        network = EffectiveNetworkPolicy(
            allowed_hosts=list(merged.get("allowed_hosts", [])),
            blocked_hosts=list(merged.get("blocked_hosts", [])),
        )
        llm = EffectiveLLMPolicy(
            allowed_models=list(merged.get("allowed_models", [])),
            blocked_models=list(merged.get("blocked_models", [])),
            daily_cost_cap=merged.get("daily_cost_cap", 0.0),
        )
        content = EffectiveContentPolicy(
            blocked_patterns=list(merged.get("blocked_patterns", [])),
            prompt_injection_defense=merged.get("prompt_injection_defense", True),
        )
        return cls(
            command=command,
            sandbox=sandbox,
            tools=tools,
            approval=approval,
            mcp=mcp,
            autonomy=autonomy,
            rate_limit=rate_limit,
            filesystem=filesystem,
            network=network,
            llm=llm,
            content=content,
        )


# ==================== workspace override input schema ====================


class WorkspaceSecurityOverride(BaseModel):
    """Validation schema for the workspace security override PUT body.

    Accepts the frontend camelCase shape and validates type / enum / range of
    the known command + sandbox fields. Unknown keys are ignored (forward-compat
    for new domains added in P2-P3). All fields optional: a missing field means
    "inherit the user-level default" (override-or-inherit, see module docstring).

    Usage in the API layer::

        try:
            override = WorkspaceSecurityOverride.model_validate(payload)
        except ValidationError:
            raise HTTPException(422, ...)   # schema error (NOT a "loosening" rejection)

    Persist ``override.model_dump(exclude_none=True, by_alias=True)`` (camelCase,
    only the explicitly-set fields).
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    # command domain
    enable_command_whitelist: bool | None = None
    allowed_sources: list[str] | None = None
    custom_allowed_commands: list[str] | None = None
    custom_denied_commands: list[str] | None = None
    allow_shell_commands: bool | None = None
    allow_background_commands: bool | None = None
    allow_pipe_commands: bool | None = None
    command_execution_timeout: int | None = Field(default=None, ge=1, le=3600)

    # sandbox domain
    enable_sandbox: bool | None = None
    container_runtime: Literal["docker", "podman", "auto"] | None = None
    drop_all_capabilities: bool | None = None
    no_new_privileges: bool | None = None
    sandbox_disable_network: bool | None = None

    # tools domain (override-or-inherit over the user-level baseline)
    custom_allowed_tools: list[str] | None = None
    custom_denied_tools: list[str] | None = None
    require_approval_risk: Literal["low", "medium", "high", "critical", "never"] | None = None

    # approval domain (override-or-inherit)
    approval_enabled: bool | None = None
    approval_required_for_risk: Literal["low", "medium", "high", "critical", "never"] | None = None
    approval_always_require: list[str] | None = None
    approval_timeout_seconds: float | None = Field(default=None, ge=1, le=3600)
    approval_no_channel_behavior: Literal["allow", "deny"] | None = None

    # mcp domain (override-or-inherit)
    custom_allowed_mcp_servers: list[str] | None = None
    custom_denied_mcp_servers: list[str] | None = None

    # autonomy domain (override-or-inherit)
    allow_scheduled_tasks: bool | None = None
    allow_cron: bool | None = None
    max_subtask_depth: int | None = Field(default=None, ge=1, le=50)

    # rate_limit domain (override-or-inherit)
    tool_calls_per_minute: int | None = Field(default=None, ge=0, le=100000)

    # filesystem domain (override-or-inherit)
    custom_blocked_paths: list[str] | None = None

    # network domain (override-or-inherit)
    custom_allowed_hosts: list[str] | None = None
    custom_blocked_hosts: list[str] | None = None

    # llm domain (override-or-inherit)
    custom_allowed_models: list[str] | None = None
    custom_blocked_models: list[str] | None = None
    daily_cost_cap: float | None = Field(default=None, ge=0)

    # content domain (override-or-inherit)
    custom_blocked_patterns: list[str] | None = None
    prompt_injection_defense: bool | None = None
