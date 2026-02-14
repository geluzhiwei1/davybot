# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Market API client for direct HTTP requests.

Provides a Python client for interacting with the Market API
as an alternative to CLI commands.
"""

import logging
from typing import Any

import httpx

from .models import NetworkError, ResourceInfo, SearchResult

logger = logging.getLogger(__name__)


class MarketClient:
    """HTTP client for Market API.

    Provides direct API access for searching and retrieving resource information.
    """

    # Default API base URL
    DEFAULT_API_URL = "http://www.davybot.com/market/api/v1"

    # Request timeout in seconds
    DEFAULT_TIMEOUT = 30

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Initialize Market API client.

        Args:
            api_url: Market API base URL
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds

        """
        self.api_url = (api_url or self.DEFAULT_API_URL).rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

        # Build base URL without /api path for health check
        # Remove /api/v1 or /api suffix to get base URL
        if self.api_url.endswith("/api/v1"):
            self.base_url = self.api_url[:-7]  # Remove /api/v1 (7 chars)
        elif self.api_url.endswith("/api"):
            self.base_url = self.api_url[:-4]  # Remove /api (4 chars)
        else:
            self.base_url = self.api_url

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with authentication if configured."""
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle API response.

        Args:
            response: HTTP response

        Returns:
            Parsed JSON response

        Raises:
            NetworkError: If request fails

        """
        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.exception(f"API request failed: {e.response.status_code}")
            raise NetworkError(f"API error: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.exception("Network error: ")
            raise NetworkError(f"Network error: {e}")
        except Exception as e:
            logger.exception("Unexpected error: ")
            raise NetworkError(f"Unexpected error: {e}")

    # ========================================================================
    # Health Check
    # ========================================================================

    def health(self) -> dict[str, Any]:
        """Check Market API health status.

        Returns:
            Health status dictionary

        """
        try:
            # Health check is at root domain, not under /market path
            # Extract root domain from api_url
            # e.g., http://www.davybot.com/market/api/v1 -> http://www.davybot.com
            import urllib.parse

            parsed = urllib.parse.urlparse(self.api_url)
            root_url = f"{parsed.scheme}://{parsed.netloc}"
            url = f"{root_url}/health"

            # Disable SSL verification for development
            response = httpx.get(url, timeout=self.timeout, verify=False)
            return self._handle_response(response)
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ========================================================================
    # Search
    # ========================================================================

    def search(
        self,
        query: str,
        resource_type: str = "skill",
        limit: int = 20,
        skip: int = 0,
    ) -> list[SearchResult]:
        """Search for resources in the market.

        Args:
            query: Search query string
            resource_type: Resource type filter (skill, agent, plugin, etc.)
            limit: Maximum number of results
            skip: Number of results to skip (pagination)

        Returns:
            List of SearchResult objects

        """
        try:
            # Use POST /search endpoint (matches davybot-market-cli API)
            url = f"{self.api_url}/search"
            payload = {"query": query, "limit": limit, "skip": skip}
            if resource_type:
                payload["type"] = resource_type

            # Disable SSL verification for development
            response = httpx.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=self.timeout,
                verify=False,
            )
            data = self._handle_response(response)

            # Parse results from response
            results = []
            for item in data.get("results", data.get("items", [])):
                results.append(SearchResult.from_dict(item))

            return results

        except NetworkError:
            raise
        except Exception:
            logger.exception("Search failed: ")
            return []

    def search_skills(self, query: str, limit: int = 20) -> list[SearchResult]:
        """Search for skills."""
        return self.search(query, "skill", limit)

    def search_agents(self, query: str, limit: int = 20) -> list[SearchResult]:
        """Search for agents."""
        return self.search(query, "agent", limit)

    def search_plugins(self, query: str, limit: int = 20) -> list[SearchResult]:
        """Search for plugins."""
        return self.search(query, "plugin", limit)

    # ========================================================================
    # Resource Info
    # ========================================================================

    def get_resource(self, resource_type: str, identifier: str) -> ResourceInfo | None:
        """Get detailed information about a resource.

        Args:
            resource_type: Resource type (skill, agent, plugin)
            identifier: Resource ID or name

        Returns:
            ResourceInfo object or None

        """
        try:
            url = f"{self.api_url}/{resource_type}s/{identifier}"
            # Disable SSL verification for development
            response = httpx.get(url, headers=self._get_headers(), timeout=self.timeout, verify=False)
            data = self._handle_response(response)

            return ResourceInfo(
                result=SearchResult.from_dict(data),
                readme=data.get("readme"),
                license=data.get("license"),
                python_version=data.get("python_version"),
                dependencies=data.get("dependencies", []),
                install_path=data.get("install_path"),
            )

        except NetworkError:
            return None
        except Exception:
            logger.exception("Get resource failed: ")
            return None

    def get_skill(self, identifier: str) -> ResourceInfo | None:
        """Get skill information."""
        return self.get_resource("skill", identifier)

    def get_agent(self, identifier: str) -> ResourceInfo | None:
        """Get agent information."""
        return self.get_resource("agent", identifier)

    def get_plugin(self, identifier: str) -> ResourceInfo | None:
        """Get plugin information."""
        return self.get_resource("plugin", identifier)

    # ========================================================================
    # List Resources
    # ========================================================================

    def list_resources(
        self,
        resource_type: str,
        limit: int = 50,
        skip: int = 0,
    ) -> list[SearchResult]:
        """List all resources of a type.

        Args:
            resource_type: Resource type (skill, agent, plugin)
            limit: Maximum number of results
            skip: Number of results to skip (pagination)

        Returns:
            List of SearchResult objects

        """
        try:
            url = f"{self.api_url}/{resource_type}s"
            # Disable SSL verification for development
            response = httpx.get(
                url,
                params={"skip": skip, "limit": limit},
                headers=self._get_headers(),
                timeout=self.timeout,
                verify=False,
            )
            data = self._handle_response(response)

            results = []
            # Handle both "items" and "results" response format
            for item in data.get("items", data.get("results", [])):
                results.append(SearchResult.from_dict(item))

            return results

        except NetworkError:
            raise
        except Exception:
            logger.exception("List resources failed: ")
            return []

    def list_skills(self, limit: int = 50) -> list[SearchResult]:
        """List all skills."""
        return self.list_resources("skill", limit)

    def list_agents(self, limit: int = 50) -> list[SearchResult]:
        """List all agents."""
        return self.list_resources("agent", limit)

    def list_plugins(self, limit: int = 50) -> list[SearchResult]:
        """List all plugins."""
        return self.list_resources("plugin", limit)

    # ========================================================================
    # Download
    # ========================================================================

    def get_download_url(
        self,
        resource_type: str,
        resource_id: str,
        format: str = "zip",
    ) -> str | None:
        """Get download URL for a resource.

        Args:
            resource_type: Resource type
            resource_id: Resource ID
            format: Download format (zip or python)

        Returns:
            Download URL or None

        """
        try:
            url = f"{self.api_url}/{resource_type}s/{resource_id}/download"
            # Disable SSL verification for development
            response = httpx.get(
                url,
                params={"format": format},
                headers=self._get_headers(),
                timeout=self.timeout,
                verify=False,
            )
            data = self._handle_response(response)
            return data.get("download_url")

        except Exception:
            logger.exception("Get download URL failed: ")
            return None

    def download_resource(
        self,
        resource_type: str,
        resource_id: str,
        output_path: str,
        format: str = "zip",
    ) -> bool:
        """Download a resource to file.

        Args:
            resource_type: Resource type
            resource_id: Resource ID
            output_path: Output file path
            format: Download format

        Returns:
            True if successful

        """
        try:
            url = f"{self.api_url}/{resource_type}s/{resource_id}/download"
            response = httpx.get(
                url,
                params={"format": format},
                headers=self._get_headers(),
                timeout=120,  # Longer timeout for downloads
                follow_redirects=True,
            )

            response.raise_for_status()

            with Path(output_path).open("wb") as f:
                f.writelines(response.iter_bytes(chunk_size=8192))

            logger.info(f"Downloaded {resource_type} to {output_path}")
            return True

        except Exception:
            logger.exception("Download failed: ")
            return False

    # ========================================================================
    # Ratings and Reviews
    # ========================================================================

    def get_rating(self, resource_type: str, resource_id: str) -> dict[str, Any] | None:
        """Get resource rating information."""
        try:
            url = f"{self.api_url}/{resource_type}s/{resource_id}/rating"
            response = httpx.get(url, headers=self._get_headers(), timeout=self.timeout)
            return self._handle_response(response)
        except Exception:
            logger.exception("Get rating failed: ")
            return None

    def submit_rating(
        self,
        resource_type: str,
        resource_id: str,
        rating: int,
        comment: str | None = None,
    ) -> bool:
        """Submit a rating for a resource.

        Args:
            resource_type: Resource type
            resource_id: Resource ID
            rating: Rating value (1-5)
            comment: Optional comment

        Returns:
            True if successful

        """
        try:
            url = f"{self.api_url}/{resource_type}s/{resource_id}/ratings"
            response = httpx.post(
                url,
                json={"rating": rating, "comment": comment},
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            self._handle_response(response)
            return True
        except Exception:
            logger.exception("Submit rating failed: ")
            return False
