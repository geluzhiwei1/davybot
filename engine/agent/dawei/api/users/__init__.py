# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""用户相关 API 路由"""

from fastapi import APIRouter

from .acp import router as acp_router
from .channels import router as channels_router
from .devices import router as devices_router
from .knowledge import router as knowledge_router
from .llm import router as llm_router
from .mcp import router as mcp_router
from .mcp_relay import router as mcp_relay_router
from .memory import router as memory_router
# .remote（NAT 隧道控制 /me/remote）已随 6b 拆库迁至 davybot-biz saas 桶
# （dawei_biz.saas.users_remote），经 S3 聚合器挂载（prefix=/api/users）。
from .skills_tools import router as skills_tools_router

router = APIRouter(prefix="/api/users", tags=["Users"])

# 注册子路由
# 注：security_router 在 server_app.py 中直接挂载到 /api/me/security
router.include_router(mcp_router)
# 本机 MCP relay(davy-light-app 壳通道):/api/users/me/mcp-relay/*
# —— 不挂载则壳 register 404,relay 注册表永远为空(2026-09-17 根因)
router.include_router(mcp_relay_router)
# 设备管理(方案 §9.3):/api/users/me/devices/* —— 列表 / 重命名 / 远程登出
router.include_router(devices_router)
router.include_router(llm_router)
router.include_router(acp_router)
router.include_router(channels_router)
router.include_router(skills_tools_router)
router.include_router(memory_router)
router.include_router(knowledge_router)

__all__ = ["router"]
