# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""沙箱 Provider 工厂 (§沙箱系统升级 v2 — Phase 1)

职责:
- 按环境变量 / 配置创建对应 Provider 实例
- 版本区分 (fail-fast, 不静默降级):
  - SaaS 版 (DAWEI_DEPLOYMENT_MODE=saas): 仅硬件隔离 (CubeSandbox/E2B/AgentENV/
    SaaSGateway); docker/subprocess 一律拒绝
  - PC App 版 (local, 默认): **仅 Docker/Podman** (2026-09-19 简化决策)。
    E2B/CubeSandbox/AgentENV/SaaSGateway 与 subprocess 均拒绝;
    Docker/Podman 不可用时显式报错, 不再兜底 subprocess。

环境变量:
  DAWEI_SANDBOX_PROVIDER   - auto | docker (local) | e2b | cubesandbox | agentenv | saas
  DAWEI_SANDBOX_API_URL    - E2B/CubeSandbox API 地址 (saas)
  DAWEI_SANDBOX_API_KEY    - E2B/CubeSandbox API Key (saas)
  DAWEI_SANDBOX_TEMPLATE   - CubeSandbox 模板 ID
  DAWEI_DEPLOYMENT_MODE    - local (PC App/单机, 默认) | saas (多租户服务)
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import Any

from dawei.sandbox.base import ProviderType, SandboxProvider

logger = logging.getLogger(__name__)


def _deployment_mode() -> str:
    """部署隔离等级: local (PC App/单机) | saas (多租户服务)

    委托 dawei.runtime (唯一合法 mode 读取点, 多模式统一方案 §6);
    DAWEI_RUNTIME_MODE 为上游, DAWEI_DEPLOYMENT_MODE 仅为兼容输入。
    """
    from dawei.runtime import deployment_class

    return deployment_class()


def _guard_mode_without_sandbox() -> None:
    """server/tui 模式无沙箱 (多模式统一方案 §3)。

    这两个模式不注册 sandbox capability (前端整块隐藏);
    引擎侧对任何 provider 创建显式报错, 不留"配了就能跑"的隐式后门。
    """
    from dawei.runtime import runtime_mode

    mode = runtime_mode()
    if mode not in ("saas", "desktop"):
        from dawei.core.exceptions import SandboxError

        raise SandboxError(
            f"当前模式 ({mode}) 未配置沙箱 — server/tui 无沙箱能力 "
            "(多模式统一方案 §3)。沙箱仅 saas/desktop 提供。"
        )


def _guard_saas_isolation(provider_type: ProviderType) -> None:
    """SaaS 版守卫: 多租户模式下禁止非硬件隔离 provider。

    nn-bot 双版本区分:
    - SaaS 版 (saas): CubeSandbox + RustFS, 多租户宿主上 docker (共享内核) /
      subprocess (无隔离) 执行不可信命令不可接受 —— fail-fast, 不静默降级
    - PC App 版 (local, 默认): 见 _guard_local_simplified
    """
    if _deployment_mode() != "saas":
        return
    if provider_type in (ProviderType.SUBPROCESS, ProviderType.DOCKER):
        from dawei.core.exceptions import SandboxSecurityError

        raise SandboxSecurityError(
            f"SaaS 模式 (DAWEI_DEPLOYMENT_MODE=saas) 禁止非硬件隔离 provider: "
            f"{provider_type.value} — 多租户宿主不得执行未隔离命令。"
            "请配置 CubeSandbox (DAWEI_SANDBOX_API_URL / E2B_API_URL), "
            "或仅在单机/桌面部署时使用 DAWEI_DEPLOYMENT_MODE=local",
        )


def _guard_local_simplified(provider_type: ProviderType) -> None:
    """PC App 版 (local) 守卫: 仅支持 Docker/Podman (2026-09-19 简化决策)。

    - 桌面版不再提供 E2B/CubeSandbox/AgentENV/SaaSGateway (云端硬件隔离, 归 SaaS)
    - 桌面版不再提供 subprocess (无隔离, 安全与可观测性不可接受)
    - Docker/Podman 不可用时显式报错引导安装, 不静默降级
    """
    if _deployment_mode() != "local":
        return
    if provider_type in (
        ProviderType.SUBPROCESS,
        ProviderType.E2B,
        ProviderType.CUBESANDBOX,
        ProviderType.AGENTENV,
        ProviderType.SAAS,
    ):
        from dawei.core.exceptions import SandboxSecurityError

        raise SandboxSecurityError(
            f"PC App 版 (DAWEI_DEPLOYMENT_MODE=local) 仅支持 Docker/Podman provider, "
            f"拒绝: {provider_type.value}。云端硬件隔离 (CubeSandbox/E2B/AgentENV) "
            "请使用 SaaS 版; subprocess 已移除。请设置 "
            "DAWEI_SANDBOX_PROVIDER=docker 并安装 Docker 或 Podman。",
        )


