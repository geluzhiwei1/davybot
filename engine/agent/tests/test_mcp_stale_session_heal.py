# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""陈旧 ClientSession 的 -32602 自愈回归（线上 task 42c05231 根因）。

背景：light-app 壳重启后，壳侧 stdio 子进程被 lazily 重 spawn 但从未收到
initialize；严格生命周期的 MCP SDK（Python 两代实现）把未初始化请求一律拒为
-32602 "Invalid request parameters"。引擎侧 ClientSession 停留在旧"已连接"
状态（auto_connect_all 跳过 connected），永不重发 initialize → 每次调用失败。

修复分两层（本文件验证引擎层，壳侧门禁见 light-app cargo 测试
auto_initialize_guard_answers_strict_lifecycle_server）：
  call_tool 捕获 lifecycle 风格错误后 disconnect+connect 一次（全新
  ClientSession 会重新 initialize 并刷新工具面）再重试一次。

结构对位 test_mcp_relay_e2e.py，但壳循环直调注册表（免 HTTP，KISS）：
registry.claim/resolve ↔ fake shell ↔ 严格生命周期真子进程（python3）。
"""

import asyncio
import json
import os
import sys

import pytest

pytestmark = pytest.mark.unit

pytest.importorskip("mcp")

from dawei.tools import mcp_tool_manager as mtm  # noqa: E402
from dawei.tools.mcp_relay import (  # noqa: E402
    RelayRegistry,
    RelayServerSpec,
    get_relay_registry,
    reset_relay_registry,
)
from dawei.tools.mcp_tool_manager import (  # noqa: E402
    _reset_manager_registry,
    get_or_create_mcp_manager,
)

UID = "stale-heal-user"
SRV = "stale-echo"
DEV = "stale-heal-desktop"

# 严格生命周期 echo server：initialize 前任何请求回 -32602（复现 Python MCP
# SDK 行为）；每次 initialize 向 $INIT_LOG 追加一行（断言重连确实重新握手）。
STRICT_CHILD = r"""
import json, os, sys
INIT_LOG = os.environ.get("INIT_LOG", "")
initialized = False
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    if "id" not in msg or "method" not in msg:
        continue
    m, rid = msg["method"], msg["id"]
    if m == "initialize":
        initialized = True
        if INIT_LOG:
            with open(INIT_LOG, "a") as f:
                f.write("init\n")
        result = {
            "protocolVersion": (msg.get("params") or {}).get("protocolVersion", "2025-11-25"),
            "capabilities": {},
            "serverInfo": {"name": "strict-echo", "version": "0"},
        }
    elif not initialized:
        print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {
            "code": -32602, "message": "Invalid request parameters"}}), flush=True)
        continue
    elif m == "tools/list":
        result = {"tools": [{"name": "echo", "description": "echo back",
                             "inputSchema": {"type": "object"}}]}
    elif m == "tools/call":
        text = (msg.get("params") or {}).get("arguments", {}).get("text", "")
        result = {"content": [{"type": "text", "text": "echo:" + text}], "isError": False}
    elif m == "resources/list":
        result = {"resources": []}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}), flush=True)
"""


async def _spawn_child(init_log: str):
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-u",
        "-c",
        STRICT_CHILD,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={**os.environ, "INIT_LOG": init_log},
    )


async def _child_request(proc, msg: dict) -> dict:
    proc.stdin.write((json.dumps(msg) + "\n").encode())
    await proc.stdin.drain()
    while True:
        line = await proc.stdout.readline()
        if not line:
            raise RuntimeError("strict child exited")
        resp = json.loads(line)
        if resp.get("id") == msg.get("id"):
            return resp


async def _fake_shell_loop(
    registry: RelayRegistry, user: str, device: str, state: dict, stop: asyncio.Event
) -> None:
    """内存壳循环：claim → 转发子进程（state["proc"] 每帧重读，支持热换）→ resolve。"""
    while not stop.is_set():
        frames = await registry.claim(user, device, wait=0.2, limit=8)
        for f in frames:
            msg = f.get("message") or {}
            if not msg.get("method"):
                continue
            proc = state["proc"]
            if msg.get("id") is None:  # 通知：只转发不回报
                proc.stdin.write((json.dumps(msg) + "\n").encode())
                await proc.stdin.drain()
                continue
            try:
                resp = await _child_request(proc, msg)
                registry.resolve(user, f["id"], message=resp)
            except Exception as e:  # 子进程故障 → error 回报（合成 -32000）
                registry.resolve(user, f["id"], error=str(e)[:200])


async def _scenario(init_log: str) -> dict:
    out: dict = {}
    registry = get_relay_registry()
    registry.register(UID, [RelayServerSpec(name=SRV, timeout=60)], device_id=DEV)

    state: dict = {"proc": await _spawn_child(init_log)}
    stop = asyncio.Event()
    shell = asyncio.create_task(_fake_shell_loop(registry, UID, DEV, state, stop))
    try:
        mgr = get_or_create_mcp_manager(workspace_root=None, user_id=UID)
        out["transport"] = mgr.get_config(SRV).transport

        # 1) 正常连接（initialize 落到子进程 1）
        out["connect"] = await mgr.connect_server(SRV)
        out["status"] = mgr.get_server_info(SRV).status
        r1 = await mgr.call_tool(SRV, "echo", {"text": "before"})
        out["r1"] = (r1["status"], r1["result"]["content"][0]["text"])
        out["init_lines_1"] = open(init_log).read().count("init")

        # 2) 模拟壳重启：杀子进程，换一个未初始化的新子进程（引擎会话不动）
        old = state["proc"]
        state["proc"] = None
        old.stdin.close()
        await old.wait()
        state["proc"] = await _spawn_child(init_log)

        # 3) 陈旧会话调用：新子进程未初始化 → 首次 -32602 → 重连重试一次
        r2 = await mgr.call_tool(SRV, "echo", {"text": "after"})
        out["r2"] = (r2["status"], r2["result"]["content"][0]["text"] if r2["status"] == "success" else r2.get("error"))
        out["init_lines_2"] = open(init_log).read().count("init")
        return out
    finally:
        stop.set()
        shell.cancel()
        await asyncio.gather(shell, return_exceptions=True)
        proc = state.get("proc")
        if proc is not None:
            proc.terminate()
            await proc.wait()


def test_stale_session_minus32602_heals_via_reconnect_retry(tmp_path, monkeypatch):
    """壳重启后陈旧会话的 tools/call 必须 -32602 一次后自愈成功。"""
    # 隔离：不吃真 ~/.normnomos 用户配置；注册表全部重置
    monkeypatch.setattr(mtm, "get_dawei_home", lambda: tmp_path)
    _reset_manager_registry()
    reset_relay_registry()
    try:
        out = asyncio.run(_scenario(str(tmp_path / "init.log")))
    finally:
        _reset_manager_registry()
        reset_relay_registry()

    assert out["transport"] == "local", "relay stub 应生效（壳在线）"
    assert out["connect"] is True
    assert out["status"] == "connected"
    assert out["r1"] == ("success", "echo:before"), f"重启前调用应成功: {out['r1']}"
    assert out["init_lines_1"] == 1, f"首个子进程恰好握手一次: {out['init_lines_1']}"
    # 核心回归：陈旧会话调用自愈（新子进程被重连后的 initialize 重新握手）
    assert out["r2"][0] == "success", f"壳重启后调用必须自愈: {out['r2']}"
    assert out["r2"][1] == "echo:after"
    assert out["init_lines_2"] == 2, f"重连必须重新 initialize 新子进程: {out['init_lines_2']}"
