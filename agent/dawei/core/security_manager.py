# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""安全配置管理器 - 全局单例

作为安全配置的唯一真相源，负责：
- 加载用户级安全配置（~/.dawei/configs/security.json）
- 合并工作区级安全覆盖（{workspace}/.dawei/security.json）
- 提供合并后的配置给所有执行层

使用:
    from dawei.core.security_manager import security_manager

    settings = security_manager.get_settings()
    if settings["enable_command_whitelist"]:
        ...
"""

import json
import logging
import threading
from pathlib import Path
from typing import Any

from dawei import get_dawei_home
from dawei.core.super_mode import is_super_mode_enabled, log_security_bypass
from dawei.workspace.user_security_settings import UserSecuritySettings

logger = logging.getLogger(__name__)

# 用户级安全配置存储路径
_SECURITY_CONFIG_FILE = "configs/security.json"


class SecurityManager:
    """安全配置全局单例"""

    def __init__(self):
        self._lock = threading.Lock()
        self._user_settings: UserSecuritySettings = UserSecuritySettings()
        self._merged: dict[str, Any] | None = None
        self._workspace_security: dict[str, Any] = {}
        self._loaded = False

    # ==================== 公共接口 ====================

    def load(self) -> None:
        """加载用户级安全配置（应用启动时调用一次）"""
        with self._lock:
            self._user_settings = self._load_user_settings()
            self._merged = None  # 强制下次 get_settings 时重新合并
            self._loaded = True
            logger.info(
                f"SecurityManager loaded: enable_command_whitelist={self._user_settings.enable_command_whitelist}, "
                f"enable_sandbox={self._user_settings.enable_sandbox}",
            )

    def set_workspace(self, workspace_path: str | Path) -> None:
        """切换工作区时调用，加载工作区级安全覆盖"""
        with self._lock:
            self._workspace_security = self._load_workspace_security(workspace_path)
            self._merged = None  # 强制重新合并
            logger.debug(f"SecurityManager: workspace security loaded from {workspace_path}")

    def update_workspace_security(self, settings: dict[str, Any]) -> None:
        """工作区安全配置变更后调用，更新内存缓存"""
        with self._lock:
            self._workspace_security = settings
            self._merged = None  # 强制重新合并
            logger.info(f"SecurityManager: workspace security updated, enable_command_whitelist={settings.get('enableCommandWhitelist')}")

    def get_settings(self) -> dict[str, Any]:
        """获取合并后的安全配置（所有执行层从这里读取）"""
        if is_super_mode_enabled():
            log_security_bypass("get_settings")
            return self._super_mode_settings()

        with self._lock:
            if self._merged is None:
                self._merged = self._merge()
            return self._merged

    def get_user_settings(self) -> UserSecuritySettings:
        """获取用户级安全配置（API 层读写用）"""
        with self._lock:
            return self._user_settings

    def update_user_settings(self, settings: UserSecuritySettings) -> None:
        """更新用户级安全配置（API 层写入后调用）"""
        with self._lock:
            self._user_settings = settings
            self._merged = None  # 强制重新合并
            logger.info(f"SecurityManager: user settings updated")

    def reload(self) -> None:
        """重新加载配置"""
        self.load()

    # ==================== 内部方法 ====================

    def _load_user_settings(self) -> UserSecuritySettings:
        """从 ~/.dawei/configs/security.json 加载用户配置"""
        config_file = get_dawei_home() / _SECURITY_CONFIG_FILE

        if not config_file.exists():
            logger.debug(f"User security config not found: {config_file}, using defaults")
            return UserSecuritySettings()

        try:
            with config_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            settings = UserSecuritySettings.from_dict(data)
            logger.info(f"User security config loaded from {config_file}")
            return settings
        except Exception as e:
            logger.error(f"Failed to load user security config: {e}, using defaults")
            return UserSecuritySettings()

    def _load_workspace_security(self, workspace_path: str | Path) -> dict[str, Any]:
        """从工作区 .dawei/settings.json 的 globalSettings.security 加载工作区级覆盖"""
        ws_path = Path(workspace_path)
        config_file = ws_path / ".dawei" / "settings.json"

        if not config_file.exists():
            return {}

        try:
            with config_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            security_data = data.get("globalSettings", {}).get("security", {})
            if security_data:
                logger.debug(f"Workspace security config loaded from {config_file}")
            return security_data if isinstance(security_data, dict) else {}
        except Exception as e:
            logger.warning(f"Failed to load workspace security config: {e}")
            return {}

    def _merge(self) -> dict[str, Any]:
        """合并用户级和工作区级配置，工作区只能收紧不能放宽"""
        user = self._user_settings
        ws = self._workspace_security

        # === 命令执行安全 ===
        if not user.allow_workspace_override_command_security:
            command = {
                "enable_command_whitelist": user.enable_command_whitelist,
                "use_system_command_whitelist": user.use_system_command_whitelist,
                "allowed_commands": list(user.base_allowed_commands),
                "denied_commands": list(user.base_denied_commands),
                "allow_shell_commands": user.allow_shell_commands,
                "allow_background_commands": user.allow_background_commands,
                "allow_pipe_commands": user.allow_pipe_commands,
                "command_execution_timeout": user.command_execution_timeout,
            }
        else:
            # 合并命令白名单
            allowed = list(user.base_allowed_commands)
            ws_allowed = ws.get("customAllowedCommands", [])
            if ws_allowed:
                allowed = list(set(allowed + ws_allowed))

            # 合并命令黑名单（拒绝优先）
            denied = list(user.base_denied_commands)
            ws_denied = ws.get("customDeniedCommands", [])
            if ws_denied:
                denied = list(set(denied + ws_denied))

            # 冲突移除
            conflicts = set(allowed) & set(denied)
            if conflicts:
                logger.warning(f"Conflicting commands removed: {conflicts}")
                allowed = [c for c in allowed if c not in conflicts]

            command = {
                "enable_command_whitelist": ws.get(
                    "enableCommandWhitelist", user.enable_command_whitelist,
                ),
                "use_system_command_whitelist": ws.get(
                    "useSystemCommandWhitelist", user.use_system_command_whitelist,
                ),
                "allowed_commands": allowed,
                "denied_commands": denied,
                "allow_shell_commands": ws.get(
                    "allowShellCommands", user.allow_shell_commands,
                ),
                "allow_background_commands": ws.get(
                    "allowBackgroundCommands", user.allow_background_commands,
                ),
                "allow_pipe_commands": ws.get(
                    "allowPipeCommands", user.allow_pipe_commands,
                ),
                "command_execution_timeout": min(
                    user.command_execution_timeout,
                    ws.get("commandExecutionTimeout", user.command_execution_timeout),
                ),
            }

        # === 容器沙箱配置 ===
        if user.allow_workspace_override_sandbox:
            sandbox = {
                "enable_sandbox": ws.get("enableSandbox", user.enable_sandbox),
                "container_runtime": ws.get("containerRuntime", user.container_runtime),
                "drop_all_capabilities": ws.get(
                    "dropAllCapabilities", user.drop_all_capabilities,
                ),
                "no_new_privileges": ws.get(
                    "noNewPrivileges", user.no_new_privileges,
                ),
                "sandbox_disable_network": ws.get(
                    "sandboxDisableNetwork", user.sandbox_disable_network,
                ),
            }
        else:
            sandbox = {
                "enable_sandbox": user.enable_sandbox,
                "container_runtime": user.container_runtime,
                "drop_all_capabilities": user.drop_all_capabilities,
                "no_new_privileges": user.no_new_privileges,
                "sandbox_disable_network": user.sandbox_disable_network,
            }

        return {**command, **sandbox}

    @staticmethod
    def _super_mode_settings() -> dict[str, Any]:
        """Super mode: 全部放开"""
        return {
            "enable_command_whitelist": False,
            "use_system_command_whitelist": False,
            "allowed_commands": [],
            "denied_commands": [],
            "allow_shell_commands": True,
            "allow_background_commands": True,
            "allow_pipe_commands": True,
            "command_execution_timeout": 300,
            "enable_sandbox": False,
            "container_runtime": "auto",
            "drop_all_capabilities": False,
            "no_new_privileges": False,
            "sandbox_disable_network": False,
        }


# ==================== 全局单例 ====================
security_manager = SecurityManager()
