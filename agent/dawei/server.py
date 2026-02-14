# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei Server - AI Agent API Platform

Main FastAPI application with WebSocket support for real-time agent communication.
"""

import argparse
import io
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

# 强制 UTF-8 编码（解决 Windows 控制台编码问题）
if sys.platform == "win32":
    # Only wrap if stdout/stderr have buffer attribute (avoid double-wrapping)
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Configure root logger to use UTF-8 stream before any other imports
# This ensures all loggers (including uvicorn's) use UTF-8 encoding
import logging

# Define UTF8StreamHandler here for server use (also defined in dawei.logg.logging)
# 共享的 UTF-8 流（避免重复创建文件描述符）
_shared_utf8_stream = None


class UTF8StreamHandler(logging.StreamHandler):
    """自定义 StreamHandler，强制使用 UTF-8 编码写入控制台

    适用于 Windows 控制台编码为 GBK 的情况。

    关键改进：使用共享的 UTF-8 流，避免多次调用 os.dup() 导致文件描述符混乱。
    """

    def __init__(self):
        super().__init__()
        self._setup_utf8_stream()

    def _setup_utf8_stream(self):
        """设置 UTF-8 输出流"""
        global _shared_utf8_stream

        if sys.platform == "win32":
            # Windows: 使用共享的 UTF-8 流（避免重复 dup）
            if _shared_utf8_stream is None:
                import io

                # 创建一个直接写入 stderr 的 UTF-8 文本流
                _shared_utf8_stream = io.TextIOWrapper(
                    sys.stderr.buffer,
                    encoding="utf-8",
                    errors="replace",
                    line_buffering=True,
                )
            self.stream = _shared_utf8_stream
        else:
            # 非 Windows: 使用 stderr
            self.stream = sys.stderr

    def emit(self, record):
        """写入日志记录，强制使用 UTF-8 编码"""
        try:
            msg = self.format(record)
            # 统一使用字符串写入（流已经是 UTF-8 编码的文本流）
            self.stream.write(msg + "\n")
            self.flush()
        except (OSError, IOError, ValueError) as e:
            # Fast Fail: 只捕获预期的I/O错误，让其他错误快速失败
            self.handleError(record)
        except Exception as e:
            # Fast Fail: 记录未预期的错误但仍快速失败
            # 添加上下文信息以便调试
            import logging
            logging.getLogger(__name__).error(
                f"Unexpected error in UTF8StreamHandler.emit: {e}",
                exc_info=True,
                extra={"record": record}
            )
            self.handleError(record)
            raise  # 重新抛出未预期的异常


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[UTF8StreamHandler()],
)

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

# Import API routers
from .api import conversations, skills, system, tools, websocket, workspaces
from .api.exception_handlers import register_exception_handlers
from .websocket.handlers.chat import ConnectHandler
from .websocket.ws_server import websocket_server

try:
    from .api import market

    MARKET_AVAILABLE = True
except ImportError:
    market = None
    MARKET_AVAILABLE = False

# Load environment variables
load_dotenv()


def get_dawei_home() -> Path:
    """Get the DAWEI_HOME directory path.

    Returns:
        Path: DAWEI_HOME directory path (default: ~/.dawei)

    """
    dawei_home = os.getenv("DAWEI_HOME")
    if dawei_home:
        return Path(dawei_home)
    # Default to user's home directory /.dawei
    return Path.home() / ".dawei"


def record_server_start(host: str, port: int) -> None:
    """Record server startup parameters to DAWEI_HOME/server.start file.

    Args:
        host: Server host address
        port: Server port number

    """
    try:
        dawei_home = get_dawei_home()
        dawei_home.mkdir(parents=True, exist_ok=True)

        server_start_file = dawei_home / "server.start"

        # Prepare server start data
        # For "0.0.0.0" host, use "localhost" for accessible URLs
        accessible_host = "localhost" if host == "0.0.0.0" else host

        start_data = {
            "host": host,
            "port": port,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "web_ui": f"http://{accessible_host}:{port}/",
            "api_docs": f"http://{accessible_host}:{port}/docs",
            "websocket": f"ws://{accessible_host}:{port}/ws",
        }

        # Write to file
        with server_start_file.open("w", encoding="utf-8") as f:
            json.dump(start_data, f, indent=2, ensure_ascii=False)

        print(f"[Dawei Server] ✓ Server start info recorded to: {server_start_file}")
    except Exception as e:
        print(f"[Dawei Server] ⚠ Failed to record server start info: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown events.

    Initializes WebSocket server, registers message handlers, and handles cleanup.
    """
    # Startup
    await websocket_server.initialize()

    # ✅ Validate .dawei directory structure
    try:
        from .workspace.dawei_structure_validator import validate_dawei_on_startup

        validate_dawei_on_startup()
        print("[Dawei Server] ✓ .dawei directory structure validation passed")
    except ImportError as e:
        print(f"[Dawei Server] ⚠ .dawei validation module not available: {e}")
    except Exception as e:
        # Fast Fail: Critical validation error prevents server startup
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

    # ✅ Initialize LLM API protection layer
    try:
        from dawei.llm_api.base_client import BaseClient

        await BaseClient.initialize_global_components()
        print("[Dawei Server] ✓ LLM API protection layer initialized")
    except ImportError as e:
        print(f"[Dawei Server] ⚠ LLM API protection module not available: {e}")
    except Exception as e:
        print(f"[Dawei Server] ⚠ Failed to initialize LLM API protection: {e}")

    # ✅ Initialize DaweiMem memory system
    try:
        import os

        from dawei.memory.database import init_memory_database

        # Memory system is always enabled
        print("[Dawei Server] ✓ DaweiMem memory system is enabled")

        # Initialize memory database for each workspace
        from pathlib import Path

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

    # ✅ Initialize Scheduler Manager
    try:
        from dawei.tools.scheduler import scheduler_manager

        await scheduler_manager.initialize()
        print("[Dawei Server] ✓ Scheduler manager initialized")
    except ImportError as e:
        print(f"[Dawei Server] ⚠ Scheduler module not available: {e}")
    except Exception as e:
        print(f"[Dawei Server] ⚠ Failed to initialize scheduler: {e}")

    yield

    # Shutdown
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

    # Shutdown - cleanup logic can be added here if needed


