# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""用户级安全配置模型

定义用户的全局默认安全策略，所有工作区继承这些配置
除非工作区明确覆盖了某些选项
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

    # === 路径安全配置 ===
    # 全局默认路径安全策略
    enable_path_traversal_protection: bool = True
    allow_absolute_paths: bool = False
    # 全局允许的文件扩展名（工作区可以扩展但不能缩小）
    base_allowed_extensions: set[str] = field(default_factory=lambda: {
        '.py', '.txt', '.md', '.json', '.yaml', '.yml', '.toml',
        '.html', '.css', '.js', '.ts', '.vue', '.jsx', '.tsx',
        '.xml', '.csv', '.sql'
    })
    # 全局禁止的文件扩展名（工作区不能允许这些）
    base_denied_extensions: set[str] = field(default_factory=lambda: {
        '.exe', '.dll', '.so', '.dylib', '.app', '.deb', '.rpm',
        '.scr', '.vbs', '.jar', '.com', '.pif', '.bat', '.sh'
    })
    max_file_size_mb: int = 100

    # === 命令执行安全配置 ===
    enable_command_whitelist: bool = True
    use_system_command_whitelist: bool = True
    # 用户级自定义命令白名单（工作区可以添加但不能删除）
    base_allowed_commands: list[str] = field(default_factory=list)
    # 用户级强制禁用的命令（工作区不能允许）
    base_denied_commands: list[str] = field(default_factory=list)
    allow_shell_commands: bool = False
    allow_background_commands: bool = False
    allow_pipe_commands: bool = False
    command_execution_timeout: int = 30

    # === 沙箱配置 ===
    # 全局默认沙箱策略
    enable_sandbox: bool = True
    sandbox_mode: Literal['docker', 'podman', 'lightweight', 'disabled'] = 'docker'
    allow_sandbox_fallback: bool = True
    # 是否强制所有工作区使用沙箱
    enforce_sandbox: bool = False  # 如果为 True，工作区不能禁用沙箱

    # === 容器运行时选择 ===
    # 当 sandbox_mode 为 'docker' 或 'podman' 时，指定使用哪个容器运行时
    container_runtime: Literal['docker', 'podman', 'auto'] = 'auto'  # auto=自动检测可用运行时

    # === 容器沙箱细粒度安全控制 ===
    # 容器 capabilities控制（移除所有capabilities会降低安全性但提高兼容性）
    drop_all_capabilities: bool = True  # True=移除所有capabilities (更安全), False=保留默认capabilities
    # 禁止获得新权限（防止权限提升攻击）
    no_new_privileges: bool = True  # True=禁止获得新权限 (更安全), False=允许提权
    # 网络访问控制（禁用网络可以防止网络攻击但会限制某些功能）
    sandbox_disable_network: bool = True  # True=禁用网络 (更安全), False=允许网络访问

    # === 模式权限配置 ===
    enable_mode_restrictions: bool = True
    plan_mode_allow_writes: bool = False
    # 用户级禁用的模式（所有工作区都不能使用）
    globally_disabled_modes: list[str] = field(default_factory=list)

    # === 工具权限配置 ===
    # 全局启用的工具组（工作区可以禁用但不能启用已禁用的组）
    base_enabled_tool_groups: list[str] = field(default_factory=lambda: [
        'read', 'browser', 'task_graph', 'workflow'
    ])
    # 全局禁用的工具组（工作区不能启用）
    base_disabled_tool_groups: list[str] = field(default_factory=list)
    # 全局禁用的具体工具
    base_disabled_tools: list[str] = field(default_factory=list)

    # === 网络安全配置 ===
    allow_network_access: bool = True
    # 全局允许的域名白名单
    base_allowed_domains: list[str] = field(default_factory=list)
    # 全局禁止的域名黑名单（工作区不能允许）
    base_denied_domains: list[str] = field(default_factory=list)
    max_network_request_size: int = 10

    # === 资源限制配置 ===
    # 用户级最大资源限制（工作区不能超过这些值）
    max_concurrent_operations: int = 5
    max_memory_mb: int = 2048
    max_execution_time: int = 300

    # === 高级安全选项 ===
    enable_security_audit_log: bool = True
    require_confirmation_for_dangerous: bool = True
    block_executable_files: bool = True
    allow_symlinks_outside_workspace: bool = False

    # === 工作区覆盖控制 ===
    # 控制工作区是否可以覆盖某些配置
    allow_workspace_override_path_security: bool = True
    allow_workspace_override_command_security: bool = True
    allow_workspace_override_sandbox: bool = True
    allow_workspace_override_tool_permissions: bool = True
    allow_workspace_override_network_security: bool = True
    allow_workspace_override_resource_limits: bool = False  # 资源限制通常不应被工作区放宽

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        from dataclasses import asdict
        data = asdict(self)
        # 转换 set 为 list
        data['base_allowed_extensions'] = list(self.base_allowed_extensions)
        data['base_denied_extensions'] = list(self.base_denied_extensions)
        return data

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any]) -> "UserSecuritySettings":
        """从字典创建用户安全配置"""
        return cls(
            # 路径安全
            enable_path_traversal_protection=config_dict.get(
                "enablePathTraversalProtection", True
            ),
            allow_absolute_paths=config_dict.get(
                "allowAbsolutePaths", False
            ),
            base_allowed_extensions=set(config_dict.get(
                "baseAllowedExtensions",
                ['.py', '.txt', '.md', '.json', '.yaml', '.yml']
            )),
            base_denied_extensions=set(config_dict.get(
                "baseDeniedExtensions",
                ['.exe', '.dll', '.so', '.dylib']
            )),
            max_file_size_mb=config_dict.get("maxFileSizeMb", 100),

            # 命令执行
            enable_command_whitelist=config_dict.get(
                "enableCommandWhitelist", True
            ),
            use_system_command_whitelist=config_dict.get(
                "useSystemCommandWhitelist", True
            ),
            base_allowed_commands=config_dict.get(
                "baseAllowedCommands", []
            ),
            base_denied_commands=config_dict.get(
                "baseDeniedCommands", []
            ),
            allow_shell_commands=config_dict.get(
                "allowShellCommands", False
            ),
            allow_background_commands=config_dict.get(
                "allowBackgroundCommands", False
            ),
            allow_pipe_commands=config_dict.get(
                "allowPipeCommands", False
            ),
            command_execution_timeout=config_dict.get(
                "commandExecutionTimeout", 30
            ),

            # 沙箱
            enable_sandbox=config_dict.get("enableSandbox", True),
            sandbox_mode=config_dict.get(
                "sandboxMode", "docker"
            ),
            allow_sandbox_fallback=config_dict.get(
                "allowSandboxFallback", True
            ),
            enforce_sandbox=config_dict.get(
                "enforceSandbox", False
            ),
            container_runtime=config_dict.get(
                "containerRuntime", "auto"
            ),
            # 容器安全控制
            drop_all_capabilities=config_dict.get(
                "dropAllCapabilities", True
            ),
            no_new_privileges=config_dict.get(
                "noNewPrivileges", True
            ),
            sandbox_disable_network=config_dict.get(
                "sandboxDisableNetwork", True
            ),

            # 模式权限
            enable_mode_restrictions=config_dict.get(
                "enableModeRestrictions", True
            ),
            plan_mode_allow_writes=config_dict.get(
                "planModeAllowWrites", False
            ),
            globally_disabled_modes=config_dict.get(
                "globallyDisabledModes", []
            ),

            # 工具权限
            base_enabled_tool_groups=config_dict.get(
                "baseEnabledToolGroups",
                ['read', 'browser', 'task_graph', 'workflow']
            ),
            base_disabled_tool_groups=config_dict.get(
                "baseDisabledToolGroups", []
            ),
            base_disabled_tools=config_dict.get(
                "baseDisabledTools", []
            ),

            # 网络安全
            allow_network_access=config_dict.get(
                "allowNetworkAccess", True
            ),
            base_allowed_domains=config_dict.get(
                "baseAllowedDomains", []
            ),
            base_denied_domains=config_dict.get(
                "baseDeniedDomains", []
            ),
            max_network_request_size=config_dict.get(
                "maxNetworkRequestSize", 10
            ),

            # 资源限制
            max_concurrent_operations=config_dict.get(
                "maxConcurrentOperations", 5
            ),
            max_memory_mb=config_dict.get("maxMemoryMb", 2048),
            max_execution_time=config_dict.get(
                "maxExecutionTime", 300
            ),

            # 高级选项
            enable_security_audit_log=config_dict.get(
                "enableSecurityAuditLog", True
            ),
            require_confirmation_for_dangerous=config_dict.get(
                "requireConfirmationForDangerous", True
            ),
            block_executable_files=config_dict.get(
                "blockExecutableFiles", True
            ),
            allow_symlinks_outside_workspace=config_dict.get(
                "allowSymlinksOutsideWorkspace", False
            ),

            # 工作区覆盖控制
            allow_workspace_override_path_security=config_dict.get(
                "allowWorkspaceOverridePathSecurity", True
            ),
            allow_workspace_override_command_security=config_dict.get(
                "allowWorkspaceOverrideCommandSecurity", True
            ),
            allow_workspace_override_sandbox=config_dict.get(
                "allowWorkspaceOverrideSandbox", True
            ),
            allow_workspace_override_tool_permissions=config_dict.get(
                "allowWorkspaceOverrideToolPermissions", True
            ),
            allow_workspace_override_network_security=config_dict.get(
                "allowWorkspaceOverrideNetworkSecurity", True
            ),
            allow_workspace_override_resource_limits=config_dict.get(
                "allowWorkspaceOverrideResourceLimits", False
            ),
        )
