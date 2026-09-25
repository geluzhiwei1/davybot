# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""桶2：业务路由聚合器（§18.2-C；S3 单一入口）。

经 entry point group ``dawei.routers``（值 = 本模块）被核心 server_app 装载，
暴露有序 ``routers: list[APIRouter]``。ip 链顺序有依赖（ip_templates →
ip_workspace(+portfolio) → ip_routes，catch-all 阴影），故必须保持本列表顺序。
装了 biz 但本模块加载失败 = 启动 FAST FAIL（S3）。

6b-2 起各路由文件 git mv 自 dawei/api/ 并逐个追加于下方列表。
"""

from dawei_biz.bridges.social.router import router as social_router
from dawei_biz.routers import compliance, deep_research, deep_research_product
from dawei_biz.routers import ip_routes, ip_templates, ip_workspace, knowledge_uni, templates_sync

# saas 桶路由（§18.2-E）：users_remote 自带 /api/users/me/remote 全前缀
# （原经核心 users 路由挂载，迁库后路径由 router 自身 prefix 保证不变）。
from dawei_biz.saas import admin_sandbox, internal_agent_stream, license, users_remote

routers = [
    social_router,
    knowledge_uni.router,
    # NOTE: ip_templates.router → ip_workspace.router → ip_routes.router
    # ip_routes has catch-all /api/ip/{module}/{task_id} that shadows others.
    ip_templates.router,
    ip_workspace.router,
    ip_workspace.portfolio_router,
    ip_routes.router,
    compliance.router,
    deep_research.router,  # 深度研究 · 通用框架 (pipelines/share)
    deep_research_product.router,  # 深度研究 · 产品调研
    templates_sync.router,
    # ── saas 桶（原 server_app 直挂顺序: license → admin_sandbox → internal）──
    license.router,
    admin_sandbox.router,
    internal_agent_stream.router,
    users_remote.router,
]
