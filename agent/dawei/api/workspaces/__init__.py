# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Workspace API模块

Workspace API的模块化实现，将原本3,291行的单一文件拆分为8个子模块
"""

from fastapi import APIRouter

# 导入记忆系统API
from . import memory as memory_api
from .checkpoints import router as checkpoints_router

# 导入各子模块的路由器
from .config import router as config_router
from .core import get_user_workspace
from .core import router as core_router
from .crud import router as crud_router
from .files import router as files_router
from .graphs import router as graphs_router
from .llm import router as llm_router
from .models import *
from .plugins import router as plugins_router
from .plugin_config import router as plugin_config_router
from .ui_settings import router as ui_settings_router

# 创建主路由器
router = APIRouter(prefix="/api/workspaces")

# 注册所有子路由器
router.include_router(core_router)
router.include_router(files_router)
router.include_router(llm_router)
router.include_router(graphs_router)
router.include_router(checkpoints_router)
router.include_router(config_router)
router.include_router(ui_settings_router)
router.include_router(crud_router)
router.include_router(plugins_router)
router.include_router(plugin_config_router)

# 注册记忆系统路由器
# Note: Memory router has its own prefix with workspace_id: /api/workspaces/{workspace_id}/memory
router.include_router(memory_api.router)

# 导出
__all__ = ["router"]
