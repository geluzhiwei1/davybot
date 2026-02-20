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
from datetime import UTC, datetime, timezone
from pathlib import Path

# 强制 UTF-8 编码（解决 Windows 控制台编码问题）
if sys.platform == "win32":
    # Helper function to get the underlying binary stream
    def _get_binary_stream(stream):
        if hasattr(stream, "buffer"):
            return stream.buffer
        elif hasattr(stream, "raw"):
            return stream.raw
        else:
            return stream

    # Wrap stdout if needed
    if hasattr(sys.stdout, "buffer") or hasattr(sys.stdout, "raw"):
        try:
            sys.stdout = io.TextIOWrapper(_get_binary_stream(sys.stdout), encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass  # Use default if wrapping fails

    # Wrap stderr if needed
    if hasattr(sys.stderr, "buffer") or hasattr(sys.stderr, "raw"):
        try:
            sys.stderr = io.TextIOWrapper(_get_binary_stream(sys.stderr), encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass  # Use default if wrapping fails

# 共享的 UTF-8 流（避免重复创建文件描述符）
_shared_utf8_stream = None


class UTF8StreamHandler(logging.StreamHandler):
    """自定义 StreamHandler，强制使用 UTF-8 编码写入控制台

    适用于 Windows 控制台编码为 GBK 的情况。
    """

    def __init__(self):
        super().__init__()
        self._setup_utf8_stream()

    def _setup_utf8_stream(self):
        """设置 UTF-8 输出流"""
        global _shared_utf8_stream

        if sys.platform == "win32":
            if _shared_utf8_stream is None:
                # Get the underlying binary stream (handle both .buffer and .raw attributes)
                if hasattr(sys.stderr, "buffer"):
                    binary_stream = sys.stderr.buffer
                elif hasattr(sys.stderr, "raw"):
                    binary_stream = sys.stderr.raw
                else:
                    # Fallback: use sys.stderr directly
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
        """写入日志记录，强制使用 UTF-8 编码"""
        try:
            msg = self.format(record)
            self.stream.write(msg + "\n")
            self.flush()
        except (OSError, ValueError):
            self.handleError(record)
        except Exception as e:
            logging.getLogger(__name__).error(f"Unexpected error in UTF8StreamHandler.emit: {e}")
            self.handleError(record)
            raise


# Configure root logger
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[UTF8StreamHandler()],
)

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

# Import API routers
from dawei.api import conversations, skills, system, tools, websocket, workspaces
from dawei.api.exception_handlers import register_exception_handlers
from dawei.websocket.handlers.chat import ConnectHandler
from dawei.websocket.ws_server import websocket_server
from dawei.api import market
from dawei.api import privacy

# Load environment variables
cwd_env = Path(".env")

if cwd_env.exists():
    load_dotenv(cwd_env, override=True)


def get_workspaces_root() -> Path:
    """Get the DAWEI_HOME directory path.

    Returns:
        Path: DAWEI_HOME directory path (default: ~/.dawei)
    """
    dawei_home = os.getenv("DAWEI_HOME")
    if dawei_home:
        return Path(dawei_home)
    return Path.home() / ".dawei"


def record_server_start(host: str, port: int) -> None:
    """Record server startup parameters to DAWEI_HOME/server.start file."""
    try:
        dawei_home = get_workspaces_root()
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

        print(f"[Dawei Server] ✓ Server start info recorded to: {server_start_file}")
    except Exception as e:
        print(f"[Dawei Server] ⚠ Failed to record server start info: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown events."""
    # Startup
    await websocket_server.initialize()

    # Validate .dawei directory structure
    try:
        from dawei.workspace.dawei_structure_validator import validate_dawei_on_startup
        validate_dawei_on_startup()
        print("[Dawei Server] ✓ .dawei directory structure validation passed")
    except ImportError as e:
        print(f"[Dawei Server] ⚠ .dawei validation module not available: {e}")
    except Exception as e:
        print(f"[Dawei Server] ❌ .dawei directory structure validation failed: {e}")

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
    try:
        from dawei.llm_api.base_client import BaseClient
        await BaseClient.initialize_global_components()
        print("[Dawei Server] ✓ LLM API protection layer initialized")
    except ImportError as e:
        print(f"[Dawei Server] ⚠ LLM API protection module not available: {e}")
    except Exception as e:
        print(f"[Dawei Server] ⚠ Failed to initialize LLM API protection: {e}")

    # Initialize DaweiMem memory system
    try:
        from dawei.memory.database import init_memory_database
        print("[Dawei Server] ✓ DaweiMem memory system is enabled")

        workspaces_root = Path(os.getenv("WORKSPACES_ROOT", "./workspaces"))

        if workspaces_root.exists():
            initialized_count = 0
            for workspace_dir in workspaces_root.iterdir():
                if workspace_dir.is_dir():
                    db_path = workspace_dir / ".dawei" / "memory.db"
                    try:
                        if init_memory_database(str(db_path)):
                            initialized_count += 1
                    except Exception as e:
                        print(
                            f"[Dawei Server] ⚠ Failed to initialize memory DB for {workspace_dir.name}: {e}",
                        )

            print(
                f"[Dawei Server] ✓ Memory system initialized for {initialized_count} workspace(s)",
            )
        else:
            print(
                "[Dawei Server] ℹ Workspaces root not found, memory DBs will be created on demand",
            )
    except ImportError as e:
        print(f"[Dawei Server] ⚠ Memory system module not available: {e}")
    except Exception as e:
        print(f"[Dawei Server] ⚠ Failed to initialize memory system: {e}")

    # Initialize Scheduler Manager
    try:
        from dawei.tools.scheduler import scheduler_manager
        await scheduler_manager.initialize()
        print("[Dawei Server] ✓ Scheduler manager initialized")
    except ImportError as e:
        print(f"[Dawei Server] ⚠ Scheduler module not available: {e}")
    except Exception as e:
        print(f"[Dawei Server] ⚠ Failed to initialize scheduler: {e}")

    yield

    # Shutdown LLM API protection layer
    try:
        from dawei.llm_api.base_client import BaseClient
        await BaseClient.shutdown_global_components()
        print("[Dawei Server] ✓ LLM API protection layer shutdown")
    except ImportError as e:
        print(f"[Dawei Server] ⚠ LLM API protection module not available during shutdown: {e}")
    except Exception as e:
        print(f"[Dawei Server] ⚠ Failed to shutdown LLM API protection: {e}")

    # Shutdown scheduler manager
    try:
        from dawei.tools.scheduler import scheduler_manager
        await scheduler_manager.shutdown()
        print("[Dawei Server] ✓ Scheduler manager shutdown")
    except ImportError as e:
        print(f"[Dawei Server] ⚠ Scheduler module not available during shutdown: {e}")
    except Exception as e:
        print(f"[Dawei Server] ⚠ Failed to shutdown scheduler: {e}")


def create_app(host: str = "0.0.0.0", port: int = 8465) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        host: Server host address
        port: Server port number

    Returns:
        FastAPI: Configured application instance
    """
    app = FastAPI(
        title="Dawei Agent API - Orchestrator Mode",
        description="AI-powered agent platform with multi-agent orchestration",
        version="2.0.0",
        lifespan=lifespan,
    )

    # Add CORS middleware
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

    # Add GZip middleware for response compression
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Store server configuration in app state for lifespan access
    app.state.host = host
    app.state.port = port

    # Include all API routers
    app.include_router(tools.router)
    app.include_router(websocket.router)
    app.include_router(workspaces.router)
    app.include_router(conversations.router)
    app.include_router(system.router)
    app.include_router(skills.router)

    # Register unified exception handlers
    register_exception_handlers(app)

    # Market API
    app.include_router(market.router)
    print("[Dawei Server] ✓ Market API router registered")

    # Privacy Configuration API
    app.include_router(privacy.router)
    print("[Dawei Server] ✓ Privacy Configuration API router registered")

    # Add monitoring endpoints
    @app.get("/api/stats/llm")
    async def get_llm_stats():
        """Get LLM API protection layer statistics"""
        try:
            from dawei.llm_api.base_client import BaseClient
            stats = BaseClient.get_global_stats()
            return {"success": True, "data": stats}
        except ImportError as e:
            return {"success": False, "error": f"LLM API protection module not available: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/stats/memory")
    async def get_memory_system_stats():
        """Get DaweiMem memory system statistics"""
        try:
            workspaces_root = Path(os.getenv("WORKSPACES_ROOT", "./workspaces"))

            if not workspaces_root.exists():
                return {
                    "success": True,
                    "data": {
                        "enabled": True,
                        "workspaces": [],
                        "total_memories": 0,
                        "message": "No workspaces found",
                    },
                }

            from dawei.memory.memory_graph import MemoryGraph

            total_memories = 0
            workspace_stats = []

            for workspace_dir in workspaces_root.iterdir():
                if workspace_dir.is_dir():
                    db_path = workspace_dir / ".dawei" / "memory.db"
                    if db_path.exists():
                        try:
                            graph = MemoryGraph(str(db_path))
                            stats = await graph.get_stats()
                            total_memories += stats.total
                            workspace_stats.append(
                                {
                                    "workspace": workspace_dir.name,
                                    "memories": stats.total,
                                    "by_type": stats.by_type,
                                },
                            )
                        except Exception as e:
                            print(
                                f"[Dawei Server] Warning: Failed to get stats for {workspace_dir.name}: {e}",
                            )

            return {
                "success": True,
                "data": {
                    "enabled": True,
                    "workspaces": workspace_stats,
                    "total_memories": total_memories,
                },
            }
        except ImportError as e:
            return {"success": False, "error": f"Memory system module not available: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/metrics")
    async def get_prometheus_metrics():
        """Get Prometheus metrics"""
        try:
            from dawei.llm_api.base_client import BaseClient
            metrics = BaseClient.get_prometheus_metrics()
            from fastapi.responses import Response
            return Response(content=metrics, media_type="text/plain")
        except ImportError as e:
            return Response(
                content=f"# Error generating metrics: LLM API protection module not available: {e}",
                media_type="text/plain",
            )
        except Exception as e:
            return Response(content=f"# Error generating metrics: {e}", media_type="text/plain")

    # Mount static files for frontend
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
        app.mount(
            "/app",
            StaticFiles(directory=str(frontend_path), html=True),
            name="frontend",
        )
        print(f"[Dawei Server] ✓ Frontend mounted from: {frontend_path}")
    else:
        print("[Dawei Server] ⚠ Frontend not found. API-only mode.")
