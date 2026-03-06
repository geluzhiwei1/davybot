# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""用户相关 API 路由"""

from fastapi import APIRouter

from .security import router as security_router

router = APIRouter(prefix="/users", tags=["Users"])

# 注册子路由
router.include_router(security_router)

__all__ = ['router']
