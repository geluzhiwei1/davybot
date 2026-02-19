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
    CliExecutionError,
    CliNotFoundError,
    InstallationError,
    MarketError,
    MarketInstaller,
    ResourceNotFoundError,
)
from dawei.market.cli_wrapper import CliWrapper

from .workspaces import get_user_workspace

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/market", tags=["market"])

# Singleton instances
_cli_wrapper: CliWrapper | None = None
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


def get_cli_wrapper() -> CliWrapper:
    """Get or create global CLI wrapper instance."""
    global _cli_wrapper
    if _cli_wrapper is None:
        _cli_wrapper = CliWrapper()
    return _cli_wrapper


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
    cli = get_cli_wrapper()
    return cli.health()


@router.post("/search", response_model=SearchResponse)
async def search_resources(request: SearchRequest):
    """Search for resources in the market.

    Supports searching for skills, agents, and plugins.
    """
    try:
        cli = get_cli_wrapper()

        # Route to appropriate search method
        if request.type == "skill":
            search_result = cli.search_skills(request.query, request.limit)
        elif request.type == "agent":
            search_result = cli.search_agents(request.query, request.limit)
        elif request.type == "plugin":
            # Plugin search via CLI
            search_result = cli.search(request.query, "plugin", request.limit)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid resource type: {request.type}. Use skill, agent, or plugin.",
            )

        # CLI returns dict with 'items' or 'results' key (depending on SDK version)
        results = search_result.get("items") or search_result.get("results", [])

        return SearchResponse(
            success=True,
            query=request.query,
            type=request.type,
            total=len(results),
            results=results,
        )

    except CliNotFoundError as e:
        logger.error(f"Market CLI not found: {e}")
        raise HTTPException(
            status_code=503,
            detail={"error": "market_cli_not_found", "message": str(e)},
        )
    except CliExecutionError as e:
        logger.exception("Market CLI execution error during search: ")
        raise HTTPException(
            status_code=500,
            detail={"error": "search_failed", "message": str(e)},
        )
    except Exception as e:
        logger.exception("Search failed unexpectedly: ")
        raise HTTPException(
            status_code=500,
            detail={"error": "search_failed", "message": str(e)},
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
        cli = get_cli_wrapper()

        if resource_type not in ("skill", "agent", "plugin"):
            raise HTTPException(status_code=400, detail=f"Invalid resource type: {resource_type}")

        info = cli.info(resource_type, resource_name)

        if not info.get("success", True):
            return InfoResponse(success=False, error=info.get("error", " error"))

        return InfoResponse(success=True, resource=info)

    except CliNotFoundError as e:
        logger.error(f"Market CLI not found: {e}")
        raise HTTPException(
            status_code=503,
            detail={"error": "market_cli_not_found", "message": str(e)},
        )
    except CliExecutionError as e:
        logger.exception("Market CLI execution error during info retrieval: ")
        raise HTTPException(
            status_code=500,
            detail={"error": "info_failed", "message": str(e)},
        )
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
    except Exception as e:
        logger.exception("List installed failed: ")
        raise HTTPException(
            status_code=500,
            detail={"error": "list_installed_failed", "message": str(e)},
        )


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
    skip: int = Query(0, description="Number of results to skip"),
):
    """Get featured/popular resources from the market.

    Returns highly rated and frequently downloaded resources.
    Supports pagination via limit and skip parameters.
    """
    try:
        cli = get_cli_wrapper()

        # Get ALL resources to calculate correct total and sort
        # Use a large limit to fetch all available resources
        if type == "skill":
            list_result = cli.list_skills(limit=1000, skip=0)
        elif type == "agent":
            list_result = cli.list_agents(limit=1000, skip=0)
        elif type == "plugin":
            list_result = cli.list_plugins(limit=1000, skip=0)
        else:
            raise HTTPException(status_code=400, detail=f"Invalid resource type: {type}")

        # CLI returns dict with 'items' or 'results' key (depending on SDK version)
        all_results = list_result.get("items") or list_result.get("results", [])

        # Sort by downloads/rating (handle dict format)
        def get_popularity(r: dict) -> tuple:
            downloads = r.get("downloads", 0) or 0
            rating = r.get("rating", 0) or 0
            return (downloads, rating)

        sorted_results = sorted(all_results, key=get_popularity, reverse=True)

        # Apply pagination
        paginated_results = sorted_results[skip:skip + limit]
        total_count = len(sorted_results)

        return {
            "success": True,
            "type": type,
            "total": total_count,
            "resources": paginated_results,
        }

    except CliNotFoundError as e:
        logger.error(f"Market CLI not found: {e}")
        raise HTTPException(
            status_code=503,
            detail={"error": "market_cli_not_found", "message": str(e)},
        )
    except CliExecutionError as e:
        logger.exception("Market CLI execution error during featured retrieval: ")
        raise HTTPException(
            status_code=500,
            detail={"error": "featured_failed", "message": str(e)},
        )
    except Exception as e:
        logger.exception("Get featured failed: ")
        raise HTTPException(
            status_code=500,
            detail={"error": "featured_failed", "message": str(e)},
        )
