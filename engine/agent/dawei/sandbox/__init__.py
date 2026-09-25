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

# E2BProvider: 随 davybot-biz（saas 桶）分发, 经 S4 loader 装载
# 使用时: from dawei.sandbox.saas_loader import load_saas_module
#         E2BProvider = load_saas_module("cubesandbox").E2BProvider

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
# 云 provider（随 davybot-biz，经 entry point group dawei.sandbox_providers 装载）:
# E2BProvider / CubeSandboxProvider: entry 'cubesandbox'
# AgentENVProvider:                  entry 'agentenv'
# SaaSGateway:                       entry 'saas_gateway'
# BackendSelector:                   entry 'backend_selector'
# 核心内置（本包内）:
# WorkspaceStore:                    dawei.sandbox.workspace_store


def _lazy_saas_imports():
    """集中导出 SaaS 相关类 (懒加载, 避免破坏现有 import)

    用法:
        from dawei.sandbox import _lazy_saas_imports as saas
        provider = saas.CubeSandboxProvider(...)

    云 provider 经 saas_loader（S4）解析 —— biz 缺席时 ImportError 指明原因。
    """
    from dawei.sandbox.base import BackendType
    from dawei.sandbox.saas_loader import load_saas_module
    from dawei.sandbox.workspace_store import (
        FileMeta,
        SyncStats,
        WorkspaceStore,
        get_workspace_store,
        reset_workspace_store,
    )

    _agentenv = load_saas_module("agentenv")
    _backend = load_saas_module("backend_selector")
    _cube = load_saas_module("cubesandbox")
    _gateway = load_saas_module("saas_gateway")

    return {
        "CubeSandboxProvider": _cube.CubeSandboxProvider,
        "E2BProvider": _cube.E2BProvider,
        "AgentENVProvider": _agentenv.AgentENVProvider,
        "AgentENVSandboxSession": _agentenv.AgentENVSandboxSession,
        "SaaSGateway": _gateway.SaaSGateway,
        "is_saas_gateway_enabled": _gateway.is_saas_gateway_enabled,
        "BackendType": BackendType,
        "BackendSelector": _backend.BackendSelector,
        "WorkspaceMeta": _backend.WorkspaceMeta,
        "WorkspaceStore": WorkspaceStore,
        "FileMeta": FileMeta,
        "SyncStats": SyncStats,
        "get_workspace_store": get_workspace_store,
        "reset_workspace_store": reset_workspace_store,
    }
