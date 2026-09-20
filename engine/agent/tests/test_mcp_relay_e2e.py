# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""MCP relay 真 HTTP E2E —— 引擎路由 ↔ 壳协议 ↔ 真 stdio 子进程全链(device 模型)。

与另两侧互补,三者拼起来覆盖「云端引擎 ↔ davy-light-app 壳 ↔ 本机子进程」:
  - test_mcp_relay.py   : 内存 fake shell(直调注册表),验证注册表/流语义;
  - cargo e2e.rs(壳仓) : 真 Rust run_loop + 真 stdio 子进程 + mock 云端;
  - 本文件              : 真 uvicorn(真 FastAPI users 路由 + 真 JWT 鉴权)
                          + Python 复刻壳循环(register/claim/result 携
                          device_id,行为对齐 relay.rs 线为:Bearer 头、
                          帧字段、通知不回报、device/logout 拦截自处理)
                          + 真 stdio 子进程(python3 echo MCP server)×2
                          —— 双设备注册/定向路由/远程登出全链。

约束:RelayRegistry 单 event loop(mcp_relay.py 类注释),因此 uvicorn 跑在
后台线程,ClientSession/壳循环经 run_coroutine_threadsafe 调度到 uvicorn 的
loop 上执行 —— 与生产(路由与工具管理器同 loop)同构。
"""

import asyncio
import json
import sys
import threading
import time
from typing import Self

import httpx
import pytest

pytestmark = pytest.mark.unit

pytest.importorskip("mcp")
pytest.importorskip("uvicorn")

from dawei.tools.mcp_relay import local_relay_client, reset_relay_registry  # noqa: E402

UID = "relay-e2e-user"
UID2 = "relay-e2e-user-b"
SRV = "e2e-echo-server"
DEV_A = "e2e-desktop-a"
DEV_B = "e2e-desktop-b"

# 真 stdio 子进程:行分隔 JSON-RPC echo MCP server(对位 light-app child.rs
# 测试用的 python3 fake-server;只应答请求帧,通知帧静默吞掉)。
ECHO_CHILD = r"""
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    if msg.get("method") is None or msg.get("id") is None:
        continue
    m, rid = msg["method"], msg["id"]
    if m == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {},
                  "serverInfo": {"name": "e2e-echo", "version": "0.1.0"}}
    elif m == "tools/list":
        result = {"tools": [{"name": "echo", "description": "echo back",
                             "inputSchema": {"type": "object"}}]}
    elif m == "tools/call":
        text = (msg.get("params") or {}).get("arguments", {}).get("text", "")
        result = {"content": [{"type": "text", "text": "echo:" + text}], "isError": False}
    else:
        result = {}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}) + "\n")
    sys.stdout.flush()
