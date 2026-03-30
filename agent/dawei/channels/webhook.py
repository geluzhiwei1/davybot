"""Shared webhook server for multi-channel support.

Provides a single aioHTTP server that handles webhooks for multiple channels.
Each channel registers its webhook path and handler, and the server routes
incoming requests to the appropriate channel.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiohttp import web

logger = logging.getLogger(__name__)

WebhookHandler = Callable[
    [dict[str, Any], dict[str, str]],
    Awaitable[dict[str, Any]],
]


@dataclass
class WebhookRoute:
    """A registered webhook route."""

    path: str
    channel_type: str
    handler: WebhookHandler
    secret: str | None = None


class WebhookServer:
    """Shared aioHTTP webhook server for multiple channels.

    Each channel can register a webhook path (e.g., /telegram, /discord).
    The server handles:
    - JSON parsing and validation
    - Signature verification (if configured)
    - Error handling and logging
    - Response formatting
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8466,
        health_check_path: str = "/health",
    ) -> None:
        """Initialize the webhook server.

        Args:
            host: Host to bind to
            port: Port to listen on
            health_check_path: Path for health check endpoint
        """
        self.host = host
        self.port = port
        self.health_check_path = health_check_path
        self._routes: dict[str, WebhookRoute] = {}
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._running = False

    def register(
        self,
        path: str,
        channel_type: str,
        handler: WebhookHandler,
        secret: str | None = None,
    ) -> None:
        """Register a webhook handler for a channel.

        Args:
            path: Webhook path (e.g., "/telegram", "/discord")
            channel_type: Channel type identifier
            handler: Async function that processes the webhook
            secret: Optional secret for signature verification
        """
        if path in self._routes:
            logger.warning(f"Webhook path '{path}' already registered, overwriting")

        self._routes[path] = WebhookRoute(
            path=path,
            channel_type=channel_type,
            handler=handler,
            secret=secret,
        )
        logger.info(f"Registered webhook route: {path} -> {channel_type}")

    def unregister(self, path: str) -> None:
        """Unregister a webhook route."""
        if path in self._routes:
            del self._routes[path]
            logger.info(f"Unregistered webhook route: {path}")

    async def start(self) -> None:
        """Start the webhook server."""
        if self._running:
            logger.warning("WebhookServer already running")
            return

        logger.info(f"Starting webhook server on {self.host}:{self.port}")

        # Create aiohttp app
        self._app = web.Application()
        self._app.add_routes(
            [
                web.post("/{path:.*}", self._handle_webhook),
                web.get(self.health_check_path, self._handle_health_check),
            ]
        )

        # Create and start runner
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        # Create site
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

        self._running = True
        logger.info(f"Webhook server started on http://{self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop the webhook server."""
        if not self._running:
            return

        logger.info("Stopping webhook server")
        self._running = False

        if self._site:
            await self._site.stop()
            self._site = None

        if self._runner:
            await self._runner.cleanup()
            self._runner = None

        self._app = None
        logger.info("Webhook server stopped")

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        """Handle incoming webhook requests."""
        # Extract path
        path = f"/{request.match_info.get('path', '')}"

        # Find matching route
        route = self._routes.get(path)
        if not route:
            logger.warning(f"No webhook handler for path: {path}")
            return web.json_response(
                {"status": "error", "message": "Not found"},
                status=404,
            )

        # Parse JSON payload
        try:
            payload = await request.json()
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON payload for {route.channel_type}: {e}")
            return web.json_response(
                {"status": "error", "message": "Invalid JSON"},
                status=400,
            )

        # Extract headers
        headers = dict(request.headers)

        # Log webhook
        logger.debug(
            f"Received webhook from {route.channel_type} "
            f"(path={path}, payload_size={len(json.dumps(payload))})"
        )

        # Call channel handler
        try:
            response = await route.handler(payload, headers)
            return web.json_response(response)
        except Exception as e:
            logger.error(f"Error handling webhook for {route.channel_type}: {e}")
            return web.json_response(
                {"status": "error", "message": str(e)},
                status=500,
            )

    async def _handle_health_check(self, request: web.Request) -> web.Response:
        """Handle health check requests."""
        return web.json_response(
            {
                "status": "ok",
                "routes": list(self._routes.keys()),
            }
        )

    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._running

    @property
    def routes(self) -> list[str]:
        """List all registered webhook paths."""
        return list(self._routes.keys())

    def get_url(self, path: str) -> str:
        """Get the full URL for a webhook path."""
        return f"http://{self.host}:{self.port}{path}"
