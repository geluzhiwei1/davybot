# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""G3 全量恒等守卫（拆库方案 §18.5）—— 双装（dawei + dawei_biz）后，
工具 catalog 与路由集合与「拆分前」快照 diff = ∅。

快照出处（provenance）:
    拆分前 HEAD（473a443）git worktree 冷启动 create_app() 实测清单，
    采集环境与 _DUMP_CODE 一致（server 模式、mode env 清零）。
    快照: tests/snapshots/g3_pre_split_catalog.json (83)
          tests/snapshots/g3_pre_split_routes.json  (530, 见下)

归一化:
    - 仅比对 API 面（/api/*、/admin/*）。静态前端挂载（/app-ui*、
      /legalbot-ui*）由 _mount_frontend_static 按构建产物存在与否条件注册，
      API-only 为合法形态，故剔除并白名单校验。
    - 路由按多重集（sorted list）比对：拆分前后均存在遗留重复注册
      ``GET /api/ip/portfolio/stats`` ×2，保留之 —— 多重集比对可同时
      捕捉成员与注册次数漂移。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshots"

# 前端静态挂载（server_app._mount_frontend_static）：dist 存在才注册，
# 出现与否均为合法；出现则必须恰为此白名单内。
STATIC_MOUNT_ALLOWLIST = frozenset({
    "GET /app-ui",
    "GET /app-ui/{path:path}",
    "GET /legalbot-ui",
    "GET /legalbot-ui/assets/{path:path}",
    "GET /legalbot-ui/{path:path}",
})

# 子进程双装清单采集：与快照 provenance 同路径（mode env 清零 + server 模式）。
_DUMP_CODE = """
import json, os, sys

for k in ("DAWEI_RUNTIME_MODE","DAWEI_DEPLOYMENT_MODE","WORKSPACE_STORE_BACKEND",
          "MARKET_API_URL","DAWEI_SERVER_PASSWORD"):
    os.environ.pop(k, None)
os.environ["DAWEI_RUNTIME_MODE"] = "server"

import dawei_biz  # noqa: F401  双装形态：S2 组/目录 + S5 钩子（S3 路由由 entry points 装载）
from fastapi.routing import APIRoute
from dawei.server_app import create_app
from dawei.tools.tool_catalog import get_catalog

app = create_app()
routes = sorted(
    ("|".join(sorted(r.methods)) + " " + r.path)
    for r in app.routes if isinstance(r, APIRoute)
)
print(json.dumps({"catalog": sorted(e.name for e in get_catalog()), "routes": routes}))
"""


def _split_api_routes(routes: list[str]) -> tuple[list[str], list[str]]:
    """按前缀切分为 (api_routes, non_api_routes)。"""
    api, non_api = [], []
    for r in routes:
        (api if r.split(" ", 1)[1].startswith(("/api/", "/admin/")) else non_api).append(r)
    return sorted(api), sorted(non_api)


@pytest.fixture(scope="module")
def inventory() -> dict:
    """双装冷启动实测清单（子进程隔离，防 mode env 泄漏影响同进程其他用例）。"""
    proc = subprocess.run(
        [sys.executable, "-c", _DUMP_CODE],
        capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, f"双装清单采集失败:\n{proc.stderr[-2000:]}"
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    return json.loads(lines[-1])


def _load(name: str) -> list[str]:
    return json.loads((SNAPSHOT_DIR / name).read_text(encoding="utf-8"))


def test_g3_catalog_identity(inventory: dict):
    """catalog 83 项与拆分前逐一恒等（双向 diff = ∅）。"""
    current = sorted(inventory["catalog"])
    expected = _load("g3_pre_split_catalog.json")
    lost = sorted(set(expected) - set(current))
    gained = sorted(set(current) - set(expected))
    assert not lost and not gained, (
        f"G3 catalog 漂移: lost={lost} gained={gained} "
        "(拆分不得增删任何工具；新增走快照评审更新)"
    )


def test_g3_api_routes_identity(inventory: dict):
    """API 面（/api/*、/admin/*）路由与拆分前多重集恒等。"""
    api_routes, non_api = _split_api_routes(inventory["routes"])
    expected = _load("g3_pre_split_routes.json")
    lost = sorted(set(expected) - set(api_routes))
    gained = sorted(set(api_routes) - set(expected))
    assert not lost and not gained, (
        f"G3 路由漂移: lost={lost} gained={gained} "
        "(拆分不得增删任何路由；新增走快照评审更新)"
    )
    assert api_routes == expected, "路由多重集不等（注册次数漂移）"


def test_g3_non_api_routes_are_known_static_mounts(inventory: dict):
    """非 API 路由仅允许已知前端静态挂载（dist 缺失时可全体缺席）。"""
    _api_routes, non_api = _split_api_routes(inventory["routes"])
    unknown = sorted(set(non_api) - STATIC_MOUNT_ALLOWLIST)
    assert not unknown, f"未知非 API 路由: {unknown} (须登记或归一化)"
