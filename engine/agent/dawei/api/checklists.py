# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""合规检查清单管理 API 路由

提供检查清单的 CRUD、模板库、任务指派、进度追踪等功能。
M4 — Compliance Checklist Management, Phase 2 Weeks 7-9.
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from dawei.logg.logging import get_logger
from dawei.workspace import workspace_manager

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/checklists",
    tags=["checklists"],
)


# =============================================================================
# Pydantic Models
# =============================================================================

class ChecklistItemCreate(BaseModel):
    """创建检查项请求"""
    task: str = Field(..., description="检查任务描述")
    assigned_to: str | None = Field(None, description="指派给谁")
    guidance: str | None = Field(None, description="操作指引/法规依据")
    category: str | None = Field("通用", description="任务分类")


class ChecklistItemUpdate(BaseModel):
    """更新检查项请求"""
    task: str | None = None
    status: str | None = None  # pending / in_progress / completed / not_applicable
    completed_by: str | None = None
    assigned_to: str | None = None
    evidence: list[str] | None = None
    notes: str | None = None


class ChecklistCreate(BaseModel):
    """创建检查清单请求"""
    template: str | None = Field(None, description="模板 slug (可选)")
    title: str = Field(..., description="清单标题")
    params: dict[str, Any] | None = Field(None, description="上下文参数如 country, industry 等")
    assignee: str | None = Field(None, description="总负责人")
    deadline: str | None = Field(None, description="截止日期 ISO 8601")
    items: list[ChecklistItemCreate] | None = Field(None, description="初始检查项列表")
    pdca_phase: str | None = Field("do", description="所在 PDCA 阶段: plan/do/check/act")
    pdca_plan: str | None = Field(None, description="所属 PDCA 计划名称")


ChecklistItemData = dict[str, Any]


# =============================================================================
# Storage Helpers
# =============================================================================

def _get_checklists_dir(workspace_id: str) -> Path:
    """获取工作区检查清单目录"""
    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' not found.")

    base_path = Path(workspace_info["path"])
    if not base_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Workspace path '{base_path}' not found.")

    checklists_dir = base_path / ".dawei" / "checklists"
    checklists_dir.mkdir(parents=True, exist_ok=True)
    return checklists_dir


def _load_checklist(file_path: Path) -> dict:
    """加载单个检查清单 JSON 文件"""
    with file_path.open(encoding="utf-8") as f:
        return json.load(f)


def _save_checklist(file_path: Path, data: dict) -> None:
    """保存检查清单 JSON 文件"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _compute_progress(items: list) -> dict:
    """计算检查清单进度"""
    total = len(items)
    if total == 0:
        return {"total": 0, "completed": 0, "in_progress": 0, "pending": 0, "not_applicable": 0, "completion_pct": 0}

    counts = {"completed": 0, "in_progress": 0, "pending": 0, "not_applicable": 0}
    for item in items:
        status = item.get("status", "pending")
        if status in counts:
            counts[status] += 1
        else:
            counts["pending"] += 1

    effective = total - counts["not_applicable"]
    completion_pct = round((counts["completed"] / effective) * 100) if effective > 0 else 0
    return {**counts, "total": total, "completion_pct": completion_pct}


# =============================================================================
# CRUD Endpoints — Checklists
# =============================================================================

@router.get("")
async def list_checklists(
    workspace_id: str,
    status: str | None = Query(None, description="按状态过滤: active / archived"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """列出所有检查清单，支持状态过滤和分页"""
    checklists_dir = _get_checklists_dir(workspace_id)
    items = []

    for file_path in sorted(checklists_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = _load_checklist(file_path)
        cl_status = data.get("status", "active")
        if status and cl_status != status:
            continue
        progress = _compute_progress(data.get("items", []))
        items.append({
            "id": data.get("id", file_path.stem),
            "title": data.get("title", ""),
            "template": data.get("template", ""),
            "status": cl_status,
            "pdca_phase": data.get("pdca_cycle", {}).get("phase", "do"),
            "created_by": data.get("created_by", ""),
            "created_at": data.get("created_at", ""),
            "deadline": data.get("pdca_cycle", {}).get("deadline", ""),
            "progress": progress,
        })

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return {"success": True, "data": items[start:end], "total": total, "page": page, "page_size": page_size}


def _find_template_file(template_slug: str) -> Path | None:
    """在 {DAWEI_HOME}/data/templates/*/checklists/ 下查找模板文件。

    v3 market 模板按团队落盘为 {team}/checklists/{slug}.json
    （见 resource_installer.install_templates），旧内置模板在
    compliance/checklists/ 下，统一扫描。
    """
    import os
    dawei_home = Path(os.environ.get("DAWEI_HOME", "~/.normnomos")).expanduser()
    templates_root = dawei_home / "data" / "templates"

    for ext in (".json", ".yaml", ".yml"):
        matches = sorted(templates_root.glob(f"*/checklists/{template_slug}{ext}"))
        if matches:
            return matches[0]
    return None


