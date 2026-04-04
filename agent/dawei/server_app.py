# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei Server - AI Agent API Platform

Main FastAPI application with WebSocket support for real-time agent communication.
This module is used by CLI to create the FastAPI application.
"""

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
            if _shared_utf8_stream is None:
                if hasattr(sys.stderr, "buffer"):
                    binary_stream = sys.stderr.buffer
                elif hasattr(sys.stderr, "raw"):
                    binary_stream = sys.stderr.raw
                else:
                    binary_stream = sys.stderr

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
        self.stream.write(msg + "\n")
        self.flush()


# Configure root logger
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[UTF8StreamHandler()],
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from dawei.api import (
    auth,
    checkpoints,
    conversations,
    knowledge_bases,
    knowledge_domains,
    market,
    privacy,
    scheduled_tasks,
    container_runtime,
    skills,
    system,
    tools,
    websocket,
    workspaces,
    users,
)
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
        "web_ui": f"http://{accessible_host}:{port}/",
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

    # Create global DAWEI_HOME directories
    dawei_home = get_dawei_home()
    for dir_name in ("checkpoints", "sessions", "logs", "configs"):
        (dawei_home / dir_name).mkdir(parents=True, exist_ok=True)
    print(f"[Dawei Server] Global directories created at {dawei_home}")

    # Initialize WebSocket server
    await websocket_server.initialize()

    # Validate .dawei directory structure
    from dawei.workspace.dawei_structure_validator import validate_dawei_on_startup
    validate_dawei_on_startup()
    print("[Dawei Server] .dawei directory structure validation passed")

    # Record server startup parameters
    host = getattr(app.state, "host", "0.0.0.0")
    port = getattr(app.state, "port", 8465)
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

    # Initialize Evolution Scheduler
    from dawei.evolution import evolution_scheduler
    await evolution_scheduler.start()
    print("[Dawei Server] Evolution scheduler started")

    # Initialize Remote Ping Service
    from dawei.remote import start_ping_service
    await start_ping_service()
    print("[Dawei Server] Remote ping service started")

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

    from dawei.remote import stop_ping_service
    await _safe_shutdown("Remote ping service", stop_ping_service())

    if shutdown_errors:
        logger.warning("Shutdown encountered %d error(s): %s", len(shutdown_errors), shutdown_errors)


def create_app(host: str = "0.0.0.0", port: int = 8465) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Dawei Agent API - Orchestrator Mode",
        description="AI-powered agent platform with multi-agent orchestration",
        version="2.0.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
            "http://192.168.1.252:3000",
            "*",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.add_middleware(GZipMiddleware, minimum_size=1000)

    app.state.host = host
    app.state.port = port

    # Include all API routers
    app.include_router(tools.router)
    app.include_router(websocket.router)
    app.include_router(workspaces.router)
    app.include_router(users.router)
    app.include_router(conversations.router)
    app.include_router(system.router)
    app.include_router(skills.router)
    app.include_router(scheduled_tasks.router)
    app.include_router(checkpoints.router)
    app.include_router(auth.router)
    app.include_router(knowledge_bases.router)
    app.include_router(knowledge_domains.router)
    app.include_router(market.router)
    app.include_router(privacy.router)
    app.include_router(container_runtime.router)

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

        workspaces_root = Path(os.getenv("DAWEI_HOME", "~/.dawei")).expanduser()
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

    @app.get("/api/metrics")
    async def get_prometheus_metrics():
        from dawei.llm_api.base_client import BaseClient
        from fastapi.responses import Response
        return Response(content=BaseClient.get_prometheus_metrics(), media_type="text/plain")

    # Mount frontend static files
    _mount_frontend_static(app)

    return app


def _mount_frontend_static(app: FastAPI) -> None:
    """Mount frontend static files if they exist."""
    import dawei

    package_dir = Path(dawei.__file__).parent
    frontend_path = package_dir / "frontend"

    if not frontend_path.exists():
        agent_dir = Path(__file__).parent.parent
        frontend_path = agent_dir / "frontend"

    if not frontend_path.exists():
        repo_root = Path(__file__).parent.parent.parent
        frontend_path = repo_root / "webui" / "dist"

    if frontend_path.exists():
        app.mount("/app", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
        print(f"[Dawei Server] Frontend mounted from: {frontend_path}")
    else:
        print("[Dawei Server] Frontend not found. API-only mode.")
