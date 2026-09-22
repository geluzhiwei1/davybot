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

import contextvars
import json
import logging
import threading
from pathlib import Path
from typing import Any

from dawei import get_dawei_home
from dawei.core.effective_policy import EffectiveSecurityPolicy, merge_override, merge_override_list
from dawei.core.super_mode import is_super_mode_enabled, log_security_bypass
from dawei.workspace.user_security_settings import UserSecuritySettings

logger = logging.getLogger(__name__)

# 用户级安全配置按 user_id 分目录存储：configs/{user_id}/security.json

# 运行时安全上下文（per-coroutine）：用 contextvar 替代全局指针，消除并发多工作区下
# 的竞态——每个 asyncio task 拥有独立上下文副本，set_context 只影响当前协程链，
# 深层调用点（approval_gate / rate_limiter 等）的 get_policy() 无参调用各自取到
# 属于本次执行的 (user_id, workspace_id)，不会互相覆盖。
_CTX_USER_ID: contextvars.ContextVar[str] = contextvars.ContextVar(
    "dawei_security_user_id", default="default_user"
)
_CTX_WORKSPACE_ID: contextvars.ContextVar[str] = contextvars.ContextVar(
    "dawei_security_workspace_id", default=""
)


def current_user_id() -> str:
    """当前协程上下文的安全用户 ID（无上下文时 default_user）。

    沙箱 TrustedContext 构造点统一用它取真实会话用户，避免各处硬编码
    'local' / 'tool-executor' 等无 security.json 的服务身份 ——
    provider 按 ctx.user_id 读用户配置（挂载模式/配额），伪造身份会
    全部回落缺省（ro 挂载），且绕过 per-user 配额。
    """
    return _CTX_USER_ID.get()