def _read_user_sandbox_settings() -> dict[str, Any]:
    """从用户安全配置读取沙箱相关字段。

    通过 SecurityManager 单例获取，自动处理文件加载和缓存。
    任何异常都静默降级（返回空 dict），不影响 Provider 创建。
    """
    try:
        from dawei.core.security_manager import security_manager

        settings = security_manager.get_user_settings()
        return {
            "sandbox_provider": settings.sandbox_provider,
            "workspace_mount_mode": settings.workspace_mount_mode,
            "virtiofs_enabled": settings.virtiofs_enabled,
        }
    except Exception as e:
        logger.debug("[PROVIDER_FACTORY] 读取用户沙箱配置失败, 降级到环境变量: %s", e)
        return {}


def create_provider(
    provider_type: ProviderType = ProviderType.AUTO,
    config: dict[str, Any] | None = None,
) -> SandboxProvider:
    """创建沙箱 Provider

    Args:
        provider_type: Provider 类型, AUTO 时按优先级链选择
        config: 可选配置字典 (传递给 Provider 构造函数)

    Returns:
        SandboxProvider 实例

    优先级 (当 provider_type == AUTO 时):
        1. 用户安全配置 (security.json 中的 sandboxProvider)
        2. 环境变量 DAWEI_SANDBOX_PROVIDER
        3. 自动检测: local → Docker/Podman (不可用即报错);
                       saas  → CubeSandbox/E2B (不可用即报错)
    """
    cfg = config or {}

    # 合并用户安全配置到 cfg（mount_mode, virtiofs 等）
    user_sb = _read_user_sandbox_settings()
    cfg.setdefault("workspace_mount_mode", user_sb.get("workspace_mount_mode", "ro"))
    cfg.setdefault("virtiofs_enabled", user_sb.get("virtiofs_enabled", False))

    # 仅在调用方未显式指定时，走优先级链
    if provider_type == ProviderType.AUTO:
        # 1. 用户安全配置
        user_provider = user_sb.get("sandbox_provider", "").strip().lower()
        if user_provider and user_provider != "auto":
            try:
                provider_type = ProviderType(user_provider)
                logger.info(
                    "[PROVIDER_FACTORY] 用户配置选择 Provider: %s", provider_type.value
                )
            except ValueError:
                logger.warning(
                    "[PROVIDER_FACTORY] 用户配置中未知 sandboxProvider=%s", user_provider
                )

        # 2. 环境变量
        if provider_type == ProviderType.AUTO:
            env_provider = os.environ.get("DAWEI_SANDBOX_PROVIDER", "").strip().lower()
            if env_provider and env_provider != "auto":
                try:
                    provider_type = ProviderType(env_provider)
                    logger.info(
                        "[PROVIDER_FACTORY] 环境变量选择 Provider: %s", provider_type.value
                    )
                except ValueError:
                    logger.warning(
                        "[PROVIDER_FACTORY] 未知 DAWEI_SANDBOX_PROVIDER=%s",
                        env_provider,
                    )

        # 3. 自动检测
        if provider_type == ProviderType.AUTO:
            provider_type = _auto_detect()
            logger.info("[PROVIDER_FACTORY] 自动检测选择 Provider: %s", provider_type.value)

    # 版本守卫 (fail-fast, 覆盖 auto 解析与显式误配两条路径):
    # - saas:  docker/subprocess 一律拒绝 (2026-09-13)
    # - local: 仅 Docker/Podman, e2b/subprocess 等一律拒绝 (2026-09-19)
    # - server/tui: 无沙箱 (多模式统一方案 §3), 显式报错而非隐式坏掉
    _guard_mode_without_sandbox()
    _guard_saas_isolation(provider_type)
    _guard_local_simplified(provider_type)

    if provider_type == ProviderType.SAAS:
        return _create_saas_gateway(cfg)
    if provider_type in (ProviderType.E2B, ProviderType.CUBESANDBOX):
        return _create_cubesandbox_provider(cfg)
    if provider_type == ProviderType.AGENTENV:
        return _create_agentenv_provider(cfg)
    if provider_type == ProviderType.DOCKER:
        return _create_docker_provider(cfg)

    from dawei.core.exceptions import SandboxError

    raise SandboxError(
        f"不支持的沙箱 provider: {provider_type.value} "
        "(local 允许: docker; saas 允许: e2b/cubesandbox/agentenv/saas)"
    )


