# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""安全配置合并器

负责合并用户级和工作区级安全配置，生成有效配置
"""

import logging
from typing import Any

from dawei.workspace.user_security_settings import UserSecuritySettings

logger = logging.getLogger(__name__)


class SecuritySettingsMerger:
    """安全配置合并器

    合并规则：
    1. 工作区配置优先于用户配置
    2. 用户配置中的"强制"设置不能被工作区覆盖
    3. 工作区只能收紧用户配置，不能放宽（除非用户明确允许）
    """

    @staticmethod
    def merge(
        user_settings: UserSecuritySettings,
        workspace_settings: dict[str, Any]
    ) -> dict[str, Any]:
        """合并用户和工作区安全配置

        Args:
            user_settings: 用户级安全配置
            workspace_settings: 工作区级安全配置（从 WorkspaceSettings.security 获取）

        Returns:
            dict: 合并后的有效配置
        """
        # 提取工作区安全配置
        workspace_security = workspace_settings.get('security', {})

        # === 路径安全合并 ===
        path_security = SecuritySettingsMerger._merge_path_security(
            user_settings, workspace_security
        )

        # === 命令执行安全合并 ===
        command_security = SecuritySettingsMerger._merge_command_security(
            user_settings, workspace_security
        )

        # === 沙箱配置合并 ===
        sandbox_config = SecuritySettingsMerger._merge_sandbox_config(
            user_settings, workspace_security
        )

        # === 模式权限合并 ===
        mode_permissions = SecuritySettingsMerger._merge_mode_permissions(
            user_settings, workspace_security
        )

        # === 工具权限合并 ===
        tool_permissions = SecuritySettingsMerger._merge_tool_permissions(
            user_settings, workspace_security
        )

        # === 网络安全合并 ===
        network_security = SecuritySettingsMerger._merge_network_security(
            user_settings, workspace_security
        )

        # === 资源限制合并 ===
        resource_limits = SecuritySettingsMerger._merge_resource_limits(
            user_settings, workspace_security
        )

        # === 高级选项合并 ===
        advanced_options = SecuritySettingsMerger._merge_advanced_options(
            user_settings, workspace_security
        )

        # 构建有效配置
        return {
            **path_security,
            **command_security,
            **sandbox_config,
            **mode_permissions,
            **tool_permissions,
            **network_security,
            **resource_limits,
            **advanced_options,
        }

    @staticmethod
    def _merge_path_security(
        user: UserSecuritySettings,
        workspace: dict[str, Any]
    ) -> dict[str, Any]:
        """合并路径安全配置"""
        if not user.allow_workspace_override_path_security:
            return {
                "enable_path_traversal_protection": user.enable_path_traversal_protection,
                "allow_absolute_paths": user.allow_absolute_paths,
                "allowed_file_extensions": list(user.base_allowed_extensions),
                "denied_file_extensions": list(user.base_denied_extensions),
                "max_file_size_mb": user.max_file_size_mb,
            }

        # 合并扩展名
        allowed_exts = user.base_allowed_extensions.copy()
        ws_allowed = workspace.get('allowedFileExtensions', [])
        if ws_allowed:
            allowed_exts.update(ws_allowed)

        denied_exts = user.base_denied_extensions.copy()
        ws_denied = workspace.get('deniedFileExtensions', [])
        if ws_denied:
            denied_exts.update(ws_denied)

        # 移除冲突项（拒绝优先）
        conflicting = allowed_exts & denied_exts
        if conflicting:
            logger.warning(
                f"Conflicting file extensions: {conflicting}. "
                "Denied extensions take precedence."
            )
            allowed_exts -= conflicting

        return {
            "enable_path_traversal_protection": workspace.get(
                'enablePathTraversalProtection',
                user.enable_path_traversal_protection
            ),
            "allow_absolute_paths": workspace.get(
                'allowAbsolutePaths',
                user.allow_absolute_paths
            ),
            "allowed_file_extensions": list(allowed_exts),
            "denied_file_extensions": list(denied_exts),
            "max_file_size_mb": min(
                user.max_file_size_mb,
                workspace.get('maxFileSizeMb', user.max_file_size_mb)
            ),
        }

    @staticmethod
    def _merge_command_security(
        user: UserSecuritySettings,
        workspace: dict[str, Any]
    ) -> dict[str, Any]:
        """合并命令执行安全配置"""
        if not user.allow_workspace_override_command_security:
            return {
                "enable_command_whitelist": user.enable_command_whitelist,
                "use_system_command_whitelist": user.use_system_command_whitelist,
                "allowed_commands": user.base_allowed_commands.copy(),
                "denied_commands": user.base_denied_commands.copy(),
                "allow_shell_commands": user.allow_shell_commands,
                "allow_background_commands": user.allow_background_commands,
                "allow_pipe_commands": user.allow_pipe_commands,
                "command_execution_timeout": user.command_execution_timeout,
            }

        # 合并命令白名单
        allowed_cmds = user.base_allowed_commands.copy()
        ws_allowed = workspace.get('customAllowedCommands', [])
        if ws_allowed:
            allowed_cmds.extend(ws_allowed)
            allowed_cmds = list(set(allowed_cmds))

        # 合并命令黑名单
        denied_cmds = user.base_denied_commands.copy()
        ws_denied = workspace.get('customDeniedCommands', [])
        if ws_denied:
            denied_cmds.extend(ws_denied)
            denied_cmds = list(set(denied_cmds))

        # 移除冲突（拒绝优先）
        conflicting = set(allowed_cmds) & set(denied_cmds)
        if conflicting:
            logger.warning(
                f"Conflicting commands: {conflicting}. "
                "Denied commands take precedence."
            )
            allowed_cmds = [cmd for cmd in allowed_cmds if cmd not in conflicting]

        return {
            "enable_command_whitelist": workspace.get(
                'enableCommandWhitelist',
                user.enable_command_whitelist
            ),
            "use_system_command_whitelist": workspace.get(
                'useSystemCommandWhitelist',
                user.use_system_command_whitelist
            ),
            "allowed_commands": allowed_cmds,
            "denied_commands": denied_cmds,
            "allow_shell_commands": workspace.get(
                'allowShellCommands',
                user.allow_shell_commands
            ),
            "allow_background_commands": workspace.get(
                'allowBackgroundCommands',
                user.allow_background_commands
            ),
            "allow_pipe_commands": workspace.get(
                'allowPipeCommands',
                user.allow_pipe_commands
            ),
            "command_execution_timeout": min(
                user.command_execution_timeout,
                workspace.get('commandExecutionTimeout', user.command_execution_timeout)
            ),
        }

    @staticmethod
    def _merge_sandbox_config(
        user: UserSecuritySettings,
        workspace: dict[str, Any]
    ) -> dict[str, Any]:
        """合并沙箱配置"""
        # 如果用户强制执行沙箱，工作区不能禁用
        if user.enforce_sandbox:
            return {
                "enable_sandbox": True,
                "sandbox_mode": user.sandbox_mode,
                "allow_sandbox_fallback": user.allow_sandbox_fallback,
            }

        if not user.allow_workspace_override_sandbox:
            return {
                "enable_sandbox": user.enable_sandbox,
                "sandbox_mode": user.sandbox_mode,
                "allow_sandbox_fallback": user.allow_sandbox_fallback,
            }

        return {
            "enable_sandbox": workspace.get(
                'enableSandbox',
                user.enable_sandbox
            ),
            "sandbox_mode": workspace.get(
                'sandboxMode',
                user.sandbox_mode
            ),
            "allow_sandbox_fallback": workspace.get(
                'allowSandboxFallback',
                user.allow_sandbox_fallback
            ),
        }

    @staticmethod
    def _merge_mode_permissions(
        user: UserSecuritySettings,
        workspace: dict[str, Any]
    ) -> dict[str, Any]:
        """合并模式权限配置"""
        # 合并禁用的模式（用户级+工作区级）
        restricted_modes = user.globally_disabled_modes.copy()
        ws_restricted = workspace.get('restrictedModes', [])
        if ws_restricted:
            restricted_modes.extend(ws_restricted)
            restricted_modes = list(set(restricted_modes))

        return {
            "enable_mode_restrictions": workspace.get(
                'enableModeRestrictions',
                user.enable_mode_restrictions
            ),
            "plan_mode_allow_writes": workspace.get(
                'planModeAllowWrites',
                user.plan_mode_allow_writes
            ),
            "restricted_modes": restricted_modes,
        }

    @staticmethod
    def _merge_tool_permissions(
        user: UserSecuritySettings,
        workspace: dict[str, Any]
    ) -> dict[str, Any]:
        """合并工具权限配置"""
        if not user.allow_workspace_override_tool_permissions:
            return {
                "enabled_tool_groups": user.base_enabled_tool_groups.copy(),
                "disabled_tool_groups": user.base_disabled_tool_groups.copy(),
                "disabled_tools": user.base_disabled_tools.copy(),
            }

        # 合并启用的工具组（工作区不能启用用户禁用的组）
        enabled_groups = user.base_enabled_tool_groups.copy()
        ws_enabled = workspace.get('enabledToolGroups', [])
        if ws_enabled:
            for group in ws_enabled:
                if group not in user.base_disabled_tool_groups:
                    enabled_groups.append(group)
            enabled_groups = list(set(enabled_groups))

        # 合并禁用的工具组
        disabled_groups = user.base_disabled_tool_groups.copy()
        ws_disabled_groups = workspace.get('disabledToolGroups', [])
        if ws_disabled_groups:
            disabled_groups.extend(ws_disabled_groups)
            disabled_groups = list(set(disabled_groups))

        # 移除冲突（禁用优先）
        conflicting = set(enabled_groups) & set(disabled_groups)
        if conflicting:
            logger.warning(
                f"Conflicting tool groups: {conflicting}. "
                "Disabled groups take precedence."
            )
            enabled_groups = [g for g in enabled_groups if g not in conflicting]

        # 合并禁用的工具
        disabled_tools = user.base_disabled_tools.copy()
        ws_disabled_tools = workspace.get('disabledTools', [])
        if ws_disabled_tools:
            disabled_tools.extend(ws_disabled_tools)
            disabled_tools = list(set(disabled_tools))

        return {
            "enabled_tool_groups": enabled_groups,
            "disabled_tool_groups": disabled_groups,
            "disabled_tools": disabled_tools,
        }

    @staticmethod
    def _merge_network_security(
        user: UserSecuritySettings,
        workspace: dict[str, Any]
    ) -> dict[str, Any]:
        """合并网络安全配置"""
        if not user.allow_workspace_override_network_security:
            return {
                "allow_network_access": user.allow_network_access,
                "allowed_network_domains": user.base_allowed_domains.copy(),
                "denied_network_domains": user.base_denied_domains.copy(),
                "max_network_request_size": user.max_network_request_size,
            }

        # 合并允许的域名（工作区不能添加用户禁止的域名）
        allowed_domains = user.base_allowed_domains.copy()
        ws_allowed = workspace.get('allowedNetworkDomains', [])
        if ws_allowed:
            for domain in ws_allowed:
                if domain not in user.base_denied_domains:
                    allowed_domains.append(domain)
            allowed_domains = list(set(allowed_domains))

        # 合并禁止的域名
        denied_domains = user.base_denied_domains.copy()
        ws_denied = workspace.get('deniedNetworkDomains', [])
        if ws_denied:
            denied_domains.extend(ws_denied)
            denied_domains = list(set(denied_domains))

        # 移除冲突（禁止优先）
        conflicting = set(allowed_domains) & set(denied_domains)
        if conflicting:
            logger.warning(
                f"Conflicting domains: {conflicting}. "
                "Denied domains take precedence."
            )
            allowed_domains = [d for d in allowed_domains if d not in conflicting]

        return {
            "allow_network_access": workspace.get(
                'allowNetworkAccess',
                user.allow_network_access
            ),
            "allowed_network_domains": allowed_domains,
            "denied_network_domains": denied_domains,
            "max_network_request_size": min(
                user.max_network_request_size,
                workspace.get('maxNetworkRequestSize', user.max_network_request_size)
            ),
        }

    @staticmethod
    def _merge_resource_limits(
        user: UserSecuritySettings,
        workspace: dict[str, Any]
    ) -> dict[str, Any]:
        """合并资源限制配置"""
        # 资源限制通常不应被工作区放宽
        max_ops = user.max_concurrent_operations
        max_mem = user.max_memory_mb
        max_time = user.max_execution_time

        # 如果用户允许覆盖，工作区可以收紧限制
        if user.allow_workspace_override_resource_limits:
            max_ops = min(max_ops, workspace.get('maxConcurrentOperations', max_ops))
            max_mem = min(max_mem, workspace.get('maxMemoryMb', max_mem))
            max_time = min(max_time, workspace.get('maxExecutionTime', max_time))

        return {
            "max_concurrent_operations": max_ops,
            "max_memory_mb": max_mem,
            "max_execution_time": max_time,
        }

    @staticmethod
    def _merge_advanced_options(
        user: UserSecuritySettings,
        workspace: dict[str, Any]
    ) -> dict[str, Any]:
        """合并高级安全选项"""
        # 高级选项采用"最安全"原则
        return {
            "enable_security_audit_log": user.enable_security_audit_log
            or workspace.get('enableSecurityAuditLog', False),
            "require_confirmation_for_dangerous": (
                user.require_confirmation_for_dangerous
                or workspace.get('requireConfirmationForDangerous', False)
            ),
            "block_executable_files": (
                user.block_executable_files
                or workspace.get('blockExecutableFiles', False)
            ),
            "allow_symlinks_outside_workspace": (
                user.allow_symlinks_outside_workspace
                and workspace.get('allowSymlinksOutsideWorkspace', False)
            ),  # 只有两个都允许才允许
        }