class SecurityManager:
    """安全配置全局单例（多租户：按 user_id + workspace_id 分键隔离）"""

    def __init__(self):
        self._lock = threading.Lock()
        # 多租户存储：user_id → 用户级配置； (user_id, workspace_id) → 工作区级覆盖
        self._user_settings: dict[str, UserSecuritySettings] = {}
        self._workspace_security: dict[tuple[str, str], dict[str, Any]] = {}
        # 原始 JSON 缓存（user_id → security.json 原文 dict）：用于区分
        # 「显式配置」与「模型缺省」（如 commandExecutionTimeout 缺省 30
        # 不应被当作用户设置的超时上限）。与 _user_settings 同生命周期。
        self._raw_user_config: dict[str, dict[str, Any]] = {}
        # 合并结果缓存：key=(user_id, workspace_id)
        self._merged_cache: dict[tuple[str, str], dict[str, Any]] = {}

    # ==================== 上下文（per-coroutine，contextvar）====================

    @staticmethod
    def _ctx_uid() -> str:
        return _CTX_USER_ID.get()

    @staticmethod
    def _ctx_wid() -> str:
        return _CTX_WORKSPACE_ID.get()

    def set_context(self, user_id: str | None, workspace_path: str | Path | None) -> None:
        """确立运行时安全上下文（user_id + workspace）——写入 contextvar（per-coroutine）。

        在 Agent/ToolExecutor 进入执行时调用。contextvar 只影响当前协程链，并发其它
        工作区的执行互不干扰。同时惰性加载该 user 的用户级配置与该 workspace 的覆盖
        （首次加载后命中缓存，后续仅 dict 查找）。
        """
        if user_id:
            _CTX_USER_ID.set(user_id)
        if workspace_path is not None:
            _CTX_WORKSPACE_ID.set(str(workspace_path))
        uid = _CTX_USER_ID.get()
        wid = _CTX_WORKSPACE_ID.get()
        # lock-free 快路径：已加载则直接返回，避免每次工具调用都抢锁
        if uid in self._user_settings and (not wid or (uid, wid) in self._workspace_security):
            return
        with self._lock:
            if uid not in self._user_settings:
                self._user_settings[uid] = self._load_user_settings(uid)
            if wid and (uid, wid) not in self._workspace_security:
                self._workspace_security[(uid, wid)] = self._load_workspace_security(wid)
        logger.debug(f"SecurityManager context: user={uid}, ws={wid}")

    # ==================== 公共接口 ====================

    def load(self, user_id: str | None = None) -> None:
        """加载用户级安全配置（应用启动时调用一次；多租户按 user_id 分键 + 分路径）。"""
        with self._lock:
            uid = user_id or _CTX_USER_ID.get()
            self._user_settings[uid] = self._load_user_settings(uid)
            self._merged_cache.clear()
            logger.info(
                f"SecurityManager loaded for user={uid}: "
                f"enable_command_whitelist={self._user_settings[uid].enable_command_whitelist}, "
                f"enable_sandbox={self._user_settings[uid].enable_sandbox}",
            )

    def set_workspace(self, workspace_path: str | Path, user_id: str | None = None) -> None:
        """切换工作区时调用（向后兼容封装 → set_context）。"""
        self.set_context(user_id, workspace_path)

    def update_workspace_security(
        self,
        settings: dict[str, Any],
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> None:
        """工作区安全配置变更后调用，更新对应 (user_id, workspace_id) 的内存缓存。"""
        with self._lock:
            uid = user_id or _CTX_USER_ID.get()
            wid = workspace_id or _CTX_WORKSPACE_ID.get() or ""
            self._workspace_security[(uid, wid)] = settings
            self._merged_cache.pop((uid, wid), None)
            logger.info(
                f"SecurityManager: workspace security updated (user={uid}, ws={wid}), "
                f"enableCommandWhitelist={settings.get('enableCommandWhitelist')}"
            )

    def get_settings(
        self, user_id: str | None = None, workspace_id: str | None = None
    ) -> dict[str, Any]:
        """获取合并后的安全配置（所有执行层从这里读取）。"""
        if is_super_mode_enabled():
            log_security_bypass("get_settings")
            return self._super_mode_settings()

        with self._lock:
            uid = user_id or _CTX_USER_ID.get()
            wid = workspace_id or _CTX_WORKSPACE_ID.get() or ""
            key = (uid, wid)
            cached = self._merged_cache.get(key)
            if cached is None:
                # 确保数据已加载
                if uid not in self._user_settings:
                    self._user_settings[uid] = self._load_user_settings(uid)
                if key not in self._workspace_security:
                    self._workspace_security[key] = (
                        self._load_workspace_security(wid) if wid else {}
                    )
                cached = self._merge(uid, wid)
                self._merged_cache[key] = cached
            return cached

    def get_policy(
        self, user_id: str | None = None, workspace_id: str | None = None
    ) -> EffectiveSecurityPolicy:
        """获取合并后的【强类型】安全策略（推荐执行层使用）。"""
        return EffectiveSecurityPolicy.from_merged_dict(self.get_settings(user_id, workspace_id))

    def get_user_settings(self, user_id: str | None = None) -> UserSecuritySettings:
        """获取用户级安全配置（API 层读写用）。"""
        with self._lock:
            uid = user_id or _CTX_USER_ID.get()
            if uid not in self._user_settings:
                self._user_settings[uid] = self._load_user_settings(uid)
            return self._user_settings[uid]

    def get_user_command_timeout_cap(self, user_id: str | None = None) -> int:
        """用户【显式】配置的单命令超时上限（秒）；0 = 未配置（不限制）。

        只认 security.json 里真实写过的 commandExecutionTimeout —— 模型缺省
        (30) 不算，避免无配置用户被误扣到 30s。沙箱 provider 用它对工具层
        传入的 timeout 取 min（2026-09-22 接活前端「执行超时」字段）。
        """
        uid = user_id or _CTX_USER_ID.get()
        with self._lock:
            # raw 缓存缺失（首次读取 / API 更新后失效）→ 从磁盘重载
            if uid not in self._raw_user_config:
                self._user_settings[uid] = self._load_user_settings(uid)
            raw = self._raw_user_config.get(uid, {})
        try:
            value = int(raw.get("commandExecutionTimeout", 0) or 0)
            return value if value > 0 else 0
        except (TypeError, ValueError):
            return 0

    def update_user_settings(
        self, settings: UserSecuritySettings, user_id: str | None = None
    ) -> None:
        """更新用户级安全配置（API 层写入后调用）。"""
        with self._lock:
            uid = user_id or _CTX_USER_ID.get()
            self._user_settings[uid] = settings
            # raw 缓存失效：API 更新后由下次读取从磁盘重载（显式值语义）
            self._raw_user_config.pop(uid, None)
            # 清该 user 所有 workspace 的合并缓存
            for key in list(self._merged_cache.keys()):
                if key[0] == uid:
                    self._merged_cache.pop(key, None)
            logger.info(f"SecurityManager: user settings updated (user={uid})")

    def reload(self) -> None:
        """重新加载配置"""
        self.load()

    # ==================== 内部方法 ====================

    def _load_user_settings(self, user_id: str) -> UserSecuritySettings:
        """从 configs/{user_id}/security.json 加载用户配置（不迁移旧数据）。"""
        config_file = self._get_config_file(user_id)
        self._raw_user_config[user_id] = {}

        if not config_file.exists():
            logger.debug(f"User security config not found: {config_file}, using defaults")
            return UserSecuritySettings()

        try:
            with config_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self._raw_user_config[user_id] = data if isinstance(data, dict) else {}
            settings = UserSecuritySettings.from_dict(data)
            logger.info(f"User security config loaded from {config_file}")
            return settings
        except Exception as e:
            logger.error(f"Failed to load user security config: {e}, using defaults")
            return UserSecuritySettings()

    @staticmethod
    def _get_config_file(user_id: str) -> Path:
        """用户级配置文件路径：configs/{user_id}/security.json（不兼容旧 configs/security.json）。"""
        safe_uid = "".join(c if c.isalnum() or c in "-_" else "_" for c in (user_id or "default_user"))
        return get_dawei_home() / "configs" / safe_uid / "security.json"

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

    def _merge(self, uid: str, wid: str) -> dict[str, Any]:
        """合并用户级默认与工作区级覆盖（override-or-inherit）。

        工作区可自由覆盖任一字段、任一方向（含放宽）；用户级仅提供默认值。
        """
        user = self._user_settings.get(uid) or UserSecuritySettings()
        ws = self._workspace_security.get((uid, wid), {})

        # === 命令执行安全（override-or-inherit）===
        command = {
            "enable_command_whitelist": merge_override(
                user.enable_command_whitelist, ws.get("enableCommandWhitelist")
            ),
            "allowed_sources": merge_override_list(
                user.allowed_sources, ws.get("allowedSources")
            ),
            "custom_allowed_commands": merge_override_list(
                user.custom_allowed_commands, ws.get("customAllowedCommands")
            ),
            "custom_denied_commands": merge_override_list(
                user.custom_denied_commands, ws.get("customDeniedCommands")
            ),
            "allow_shell_commands": merge_override(
                user.allow_shell_commands, ws.get("allowShellCommands")
            ),
            "allow_background_commands": merge_override(
                user.allow_background_commands, ws.get("allowBackgroundCommands")
            ),
            "allow_pipe_commands": merge_override(
                user.allow_pipe_commands, ws.get("allowPipeCommands")
            ),
            "command_execution_timeout": merge_override(
                user.command_execution_timeout, ws.get("commandExecutionTimeout")
            ),
        }

        # === 容器沙箱配置（override-or-inherit）===
        sandbox = {
            "enable_sandbox": merge_override(user.enable_sandbox, ws.get("enableSandbox")),
            "container_runtime": merge_override(
                user.container_runtime, ws.get("containerRuntime")
            ),
            "drop_all_capabilities": merge_override(
                user.drop_all_capabilities, ws.get("dropAllCapabilities")
            ),
            "no_new_privileges": merge_override(
                user.no_new_privileges, ws.get("noNewPrivileges")
            ),
            "sandbox_disable_network": merge_override(
                user.sandbox_disable_network, ws.get("sandboxDisableNetwork")
            ),
        }

        # === 工具权限与风险分级（override-or-inherit）===
        tools = {
            "allowed_tools": merge_override_list(
                user.base_allowed_tools, ws.get("customAllowedTools")
            ),
            "denied_tools": merge_override_list(
                user.base_denied_tools, ws.get("customDeniedTools")
            ),
            "require_approval_risk": merge_override(
                user.require_approval_risk, ws.get("requireApprovalRisk")
            ),
        }

        # === 审批工作流（override-or-inherit）===
        approval = {
            "approval_enabled": merge_override(
                user.approval_enabled, ws.get("approvalEnabled")
            ),
            "approval_required_for_risk": merge_override(
                user.approval_required_for_risk, ws.get("approvalRequiredForRisk")
            ),
            "approval_always_require": merge_override_list(
                user.approval_always_require, ws.get("approvalAlwaysRequire")
            ),
            "approval_timeout_seconds": merge_override(
                user.approval_timeout_seconds, ws.get("approvalTimeoutSeconds")
            ),
            "approval_no_channel_behavior": merge_override(
                user.approval_no_channel_behavior, ws.get("approvalNoChannelBehavior")
            ),
        }

        # === MCP 服务策略（override-or-inherit）===
        mcp = {
            "allowed_mcp_servers": merge_override_list(
                user.base_allowed_mcp_servers, ws.get("customAllowedMcpServers")
            ),
            "denied_mcp_servers": merge_override_list(
                user.base_denied_mcp_servers, ws.get("customDeniedMcpServers")
            ),
        }

        # === 自主执行策略（override-or-inherit）===
        autonomy = {
            "allow_scheduled_tasks": merge_override(
                user.allow_scheduled_tasks, ws.get("allowScheduledTasks")
            ),
            "allow_cron": merge_override(user.allow_cron, ws.get("allowCron")),
            "max_subtask_depth": merge_override(
                user.max_subtask_depth, ws.get("maxSubtaskDepth")
            ),
        }

        # === 速率限制（override-or-inherit）===
        rate_limit = {
            "tool_calls_per_minute": merge_override(
                user.tool_calls_per_minute, ws.get("toolCallsPerMinute")
            ),
        }

        # === 文件系统（override-or-inherit）===
        filesystem = {
            "blocked_paths": merge_override_list(
                user.base_blocked_paths, ws.get("customBlockedPaths")
            ),
        }

        # === 网络（override-or-inherit）===
        network = {
            "allowed_hosts": merge_override_list(
                user.base_allowed_hosts, ws.get("customAllowedHosts")
            ),
            "blocked_hosts": merge_override_list(
                user.base_blocked_hosts, ws.get("customBlockedHosts")
            ),
        }

        # === LLM（override-or-inherit）===
        llm = {
            "allowed_models": merge_override_list(
                user.base_allowed_models, ws.get("customAllowedModels")
            ),
            "blocked_models": merge_override_list(
                user.base_blocked_models, ws.get("customBlockedModels")
            ),
            "daily_cost_cap": merge_override(
                user.daily_cost_cap, ws.get("dailyCostCap")
            ),
        }

        # === 内容（override-or-inherit）===
        content = {
            "blocked_patterns": merge_override_list(
                user.base_blocked_patterns, ws.get("customBlockedPatterns")
            ),
            "prompt_injection_defense": merge_override(
                user.prompt_injection_defense, ws.get("promptInjectionDefense")
            ),
        }

        return {
            **command,
            **sandbox,
            **tools,
            **approval,
            **mcp,
            **autonomy,
            **rate_limit,
            **filesystem,
            **network,
            **llm,
            **content,
        }

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
