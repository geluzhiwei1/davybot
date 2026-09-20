# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""本机 MCP relay —— davy-light-app 壳承载私有 MCP server 的云端透传层。

目标(方案.md):用户的私有 stdio MCP server 跑在本机 light-app 壳里,
云端 SaaS 智能体远程调用。NAT 后的本机无法被云端直连,复用浏览器轨的
claim/result 范式:云端 MCPToolManager 以 ``transport="local"`` 连接时不
spawn/直连任何 server,而是把 ClientSession 发出的 JSON-RPC 帧(与 mcp
stdio 传输线上的 SessionMessage 逐字对齐)放进 per-user 队列;本机壳长轮询
claim 取走 → 转发给本地 stdio 子进程 → 响应帧 POST 回来 → 云端 future
解析 → 塞回 read_stream,ClientSession 照常消费。MCP 语义
(initialize / tools/list / call_tool / resources)完整保留。

设备模型(P1,方案 §8.2):user ─► devices{device_id ─► 状态};帧路由
广播(任意在线设备可领)/定向;presence per-device,用户在线 = any。
device_id 为壳安装级 UUID(``~/.normnomos/light-app/device.json``),粘性
绑定到 user_id(§7.3:他用户注册同设备 409,登出即解绑)。旧版壳(空
device_id)映射伪设备 ``_legacy``,共享广播帧,不参与设备管理面。

协议(壳 → 云端,全部携带 ``Authorization: Bearer <jwt>``;
端点实现见 ``dawei/api/users/mcp_relay.py``)::

    POST   /api/users/me/mcp-relay/register  {"client","device_id","label?","client_version?","servers":[...]}
    POST   /api/users/me/mcp-relay/claim     {"device_id","wait":25,"limit":8} → {"frames":[{id,server,message}]}
    POST   /api/users/me/mcp-relay/result    {"device_id","id","message"|"error"}
    GET    /api/users/me/mcp-relay/servers   (聚合在线状态 + per-device 视图)
    DELETE /api/users/me/mcp-relay?device_id=...  (单设备下线,不影响他设备)

云 → 桌控制帧(§9.3 远程登出):定向通知帧 ``method="device/logout"``
(server 名 ``_control``),壳按 method 拦截自处理,不转发子进程;已登出
(revoked)设备的 register/claim → 403 device_logged_out,壳收到后本地登出
并重新生成 device_id(远程登出即废止旧设备身份,重新登录 = 全新绑定)。

限制(单向 request-response 模型的固有权衡,FAST FAIL):
- server 主动发起的请求(sampling/roots)与推送通知(tools/list_changed)
  无法上行 —— 壳侧对子进程的此类请求以 -32601 应答;工具列表刷新靠重连。
- 队列/在线态/粘性绑定是进程内存态(单 uvicorn worker 假设,与
  WebSocketManager 一致);进程重启后壳经 register 自愈。