"""


def _mint_token(sub: str = UID) -> str:
    """用引擎同一 Settings 实例签发 JWT(与 get_authenticated_user_id 同源校验)。"""
    import jwt

    from dawei.config.settings import get_settings

    sec = get_settings().security
    now = int(time.time())
    return jwt.encode({"sub": sub, "iat": now, "exp": now + 3600}, sec.jwt_secret, algorithm=sec.jwt_algorithm)


class _RealServer:
    """真 uvicorn(127.0.0.1:0)挂真 users 路由;loop 经 startup 钩子捕获。"""

    def __init__(self):
        from fastapi import FastAPI

        from dawei.api.users import router as users_router

        self.app = FastAPI()
        self.app.include_router(users_router)
        self.loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()
        self.app.add_event_handler("startup", self._on_startup)

    def _on_startup(self) -> None:
        self.loop = asyncio.get_running_loop()
        self._ready.set()

    def __enter__(self) -> "Self":
        import uvicorn

        self.token = _mint_token(UID)
        self.token2 = _mint_token(UID2)
        self.server = uvicorn.Server(uvicorn.Config(self.app, host="127.0.0.1", port=0, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        assert self._ready.wait(15), "uvicorn 启动超时"
        for _ in range(50):  # sockets 就绪(startup 后立即可读)
            if getattr(self.server, "servers", None):
                break
            time.sleep(0.1)
        self.port = self.server.servers[0].sockets[0].getsockname()[1]
        self.base = f"http://127.0.0.1:{self.port}"
        return self

    def run(self, coro, timeout: float = 120.0):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def __exit__(self, *exc) -> None:
        self.server.should_exit = True
        self.thread.join(10)
        reset_relay_registry()


async def _child_request(proc, msg: dict) -> dict:
    """请求帧 → 子进程 stdin(行写)→ 等 stdout 匹配 id 的响应行。串行调用。"""
    proc.stdin.write((json.dumps(msg) + "\n").encode())
    await proc.stdin.drain()
    while True:
        line = await proc.stdout.readline()
        if not line:
            raise RuntimeError("echo child exited")
        resp = json.loads(line)
        if resp.get("id") == msg.get("id"):
            return resp


async def _shell_loop(hc: httpx.AsyncClient, proc, stop: asyncio.Event, device_id: str, state: dict) -> None:
    """复刻 relay.rs 壳循环(P1):claim 携 device_id → 请求帧转发子进程并回报,
    通知只转发;``device/logout`` 控制帧按 method 拦截自处理(记录后退出,
    真壳为清凭证 + 重新生成 device_id)。"""
    handled: set = state.setdefault(f"handled_{device_id[-1]}", set())
    while not stop.is_set():
        r = await hc.post("/api/users/me/mcp-relay/claim", json={"device_id": device_id, "wait": 25, "limit": 8})
        if r.status_code != 200:
            state.setdefault("claim_status", {})[device_id] = r.status_code
            return  # 下线/401/403:退出循环(真壳走退避重连或本地登出,此处直接退)
        for f in r.json().get("frames", []):
            msg = f.get("message") or {}
            if msg.get("method") == "device/logout":
                state["logout_frame"] = f  # 云→桌控制帧:不转发子进程
                return
            if msg.get("method") and msg.get("id") is not None:
                handled.add(f["id"])
                try:
                    resp = await _child_request(proc, msg)
                    await hc.post(
                        "/api/users/me/mcp-relay/result",
                        json={"device_id": device_id, "id": f["id"], "message": resp},
                    )
                except Exception as e:  # 子进程故障 → error 回报(合成 -32000)
                    await hc.post(
                        "/api/users/me/mcp-relay/result",
                        json={"device_id": device_id, "id": f["id"], "error": str(e)[:200]},
                    )
            elif msg.get("method"):
                proc.stdin.write((json.dumps(msg) + "\n").encode())  # 通知:不回报
                await proc.stdin.drain()


async def _wait_state(state: dict, key: str, timeout: float = 15.0):
    """轮询壳循环侧写(state[key] 就绪或超时断言)。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while key not in state:
        if loop.time() > deadline:
            raise AssertionError(f"timeout waiting for state[{key!r}]")
        await asyncio.sleep(0.05)


async def _spawn_child():
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        ECHO_CHILD,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )


