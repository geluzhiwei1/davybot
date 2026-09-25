# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工具系统健康体检（单一实现源）

被两处复用:
- scripts/audit_tool_system.py   开发期 CLI 诊断
- tests/test_tool_system_health.py  CI 常驻门禁（FAST FAIL）

检查项:
  1. 注册工具重名
  2. 空 schema 且工具确有具名参数（无参工具空 schema 是合法设计, 不误报）
  3. 描述缺失
  4. 工具名合法性（LLM function-calling 标识符约束）
  5. JSON Schema 可序列化 + required ⊆ properties
  6. 多层注册表一致性（tool_catalog / tool_executor SNAPSHOT_TOOLS /
     SANDBOX_ROUTABLE_TOOLS 引用了不存在的工具名）
  7. SandboxProvider 契约（execute_command/async 接受 timeout kwarg）

契约 A/B（schema 字段 ↔ _run 形参一致性）由 tool_contract.py 单独保障
（CustomBaseTool __init__/run 双点强制）, 不在此重复。
"""

from __future__ import annotations

import inspect
import json
import re
from collections import Counter
from typing import Any

_EMPTY_OBJECT_SCHEMA = {"type": "object", "properties": {}, "required": []}


def _accepts_named_args(inst: Any) -> bool:
    """工具实现是否接受具名参数（启发式: 检查 _run/_async_run 形参）

    无实例 / 无法内省时保守返回 True（宁可误报不可漏报）。
    """
    if inst is None:
        return True
    for meth_name in ("_run", "_async_run"):
        meth = getattr(inst, meth_name, None)
        if meth is None:
            continue
        try:
            params = [p for p in inspect.signature(meth).parameters.values() if p.name != "self" and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
        except (TypeError, ValueError):
            return True
        if params:
            return True
    return False


def audit() -> dict[str, Any]:
    """执行全量体检, 返回报告 dict。

    所有键值: 空容器 = 该项健康; 非空 = 问题清单。
    """
    report: dict[str, Any] = {}

    from dawei.tools.tool_provider import CustomToolProvider

    tools = CustomToolProvider().get_tools()
    names = [t["name"] for t in tools]
    report["total"] = len(tools)

    # 1. 重名
    report["duplicates"] = {n: c for n, c in Counter(names).items() if c > 1}

    # 2. 空 schema 且工具确有具名参数（真无参工具不报）
    report["empty_schema"] = [t["name"] for t in tools if not ((t.get("parameters") or {}).get("properties") or {}) and _accepts_named_args(t.get("callable"))]

    # 3. 描述缺失
    report["empty_description"] = [t["name"] for t in tools if not (t.get("description") or "").strip()]

    # 4. 名字合法性（LLM function-calling 标识符约束）
    report["invalid_names"] = [n for n in names if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,63}", n)]

    # 5. schema 问题: 必须是含 type:object 的 dict + JSON 可序列化 + required ⊆ properties
    # （严格校验的提供商 GLM/Deepseek 对缺失 type 的 parameters 直接 400）
    problems: list[str] = []
    for t in tools:
        params = t.get("parameters") or {}
        if not isinstance(params, dict) or params.get("type") != "object":
            problems.append(f"{t['name']}: parameters 不是含 type:object 的 JSON Schema")
            continue
        try:
            json.dumps(params)
        except (TypeError, ValueError) as e:
            problems.append(f"{t['name']}: not JSON-serializable: {e}")
        for req in params.get("required", []) or []:
            if req not in (params.get("properties") or {}):
                problems.append(f"{t['name']}: required '{req}' missing from properties")
    report["schema_problems"] = problems

    # 6. 注册表一致性（catalog / 静态注册表 引用悬空工具名）
    reg = set(names)
    dangling: dict[str, list[str]] = {}

    try:
        from dawei.tools import tool_catalog as tc

        catalog = getattr(tc, "TOOL_CATALOG", None)
        if catalog is None and hasattr(tc, "get_catalog"):
            # S2 拆库后：核心目录 + biz 注册条目合一（biz 缺席 = 仅核心目录）
            catalog = tc.get_catalog()
        if catalog is None:
            # 兜底: 扫描模块级 list
            catalog = next(
                (v for v in vars(tc).values() if isinstance(v, list) and v and hasattr(v[0], "name")),
                [],
            )
        catalog_names = {getattr(e, "name", None) for e in catalog} - {None}
        not_registered = sorted(catalog_names - reg)
        if not_registered:
            dangling["catalog_not_registered"] = not_registered
    except Exception as e:  # noqa: BLE001
        dangling["catalog_import_error"] = [str(e)[:100]]

    try:
        from dawei.tools import tool_executor as te

        for attr in ("SNAPSHOT_TOOLS", "SANDBOX_ROUTABLE_TOOLS"):
            refs = getattr(te, attr, None) or []
            unknown = sorted(set(refs) - reg)
            if refs and unknown:
                dangling[f"tool_executor.{attr}_unknown"] = unknown
    except Exception as e:  # noqa: BLE001
        dangling["tool_executor_import_error"] = [str(e)[:100]]

    report["registry_consistency"] = dangling

    # 7. SandboxProvider timeout 契约（facade 强制透传 timeout, provider 必须接受）
    provider_issues: list[str] = []
    try:
        from dawei.sandbox.docker_provider import DockerProvider
        from dawei.sandbox.subprocess_provider import SubprocessProvider

        providers = [SubprocessProvider, DockerProvider]

        # 云 provider 随 davybot-biz（S4 entry points）—— 缺席如实标注, 不算不健康
        try:
            from dawei.sandbox.saas_loader import load_saas_module

            providers.append(load_saas_module("agentenv").AgentENVProvider)
            providers.append(load_saas_module("cubesandbox").CubeSandboxProvider)
            providers.append(load_saas_module("cubesandbox").E2BProvider)
            providers.append(load_saas_module("saas_gateway").SaaSGateway)
        except ImportError as e:
            provider_issues.append(f"cloud providers skipped: {str(e)[:120]}")

        for cls in providers:
            for meth in ("execute_command", "execute_command_async"):
                sig = inspect.signature(getattr(cls, meth))
                if "timeout" not in sig.parameters:
                    provider_issues.append(f"{cls.__name__}.{meth} 不接受 timeout kwarg")
    except Exception as e:  # noqa: BLE001
        provider_issues.append(f"provider scan error: {e}")
    report["sandbox_provider_contract"] = provider_issues

    return report


def format_report(report: dict[str, Any]) -> str:
    """把 audit() 报告渲染为人类可读文本（CLI / 日志用）"""
    lines = [f"registered tools: {report['total']}"]
    for key, val in report.items():
        if key == "total":
            continue
        if not val:
            lines.append(f"✅ {key}: OK")
        else:
            lines.append(f"❌ {key}:")
            if isinstance(val, dict):
                for k, v in val.items():
                    lines.append(f"   - {k}: {v}")
            else:
                for item in val:
                    lines.append(f"   - {item}")
    return "\n".join(lines)


__all__ = ["audit", "format_report", "_accepts_named_args"]