def _load_template_items(template_slug: str, assignee: str = "") -> list[dict[str, Any]]:
    """从模板文件加载检查项列表"""
    tmpl_path = _find_template_file(template_slug)
    if not tmpl_path:
        return []

    tmpl_data = _load_checklist(tmpl_path)
    template_items = tmpl_data.get("items", [])
    items = []
    for tmpl_item in template_items:
        items.append({
            "id": f"item-{uuid.uuid4().hex[:8]}",
            "task": tmpl_item.get("task", ""),
            "status": "pending",
            "assigned_to": assignee,
            "guidance": tmpl_item.get("guidance", ""),
            "category": tmpl_item.get("category", "通用"),
            "evidence": [],
            "notes": "",
        })
    return items


@router.post("")
async def create_checklist(
    workspace_id: str,
    body: ChecklistCreate,
    request: Request,
):
    """创建新的检查清单

    支持两个来源的检查项（优先级）：
    1. body.items — 显式传入的检查项
    2. body.template — 从模板文件加载检查项
    二者可同时存在（手动项 + 模板项）。
    """
    checklist_id = f"cl-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC).isoformat()
    created_by = getattr(request.state, "user_email", "anonymous") if hasattr(request.state, "user_email") else "anonymous"

    items = []

    # 从模板加载检查项
    if body.template:
        loader_assignee = body.assignee or created_by
        template_items = _load_template_items(body.template, loader_assignee)
        if template_items:
            items.extend(template_items)
            logger.info(f"Loaded {len(template_items)} items from template '{body.template}'")
        else:
            logger.warning(f"Template '{body.template}' not found or has no items")

    # 显式传入的检查项（追加到模板项之后）
    if body.items:
        for idx, item_create in enumerate(body.items):
            items.append({
                "id": f"item-{uuid.uuid4().hex[:8]}",
                "task": item_create.task,
                "status": "pending",
                "assigned_to": item_create.assigned_to or body.assignee or created_by,
                "guidance": item_create.guidance or "",
                "category": item_create.category or "通用",
                "evidence": [],
                "notes": "",
            })

    data = {
        "id": checklist_id,
        "template": body.template or "",
        "title": body.title,
        "params": body.params or {},
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
        "status": "active",
        "items": items,
        "pdca_cycle": {
            "phase": body.pdca_phase or "do",
            "plan": body.pdca_plan or "",
            "deadline": body.deadline or "",
        },
    }

    file_path = _get_checklists_dir(workspace_id) / f"{checklist_id}.json"
    _save_checklist(file_path, data)

    progress = _compute_progress(items)
    return {"success": True, "data": {**data, "progress": progress}}


@router.get("/{checklist_id}")
async def get_checklist(workspace_id: str, checklist_id: str):
    """获取单个检查清单详情"""
    file_path = _get_checklists_dir(workspace_id) / f"{checklist_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Checklist '{checklist_id}' not found.")

    data = _load_checklist(file_path)
    progress = _compute_progress(data.get("items", []))
    return {"success": True, "data": {**data, "progress": progress}}


@router.delete("/{checklist_id}")
async def delete_checklist(workspace_id: str, checklist_id: str):
    """删除检查清单（软删除 — 标记为 archived）"""
    file_path = _get_checklists_dir(workspace_id) / f"{checklist_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Checklist '{checklist_id}' not found.")

    data = _load_checklist(file_path)
    data["status"] = "archived"
    data["updated_at"] = datetime.now(UTC).isoformat()
    _save_checklist(file_path, data)
    return {"success": True, "message": f"Checklist '{checklist_id}' archived."}


# =============================================================================
# CRUD Endpoints — Checklist Items
# =============================================================================

