# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工具系统健康常驻门禁（CI 守门, FAST FAIL）

复用 dawei/tools/tool_system_health.py 的 audit()（单一实现源）。
任何一项不过 = 工具系统存在影响 LLM 调用/注册表一致性的实际缺陷。

历史背景:
- 2026-09 smart_text_edit 因 schema 字段名 ≠ _run 形参名 100% 失败 4 个月无人知
  → 已由 tool_contract.py 双点强制 + test_tool_contract.py 保障
- 2026-09 legal_search 幽灵 catalog 条目诱导 LLM 调用不存在的工具
  → registry_consistency 检查保障
- 2026-09 空 object schema 使 GLM/Deepseek 400（parameters 缺 type）
  → schema_problems 检查保障
- 2026-09 6 个 sandbox provider 中 5 个不接受 timeout kwarg（facade 透传即 TypeError）
  → sandbox_provider_contract 检查保障
"""

from __future__ import annotations

import inspect

import pytest

from dawei.tools.tool_system_health import audit

# 体检所有检查项: 键名 → 人读说明
AUDIT_CHECKS = {
    "duplicates": "注册工具重名（LLM 调用歧义）",
    "empty_schema": "有具名参数的工具却无 schema（LLM 无法传参）",
    "empty_description": "描述缺失（LLM 无从选择工具）",
    "invalid_names": "工具名不合法（function-calling 标识符约束）",
    "schema_problems": "schema 非法（无 type:object / 不可序列化 / required ⊄ properties）",
    "registry_consistency": "注册表悬空引用（catalog/静态表指向不存在的工具）",
    "sandbox_provider_contract": "SandboxProvider 不接受 timeout kwarg（facade 透传即 TypeError）",
}


@pytest.fixture(scope="module")
def report() -> dict:
    """整个模块只跑一次全量体检（实例化 109 个工具, 开销秒级）"""
    return audit()


@pytest.mark.unit
class TestRegistryFloor:
    """注册量下限守卫

    tool_provider.py 对每个工具的实例化异常是"记日志+跳过"策略,
    若某个公共依赖损坏会导致注册表静默萎缩 — LLM 能力悄失。
    下限断言让这种静默失败变成显性失败。
    """

    def test_registry_size_sane(self, report: dict) -> None:
        # 形敏下限（拆库 §18）：双装 109 基线 ≥50；核心纯净形态（无 davybot-biz）
        # 实测 40 基线 ≥30 —— 下限防的是公共依赖损坏导致的批量静默萎缩,
        # 而非业务工具缺席（缺席 = 设计内合法形态, G2 另有 catalog==18 恒等守卫）。
        import importlib.util

        dual = importlib.util.find_spec("dawei_biz") is not None
        floor = 50 if dual else 30
        assert report["total"] >= floor, (
            f"注册工具仅 {report['total']} 个 (<{floor}, 形态={'双装' if dual else '核心纯净'}), "
            f"大概率发生了批量加载失败 — 检查 CustomToolProvider.get_tools() 的 WARNING/ERROR 日志"
        )


@pytest.mark.unit
class TestAuditChecks:
    """体检逐项门禁: 每项独立成 test, 失败时定位明确"""

    @pytest.mark.parametrize("key", list(AUDIT_CHECKS), ids=list(AUDIT_CHECKS))
    def test_check_clean(self, report: dict, key: str) -> None:
        assert not report[key], f"{AUDIT_CHECKS[key]}: {report[key]}"


def _cloud_provider_paths() -> list[str]:
    """云沙箱 provider 模块路径（S4 entry points 解析; biz 缺席 → 空列表）。

    6b-2 拆库后云 provider 随 davybot-biz 分发（dawei_biz.saas.*），
    核心开源形态（仅 docker/subprocess）不测缺席项 — 与 audit 检查 7 语义一致。
    """
    cloud_classes = {
        "e2b": "E2BProvider",
        "cubesandbox": "CubeSandboxProvider",
        "agentenv": "AgentENVProvider",
        "saas_gateway": "SaaSGateway",
    }
    paths: list[str] = []
    try:
        from dawei.sandbox.saas_loader import available_saas_providers, load_saas_module

        for name in available_saas_providers():
            class_name = cloud_classes.get(name)
            if class_name:
                paths.append(f"{load_saas_module(name).__name__}:{class_name}")
    except Exception:  # noqa: BLE001 — biz 缺席 = 仅核心 provider
        pass
    return paths


@pytest.mark.unit
class TestSandboxProviderContract:
    """显式 provider 契约测试（audit 检查 7 的细粒度版, 失败信息精确到类.方法）

    SandboxFacade.execute_command(command, ctx, timeout=timeout) 强制透传,
    任何 provider 不接受 timeout kwarg → 运行时 TypeError。
    2026-09-14 的修复只改了 6 个 provider 中的 1 个, 此测试防回归。
    """

    PROVIDERS = [
        "dawei.sandbox.subprocess_provider:SubprocessProvider",
        "dawei.sandbox.docker_provider:DockerProvider",
    ]

    @pytest.mark.parametrize("provider_path", PROVIDERS + _cloud_provider_paths())
    @pytest.mark.parametrize("method", ["execute_command", "execute_command_async"])
    def test_accepts_timeout_kwarg(self, provider_path: str, method: str) -> None:
        module_path, class_name = provider_path.rsplit(":", 1)
        import importlib

        cls = getattr(importlib.import_module(module_path), class_name)
        sig = inspect.signature(getattr(cls, method))
        param = sig.parameters.get("timeout")
        assert param is not None, f"{class_name}.{method} 不接受 timeout kwarg — SandboxFacade 透传 timeout 时将 TypeError"
        assert param.default is None or param.default is not inspect.Parameter.empty, f"{class_name}.{method}.timeout 必须有默认值（可选参数）"
