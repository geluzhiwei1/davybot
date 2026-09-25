# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""合规项目 API — 项目列表、详情、创建、配置

一个"合规项目" = 一个 workspace_type=compliance 的 workspace。
本模块封装 workspace 创建/查询逻辑，提供面向前端的简化接口。

端点：
  GET  /api/compliance/projects                          — 列出所有合规项目
  GET  /api/compliance/projects/config                   — 向导配置：domain 列表 + templates
  GET  /api/compliance/projects/{wid}                    — 项目详情
  POST /api/compliance/projects                          — 创建合规项目（支持空白项目）
  PUT  /api/compliance/projects/{wid}/investigation      — 保存摸底调查表
  GET  /api/compliance/projects/{wid}/investigation      — 读取摸底调查表
  POST /api/compliance/projects/{wid}/screen             — 执行制裁筛查
  GET  /api/compliance/projects/{wid}/screening-results  — 历史筛查结果
  POST /api/compliance/projects/{wid}/stages/{stage}/run — 触发阶段执行（PDCA）
  GET  /api/compliance/projects/{wid}/stages/{stage}/runs— 阶段执行历史
  GET  /api/compliance/projects/{wid}/risk-summary       — 风险摘要
  POST /api/compliance/projects/{wid}/materials          — 上传材料
  GET  /api/compliance/projects/{wid}/materials          — 列出材料
  DELETE /api/compliance/projects/{wid}/materials/{mid}  — 删除材料
  POST /api/compliance/projects/{wid}/agent-teams        — 添加智能体团队
  GET  /api/compliance/projects/{wid}/agent-teams        — 列出智能体团队
  DELETE /api/compliance/projects/{wid}/agent-teams/{slug} — 移除智能体团队
  PUT  /api/compliance/projects/{wid}/contract-clauses   — 保存合同条款
  GET  /api/compliance/projects/{wid}/contract-clauses   — 读取合同条款
  POST /api/compliance/projects/{wid}/contract-clauses/review — 触发合同审核
  GET  /api/compliance/projects/{wid}/contract-clauses/reviews — 审核历史
  POST /api/compliance/projects/{wid}/ethics-plan/generate    — 生成 Ethics Plan
  GET  /api/compliance/projects/{wid}/ethics-plan             — 获取 Ethics Plan
