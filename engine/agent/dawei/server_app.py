# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei Server - AI Agent API Platform

Main FastAPI application with WebSocket support for real-time agent communication.
This module is used by CLI to create the FastAPI application.
"""

import asyncio
import io
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dawei.core.datetime_compat import UTC

# 强制 UTF-8 编码（解决 Windows 控制台编码问题）
if sys.platform == "win32":
    def _get_binary_stream(stream):
        if hasattr(stream, "buffer"):
            return stream.buffer
        elif hasattr(stream, "raw"):
            return stream.raw
        else:
            return stream

    if hasattr(sys.stdout, "buffer") or hasattr(sys.stdout, "raw"):
        try:
            sys.stdout = io.TextIOWrapper(_get_binary_stream(sys.stdout), encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    if hasattr(sys.stderr, "buffer") or hasattr(sys.stderr, "raw"):
        try:
            sys.stderr = io.TextIOWrapper(_get_binary_stream(sys.stderr), encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

_shared_utf8_stream = None

logger = logging.getLogger(__name__)


class UTF8StreamHandler(logging.StreamHandler):
    """自定义 StreamHandler，强制使用 UTF-8 编码写入控制台"""

    def __init__(self):
        super().__init__()
        self._setup_utf8_stream()

    def _setup_utf8_stream(self):
        global _shared_utf8_stream

        if sys.platform == "win32":
            # 旧 TextIOWrapper 先 detach() 脱钩，再替换——避免 GC 时 __del__ → close()
            # 关掉底层二进制流，导致 "I/O operation on closed file"。
            if _shared_utf8_stream is not None:
                try:
                    _shared_utf8_stream.detach()
                except Exception:
                    pass

            # Always rebuild from current sys.stderr — it may have been
            # redirected (e.g. sidecar mode) since the last call.
            if hasattr(sys.stderr, "buffer"):
                binary_stream = sys.stderr.buffer
            elif hasattr(sys.stderr, "raw"):
                binary_stream = sys.stderr.raw
            else:
                # sys.stderr is already a text stream (e.g. a log file)
                self.stream = sys.stderr
                return

            _shared_utf8_stream = io.TextIOWrapper(
                binary_stream,
                encoding="utf-8",
                errors="replace",
                line_buffering=True,
            )
            self.stream = _shared_utf8_stream
        else:
            self.stream = sys.stderr

    def emit(self, record):
        msg = self.format(record)
        try:
            self.stream.write(msg + "\n")
            self.flush()
        except (ValueError, OSError):
            # Stream closed (e.g. sidecar mode redirected stderr after handler init)
            self._setup_utf8_stream()
            self.stream.write(msg + "\n")
            self.flush()


# Configure root logger — respect LOG_LEVEL from env (default INFO)
_log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level_name, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[UTF8StreamHandler()],
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from dawei.api import (
    auth,
    checklists,
    checkpoints,
    conversations,
    knowledge_bases,
    knowledge_domains,
    market,
    privacy,
    runtime_api,  # 运行模式统一 API (/api/runtime-info)
    scheduled_tasks,
    container_runtime,
    skills,
    system,
    tools,
    websocket,
    workspaces,
    users,
    sandbox_system,  # 沙箱系统 API (前端安全设置页面)
    shares,  # 工作区分享 Viewer 公开端点 (/api/shares, 方案 §5.2)
)
# Internal server-to-server endpoints (not in dawei.api.__init__ to keep that
# namespace user-facing). Imported here for explicit router registration.
from dawei.api.users.security import router as users_security_router
from dawei.api import global_scheduled_tasks
from dawei.api.exception_handlers import register_exception_handlers
from dawei.websocket.handlers.chat import ConnectHandler
from dawei.websocket.ws_server import websocket_server
from dawei import get_dawei_home


def record_server_start(host: str, port: int) -> None:
    """Record server startup parameters to DAWEI_HOME/server.start file."""
    dawei_home = get_dawei_home()
    dawei_home.mkdir(parents=True, exist_ok=True)

    server_start_file = dawei_home / "server.start"
    accessible_host = "localhost" if host == "0.0.0.0" else host

    start_data = {
        "host": host,
        "port": port,
        "started_at": datetime.now(UTC).isoformat(),
        "web_ui": f"http://{accessible_host}:{port}/app-ui/",
        "api_docs": f"http://{accessible_host}:{port}/docs",
        "websocket": f"ws://{accessible_host}:{port}/ws",
    }

    with server_start_file.open("w", encoding="utf-8") as f:
        json.dump(start_data, f, indent=2, ensure_ascii=False)

    print(f"[Dawei Server] Server start info recorded to: {server_start_file}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown events."""
    # --- Startup ---

    # 注册主事件循环（bug#5 修复）：MCP 长连接 owner task 与 session 绑定在
    # 本 loop；worker 线程里的同步 MCP 工具经 run_on_main_loop 投递回来。
    import asyncio as _asyncio

    from dawei.tools.custom_tools.async_utils import set_main_loop

    set_main_loop(_asyncio.get_running_loop())
    print("[Dawei Server] Main event loop registered for sync-tool marshalling")

    # 运行模式统一出口: boot 时校验模式变量一致性 (FAST FAIL, 多模式统一方案 §L3)
    from dawei import runtime as dawei_runtime

    _runtime_info = dawei_runtime.validate_environment()
    print(
        f"[Dawei Server] Runtime mode: {_runtime_info['mode']} "
        f"({_runtime_info['deployment_class']}) caps={_runtime_info['capabilities']}"
    )

    # Create global DAWEI_HOME directories
    dawei_home = get_dawei_home()
    for dir_name in ("checkpoints", "sessions", "logs", "configs"):
        (dawei_home / dir_name).mkdir(parents=True, exist_ok=True)
    print(f"[Dawei Server] Global directories created at {dawei_home}")

    # Load SecurityManager (global singleton for security config)
    from dawei.core.security_manager import security_manager
    security_manager.load()
    print("[Dawei Server] SecurityManager loaded")

    # Initialize WebSocket server
    await websocket_server.initialize()

    # Validate .dawei directory structure
    from dawei.workspace.dawei_structure_validator import validate_dawei_on_startup
    validate_dawei_on_startup()
    print("[Dawei Server] .dawei directory structure validation passed")

    # Record server startup parameters
    host = getattr(app.state, "host", "0.0.0.0")
    port = getattr(app.state, "port", 8431)
    record_server_start(host, port)

    # Register ConnectHandler
    connect_handler = ConnectHandler()
    await connect_handler.initialize(
        websocket_server.message_router,
        websocket_server.websocket_manager,
        websocket_server.session_manager,
    )
    await websocket_server.message_router.register_handler(connect_handler)

    # Initialize LLM API protection layer
    from dawei.llm_api.base_client import BaseClient
    await BaseClient.initialize_global_components()
    print("[Dawei Server] LLM API protection layer initialized")

    # Initialize DaweiMem memory system
    from dawei.memory.database import init_memory_database
    print("[Dawei Server] DaweiMem memory system is enabled")

    workspaces_root = dawei_home
    if workspaces_root.exists():
        initialized_count = 0
        for workspace_dir in workspaces_root.iterdir():
            if workspace_dir.is_dir():
                db_path = workspace_dir / ".dawei" / "memory.db"
                if init_memory_database(str(db_path)):
                    initialized_count += 1
        print(f"[Dawei Server] Memory system initialized for {initialized_count} workspace(s)")
    else:
        print("[Dawei Server] Workspaces root not found, memory DBs will be created on demand")

    # Initialize Knowledge Base Manager (Multi-tenancy support)
    from dawei.knowledge.init import initialize_knowledge_base_manager
    kb_manager = initialize_knowledge_base_manager()
    print("[Dawei Server] Knowledge Base Manager initialized (Multi-tenancy support enabled)")

    # Initialize Knowledge Base Auto-Sync Scheduler
    from dawei.knowledge.sync_scheduler import initialize_sync_scheduler
    await initialize_sync_scheduler(kb_manager)
    print("[Dawei Server] Knowledge Base Auto-Sync Scheduler started")

    # Initialize Scheduler Manager
    from dawei.tools.scheduler import scheduler_manager
    await scheduler_manager.initialize()
    print("[Dawei Server] Scheduler manager initialized")

    # Cleanup orphaned temp workspaces
    from dawei.workspace.temp_workspace_manager import temp_workspace_manager
    cleaned = await temp_workspace_manager.cleanup_orphaned_temp_workspaces()
    if cleaned > 0:
        print(f"[Dawei Server] Cleaned up {cleaned} orphaned temp workspace(s)")

    # Initialize Evolution Scheduler
    from dawei.evolution import evolution_scheduler
    await evolution_scheduler.start()
    print("[Dawei Server] Evolution scheduler started")

    # 进程生命周期钩子（S5 ext_hooks 注册表，§18.5-G1 倒挂清零）—— saas ping
    # 等进程级业务服务由 davybot-biz 在 import 时注册，核心只分发不感知；
    # E2 门控（auth cap + 显式 SUPPORT_SYSTEM_URL）在各钩子内部，
    # 自包含形态(server/tui)零外呼，业务缺席 = 无钩子 = 无行为。
    from dawei.core.ext_hooks import run_lifecycle_startup

    hooks_started = await run_lifecycle_startup()
    if hooks_started:
        print(f"[Dawei Server] {hooks_started} lifecycle hook(s) started")
    else:
        print("[Dawei Server] No lifecycle hooks registered (biz absent = no behavior)")

    # 沙箱空闲清理循环 (2026-09-14 修复: cleanup_idle 此前无任何调度方,
    # 空闲沙箱 (>pause 不暂停 / >destroy 不销毁) 会一直常驻)
    # 每 60s: idle_pause(300s) → pause; idle_destroy(1800s) → 销毁; 同时回收 grace 期已过的断连会话
    async def _sandbox_idle_cleanup_loop() -> None:
        while True:
            await asyncio.sleep(60)
            try:
                from dawei.sandbox.sandbox_facade import SandboxFacade
                await SandboxFacade.cleanup_idle()
            except Exception as e:
                logger.warning("Sandbox idle cleanup failed: %s", e)

    sandbox_cleanup_task = asyncio.create_task(_sandbox_idle_cleanup_loop())
    print("[Dawei Server] Sandbox idle cleanup loop started (60s interval)")

    yield

    # --- Shutdown ---
    shutdown_errors = []

    async def _safe_shutdown(name: str, coro) -> None:
        """Run a shutdown coroutine, collecting errors to report at end."""
        try:
            await coro
            print(f"[Dawei Server] {name} shutdown complete")
        except Exception as e:
            shutdown_errors.append(f"{name}: {e}")
            logger.error("Failed to shutdown %s: %s", name, e)

    await _safe_shutdown("LLM API protection", BaseClient.shutdown_global_components())
    await _safe_shutdown("Scheduler", scheduler_manager.shutdown())
    await _safe_shutdown("Evolution scheduler", evolution_scheduler.stop())

    from dawei.knowledge.sync_scheduler import shutdown_sync_scheduler
    await _safe_shutdown("Knowledge sync scheduler", shutdown_sync_scheduler())

    from dawei.core.dependency_container import DEPENDENCY_CONTAINER
    try:
        kb_mgr = DEPENDENCY_CONTAINER.get_service("KnowledgeBaseManager")
        kb_mgr.cleanup_embedding_managers()
        print("[Dawei Server] Knowledge base embedding managers cleaned up")
    except ValueError:
        pass  # Not initialized, nothing to clean

    from dawei.core.ext_hooks import run_lifecycle_shutdown

    hooks_stopped = await run_lifecycle_shutdown()
    if hooks_stopped:
        print(f"[Dawei Server] {hooks_stopped} lifecycle hook(s) shut down")

    # 停止空闲清理循环 + 销毁全部沙箱会话 (2026-09-14 修复: 此前优雅停机
    # 不销毁沙箱, 进程退出后 _sessions 内存映射丢失, 远端 MicroVM 成孤儿,
    # 只能靠平台侧 lifetime 回收)
    sandbox_cleanup_task.cancel()
    try:
        await sandbox_cleanup_task
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning("Sandbox cleanup loop cancellation issue: %s", e)

    try:
        from dawei.sandbox.sandbox_facade import SandboxFacade
        SandboxFacade.destroy_all_sessions()
        print("[Dawei Server] All sandbox sessions destroyed on shutdown")
    except Exception as e:
        shutdown_errors.append(f"Sandbox sessions: {e}")
        logger.warning("Failed to destroy sandbox sessions: %s", e)

    if shutdown_errors:
        logger.warning("Shutdown encountered %d error(s): %s", len(shutdown_errors), shutdown_errors)


