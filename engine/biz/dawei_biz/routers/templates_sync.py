# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""模板同步 API — 显式模板下载/强制刷新端点。

POST /api/templates/sync — 下载模板到 DAWEI_HOME/data/templates/

注意：日常使用时无需调用此 API。
IPTemplateManager / ComplianceTemplateManager 的 load_template() 会自动触发按需安装。
此 API 仅用于管理员强制刷新或预加载场景。
"""

import logging
import os
import shutil
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from dawei import get_dawei_home

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/templates", tags=["Templates"])


class TemplateSyncRequest(BaseModel):
    """模板同步请求"""

    domain: str = Field(
        "all",
        description="模板域: 'ip', 'compliance', 或 'all'",
        pattern=r"^(ip|compliance|all)$",
    )
    categories: list[str] = Field(
        default_factory=list,
        description="按分类筛选。为空则同步全部。",
    )
    force: bool = Field(
        False,
        description="true 时忽略缓存版本，强制重新下载",
    )


class TemplateSyncResponse(BaseModel):
    """模板同步响应"""

    synced: list[str] = Field(default_factory=list, description="本次下载的模板")
    cached: list[str] = Field(default_factory=list, description="使用缓存的模板")
    errors: list[dict[str, str]] = Field(
        default_factory=list, description="下载失败的模板"
    )


def _sync_domain(
    domain: str,
    data_root: Path,
    templates_root: Path,
    categories: list[str],
    force: bool,
    response: TemplateSyncResponse,
) -> None:
    """同步单个 domain 的模板（domain 级别：workspace/ + checklists/ + knowledge/）。"""
    src_root = data_root / f"{domain}-templates"
    if not src_root.exists():
        response.errors.append({
            "id": f"{domain}/*",
            "message": f"Template source not found for domain: {domain}",
        })
        return

    # 1. 同步 workspace/（含 index.yaml + 所有 category）
    src_workspace = src_root / "workspace"
    if not src_workspace.exists():
        response.errors.append({
            "id": f"{domain}/workspace",
            "message": f"workspace/ directory not found for domain: {domain}",
        })
        return

    dest_workspace = templates_root / domain / "workspace"
    dest_workspace.mkdir(parents=True, exist_ok=True)

    for item in src_workspace.iterdir():
        if item.is_dir():
            category = item.name
            if categories and category not in categories:
                continue

            # Check if already synced (unless force=True)
            if not force:
                final_dir = dest_workspace / category
                if final_dir.exists():
                    response.cached.append(f"template/{domain}/{category}/*")
                    continue

            # Atomic install
            tmp_dir = dest_workspace / f".tmp_{category}"
            final_dir = dest_workspace / category
            try:
                if tmp_dir.exists():
                    shutil.rmtree(tmp_dir)
                shutil.copytree(item, tmp_dir)
                if final_dir.exists():
                    shutil.rmtree(final_dir)
                tmp_dir.rename(final_dir)
                response.synced.append(f"template/{domain}/{category}/*")
            except Exception as e:
                if tmp_dir.exists():
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                response.errors.append({
                    "id": f"template/{domain}/{category}/*",
                    "message": str(e),
                })

        elif item.name == "index.yaml":
            shutil.copy2(item, dest_workspace / "index.yaml")

    # 2. 同步 checklists/（domain 级别共享）
    src_checklists = src_root / "checklists"
    if src_checklists.exists():
        dst = templates_root / domain / "checklists"
        dst.mkdir(parents=True, exist_ok=True)
        for f in src_checklists.iterdir():
            if f.is_file():
                shutil.copy2(f, dst / f.name)
        response.synced.append(f"template/{domain}/checklists/*")

    # 3. 同步 knowledge/（domain 级别共享，仅 IP domain）
    src_knowledge = src_root / "knowledge"
    if src_knowledge.exists():
        dst = templates_root / domain / "knowledge"
        dst.mkdir(parents=True, exist_ok=True)
        for item in src_knowledge.iterdir():
            target = dst / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        response.synced.append(f"template/{domain}/knowledge/*")


@router.post("/sync", response_model=TemplateSyncResponse)
async def sync_templates(req: TemplateSyncRequest) -> TemplateSyncResponse:
    """同步模板到 DAWEI_HOME/data/templates/

    显式同步端点。日常使用时 load_template() 会自动触发按需安装。
    此 API 用于管理员强制刷新或预加载。

    - force=false: 跳过已存在的 category
    - force=true: 强制重新下载所有 category
    """
    dawei_home = get_dawei_home()
    templates_root = dawei_home / "data" / "templates"
    templates_root.mkdir(parents=True, exist_ok=True)

    data_root = Path(os.environ.get(
        "MARKET_DATA_ROOT",
        str(Path(__file__).resolve().parents[4] / "nn-market-resources" / "data"),
    ))

    response = TemplateSyncResponse()
    domains = ["ip", "compliance"] if req.domain == "all" else [req.domain]

    for domain in domains:
        _sync_domain(domain, data_root, templates_root, req.categories, req.force, response)

    return response