"""

import asyncio
import json
import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File, Form
from pydantic import BaseModel, Field

from dawei.core.path_security import sanitize_workspace_response
from dawei.storage.storage_provider import StorageProvider
from dawei_biz.services.compliance_template import ComplianceTemplateManager
from dawei.workspace.models import WorkspaceType

logger = logging.getLogger(__name__)

router = APIRouter(tags=["compliance-projects"])

# ─── Domain 元数据（从 index.yaml 的 category 推导） ──────────────────

_DOMAIN_META: dict[str, dict[str, str]] = {
    "sanctions": {"label": "制裁合规", "icon": "shield", "color": "red",
                   "desc": "OFAC/EU/UN/UK 制裁名单筛查、交易链审计、ICP内控"},
    "supply-chain": {"label": "供应链合规", "icon": "link", "color": "orange",
                      "desc": "UFLPA、冲突矿产、供应链尽调、强迫劳动风险"},
    "data": {"label": "数据合规", "icon": "database", "color": "blue",
             "desc": "PIPL、GDPR、数据出境、个人信息保护"},
    "export-control": {"label": "出口管制", "icon": "ship", "color": "amber",
                       "desc": "EAR/ECCN、ITAR、FDPR、De Minimis"},
    "anti-bribery": {"label": "反商业贿赂", "icon": "handshake", "color": "purple",
                     "desc": "FCPA、反不正当竞争、第三方尽调"},
    "antitrust": {"label": "反垄断", "icon": "scale", "color": "indigo",
                  "desc": "经营者集中申报、市场支配地位、垄断协议"},
    "esg": {"label": "ESG合规", "icon": "leaf", "color": "green",
            "desc": "CBAM碳关税、CSRD披露、EU分类法"},
    "labor": {"label": "劳动合规", "icon": "users", "color": "cyan",
              "desc": "劳动合同、用工管理、解雇、跨境用工"},
    "ip-compliance": {"label": "知识产权合规", "icon": "lightbulb", "color": "violet",
                      "desc": "专利、商标、著作权、FTO分析、开源合规"},
    "overseas-investment": {"label": "境外投资", "icon": "globe", "color": "pink",
                            "desc": "ODI备案、CFIUS审查、EU FDI筛选"},
    "overseas-tax": {"label": "海外税务", "icon": "receipt", "color": "yellow",
                     "desc": "转让定价、PE风险、CFC、数字税"},
    "product-quality": {"label": "产品质量", "icon": "check-circle", "color": "teal",
                        "desc": "产品认证、召回、市场准入"},
}

_VALID_LIFECYCLE_STAGES = {"initiation", "screening", "monitoring", "reporting", "exit"}
_VALID_MATERIAL_CATEGORIES = {"contracts", "bidding", "financials", "certificates", "misc"}

# ─── 请求/响应模型 ──────────────────────────────────────────────────


class CreateProjectRequest(BaseModel):
    """创建合规项目请求（支持空白项目 — template_slug 可为 null）"""

    project_name: str = Field(..., description="项目名称")
    template_slug: str | None = Field(None, description="合规模板 slug；null=空白项目")
    domain: str | None = Field(None, description="合规域；空白项目可省略")
    form_data: dict[str, Any] = Field(default_factory=dict, description="表单数据")
    description: str | None = Field(None, description="项目描述")
    team_id: str | None = Field(None, description="Market 团队 ID（可选）")


class ProjectInfo(BaseModel):
    """合规项目信息（列表项）"""

    workspace_id: str
    name: str
    display_name: str
    domain: str
    domain_label: str
    template_slug: str | None = None
    template_name: str | None = None
    description: str | None = None
    created_at: str | None = None
    evolution_enabled: bool = False
    current_phase: str | None = None
    cycle_count: int = 0
    lifecycle_stage: str = "initiation"
    risk_level: str | None = None
    materials_count: int = 0
    agent_teams: list[str] = []


class InvestigationData(BaseModel):
    """摸底调查表数据（部分或完整）"""

    project_info: dict[str, Any] = Field(default_factory=dict)
    parties: list[dict[str, Any]] = Field(default_factory=list)
    logistics: dict[str, Any] = Field(default_factory=dict)
    financials: dict[str, Any] = Field(default_factory=dict)


class ContractClausesData(BaseModel):
    """合同条款数据"""

    contract_info: dict[str, Any] = Field(default_factory=dict)
    definitions: list[dict[str, Any]] = Field(default_factory=list)
    commitments: list[dict[str, Any]] = Field(default_factory=list)
    system_requirements: dict[str, Any] = Field(default_factory=dict)


class AddAgentTeamRequest(BaseModel):
    """添加智能体团队"""

    team_slug: str = Field(..., description="Market 团队 slug，如 sanctions-team")
    team_id: str | None = Field(None, description="完整 team_id（可选）")


class RunStageRequest(BaseModel):
    """触发阶段执行"""

    lifecycle_stage: str = Field(..., description="initiation/screening/monitoring/reporting/exit")
    notes: str | None = Field(None, description="用户备注")


# ─── 辅助函数 ──────────────────────────────────────────────────────


async def _read_workspaces_index() -> list[dict[str, Any]]:
    """读取系统级 workspaces.json，返回所有 workspace 记录"""
    system_storage = StorageProvider.get_system_storage()
    if not await system_storage.exists("workspaces.json"):
        return []
    content = await system_storage.read_file("workspaces.json")
    data = json.loads(content)
    return data.get("workspaces", [])


async def _read_workspace_config(workspace_path: str) -> dict[str, Any]:
    """读取工作区级 .dawei/workspace.json"""
    workspace_storage = StorageProvider.get_workspace_storage(workspace_path)
    if not await workspace_storage.exists(".dawei/workspace.json"):
        return {}
    content = await workspace_storage.read_file(".dawei/workspace.json")
    return json.loads(content)


async def _get_evolution_status(workspace_path: str) -> dict[str, Any]:
    """读取 evolution.json 状态"""
    ev_path = Path(workspace_path) / ".dawei" / "evolution.json"
    if not ev_path.exists():
        return {"enabled": False, "current_phase": None, "cycle_count": 0}
    try:
        return json.loads(ev_path.read_text(encoding="utf-8"))
    except Exception:
        return {"enabled": False, "current_phase": None, "cycle_count": 0}


async def _count_evolution_cycles(workspace_path: str) -> int:
    """统计 evolution cycle 数量"""
    ev_dir = Path(workspace_path) / ".dawei"
    count = 0
    if ev_dir.exists():
        for item in ev_dir.iterdir():
            if item.is_dir() and item.name.startswith("evolution-"):
                count += 1
    return count


def _get_latest_plan_summary(workspace_path: str) -> dict[str, Any] | None:
    """读取最新的 plan 文件摘要"""
    plans_dir = Path(workspace_path) / ".dawei" / "plans"
    if not plans_dir.exists():
        return None
    plan_files = sorted(plans_dir.glob("*.md"), reverse=True)
    if not plan_files:
        return None
    latest = plan_files[0]
    try:
        content = latest.read_text(encoding="utf-8")
        title = ""
        for line in content.split("\n"):
            if line.startswith("#"):
                title = line.lstrip("#").strip()
                break
        return {
            "filename": latest.name,
            "title": title,
            "content": content,
            "size": len(content),
        }
    except Exception:
        return None


def _resolve_team_id_from_template(template_slug: str) -> str | None:
    """从模板的 team_slug 字段推导 market team_id"""
    if not template_slug:
        return None
    manager = ComplianceTemplateManager()
    template = manager.load_template(template_slug)
    if not template:
        return None
    t = template.get("template", template)
    team_slug = t.get("team_slug")
    if team_slug:
        return f"team/{team_slug}"
    return None


def _get_project_template_agent_teams(template_slug: str) -> list[str]:
    """从项目模板中获取预装的智能体团队 slug 列表"""
    if not template_slug or not template_slug.startswith("project-"):
        return []
    manager = ComplianceTemplateManager()
    template = manager.load_template(template_slug)
    if not template:
        return []
    t = template.get("template", template)
    return t.get("agent_teams", [])


async def _resolve_workspace_path(workspace_id: str) -> str:
    """根据 workspace_id 查找路径，找不到则抛 404"""
    all_workspaces = await _read_workspaces_index()
    for w in all_workspaces:
        if w.get("id") == workspace_id:
            path = w.get("path", "")
            if path:
                return path
    raise HTTPException(status_code=404, detail="Project not found")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json_file(path: Path) -> dict[str, Any] | None:
    """安全读取 JSON 文件"""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json_file(path: Path, data: dict[str, Any]) -> None:
    """安全写入 JSON 文件（自动创建父目录）"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _list_screening_results(ws_path: str) -> list[dict[str, Any]]:
    """列出筛查结果目录下的所有结果（按时间倒序）"""
    results_dir = Path(ws_path) / "output" / "screening_results"
    if not results_dir.exists():
        return []
    results = []
    for f in sorted(results_dir.glob("*.json"), reverse=True):
        data = _read_json_file(f)
        if data:
            results.append({
                "screening_id": data.get("screening_id", f.stem),
                "screened_at": data.get("screened_at", ""),
                "overall_risk": data.get("overall_risk"),
                "parties_screened": data.get("parties_screened", 0),
                "total_hits": data.get("total_hits", 0),
                "filename": f.name,
            })
    return results