def create_app(host: str = "0.0.0.0", port: int = 8431) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Dawei Agent API - Orchestrator Mode",
        description="AI-powered agent platform with multi-agent orchestration",
        version="2.0.0",
        lifespan=lifespan,
    )

    # server 自包含访问密码门 (DAWEI_SERVER_PASSWORD) — 须先于 CORS 注册:
    # add_middleware 是 LIFO, 后注册的先入站; CORS 先处理预检 OPTIONS (不带 Authorization),
    # 密码门再拦真实请求, 否则浏览器跨域预检会被 401 打死。
    from dawei.api.access_gate import AccessPasswordMiddleware

    app.add_middleware(AccessPasswordMiddleware)

    # CORS middleware
    # NOTE: allow_credentials=True is incompatible with allow_origins=["*"] per CORS spec.
    #   Browsers will reject credentialed requests to wildcard origins.
    #   When running behind nginx (production), add the deployment origin below.
    #   When running locally for dev, localhost:8015 (davybot-app Vite) is the main consumer.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8431",
            "http://localhost:8015",  # davybot-app Vite dev
            "tauri://localhost",
            "https://tauri.localhost",
            "http://tauri.localhost",
            # E3: 云端域名不再内置 —— 额外部署源(nginx/生产域名)经
            # DAWEI_CORS_ORIGINS(逗号分隔)显式注入
            *[
                origin.strip()
                for origin in os.getenv("DAWEI_CORS_ORIGINS", "").split(",")
                if origin.strip()
            ],
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Tauri CORS safety net — origins are now listed directly in CORSMiddleware above,
    # but this rewrite middleware is kept as a fallback in case any code path or
    # Starlette version doesn't handle non-standard schemes correctly.
    # add_middleware is LIFO: last registered runs FIRST on inbound, LAST on outbound.
    TAURI_ORIGINS = {b"tauri://localhost", b"https://tauri.localhost", b"http://tauri.localhost"}
    TAURI_REWRITE_ORIGIN = b"http://localhost:8431"

    class TauriCorsMiddleware:
        """Rewrites Tauri origins for CORS and restores them in the response."""

        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            original_origin = None

            if scope["type"] in ("http", "websocket"):
                headers = scope.get("headers", [])
                for i, (name, value) in enumerate(headers):
                    if name == b"origin" and value in TAURI_ORIGINS:
                        original_origin = value
                        headers[i] = (b"origin", TAURI_REWRITE_ORIGIN)
                        break

            if original_origin is None:
                await self.app(scope, receive, send)
                return

            # Intercept outbound response headers to restore the original origin.
            # Replace ALL matching ACAO headers (CORSMiddleware + _add_cors_headers
            # may each set the header, producing duplicates).
            async def send_with_original_origin(message):
                if message["type"] == "http.response.start":
                    headers = message.get("headers", [])
                    for i, (name, value) in enumerate(headers):
                        if name == b"access-control-allow-origin" and value == TAURI_REWRITE_ORIGIN:
                            headers[i] = (b"access-control-allow-origin", original_origin)
                await send(message)

            await self.app(scope, receive, send_with_original_origin)

    app.add_middleware(TauriCorsMiddleware)

    app.add_middleware(GZipMiddleware, minimum_size=1000)

    app.state.host = host
    app.state.port = port

    # Include all API routers
    app.include_router(tools.router)
    app.include_router(websocket.router)
    app.include_router(workspaces.router)
    app.include_router(users.router)
    app.include_router(users_security_router, prefix="/api")
    app.include_router(conversations.router)
    app.include_router(shares.router)  # 工作区分享 Viewer 公开端点 (verify/只读/clone)
    app.include_router(system.router)
    app.include_router(skills.router)
    app.include_router(scheduled_tasks.router)
    app.include_router(global_scheduled_tasks.router)
    app.include_router(checklists.router)
    app.include_router(checkpoints.router)
    app.include_router(auth.router)
    app.include_router(knowledge_bases.router)
    app.include_router(knowledge_domains.router)
    app.include_router(market.router)
    # 业务路由（knowledge_uni/ip×5/compliance/deep_research×2/templates_sync）
    # 已随 6b 拆库迁至 davybot-biz，经下方 S3 entry points 装载（ip 链顺序由
    # dawei_biz.routers 聚合器保证）。
    app.include_router(privacy.router)
    app.include_router(container_runtime.router)
    app.include_router(sandbox_system.router)  # 沙箱系统 API (前端安全设置页面)
    app.include_router(runtime_api.router)  # 运行模式统一 API (/api/runtime-info)
    # saas 桶路由（license/admin_sandbox/internal_agent_stream + users remote）
    # 亦经 S3 聚合器装载。

    # ── 阶段六 6b（拆库方案 §18.3-S3）：业务路由经 entry points 装载 ──────────
    # 值 = dawei_biz.routers 聚合模块（暴露有序 routers 列表；social/ip/compliance/
    # deep_research/knowledge_uni/templates_sync 等业务路由全在此）。
    # 缺席 = 零路由（核心-only 形态）；装了 biz 但加载/注册失败 = FAST FAIL，
    # 不允许半 boot。
    from importlib.metadata import entry_points

    for _ep in entry_points(group="dawei.routers"):
        try:
            _mod = _ep.load()
            _biz_routers = list(getattr(_mod, "routers", None) or [])
            if not _biz_routers:
                _r = getattr(_mod, "router", None)
                if _r is None:
                    raise AttributeError(f"module {_ep.value} exposes no 'router(s)'")
                _biz_routers = [_r]
            for _r in _biz_routers:
                app.include_router(_r)
            logger.info(f"[S3] loaded {len(_biz_routers)} biz routers from entry '{_ep.name}'")
        except Exception as e:
            raise RuntimeError(f"[S3] biz router entry '{_ep.name}' ({_ep.value}) failed: {e}") from e

    # Register unified exception handlers
    register_exception_handlers(app)

    # Monitoring endpoints
    @app.get("/api/stats/llm")
    async def get_llm_stats():
        from dawei.llm_api.base_client import BaseClient
        return {"success": True, "data": BaseClient.get_global_stats()}

    @app.get("/api/stats/memory")
    async def get_memory_system_stats():
        from dawei.memory.memory_graph import MemoryGraph

        workspaces_root = get_dawei_home()
        if not workspaces_root.exists():
            return {"success": True, "data": {"enabled": True, "workspaces": [], "total_memories": 0}}

        total_memories = 0
        workspace_stats = []
        for workspace_dir in workspaces_root.iterdir():
            if not workspace_dir.is_dir():
                continue
            db_path = workspace_dir / ".dawei" / "memory.db"
            if db_path.exists():
                graph = MemoryGraph(str(db_path))
                stats = await graph.get_stats()
                total_memories += stats.total
                workspace_stats.append({
                    "workspace": workspace_dir.name,
                    "memories": stats.total,
                    "by_type": stats.by_type,
                })

        return {"success": True, "data": {"enabled": True, "workspaces": workspace_stats, "total_memories": total_memories}}

    # Mount frontend static files
    _mount_frontend_static(app)

    return app


