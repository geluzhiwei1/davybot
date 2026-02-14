"""Market API endpoints for resource management.

Provides REST API endpoints for searching, installing, and managing
skills, agents, and plugins from the davybot market.
"""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from dawei.market import (
    InstallationError,
    MarketClient,
    MarketError,
    MarketInstaller,
    ResourceNotFoundError,
)

from .workspaces import get_user_workspace

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/market", tags=["market"])

# Singleton instances
_market_client: MarketClient | None = None
_installers: dict[str, MarketInstaller] = {}


# ============================================================================
# Request/Response Models
# ============================================================================


class SearchRequest(BaseModel):
    """Search request model."""

    query: str = Field(..., description="Search query string")
    type: str = Field("skill", description="Resource type: skill, agent, plugin")
    limit: int = Field(20, description="Maximum number of results", ge=1, le=100)


class SearchResponse(BaseModel):
    """Search response model."""

    success: bool
    query: str
    type: str
    total: int
    results: list[dict[str, Any]]


class InstallRequest(BaseModel):
    """Install request model."""

    resource_type: str = Field(..., description="Resource type: skill, agent, plugin")
    resource_name: str = Field(..., description="Resource name or URI")
    workspace: str = Field(..., description="Workspace path")
    force: bool = Field(False, description="Force reinstall if already exists")


class InstallResponse(BaseModel):
    """Install response model."""

    success: bool
    result: dict[str, Any]


class InfoResponse(BaseModel):
    """Resource info response model."""

    success: bool
    resource: dict[str, Any] | None = None
    error: str | None = None


class UninstallRequest(BaseModel):
    """Uninstall request model."""

    workspace: str = Field(..., description="Workspace path")


# ============================================================================
# Helper Functions
# ============================================================================


def get_market_client() -> MarketClient:
    """Get or create global market client instance."""
    global _market_client
    if _market_client is None:
        _market_client = MarketClient()
    return _market_client


def get_installer(workspace: str) -> MarketInstaller:
    """Get or create installer for workspace."""
    if workspace not in _installers:
        _installers[workspace] = MarketInstaller(workspace)
    return _installers[workspace]


def validate_workspace(workspace: str) -> Path:
    """Validate workspace path exists."""
    workspace_path = Path(workspace).resolve()
    if not workspace_path.exists():
        raise HTTPException(status_code=400, detail=f"Workspace path does not exist: {workspace}")
    if not workspace_path.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Workspace path is not a directory: {workspace}",
        )
    return workspace_path


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/health")
async def health_check():
    """Check Market API health status."""
    client = get_market_client()
    return client.health()


@router.post("/search", response_model=SearchResponse)
async def search_resources(request: SearchRequest):
    """Search for resources in the market.

    Supports searching for skills, agents, and plugins.
    """
    try:
        client = get_market_client()

        # Route to appropriate search method
        # Note: The official API doesn't support 'plugin' type in search
        # so we use list_resources for plugins instead
        if request.type == "skill":
            results = client.search_skills(request.query, request.limit)
        elif request.type == "agent":
            results = client.search_agents(request.query, request.limit)
        elif request.type == "plugin":
            # Use list_resources for plugins since search doesn't support plugin type
            # If query is empty, return all plugins, otherwise filter manually
            all_plugins = client.list_resources("plugin", request.limit, 0)
            if request.query:
                # Simple filter by name/description/tags
                query_lower = request.query.lower()
                results = [p for p in all_plugins if (query_lower in p.name.lower() or query_lower in p.description.lower() or any(query_lower in tag.lower() for tag in p.tags))][: request.limit]
            else:
                results = all_plugins
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid resource type: {request.type}. Use skill, agent, or plugin.",
            )

        return SearchResponse(
            success=True,
            query=request.query,
            type=request.type,
            total=len(results),
            results=[r.to_dict() for r in results],
        )

    except MarketError as e:
        logger.warning(f"Market API unavailable for search: {e}")
        # Return empty results instead of 500 error
        return SearchResponse(
            success=True,
            query=request.query,
            type=request.type,
            total=0,
            results=[],
        )
    except Exception:
        logger.exception("Search failed unexpectedly")
        # Return empty results instead of 500 error for better UX
        return SearchResponse(
            success=True,
            query=request.query,
            type=request.type,
            total=0,
            results=[],
        )


@router.get("/search")
async def search_resources_get(
    q: str = Query(..., description="Search query"),
    type: str = Query("skill", description="Resource type"),
    limit: int = Query(20, description="Max results", ge=1, le=100),
):
    """GET endpoint for search (for browser compatibility)."""
    request = SearchRequest(query=q, type=type, limit=limit)
    return await search_resources(request)


@router.get("/info/{resource_type}/{resource_name}", response_model=InfoResponse)
async def get_resource_info(resource_type: str, resource_name: str):
    """Get detailed information about a resource.

    Returns full resource details including readme, dependencies, etc.
    """
    try:
        client = get_market_client()

        # Route to appropriate get method
        if resource_type == "skill":
            info = client.get_skill(resource_name)
        elif resource_type == "agent":
            info = client.get_agent(resource_name)
        elif resource_type == "plugin":
            info = client.get_plugin(resource_name)
        else:
            raise HTTPException(status_code=400, detail=f"Invalid resource type: {resource_type}")

        if info is None:
            return InfoResponse(success=False, error=f"Resource '{resource_name}' not found")

        return InfoResponse(success=True, resource=info.to_dict())

    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.to_dict())
    except Exception as e:
        logger.exception("Get resource info failed")
        raise HTTPException(status_code=500, detail={"error": "info_failed", "message": str(e)})


