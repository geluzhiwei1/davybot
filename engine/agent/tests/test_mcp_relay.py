# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""mcp_relay(device 模型,方案 §8.2/§9)单元测试。

覆盖:注册表 register/claim/result 往返、长轮询唤醒、通知帧无 future、
双设备清单互不覆盖 / 定向帧只达目标 / 广播帧恰好一台领取 / 按设备登出不
误杀他设备、粘性绑定(§7.3 他用户同设备 409 / 登出解绑)、远程登出
(§9.3 revoked + device/logout 控制帧可达 + 帧送完 403)、label 首注册
生效与 rename、devices 管理面(列表/rename/revoke/kick 限频)、
stub 配置并入 MCPToolManager、transport=local 离线 FAST FAIL 与
host_device 路由、fake-shell 全链路(local_relay_client + 真 ClientSession)、
/call 入口路由与 FAST FAIL、账户隔离硬约束。

不依赖网络/子进程;fake shell 直接调注册表 API 模拟壳的 claim→执行→result。
"""

import asyncio

import pytest

pytestmark = pytest.mark.unit

from dawei.tools.mcp_relay import (  # noqa: E402
    DEVICE_ID_RE,
    OFFLINE_AFTER,
    DeviceBoundError,
    DeviceRevokedError,
    RelayServerSpec,
    get_relay_registry,
    host_device,
    local_relay_client,
    reset_relay_registry,
)

UID = "relay-unit-user"
UID2 = "relay-unit-other"
SRV = "my-local-mcp"
DEV_A = "desktop-aaa"
DEV_B = "desktop-bbb"


@pytest.fixture(autouse=True)
def fresh_registry():
    reset_relay_registry()
    yield
    reset_relay_registry()


def _age_device(user_id: str, device_id: str, seconds: float) -> None:
    """拨回设备时钟模拟掉线(同 loop.time 基准)。"""
    reg = get_relay_registry()
    dev = reg._users[user_id].devices[device_id or "_legacy"]
    dev.last_seen -= seconds


# ── 注册表核心 ────────────────────────────────────────────────


async def test_register_claim_result_roundtrip():
    reg = get_relay_registry()
    names, changed = reg.register(UID, [RelayServerSpec(name=SRV, timeout=120)], device_id=DEV_A)
    assert names == [SRV]
    assert changed is True
    assert reg.is_online(UID)

    # 重注册同清单:changed=False
    _, changed2 = reg.register(UID, [RelayServerSpec(name=SRV, timeout=120)], device_id=DEV_A)
    assert changed2 is False

    # 仅 timeout 变化也须 changed=True(触发 areload,防 stub 超时陈旧)
    _, changed3 = reg.register(UID, [RelayServerSpec(name=SRV, timeout=300)], device_id=DEV_A)
    assert changed3 is True

    # 请求帧定向入队 → claim 领取 → result 回填 future
    _, fut = reg.enqueue(UID, SRV, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, device_id=DEV_A)
    assert fut is not None
    assert not fut.done()
    frames = await reg.claim(UID, DEV_A, wait=0.1, limit=4)
    assert len(frames) == 1
    assert frames[0]["server"] == SRV
    assert frames[0]["message"]["method"] == "tools/list"

    assert reg.resolve(UID, frames[0]["id"], message={"jsonrpc": "2.0", "id": 1, "result": {"tools": []}})
    assert fut.done()
    assert fut.result()["result"] == {"tools": []}

    # 重复 resolve → False
    assert not reg.resolve(UID, frames[0]["id"], message={"jsonrpc": "2.0", "id": 1, "result": {}})


async def test_claim_long_poll_wakes_on_enqueue():
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)

    claim_task = asyncio.create_task(reg.claim(UID, DEV_A, wait=5.0, limit=4))
    await asyncio.sleep(0.05)
    assert not claim_task.done(), "空队列应挂起等待"
    reg.enqueue(UID, SRV, {"jsonrpc": "2.0", "id": 7, "method": "ping"}, device_id=DEV_A)
    frames = await asyncio.wait_for(claim_task, timeout=2.0)
    assert len(frames) == 1
    assert frames[0]["message"]["id"] == 7


async def test_notification_frame_has_no_future():
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    fid, fut = reg.enqueue(UID, SRV, {"jsonrpc": "2.0", "method": "notifications/initialized"}, device_id=DEV_A)
    assert fut is None
    frames = await reg.claim(UID, DEV_A, wait=0.1, limit=4)
    assert [f["id"] for f in frames] == [fid]
    # 通知帧无 future 可 resolve
    assert not reg.resolve(UID, fid, message={"jsonrpc": "2.0", "result": {}})


async def test_unregister_fails_pending_with_rpc_error():
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    _, fut = reg.enqueue(UID, SRV, {"jsonrpc": "2.0", "id": 3, "method": "tools/call"}, device_id=DEV_A)
    await reg.claim(UID, DEV_A, wait=0.1, limit=4)

    assert reg.unregister(UID, DEV_A)
    assert not reg.is_online(UID)
    assert fut.done()
    assert fut.result()["error"]["code"] == -32000

    assert not reg.unregister(UID, DEV_A)  # 幂等


async def test_resolve_error_synthesizes_rpc_error():
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    _, fut = reg.enqueue(UID, SRV, {"jsonrpc": "2.0", "id": 9, "method": "tools/call"}, device_id=DEV_A)
    frames = await reg.claim(UID, DEV_A, wait=0.1, limit=4)
    assert reg.resolve(UID, frames[0]["id"], error="child exited")
    assert fut.result()["error"]["message"].endswith("child exited")


# ── 设备模型(§8.2)──────────────────────────────────────────


async def test_two_devices_lists_do_not_overwrite():
    """双桌面各自注册,清单互不覆盖;聚合面 = 并集(P0 覆盖缺陷修复)。"""
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name="srv-a")], device_id=DEV_A)
    reg.register(UID, [RelayServerSpec(name="srv-b")], device_id=DEV_B)

    agg = reg.get_servers(UID)
    assert sorted(s["name"] for s in agg["servers"]) == ["srv-a", "srv-b"]

    listing = {d["device_id"]: d["servers"] for d in reg.devices(UID)}
    assert listing[DEV_A] == ["srv-a"]
    assert listing[DEV_B] == ["srv-b"]

    assert set(reg.get_stub_configs(UID)) == {"srv-a", "srv-b"}


async def test_directed_frame_only_claimed_by_target():
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_B)
    _, fut = reg.enqueue(UID, SRV, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, device_id=DEV_B)

    assert await reg.claim(UID, DEV_A, wait=0.1, limit=4) == [], "定向帧不得被他设备领取"
    frames = await reg.claim(UID, DEV_B, wait=0.1, limit=4)
    assert len(frames) == 1
    reg.resolve(UID, frames[0]["id"], message={"jsonrpc": "2.0", "id": 1, "result": {}})
    assert fut.done()


async def test_broadcast_frame_claimed_exactly_once():
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_B)
    reg.enqueue(UID, SRV, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

    first = await reg.claim(UID, DEV_A, wait=0.1, limit=4)
    assert len(first) == 1
    assert await reg.claim(UID, DEV_B, wait=0.1, limit=4) == [], "广播帧先到先得,只被一台领取"


async def test_unregister_one_device_spares_other():
    """单设备下线:只回填该设备已领帧,不影响他设备(§8.1 缺陷修复)。"""
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name="srv-a")], device_id=DEV_A)
    reg.register(UID, [RelayServerSpec(name="srv-b")], device_id=DEV_B)

    _, fut_a = reg.enqueue(UID, "srv-a", {"jsonrpc": "2.0", "id": 5, "method": "tools/call"}, device_id=DEV_A)
    await reg.claim(UID, DEV_A, wait=0.1, limit=4)

    assert reg.unregister(UID, DEV_A)
    assert fut_a.done()
    assert fut_a.result()["error"]["code"] == -32000

    # B 不受影响:仍在线、可正常收发
    assert reg.is_online(UID)
    _, fut_b = reg.enqueue(UID, "srv-b", {"jsonrpc": "2.0", "id": 6, "method": "tools/call"}, device_id=DEV_B)
    frames = await reg.claim(UID, DEV_B, wait=0.1, limit=4)
    assert len(frames) == 1
    reg.resolve(UID, frames[0]["id"], message={"jsonrpc": "2.0", "id": 6, "result": {}})
    assert fut_b.done()
    assert "error" not in fut_b.result()


# ── 粘性绑定(§7.3)与远程登出(§9.3)─────────────────────


async def test_register_same_device_other_user_rejected():
    """device_id 粘性绑定:他用户注册同设备 → DeviceBoundError(API 层 409)。"""
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    with pytest.raises(DeviceBoundError) as ei:
        reg.register(UID2, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    assert ei.value.owner_user == UID
    # 同账号 re-register 合法
    names, _ = reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    assert names == [SRV]


async def test_logout_unbinds_sticky_binding():
    """登出即解绑:原账号 unregister 后,其他账号可重新绑定同设备。"""
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    assert reg.unregister(UID, DEV_A)
    names, _ = reg.register(UID2, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    assert names == [SRV]


async def test_revoke_device_delivers_control_frame_then_blocks():
    """远程登出:定向 device/logout 控制帧可达 → revoked 语义(register 拒绝、
    不再计入在线)。"""
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A, label="MacBook")

    assert reg.revoke_device(UID, DEV_A)

    # 在线设备:在档 claim 领到控制帧(server=_control,method=device/logout)
    frames = await reg.claim(UID, DEV_A, wait=0.1, limit=4)
    assert len(frames) == 1
    assert frames[0]["server"] == "_control"
    assert frames[0]["message"]["method"] == "device/logout"
    assert frames[0]["message"]["params"]["device_id"] == DEV_A

    # 帧送完后:register 拒绝(重新登录须生成新 device_id)
    with pytest.raises(DeviceRevokedError):
        reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    # revoked 不计入 presence
    assert not reg.is_online(UID)
    dev = reg.get_device(UID, DEV_A)
    assert dev is not None
    assert dev.revoked


async def test_sweep_revoked_offline_device():
    """revoked 且离线的设备记录被清扫,但设备身份仍在废止集(防复活)。"""
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    reg.revoke_device(UID, DEV_A)
    _age_device(UID, DEV_A, OFFLINE_AFTER + 1)

    assert reg.devices(UID) == []  # 访问即清扫
    with pytest.raises(DeviceRevokedError):
        reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)


async def test_register_invalid_device_id_rejected():
    reg = get_relay_registry()
    with pytest.raises(ValueError, match="invalid device_id"):
        reg.register(UID, [RelayServerSpec(name=SRV)], device_id="bad id!")
    assert DEVICE_ID_RE.match(DEV_A)


# ── 设备管理面数据(§9.2/§9.4)──────────────────────────────


async def test_label_first_registration_only_and_rename():
    """label 仅首注册生效(用户改名不被壳心跳覆盖);rename 可改。"""
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A, label="MacBook · macOS", client_version="0.9.2")
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A, label="should-not-apply")

    dev = reg.get_device(UID, DEV_A)
    assert dev.label == "MacBook · macOS"
    assert dev.client_version == "0.9.2"

    assert reg.rename_device(UID, DEV_A, "  公司机  ")
    assert reg.get_device(UID, DEV_A).label == "公司机"
    assert not reg.rename_device(UID, "ghost-device-x", "x")


async def test_devices_listing_hides_legacy_and_sorts():
    """legacy 伪设备不进设备管理面;按 last_seen 降序。"""
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    reg.register(UID, [RelayServerSpec(name=SRV)])  # 旧版壳 → _legacy
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_B)

    ids = [d["device_id"] for d in reg.devices(UID)]
    assert ids == [DEV_B, DEV_A]
    entry = reg.devices(UID)[1]
    assert entry["online"] is True
    assert entry["servers"] == [SRV]
    assert entry["registered_at"]
    assert entry["last_seen"]


async def test_claim_missing_device_returns_empty_no_resurrect():
    """claim 不复活设备记录(壳 register 自愈);幽灵设备 → 空返回。"""
    reg = get_relay_registry()
    assert await reg.claim(UID, "ghost-device-1", wait=0.1, limit=4) == []
    assert reg.get_device(UID, "ghost-device-1") is None


async def test_offline_device_drops_from_union_but_listed():
    """离线设备退出聚合/stub 面,但记录保留展示(仅 revoked 才被清扫)。"""
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name="srv-a")], device_id=DEV_A)
    _age_device(UID, DEV_A, OFFLINE_AFTER + 1)

    assert not reg.is_online(UID)
    assert reg.get_stub_configs(UID) == {}
    assert reg.get_servers(UID)["online"] is False
    assert [d["device_id"] for d in reg.devices(UID)] == [DEV_A]
    assert reg.devices(UID)[0]["online"] is False


# ── host_device 路由(§8.3,transport=local 连接侧)─────────


async def test_host_device_routing():
    reg = get_relay_registry()
    # 全离线 → FAST FAIL(含「离线」字样,连接侧 last_error 判据)
    with pytest.raises(ConnectionError) as ei:
        host_device(UID, SRV)
    assert "离线" in str(ei.value)

    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    reg.register(UID, [RelayServerSpec(name="srv-b")], device_id=DEV_B)
    assert host_device(UID, SRV) == DEV_A  # 唯一在线托管 → 定向

    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_B)  # B 也托管
    assert host_device(UID, SRV) is None  # 多台 → 广播

    with pytest.raises(ConnectionError) as ei:  # 无在线托管 → FAST FAIL
        host_device(UID, "ghost-srv")
    assert "未在桌面版注册" in str(ei.value)

    reg.register(UID, [RelayServerSpec(name="ghost-srv")])  # legacy 在档 → 广播兜底
    assert host_device(UID, "ghost-srv") is None


# ── stub 配置并入 MCPToolManager ──────────────────────────────


def test_stub_configs_merge_into_manager():
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV, timeout=77)], device_id=DEV_A)

    from dawei.tools.mcp_tool_manager import MCPToolManager

    mgr = MCPToolManager(workspace_root=None, user_id=UID)
    cfg = mgr.get_config(SRV)
    assert cfg is not None
    assert cfg.transport == "local"
    assert cfg.timeout == 77
    assert cfg.source_level == "local"
    assert mgr.get_config_sources(SRV)["local"] is True
    stats = mgr.get_statistics()
    assert stats["by_source_level"]["local"] >= 1


# ── transport=local 连接路径 ───────────────────────────────────


async def test_connect_local_offline_fails_fast():
    # 注册后立即下线(壳掉线):FAST FAIL,不进入 owner/30s 等待
    from dawei.tools.mcp_tool_manager import MCPToolManager

    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    mgr = MCPToolManager(workspace_root=None, user_id=UID)
    reg.unregister(UID, DEV_A)  # stub 已并入 manager,但壳已离线

    ok = await mgr.connect_server(SRV)
    assert ok is False
    info = mgr.get_server_info(SRV)
    assert info.status == "error"
    assert "离线" in (info.last_error or "")


def _fake_shell_dispatcher(message):
    """模拟壳侧子进程的 MCP 应答(initialize/tools/list/resources/list/call_tool)。"""
    method = message.get("method")
    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "fake-local", "version": "0.0.1"},
        }
    elif method == "tools/list":
        result = {
            "tools": [
                {
                    "name": "echo",
                    "description": "echo back",
                    "inputSchema": {"type": "object"},
                }
            ]
        }
    elif method == "resources/list":
        result = {"resources": []}
    elif method == "tools/call":
        result = {
            "content": [{"type": "text", "text": "echoed"}],
            "isError": False,
        }
    else:
        result = {}
    return {"jsonrpc": "2.0", "id": message.get("id"), "result": result}


async def _start_fake_shell(reg, uid, device_id=""):
    """fake shell 常驻循环:持续 claim→回填(跳过通知),直至被取消。

    不能"一轮一领"——通知与请求交错到达时,单轮 claim 可能只领走通知
    就返回,把后续请求留在队列里无人认领(shell 挂起)。
    """

    async def shell_loop():
        while True:
            frames = await reg.claim(uid, device_id, wait=1.0, limit=16)
            for f in frames:
                msg = f["message"]
                if msg.get("method") == "device/logout":
                    return  # 壳按 method 拦截自处理,不转发子进程
                if "id" in msg:
                    reg.resolve(uid, f["id"], message=_fake_shell_dispatcher(msg))

    return asyncio.create_task(shell_loop())


async def test_local_relay_client_full_session_roundtrip():
    """local_relay_client(唯一在线托管 → 定向)+ 真实 ClientSession 全链。"""
    pytest.importorskip("mcp")
    from mcp import ClientSession

    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV, timeout=30)], device_id=DEV_A)
    shell = await _start_fake_shell(reg, UID, DEV_A)

    try:
        async with local_relay_client(SRV, UID, timeout=30) as (read_stream, write_stream), ClientSession(read_stream, write_stream) as session:
            init = await asyncio.wait_for(session.initialize(), timeout=10)
            assert init.serverInfo.name == "fake-local"

            tools = await asyncio.wait_for(session.list_tools(), timeout=10)
            assert [t.name for t in tools.tools] == ["echo"]

            call = await asyncio.wait_for(session.call_tool("echo", {"text": "hi"}), timeout=10)
            assert call.content[0].text == "echoed"
    finally:
        shell.cancel()


async def test_manager_connect_local_with_fake_shell():
    """MCPToolManager.connect_server(transport=local)全链:_owner 分支 + list_tools。"""
    pytest.importorskip("mcp")
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV, timeout=30)], device_id=DEV_A)

    from dawei.tools.mcp_tool_manager import MCPToolManager

    mgr = MCPToolManager(workspace_root=None, user_id=UID)
    shell_task = await _start_fake_shell(reg, UID, DEV_A)
    try:
        ok = await asyncio.wait_for(mgr.connect_server(SRV), timeout=30)
    finally:
        shell_task.cancel()
    assert ok is True

    info = mgr.get_server_info(SRV)
    assert info.status == "connected"
    assert [t["name"] for t in info.tools] == ["echo"]

    await mgr.disconnect_server(SRV)
    assert mgr.get_server_info(SRV).status == "disconnected"


# ── 路由挂载冒烟 ──────────────────────────────────────────────


def test_relay_router_mounted():
    from dawei.api.users import router as users_router

    paths = {getattr(r, "path", "") for r in users_router.routes}
    for expected in (
        "/api/users/me/mcp-relay/register",
        "/api/users/me/mcp-relay/claim",
        "/api/users/me/mcp-relay/result",
        "/api/users/me/mcp-relay/servers",
        "/api/users/me/mcp-relay/call",
        "/api/users/me/mcp-relay",
        "/api/users/me/devices",
        "/api/users/me/devices/{device_id}/rename",
        "/api/users/me/devices/{device_id}",
    ):
        assert expected in paths, f"missing route {expected}"


# ── 账户隔离(硬约束,2026-09-18 paper-search 回归)──────────────
# light-app 壳的 MCP/浏览器只服务其登录账号。stub 面 / 帧队列 / 在线判定
# 严格按 user_id,不做任何跨用户回退 —— 即使全注册表只有一只在线壳,
# 其他用户(含引擎遗留 default_user)也不得看到或触达它。


async def test_strict_isolation_other_user_sees_nothing():
    """唯一在线壳属于 web-user:其他用户(含 default_user)看不到 stub、不在线。"""
    reg = get_relay_registry()
    reg.register("web-user", [RelayServerSpec(name=SRV, timeout=66)], device_id=DEV_A)

    assert reg.get_stub_configs("default_user") == {}
    assert reg.get_stub_configs("other-user") == {}
    assert not reg.is_online("default_user")
    assert not reg.is_online("other-user")
    # 归属用户正常可见
    assert SRV in reg.get_stub_configs("web-user")
    assert reg.is_online("web-user")


async def test_strict_isolation_frames_do_not_cross_users():
    """default_user 入队的帧只进自己的队列,绝不出现在 web-user 的 claim 里。"""
    reg = get_relay_registry()
    reg.register("web-user", [RelayServerSpec(name=SRV)], device_id=DEV_A)

    _, fut = reg.enqueue("default_user", SRV, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert fut is not None

    frames = await reg.claim("web-user", DEV_A, wait=0.1, limit=4)
    assert frames == [], "跨用户帧泄漏"

    # default_user 自己的设备上线后才能领到(帧最终 TTL 过期兜底)
    reg.register("default_user", [RelayServerSpec(name=SRV)])  # legacy 伪设备
    own = await reg.claim("default_user", "", wait=0.1, limit=4)
    assert len(own) == 1
    assert own[0]["server"] == SRV


# ── 出站帧序列化失败(None 路径)───────────────────────────────


class _UnserializableBody:
    """model_dump_json 必炸且非 dict → _message_to_dict 判定为 None。

    pump 对该结果不再静默丢弃:请求帧(有 id)合成 JSON-RPC 错误回填,
    ClientSession 走 McpError 而非干等 SDK 超时。
    """

    id = 7

    def model_dump_json(self, **kwargs):
        raise RuntimeError("boom")


def test_message_to_dict_unserializable_returns_none():
    from dawei.tools.mcp_relay import _message_to_dict

    outgoing = type("Outgoing", (), {})()
    outgoing.message = _UnserializableBody()
    assert _message_to_dict(outgoing) is None


# ── /call 入口(方案 §5.2;直接调 handler,FAST FAIL 语义)──────

from fastapi import HTTPException  # noqa: E402

from dawei.api.users import devices as devices_api  # noqa: E402
from dawei.api.users import mcp_relay as relay_api  # noqa: E402


async def _call(server=SRV, tool="echo", args=None, uid=UID, device_id=None):
    relay_api._call_rate.clear()
    req = relay_api.RelayCallRequest(server=server, tool=tool, arguments=args or {}, device_id=device_id)
    return await relay_api.call_local_mcp_tool(req, current_user=uid)


async def test_call_endpoint_roundtrip_with_fake_shell():
    """在线注册 + fake shell 执行 → 200,content 文本非 JSON 时原样返回。"""
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV, timeout=30)], device_id=DEV_A)
    shell = await _start_fake_shell(reg, UID, DEV_A)
    try:
        resp = await _call(tool="echo", args={"text": "hi"})
        assert resp["success"] is True
        assert resp["frame_id"].startswith("f-")
        assert resp["result"] == "echoed"
    finally:
        shell.cancel()


async def test_call_endpoint_offline_409():
    relay_api._call_rate.clear()
    req = relay_api.RelayCallRequest(server=SRV, tool="echo")
    with pytest.raises(HTTPException) as ei:
        await relay_api.call_local_mcp_tool(req, current_user=UID)
    assert ei.value.status_code == 409
    assert "离线" in ei.value.detail


async def test_call_offline_fails_fast_with_stale_device_records():
    """/call FAST FAIL 回归(e2e 2026-09-19):A 登出解绑 + B revoked 仍在
    设备表内(清扫前)时,不得因在档记录绕过离线检查把帧广播给无人认领
    (75s 挂起);必须立即 409。"""
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_B)
    reg.revoke_device(UID, DEV_B)
    reg.unregister(UID, DEV_A)  # B revoked 记录仍在表内

    with pytest.raises(HTTPException) as ei:
        await _call()
    assert ei.value.status_code == 409
    assert "离线" in ei.value.detail


async def test_call_endpoint_unregistered_server_409():
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)  # 在线,但目标不在清单
    with pytest.raises(HTTPException) as ei:
        await _call(server="ghost")
    assert ei.value.status_code == 409
    assert "未在桌面版注册" in ei.value.detail


async def test_call_endpoint_bad_server_name_400():
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    with pytest.raises(HTTPException) as ei:
        await _call(server="bad name!")
    assert ei.value.status_code == 400


async def test_call_endpoint_timeout_504(monkeypatch):
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV, timeout=5)], device_id=DEV_A)
    monkeypatch.setattr(relay_api, "CALL_TIMEOUT", 0.05)
    with pytest.raises(HTTPException) as ei:
        await _call()
    assert ei.value.status_code == 504
    # 超时后 future 已被 wait_for 取消:壳迟到回报不得复活它
    frames = await reg.claim(UID, DEV_A, wait=0.1, limit=4)
    assert len(frames) == 1
    assert not reg.resolve(UID, frames[0]["id"], message={"jsonrpc": "2.0", "id": 1, "result": {}})


def test_call_rate_limiter_sliding_window():
    relay_api._call_rate.clear()
    for _ in range(relay_api.CALL_RATE_LIMIT):
        relay_api._check_call_rate(UID)
    with pytest.raises(HTTPException) as ei:
        relay_api._check_call_rate(UID)
    assert ei.value.status_code == 429
    relay_api._check_call_rate("another-user")  # per-user 隔离不受影响


def test_parse_tool_payload_variants():
    ok = {"result": {"content": [{"type": "text", "text": '{"ok": true}'}], "isError": False}}
    assert relay_api._parse_tool_payload(ok) == {"ok": True}
    raw = {"result": {"content": [{"type": "text", "text": "plain text"}], "isError": False}}
    assert relay_api._parse_tool_payload(raw) == "plain text"
    with pytest.raises(HTTPException) as ei:
        relay_api._parse_tool_payload({"result": {"content": [{"type": "text", "text": "boom"}], "isError": True}})
    assert ei.value.status_code == 502
    assert "boom" in ei.value.detail
    with pytest.raises(HTTPException) as ei:
        relay_api._parse_tool_payload({"error": {"code": -32000, "message": "child exited"}})
    assert ei.value.status_code == 502
    assert "child exited" in ei.value.detail
    with pytest.raises(HTTPException) as ei:
        relay_api._parse_tool_payload({"jsonrpc": "2.0", "id": 1})  # 无 result → 畸形
    assert ei.value.status_code == 502


# ── /call 设备路由(§8.3)────────────────────────────────────


async def test_call_explicit_device_directed_to_target():
    """显式 device_id → 定向:只有目标设备的 shell 收到并回报。"""
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV, timeout=30)], device_id=DEV_A)
    reg.register(UID, [RelayServerSpec(name=SRV, timeout=30)], device_id=DEV_B)
    shell_b = await _start_fake_shell(reg, UID, DEV_B)
    try:
        resp = await _call(device_id=DEV_B)
        assert resp["success"] is True
        assert resp["result"] == "echoed"
    finally:
        shell_b.cancel()
    # 帧在 B 的定向队列,A 从未领到
    assert await reg.claim(UID, DEV_A, wait=0.05, limit=4) == []


async def test_call_explicit_missing_or_revoked_device_409():
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    with pytest.raises(HTTPException) as ei:
        await _call(device_id="ghost-device-1")
    assert ei.value.status_code == 409

    devices_api._kick_rate.clear()
    await devices_api.revoke_my_device(DEV_A, current_user=UID)
    with pytest.raises(HTTPException) as ei:
        await _call(device_id=DEV_A)
    assert ei.value.status_code == 409


async def test_call_default_directed_when_unique_host(monkeypatch):
    """缺省路由:唯一在线托管 → 定向到它(不托管的在线设备抢不到帧)。"""
    monkeypatch.setattr(relay_api, "CALL_TIMEOUT", 0.3)
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV, timeout=30)], device_id=DEV_A)
    reg.register(UID, [RelayServerSpec(name="srv-b", timeout=30)], device_id=DEV_B)
    shell_b = await _start_fake_shell(reg, UID, DEV_B)  # B 在线但不托管 SRV
    try:
        with pytest.raises(HTTPException) as ei:  # A 无 shell → 超时,证明帧没广播
            await _call()
        assert ei.value.status_code == 504
        # 超时帧留在 A 的定向队列,A 可领取
        frames = await reg.claim(UID, DEV_A, wait=0.1, limit=4)
        assert len(frames) == 1
    finally:
        shell_b.cancel()


async def test_call_default_broadcast_when_multiple_hosts():
    """缺省路由:多台在线托管 → 广播,任意一台(此处 B)执行。"""
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV, timeout=30)], device_id=DEV_A)
    reg.register(UID, [RelayServerSpec(name=SRV, timeout=30)], device_id=DEV_B)
    shell_b = await _start_fake_shell(reg, UID, DEV_B)  # 只有 B 在 claim
    try:
        resp = await _call()
        assert resp["success"] is True
        assert resp["result"] == "echoed"
    finally:
        shell_b.cancel()


# ── register/claim handler 设备语义(§8.2/§9.3)────────────


async def test_register_handler_bound_409_and_revoked_403():
    reg = get_relay_registry()
    reg.register(UID2, [RelayServerSpec(name=SRV)], device_id=DEV_A)  # UID2 绑定 DEV_A
    req = relay_api.RegisterRequest(device_id=DEV_A, servers=[relay_api.RelayServerIn(name=SRV)])
    with pytest.raises(HTTPException) as ei:
        await relay_api.register_local_mcp(req, current_user=UID)
    assert ei.value.status_code == 409
    assert "device_bound" in ei.value.detail

    reg.revoke_device(UID2, DEV_A)
    with pytest.raises(HTTPException) as ei:
        await relay_api.register_local_mcp(req, current_user=UID2)
    assert ei.value.status_code == 403
    assert "device_logged_out" in ei.value.detail
    # 结构化错误标记(壳侧 is_device_logged_out 优先按此判定,契约锁定)
    assert (ei.value.headers or {}).get("X-Relay-Error") == "device_logged_out"


async def test_revoked_device_claim_delivers_frames_then_403():
    """claim 的 revoked 语义:有帧先放行送达(device/logout 可达),送完 → 403。"""
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    devices_api._kick_rate.clear()
    await devices_api.revoke_my_device(DEV_A, current_user=UID)

    # 控制帧优先送达:第一次 claim 200 + device/logout 帧
    resp = await relay_api.claim_local_mcp_frames(
        relay_api.ClaimRequest(device_id=DEV_A, wait=0.1), current_user=UID
    )
    assert [f["message"]["method"] for f in resp.frames] == ["device/logout"]

    # 送完 → 403 触发壳本地登出
    with pytest.raises(HTTPException) as ei:
        await relay_api.claim_local_mcp_frames(
            relay_api.ClaimRequest(device_id=DEV_A, wait=0.1), current_user=UID
        )
    assert ei.value.status_code == 403
    assert "device_logged_out" in ei.value.detail
    assert (ei.value.headers or {}).get("X-Relay-Error") == "device_logged_out"


# ── 设备管理 API(§9.3)─────────────────────────────────────


async def test_devices_api_list_rename_revoke():
    reg = get_relay_registry()
    reg.register(
        UID, [RelayServerSpec(name=SRV, timeout=30)], device_id=DEV_A, label="A 机", client_version="1.0"
    )
    devices_api._kick_rate.clear()

    resp = await devices_api.list_my_devices(current_user=UID)
    assert [d["device_id"] for d in resp.devices] == [DEV_A]
    assert resp.devices[0]["label"] == "A 机"
    assert resp.devices[0]["client_version"] == "1.0"
    assert resp.devices[0]["online"] is True

    ok = await devices_api.rename_my_device(DEV_A, devices_api.RenameRequest(label="家里 PC"), current_user=UID)
    assert ok.success is True
    assert reg.get_device(UID, DEV_A).label == "家里 PC"

    ok = await devices_api.revoke_my_device(DEV_A, current_user=UID)
    assert ok.success is True
    assert reg.get_device(UID, DEV_A).revoked
    # revoke 同时入队 device/logout 控制帧
    assert reg.has_queued(UID, DEV_A)


async def test_devices_api_404_and_invalid_id():
    reg = get_relay_registry()
    reg.register(UID, [RelayServerSpec(name=SRV)], device_id=DEV_A)
    devices_api._kick_rate.clear()
    with pytest.raises(HTTPException) as ei:
        await devices_api.rename_my_device("ghost-device-9", devices_api.RenameRequest(label="x"), current_user=UID)
    assert ei.value.status_code == 404
    with pytest.raises(HTTPException) as ei:
        await devices_api.revoke_my_device("bad id!", current_user=UID)  # 400 先于限频
    assert ei.value.status_code == 400


def test_kick_rate_limiter_sliding_window():
    devices_api._kick_rate.clear()
    for _ in range(devices_api.KICK_RATE_LIMIT):
        devices_api._check_kick_rate(UID)
    with pytest.raises(HTTPException) as ei:
        devices_api._check_kick_rate(UID)
    assert ei.value.status_code == 429
    devices_api._check_kick_rate("another-user")  # per-user 隔离
