"""Market API endpoints for resource installation.

- ``POST /api/market/install-v2`` — install resources via resource_installer.py (user JWT)

Historical note: the local ``GET /api/market/templates/*`` catalog/version
endpoints were removed — the frontend lists templates from the server market
API (``/v1/market/resources?type=template``) and reads installed templates
from the checklists API; the local ``nn-market-resources/data`` catalog they
read was stale after the v3 resource-ID migration.
"""

import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .workspaces import get_user_workspace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["market"])


# ============================================================================
# Install-v2 Models
# ============================================================================


class InstallV2Request(BaseModel):
    """Install request using resource_installer.py.

    Accepts individual resource IDs or a team ID.
    Resource IDs use format: 'skill/docx', 'agent/patent-team', 'mcp/paper-search-mcp'.
    """

    workspace: str = Field(..., description="Workspace ID or path")
    resource_id: str | None = Field(None, description="Single resource ID e.g. 'skill/docx'")
    resource_ids: list[str] | None = Field(None, description="Multiple resource IDs")
    team_id: str | None = Field(None, description="Team ID e.g. 'team/sanctions-compliance'")
    team_meta: dict[str, Any] | None = Field(None, description="Team metadata with skills/agents/mcps/knowledges lists")
    versions: dict[str, str] | None = Field(None, description="Version map for templates e.g. {'template/ip/.../slug': '1.0.0'}")


class InstallV2Response(BaseModel):
    success: bool
    installed: Dict[str, Any]
    error: str | None = None


# ============================================================================
# Helpers
# ============================================================================


def _bearer_token(http_request: Request) -> str | None:
    """Extract the Bearer JWT from the incoming request."""
    from dawei.api.auth import extract_market_token
    return extract_market_token(http_request)


# ============================================================================
# POST /api/market/install-v2
# ============================================================================


@router.post("/install-v2", response_model=InstallV2Response)
async def install_resources_v2(request: InstallV2Request, http_request: Request):
    """Install resources using resource_installer.py.

    Supports:
    - Single resource: resource_id = 'skill/docx'
    - Multiple resources: resource_ids = ['skill/docx', 'agent/patent-team']
    - Team install: team_id + team_meta with skills/agents/mcps/knowledges lists

    Market install authenticates as the calling user by forwarding this
    request's Bearer JWT (the page login) — no separate service account.
    """
    from dawei.workspace.resource_installer import install_resources_to_workspace

    market_token = _bearer_token(http_request)

    # Resolve workspace path
    user_workspace = await get_user_workspace(request.workspace, http_request)
    workspace_path = str(user_workspace.workspace_path)

    # Build parameters
    skill_ids: list[str] = []
    agent_ids: list[str] = []
    mcp_ids: list[str] = []
    knowledge_ids: list[str] = []
    template_ids: list[str] = []

    # Single resource_id → route to correct list
    if request.resource_id:
        res_type, _ = request.resource_id.split("/", 1) if "/" in request.resource_id else (request.resource_id, request.resource_id)
        if res_type == "skill":
            skill_ids = [request.resource_id]
        elif res_type == "agent":
            agent_ids = [request.resource_id]
        elif res_type == "mcp":
            mcp_ids = [request.resource_id]
        elif res_type == "knowledge":
            knowledge_ids = [request.resource_id]
        elif res_type == "template":
            template_ids = [request.resource_id]

    # Multiple resource_ids → route each
    if request.resource_ids:
        for rid in request.resource_ids:
            res_type, _ = rid.split("/", 1) if "/" in rid else (rid, rid)
            if res_type == "skill":
                skill_ids.append(rid)
            elif res_type == "agent":
                agent_ids.append(rid)
            elif res_type == "mcp":
                mcp_ids.append(rid)
            elif res_type == "knowledge":
                knowledge_ids.append(rid)
            elif res_type == "template":
                template_ids.append(rid)

    try:
        # 【2026-09-14 事件循环阻塞修复】installer 为同步重 IO(市场下载+文件复制),
        # 直接在 async handler 内调用会阻塞整个事件循环(WS 心跳/其它会话全部停摆)
        result = await asyncio.to_thread(
            install_resources_to_workspace,
            workspace_path=workspace_path,
            team_id=request.team_id,
            team_meta=request.team_meta,
            skill_ids=skill_ids or None,
            agent_ids=agent_ids or None,
            mcp_ids=mcp_ids or None,
            knowledge_ids=knowledge_ids or None,
            template_ids=template_ids or None,
            versions=request.versions,
            market_token=market_token,
        )
    except ValueError as e:
        # 资源在市场中不存在/不可见(如被资源组隐藏)→ 404,而非 500
        logger.warning("install-v2 resource not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        # 团队归属/模块可见性不通过(can-access 预校验)→ 403 forbidden_team
        logger.warning("install-v2 access denied: %s", e)
        raise HTTPException(status_code=403, detail=str(e)) from e

    # 【2026-09-14 安装后生效】安装写入 .dawei/ 的资源此前被已初始化的
    # WorkspaceContext 缓存挡住(ToolManager/ModeManager/MCPToolManager 都是安装前
    # 快照), 要重启进程才可见。使缓存失效后, 下一次会话即加载新装的
    # skills/agents/modes/mcp/knowledge。
    try:
        from dawei.workspace.workspace_service import WorkspaceService

        removed = await WorkspaceService.invalidate_context(workspace_path)
        if removed:
            logger.info(
                "install-v2: invalidated %d cached WorkspaceContext(s) for %s",
                removed, workspace_path,
            )
    except Exception as e:
        logger.warning("install-v2: workspace context invalidation failed: %s", e)

    return InstallV2Response(success=True, installed=result)