def create_app(host: str = "0.0.0.0", port: int = 8465) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        host: Server host address
        port: Server port number

    Returns:
        FastAPI: Configured application instance

    """
    # 创建主应用（带 lifespan）
    app = FastAPI(
        title="Dawei Agent API - Orchestrator Mode",
        description="AI-powered agent platform with multi-agent orchestration",
        version="2.0.0",
        lifespan=lifespan,  # 直接应用 lifespan
    )

    # 注：不再使用子应用挂载，所有路由直接挂载到根路径

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

    # Add GZip middleware for response compression (compresses responses >= 1KB)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Store server configuration in app state for lifespan access
    app.state.host = host
    app.state.port = port

    # Include all API routers
    app.include_router(tools.router)
    app.include_router(websocket.router)
    app.include_router(workspaces.router)  # Includes memory router via workspaces/__init__.py
    app.include_router(conversations.router)
    app.include_router(system.router)
    app.include_router(skills.router)

    # Register unified exception handlers (must be after routers)
    register_exception_handlers(app)

    # Debug market availability
    print(
        f"[Dawei Server] MARKET_AVAILABLE: {MARKET_AVAILABLE}, market module: {market is not None}",
    )

    # Market API (optional - if available)
    if MARKET_AVAILABLE and market is not None:
        app.include_router(market.router)
        print("[Dawei Server] ✓ Market API router registered")
    else:
        print("[Dawei Server] ⚠ Market API not available (optional feature)")

    # ✅ Add monitoring endpoint for LLM API protection layer
    @app.get("/api/stats/llm")
    async def get_llm_stats():
        """Get LLM API protection layer statistics"""
        try:
            from dawei.llm_api.base_client import BaseClient

            stats = BaseClient.get_global_stats()
            return {"success": True, "data": stats}
        except ImportError as e:
            return {
                "success": False,
                "error": f"LLM API protection module not available: {e}",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/stats/memory")
    async def get_memory_system_stats():
        """Get DaweiMem memory system statistics"""
        try:
            import os
            from pathlib import Path

            # Memory system is always enabled
            # Get statistics from all workspace memory databases
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
            return {
                "success": False,
                "error": f"Memory system module not available: {e}",
            }
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

    # Mount static files for frontend (if available)
    _mount_frontend_static(app)

    return app


def _mount_frontend_static(app: FastAPI) -> None:
    """Mount frontend static files if they exist.

    Args:
        app: FastAPI application instance

    """
    # Try package frontend first, fallback to local development
    frontend_path = Path(__file__).parent / "dawei" / "frontend"
    if not frontend_path.exists():
        frontend_path = Path(__file__).parent.parent.parent / "apps" / "web" / "dist"

    if frontend_path.exists():
        app.mount(
            "/app",
            StaticFiles(directory=str(frontend_path), html=True),
            name="frontend",
        )
        print(f"[Dawei Server] Serving frontend from: {frontend_path}")
    else:
        print("[Dawei Server] Warning: Frontend not found. API-only mode.")


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments for the server.

    Returns:
        Parsed arguments namespace

    """
    parser = argparse.ArgumentParser(
        description="Dawei Server - AI Agent API Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind the server to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8465,
        help="Port to bind the server to (default: 8465)",
    )
    parser.add_argument(
        "--reload",
        "-r",
        action="store_true",
        help="Enable auto-reload for development",
    )

    return parser.parse_args()


def main() -> None:
    """Entry point for running the Dawei server.

    Parses command line arguments and starts the uvicorn server.
    """
    args = parse_arguments()

    # Check if port is in use
    from .core.port_manager import (
        find_process_using_port,
        is_port_in_use,
        kill_process_using_port,
    )

    if is_port_in_use(args.port, args.host):
        print(f"⚠️  Port {args.port} is already in use!")

        process_info = find_process_using_port(args.port)
        if process_info:
            pid, process_name = process_info
            print(f"   Process: {process_name} (PID: {pid})")

            # Ask user if they want to kill the process
            response = input("\nDo you want to kill the process and continue? [y/N]: ").strip().lower()
            if response in ["y", "yes"]:
                if kill_process_using_port(args.port, force=True):
                    print("✅ Process killed. Starting server...")
                else:
                    print("❌ Failed to kill process. Please check manually.")
                    print(
                        (f"   You can manually kill the process using: kill {pid}" if sys.platform != "win32" else f"   You can manually kill the process using: taskkill /F /PID {pid}"),
                    )
                    sys.exit(1)
            else:
                print("❌ Aborted. Please free up the port and try again.")
                sys.exit(1)
        else:
            print("❌ Could not identify the process using the port.")
            print("   Please check manually and free up the port.")
            sys.exit(1)

    print(f"Starting Dawei Server on {args.host}:{args.port}")
    print(f"API Documentation: http://{args.host}:{args.port}/docs")
    print(f"WebSocket Endpoint: ws://{args.host}:{args.port}/ws")

    # Create app with host and port configuration
    app_instance = create_app(host=args.host, port=args.port)

    uvicorn.run(app_instance, host=args.host, port=args.port, reload=args.reload)


# Create the application instance
app = create_app()


# Allow running directly with `python -m dawei.server`
if __name__ == "__main__":
    main()
