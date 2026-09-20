# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""用户级安全配置模型

定义用户的全局默认安全策略，所有工作区继承这些配置
除非工作区明确覆盖了某些选项

配置项：
- 命令执行安全（CommandExecutor / CommandWhitelist）
- 容器沙箱配置（SandboxManager / SandboxConfig）
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass
class UserSecuritySettings:
    """用户级安全配置类

    作为所有工作区的默认安全策略，工作区可以覆盖这些设置
    """

    # === 命令执行安全配置 ===
    enable_command_whitelist: bool = True
    # allowed_sources: 命令允许列表的来源。"system"=系统白名单, "custom"=自定义列表
    # 例: ["system"]=只用系统白名单, ["system","custom"]=联合, ["custom"]=只用自定义
    allowed_sources: list[str] = field(default_factory=lambda: ["system"])
    # 自定义允许/拒绝命令列表（配合 allowed_sources 使用）
    custom_allowed_commands: list[str] = field(default_factory=list)
    custom_denied_commands: list[str] = field(default_factory=list)
    allow_shell_commands: bool = False
    allow_background_commands: bool = False
    allow_pipe_commands: bool = False
    command_execution_timeout: int = 30

    # === 容器沙箱配置 ===
    enable_sandbox: bool = False
    container_runtime: Literal["docker", "podman", "auto"] = "auto"
    drop_all_capabilities: bool = True
    no_new_privileges: bool = True
    sandbox_disable_network: bool = True

    # === 沙箱 Provider v2 配置 ===
    # sandbox_provider: 沙箱后端类型 "auto"|"subprocess"|"docker"|"e2b"
    sandbox_provider: str = "auto"
    # workspace_mount_mode: 工作区挂载模式 "ro"=只读挂载, "rw"=读写挂载, "none"=不挂载
    workspace_mount_mode: str = "ro"
    # virtiofs_enabled: 是否启用 virtiofs（仅 e2b/CubeSandbox 生效）
    virtiofs_enabled: bool = False

    # === 工具权限与风险分级（P2.1）===
    base_allowed_tools: list[str] = field(default_factory=list)
    base_denied_tools: list[str] = field(default_factory=list)
    require_approval_risk: str = "critical"

    # === 审批工作流（P2.2）===
    approval_enabled: bool = False
    approval_required_for_risk: str = "critical"
    approval_always_require: list[str] = field(default_factory=list)
    approval_timeout_seconds: float = 120.0
    approval_no_channel_behavior: str = "allow"

    # === MCP 服务策略（P3 域6）===
    base_allowed_mcp_servers: list[str] = field(default_factory=list)
    base_denied_mcp_servers: list[str] = field(default_factory=list)

    # === 自主执行策略（P3 域9）===
    allow_scheduled_tasks: bool = True
    allow_cron: bool = False
    max_subtask_depth: int = 5

    # === 速率限制（P3 域11）===
    tool_calls_per_minute: int = 0  # 0 = 不限

    # === 文件系统（P3 域4）===
    base_blocked_paths: list[str] = field(default_factory=list)

    # === 网络策略（域5）===
    base_allowed_hosts: list[str] = field(default_factory=list)
    base_blocked_hosts: list[str] = field(default_factory=list)

    # === LLM 策略（域7）===
    base_allowed_models: list[str] = field(default_factory=list)
    base_blocked_models: list[str] = field(default_factory=list)
    daily_cost_cap: float = 0.0  # 0 = 不限

    # === 内容策略（域8）===
    base_blocked_patterns: list[str] = field(default_factory=list)
    prompt_injection_defense: bool = True

    # === 工作区覆盖控制 ===
    allow_workspace_override_command_security: bool = True
    allow_workspace_override_sandbox: bool = True

    def to_dict(self) -> dict[str, Any]:
        """转换为 camelCase 字典（与 from_dict / 前端约定一致，保证持久化往返一致）。"""
        from dataclasses import asdict

        def _camelize(key: str) -> str:
            parts = key.split("_")
            return parts[0] + "".join(p.title() for p in parts[1:])

        return {_camelize(k): v for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any]) -> "UserSecuritySettings":
        """从字典创建用户安全配置"""
        return cls(
            # 命令执行
            enable_command_whitelist=config_dict.get("enableCommandWhitelist", True),
            allowed_sources=config_dict.get("allowedSources", ["system"]),
            custom_allowed_commands=config_dict.get("customAllowedCommands", []),
            custom_denied_commands=config_dict.get("customDeniedCommands", []),
            allow_shell_commands=config_dict.get("allowShellCommands", False),
            allow_background_commands=config_dict.get("allowBackgroundCommands", False),
            allow_pipe_commands=config_dict.get("allowPipeCommands", False),
            command_execution_timeout=config_dict.get("commandExecutionTimeout", 30),
            # 容器沙箱
            enable_sandbox=config_dict.get("enableSandbox", False),
            container_runtime=config_dict.get("containerRuntime", "auto"),
            drop_all_capabilities=config_dict.get("dropAllCapabilities", True),
            no_new_privileges=config_dict.get("noNewPrivileges", True),
            sandbox_disable_network=config_dict.get("sandboxDisableNetwork", True),
            # 沙箱 Provider v2
            sandbox_provider=config_dict.get("sandboxProvider", "auto"),
            workspace_mount_mode=config_dict.get("workspaceMountMode", "ro"),
            virtiofs_enabled=config_dict.get("virtiofsEnabled", False),
            # 工具权限与风险分级
            base_allowed_tools=config_dict.get("baseAllowedTools", []),
            base_denied_tools=config_dict.get("baseDeniedTools", []),
            require_approval_risk=config_dict.get("requireApprovalRisk", "critical"),
            # 审批工作流
            approval_enabled=config_dict.get("approvalEnabled", False),
            approval_required_for_risk=config_dict.get("approvalRequiredForRisk", "critical"),
            approval_always_require=config_dict.get("approvalAlwaysRequire", []),
            approval_timeout_seconds=config_dict.get("approvalTimeoutSeconds", 120.0),
            approval_no_channel_behavior=config_dict.get("approvalNoChannelBehavior", "allow"),
            # MCP 服务策略
            base_allowed_mcp_servers=config_dict.get("baseAllowedMcpServers", []),
            base_denied_mcp_servers=config_dict.get("baseDeniedMcpServers", []),
            # 自主执行
            allow_scheduled_tasks=config_dict.get("allowScheduledTasks", True),
            allow_cron=config_dict.get("allowCron", False),
            max_subtask_depth=config_dict.get("maxSubtaskDepth", 5),
            # 速率限制
            tool_calls_per_minute=config_dict.get("toolCallsPerMinute", 0),
            # 文件系统
            base_blocked_paths=config_dict.get("baseBlockedPaths", []),
            # 网络
            base_allowed_hosts=config_dict.get("baseAllowedHosts", []),
            base_blocked_hosts=config_dict.get("baseBlockedHosts", []),
            # LLM
            base_allowed_models=config_dict.get("baseAllowedModels", []),
            base_blocked_models=config_dict.get("baseBlockedModels", []),
            daily_cost_cap=config_dict.get("dailyCostCap", 0.0),
            # 内容
            base_blocked_patterns=config_dict.get("baseBlockedPatterns", []),
            prompt_injection_defense=config_dict.get("promptInjectionDefense", True),
            # 工作区覆盖控制
            allow_workspace_override_command_security=config_dict.get(
                "allowWorkspaceOverrideCommandSecurity", True,
            ),
            allow_workspace_override_sandbox=config_dict.get(
                "allowWorkspaceOverrideSandbox", True,
            ),
        )