async def _scenario(rs: _RealServer) -> dict:
    from mcp import ClientSession

    reset_relay_registry()
    proc_a = await _spawn_child()
    proc_b = await _spawn_child()
    stop = asyncio.Event()
    state: dict = {}
    out: dict = {}
    shell_a = shell_b = None
    try:
        async with httpx.AsyncClient(base_url=rs.base, timeout=40.0) as anon:
            # 鉴权负路径:无 Bearer → 401(真鉴权依赖在跑)
            out["anon_claim"] = (await anon.post("/api/users/me/mcp-relay/claim", json={"wait": 0.1, "limit": 1})).status_code
            out["anon_devices"] = (await anon.get("/api/users/me/devices")).status_code

        async with httpx.AsyncClient(base_url=rs.base, timeout=40.0, headers={"Authorization": f"Bearer {rs.token2}"}) as hc2, httpx.AsyncClient(base_url=rs.base, timeout=40.0, headers={"Authorization": f"Bearer {rs.token}"}) as hc:
            # 同账号双桌面各自注册(§8.2:P0 冲突 409 退役,多桌面合法)
            reg_a = await hc.post(
                "/api/users/me/mcp-relay/register",
                json={
                    "client": "light-app",
                    "device_id": DEV_A,
                    "label": "公司 MacBook · macOS",
                    "client_version": "0.9.2",
                    "servers": [{"name": SRV, "timeout": 60}],
                },
            )
            out["register_a"] = reg_a.status_code
            reg_b = await hc.post(
                "/api/users/me/mcp-relay/register",
                json={
                    "client": "light-app",
                    "device_id": DEV_B,
                    "label": "家里 PC · Windows",
                    "client_version": "0.9.1",
                    "servers": [{"name": SRV, "timeout": 60}],
                },
            )
            out["register_b"] = reg_b.status_code

            # 粘性绑定(§7.3):他账号注册同设备 → 409 device_bound
            bound = await hc2.post(
                "/api/users/me/mcp-relay/register",
                json={"client": "light-app", "device_id": DEV_A, "servers": [{"name": SRV, "timeout": 60}]},
            )
            out["register_bound_409"] = bound.status_code
            out["register_bound_detail"] = "device_bound" in bound.json().get("detail", "")

            # 聚合视图:并集 + per-device;设备管理面列表
            servers = (await hc.get("/api/users/me/mcp-relay/servers")).json()
            out["online"] = servers["online"]
            out["server_specs"] = [(s["name"], s["timeout"]) for s in servers["servers"]]
            out["devices_in_agg"] = sorted(d["device_id"] for d in servers["devices"])
            dev_list = (await hc.get("/api/users/me/devices")).json()
            out["devices_count"] = len(dev_list["devices"])
            out["label_a"] = {d["device_id"]: d["label"] for d in dev_list["devices"]}.get(DEV_A)
            out["version_b"] = {d["device_id"]: d["client_version"] for d in dev_list["devices"]}.get(DEV_B)

            # rename(§9.3)
            out["rename_status"] = (
                await hc.post(f"/api/users/me/devices/{DEV_B}/rename", json={"label": "家里 PC 改名"})
            ).status_code
            out["renamed_label"] = {
                d["device_id"]: d["label"] for d in (await hc.get("/api/users/me/devices")).json()["devices"]
            }.get(DEV_B)

            # 双壳上线(各自 device_id 长轮询)
            shell_a = asyncio.create_task(_shell_loop(hc, proc_a, stop, DEV_A, state))
            shell_b = asyncio.create_task(_shell_loop(hc, proc_b, stop, DEV_B, state))

            # /call 缺省:两台托管 → 广播(B 单壳即可领)
            call_bc = await hc.post(
                "/api/users/me/mcp-relay/call", json={"server": SRV, "tool": "echo", "arguments": {"text": "bc"}}
            )
            out["call_broadcast_status"] = call_bc.status_code
            out["call_broadcast_result"] = call_bc.json().get("result")

            # /call 定向 B(§8.3):帧只进 B 的定向队列
            call_b = await hc.post(
                "/api/users/me/mcp-relay/call",
                json={"server": SRV, "tool": "echo", "arguments": {"text": "to-b"}, "device_id": DEV_B},
            )
            out["call_directed_status"] = call_b.status_code
            out["call_directed_result"] = call_b.json().get("result")
            out["call_directed_by_b"] = call_b.json().get("frame_id") in state.get("handled_b", set())

            # 远程登出 B(§9.3):控制帧定向送达 → 后续 claim 403 → 同身份重注册 403
            out["kick_status"] = (await hc.delete(f"/api/users/me/devices/{DEV_B}")).status_code
            await _wait_state(state, "logout_frame")
            out["logout_frame_server"] = state["logout_frame"]["server"]
            out["logout_frame_device"] = state["logout_frame"]["message"]["params"].get("device_id")
            out["claim_after_kick"] = (
                await hc.post("/api/users/me/mcp-relay/claim", json={"device_id": DEV_B, "wait": 0.1, "limit": 4})
            ).status_code
            out["register_after_kick"] = (
                await hc.post(
                    "/api/users/me/mcp-relay/register",
                    json={"client": "light-app", "device_id": DEV_B, "servers": []},
                )
            ).status_code

            by_id = {d["device_id"]: d for d in (await hc.get("/api/users/me/devices")).json()["devices"]}
            out["b_revoked"] = by_id[DEV_B]["revoked"]
            out["b_online"] = by_id[DEV_B]["online"]
            out["a_online_after_kick"] = by_id[DEV_A]["online"]

            # 云端引擎侧:唯一在线托管(A)→ 定向;真 ClientSession 帧透传全链
            async with local_relay_client(SRV, UID, timeout=60) as (read, write), ClientSession(read, write) as session:
                init = await asyncio.wait_for(session.initialize(), timeout=20)
                tools = await asyncio.wait_for(session.list_tools(), timeout=20)
                call = await asyncio.wait_for(session.call_tool("echo", {"text": "hi-e2e"}), timeout=20)
                out["server_name"] = init.serverInfo.name
                out["tool_names"] = [t.name for t in tools.tools]
                out["call_text"] = call.content[0].text

            # /call 缺省:唯一托管 → 定向 A
            call_a = await hc.post(
                "/api/users/me/mcp-relay/call", json={"server": SRV, "tool": "echo", "arguments": {"text": "to-a"}}
            )
            out["call_unique_status"] = call_a.status_code
            out["call_unique_result"] = call_a.json().get("result")

            # A 下线:DELETE 携 device_id → 离线态(优雅登出路径)
            out["unregister_a"] = (await hc.delete(f"/api/users/me/mcp-relay?device_id={DEV_A}")).status_code
            gone = (await hc.get("/api/users/me/mcp-relay/servers")).json()
            out["online_after_unregister"] = gone["online"]
            out["call_offline_status"] = (
                await hc.post("/api/users/me/mcp-relay/call", json={"server": SRV, "tool": "echo"})
            ).status_code
            out["register_bad_name"] = (
                await hc.post(
                    "/api/users/me/mcp-relay/register",
                    json={"client": "light-app", "device_id": "e2e-desktop-c", "servers": [{"name": "bad name!"}]},
                )
            ).status_code
            return out
    finally:
        stop.set()
        for shell in (shell_a, shell_b):
            if shell is not None:
                shell.cancel()
                await asyncio.gather(shell, return_exceptions=True)
        for proc in (proc_a, proc_b):
            proc.terminate()
            await proc.wait()