"""

import asyncio
import json
import logging
import re
import uuid
from collections import deque
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from dawei.core.datetime_compat import UTC

logger = logging.getLogger(__name__)

# mcp SDK 与 MCPToolManager 同门禁(未装 SDK 时本模块仅提供注册表,不建流)。
try:
    from mcp.types import JSONRPCMessage

    try:
        # mcp>=1.x 流上对象是 SessionMessage(dataclass,mcp/shared/message.py;
        # 不在 mcp.types —— 从错误模块导入会静默回退成裸 JSONRPCMessage,
        # 导致 ClientSession receive loop AttributeError)。
        from mcp.shared.message import SessionMessage
    except ImportError:  # pragma: no cover - 旧版裸 pydantic 对象
        SessionMessage = None  # type: ignore[assignment]
    MCP_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    JSONRPCMessage = None  # type: ignore[assignment]
    SessionMessage = None  # type: ignore[assignment]
    MCP_SDK_AVAILABLE = False

# 壳 claim 长轮询 ≤30s + 失败退避,超过该窗口没有 register/claim/result
# 即视为离线(connect 时 FAST FAIL,不白等 30s initialize 超时)。
OFFLINE_AFTER = 120.0
# 队列中无人 claim 的帧惰性过期(壳离线时防泄漏;请求帧以错误回填)。
FRAME_TTL = 600.0
# 壳长轮询最大 hold 秒数(API 层钳位输入)。
MAX_CLAIM_WAIT = 30.0
# frame future 超时 = max(server timeout, 60) + 轮询余量。
RELAY_MARGIN = 35.0

# server 名是配置键 + 审计标识,收紧字符集(与文件配置键同域)。
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
# device_id:壳安装级 UUID(粘性绑定/定向路由键;空 = 旧版壳)。
DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
# 旧版壳(空 device_id)映射的伪设备键:可领广播帧,不参与设备管理面。
LEGACY_DEVICE = "_legacy"
# 云 → 桌控制帧的伪 server 名(壳按 method 拦截,不转发子进程)。
CONTROL_SERVER = "_control"


def _rpc_error(request: dict[str, Any], text: str) -> dict[str, Any]:
    """构造 JSON-RPC 错误响应(让 ClientSession 走 McpError 路径,而非挂起)。"""
    return {
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "error": {"code": -32000, "message": text},
    }


def _message_to_dict(outgoing: Any) -> dict[str, Any] | None:
    """流上对象(SessionMessage / 旧版裸 pydantic)→ 可入队 dict。

    序列化与 stdio_client 写 stdin 逐字一致:model_dump_json(by_alias=True,
    exclude_none=True) —— alias 形态正是 MCP 线上协议,壳/子进程两侧无需再适配。
    """
    body = getattr(outgoing, "message", outgoing)
    if body is None:
        return None
    try:
        return json.loads(body.model_dump_json(by_alias=True, exclude_none=True))
    except Exception:
        if isinstance(body, dict):
            return dict(body)
        return None


def _dict_to_session_message(payload: dict[str, Any]) -> Any:
    """响应 dict → 流上对象(与 _message_to_dict 互逆)。"""
    if JSONRPCMessage is None:
        return payload
    msg = JSONRPCMessage.model_validate(payload)
    if SessionMessage is not None:
        return SessionMessage(message=msg)
    return msg


@dataclass
class RelayServerSpec:
    """壳注册的本机 server 描述(command/env 留在本机,云端只见名字。"""

    name: str
    timeout: int = 300


class DeviceBoundError(Exception):
    """device_id 已粘性绑定其他用户(方案 §7.3 L3:同机换账号须先登出解绑)。
    携带绑定方 user_id,API 层转 409。"""

    def __init__(self, device_id: str, owner_user: str):
        self.device_id = device_id
        self.owner_user = owner_user
        super().__init__("device_bound: 该设备已绑定其他账号")


class DeviceRevokedError(Exception):
    """设备已被账号所有者远程登出(方案 §9.3)。API 层转 403;壳收到后
    本地登出并重新生成 device_id(旧设备身份废止,重新登录 = 全新绑定)。"""

    def __init__(self, device_id: str):
        self.device_id = device_id
        super().__init__("device_logged_out: 本设备已被账号所有者登出")


@dataclass
class PendingFrame:
    frame_id: str
    server: str
    message: dict[str, Any]
    device_id: str | None = None  # 定向设备;None = 广播(任意在线设备可领)
    claimed_by: str | None = None  # 领取设备的 key(register 面向 unregister 生效)
    future: asyncio.Future | None = None  # 请求帧等待响应;通知帧为 None
    enqueued_at: float = 0.0  # loop.time()(enqueue 时填充)

    def to_claim(self) -> dict[str, Any]:
        return {"id": self.frame_id, "server": self.server, "message": self.message}


@dataclass
class _DeviceRelay:
    """per-device relay 状态(方案 §8.2):注册面 + 定向队列 + presence。"""

    device_id: str  # 真实 device_id;旧版壳伪设备为 ""
    label: str = ""  # 用户可编辑;首注册时壳上报 "hostname · OS"
    client_version: str = ""
    registered_at: float = 0.0
    last_seen: float = 0.0
    servers: dict[str, RelayServerSpec] = field(default_factory=dict)
    queue: deque[PendingFrame] = field(default_factory=deque)  # 定向给本设备的帧
    event: asyncio.Event = field(default_factory=asyncio.Event)
    revoked: bool = False  # 远程登出标记(记录保留至下线后被清扫)


@dataclass
class _UserRelay:
    """per-user relay 状态:设备表 + 广播队列 + 已领未回 future。"""

    devices: dict[str, _DeviceRelay] = field(default_factory=dict)  # key = device_id 或 _legacy
    broadcast: deque[PendingFrame] = field(default_factory=deque)  # 先到先得
    pending: dict[str, PendingFrame] = field(default_factory=dict)  # 已 claim 未回(帧 id 全局唯一)


class RelayRegistry:
    """进程级单例注册表(单 event loop 假设;与 WebSocketManager 同生命周期)。"""

    def __init__(self) -> None:
        self._users: dict[str, _UserRelay] = {}
        self._device_owner: dict[str, str] = {}  # device_id → user_id(粘性绑定 §7.3)
        self._revoked: set[str] = set()  # 远程登出废止的设备身份(内存态)

    def _user(self, user_id: str) -> _UserRelay:
        return self._users.setdefault(user_id, _UserRelay())

    # ── 注册面 ────────────────────────────────────────────────

    def register(
        self,
        user_id: str,
        specs: list[RelayServerSpec],
        device_id: str = "",
        label: str = "",
        client_version: str = "",
    ) -> tuple[list[str], bool]:
        """登记设备与 server 清单(全量覆盖该设备);返回 (该设备 names, changed)。
        changed=True 表示聚合 stub 配置面变化,调用方应 areload 该用户的
        MCPToolManager。

        设备语义(§8.2/§7.3/§9.3):
        - 多桌面各自独立设备,同账号双桌面合法(P0 冲突 409 退役);
        - device_id 已绑定其他用户 → DeviceBoundError(409,须原账号登出解绑);
        - revoked 设备 → DeviceRevokedError(403,壳本地登出换新身份);
        - label 仅首注册生效(用户改名不被壳心跳覆盖);
        - 空 device_id(旧版壳)= legacy 伪设备。
        """
        if device_id:
            if not DEVICE_ID_RE.match(device_id):
                raise ValueError(f"invalid device_id: {device_id[:16]}…")
            if device_id in self._revoked:
                raise DeviceRevokedError(device_id)
            owner = self._device_owner.get(device_id)
            if owner is not None and owner != user_id:
                raise DeviceBoundError(device_id, owner)

        user = self._user(user_id)
        self._sweep_user(user)
        before = self._union_specs(user)
        key = device_id or LEGACY_DEVICE
        dev = user.devices.get(key)
        if dev is None:
            dev = _DeviceRelay(device_id=device_id, registered_at=self._now())
            user.devices[key] = dev
        dev.last_seen = self._now()
        dev.client_version = client_version or dev.client_version
        if not dev.label:
            dev.label = label.strip()[:64] or (device_id[:8] or "桌面版")
        dev.servers = {s.name: s for s in specs}
        if device_id:
            self._device_owner[device_id] = user_id
        changed = self._union_specs(user) != before
        return sorted(dev.servers.keys()), changed

    def unregister(self, user_id: str, device_id: str = "") -> bool:
        """单设备下线:清该设备注册面 + 其队列/已领帧错误回填;不影响他设备
        (§8.1 缺陷修复)。真实设备同时解绑粘性映射(§7.3 登出即解绑)。"""
        user = self._users.get(user_id)
        if user is None:
            return False
        key = device_id or LEGACY_DEVICE
        dev = user.devices.pop(key, None)
        if dev is None:
            return False
        frames = list(dev.queue) + [f for f in user.pending.values() if f.claimed_by == key]
        for frame in frames:
            user.pending.pop(frame.frame_id, None)
        self._fail_frames(frames, "local mcp host unregistered")
        if key != LEGACY_DEVICE:
            self._device_owner.pop(key, None)
        return True

    def revoke_device(self, user_id: str, device_id: str) -> bool:
        """远程登出(§9.3):标记 revoked + 解绑 + 向该设备投递 device/logout
        控制帧(在档 claim 长轮询立即唤醒)。设备记录保留至壳 DELETE 下线或
        离线后被清扫(期间 register/claim 由 API 层按 revoked 拒绝)。"""
        if not device_id:
            return False
        user = self._users.get(user_id)
        dev = user.devices.get(device_id) if user else None
        if dev is None:
            return False
        dev.revoked = True
        self._revoked.add(device_id)  # 身份废止常驻(清扫后仍拒 register,§9.3)
        self._device_owner.pop(device_id, None)
        frame = PendingFrame(
            frame_id=f"f-{uuid.uuid4().hex[:12]}",
            server=CONTROL_SERVER,
            message={
                "jsonrpc": "2.0",
                "method": "device/logout",
                "params": {"device_id": device_id, "ts": datetime.now(tz=UTC).isoformat()},
            },
            device_id=device_id,
            enqueued_at=self._now(),
        )
        dev.queue.append(frame)
        dev.event.set()
        logger.warning(f"relay device revoked (user={user_id}, device={device_id[:8]})")
        return True

    def rename_device(self, user_id: str, device_id: str, label: str) -> bool:
        dev = self.get_device(user_id, device_id)
        if dev is None:
            return False
        dev.label = label.strip()[:64]
        return True

    def get_device(self, user_id: str, device_id: str) -> _DeviceRelay | None:
        """单设备查询(真实设备 only;legacy 伪设备不参与管理面)。"""
        user = self._users.get(user_id)
        if user is None or not device_id:
            return None
        return user.devices.get(device_id)

    def has_queued(self, user_id: str, device_id: str) -> bool:
        """该设备定向队列是否仍有待领帧(claim 的 revoked 放行判定:
        有帧先放行送达,送完再 403 —— 保证 device/logout 控制帧可达)。"""
        dev = self.get_device(user_id, device_id)
        return dev is not None and bool(dev.queue)

    def devices(self, user_id: str) -> list[dict[str, Any]]:
        """设备管理面数据源(§9.4):per-device presence/能力;legacy 不列。"""
        user = self._users.get(user_id)
        if user is None:
            return []
        self._sweep_user(user)
        now = self._now()
        out = []
        for key, dev in user.devices.items():
            if key == LEGACY_DEVICE:
                continue
            fresh = (now - dev.last_seen) < OFFLINE_AFTER
            out.append(
                {
                    "device_id": dev.device_id,
                    "label": dev.label,
                    "client_version": dev.client_version,
                    "registered_at": datetime.fromtimestamp(dev.registered_at, tz=UTC).isoformat(),
                    "last_seen": datetime.fromtimestamp(dev.last_seen, tz=UTC).isoformat(),
                    "online": fresh and not dev.revoked,
                    "revoked": dev.revoked,
                    "servers": sorted(dev.servers.keys()),
                }
            )
        out.sort(key=lambda d: d["last_seen"], reverse=True)
        return out

    # ── presence / 聚合面 ─────────────────────────────────────

    def is_online(self, user_id: str) -> bool:
        """用户在线 = 任一设备 presence 新鲜且未 revoked(§8.2)。"""
        user = self._users.get(user_id)
        if user is None:
            return False
        now = self._now()
        return any((now - d.last_seen) < OFFLINE_AFTER and not d.revoked for d in user.devices.values())

    def get_servers(self, user_id: str) -> dict[str, Any]:
        """聚合视图(§8.2):servers = 各在线设备清单并集(前端/back-compat
        形态不变);devices = per-device 视图;last_seen = 最新心跳。"""
        user = self._users.get(user_id)
        if user is None or not user.devices:
            return {"online": False, "last_seen": None, "servers": [], "devices": []}
        now = self._now()
        fresh = [d for d in user.devices.values() if (now - d.last_seen) < OFFLINE_AFTER and not d.revoked]
        union: dict[str, RelayServerSpec] = {}
        for dev in sorted(fresh, key=lambda d: d.device_id):
            for name, spec in dev.servers.items():
                union.setdefault(name, spec)
        last_seen = max(d.last_seen for d in user.devices.values())
        return {
            "online": bool(fresh),
            "last_seen": datetime.fromtimestamp(last_seen, tz=UTC).isoformat(),
            "servers": [{"name": s.name, "timeout": s.timeout} for s in union.values()],
            "devices": self.devices(user_id),
        }

    def online_host_devices(self, user_id: str, server: str) -> list[str]:
        """在线托管该 server 的真实设备 id 列表(路由决策:/call 唯一 → 定向,
        多台 → 广播;§8.3)。"""
        user = self._users.get(user_id)
        if user is None:
            return []
        now = self._now()
        return [
            d.device_id
            for key, d in sorted(user.devices.items())
            if key != LEGACY_DEVICE
            and (now - d.last_seen) < OFFLINE_AFTER
            and not d.revoked
            and server in d.servers
        ]

    # ── 帧队列 ────────────────────────────────────────────────

    def enqueue(
        self, user_id: str, server: str, message: dict[str, Any], device_id: str | None = None
    ) -> tuple[str, asyncio.Future | None]:
        """ClientSession 出站帧 / /call 合成帧入队。请求帧(有 method+id)
        返回 future 等响应;通知帧 future=None。device_id=None → 广播(任意
        在线设备可领);显式 → 定向(设备不在档抛 KeyError,调用方 FAST FAIL)。"""
        user = self._user(user_id)
        self._expire_user(user)
        loop = asyncio.get_running_loop()
        frame = PendingFrame(
            frame_id=f"f-{uuid.uuid4().hex[:12]}",
            server=server,
            message=message,
            device_id=device_id,
            enqueued_at=loop.time(),
        )
        if isinstance(message, dict) and "id" in message and "method" in message:
            frame.future = loop.create_future()
        if device_id is not None:
            dev = user.devices.get(device_id)
            if dev is None:
                raise KeyError(device_id)
            dev.queue.append(frame)
            dev.event.set()
        else:
            user.broadcast.append(frame)
            for dev in user.devices.values():
                dev.event.set()
        return frame.frame_id, frame.future

    def take(self, user_id: str, device_id: str, limit: int) -> list[dict[str, Any]]:
        """claim 出队:定向帧优先,再广播帧(先到先得);请求帧转 pending。"""
        user = self._users.get(user_id)
        if user is None:
            return []
        key = device_id or LEGACY_DEVICE
        dev = user.devices.get(key)
        if dev is None:
            return []
        self._expire_user(user)
        dev.event.clear()
        frames: list[dict[str, Any]] = []

        def drain(queue: deque[PendingFrame]) -> None:
            while queue and len(frames) < limit:
                frame = queue.popleft()
                if frame.future is not None:
                    frame.claimed_by = key
                    user.pending[frame.frame_id] = frame
                frames.append(frame.to_claim())

        drain(dev.queue)
        drain(user.broadcast)
        return frames

    async def claim(self, user_id: str, device_id: str, wait: float, limit: int) -> list[dict[str, Any]]:
        """长轮询 claim:立即取,空则挂起等新帧或超时。设备不在档 → 空返回
        (不复活记录;壳 register 自愈),claim 本身即该设备心跳。"""
        user = self._users.get(user_id)
        key = device_id or LEGACY_DEVICE
        dev = user.devices.get(key) if user else None
        if dev is None:
            return []
        dev.last_seen = self._now()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + min(max(wait, 0.0), MAX_CLAIM_WAIT)
        while True:
            frames = self.take(user_id, key, limit)
            if frames:
                return frames
            remaining = deadline - loop.time()
            if remaining <= 0:
                return []
            try:
                await asyncio.wait_for(dev.event.wait(), timeout=remaining)
            except TimeoutError:
                return self.take(user_id, key, limit)

    def resolve(
        self,
        user_id: str,
        frame_id: str,
        message: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> bool:
        """壳回报响应。error 时合成 JSON-RPC 错误响应回填 future。"""
        user = self._users.get(user_id)
        if user is None:
            return False
        frame = user.pending.pop(frame_id, None)
        if frame is None or frame.future is None or frame.future.done():
            return False
        if error:
            message = _rpc_error(frame.message, error[:500])
        elif not isinstance(message, dict):
            message = _rpc_error(frame.message, "local relay: empty result payload")
        frame.future.set_result(message)
        return True

    def fail_pending(
        self,
        user_id: str,
        server: str | None = None,
        text: str = "",
        device_id: str | None = None,
    ) -> None:
        """断开连接时以错误回填(可限定 server / 定向设备)未决 future。"""
        user = self._users.get(user_id)
        if user is None:
            return
        if device_id is not None:
            key = device_id or LEGACY_DEVICE
            pending = [
                f
                for f in user.pending.values()
                if f.claimed_by == key and (server is None or f.server == server)
            ]
        else:
            pending = [f for f in user.pending.values() if server is None or f.server == server]
        for frame in pending:
            user.pending.pop(frame.frame_id, None)
        self._fail_frames(pending, text or "local relay closed")

    # ── stub 配置面(供 MCPToolManager 合并) ──────────────────

    def get_stub_configs(self, user_id: str) -> dict[str, Any]:
        """在线设备的本机 server 并集 → transport="local" 的 stub MCPConfig
        (dict 形态,由调用方转 MCPConfig;延迟导入避免循环依赖)。

        账户隔离(硬约束):严格按 user_id 取面,不做任何跨用户回退 ——
        light-app 壳的 MCP/浏览器只服务其登录账号,引擎侧调用方必须携带
        与壳一致的账号 id(WS 会话 → WorkspaceContext → MCP 工具类全链
        传播;曾出现的 default_user 拆分已在线路层修复)。"""
        user = self._users.get(user_id)
        if user is None:
            return {}
        now = self._now()
        fresh = [d for d in user.devices.values() if (now - d.last_seen) < OFFLINE_AFTER and not d.revoked]
        if not fresh:
            return {}
        from dawei.tools.mcp_tool_manager import MCPConfig

        union: dict[str, RelayServerSpec] = {}
        for dev in sorted(fresh, key=lambda d: d.device_id):
            for name, spec in dev.servers.items():
                union.setdefault(name, spec)
        return {
            name: MCPConfig(
                server_name=name,
                command="",  # command/env 留在本机壳,云端不可见
                transport="local",
                timeout=spec.timeout,
                source_level="local",
            )
            for name, spec in union.items()
        }

    # ── 内部 ──────────────────────────────────────────────────

    @staticmethod
    def _now() -> float:
        try:
            return asyncio.get_running_loop().time()
        except RuntimeError:  # 同步上下文(测试/初始化):0 基准,首次异步触碰即校准
            return 0.0

    def _union_specs(self, user: _UserRelay) -> dict[str, int]:
        """在线设备 server 并集(stub 配置面变化的判定基准)。"""
        now = self._now()
        union: dict[str, int] = {}
        for dev in sorted(user.devices.values(), key=lambda d: d.device_id):
            if (now - dev.last_seen) < OFFLINE_AFTER and not dev.revoked:
                for name, spec in dev.servers.items():
                    union.setdefault(name, spec.timeout)
        return union

    def _expire_user(self, user: _UserRelay) -> None:
        """惰性清理:超时未 claim 的帧以错误回填(壳离线防泄漏)。"""
        now = self._now()

        def expire(queue: deque[PendingFrame]) -> None:
            while queue and (now - queue[0].enqueued_at) > FRAME_TTL:
                frame = queue.popleft()
                if frame.future is not None and not frame.future.done():
                    frame.future.set_result(
                        _rpc_error(frame.message, f"local relay frame unclaimed after {FRAME_TTL:.0f}s")
                    )

        for dev in user.devices.values():
            expire(dev.queue)
        expire(user.broadcast)

    def _sweep_user(self, user: _UserRelay) -> None:
        """清扫:revoked 且已离线的设备移出设备表(登出记录不永生)。"""
        now = self._now()
        stale = [
            key
            for key, dev in user.devices.items()
            if dev.revoked and key != LEGACY_DEVICE and (now - dev.last_seen) > OFFLINE_AFTER
        ]
        for key in stale:
            user.devices.pop(key, None)

    @staticmethod
    def _fail_frames(frames: list[PendingFrame], text: str) -> None:
        for frame in frames:
            if frame.future is not None and not frame.future.done():
                frame.future.set_result(_rpc_error(frame.message, text))


_REGISTRY: RelayRegistry | None = None


def get_relay_registry() -> RelayRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = RelayRegistry()
    return _REGISTRY


def reset_relay_registry() -> RelayRegistry:
    """测试用:丢弃全部状态重建单例。"""
    global _REGISTRY
    _REGISTRY = RelayRegistry()
    return _REGISTRY


def host_device(user_id: str, server_name: str) -> str | None:
    """transport=local 连接的路由决策(§8.3):唯一在线托管设备 → 定向
    (确定性执行);0 台在线托管 → FAST FAIL;多台 → 广播(None)。"""
    registry = get_relay_registry()
    if not registry.is_online(user_id):
        # 「离线」字样是连接侧 last_error 的 FAST FAIL 判据(test_mcp_relay 契约)
        raise ConnectionError(f"local mcp host 离线: light-app 未运行或未登录 (user '{user_id}')")
    hosts = registry.online_host_devices(user_id, server_name)
    if not hosts:
        # 伪设备(legacy)在档也可领广播帧 —— stub 面陈旧时的兜底
        user = registry._users.get(user_id)
        if user is not None and LEGACY_DEVICE in user.devices:
            return None
        raise ConnectionError(f"local mcp server '{server_name}' 未在桌面版注册 (user '{user_id}')")
    return hosts[0] if len(hosts) == 1 else None


@asynccontextmanager
async def local_relay_client(server_name: str, user_id: str, timeout: int | None = 300):
    """transport="local" 的 client 上下文 —— 对位 stdio_client,产出
    ``(read_stream, write_stream)`` 内存流对,供 MCPToolManager._owner() 内
    ``async with cm as (read, write): async with ClientSession(read, write)``。

    出站(SessionMessage)→ dict 入队(按 host_device 定向/广播);壳回报 →
    future → JSONRPCMessage 塞回 read_stream。enter/exit 必须发生在同一
    task(owner task,bug#5 约束),内部 pump 是普通 asyncio task,随 CM
    退出一并取消。
    """
    import anyio

    registry = get_relay_registry()
    device_id = host_device(user_id, server_name)

    read_send, read_recv = anyio.create_memory_object_stream(0)
    write_send, write_recv = anyio.create_memory_object_stream(0)
    frame_timeout = max(int(timeout or 300), 60) + RELAY_MARGIN

    async def _pump_out():
        """ClientSession 出站帧 → 注册表队列 → 等壳回报 → 回填 read_stream。"""
        try:
            async for outgoing in write_recv:
                message = _message_to_dict(outgoing)
                if message is None:
                    # 序列化失败(实际不可达,防御路径):请求帧回填 JSON-RPC
                    # 错误让 ClientSession 走 McpError,不干等到 SDK 超时;
                    # 通知帧(无 id)无人在等,跳过即可
                    body = getattr(outgoing, "message", outgoing)
                    req_id = getattr(body, "id", None)
                    if req_id is not None:
                        err = _rpc_error({"id": req_id}, "local relay: outgoing frame serialization failed")
                        await read_send.send(_dict_to_session_message(err))
                    continue
                try:
                    frame_id, fut = registry.enqueue(user_id, server_name, message, device_id=device_id)
                except KeyError:
                    # 定向设备已下线:单帧失败不断流
                    err = _rpc_error(message, f"local relay device '{device_id}' 已下线")
                    await read_send.send(_dict_to_session_message(err))
                    continue
                if fut is None:
                    continue  # 通知帧(无 id),无响应可等
                try:
                    response = await asyncio.wait_for(fut, timeout=frame_timeout)
                except asyncio.CancelledError:
                    raise
                except TimeoutError:
                    response = _rpc_error(message, f"local relay frame {frame_id} timed out after {frame_timeout:.0f}s")
                except Exception as e:  # noqa: BLE001 - 单帧失败不应断流
                    response = _rpc_error(message, f"local relay error: {e}")
                await read_send.send(_dict_to_session_message(response))
        except (anyio.ClosedResourceError, asyncio.CancelledError):
            pass

    pumps = [asyncio.create_task(_pump_out())]
    try:
        yield read_recv, write_send
    finally:
        for task in pumps:
            task.cancel()
        for task in pumps:
            with suppress(Exception):
                await task
        registry.fail_pending(user_id, server_name, "local relay client closed", device_id=device_id)
        with suppress(Exception):
            await read_send.aclose()
        with suppress(Exception):
            await write_recv.aclose()
