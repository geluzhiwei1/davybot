# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""S5 桥接层：业务域与核心扩展钩子的接线（§18.3-S5）。

- social/：社媒域（session_context、router、service、browser_track、trending 等）；
- research/：调研桥接。

本包被 import（dawei_biz 任一 entry point 模块装载均先执行包 ``__init__`` 链）
即触发三个编队模块底部的 ext_hooks 自注册 —— 核心主链不 import 任何业务符号，
业务缺席=无行为。阶段六 6b-2 git mv 自 dawei/{social,research} 与
dawei/websocket/{social,market,research}_fleet.py。
（原 dawei/ip_sdk 外部 SaaS SDK client 为零调用死代码，6e 前清理时删除。）
"""

from dawei_biz.bridges import market_fleet, research_fleet, social_fleet  # noqa: E402,F401 —— S5 注册副作用
