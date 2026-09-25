# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""E5 零云端默认守卫 —— 引擎源码不得硬编码 normnomos 云端地址。

拆库方案.md §5.2 E5: 云端地址只能来自 env / 显式入参;
代码路径(默认值/常量/字面量)零容忍。docstring 中的说明性提及允许(不进入运行时)。

§18.5-G4（6c）：扫描范围扩至 dawei_biz 双包 —— biz 缺席（开源仓无
engine/biz sibling）时该部分跳过（业务不在场 = 不存在）。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

AGENT_ROOT = Path(__file__).resolve().parents[2]
DAWEI_ROOT = AGENT_ROOT / "dawei"
# 拆库双项目布局：engine/agent + engine/biz（sibling）
BIZ_ROOT = AGENT_ROOT.parent / "biz" / "dawei_biz"


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """收集 Module/ClassDef/FunctionDef 首语句 docstring 的行号。"""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                lines.add(body[0].value.lineno)
    return lines


def _find_cloud_defaults(root: Path, rel_base: Path) -> list[str]:
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        if "normnomos.com" not in src:
            continue
        tree = ast.parse(src)
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "normnomos.com" in node.value
                and node.lineno not in docstrings
            ):
                offenders.append(f"{path.relative_to(rel_base)}:{node.lineno}")
    return offenders


@pytest.mark.unit
def test_no_cloud_defaults_in_engine_code():
    offenders = _find_cloud_defaults(DAWEI_ROOT, AGENT_ROOT)
    assert not offenders, (
        "引擎代码路径硬编码 normnomos 云端地址(仅 docstring 允许提及;地址须经 env 注入):\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.unit
def test_g4_no_cloud_defaults_in_biz_code():
    """G4（§18.5）：同一零容忍标准扩至 dawei_biz 包；缺席即跳过。"""
    if not BIZ_ROOT.is_dir():
        pytest.skip("engine/biz sibling absent — G4 biz scan n/a (业务不在场 = 不存在)")
    offenders = _find_cloud_defaults(BIZ_ROOT, BIZ_ROOT.parent)
    assert not offenders, (
        "biz 代码路径硬编码 normnomos 云端地址(仅 docstring 允许提及;地址须经 env 注入):\n  "
        + "\n  ".join(offenders)
    )
