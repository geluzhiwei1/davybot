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
    use_system_command_whitelist: bool = True
    base_allowed_commands: list[str] = field(default_factory=list)
    base_denied_commands: list[str] = field(default_factory=list)
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

    # === 工作区覆盖控制 ===
    allow_workspace_override_command_security: bool = True
    allow_workspace_override_sandbox: bool = True

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any]) -> "UserSecuritySettings":
        """从字典创建用户安全配置"""
        return cls(
            # 命令执行
            enable_command_whitelist=config_dict.get("enableCommandWhitelist", True),
            use_system_command_whitelist=config_dict.get("useSystemCommandWhitelist", True),
            base_allowed_commands=config_dict.get("baseAllowedCommands", []),
            base_denied_commands=config_dict.get("baseDeniedCommands", []),
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
            # 工作区覆盖控制
            allow_workspace_override_command_security=config_dict.get(
                "allowWorkspaceOverrideCommandSecurity", True,
            ),
            allow_workspace_override_sandbox=config_dict.get(
                "allowWorkspaceOverrideSandbox", True,
            ),
        )
