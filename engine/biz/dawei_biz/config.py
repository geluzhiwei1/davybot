# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""业务 env 键注册表（拆库方案 §18.3-S7）。

SSOT 清单（data-only）：本包实际消费的环境变量键名。读取点仍在各模块
（``os.getenv`` / ``os.environ.get``，模块级，E1 无云端缺省），本文件只做
登记，供 E1 守卫（test_no_cloud_defaults.py，6c 落地）与审计扫描。

背景：
- 6b-2 搬迁后核心 ``dawei/config/settings.py`` 已无业务键（核心零业务键），
  无需删除动作 —— 本注册表即业务键的最终归属地。
- 与核心共享的键（见 SHARED_WITH_CORE_ENV_KEYS）不属业务专有，不入
  BIZ_ENV_KEYS：核心读点在 engine/agent，E1 由核心侧守卫覆盖。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 业务专有键（biz-only；全部无云端缺省，未配置 = 集成关闭）
# ---------------------------------------------------------------------------

# dawei_biz/tools/_service_client.py —— 5 个业务服务基址
# 注：BUSINESS_NORFLOW_API_URL 为历史拼写（NOR 而非 NORM），已上线契约，保留。
SERVICE_API_URL_KEYS: tuple[str, ...] = (
    "BUSINESS_KB_SEARCHER_API_URL",
    "BUSINESS_SANCTIONS_API_URL",
    "BUSINESS_NORFLOW_API_URL",
    "BUSINESS_MARKET_API_URL",
    "BUSINESS_RESEARCHFLOW_API_URL",
)

# dawei_biz/bridges/research —— research 控制面
RESEARCH_KEYS: tuple[str, ...] = (
    "RESEARCH_CONTROL_URL",
    "RESEARCH_API_KEY",
    "RESEARCH_AUTH_TOKEN",
)

# dawei_biz/bridges/social —— social 控制面（发布/采集/生图）
SOCIAL_KEYS: tuple[str, ...] = (
    "SOCIAL_CONTROL_URL",
    "SOCIAL_API_KEY",
    "SOCIAL_AUTH_TOKEN",
    "SOCIAL_TENANT_ID",
    "SOCIAL_BROWSER_HEADLESS",
    "SOCIAL_IMAGE_MODEL",
)

# dawei_biz/saas —— SaaS 运营面（内部回调 + 沙箱管理 + 源码根定位）
SAAS_KEYS: tuple[str, ...] = (
    "DAWEI_INTERNAL_TOKEN",
    "SANDBOX_ADMIN_TOKEN",
    "DAWEI_AGENT_SRC_DIR",
)

# 全量聚合（E1 守卫扫描入口）
BIZ_ENV_KEYS: tuple[str, ...] = (
    *SERVICE_API_URL_KEYS,
    *RESEARCH_KEYS,
    *SOCIAL_KEYS,
    *SAAS_KEYS,
)

# ---------------------------------------------------------------------------
# 与核心共享的键（仅登记，不属 BIZ_ENV_KEYS）
# ---------------------------------------------------------------------------
# UNISEARCHER_API_URL      核心读点 dawei/workspace/resource_installer.py（知识市场），
#                          biz 读点 dawei_biz/routers/knowledge_uni.py。
# SUPPORT_SYSTEM_URL / SUPPORT_SYSTEM_VERIFY_SSL
#                          核心读点 server_app.py / llm_provider.py / api/auth.py。
# OAUTH_CLIENT_ID / OAUTH_CLIENT_SECRET / OAUTH_REDIRECT_URI
#                          核心读点 api/auth.py。
# DAWEI_SANDBOX_*          共享族（13+ 键）。核心读点 provider_factory / sandbox_facade /
#                          api/sandbox_system；biz 读点 saas/（agentenv / cubesandbox /
#                          gateway / backend_selector，SaaS 云沙箱 provider 侧）。
SHARED_WITH_CORE_ENV_KEYS: tuple[str, ...] = (
    "UNISEARCHER_API_URL",
    "SUPPORT_SYSTEM_URL",
    "SUPPORT_SYSTEM_VERIFY_SSL",
    "OAUTH_CLIENT_ID",
    "OAUTH_CLIENT_SECRET",
    "OAUTH_REDIRECT_URI",
)
