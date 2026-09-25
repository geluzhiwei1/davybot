# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""G1 隔离守卫（拆库方案 §18.5，BLOCKING）—— 镜像前端 F7b biz-isolation.test.ts。

dawei/ 核心树静态 import ``dawei_biz`` = 0。业务装载只允许经缝：

- S1 工具       entry point group ``dawei.tools``
- S2 工具组/目录 ``register_tool_group`` / ``register_catalog_entries``（biz→core 注册）
- S3 路由       entry point group ``dawei.routers``
- S4 沙箱       entry point group ``dawei.sandbox_providers``
- S5 钩子       ``dawei.core.ext_hooks`` 注册表

以上均经 importlib.metadata / 注册函数，无 ``dawei_biz`` 模块字面量 import ——
故本守卫扫静态 import 语句即可全覆盖；倒挂复发处置一律下沉接口，禁反向依赖。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import dawei

pytestmark = pytest.mark.unit

CORE_ROOT = Path(dawei.__file__).resolve().parent
TESTS_ROOT = Path(__file__).resolve().parent


def _iter_biz_imports(source: str) -> list[tuple[int, str]]:
    """提取源码中指向 dawei_biz 的静态 import（file 内行号, 语句描述）。"""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "dawei_biz" or alias.name.startswith("dawei_biz."):
                    hits.append((node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 0 and (module == "dawei_biz" or module.startswith("dawei_biz.")):
                hits.append((node.lineno, f"from {module} import ..."))
    return hits


def test_g1_core_tree_never_imports_dawei_biz():
    violations: list[str] = []
    for py in sorted(CORE_ROOT.rglob("*.py")):
        try:
            source = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            violations.append(f"{py}: unreadable ({e})")
            continue
        for lineno, stmt in _iter_biz_imports(source):
            violations.append(f"{py.relative_to(CORE_ROOT)}:{lineno}: {stmt}")

    assert not violations, (
        "核心→biz 倒挂（G1 违规；处置一律下沉接口/注册缝，禁反向依赖）:\n  "
        + "\n  ".join(violations)
    )


def test_g1_guard_detects_probe():
    """负路径（F7b 同法）：守卫必须能抓住倒挂 —— 防守卫自身失效。"""
    probe = (
        "from dawei_biz.saas.remote import start_ping_service\n"  # 6b-4 前的真实倒挂
        "import dawei_biz\n"
        "import dawei_biz.tools.market_tools as mt\n"
        "from dawei.core import ext_hooks\n"  # 合法 core import，不得误报
    )
    hits = _iter_biz_imports(probe)
    assert len(hits) == 3
    assert hits[0] == (1, "from dawei_biz.saas.remote import ...")


def test_g6_core_tests_no_biz_residue():
    """G6（§18.5）：biz 用例已随迁，核心套件不得残留 dawei_biz import。

    守卫测试自身对 dawei_biz 的「字符串」提及是检测样本（AST 中为字符串
    常量而非 import 语句），不在此列。
    """
    violations: list[str] = []
    for py in sorted(TESTS_ROOT.rglob("*.py")):
        source = py.read_text(encoding="utf-8")
        for lineno, stmt in _iter_biz_imports(source):
            violations.append(f"{py.relative_to(TESTS_ROOT)}:{lineno}: {stmt}")
    assert not violations, (
        "核心测试套件残留 biz import（用例应随迁 engine/biz/tests）:\n  " + "\n  ".join(violations)
    )
