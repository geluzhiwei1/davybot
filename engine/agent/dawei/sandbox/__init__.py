# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""沙箱模块 - v2 Provider 架构 + 向后兼容

v2 新增:
  - TrustedContext / SandboxProvider ABC / SandboxResult
  - SandboxFacade (统一入口)
  - SubprocessProvider / DockerProvider / E2BProvider
  - CommandClassifier (N3 ro/rw 路由)
  - PiiSafeLogger (N6 日志脱敏)
  - PathValidator (F3 workspace_path 白名单)
  - ResourceQuota / GlobalQuota + LRU 淘汰
  - PausePolicy / grace 期命令队列 (N1/N2)
  - eBPF 网络策略模板 (N4)

SaaS 扩展 (v4.1.0+):
  - CubeSandboxProvider (原 E2BProvider, virtiofs 直挂 + s3fs 路径)
  - AgentENVProvider (SDK 同步模式, kvcache-ai)
  - SaaSGateway (按 workspace 路由到具体 backend)
  - WorkspaceStore (RustFS/S3/MinIO 统一存储, 含 AES-GCM 客户端加密)
  - BackendSelector (workspace → backend 选择策略)
  - BackendType 枚举 (区别于 ProviderType)

v1 向后兼容:
  - CommandWhitelist (不变)
  - CommandExecutor → SubprocessProvider 别名
  - SandboxManager (不变, DockerProvider 内部委托)
"""

# === v2 核心抽象 (base.py) ===
from dawei.sandbox.base import (
    GlobalQuota,
    IsolationLevel,
    PausePolicy,
    ProviderType,
    ResourceQuota,
    SandboxCapabilities,
    SandboxProvider,
    SandboxResult,
    TrustedContext,
    UntrustedContextError,
    from_authenticated_session,
    from_user_workspace,
)

# === v2 工具模块 ===
from dawei.sandbox.command_classifier import CommandRisk, classify_command

# === v1 向后兼容 (保持不变) ===
from dawei.sandbox.command_whitelist import CommandWhitelist
from dawei.sandbox.path_validator import validate_workspace_path
from dawei.sandbox.pii_logger import PiiSafeLogger, get_pii_safe_logger

# === v2 Provider 工厂 (provider_factory.py) ===
from dawei.sandbox.provider_factory import create_provider

# === v2 统一入口 (sandbox_facade.py) ===
from dawei.sandbox.sandbox_facade import SandboxFacade

# === v2 Provider 实现 ===
# CommandExecutor: v1 → v2 别名 (subprocess_provider.CommandExecutor)
from dawei.sandbox.subprocess_provider import CommandExecutor, SubprocessProvider

# DockerProvider: 延迟导入, 避免 docker-py 未安装时 __init__ 失败
# 使用时: from dawei.sandbox.docker_provider import DockerProvider
# 或:     from dawei.sandbox import DockerProvider (会触发 docker import)

# E2BProvider: 延迟导入, 避免 e2b SDK 未安装时 __init__ 失败
# 使用时: from dawei.sandbox.e2b_provider import E2BProvider

__all__ = [
    # v2 核心
    "TrustedContext",
    "UntrustedContextError",
    "SandboxProvider",
    "SandboxResult",
    "SandboxCapabilities",
    "IsolationLevel",
    "ProviderType",
    "PausePolicy",
    "ResourceQuota",
    "GlobalQuota",
    "from_authenticated_session",
    "from_user_workspace",
    # v2 入口
    "SandboxFacade",
    "create_provider",
    # v2 Provider
    "SubprocessProvider",
    # v2 工具
    "CommandRisk",
    "classify_command",
    "validate_workspace_path",
    "PiiSafeLogger",
    "get_pii_safe_logger",
    # v1 向后兼容
    "CommandWhitelist",
    "CommandExecutor",
]

__version__ = "4.2.0"


# === v4.2 SaaS 扩展 (延迟导入, 仅按需加载) ===
# E2BProvider / CubeSandboxProvider: dawei.sandbox.cubesandbox_provider
# AgentENVProvider:                  dawei.sandbox.agentenv_provider
# SaaSGateway:                       dawei.sandbox.saas_gateway
# WorkspaceStore:                    dawei.sandbox.workspace_store
# BackendSelector:                   dawei.sandbox.backend_selector


def _lazy_saas_imports():
    """集中导出 SaaS 相关类 (懒加载, 避免破坏现有 import)

    用法:
        from dawei.sandbox import _lazy_saas_imports as saas
        provider = saas.CubeSandboxProvider(...)
    """
    from dawei.sandbox.agentenv_provider import AgentENVProvider, AgentENVSandboxSession
    from dawei.sandbox.backend_selector import BackendSelector, WorkspaceMeta
    from dawei.sandbox.base import BackendType
    from dawei.sandbox.cubesandbox_provider import (
        CubeSandboxProvider,
        E2BProvider,
    )
    from dawei.sandbox.saas_gateway import SaaSGateway, is_saas_gateway_enabled
    from dawei.sandbox.workspace_store import (
        FileMeta,
        SyncStats,
        WorkspaceStore,
        get_workspace_store,
        reset_workspace_store,
    )

    return {
        "CubeSandboxProvider": CubeSandboxProvider,
        "E2BProvider": E2BProvider,
        "AgentENVProvider": AgentENVProvider,
        "AgentENVSandboxSession": AgentENVSandboxSession,
        "SaaSGateway": SaaSGateway,
        "is_saas_gateway_enabled": is_saas_gateway_enabled,
        "BackendType": BackendType,
        "BackendSelector": BackendSelector,
        "WorkspaceMeta": WorkspaceMeta,
        "WorkspaceStore": WorkspaceStore,
        "FileMeta": FileMeta,
        "SyncStats": SyncStats,
        "get_workspace_store": get_workspace_store,
        "reset_workspace_store": reset_workspace_store,
    }
