# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工具契约校验（FAST FAIL 机制）

背景（2026-09-17 事故）：SmartFileEditTool 的 args_schema 声明字段
``chunk_size``，而 ``_run`` 形参误命名为 ``_chunk_size``。
``CustomBaseTool.run()`` 以 ``self._run(**validated_args.dict())`` 调用，
``.dict()`` 会注入全部 schema 字段（含默认值）→ 每次调用必然在参数绑定
阶段抛 ``TypeError: unexpected keyword argument`` → 被
``@safe_tool_operation`` 兜底吞掉 → 工具 100% 失效但表面"执行成功"。

本模块在**实例化期**（startup）与**首次执行期**（run 兜底）强制校验：

  契约 A（正向）：args_schema 的每个字段必须是 ``_run`` 可接受的关键字参数
                 （除非 ``_run`` 声明了 ``**kwargs``）。
  契约 B（反向）：``_run`` 的每个无默认值形参必须出现在 args_schema 中
                 （否则 run() 注定抛 missing argument）。

违反任意一条即抛 ``ToolContractError``，让坏工具在启动时暴露，
而不是在 LLM 调用时静默失败。
"""

import inspect
from typing import Any

from pydantic import BaseModel


class ToolContractError(RuntimeError):
    """工具违反 schema ↔ _run 签名契约。抛出即代表该工具 100% 无法经 run() 执行。"""


def get_contract_violations(tool: Any, tool_name: str | None = None) -> list[str]:
    """返回工具的契约违规列表（空列表 = 通过）。

    无 args_schema 或无 _run 的对象不校验（不是本契约的适用对象）。
    """
    name = tool_name or getattr(tool, "name", None) or type(tool).__name__

    args_schema = getattr(tool, "args_schema", None)
    run_method = getattr(tool, "_run", None)
    if args_schema is None or run_method is None:
        return []
    if not (inspect.isclass(args_schema) and issubclass(args_schema, BaseModel)):
        return []

    try:
        signature = inspect.signature(run_method)
    except (TypeError, ValueError):  # pragma: no cover - C 扩展等不可内省对象
        return []

    params = list(signature.parameters.values())
    # 去掉 self（绑定方法）；宽容处理静态函数等意外形态
    if params and params[0].name in ("self", "cls"):
        params = params[1:]

    has_var_keyword = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params)
    accepted_kwargs = {
        p.name
        for p in params
        if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    required_params = {
        p.name
        for p in params
        if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        and p.default is inspect.Parameter.empty
    }

    schema_fields = set(args_schema.model_fields.keys())
    violations: list[str] = []

    # 契约 A：schema 字段必须能作为 kwargs 传给 _run
    if not has_var_keyword:
        for field in sorted(schema_fields - accepted_kwargs):
            violations.append(
                f"[{name}] args_schema 字段 '{field}' 不是 _run() 的形参"
                f"（_run 形参: {sorted(accepted_kwargs)}）。"
                f"run() 以 _run(**schema.dict()) 调用，该字段注入必然抛 TypeError。"
            )

    # 契约 B：_run 必填形参必须在 schema 中（否则必抛 missing argument）
    for param in sorted(required_params - schema_fields):
        violations.append(
            f"[{name}] _run() 必填形参 '{param}' 不在 args_schema 字段中"
            f"（schema 字段: {sorted(schema_fields)}）。"
            f"run() 只按 schema 注入参数，该形参永远收不到值。"
        )

    return violations


def validate_tool_contract(tool: Any, tool_name: str | None = None) -> None:
    """校验工具契约，违规抛 ToolContractError（FAST FAIL）。"""
    violations = get_contract_violations(tool, tool_name)
    if violations:
        raise ToolContractError("工具契约违规: " + " | ".join(violations))
