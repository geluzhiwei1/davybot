# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""桶3：SaaS/enterprise 部署支撑（§18.2-C/E「saas 桶」）。

云沙箱 provider ×7（e2b_provider / e2b_compat / cubesandbox_provider /
agentenv_provider / saas_gateway / backend_selector / sandbox_admin_methods）+
api 侧 saas 件（admin_sandbox / internal_agent_stream / license）+ remote/
（ping_service、nat_service）。随 davybot-biz 分发、mode/caps 门控；核心开源
形态（docker/subprocess 沙箱）不依赖本桶。经 entry point group
``dawei.sandbox_providers`` 被 provider_factory import 自注册（S4）。
"""
