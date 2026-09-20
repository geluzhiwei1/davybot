# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""沙箱核心抽象层 (§沙箱系统升级 v2 — Phase 1)

定义:
- TrustedContext: 不可变信任上下文 (F1 信任边界修复)
- SandboxProvider: Provider 抽象基类
- SandboxResult / SandboxCapabilities: 统一结果与能力声明
- IsolationLevel / ProviderType / PausePolicy: 枚举
- ResourceQuota / GlobalQuota: 配额定义
- 异常类: SandboxSecurityError 等 (复用 core.exceptions)
"""

from __future__ import annotations

import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, NewType

if TYPE_CHECKING:
    from dawei.websocket.session import SessionData

# ================================================================
# 类型别名 — 编译期防止误用
# ================================================================

UserId = NewType("UserId", str)
WorkspaceId = NewType("WorkspaceId", str)  # UUID 或哈希, 不暴露物理路径


# ================================================================
# 枚举
# ================================================================


class IsolationLevel(StrEnum):
    """沙箱隔离级别"""

    NONE = "none"
    PROCESS = "process"
    CONTAINER = "container"
    HARDWARE = "hardware"


class ProviderType(StrEnum):
    """沙箱 Provider 类型"""

    AUTO = "auto"
    SUBPROCESS = "subprocess"
    DOCKER = "docker"
    E2B = "e2b"                 # 旧名, 保留后向兼容 (alias for CUBESANDBOX)
    CUBESANDBOX = "cubesandbox" # 新名, 推荐
    AGENTENV = "agentenv"       # 新增 (kvcache-ai AgentENV)
    SAAS = "saas"               # 新增 (SaaS 网关, 按 workspace 路由)


class BackendType(StrEnum):
    """硬件级沙箱的具体实现 (区别于 ProviderType)"""

    CUBESANDBOX = "cubesandbox"
    AGENTENV = "agentenv"


class PausePolicy(StrEnum):
    """沙箱 pause 期间命令处理策略 (N2)"""

    AUTO_RESUME = "auto_resume"
    REJECT = "reject"
    QUEUE = "queue"


# ================================================================
# TrustedContext — F1 信任边界修复
# ================================================================


@dataclass(frozen=True, slots=True)
class TrustedContext:
    """沙箱执行上下文 — 仅由认证层构造, 不可变

    设计原则:
    - user_id / workspace_id 一旦创建不可修改 (frozen + slots)
    - 物理路径 (workspace_path) 不进入日志, 仅 workspace_id 出现
    - 由 from_authenticated_session 工厂方法构造, 禁止直接传字符串

    SaaS 字段 (Phase 1+):
    - tenant_id: 多租户隔离 (来自 JWT claim, 默认 "_default")
    - workspace_uuid: workspace 的真实 UUID (替代 sha256 路径哈希)
    - workspace_mount_mode: "ro" | "rw" (覆盖默认, 来自用户配置)
    """

    user_id: UserId
    workspace_id: WorkspaceId
    workspace_path: Path
    permissions: frozenset[str] = field(default_factory=frozenset)
    issued_at: float = field(default_factory=time.time)
    # === SaaS 字段 (可选, 旧 desktop 模式不填) ===
    tenant_id: str = ""
    workspace_uuid: str = ""
    workspace_mount_mode: str = "rw"

    def is_expired(self, ttl_seconds: int = 3600) -> bool:
        return (time.time() - self.issued_at) > ttl_seconds

    def has_permission(self, perm: str) -> bool:
        return perm in self.permissions

    @property
    def workspace_key(self) -> str:
        """workspace 在 WorkspaceStore 中的 key (不含前缀)"""
        return self.workspace_uuid or str(self.workspace_id)


class UntrustedContextError(PermissionError):
    """外部调用方试图直接构造 TrustedContext, 拒绝"""


def from_authenticated_session(session_data: SessionData) -> TrustedContext:
    """从已认证的 SessionData 构造 TrustedContext

    调用方必须是 WebSocket handler / HTTP auth middleware,
    且 session_data.user_id 必须经过 JWT/Session 验证。
    """
    if not getattr(session_data, "is_authenticated", False):
        raise UntrustedContextError("SessionData 未通过认证")

    user_id = getattr(session_data, "user_id", None)
    workspace_id = getattr(session_data, "workspace_id", None)

    if not user_id or not workspace_id:
        raise UntrustedContextError("SessionData 缺少 user_id / workspace_id")

    permissions = frozenset(getattr(session_data, "permissions", []) or [])

    return TrustedContext(
        user_id=UserId(user_id),
        workspace_id=WorkspaceId(str(workspace_id)),
        workspace_path=Path(str(workspace_id)),
        permissions=permissions,
        issued_at=time.time(),
    )


def from_user_workspace(
    user_id: str,
    workspace_path: str | Path,
    permissions: list[str] | None = None,
) -> TrustedContext:
    """从 user_id + workspace_path 构造 TrustedContext (本地桌面模式)

    本地模式下没有 JWT 认证, 直接信任调用方。
    此工厂仅用于 self-hosted / Tauri 桌面端。
    """
    resolved = Path(workspace_path).resolve()
    ws_id = hashlib.sha256(str(resolved).encode()).hexdigest()[:16]

    return TrustedContext(
        user_id=UserId(user_id),
        workspace_id=WorkspaceId(ws_id),
        workspace_path=resolved,
        permissions=frozenset(permissions or []),
        issued_at=time.time(),
    )


# ================================================================
# 配额定义
# ================================================================


@dataclass
class ResourceQuota:
    """每用户沙箱资源配额"""

    max_concurrent_sandboxes: int = 10
    max_total_memory_mb: int = 5120
    max_sandboxes_per_workspace: int = 1
    max_commands_per_minute: int = 120


@dataclass
class GlobalQuota:
    """全局沙箱资源配额"""

    max_total_sandboxes: int = 1000
    max_total_memory_mb: int = 102400


# ================================================================
# 能力声明
# ================================================================


@dataclass
class SandboxCapabilities:
    """沙箱能力声明"""

    isolation_level: IsolationLevel = IsolationLevel.NONE
    supports_network: bool = False
    supports_filesystem: bool = False
    supports_resource_limits: bool = False
    supports_pause: bool = False
    max_timeout: int = 30
    cold_start_ms: int = 0


# ================================================================
# 统一执行结果
# ================================================================


@dataclass
class SandboxResult:
    """统一执行结果"""

    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time: int = 0  # 毫秒
    workspace: str = ""
    provider: str = "unknown"
    isolation_level: IsolationLevel = IsolationLevel.NONE

    def to_dict(self) -> dict[str, Any]:
        """转换为字典 (兼容现有调用方)"""
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "execution_time": self.execution_time,
            "workspace": self.workspace,
            "provider": self.provider,
            "isolation_level": self.isolation_level.value,
        }


# ================================================================
# SandboxProvider 抽象基类
# ================================================================


class SandboxProvider(ABC):
    """沙箱 Provider 抽象基类

    所有 Provider 实现此接口:
    - SubprocessProvider: 本地直接执行 (白名单 + subprocess)
    - DockerProvider: 容器隔离 (Docker/Podman)
    - E2BProvider: 硬件隔离 (CubeSandbox / E2B Cloud)
    """

    @abstractmethod
    def execute_command(
        self,
        command: str,
        ctx: TrustedContext,
        timeout: int | None = None,
    ) -> SandboxResult:
        """同步执行命令

        timeout 为 SandboxFacade 强制透传的每命令超时（秒）——所有实现
        必须接受该参数（可仅作签名兼容），否则 facade 调用必抛
        TypeError（2026-09-17 修复：09-14 的 timeout 透传只更新了
        CubeSandbox，其余 provider 全部在野崩溃）。
        """
        ...

    @abstractmethod
    async def execute_command_async(
        self,
        command: str,
        ctx: TrustedContext,
        timeout: int | None = None,
    ) -> SandboxResult:
        """异步执行命令（timeout 契约同上）"""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """健康检查"""
        ...

    @abstractmethod
    def get_capabilities(self) -> SandboxCapabilities:
        """获取沙箱能力声明"""
        ...

    # === 可选覆盖: 会话生命周期钩子 ===

    def prewarm_session(self, ctx: TrustedContext) -> None:
        """预热沙箱会话 (P1: 在首次工具调用前预先创建)

        默认 no-op。仅存在 cold-start 成本的 Provider (如 E2B CubeSandbox)
        需要覆盖此方法。失败时应抛异常, 由 SandboxFacade / 调用方决定是否回退 lazy。

        设计原则:
        - 幂等: 同一 ctx 多次调用安全 (已存在则直接返回)
        - 同步: 预热完成或失败后返回, 不阻塞太久 (自身有内部超时)
        - 不执行用户命令: 只创建沙箱实例
        """

    def on_disconnect(self, ctx: TrustedContext) -> None:
        """WebSocket 断开时调用 — 默认无操作"""

    def on_reconnect(self, ctx: TrustedContext) -> None:
        """WebSocket 重连时调用 — 默认无操作"""

    def destroy_session(self, ctx: TrustedContext) -> None:
        """销毁指定会话的沙箱"""

    def destroy_all_sessions(self) -> None:
        """销毁所有会话 (服务关闭时调用)"""

    async def cleanup_idle(self) -> None:
        """清理空闲沙箱 (后台任务)"""
