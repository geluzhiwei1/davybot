"""DAWEI_SERVER_PASSWORD 访问密码门 — ASGI 中间件 (server 自包含方案).

单点收口: 设了 DAWEI_SERVER_PASSWORD 且无 auth capability (server/tui 自包含) 时,
所有 /api/* 与 /ws 请求必须携带 Bearer 密码, 否则 401 (WS 则拒绝握手)。

为什么是中间件而不是只改 auth.py 漏斗:
  - 部分端点完全不调 get_authenticated_user_id (如 /api/workspaces/v2/workspaces/{id});
  - 部分端点 except Exception 吞掉 401 走 legacy 匿名兜底 (如 workspace 列表)。
中间件在 handler 之前统一拦截, 顺带覆盖这些旁路。auth.py 内的同名校验保留作第二道防线。

豁免: /api/runtime-info — 前端启动探测 (决定登录形态), 必须匿名可达。

WS: 浏览器 WebSocket 无法自定义 header → 额外接受 ?token= 查询参数
    (与 ws-client.ts 的传参方式一致)。
"""

import os
import secrets
from urllib.parse import parse_qs

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# 匿名可达豁免路径 (前端启动探测)
EXEMPT_PATHS = frozenset({"/api/runtime-info"})
# 匿名可达豁免前缀 — 工作区分享公开页 (/api/shares 自带提取码+share-token 鉴权)
EXEMPT_PREFIXES = ("/api/shares",)

# 受保护的路径前缀 (REST + WS 握手)
PROTECTED_PREFIXES = ("/api/", "/ws")


def access_gate_active() -> bool:
    """密码门是否生效: 设了密码 且 无 auth capability (自包含模式)。"""
    if not os.environ.get("DAWEI_SERVER_PASSWORD", ""):
        return False
    from dawei.runtime import get_capabilities

    return "auth" not in get_capabilities()


def _extract_provided_token(scope: Scope, headers: Headers) -> str:
    auth = headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer ") :].strip()
    if scope["type"] == "websocket":
        # 浏览器 WS 无法自定义 header → 允许 ?token=
        query = scope.get("query_string", b"").decode("latin-1")
        return (parse_qs(query).get("token") or [""])[0]
    return ""


class AccessPasswordMiddleware:
    """Bearer 访问密码门 (见模块 docstring)。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or not access_gate_active():
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith(PROTECTED_PREFIXES) or path in EXEMPT_PATHS or path.startswith(EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        expected = os.environ["DAWEI_SERVER_PASSWORD"]
        provided = _extract_provided_token(scope, Headers(scope=scope))
        if secrets.compare_digest(provided, expected):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "http":
            response = JSONResponse(
                status_code=401,
                content={"detail": "Access password required (DAWEI_SERVER_PASSWORD, send as Bearer token)"},
            )
            await response(scope, receive, send)
        else:
            # ASGI 允许 accept 前 close: 客户端表现为握手被拒 (与 _authenticate_ws 的 1008 语义一致)
            await send({"type": "websocket.close", "code": 1008, "reason": "access password required"})