def _auto_detect() -> ProviderType:
    """自动检测 Provider (按部署模式, 不降级)

    - saas:  CubeSandbox/E2B API 配置且可达 → E2B; 否则显式报错
    - local: Docker/Podman 可用 → DOCKER; 否则显式报错 (2026-09-19 起不再兜底 subprocess)
    """
    if _deployment_mode() == "saas":
        api_url = os.environ.get("DAWEI_SANDBOX_API_URL", "").strip()
        if api_url and _check_e2b_available(api_url):
            return ProviderType.E2B
        from dawei.core.exceptions import SandboxSecurityError

        raise SandboxSecurityError(
            "SaaS 模式自动检测失败: 未配置可达的 CubeSandbox/E2B "
            "(DAWEI_SANDBOX_API_URL) — 拒绝降级到 docker/subprocess, 请检查沙箱服务。",
        )

    if _check_docker_available():
        return ProviderType.DOCKER

    from dawei.core.exceptions import SandboxError

    raise SandboxError(
        "沙箱不可用: 未检测到 Docker/Podman 运行时。PC App 版仅支持 Docker/Podman "
        "(2026-09-19 简化决策, subprocess 已移除)。请安装 Docker "
        "(https://docs.docker.com/engine/install/) 或 Podman "
        "(https://podman.io/getting-started/installation) 后重试。",
    )


def _check_e2b_available(api_url: str) -> bool:
    """检测 E2B/CubeSandbox API 是否可达

    轻量探测: 尝试 TCP 连接到 API 地址, 3s 超时。
    """
    try:
        import socket
        from urllib.parse import urlparse

        parsed = urlparse(api_url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        if not host:
            return False

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((host, port))
        sock.close()

        if result == 0:
            logger.debug("[PROVIDER_FACTORY] E2B API 可达: %s:%s", host, port)
            return True
        logger.debug(
            "[PROVIDER_FACTORY] E2B API 不可达: %s:%s (errno=%s)",
            host,
            port,
            result,
        )
        return False
    except Exception as e:
        logger.debug("[PROVIDER_FACTORY] E2B 检测异常: %s", e)
        return False


def _check_docker_available() -> bool:
    """检测 Docker/Podman 运行时是否可用

    检测策略:
    1. docker CLI 是否存在
    2. docker daemon 是否响应 (docker info)
    3. 若 docker 不可用, 检测 podman
    """
    # 检测 Docker
    docker_path = shutil.which("docker")
    if docker_path:
        try:
            import subprocess

            result = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.debug(
                    "[PROVIDER_FACTORY] Docker 可用: %s",
                    result.stdout.strip(),
                )
                return True
        except Exception as e:
            logger.debug("[PROVIDER_FACTORY] Docker daemon 无响应: %s", e)

    # 检测 Podman (Docker API 兼容)
    podman_path = shutil.which("podman")
    if podman_path:
        try:
            import subprocess

            result = subprocess.run(
                ["podman", "info", "--format", "{{.Version.Version}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.debug(
                    "[PROVIDER_FACTORY] Podman 可用: %s",
                    result.stdout.strip(),
                )
                return True
        except Exception as e:
            logger.debug("[PROVIDER_FACTORY] Podman 无响应: %s", e)

    return False


# ================================================================
# Provider 创建函数 (延迟导入, 避免 optional 依赖)
# ================================================================


def _create_docker_provider(config: dict[str, Any]) -> SandboxProvider:
    """创建 DockerProvider (兼容 Podman, Docker API 兼容)"""
    from dawei.sandbox.docker_provider import DockerProvider

    return DockerProvider(config)


def _create_e2b_provider(config: dict[str, Any]) -> SandboxProvider:
    """创建 CubeSandboxProvider (旧名 E2BProvider)

    e2b SDK 未安装时显式报错 (fail-fast), 不再降级到 docker/subprocess。
    """
    try:
        from dawei.sandbox.cubesandbox_provider import CubeSandboxProvider

        return CubeSandboxProvider(config)
    except ImportError as e:
        from dawei.core.exceptions import SandboxError

        raise SandboxError(
            f"CubeSandbox/E2B SDK 不可用 ({e}) — 请安装沙箱依赖: "
            'uv pip install -e ".[sandbox]"。拒绝降级到 docker/subprocess。',
        )


def _create_cubesandbox_provider(config: dict[str, Any]) -> SandboxProvider:
    """创建 CubeSandboxProvider (新名, 推荐)"""
    return _create_e2b_provider(config)


def _create_agentenv_provider(config: dict[str, Any]) -> SandboxProvider:
    """创建 AgentENVProvider (与 E2B SDK 共享依赖, 缺失即报错)"""
    try:
        from dawei.sandbox.agentenv_provider import AgentENVProvider

        return AgentENVProvider(config)
    except ImportError as e:
        from dawei.core.exceptions import SandboxError

        raise SandboxError(
            f"AgentENV SDK 不可用 ({e}) — 请安装沙箱依赖: "
            'uv pip install -e ".[sandbox]"。拒绝降级到 docker/subprocess。',
        )


def _create_saas_gateway(config: dict[str, Any]) -> SandboxProvider:
    """创建 SaaSGateway — 按 workspace 路由到 CubeSandbox / AgentENV"""
    try:
        from dawei.sandbox.saas_gateway import SaaSGateway

        return SaaSGateway(config)
    except ImportError as e:
        from dawei.core.exceptions import SandboxError

        raise SandboxError(
            f"SaaSGateway 创建失败 ({e}) — 请安装沙箱依赖: "
            'uv pip install -e ".[sandbox]"。拒绝降级。',
        )
