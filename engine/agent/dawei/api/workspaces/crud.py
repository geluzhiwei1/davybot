"""工作区 CRUD API

实现工作区的创建、读取、更新、删除功能。

两级存储架构：
1. 系统级：~/.dawei/workspaces.json (工作区索引)
2. 工作区级：{workspace_path}/.dawei/workspace.json (详细配置)
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from dawei.api.workspaces._deps import require_workspace_access
from dawei.core.datetime_compat import UTC
from dawei.core.path_security import sanitize_workspace_response
from dawei.storage.storage_provider import StorageProvider
from dawei.workspace.models import WorkspaceCategory, WorkspaceInfo, WorkspaceLifecycle, WorkspaceType

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workspaces-crud"])


def _bearer_token(http_request: Request) -> str | None:
    """Extract the Bearer JWT from the incoming request, if present.

    Delegate to the unified ``dawei.api.auth.extract_market_token``.
    Kept as a thin wrapper for backward compatibility with existing
    call sites in this module.
    """
    from dawei.api.auth import extract_market_token
    return extract_market_token(http_request)


# ==================== 请求/响应模型 ====================


class ValidatePathRequest(BaseModel):
    """路径验证请求"""

    path: str = Field(..., description="工作区路径")


class ValidatePathResponse(BaseModel):
    """路径验证响应"""

    success: bool
    valid: bool
    message: str
    exists: bool = False
    writable: bool | None = None
    is_empty: bool | None = None
    is_workspace: bool = False


class CreateWorkspaceRequest(BaseModel):
    """创建工作区请求"""

    path: str | None = Field(None, description="工作区完整路径（合规工作区可省略，由 TempWorkspaceManager 自动生成）")
    name: str | None = Field(None, description="工作区名称（可选，默认使用目录名）")
    display_name: str | None = Field(None, description="显示名称")
    description: str | None = Field(None, description="描述")
    biz_module: str | None = Field(
        None,
        max_length=100,
        description="业务模块标识（如 research-review）：固化进 workspace.json 与系统索引；"
        "mode 收紧策略按它限定工作区可见 modes（见 core.WORKSPACE_MODULE_AGENTS）",
    )

    # Market resource selections
    team_id: str | None = Field(None, description="团队资源ID，如 team/patent-team")
    team_meta: dict[str, Any] | None = Field(None, description="团队元数据（含引用的资源列表）")
    skill_ids: list[str] | None = Field(None, description="技能资源ID列表，如 ['skill/docx', 'skill/pdf']")
    agent_ids: list[str] | None = Field(None, description="智能体资源ID列表，如 ['agent/patent-team']")
    mcp_ids: list[str] | None = Field(None, description="MCP服务资源ID列表，如 ['mcp/paper-search-mcp']")
    knowledge_ids: list[str] | None = Field(None, description="知识库资源ID列表，如 ['knowledge/us-sanctions-regulations']")

    # Compliance template fields (合规工作区模板)
    compliance_template: str | None = Field(
        None,
        description="合规工作区模板 slug，如 supply-chain-uflpa",
    )
    compliance_form_data: dict[str, Any] | None = Field(
        None,
        description="合规表单数据 (key-value pairs)",
    )


class UpdateWorkspaceRequest(BaseModel):
    """更新工作区请求"""

    display_name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    is_active: bool | None = None


class CreateTempWorkspaceRequest(BaseModel):
    """创建临时工作空间请求

    扩展字段（skill_ids / mcp_ids / team_id / agent_ids / knowledge_ids）用于
    在临时工作空间创建后立即安装 Market 资源 —— 典型场景是 nn-flow 通过
    ``NormFlowOrchestrator`` 派发任务时需要带上 NormFlow MCP + 服务报告/模板 Skill。
    安装失败不会回滚工作空间创建，只记录日志（与 ``/create`` 行为一致）。
    """

    display_name: str = Field("[临时] 新聊天", max_length=200, description="显示名称")

    # Optional Market resource installs (mirrors CreateWorkspaceRequest).
    team_id: str | None = Field(None, description="团队资源ID，如 team/normflow")
    skill_ids: list[str] | None = Field(None, description="技能资源ID列表")
    agent_ids: list[str] | None = Field(None, description="智能体资源ID列表")
    mcp_ids: list[str] | None = Field(None, description="MCP服务资源ID列表")
    knowledge_ids: list[str] | None = Field(None, description="知识库资源ID列表")
    team_meta: dict[str, Any] | None = Field(
        None, description="团队元数据（skills/agents/mcps/knowledges 列表）；缺省时从市场 API 回填"
    )


class WorkspaceResponse(BaseModel):
    """工作区响应"""

    success: bool
    workspace: dict[str, Any] | None = None
    message: str | None = None
    error: str | None = None
    # 安装结果（market 资源 + 合规模板初始化），用于前端/调试确认
    installed_resources: dict[str, Any] | None = None
    compliance_init: dict[str, Any] | None = None


class WorkspaceListResponse(BaseModel):
    """工作区列表响应"""

    success: bool
    workspaces: list[dict[str, Any]]
    total: int


# ==================== 路径验证 API ====================


@router.post("/validate-path", response_model=ValidatePathResponse)
async def validate_path(request: ValidatePathRequest):
    """验证工作区路径

    检查项：
    1. 路径是否存在
    2. 是否有写入权限
    3. 是否已经是工作区
    4. 是否为空目录
    """
    path = Path(request.path).resolve()

    # 检查路径是否存在
    if not path.exists():
        return ValidatePathResponse(
            success=True,
            valid=True,
            message="路径不存在，将创建新目录",
            exists=False,
            writable=True,
            is_empty=True,
        )

    # 检查是否是目录
    if not path.is_dir():
        return ValidatePathResponse(
            success=True,
            valid=False,
            message="路径不是目录",
            exists=True,
        )

    # 检查是否已经是工作区
    if (path / ".dawei").exists():
        return ValidatePathResponse(
            success=True,
            valid=True,
            message="此目录已经是工作区，将添加到工作区列表",
            exists=True,
            writable=True,
            is_workspace=True,
        )

    # 检查写入权限
    if not os.access(path, os.W_OK):
        return ValidatePathResponse(
            success=True,
            valid=False,
            message="无写入权限",
            exists=True,
            writable=False,
        )

    # 检查是否为空
    is_empty = not any(path.iterdir())
    if not is_empty:
        return ValidatePathResponse(
            success=True,
            valid=True,
            message="目录不为空，将在现有目录中创建工作区",
            exists=True,
            writable=True,
            is_empty=False,
        )

    return ValidatePathResponse(
        success=True,
        valid=True,
        message="路径有效，可以创建工作区",
        exists=True,
        writable=True,
        is_empty=True,
    )


# ==================== 创建工作区 API ====================


async def _create_compliance_workspace(
    request: CreateWorkspaceRequest, http_request: Request, market_token: str | None = None
) -> WorkspaceResponse:
    """合规工作区创建：由 TempWorkspaceManager 统一管理路径，忽略前端传的 path。

    流程：
    1. TempWorkspaceManager 在 ~/.normnomos/temp_workspaces/{user}/{tenant}/{uuid}/ 下创建临时工作区
    2. 更新 workspace_type 为 COMPLIANCE_PROJECT，写入 metadata
    3. 安装 market resources（team, skills, agents, mcps, knowledge）
    4. 初始化合规模板目录结构（compliance_template）
    """
    # 提取身份（物理隔离用）—— 无有效登录直接 401，无匿名身份
    from dawei.api.auth import get_authenticated_tenant_id, get_authenticated_user_id
    from dawei.workspace.temp_workspace_manager import temp_workspace_manager

    owner_id = await get_authenticated_user_id(http_request)
    tenant_id = await get_authenticated_tenant_id(http_request)

    display_name = request.display_name or "合规工作区"

    # 1. TempWorkspaceManager 创建临时工作区
    temp_ws = await temp_workspace_manager.create_temp_workspace(
        display_name=display_name,
        workspace_type=WorkspaceType.COMPLIANCE_PROJECT.value,
        owner_user_id=owner_id,
        tenant_id=tenant_id,
    )
    workspace_id = temp_ws["id"]
    workspace_path = Path(temp_ws["path"])
    logger.info(f"[COMPLIANCE] Created temp workspace: {workspace_id} at {workspace_path}")

    workspace_storage = StorageProvider.get_workspace_storage(str(workspace_path))

    # 2. 更新 workspace.json：覆盖 workspace_type + 写入 metadata
    config_path = workspace_path / ".dawei" / "workspace.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["workspace_type"] = WorkspaceType.COMPLIANCE_PROJECT.value
    config["description"] = request.description
    config.setdefault("metadata", {})["compliance_template"] = request.compliance_template
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    # 同步更新系统级索引中的 workspace_type
    await _update_workspace_in_system_index(workspace_id, workspace_type=WorkspaceType.COMPLIANCE_PROJECT.value)

    # 3. Install market resources (team, skills, agents, mcps, knowledge)
    # Backfill team_meta from the market API when only team_id was supplied.
    team_meta = request.team_meta
    if not team_meta and request.team_id:
        try:
            from dawei.workspace.resource_installer import resolve_team_meta
            team_meta = resolve_team_meta(request.team_id, token=market_token)
        except Exception as e:
            logger.warning(f"[COMPLIANCE] Failed to resolve team_meta for {request.team_id}: {e}")

    install_results = {}
    has_resources = request.team_id or request.skill_ids or request.agent_ids or request.mcp_ids or request.knowledge_ids
    if has_resources:
        try:
            from dawei.workspace.resource_installer import install_resources_to_workspace
            # 【2026-09-14 事件循环阻塞修复】同步重 IO → 线程池执行
            install_results = await asyncio.to_thread(
                install_resources_to_workspace,
                workspace_path=str(workspace_path),
                team_id=request.team_id,
                team_meta=team_meta,
                skill_ids=request.skill_ids,
                agent_ids=request.agent_ids,
                mcp_ids=request.mcp_ids,
                knowledge_ids=request.knowledge_ids,
                market_token=market_token,
            )
            logger.info(f"[COMPLIANCE] Resource install results for {workspace_id}: {install_results}")
        except Exception as e:
            logger.error(f"[COMPLIANCE] Failed to install resources for {workspace_id}: {e}", exc_info=True)

    # 4. Initialize from business template (compliance etc.) via ext_hooks —
    #    核心不 import 业务模板管理器（§18.3 缝改造）；biz 缺席 = 无初始化器 = 跳过。
    compliance_init_result = None
    if request.compliance_template:
        try:
            from dawei.core.ext_hooks import run_workspace_template_initializers

            compliance_init_result = await run_workspace_template_initializers(
                workspace_path=str(workspace_path),
                template_slug=request.compliance_template,
                form_data=request.compliance_form_data or {},
                storage=workspace_storage,
            )
            if compliance_init_result is not None:
                logger.info(
                    "[COMPLIANCE] Template '%s' initialized for workspace %s: %s",
                    request.compliance_template,
                    workspace_id,
                    compliance_init_result,
                )
            else:
                logger.warning(
                    "[COMPLIANCE] No template initializer claimed '%s' for workspace %s "
                    "(biz absent or unknown slug)",
                    request.compliance_template,
                    workspace_id,
                )
        except Exception as e:
            logger.error(
                "[COMPLIANCE] Failed to init compliance template for workspace %s: %s",
                workspace_id,
                e,
                exc_info=True,
            )

    # Build response
    sanitized_workspace = sanitize_workspace_response(config, remove_path=True)
    response = WorkspaceResponse(
        success=True,
        workspace=sanitized_workspace,
        message="合规工作区创建成功",
    )

    response_dict = response.model_dump()
    if install_results:
        response_dict["installed_resources"] = install_results
    if compliance_init_result:
        response_dict["compliance_init"] = compliance_init_result

    return WorkspaceResponse(**response_dict)


async def _update_workspace_in_system_index(workspace_id: str, workspace_type: str):
    """更新系统级索引 workspaces.json 中指定工作区的 workspace_type"""
    system_storage = StorageProvider.get_system_storage()
    if not await system_storage.exists("workspaces.json"):
        return
    content = await system_storage.read_file("workspaces.json")
    data = json.loads(content)
    for ws in data.get("workspaces", []):
        if ws.get("id") == workspace_id:
            ws["workspace_type"] = workspace_type
            break
    await system_storage.write_file(
        "workspaces.json",
        json.dumps(data, indent=2, ensure_ascii=False),
    )


@router.post("/create", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(request: CreateWorkspaceRequest, http_request: Request):
    """创建工作区

    SECURITY: This endpoint accepts arbitrary filesystem paths and writes .dawei/
    configuration files there. In production deployment, this endpoint MUST be
    behind authentication middleware. Set environment variable
    DAWEI_WORKSPACE_BASE_DIR to restrict workspace creation to a parent directory
    (e.g. DAWEI_WORKSPACE_BASE_DIR=/home/user/workspaces).

    关键步骤：
    1. 验证路径
    2. 创建工作区目录结构（如果不存在）
    3. 创建 .dawei/workspace.json（工作区级配置）
    4. 更新 ~/.dawei/workspaces.json（系统级索引）

    Market resource install authenticates to the market API as the calling user
    by forwarding this request's Bearer JWT (the page login) — no separate
    service account.
    """
    market_token = _bearer_token(http_request)

    # === 合规工作区：走 TempWorkspaceManager，忽略前端传的 path ===
    if request.compliance_template:
        return await _create_compliance_workspace(request, http_request, market_token=market_token)

    # 身份提取（服务端托管路径分配 + 系统索引注册共用）—— 无有效登录直接 401
    from dawei.api.auth import get_authenticated_tenant_id, get_authenticated_user_id

    owner_id = await get_authenticated_user_id(http_request)
    tenant_id = await get_authenticated_tenant_id(http_request)

    _base_dir = os.environ.get("DAWEI_WORKSPACE_BASE_DIR")

    if request.path:
        workspace_path = Path(request.path).resolve()

        # Security: If DAWEI_WORKSPACE_BASE_DIR is configured, enforce path confinement
        if _base_dir:
            _base = Path(_base_dir).resolve()
            try:
                workspace_path.relative_to(_base)
            except ValueError:
                logger.warning(
                    "Rejected workspace creation outside DAWEI_WORKSPACE_BASE_DIR: "
                    "request path=%s, base dir=%s",
                    str(workspace_path),
                    str(_base),
                )
                raise HTTPException(
                    status_code=403,
                    detail=f"Workspace path must be inside {_base}",
                )
    else:
        # Web（浏览器）端无法提供本地文件系统路径（只有桌面端 Tauri 有 path API），
        # 分配服务端托管的持久工作区目录，而不是 400。
        # NOTE: 不能放在 temp_workspaces/ 下 —— 启动清理会把非 temporary 的目录当孤儿删除
        # （cleanup_orphaned_temp_workspaces 只把 temporary 索引项视为已注册）。
        from dawei import get_dawei_home

        _managed_root = Path(_base_dir or (get_dawei_home() / "web_workspaces")).resolve()
        workspace_path = _managed_root / owner_id / tenant_id / str(uuid.uuid4())
        logger.info("No path supplied (web client), allocated server-managed workspace dir: %s", workspace_path)

    # Warn if path is in a system location (potential misconfiguration or attack)
    _danger_prefixes = ["/etc", "/sys", "/proc", "/dev", "/root", "/var", "/boot"]
    if any(str(workspace_path).startswith(p) for p in _danger_prefixes):
        logger.warning(
            "Workspace created in system directory: %s — ensure this is intentional",
            str(workspace_path),
        )

    # 获取或创建 workspace_storage
    # 如果路径不存在，先创建
    if not workspace_path.exists():
        workspace_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory: {workspace_path}")

    workspace_storage = StorageProvider.get_workspace_storage(str(workspace_path))

    # 检查是否已是工作区（存在 workspace.json）
    workspace_config_path = workspace_path / ".dawei" / "workspace.json"
    is_existing_workspace = workspace_config_path.exists()

    if is_existing_workspace:
        # 读取现有工作区配置
        logger.info(f"Found existing workspace at {workspace_path}")
        existing_config = json.loads(workspace_config_path.read_text())
        workspace_id = existing_config.get("id")
        workspace_name = existing_config.get("name", workspace_path.name)

        # Ownership guard：create-by-path 按 path 幂等复用，但既有工作区可能属于
        # 「其他账号」（同一台机器多账号切换）。若原样返回，调用方拿到的 workspace id
        # 在后续所有读写（conversations 等）上都会 403。这里快速失败。
        from dawei.workspace import workspace_manager

        existing_index = workspace_manager.get_workspace_by_id(workspace_id)
        if existing_index and (
            existing_index.get("owner_user_id") != owner_id
            or existing_index.get("tenant_id", "personal") != tenant_id
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Workspace path '{request.path}' already belongs to another "
                    f"user/tenant (workspace '{workspace_id}')"
                ),
            )

        # 使用提供的 display_name 和 description 更新配置（如果有）
        display_name = request.display_name or existing_config.get(
            "display_name",
            workspace_name,
        )
        description = request.description or existing_config.get("description")

        # 更新工作区配置
        workspace_info = WorkspaceInfo(
            id=workspace_id,
            name=workspace_name,
            display_name=display_name,
            description=description,
            created_at=datetime.fromisoformat(existing_config.get("created_at")),
            workspace_type=WorkspaceType.USER.value,
            lifecycle=WorkspaceLifecycle.PERSISTENT.value,
            biz_module=request.biz_module or existing_config.get("biz_module"),
        )

        # 写入更新后的配置
        await workspace_storage.write_file(
            ".dawei/workspace.json",
            json.dumps(workspace_info.to_dict(), indent=2, ensure_ascii=False),
        )
        logger.info(f"Updated existing workspace.json for {workspace_id}")
    else:
        # 创建 .dawei 目录结构
        await workspace_storage.create_directory(".dawei")
        await workspace_storage.create_directory(".dawei/chat-history")
        await workspace_storage.create_directory(".dawei/checkpoints")
        await workspace_storage.create_directory(".dawei/task_graphs")
        logger.info(f"Created .dawei directory structure in {workspace_path}")

        # 生成 UUID
        workspace_id = str(uuid.uuid4())

        # 创建工作区名称
        workspace_name = request.name or workspace_path.name

        # 创建工作区级配置 (.dawei/workspace.json)
        workspace_info = WorkspaceInfo(
            id=workspace_id,
            name=workspace_name,
            display_name=request.display_name or workspace_name,
            description=request.description,
            created_at=datetime.now(UTC),
            workspace_type=WorkspaceType.USER.value,
            lifecycle=WorkspaceLifecycle.PERSISTENT.value,
            biz_module=request.biz_module,
        )

        # 写入工作区级配置
        await workspace_storage.write_file(
            ".dawei/workspace.json",
            json.dumps(workspace_info.to_dict(), indent=2, ensure_ascii=False),
        )
        logger.info(f"Created workspace.json for {workspace_id}")

    # 更新系统级索引 (~/.normnomos/workspaces.json)
    _register_type = WorkspaceType.USER.value
    logger.info(f"About to call _register_workspace_in_system_index for {workspace_id} type={_register_type}")
    # owner_id / tenant_id 已在函数开头提取（服务端托管路径分配共用）
    await _register_workspace_in_system_index(
        workspace_id=workspace_id,
        name=workspace_name,
        display_name=request.display_name or workspace_name,
        path=str(workspace_path),
        workspace_type=_register_type,
        owner_user_id=owner_id,
        tenant_id=tenant_id,
        biz_module=request.biz_module,
    )
    logger.info(f"Finished _register_workspace_in_system_index for {workspace_id}")

    # Install market resources (team, skills, agents, mcps, knowledge)
    install_results = {}
    has_resources = request.team_id or request.skill_ids or request.agent_ids or request.mcp_ids or request.knowledge_ids
    if has_resources:
        # Backfill team_meta from the market API when only team_id was supplied
        # (mirrors /create-temp & /create compliance): install_team() is a no-op
        # without team_meta, which would silently skip the whole team install
        # (E2E 2026-09-03 gelu-research「原创论文」入口：201 但零安装).
        team_meta = request.team_meta
        if not team_meta and request.team_id:
            try:
                from dawei.workspace.resource_installer import resolve_team_meta

                team_meta = resolve_team_meta(request.team_id, token=market_token)
            except Exception as e:
                logger.warning(
                    "Failed to resolve team_meta for %s (%s): %s",
                    workspace_id, request.team_id, e,
                )
        try:
            from dawei.workspace.resource_installer import install_resources_to_workspace

            # 【2026-09-14 事件循环阻塞修复】同步重 IO → 线程池执行
            install_results = await asyncio.to_thread(
                install_resources_to_workspace,
                workspace_path=str(workspace_path),
                team_id=request.team_id,
                team_meta=team_meta,
                skill_ids=request.skill_ids,
                agent_ids=request.agent_ids,
                mcp_ids=request.mcp_ids,
                knowledge_ids=request.knowledge_ids,
                market_token=market_token,
            )
            logger.info(f"Resource install results for {workspace_id}: {install_results}")
        except Exception as e:
            logger.error(f"Failed to install resources for {workspace_id}: {e}", exc_info=True)
            # Don't fail the whole workspace creation, just log the error

    # 添加 path 到返回数据（内部使用）
    workspace_dict = workspace_info.to_dict()
    workspace_dict["path"] = str(workspace_path)

    # 🔒 安全：净化响应，移除绝对路径
    sanitized_workspace = sanitize_workspace_response(workspace_dict, remove_path=True)

    response = WorkspaceResponse(
        success=True,
        workspace=sanitized_workspace,
        message="工作区创建成功",
    )
    # Include install results in response for debugging/transparency
    if install_results:
        response_dict = response.model_dump()
        if install_results:
            response_dict["installed_resources"] = install_results
        return WorkspaceResponse(**response_dict)

    return response


async def _cleanup_workspace_directory(workspace_path: Path):
    """清理工作区目录中的 .dawei 配置

    Args:
        workspace_path: 工作区路径

    """
    # Fast Fail: 验证输入参数
    if workspace_path is None:
        logger.warning("Cleanup called with None workspace path, skipping")
        return

    if workspace_path.exists():
        import shutil

        dawei_path = workspace_path / ".dawei"
        if dawei_path.exists():
            try:
                shutil.rmtree(dawei_path)
                logger.info(f"Cleaned up .dawei directory at {dawei_path}")
            except OSError as e:
                logger.warning(f"Failed to cleanup workspace directory {workspace_path}: {e}")


async def _register_workspace_in_system_index(
    workspace_id: str,
    name: str,
    display_name: str,
    path: str,
    owner_user_id: str,
    workspace_type: str | None = None,
    tenant_id: str = "personal",
    biz_module: str | None = None,
):
    """在系统级索引中注册工作区

    更新 ~/.normnomos/workspaces.json
    """
    if workspace_type is None:
        workspace_type = WorkspaceType.USER.value

    system_storage = StorageProvider.get_system_storage()

    logger.info(f"Registering workspace {workspace_id} in workspaces.json")

    # 读取现有的 workspaces.json
    if await system_storage.exists("workspaces.json"):
        logger.info("workspaces.json exists, reading it...")
        content = await system_storage.read_file("workspaces.json")
        data = json.loads(content)
        logger.info(f"Current workspaces count: {len(data.get('workspaces', []))}")
    else:
        logger.info("workspaces.json does not exist, creating new one...")
        data = {"workspaces": []}

    # 幂等/去重：同一 id 已注册时合并更新，绝不重复 append。
    # （历史 bug：同一目录在不同租户上下文被重复注册成两条记录，
    #   导致两个账号的列表过滤都能命中、共享同一份消息。）
    existing_entries = [w for w in data.get("workspaces", []) if w.get("id") == workspace_id]
    if existing_entries:
        existing_owner = existing_entries[0].get("owner_user_id")
        if existing_owner not in (None, owner_user_id):
            # 已归属其他真实用户：拒绝抢占注册，保持隔离
            logger.warning(
                f"Workspace {workspace_id} already owned by {existing_owner}, "
                f"skip re-registration by {owner_user_id}"
            )
            return
        # 保留最早 created_at，去重后仅写回一条。
        # 身份保护：条目已归属真实用户时，绝不改写其 owner_user_id/tenant_id
        # （历史 bug：同一用户在个人身份下重注册，把租户工作区的 tenant_id
        #   覆盖成 personal，导致跨身份串数据。只有 owner 字段缺失的 legacy 无主条目可被认领。）
        existing_owner = existing_entries[0].get("owner_user_id")
        existing_tenant = existing_entries[0].get("tenant_id", "personal")
        if existing_owner is None:
            # 无主（legacy）条目：由当前调用者认领
            final_owner, final_tenant = owner_user_id, tenant_id
        elif existing_owner == owner_user_id and existing_tenant != tenant_id:
            # 同一用户、不同身份（个人 ↔ 租户）：保持原归属，防止身份抢占改写
            logger.warning(
                f"Workspace {workspace_id} owned by {existing_owner} tenant={existing_tenant}, "
                f"keep identity (caller tenant={tenant_id})"
            )
            final_owner, final_tenant = existing_owner, existing_tenant
        else:
            final_owner, final_tenant = existing_owner, existing_tenant
        oldest_created = min(w.get("created_at", datetime.now(UTC).isoformat()) for w in existing_entries)
        data["workspaces"] = [w for w in data["workspaces"] if w.get("id") != workspace_id]
        data["workspaces"].append(
            {
                "id": workspace_id,
                "name": name,
                "display_name": display_name,
                "path": path,
                "created_at": oldest_created,
                "is_active": True,
                "lifecycle": WorkspaceLifecycle.PERSISTENT.value,
                "workspace_type": workspace_type,
                "owner_user_id": final_owner,
                "tenant_id": final_tenant,
                # biz_module 未传时保留存量值（幂等更新不得抹掉模块归属）
                "biz_module": biz_module or existing_entries[0].get("biz_module"),
            },
        )
    else:
        # 添加新工作区（存储基础信息 + display_name + lifecycle + workspace_type）
        data["workspaces"].append(
            {
                "id": workspace_id,
                "name": name,
                "display_name": display_name,
                "path": path,
                "created_at": datetime.now(UTC).isoformat(),
                "is_active": True,
                "lifecycle": WorkspaceLifecycle.PERSISTENT.value,
                "workspace_type": workspace_type,
                "owner_user_id": owner_user_id,
                "tenant_id": tenant_id,
                **({"biz_module": biz_module} if biz_module else {}),
            },
        )

    logger.info(f"Writing workspaces.json with {len(data['workspaces'])} workspaces...")

    # 写回文件
    await system_storage.write_file(
        "workspaces.json",
        json.dumps(data, indent=2, ensure_ascii=False),
    )
    logger.info(f"Registered workspace {workspace_id} in workspaces.json")

    # 清除 StorageProvider 缓存并重新加载 WorkspaceManager
    StorageProvider.clear_system_storage_cache()
    from dawei.workspace.workspace_manager import workspace_manager

    workspace_manager.reload()
    logger.info(f"Reloaded workspace_manager after registering {workspace_id}")


def _derive_workspace_category(workspace_type: str) -> str:
    """从 workspace_type 字符串推导大类（计算字段，不持久化）。"""
    try:
        wt = WorkspaceType(workspace_type)
        return wt.category.value
    except ValueError:
        return WorkspaceCategory.GENERAL.value


def _inject_workspace_category(workspace: dict) -> dict:
    """注入 workspace_category 到工作区字典（计算字段）。"""
    workspace["workspace_category"] = _derive_workspace_category(
        workspace.get("workspace_type", "")
    )
    return workspace


# ==================== 读取工作区列表 API ====================


@router.get("/list", response_model=WorkspaceListResponse)
async def get_workspaces_list(
    request: Request,
    include_inactive: bool = Query(False, description="是否包含已停用的工作区"),
    lifecycle: str | None = Query(None, description="按生命周期筛选: persistent, temporary, archived"),
    workspace_type: str | None = Query(None, description="按类型筛选: user, simple_task, ip-idea-vault, compliance, ..."),
    workspace_category: str | None = Query(None, description="按大类筛选: general, ai_task, ip, compliance, law_firm"),
):
    """获取工作区列表（多租户：按 owner_user_id 过滤）

    数据来源：~/.normnomos/workspaces.json (系统级索引)
    端点: GET /api/workspaces/list
    """
    system_storage = StorageProvider.get_system_storage()

    # 读取系统级索引
    if not await system_storage.exists("workspaces.json"):
        return WorkspaceListResponse(success=True, workspaces=[], total=0)

    content = await system_storage.read_file("workspaces.json")
    data = json.loads(content)

    workspaces = data.get("workspaces", [])

    # 多租户：按 owner_user_id + tenant_id 过滤（物理隔离）
    # fail-closed：鉴权上下文提取失败时拒绝返回任何工作区，而不是放行全部
    try:
        from dawei.api.auth import get_authenticated_tenant_id, get_authenticated_user_id

        user_id = await get_authenticated_user_id(request)
        tenant_id = await get_authenticated_tenant_id(request)
    except HTTPException:
        raise  # 401（无效/缺失 token）直通，前端据此刷新或跳登录
    except Exception as e:
        logger.exception("Failed to resolve auth context for workspace list")
        raise HTTPException(status_code=500, detail="auth context unavailable") from e
    workspaces = [
        w for w in workspaces
        if w.get("owner_user_id") == user_id
        and w.get("tenant_id", "personal") == tenant_id
    ]

    # 过滤失效注册：目录已被删除的陈旧条目（与 workspace_manager.get_workspace_by_id
    # 的 _is_workspace_alive 存活检查保持一致）。否则列表展示死链工作区，
    # 前端选中后所有 by-id 调用（conversations 等）都会 404。
    workspaces = [w for w in workspaces if w.get("path") and Path(w["path"]).is_dir()]

    # 过滤活跃的工作区
    if not include_inactive:
        workspaces = [w for w in workspaces if w.get("is_active", True)]

    # 过滤生命周期
    if lifecycle:
        workspaces = [w for w in workspaces if w.get("lifecycle") == lifecycle]

    # 过滤工作区类型
    if workspace_type:
        workspaces = [w for w in workspaces if w.get("workspace_type") == workspace_type]

    # 过滤工作区大类（从 workspace_type 推导，不依赖存储字段）
    if workspace_category:
        workspaces = [
            w for w in workspaces
            if _derive_workspace_category(w.get("workspace_type", "")) == workspace_category
        ]

    # 注入 workspace_category 到响应中（计算字段，不持久化）
    sanitized_workspaces = [
        _inject_workspace_category(sanitize_workspace_response(ws, remove_path=False, keep_full_path=True))
        for ws in workspaces
    ]

    return WorkspaceListResponse(
        success=True,
        workspaces=sanitized_workspaces,
        total=len(sanitized_workspaces),
    )


@router.post("/create-temp", response_model=WorkspaceResponse, status_code=201)
async def create_temp_workspace(http_request: Request, request: CreateTempWorkspaceRequest | None = None):
    """创建临时工作空间

    临时工作空间用于常规任务和定时任务。
    标记 lifecycle=temporary，在 server 重启时自动清理无活跃任务的临时空间。

    扩展：当请求体携带 ``skill_ids`` / ``mcp_ids`` / ``team_id`` 等字段时，
    在临时工作空间创建完成后立即调用 ``install_resources_to_workspace``
    安装 Market 资源。安装失败不会回滚工作空间，只记录日志（与
    ``/create`` 一致）—— 这样上游服务（如 nn-flow orchestrator）可以在
    一次原子调用中得到一个带 Skills + MCP 配置的可执行工作空间。
    """
    # 提取身份（物理隔离用）—— 无有效登录直接 401，无匿名身份
    from dawei.api.auth import get_authenticated_tenant_id, get_authenticated_user_id
    from dawei.workspace.temp_workspace_manager import temp_workspace_manager

    owner_id = await get_authenticated_user_id(http_request)
    tenant_id = await get_authenticated_tenant_id(http_request)

    body = request or CreateTempWorkspaceRequest()
    display_name = body.display_name

    temp_ws = await temp_workspace_manager.create_temp_workspace(
        display_name=display_name,
        workspace_type=WorkspaceType.SIMPLE_TASK.value,
        owner_user_id=owner_id,
        tenant_id=tenant_id,
    )

    workspace_id = temp_ws["id"]
    workspace_path = temp_ws.get("path")

    # Install Market resources if any were requested.
    has_resources = (
        body.team_id
        or body.skill_ids
        or body.agent_ids
        or body.mcp_ids
        or body.knowledge_ids
    )
    install_results: dict[str, Any] | None = None
    if has_resources and workspace_path:
        market_token = _bearer_token(http_request)
        # Backfill team_meta from the market API when only team_id was supplied
        # (mirrors /create): install_team() is a no-op without team_meta, which
        # would silently skip the whole team install (E2E 2026-09-03 gelu-research).
        team_meta = body.team_meta
        if not team_meta and body.team_id:
            try:
                from dawei.workspace.resource_installer import resolve_team_meta

                team_meta = resolve_team_meta(body.team_id, token=market_token)
            except Exception as e:
                logger.warning(
                    "Failed to resolve team_meta for temp workspace %s (%s): %s",
                    workspace_id, body.team_id, e,
                )
        try:
            from dawei.workspace.resource_installer import install_resources_to_workspace

            # 【2026-09-14 事件循环阻塞修复】同步重 IO → 线程池执行
            install_results = await asyncio.to_thread(
                install_resources_to_workspace,
                workspace_path=str(workspace_path),
                team_id=body.team_id,
                team_meta=team_meta,
                skill_ids=body.skill_ids,
                agent_ids=body.agent_ids,
                mcp_ids=body.mcp_ids,
                knowledge_ids=body.knowledge_ids,
                market_token=market_token,
            )
            logger.info(
                "Resource install results for temp workspace %s: %s",
                workspace_id, install_results,
            )
        except Exception as e:
            logger.error(
                "Failed to install resources for temp workspace %s: %s",
                workspace_id, e, exc_info=True,
            )
            install_results = {"error": str(e)}

    response_workspace = {
        "id": workspace_id,
        "name": temp_ws["name"],
        "display_name": temp_ws["display_name"],
        "lifecycle": temp_ws["lifecycle"],
        "workspace_type": temp_ws["workspace_type"],
    }
    # Expose path for internal server-to-server callers that need to inspect
    # the workspace; sanitized away from regular users downstream.
    if workspace_path:
        response_workspace["path"] = str(workspace_path)

    return WorkspaceResponse(
        success=True,
        workspace=response_workspace,
        installed_resources=install_results,
        message="临时工作空间创建成功",
    )


# ==================== 读取工作区详情 API ====================


@router.get("/{workspace_id}/info", response_model=WorkspaceResponse)
async def get_workspace_info(workspace_id: str):
    """获取工作区详情

    数据来源：
    1. 从 workspaces.json 获取 path
    2. 从 {path}/.dawei/workspace.json 读取详细信息
    """
    system_storage = StorageProvider.get_system_storage()

    # 1. 从系统级索引获取工作区路径
    if not await system_storage.exists("workspaces.json"):
        raise HTTPException(status_code=404, detail="Workspace not found")

    content = await system_storage.read_file("workspaces.json")
    data = json.loads(content)

    workspace_basic = None
    for ws in data.get("workspaces", []):
        if ws["id"] == workspace_id:
            workspace_basic = ws
            break

    if not workspace_basic:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # 2. 从工作区级配置读取详细信息
    workspace_path = workspace_basic["path"]
    workspace_storage = StorageProvider.get_workspace_storage(workspace_path)

    workspace_info_path = ".dawei/workspace.json"
    if not await workspace_storage.exists(workspace_info_path):
        raise HTTPException(status_code=404, detail="Workspace config not found")

    workspace_content = await workspace_storage.read_file(workspace_info_path)
    workspace_info = json.loads(workspace_content)

    # 🔒 安全：净化工作区信息，移除绝对路径
    sanitized_info = sanitize_workspace_response(workspace_info, remove_path=True)

    return WorkspaceResponse(success=True, workspace=sanitized_info)


# ==================== 更新工作区 API ====================


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(workspace_id: str, request: UpdateWorkspaceRequest):
    """更新工作区信息

    同时更新系统级索引和工作区级配置
    """
    system_storage = StorageProvider.get_system_storage()

    # 1. 从系统级索引获取工作区路径
    content = await system_storage.read_file("workspaces.json")
    data = json.loads(content)

    workspace_basic = None
    for _i, ws in enumerate(data.get("workspaces", [])):
        if ws["id"] == workspace_id:
            workspace_basic = ws
            break

    if not workspace_basic:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # 2. 读取工作区级配置
    workspace_path = workspace_basic["path"]
    workspace_storage = StorageProvider.get_workspace_storage(workspace_path)

    workspace_content = await workspace_storage.read_file(".dawei/workspace.json")
    workspace_info = json.loads(workspace_content)

    # 3. 更新字段
    if request.display_name is not None:
        workspace_info["display_name"] = request.display_name
        # 同时更新系统级索引中的 display_name
        workspace_basic["display_name"] = request.display_name
    if request.description is not None:
        workspace_info["description"] = request.description
    if request.is_active is not None:
        workspace_info["is_active"] = request.is_active

    # 4. 写回工作区级配置
    await workspace_storage.write_file(
        ".dawei/workspace.json",
        json.dumps(workspace_info, indent=2, ensure_ascii=False),
    )
    logger.info(f"Updated workspace {workspace_id}")

    # 5. 更新系统级索引
    await system_storage.write_file(
        "workspaces.json",
        json.dumps(data, indent=2, ensure_ascii=False),
    )

    # 添加 path 到返回数据（内部使用）
    workspace_info["path"] = workspace_path

    # 🔒 安全：净化工作区信息，移除绝对路径
    sanitized_info = sanitize_workspace_response(workspace_info, remove_path=True)

    return WorkspaceResponse(success=True, workspace=sanitized_info)


# ==================== 删除工作区 API ====================


@router.delete("/{workspace_id}", response_model=WorkspaceResponse)
async def delete_workspace(
    workspace_id: str,
    delete_config: bool = Query(True, description="是否删除 .dawei 配置目录"),
    delete_files: bool = Query(False, description="是否删除整个工作区目录"),
):
    """删除工作区

    步骤：
    1. 从 workspaces.json 移除（系统级）
    2. 删除 .dawei 目录（工作区级，可选）
    3. 删除整个工作区目录（可选）
    """
    system_storage = StorageProvider.get_system_storage()

    # 1. 读取系统级索引
    content = await system_storage.read_file("workspaces.json")
    data = json.loads(content)

    workspace_basic = None
    workspace_index = -1
    for i, ws in enumerate(data.get("workspaces", [])):
        if ws["id"] == workspace_id:
            workspace_basic = ws
            workspace_index = i
            break

    if not workspace_basic:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_path = workspace_basic["path"]

    # 2. 删除 .dawei 目录（工作区级配置）
    if delete_config:
        workspace_storage = StorageProvider.get_workspace_storage(workspace_path)

        if await workspace_storage.exists(".dawei"):
            await workspace_storage.delete(".dawei", recursive=True)
            logger.info(f"Deleted .dawei directory for workspace {workspace_id}")

    # 3. 删除整个工作区目录（可选）
    if delete_files:
        # 注意：这需要使用父目录的 Storage
        parent_path = str(Path(workspace_path).parent)
        parent_storage = StorageProvider.get_workspace_storage(parent_path)
        workspace_dir_name = Path(workspace_path).name

        if await parent_storage.exists(workspace_dir_name):
            await parent_storage.delete(workspace_dir_name, recursive=True)
            logger.info(f"Deleted workspace directory: {workspace_path}")

    # 4. 从系统级索引移除
    data["workspaces"].pop(workspace_index)
    await system_storage.write_file(
        "workspaces.json",
        json.dumps(data, indent=2, ensure_ascii=False),
    )
    logger.info(f"Removed workspace {workspace_id} from workspaces.json")

    # 清除 StorageProvider 缓存并重新加载 WorkspaceManager
    StorageProvider.clear_system_storage_cache()
    from dawei.workspace.workspace_manager import workspace_manager

    workspace_manager.reload()
    logger.info(f"Reloaded workspace_manager after deleting {workspace_id}")

    return WorkspaceResponse(
        success=True,
        message="工作区已成功删除",
        workspace_id=workspace_id,
    )


# ==================== 清空工作区 API ====================


class ResetWorkspaceRequest(BaseModel):
    """清空工作区请求（危险操作）"""

    confirm: bool = Field(False, description="必须显式传 true 才执行清空（防误触/防 CSRF 式误调用）")


def _reset_workspace_on_disk(workspace_path: Path) -> dict[str, Any]:
    """同步磁盘清理：清除任务/日志/文件，保留工作区身份与配置。

    清除内容：
    - 任务数据：.dawei/{conversations,chat-history,task_graphs,task_nodes,checkpoints}
    - 日志/执行轨迹：.dawei/spans.db（含 WAL 边车）
    - 用户文件：工作区根目录下除 .dawei 外的全部文件/目录

    保留内容：.dawei/workspace.json（身份）、skills/MCP 等已安装资源配置。
    """
    import shutil

    from dawei.agentic.span_store import reset_span_store

    dawei_dir = workspace_path / ".dawei"

    # 1) 任务/对话数据目录 —— 删除内容并重建空目录（等同新建骨架）
    task_count = 0
    data_dirs = ["conversations", "chat-history", "task_graphs", "task_nodes", "checkpoints"]
    for name in data_dirs:
        target = dawei_dir / name
        if name == "conversations" and target.is_dir():
            task_count = len(list(target.glob("*.json")))
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True, exist_ok=True)

    # 2) 日志/执行轨迹 spans.db —— 删除并重建空库（含 schema）
    reset_span_store(workspace_path)

    # 3) 用户文件 —— 工作区根目录下除 .dawei 外全部删除
    file_count = 0
    for child in workspace_path.iterdir():
        if child.name == ".dawei":
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except OSError:
                continue
        file_count += 1

    return {"tasks_cleared": task_count, "files_cleared": file_count}


@router.post("/{workspace_id}/reset", response_model=WorkspaceResponse)
async def reset_workspace(
    workspace_id: str,
    request: ResetWorkspaceRequest | None = None,
    _access: None = Depends(require_workspace_access),
):
    """清空工作区（危险操作，需前端二次确认后调用）

    清除工作区下的任务、日志（执行轨迹）与文件，保留工作区身份与配置，
    等同于新建工作区的初始状态。工作区本身不会被删除，URL/ID 不变。
    """
    if not request or not request.confirm:
        raise HTTPException(
            status_code=400,
            detail='Dangerous operation: request body {"confirm": true} is required to reset a workspace',
        )

    from dawei.workspace import workspace_manager

    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_path = Path(workspace_info["path"])
    if not workspace_path.is_dir():
        raise HTTPException(
            status_code=404,
            detail="Workspace path does not exist or is not a directory",
        )

    # 重 IO（可能删除大量文件）放线程池执行，避免阻塞事件循环
    stats = await asyncio.to_thread(_reset_workspace_on_disk, workspace_path)
    logger.info(f"Reset workspace {workspace_id} at {workspace_path}: {stats}")

    return WorkspaceResponse(
        success=True,
        message=(
            f"工作区已清空（删除 {stats['tasks_cleared']} 个任务、"
            f"{stats['files_cleared']} 个文件/目录及全部执行日志）"
        ),
        workspace_id=workspace_id,
    )
