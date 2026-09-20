# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""合规子系统 API — 模板查询、项目管理"""

from fastapi import APIRouter

from .templates import router as templates_router
from .projects import router as projects_router

router = APIRouter(prefix="/api/compliance")

router.include_router(templates_router)
router.include_router(projects_router)

__all__ = ["router"]