def _list_materials(ws_path: str) -> list[dict[str, Any]]:
    """列出已上传的材料"""
    materials_dir = Path(ws_path) / "input" / "materials"
    if not materials_dir.exists():
        return []
    materials = []
    for category_dir in materials_dir.iterdir():
        if not category_dir.is_dir():
            continue
        for f in category_dir.iterdir():
            if f.is_file():
                stat = f.stat()
                materials.append({
                    "material_id": f.stem,
                    "filename": f.name,
                    "category": category_dir.name,
                    "size": stat.st_size,
                    "uploaded_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                })
    materials.sort(key=lambda m: m.get("uploaded_at", ""), reverse=True)
    return materials


def _count_materials(ws_path: str) -> int:
    """统计材料数量"""
    materials_dir = Path(ws_path) / "input" / "materials"
    if not materials_dir.exists():
        return 0
    return sum(1 for f in materials_dir.rglob("*") if f.is_file())


def _get_compliance_metadata(ws_config: dict[str, Any]) -> dict[str, Any]:
    """从 workspace.json 提取 compliance 元数据"""
    metadata = ws_config.get("metadata", {})
    return metadata.get("compliance", {})


def _update_compliance_metadata(ws_path: str, updates: dict[str, Any]) -> dict[str, Any]:
    """更新 workspace.json 中的 compliance 元数据"""
    config_path = Path(ws_path) / ".dawei" / "workspace.json"
    config = _read_json_file(config_path) or {}
    metadata = config.setdefault("metadata", {})
    compliance = metadata.setdefault("compliance", {})
    compliance.update(updates)
    _write_json_file(config_path, config)
    return compliance


# ─── API 端点：项目管理 ──────────────────────────────────────────────


@router.get("/projects")
async def list_projects(request: Request, domain: str | None = Query(None, description="按合规域过滤")):
    """列出所有合规项目"""
    domain_filter_val = domain

    all_workspaces = await _read_workspaces_index()

    # 多租户过滤（无有效登录直接 401；owner 缺失的 legacy 无主工作区不可见）
    from dawei.api.auth import get_authenticated_user_id

    user_id = await get_authenticated_user_id(request)
    all_workspaces = [
        w for w in all_workspaces
        if w.get("owner_user_id") == user_id
    ]

    # 过滤合规类型
    compliance_workspaces = [
        w for w in all_workspaces
        if w.get("workspace_type") == WorkspaceType.COMPLIANCE_PROJECT.value
    ]

    projects: list[dict[str, Any]] = []
    for ws in compliance_workspaces:
        ws_path = ws.get("path", "")
        ws_config = await _read_workspace_config(ws_path) if ws_path else {}
        metadata = ws_config.get("metadata", {})
        compliance_meta = metadata.get("compliance", {})
        template_slug = compliance_meta.get("template_slug") or metadata.get("compliance_template", "")

        # 推导 domain
        project_domain = compliance_meta.get("domain", "")
        if not project_domain and template_slug:
            for d in _DOMAIN_META:
                if template_slug.startswith(d):
                    project_domain = d
                    break

        # 按域过滤
        if domain_filter_val and project_domain != domain_filter_val:
            continue

        ev_status = await _get_evolution_status(ws_path) if ws_path else {}
        cycle_count = await _count_evolution_cycles(ws_path) if ws_path else 0

        domain_info = _DOMAIN_META.get(project_domain, {})
        materials_count = _count_materials(ws_path) if ws_path else 0
        agent_teams = compliance_meta.get("agent_teams", [])

        projects.append({
            "workspace_id": ws.get("id", ""),
            "name": ws.get("name", ""),
            "display_name": ws.get("display_name", ws.get("name", "")),
            "domain": project_domain,
            "domain_label": domain_info.get("label", project_domain),
            "template_slug": template_slug or None,
            "template_name": ws_config.get("display_name", ""),
            "description": ws.get("description") or ws_config.get("description", ""),
            "created_at": ws.get("created_at", ""),
            "evolution_enabled": ev_status.get("enabled", False),
            "current_phase": ev_status.get("current_phase"),
            "cycle_count": cycle_count,
            "lifecycle_stage": compliance_meta.get("lifecycle_stage", "initiation"),
            "risk_level": compliance_meta.get("risk_level"),
            "materials_count": materials_count,
            "agent_teams": agent_teams,
        })

    projects.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return {"projects": projects, "total": len(projects)}


@router.get("/projects/config")
async def get_projects_config():
    """获取项目创建向导配置：项目模板 + domain 列表 + 各 domain 的单域模板

    返回结构：
    - project_templates: 项目合规模板（纵向复合型，覆盖多域）
    - domains: 合规域列表（用于高级选项/单域分析）
    - templates: 按域分组的单域分析模板
    """
    manager = ComplianceTemplateManager()

    # 项目合规模板（纵向复合型）
    project_templates = manager.list_project_templates()

    # 单域分析模板（高级选项）
    all_templates = manager.list_templates()

    templates_by_domain: dict[str, list[dict[str, Any]]] = {}
    for t in all_templates:
        category = t.get("category", "")
        if category not in templates_by_domain:
            templates_by_domain[category] = []
        templates_by_domain[category].append({
            "slug": t.get("slug", ""),
            "name": t.get("name", ""),
            "description": t.get("description", ""),
            "estimated_time": t.get("estimated_time", ""),
            "team_slug": t.get("team_slug", ""),
        })

    domains: list[dict[str, Any]] = []
    for key, meta in _DOMAIN_META.items():
        tmpl_count = len(templates_by_domain.get(key, []))
        domains.append({
            "key": key,
            "label": meta["label"],
            "icon": meta["icon"],
            "color": meta["color"],
            "desc": meta["desc"],
            "template_count": tmpl_count,
        })

    for cat in templates_by_domain:
        if cat not in _DOMAIN_META:
            domains.append({
                "key": cat,
                "label": cat,
                "icon": "folder",
                "color": "gray",
                "desc": "",
                "template_count": len(templates_by_domain[cat]),
            })

    domains.sort(key=lambda d: d["template_count"], reverse=True)

    return {
        "project_templates": project_templates,
        "domains": domains,
        "templates": templates_by_domain,
        "total_project_templates": len(project_templates),
        "total_templates": len(all_templates),
    }


@router.get("/projects/{workspace_id}")
async def get_project_detail(workspace_id: str, request: Request):
    """获取合规项目详情（扩展版 — 含 lifecycle/risk/materials/agent_teams）"""
    ws_path = await _resolve_workspace_path(workspace_id)
    ws_basic = None
    all_workspaces = await _read_workspaces_index()
    for w in all_workspaces:
        if w.get("id") == workspace_id:
            ws_basic = w
            break

    ws_config = await _read_workspace_config(ws_path)
    metadata = ws_config.get("metadata", {})
    compliance_meta = metadata.get("compliance", {})
    template_slug = compliance_meta.get("template_slug") or metadata.get("compliance_template", "")

    project_domain = compliance_meta.get("domain", "")
    if not project_domain and template_slug:
        for d in _DOMAIN_META:
            if template_slug.startswith(d):
                project_domain = d
                break

    ev_status = await _get_evolution_status(ws_path)
    cycle_count = await _count_evolution_cycles(ws_path)
    plan_summary = _get_latest_plan_summary(ws_path)

    template_detail = None
    if template_slug:
        manager = ComplianceTemplateManager()
        tmpl = manager.load_template(template_slug)
        if tmpl:
            t = tmpl.get("template", tmpl)
            template_detail = {
                "slug": t.get("slug", ""),
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "team_slug": t.get("team_slug", ""),
                "checklist_count": len(t.get("checklists", [])),
                "phases": t.get("phases", []),
            }

    checklists_dir = Path(ws_path) / "input" / "checklists"
    checklist_files: list[dict[str, Any]] = []
    if checklists_dir.exists():
        for f in checklists_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                checklist_files.append({
                    "slug": f.stem,
                    "name": data.get("name", f.stem),
                    "item_count": len(data.get("items", [])),
                })
            except Exception:
                pass

    domain_info = _DOMAIN_META.get(project_domain, {})
    materials = _list_materials(ws_path)
    screening_results = _list_screening_results(ws_path)

    return {
        "workspace_id": workspace_id,
        "name": ws_basic.get("name", "") if ws_basic else "",
        "display_name": ws_basic.get("display_name", "") if ws_basic else "",
        "description": ws_basic.get("description", "") if ws_basic else "",
        "created_at": ws_basic.get("created_at", "") if ws_basic else "",
        "domain": project_domain,
        "domain_label": domain_info.get("label", project_domain),
        "template_slug": template_slug or None,
        "template": template_detail,
        "evolution": {
            "enabled": ev_status.get("enabled", False),
            "current_phase": ev_status.get("current_phase"),
            "cycle_count": cycle_count,
            "goals": ev_status.get("goals", []),
        },
        "plan": plan_summary,
        "checklists": checklist_files,
        "compliance": {
            "lifecycle_stage": compliance_meta.get("lifecycle_stage", "initiation"),
            "risk_level": compliance_meta.get("risk_level"),
            "materials_count": len(materials),
            "agent_teams": compliance_meta.get("agent_teams", []),
        },
        "materials": materials,
        "screening_results": screening_results,
    }


@router.post("/projects")
async def create_project(req: CreateProjectRequest, http_request: Request):
    """创建合规项目（支持空白项目 — template_slug=null）

    空白项目：不选模板、不关联域、不加载智能体团队。
    后续通过 materials 上传、agent-teams 添加逐步构建。
    """
    from dawei.api.auth import extract_market_token
    from dawei.api.workspaces.crud import (
        CreateWorkspaceRequest,
        _create_compliance_workspace,
    )

    market_token = extract_market_token(http_request)

    # 推导 team_id（空白项目时为 None）
    team_id = req.team_id
    if not team_id and req.template_slug:
        team_id = _resolve_team_id_from_template(req.template_slug)

    # 构造 workspace 创建请求
    ws_req = CreateWorkspaceRequest(
        display_name=req.project_name,
        description=req.description or f"合规项目：{req.project_name}",
        compliance_template=req.template_slug or "",
        compliance_form_data=req.form_data,
        team_id=team_id,
    )

    ws_response = await _create_compliance_workspace(ws_req, market_token=market_token)

    if not ws_response.success:
        raise HTTPException(
            status_code=500,
            detail=ws_response.error or "Failed to create compliance workspace",
        )

    workspace_data = ws_response.workspace or {}
    workspace_id = workspace_data.get("id", "")

    if not workspace_id:
        raise HTTPException(status_code=500, detail="Workspace created but ID missing")

    # 写入 compliance 元数据（含空白项目标记）
    try:
        all_workspaces = await _read_workspaces_index()
        ws_path = None
        for w in all_workspaces:
            if w.get("id") == workspace_id:
                ws_path = w.get("path")
                break

        if ws_path:
            # 项目模板：预装多个智能体团队
            agent_teams_to_install: list[str] = []
            if req.template_slug and req.template_slug.startswith("project-"):
                agent_teams_to_install = _get_project_template_agent_teams(req.template_slug)

            _update_compliance_metadata(ws_path, {
                "template_slug": req.template_slug,
                "domain": req.domain,
                "lifecycle_stage": "initiation",
                "risk_level": None,
                "materials_count": 0,
                "agent_teams": agent_teams_to_install,
            })

            # 安装智能体团队资源（best-effort）
            if agent_teams_to_install:
                from dawei.api.auth import extract_market_token as _extract_token
                _market_token = _extract_token(http_request)
                for team_slug in agent_teams_to_install:
                    try:
                        from dawei.workspace.resource_installer import install_resources_to_workspace
                        # 【2026-09-14 事件循环阻塞修复】同步重 IO → 线程池执行
                        await asyncio.to_thread(
                            install_resources_to_workspace,
                            workspace_path=ws_path,
                            team_id=f"team/{team_slug}",
                            team_meta=None,
                            market_token=_market_token,
                        )
                        logger.info(
                            "[COMPLIANCE_PROJECT] Installed agent team %s for workspace %s",
                            team_slug,
                            workspace_id,
                        )
                    except Exception as e:
                        logger.warning(
                            "[COMPLIANCE_PROJECT] Failed to install agent team %s: %s",
                            team_slug,
                            e,
                        )
    except Exception as e:
        logger.warning("[COMPLIANCE_PROJECT] Failed to write compliance metadata: %s", e)

    # 自动启用 evolution（best-effort）
    evolution_result: dict[str, Any] = {"enabled": False}
    try:
        all_workspaces = await _read_workspaces_index()
        ws_path = None
        for w in all_workspaces:
            if w.get("id") == workspace_id:
                ws_path = w.get("path")
                break

        if ws_path:
            ev_config_path = Path(ws_path) / ".dawei" / "evolution.json"
            ev_config_path.parent.mkdir(parents=True, exist_ok=True)
            ev_config = {
                "enabled": True,
                "schedule": "manual",
                "goals": [],
                "auto_trigger": True,
            }
            ev_config_path.write_text(
                json.dumps(ev_config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            evolution_result = {"enabled": True, "config": ev_config}
            logger.info(
                "[COMPLIANCE_PROJECT] Auto-enabled evolution for workspace %s",
                workspace_id,
            )
    except Exception as e:
        logger.warning(
            "[COMPLIANCE_PROJECT] Failed to auto-enable evolution for %s: %s",
            workspace_id,
            e,
        )

    # 初始化 input 目录结构
    try:
        all_workspaces = await _read_workspaces_index()
        ws_path = None
        for w in all_workspaces:
            if w.get("id") == workspace_id:
                ws_path = w.get("path")
                break
        if ws_path:
            for subdir in ["input/materials/contracts", "input/materials/bidding",
                           "input/materials/financials", "input/materials/certificates",
                           "input/materials/misc", "output/screening_results",
                           "output/contract_review", "reports"]:
                (Path(ws_path) / subdir).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning("[COMPLIANCE_PROJECT] Failed to init directories: %s", e)

    return {
        "success": True,
        "workspace_id": workspace_id,
        "project_name": req.project_name,
        "domain": req.domain,
        "template_slug": req.template_slug,
        "is_blank": req.template_slug is None,
        "evolution": evolution_result,
        "installed_resources": ws_response.installed_resources,
        "compliance_init": ws_response.compliance_init,
        "message": "合规项目创建成功",
    }


# ─── API 端点：摸底调查表 ────────────────────────────────────────────


@router.put("/projects/{workspace_id}/investigation")
async def save_investigation(workspace_id: str, data: InvestigationData):
    """保存/更新摸底调查表"""
    ws_path = await _resolve_workspace_path(workspace_id)

    # 读取现有数据（合并）
    inv_path = Path(ws_path) / "input" / "investigation.json"
    existing = _read_json_file(inv_path) or {}

    merged = existing.copy()
    merged.update({
        "version": existing.get("version", "1.0"),
        "updated_at": _now_iso(),
        "project_info": {**existing.get("project_info", {}), **data.project_info},
        "parties": data.parties if data.parties else existing.get("parties", []),
        "logistics": {**existing.get("logistics", {}), **data.logistics},
        "financials": {**existing.get("financials", {}), **data.financials},
    })

    # 初始化风险维度（首次保存时）
    if "risk_dimensions" not in merged:
        merged["risk_dimensions"] = {
            "counterparty": {"status": "pending", "risk_level": None, "last_checked": None},
            "country": {"status": "pending", "risk_level": None, "last_checked": None},
            "item": {"status": "pending", "risk_level": None, "last_checked": None},
            "end_use": {"status": "pending", "risk_level": None, "last_checked": None},
            "banking": {"status": "pending", "risk_level": None, "last_checked": None},
        }

    _write_json_file(inv_path, merged)

    parties_count = len(merged.get("parties", []))
    _update_compliance_metadata(ws_path, {"parties_count": parties_count})

    return {
        "success": True,
        "investigation": merged,
        "parties_count": parties_count,
    }


@router.get("/projects/{workspace_id}/investigation")
async def get_investigation(workspace_id: str):
    """读取摸底调查表"""
    ws_path = await _resolve_workspace_path(workspace_id)
    inv_path = Path(ws_path) / "input" / "investigation.json"
    data = _read_json_file(inv_path)

    if not data:
        return {"investigation": None, "exists": False, "parties_count": 0}

    return {
        "investigation": data,
        "exists": True,
        "parties_count": len(data.get("parties", [])),
    }


# ─── API 端点：制裁筛查 ─────────────────────────────────────────────


@router.post("/projects/{workspace_id}/screen")
async def screen_project_parties(workspace_id: str, request: Request):
    """对摸底调查表中的全部 parties 执行制裁筛查

    调用 sanctions-knowledge (:8012) 的 POST /api/v1/screen 端点。
    """
    ws_path = await _resolve_workspace_path(workspace_id)

    # 读取摸底调查表
    inv_path = Path(ws_path) / "input" / "investigation.json"
    inv_data = _read_json_file(inv_path)
    if not inv_data or not inv_data.get("parties"):
        raise HTTPException(status_code=400, detail="摸底调查表为空或无交易对象，无法筛查")

    parties = inv_data["parties"]

    # 调用 sanctions-knowledge
    try:
        from dawei.core import local_context
        from dawei_biz.tools._service_client import sanctions_client

        # 注入 JWT
        try:
            from dawei.api.auth import get_authenticated_user_id
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                local_context.set_auth_token(auth_header[7:])
        except Exception:
            pass

        results = []
        total_hits = 0
        risk_levels = []

        for party in parties:
            party_name = party.get("name", "")
            if not party_name:
                continue

            screen_body = {
                "name": party_name,
                "entity_type": party.get("entity_type", "company"),
            }
            if party.get("identifiers"):
                screen_body["identifiers"] = party["identifiers"]

            try:
                resp = await sanctions_client.post(
                    "/api/v1/screen", json_body=screen_body, timeout=45,
                )
                risk_level = resp.get("risk_level", "unknown") if resp else "unknown"
                matches = resp.get("matches", []) if resp else []
            except Exception as e:
                logger.warning("[SCREEN] Failed to screen %s: %s", party_name, e)
                risk_level = "unknown"
                matches = []

            hits = len(matches)
            total_hits += hits
            risk_levels.append(risk_level)

            results.append({
                "party_id": party.get("party_id", ""),
                "party_name": party_name,
                "risk_level": risk_level,
                "matches": matches,
                "hit_count": hits,
            })

        # 汇总风险等级
        risk_priority = {"red": 4, "yellow+": 3, "yellow": 2, "green": 1, "unknown": 0}
        overall_risk = max(risk_levels, key=lambda r: risk_priority.get(r, 0)) if risk_levels else "unknown"

        screening_id = f"screen-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        screening_result = {
            "screening_id": screening_id,
            "screened_at": _now_iso(),
            "triggered_by": "user",
            "parties_screened": len(results),
            "total_hits": total_hits,
            "overall_risk": overall_risk,
            "results": results,
        }

        # 保存筛查结果
        results_path = Path(ws_path) / "output" / "screening_results" / f"{screening_id}.json"
        _write_json_file(results_path, screening_result)

        # 更新 workspace 元数据
        _update_compliance_metadata(ws_path, {
            "risk_level": overall_risk,
            "last_screened_at": _now_iso(),
        })

        return screening_result

    except ImportError:
        raise HTTPException(status_code=503, detail="sanctions-knowledge 服务不可用")
    except Exception as e:
        logger.error("[SCREEN] Screening failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"筛查失败: {e}")


@router.get("/projects/{workspace_id}/screening-results")
async def get_screening_results(workspace_id: str):
    """查询历史筛查结果列表"""
    ws_path = await _resolve_workspace_path(workspace_id)
    results = _list_screening_results(ws_path)
    return {"results": results, "total": len(results)}


@router.get("/projects/{workspace_id}/screening-results/{screening_id}")
async def get_screening_detail(workspace_id: str, screening_id: str):
    """查询单次筛查详情"""
    ws_path = await _resolve_workspace_path(workspace_id)
    result_path = Path(ws_path) / "output" / "screening_results" / f"{screening_id}.json"
    data = _read_json_file(result_path)
    if not data:
        raise HTTPException(status_code=404, detail="Screening result not found")
    return data


# ─── API 端点：阶段执行（PDCA） ─────────────────────────────────────


@router.post("/projects/{workspace_id}/stages/{stage}/run")
async def run_stage(workspace_id: str, stage: str, req: RunStageRequest, request: Request):
    """触发某阶段执行（创建 Evolution PDCA Cycle）

    内部调用 POST /api/workspaces/{wid}/evolution/trigger
    """
    if stage not in _VALID_LIFECYCLE_STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {stage}. Valid: {_VALID_LIFECYCLE_STAGES}")

    ws_path = await _resolve_workspace_path(workspace_id)

    # 更新 lifecycle_stage
    _update_compliance_metadata(ws_path, {"lifecycle_stage": stage})

    # 触发 evolution cycle
    try:
        from dawei.api.workspaces.evolution import trigger_evolution_cycle

        cycle_result = await trigger_evolution_cycle(
            workspace_id=workspace_id,
            workspace_path=ws_path,
            mode=stage,  # plan/do/check/act 映射在 evolution 内部
            goals=[req.notes] if req.notes else [],
        )
        return {
            "success": True,
            "workspace_id": workspace_id,
            "lifecycle_stage": stage,
            "cycle": cycle_result,
            "message": f"阶段 {stage} 执行已触发",
        }
    except ImportError:
        # Fallback: 直接调 evolution API
        pass
    except Exception as e:
        logger.warning("[STAGE_RUN] Direct trigger failed: %s, trying API", e)

    # Fallback: 通过 HTTP 内部调用
    try:
        from dawei.api.auth import get_token_from_request
        token = get_token_from_request(request)
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"http://localhost:8010/api/workspaces/{workspace_id}/evolution/trigger",
                headers={"Authorization": f"Bearer {token}"} if token else {},
                json={"goals": [req.notes] if req.notes else []},
                timeout=30,
            )
            if resp.status_code == 200:
                return {
                    "success": True,
                    "workspace_id": workspace_id,
                    "lifecycle_stage": stage,
                    "cycle": resp.json(),
                    "message": f"阶段 {stage} 执行已触发（via API）",
                }
            else:
                raise HTTPException(status_code=500, detail=f"Evolution trigger failed: {resp.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"触发阶段执行失败: {e}")


@router.get("/projects/{workspace_id}/stages/{stage}/runs")
async def get_stage_runs(workspace_id: str, stage: str):
    """查询某阶段历史执行记录"""
    if stage not in _VALID_LIFECYCLE_STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {stage}")

    ws_path = await _resolve_workspace_path(workspace_id)
    ev_dir = Path(ws_path) / ".dawei"

    runs: list[dict[str, Any]] = []
    if ev_dir.exists():
        for item in sorted(ev_dir.iterdir(), reverse=True):
            if not (item.is_dir() and item.name.startswith("evolution-")):
                continue
            meta_path = item / "metadata.json"
            meta = _read_json_file(meta_path) or {}
            # 过滤匹配 stage 的 cycle
            cycle_stage = meta.get("lifecycle_stage", "")
            if stage != "all" and cycle_stage and cycle_stage != stage:
                continue
            runs.append({
                "cycle_id": item.name,
                "status": meta.get("status", "unknown"),
                "started_at": meta.get("started_at", ""),
                "completed_at": meta.get("completed_at"),
                "current_phase": meta.get("current_phase"),
                "lifecycle_stage": cycle_stage or stage,
            })

    return {"runs": runs, "total": len(runs)}


# ─── API 端点：风险摘要 ─────────────────────────────────────────────


@router.get("/projects/{workspace_id}/risk-summary")
async def get_risk_summary(workspace_id: str):
    """风险摘要（5 维度 + 实体级）"""
    ws_path = await _resolve_workspace_path(workspace_id)

    # 读取摸底调查表中的风险维度
    inv_path = Path(ws_path) / "input" / "investigation.json"
    inv_data = _read_json_file(inv_path) or {}
    risk_dimensions = inv_data.get("risk_dimensions", {})

    # 读取最新筛查结果
    results = _list_screening_results(ws_path)
    latest_screening = results[0] if results else None

    # 读取 compliance 元数据
    ws_config = await _read_workspace_config(ws_path)
    compliance_meta = ws_config.get("metadata", {}).get("compliance", {})

    return {
        "workspace_id": workspace_id,
        "overall_risk_level": compliance_meta.get("risk_level"),
        "lifecycle_stage": compliance_meta.get("lifecycle_stage", "initiation"),
        "risk_dimensions": risk_dimensions,
        "latest_screening": latest_screening,
        "parties_count": len(inv_data.get("parties", [])),
        "last_screened_at": compliance_meta.get("last_screened_at"),
    }


# ─── API 端点：材料管理 ─────────────────────────────────────────────


@router.post("/projects/{workspace_id}/materials")
async def upload_material(
    workspace_id: str,
    request: Request,
    file: UploadFile = File(...),
    category: str = Form("misc"),
):
    """上传项目材料（合同/招标/财务/证书等任意文件）"""
    if category not in _VALID_MATERIAL_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category: {category}. Valid: {_VALID_MATERIAL_CATEGORIES}")

    ws_path = await _resolve_workspace_path(workspace_id)
    materials_dir = Path(ws_path) / "input" / "materials" / category
    materials_dir.mkdir(parents=True, exist_ok=True)

    # 生成唯一文件名
    material_id = uuid.uuid4().hex[:12]
    original_name = file.filename or "unnamed"
    safe_name = f"{material_id}_{original_name}"
    file_path = materials_dir / safe_name

    content = await file.read()
    file_path.write_bytes(content)

    # 更新材料计数
    materials_count = _count_materials(ws_path)
    _update_compliance_metadata(ws_path, {"materials_count": materials_count})

    logger.info("[MATERIALS] Uploaded %s to %s/%s", original_name, workspace_id, category)

    return {
        "success": True,
        "material_id": material_id,
        "filename": original_name,
        "category": category,
        "size": len(content),
        "saved_as": safe_name,
    }


@router.get("/projects/{workspace_id}/materials")
async def list_materials(workspace_id: str, category: str | None = Query(None)):
    """列出已上传的材料"""
    ws_path = await _resolve_workspace_path(workspace_id)
    materials = _list_materials(ws_path)
    if category:
        materials = [m for m in materials if m.get("category") == category]
    return {"materials": materials, "total": len(materials)}


@router.delete("/projects/{workspace_id}/materials/{material_id}")
async def delete_material(workspace_id: str, material_id: str):
    """删除某材料"""
    ws_path = await _resolve_workspace_path(workspace_id)
    materials_dir = Path(ws_path) / "input" / "materials"

    # 搜索匹配的文件
    for f in materials_dir.rglob("*"):
        if f.is_file() and f.stem.startswith(material_id):
            f.unlink()
            materials_count = _count_materials(ws_path)
            _update_compliance_metadata(ws_path, {"materials_count": materials_count})
            return {"success": True, "deleted": material_id}

    raise HTTPException(status_code=404, detail="Material not found")


# ─── API 端点：智能体团队管理 ───────────────────────────────────────


@router.post("/projects/{workspace_id}/agent-teams")
async def add_agent_team(workspace_id: str, req: AddAgentTeamRequest, request: Request):
    """为项目添加智能体团队"""
    ws_path = await _resolve_workspace_path(workspace_id)
    ws_config = await _read_workspace_config(ws_path)
    compliance_meta = ws_config.get("metadata", {}).get("compliance", {})
    agent_teams = compliance_meta.get("agent_teams", [])

    if req.team_slug in agent_teams:
        return {"success": True, "message": "团队已存在", "agent_teams": agent_teams}

    agent_teams.append(req.team_slug)
    _update_compliance_metadata(ws_path, {"agent_teams": agent_teams})

    # 安装团队资源到 workspace（best-effort）
    try:
        from dawei.api.auth import extract_market_token
        market_token = extract_market_token(request)

        team_id = req.team_id or f"team/{req.team_slug}"
        from dawei.workspace.resource_installer import install_resources_to_workspace
        # 【2026-09-14 事件循环阻塞修复】同步重 IO → 线程池执行
        await asyncio.to_thread(
            install_resources_to_workspace,
            workspace_path=ws_path,
            team_id=team_id,
            team_meta=None,
            market_token=market_token,
        )
        logger.info("[AGENT_TEAMS] Installed team %s for workspace %s", req.team_slug, workspace_id)
    except Exception as e:
        logger.warning("[AGENT_TEAMS] Failed to install team resources: %s", e)

    return {"success": True, "agent_teams": agent_teams, "added": req.team_slug}


@router.get("/projects/{workspace_id}/agent-teams")
async def list_agent_teams(workspace_id: str):
    """列出已加载的智能体团队"""
    ws_path = await _resolve_workspace_path(workspace_id)
    ws_config = await _read_workspace_config(ws_path)
    compliance_meta = ws_config.get("metadata", {}).get("compliance", {})
    agent_teams = compliance_meta.get("agent_teams", [])

    # 附加团队详情（从 agents 目录读取）
    teams_detail = []
    for slug in agent_teams:
        team_dir = Path(ws_path) / ".dawei" / "agents" / slug
        modes_path = team_dir / "modes.yaml"
        teams_detail.append({
            "slug": slug,
            "installed": modes_path.exists(),
            "roles": ["compliance-officer", "compliance-analyst", "document-drafter", "compliance-reviewer"],
        })

    return {"agent_teams": teams_detail, "total": len(teams_detail)}


@router.delete("/projects/{workspace_id}/agent-teams/{team_slug}")
async def remove_agent_team(workspace_id: str, team_slug: str):
    """移除某智能体团队"""
    ws_path = await _resolve_workspace_path(workspace_id)
    ws_config = await _read_workspace_config(ws_path)
    compliance_meta = ws_config.get("metadata", {}).get("compliance", {})
    agent_teams = compliance_meta.get("agent_teams", [])

    if team_slug not in agent_teams:
        raise HTTPException(status_code=404, detail="Team not found in project")

    agent_teams.remove(team_slug)
    _update_compliance_metadata(ws_path, {"agent_teams": agent_teams})

    # 移除团队文件（best-effort）
    try:
        team_dir = Path(ws_path) / ".dawei" / "agents" / team_slug
        if team_dir.exists():
            shutil.rmtree(team_dir)
    except Exception as e:
        logger.warning("[AGENT_TEAMS] Failed to remove team files: %s", e)

    return {"success": True, "removed": team_slug, "agent_teams": agent_teams}


# ─── API 端点：合同条款审核 ─────────────────────────────────────────


@router.put("/projects/{workspace_id}/contract-clauses")
async def save_contract_clauses(workspace_id: str, data: ContractClausesData):
    """保存/更新合同条款数据"""
    ws_path = await _resolve_workspace_path(workspace_id)
    clauses_path = Path(ws_path) / "input" / "contract_clauses.json"

    existing = _read_json_file(clauses_path) or {}
    merged = {
        "version": existing.get("version", "1.0"),
        "updated_at": _now_iso(),
        "contract_info": {**existing.get("contract_info", {}), **data.contract_info},
        "definitions": data.definitions if data.definitions else existing.get("definitions", []),
        "commitments": data.commitments if data.commitments else existing.get("commitments", []),
        "system_requirements": {**existing.get("system_requirements", {}), **data.system_requirements},
    }

    _write_json_file(clauses_path, merged)
    return {"success": True, "contract_clauses": merged}


@router.get("/projects/{workspace_id}/contract-clauses")
async def get_contract_clauses(workspace_id: str):
    """读取合同条款数据"""
    ws_path = await _resolve_workspace_path(workspace_id)
    clauses_path = Path(ws_path) / "input" / "contract_clauses.json"
    data = _read_json_file(clauses_path)
    return {"contract_clauses": data, "exists": data is not None}


@router.post("/projects/{workspace_id}/contract-clauses/review")
async def review_contract_clauses(workspace_id: str, request: Request):
    """触发 AI 合同条款审核（三点关注）

    创建一个 monitoring 阶段的 PDCA Cycle，在 Plan 阶段分析条款。
    """
    ws_path = await _resolve_workspace_path(workspace_id)

    # 检查是否有合同条款数据
    clauses_path = Path(ws_path) / "input" / "contract_clauses.json"
    clauses = _read_json_file(clauses_path)
    if not clauses:
        raise HTTPException(status_code=400, detail="无合同条款数据，请先上传合同并提取条款")

    # 保存审核请求记录
    review_id = f"review-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    review_record = {
        "review_id": review_id,
        "reviewed_at": _now_iso(),
        "triggered_by": "user",
        "status": "initiated",
        "clauses_snapshot": clauses,
    }

    review_path = Path(ws_path) / "output" / "contract_review" / f"{review_id}.json"
    _write_json_file(review_path, review_record)

    # 更新 lifecycle stage
    _update_compliance_metadata(ws_path, {"lifecycle_stage": "monitoring"})

    return {
        "success": True,
        "review_id": review_id,
        "message": "合同条款审核已触发。请在执行记录中查看 PDCA 进度。",
    }


@router.get("/projects/{workspace_id}/contract-clauses/reviews")
async def list_contract_reviews(workspace_id: str):
    """查询合同审核历史"""
    ws_path = await _resolve_workspace_path(workspace_id)
    review_dir = Path(ws_path) / "output" / "contract_review"

    reviews: list[dict[str, Any]] = []
    if review_dir.exists():
        for f in sorted(review_dir.glob("*.json"), reverse=True):
            data = _read_json_file(f)
            if data:
                reviews.append({
                    "review_id": data.get("review_id", f.stem),
                    "reviewed_at": data.get("reviewed_at", ""),
                    "status": data.get("status", "unknown"),
                    "triggered_by": data.get("triggered_by", "user"),
                })

    return {"reviews": reviews, "total": len(reviews)}


# ─── API 端点：Ethics Plan ──────────────────────────────────────────


@router.post("/projects/{workspace_id}/ethics-plan/generate")
async def generate_ethics_plan(workspace_id: str, request: Request):
    """生成 Ethics Plan（触发 PDCA Cycle 走 Plan→Do→Check→Act）

    Agent 在 Plan 阶段分析合同条款确定必须覆盖的组件，
    Do 阶段起草各章节，Check 阶段复核，Act 阶段定稿输出。
    """
    ws_path = await _resolve_workspace_path(workspace_id)

    # 检查前提条件
    clauses_path = Path(ws_path) / "input" / "contract_clauses.json"
    if not _read_json_file(clauses_path):
        raise HTTPException(status_code=400, detail="无合同条款数据，请先进行合同条款审核")

    # 创建 ethics plan 生成记录
    version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    plan_record = {
        "version": version,
        "generated_at": _now_iso(),
        "status": "drafting",
        "message": "Ethics Plan 生成中，请查看执行记录了解进度",
    }

    reports_dir = Path(ws_path) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # 记录生成请求
    meta_path = reports_dir / "ethics-plan-meta.json"
    _write_json_file(meta_path, plan_record)

    # 更新 lifecycle stage
    _update_compliance_metadata(ws_path, {"lifecycle_stage": "monitoring"})

    return {
        "success": True,
        "version": version,
        "status": "drafting",
        "message": "Ethics Plan 生成已触发。生成完成后可在 reports/ 目录查看。",
    }


@router.get("/projects/{workspace_id}/ethics-plan")
async def get_ethics_plan(workspace_id: str):
    """获取最新 Ethics Plan 内容"""
    ws_path = await _resolve_workspace_path(workspace_id)
    reports_dir = Path(ws_path) / "reports"

    # 读取 meta
    meta_path = reports_dir / "ethics-plan-meta.json"
    meta = _read_json_file(meta_path) or {"status": "not_started"}

    # 查找 ethics-plan markdown 文件
    plan_files = sorted(reports_dir.glob("ethics-plan*.md"), reverse=True)
    content = None
    if plan_files:
        try:
            content = plan_files[0].read_text(encoding="utf-8")
        except Exception:
            pass

    return {
        "meta": meta,
        "content": content,
        "filename": plan_files[0].name if plan_files else None,
        "exists": content is not None,
    }
