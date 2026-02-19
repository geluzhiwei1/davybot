# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""CLI wrapper for davybot-market-cli integration.

Provides a Python interface using the DavybotMarketClient SDK
for interacting with the market API.

IMPORTANT: Requires davybot-market-cli to be installed.
If the SDK is not available, operations will fail immediately (fast fail).
"""

import logging
from pathlib import Path
from typing import Any

from .models import CliExecutionError

logger = logging.getLogger(__name__)


class CliNotFoundError(Exception):
    """Raised when davybot-market-cli SDK is not found."""


# Try to import the SDK client - fail immediately if not available
from davybot_market_cli.client import DavybotMarketClient
from davybot_market_cli.exceptions import (
    AuthenticationError,
    NotFoundError,
    ValidationError,
    APIError,
)

SDK_AVAILABLE = True


class CliWrapper:
    """Wrapper for davybot-market-cli SDK.

    Uses DavybotMarketClient directly instead of CLI subprocess.
    Falls back to CLI if SDK is not available.

    IMPORTANT: Requires davybot-market-cli to be installed. Will fail fast if not found.
    """

    # Default Market API URL
    DEFAULT_API_URL = "http://www.davybot.com/market/api/v1"

    # Request timeout in seconds
    DEFAULT_TIMEOUT = 60

    def __init__(
        self,
        api_url: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Initialize CLI wrapper.

        Args:
            api_url: Optional Market API URL (defaults to DEFAULT_API_URL)
            timeout: Request timeout in seconds

        Raises:
            ImportError: If SDK cannot be imported (fails at module load)

        """
        self.api_url = api_url or self.DEFAULT_API_URL
        self.timeout = timeout
        self._client: DavybotMarketClient | None = None

    def _get_client(self) -> DavybotMarketClient:
        """Get or create SDK client.

        Note: The client needs to be used as a context manager,
        so we create a new instance each time.
        """
        return DavybotMarketClient(
            base_url=self.api_url,
            timeout=self.timeout,
        )

    def _handle_error(self, error: Exception, context: str) -> None:
        """Handle SDK errors and convert to CliExecutionError."""
        error_msg = str(error)

        if isinstance(error, NotFoundError):
            raise CliExecutionError(context, 404, error_msg)
        elif isinstance(error, AuthenticationError):
            raise CliExecutionError(context, 401, error_msg)
        elif isinstance(error, ValidationError):
            raise CliExecutionError(context, 422, error_msg)
        elif isinstance(error, APIError):
            raise CliExecutionError(context, 500, error_msg)
        else:
            raise CliExecutionError(context, 500, error_msg)

    # ========================================================================
    # Health Check
    # ========================================================================

    def health(self) -> dict[str, Any]:
        """Check Market API health status.

        Returns:
            Health status dictionary

        """
        try:
            with self._get_client() as client:
                return client.health()
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "error", "error": str(e)}

    # ========================================================================
    # Search
    # ========================================================================

    def search(self, query: str, resource_type: str = "skill", limit: int = 20) -> dict[str, Any]:
        """Search for resources in the market.

        Args:
            query: Search query string
            resource_type: Resource type (skill, agent, plugin)
            limit: Maximum number of results

        Returns:
            Dictionary with search results

        Raises:
            CliExecutionError: If search fails

        """
        try:
            with self._get_client() as client:
                result = client.search(query, resource_type=resource_type, limit=limit)
                return result
        except Exception as e:
            self._handle_error(e, f"search {query}")

    def search_skills(self, query: str, limit: int = 20) -> dict[str, Any]:
        """Search for skills."""
        return self.search(query, "skill", limit)

    def search_agents(self, query: str, limit: int = 20) -> dict[str, Any]:
        """Search for agents."""
        return self.search(query, "agent", limit)

    # ========================================================================
    # List Resources
    # ========================================================================

    def list_resources(self, resource_type: str, limit: int = 50, skip: int = 0) -> dict[str, Any]:
        """List all resources of a type.

        Args:
            resource_type: Resource type (skill, agent, plugin)
            limit: Maximum number of results
            skip: Number of results to skip (pagination)

        Returns:
            Dictionary with resource list

        Raises:
            CliExecutionError: If list fails

        """
        try:
            with self._get_client() as client:
                if resource_type == "skill":
                    return client.list_skills(skip=skip, limit=limit)
                elif resource_type == "agent":
                    return client.list_agents(skip=skip, limit=limit)
                elif resource_type == "plugin":
                    # Plugin is not directly supported, try as mcp
                    try:
                        return client.list_mcp_servers(skip=skip, limit=limit)
                    except NotFoundError:
                        # MCP servers not supported in market, return empty
                        return {"resources": [], "total": 0, "success": True}
                else:
                    raise CliExecutionError(
                        f"list_{resource_type}",
                        400,
                        f"Unsupported resource type: {resource_type}",
                    )
        except NotFoundError:
            # Resource type not found in market, return empty result
            return {"resources": [], "total": 0, "success": True}
        except Exception as e:
            self._handle_error(e, f"list {resource_type}")

    def list_skills(self, limit: int = 50, skip: int = 0) -> dict[str, Any]:
        """List all skills."""
        return self.list_resources("skill", limit=limit, skip=skip)

    def list_agents(self, limit: int = 50, skip: int = 0) -> dict[str, Any]:
        """List all agents."""
        return self.list_resources("agent", limit=limit, skip=skip)

    def list_plugins(self, limit: int = 50, skip: int = 0) -> dict[str, Any]:
        """List all plugins."""
        return self.list_resources("plugin", limit=limit, skip=skip)

    # ========================================================================
    # Resource Info
    # ========================================================================

    def info(self, resource_type: str, identifier: str) -> dict[str, Any]:
        """Get detailed information about a resource.

        Args:
            resource_type: Resource type (skill, agent, plugin)
            identifier: Resource ID or name

        Returns:
            Dictionary with resource information

        Raises:
            CliExecutionError: If info retrieval fails

        """
        try:
            with self._get_client() as client:
                if resource_type == "skill":
                    return client.get_skill(identifier)
                elif resource_type == "agent":
                    return client.get_agent(identifier)
                elif resource_type == "plugin":
                    return client.get_mcp_server(identifier)
                else:
                    raise CliExecutionError(
                        f"info {identifier}",
                        400,
                        f"Unsupported resource type: {resource_type}",
                    )
        except NotFoundError:
            return {"success": False, "error": f"Resource '{identifier}' not found"}
        except Exception as e:
            self._handle_error(e, f"info {identifier}")

    # ========================================================================
    # Install
    # ========================================================================

    def install(
        self,
        resource_uri: str,
        output_dir: str,
        format: str = "zip",
    ) -> dict[str, Any]:
        """Install a resource (skill, agent, etc.).

        Args:
            resource_uri: Resource URI (e.g., skill://github.com/user/repo/skill-name)
            output_dir: Output directory
            format: Download format (zip, python)

        Returns:
            Dictionary with installation result

        Raises:
            CliExecutionError: If installation fails

        """
        # Parse resource URI to get type and ID
        # Format: skill://id or agent://id
        if "://" not in resource_uri:
            raise CliExecutionError(
                "install",
                400,
                f"Invalid resource URI format: {resource_uri}. Use skill://<id> or agent://<id>",
            )

        resource_type, resource_id = resource_uri.split("://", 1)

        try:
            with self._get_client() as client:
                output_path = Path(output_dir)

                # Download the resource
                downloaded_path = client.download(
                    resource_type=resource_type,
                    resource_id=resource_id,
                    output_path=output_path,
                    format=format,
                )

                return {
                    "success": True,
                    "stdout": f"Downloaded to: {downloaded_path}",
                    "stderr": "",
                    "returncode": 0,
                }
        except NotFoundError:
            raise CliExecutionError(
                "install",
                404,
                f"Resource not found: {resource_uri}",
            )
        except Exception as e:
            self._handle_error(e, f"install {resource_uri}")
