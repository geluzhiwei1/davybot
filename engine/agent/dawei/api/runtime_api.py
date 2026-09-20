# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""运行模式统一 API (多模式统一方案 §L3)

  GET /api/runtime-info — mode + deployment_class + capabilities

前端据此驱动可见性 (SECTIONS 表); 前端隐藏 ≠ 安全, 无能力操作照常 4xx。
"""

from fastapi import APIRouter
from pydantic import BaseModel

from dawei import runtime

router = APIRouter(tags=["runtime"])


class RuntimeInfoResponse(BaseModel):
    mode: str  # "saas" | "desktop" | "server" | "tui"
    deployment_class: str  # "saas" | "local"
    capabilities: list[str]


@router.get("/api/runtime-info", response_model=RuntimeInfoResponse)
async def get_runtime_info() -> RuntimeInfoResponse:
    """运行模式与能力声明 (唯一权威出口)"""
    return RuntimeInfoResponse(**runtime.get_runtime_info())