def _mount_frontend_static(app: FastAPI) -> None:
    """Mount frontend static files with SPA fallback if they exist."""
    import dawei
    from starlette.responses import FileResponse

    package_dir = Path(dawei.__file__).parent
    frontend_path = package_dir / "frontend"

    if not frontend_path.exists():
        agent_dir = Path(__file__).parent.parent
        frontend_path = agent_dir / "frontend"

    if not frontend_path.exists():
        repo_root = Path(__file__).parent.parent.parent
        frontend_path = repo_root / "webui" / "dist"

    if not frontend_path.exists():
        print("[Dawei Server] Frontend not found. API-only mode.")
        return

    # Mount static assets (js, css, images, etc.) at /app-ui/assets/
    assets_path = frontend_path / "assets"
    if assets_path.exists():
        app.mount("/app-ui/assets", StaticFiles(directory=str(assets_path)), name="frontend-assets")

    # SPA catch-all: any /app-ui/{path} that isn't a real file → serve index.html
    index_html = frontend_path / "index.html"

    @app.get("/app-ui/{path:path}")
    async def spa_fallback(path: str):  # type: ignore[misc]
        # Try to serve a real file first (e.g. favicon.ico, manifest.json)
        file_path = frontend_path / path
        if path and file_path.is_file():
            return FileResponse(str(file_path))
        # SPA fallback: serve index.html for all routes
        return FileResponse(str(index_html))

    @app.get("/app-ui")
    async def spa_index():  # type: ignore[misc]
        return FileResponse(str(index_html))

    # Legacy redirects: /legalbot-ui/* -> /app-ui/*
    from starlette.responses import RedirectResponse

    @app.get("/legalbot-ui/{path:path}")
    async def legacy_spa_fallback(path: str):  # type: ignore[misc]
        return RedirectResponse(url=f"/app-ui/{path}", status_code=301)

    @app.get("/legalbot-ui")
    async def legacy_spa_index():  # type: ignore[misc]
        return RedirectResponse(url="/app-ui", status_code=301)

    # Legacy assets redirect
    if assets_path.exists():
        @app.get("/legalbot-ui/assets/{path:path}")
        async def legacy_assets(path: str):  # type: ignore[misc]
            return RedirectResponse(url=f"/app-ui/assets/{path}", status_code=301)

    print(f"[Dawei Server] Frontend mounted from: {frontend_path}")