@router.post("/install", response_model=InstallResponse)
async def install_resource(request: InstallRequest):
    """Install a resource from the market.

    Downloads and installs a skill, agent, or plugin to the workspace.
    """
    try:
        # Get workspace from ID
        user_workspace = get_user_workspace(request.workspace)
        workspace_path = str(user_workspace.workspace_path)

        # Get installer
        installer = get_installer(workspace_path)

        # Perform installation
        result = installer.install(
            resource_type=request.resource_type,
            resource_name=request.resource_name,
            force=request.force,
        )

        return InstallResponse(success=result.success, result=result.to_dict())

    except InstallationError as e:
        logger.exception("Installation failed: ")
        raise HTTPException(status_code=500, detail=e.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Installation failed unexpectedly")
        raise HTTPException(
            status_code=500,
            detail={"error": "installation_failed", "message": str(e)},
        )


@router.get("/installed/{resource_type}")
async def list_installed_resources(
    resource_type: str,
    workspace_id: str = Query(..., description="Workspace ID"),
):
    """List installed resources of a type.

    Returns all installed skills, agents, or plugins in the workspace.
    """
    try:
        # Get workspace from ID
        user_workspace = get_user_workspace(workspace_id)
        workspace_path = str(user_workspace.workspace_path)

        # Get installer
        installer = get_installer(workspace_path)

        # List installed
        if resource_type == "plugin":
            installed = installer.list_plugins()
            return {
                "success": True,
                "type": resource_type,
                "total": len(installed),
                "resources": installed,
            }
        installed = installer.list_installed(resource_type)
        return {
            "success": True,
            "type": resource_type,
            "total": len(installed),
            "resources": [r.to_dict() for r in installed],
        }

    except FileNotFoundError as e:
        logger.warning(f"Workspace not found for list_installed: {e}")
        return {
            "success": True,
            "type": resource_type,
            "total": 0,
            "resources": [],
        }
    except Exception:
        logger.exception("List installed failed")
        # Return empty list instead of 500 error for better UX
        return {
            "success": True,
            "type": resource_type,
            "total": 0,
            "resources": [],
        }


@router.delete("/installed/plugin/{plugin_name}")
async def uninstall_plugin(
    plugin_name: str,
    workspace_id: str = Query(..., description="Workspace ID"),
):
    """Uninstall a plugin from the workspace.

    Removes the plugin and updates configuration.
    """
    try:
        # Get workspace from ID
        user_workspace = get_user_workspace(workspace_id)
        workspace_path = str(user_workspace.workspace_path)

        # Get installer
        installer = get_installer(workspace_path)

        # Uninstall
        result = installer.uninstall("plugin", plugin_name)

        return {"success": result.success, "result": result.to_dict()}

    except Exception as e:
        logger.exception("Uninstall failed")
        raise HTTPException(
            status_code=500,
            detail={"error": "uninstall_failed", "message": str(e)},
        )


@router.get("/categories")
async def list_categories():
    """List available resource categories/types."""
    return {
        "success": True,
        "categories": [
            {
                "value": "skill",
                "label": "Skills",
                "description": "AI agent skills and capabilities",
            },
            {
                "value": "agent",
                "label": "Agents",
                "description": "Complete agent templates",
            },
            {
                "value": "plugin",
                "label": "Plugins",
                "description": "Workspace plugins and integrations",
            },
        ],
    }


@router.get("/featured")
async def get_featured_resources(
    type: str = Query("skill", description="Resource type filter"),
    limit: int = Query(10, description="Number of results"),
):
    """Get featured/popular resources from the market.

    Returns highly rated and frequently downloaded resources.
    """
    try:
        client = get_market_client()

        # For plugins, use list_resources (search doesn't support plugin type)
        # For skills/agents, use search with a generic term
        if type == "skill":
            results = client.search_skills("*", limit)
        elif type == "agent":
            results = client.search_agents("*", limit)
        elif type == "plugin":
            # Use list_resources for plugins since search doesn't support plugin type
            results = client.list_resources("plugin", limit, 0)
        else:
            raise HTTPException(status_code=400, detail=f"Invalid resource type: {type}")

        # Sort by downloads/rating
        sorted_results = sorted(results, key=lambda r: (r.downloads, r.rating or 0), reverse=True)[:limit]

        return {
            "success": True,
            "type": type,
            "total": len(sorted_results),
            "resources": [r.to_dict() for r in sorted_results],
        }

    except MarketError as e:
        logger.warning(f"Market API unavailable for featured resources: {e}")
        # Return empty results instead of 500 error
        return {
            "success": True,
            "type": type,
            "total": 0,
            "resources": [],
        }
    except Exception:
        logger.exception("Get featured failed for type {type}: ")
        # Return empty results instead of 500 error for better UX
        return {
            "success": True,
            "type": type,
            "total": 0,
            "resources": [],
        }
