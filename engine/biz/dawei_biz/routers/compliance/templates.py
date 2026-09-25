# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""合规模板查询 API

端点：
  GET /api/compliance/templates      — 列出可用模板 (可按 team 过滤)
  GET /api/compliance/templates/{slug} — 获取模板完整定义 (含表单字段)
"""

from fastapi import APIRouter, HTTPException, Query

from dawei_biz.services.compliance_template import ComplianceTemplateManager

router = APIRouter(tags=["compliance-templates"])


@router.get("/templates")
async def list_templates(team: str = Query(None, description="按合规团队过滤，如 supply-chain")):
    """列出所有可用合规工作区模板

    返回模板基本元数据：slug, name, description, estimated_time, category。
    可传 ?team= 参数按合规团队过滤。
    """
    manager = ComplianceTemplateManager()
    templates = manager.list_templates(team_slug=team)
    return {"templates": templates, "total": len(templates)}


@router.get("/templates/{slug}")
async def get_template(slug: str):
    """获取模板完整定义

    返回模板的所有定义：data_requirements (表单字段)、checklists (关联清单)、
    workspace_structure (目录结构)、agent_instructions (Agent 指令)、
    phases (PDCA 阶段) 等。前端使用 data_requirements 动态生成表单。
    """
    manager = ComplianceTemplateManager()
    template = manager.load_template(slug)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template not found: {slug}")

    # 返回 template 顶层内容供前端使用
    return template.get("template", template)