@router.patch("/{checklist_id}/items/{item_id}")
async def update_checklist_item(
    workspace_id: str,
    checklist_id: str,
    item_id: str,
    body: ChecklistItemUpdate,
    request: Request,
):
    """更新检查项状态"""
    file_path = _get_checklists_dir(workspace_id) / f"{checklist_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Checklist '{checklist_id}' not found.")

    data = _load_checklist(file_path)
    items = data.get("items", [])

    updated_item = None
    for item in items:
        if item.get("id") == item_id:
            if body.task is not None:
                item["task"] = body.task
            if body.status is not None:
                item["status"] = body.status
                if body.status == "completed":
                    user = getattr(request.state, "user_email", "anonymous") if hasattr(request.state, "user_email") else "anonymous"
                    item["completed_by"] = body.completed_by or user
                    item["completed_at"] = datetime.now(UTC).isoformat()
            if body.completed_by is not None:
                item["completed_by"] = body.completed_by
            if body.assigned_to is not None:
                item["assigned_to"] = body.assigned_to
            if body.evidence is not None:
                item["evidence"] = body.evidence
            if body.notes is not None:
                item["notes"] = body.notes
            updated_item = item
            break

    if updated_item is None:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found in checklist.")

    data["updated_at"] = datetime.now(UTC).isoformat()
    _save_checklist(file_path, data)

    progress = _compute_progress(items)
    return {"success": True, "data": {"item": updated_item, "checklist_progress": progress}}


@router.post("/{checklist_id}/items")
async def add_checklist_item(
    workspace_id: str,
    checklist_id: str,
    body: ChecklistItemCreate,
):
    """添加检查项"""
    file_path = _get_checklists_dir(workspace_id) / f"{checklist_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Checklist '{checklist_id}' not found.")

    data = _load_checklist(file_path)
    new_item = {
        "id": f"item-{uuid.uuid4().hex[:8]}",
        "task": body.task,
        "status": "pending",
        "assigned_to": body.assigned_to or data.get("created_by", ""),
        "guidance": body.guidance or "",
        "category": body.category or "通用",
        "evidence": [],
        "notes": "",
    }
    data["items"].append(new_item)
    data["updated_at"] = datetime.now(UTC).isoformat()
    _save_checklist(file_path, data)

    progress = _compute_progress(data["items"])
    return {"success": True, "data": {"item": new_item, "checklist_progress": progress}}


# =============================================================================
# Template Endpoints
# =============================================================================

def _load_templates() -> list[dict[str, Any]]:
    """从已安装的市场模板加载检查清单模板

    扫描 {DAWEI_HOME}/data/templates/*/checklists/*.json（含旧内置
    compliance/checklists/ 与 v3 按团队安装的 {team}/checklists/）。
    """
    import os
    dawei_home = Path(os.environ.get("DAWEI_HOME", "~/.normnomos")).expanduser()
    templates_root = dawei_home / "data" / "templates"

    templates = []
    if templates_root.exists():
        for tmpl_path in sorted(templates_root.glob("*/checklists/*.json")):
            try:
                tmpl_data = _load_checklist(tmpl_path)
                templates.append({
                    "slug": tmpl_data.get("slug", tmpl_path.stem),
                    "name": tmpl_data.get("name", tmpl_path.stem),
                    "category": tmpl_data.get("category", "通用"),
                    "description": tmpl_data.get("description", ""),
                    "item_count": len(tmpl_data.get("items", [])),
                    "applicable_scenarios": tmpl_data.get("applicable_scenarios", []),
                })
            except Exception:
                logger.warning(f"Failed to load template: {tmpl_path}")

    return templates


@router.get("/templates/all")
async def list_templates(
    category: str | None = Query(None, description="按类别过滤"),
):
    """列出所有可用模板"""
    all_templates = _load_templates()
    if category:
        all_templates = [t for t in all_templates if t.get("category") == category]

    categories = sorted({t.get("category", "通用") for t in all_templates})
    return {"success": True, "data": {"templates": all_templates, "categories": categories, "total": len(all_templates)}}


@router.get("/templates/{template_slug}")
async def get_template(template_slug: str):
    """获取单个模板详情（包含完整检查项）"""
    tmpl_path = _find_template_file(template_slug)
    if tmpl_path:
        data = _load_checklist(tmpl_path)
        return {"success": True, "data": data}

    raise HTTPException(status_code=404, detail=f"Template '{template_slug}' not found.")