def test_mcp_relay_real_http_e2e():
    """全链路:真 HTTP+真 JWT+真路由 ↔ 双设备壳协议循环 ↔ 真子进程;多桌面
    注册/定向路由/远程登出/粘性绑定/鉴权与下线路径行为正确。"""
    with _RealServer() as rs:
        out = rs.run(_scenario(rs))
    assert out["anon_claim"] == 401, "无 token 的 claim 必须 401"
    assert out["anon_devices"] == 401, "无 token 的设备列表必须 401"
    assert out["register_a"] == 200
    assert out["register_b"] == 200, "同账号多桌面各自注册合法(§8.2)"
    assert out["register_bound_409"] == 409, "他账号注册同设备必须 409(粘性绑定)"
    assert out["register_bound_detail"] is True, "409 detail 须含 device_bound"
    assert out["online"] is True
    assert out["server_specs"] == [(SRV, 60)]
    assert out["devices_in_agg"] == [DEV_A, DEV_B]
    assert out["devices_count"] == 2
    assert out["label_a"] == "公司 MacBook · macOS"
    assert out["version_b"] == "0.9.1"
    assert out["rename_status"] == 200
    assert out["renamed_label"] == "家里 PC 改名"
    assert out["call_broadcast_status"] == 200, "多台托管 → 广播,B 壳可领"
    assert out["call_broadcast_result"] == "echo:bc"
    assert out["call_directed_status"] == 200, "定向 /call 必须由 B 执行"
    assert out["call_directed_result"] == "echo:to-b"
    assert out["call_directed_by_b"] is True, "定向帧的执行者必须是 B"
    assert out["kick_status"] == 200
    assert out["logout_frame_server"] == "_control", "远程登出控制帧走 _control 伪 server"
    assert out["logout_frame_device"] == DEV_B, "控制帧 params 携 device_id(防跨设备误投)"
    assert out["claim_after_kick"] == 403, "被登出设备后续 claim 必须 403"
    assert out["register_after_kick"] == 403, "被登出设备同身份重注册必须 403(须换新 device_id)"
    assert out["b_revoked"] is True
    assert out["b_online"] is False
    assert out["a_online_after_kick"] is True, "登出 B 不得影响 A"
    assert out["server_name"] == "e2e-echo"
    assert out["tool_names"] == ["echo"]
    assert out["call_text"] == "echo:hi-e2e"
    assert out["call_unique_status"] == 200, "唯一托管时缺省 /call 定向 A"
    assert out["call_unique_result"] == "echo:to-a"
    assert out["unregister_a"] == 200
    assert out["online_after_unregister"] is False
    assert out["call_offline_status"] == 409, "离线后 /call 必须 409"
    assert out["register_bad_name"] == 400, "非法 server 名必须 400(NAME_RE)"
