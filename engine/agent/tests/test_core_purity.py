# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""G2 核心纯净守卫（拆库方案 §18.5，BLOCKING）。

仅核心冷启（subprocess 全新进程；dawei_biz 虽与本 venv 同装但零装载 ——
「仅装核心」的进程级等价）：

1. caps 精确 == [relay]（server 自包含形态，零云端 env）；
2. 工具 catalog 恰 = 核心集 —— 快照 = 拆分前全量(83) − 18.2 biz 清单(65)，
   双向恒等（缺失 = 搬迁漏项，多出 = 核心混入业务）；
3. 工具组恰 = 核心 10 组，knowledge 组仅 2 个用户知识库工具
   （legal_* 8 个经 biz register_tool_group 合并，缺席即不在）。
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit

# 拆分前全量 catalog(83) − dawei_biz/tools/_catalog.py BIZ_CATALOG(65) = 核心 18
CORE_CATALOG_SNAPSHOT = frozenset({
    "ask_followup_question",
    "attempt_completion",
    "docx_diff",
    "docx_edit",
    "docx_read_structured",
    "execute_command",
    "expand_tool_result",
    "insert_text_content",
    "list_files",
    "new_task",
    "query_user_knowledge_base",
    "read_file",
    "search_tools",
    "search_user_knowledge_base",
    "smart_text_edit",
    "switch_mode",
    "update_todo_list",
    "write_text_file",
})

CORE_GROUP_NAMES = frozenset({
    "read", "edit", "command", "mcp", "workflow",
    "knowledge", "docx", "skills", "browser", "task_graph",
})

CORE_KNOWLEDGE_TOOLS = frozenset({"search_user_knowledge_base", "query_user_knowledge_base"})

_BIZ_GROUPS = frozenset({"sanctions", "normflow", "market", "research", "social"})

_COLD_START_CODE = r"""
import json
import os
import sys

# 零云端 env 冷启（镜像 test_runtime._clear_mode_env + dotenv 注入二次清理）
for key in (
    "DAWEI_RUNTIME_MODE", "DAWEI_DEPLOYMENT_MODE", "WORKSPACE_STORE_BACKEND",
    "MARKET_API_URL", "DAWEI_SERVER_PASSWORD",
):
    os.environ.pop(key, None)
os.environ["DAWEI_RUNTIME_MODE"] = "server"

import dawei  # noqa: F401 —— 触发 dotenv 装载
for key in ("MARKET_API_URL", "WORKSPACE_STORE_BACKEND", "DAWEI_SERVER_PASSWORD", "DAWEI_DEPLOYMENT_MODE"):
    os.environ.pop(key, None)

from dawei.runtime import validate_environment
from dawei.tools.tool_catalog import get_catalog
from dawei.tools.tool_manager import get_all_tool_groups

groups = get_all_tool_groups()
print(json.dumps({
    "biz_loaded": any(m == "dawei_biz" or m.startswith("dawei_biz.") for m in sys.modules),
    "runtime_info": validate_environment(),
    "catalog": sorted(e.name for e in get_catalog()),
    "groups": {
        name: sorted(set(g.get("tools", [])) | set(g.get("custom_tools", [])))
        for name, g in groups.items()
    },
}))
"""


def _cold_start() -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", _COLD_START_CODE],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"core cold start failed:\n{proc.stderr[-2000:]}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_g2_cold_start_never_loads_biz():
    assert _cold_start()["biz_loaded"] is False


def test_g2_cold_start_caps_relay_only():
    info = _cold_start()["runtime_info"]
    assert info["mode"] == "server"
    assert info["deployment_class"] == "local"
    assert info["capabilities"] == ["relay"]


def test_g2_catalog_is_exactly_core_set():
    catalog = frozenset(_cold_start()["catalog"])
    missing = CORE_CATALOG_SNAPSHOT - catalog
    extra = catalog - CORE_CATALOG_SNAPSHOT
    assert not missing, f"核心 catalog 缺项（搬迁漏项）: {sorted(missing)}"
    assert not extra, f"核心 catalog 多项（业务混入核心）: {sorted(extra)}"


def test_g2_groups_core_only_knowledge_two():
    groups = _cold_start()["groups"]
    assert frozenset(groups) == CORE_GROUP_NAMES
    assert not (frozenset(groups) & _BIZ_GROUPS), "biz 组缺席时不得出现"
    assert frozenset(groups["knowledge"]) == CORE_KNOWLEDGE_TOOLS
