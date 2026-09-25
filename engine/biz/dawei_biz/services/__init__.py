# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""桶2：workspace 业务服务（§18.2-D）。

ip_workspace_service / ip_agent_executor / ip_template / compliance_template /
product_survey_{service,executor} / industry_research_service / deep_research_framework
—— 业务路由的工具层依赖，随路由同迁（保持相对引用最小改动）。
6b-2 git mv 自 dawei/workspace/。
"""

from dawei_biz.services import compliance_template  # noqa: E402,F401 —— ext_hooks 注册副作用
