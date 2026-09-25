# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""davybot-biz —— DavyBot 业务扩展后端（拆库方案 §18.3 双项目布局）。

进程内业务扩展：工具（桶1）/ 路由 + 服务（桶2）/ 桥接（S5 编队与上下文钩子）/
SaaS 部署支撑（桶3）/ 模板数据（S6）。AGPL 开源（§18.1：引擎进程内不得有闭源
代码；确需闭源的业务逻辑唯一出口 = 下沉 service-api/* 闭源服务进程）。

装载契约（核心 → biz 单向，禁反向依赖）：
- 工具：核心 CustomToolProvider 经 entry point group ``dawei.tools`` import 扫描（S1）；
- 工具组：本包 import 时向 ``register_tool_group()`` 注册 sanctions/normflow/
  market/research/social 组（S2）；
- 路由：核心 server_app 经 group ``dawei.routers`` import（模块暴露 ``router``，
  S3；装了 biz 但注册失败 = 启动 FAST FAIL）；
- 沙箱：核心 provider_factory 经 group ``dawei.sandbox_providers`` import 自注册（S4）；
- 编队/会话上下文（S5）：本包被 import（任一 entry point 模块装载均先执行本
  ``__init__``）→ bridges 自动向 ``dawei.core.ext_hooks`` 注册 —— 业务缺席=无行为。

模块清单与归属依据见 project/docs/拆库方案.md §18.2（本表即 git mv 清单）。
"""

try:
    from dawei_biz._version import __version__  # noqa: F401 —— setuptools_scm 构建时生成
except ImportError:  # 源码树直接 import（未安装）时的兜底
    __version__ = "0.0.0.dev0"  # noqa: F401

# S5：本包任一 entry point 模块被核心装载时，先经本 __init__ 触发 bridges
# → 三编队向 dawei.core.ext_hooks 自注册（业务缺席=无行为，单向 biz→core）。
from dawei_biz import bridges  # noqa: E402,F401

# S2：注册 biz 工具组（核心 register_tool_group，单向 biz→core）。
# 名单取自各工具模块的 *_TOOL_NAMES 常量（单一事实源，防名称漂移）。
# 组名与既有 workspace modes.yaml 的 groups 声明保持稳定；同名组（knowledge）
# 为合并语义 —— biz 缺席时核心 knowledge 组仅含 2 个用户知识库工具。
from dawei.tools.tool_manager import register_tool_group  # noqa: E402
from dawei.tools.tool_catalog import register_catalog_entries  # noqa: E402

from dawei_biz.tools._catalog import BIZ_CATALOG  # noqa: E402
from dawei_biz.tools.legal_knowledge_tools import LEGAL_TOOL_NAMES  # noqa: E402
from dawei_biz.tools.market_tools import MARKET_TOOL_NAMES  # noqa: E402
from dawei_biz.tools.normflow_tools import NORMFLOW_TOOL_NAMES  # noqa: E402
from dawei_biz.tools.research_tools import RESEARCH_TOOL_NAMES  # noqa: E402
from dawei_biz.tools.sanctions_tools import SANCTIONS_TOOL_NAMES  # noqa: E402
from dawei_biz.tools.social_draft_tools import SOCIAL_DRAFT_TOOL_NAMES  # noqa: E402

register_tool_group("knowledge", custom_tools=sorted(LEGAL_TOOL_NAMES))
register_tool_group("sanctions", custom_tools=sorted(SANCTIONS_TOOL_NAMES))
register_tool_group("normflow", custom_tools=sorted(NORMFLOW_TOOL_NAMES))
register_tool_group("market", custom_tools=sorted(MARKET_TOOL_NAMES))
register_tool_group("research", custom_tools=sorted(RESEARCH_TOOL_NAMES))
register_tool_group("social", custom_tools=sorted(SOCIAL_DRAFT_TOOL_NAMES))

# S2：目录条目（search_tools 渐进式披露 / 系统提示目录摘要）随包注入
register_catalog_entries(BIZ_CATALOG)

# G1 倒挂清零（§18.5）：saas ping 由 server_app 软 import 改生命周期钩子注册。
# E2 门控（auth cap + 显式 SUPPORT_SYSTEM_URL）在钩子内 —— 自包含形态零外呼。
import os  # noqa: E402

from dawei.core.ext_hooks import register_lifecycle_hooks  # noqa: E402

from dawei_biz.saas.remote import start_ping_service, stop_ping_service  # noqa: E402


async def _saas_ping_startup() -> None:
    from dawei.runtime import get_capabilities

    if "auth" not in get_capabilities():
        print("[SaaS Ping] disabled (auth cap absent)")
        return
    if not os.getenv("SUPPORT_SYSTEM_URL", "").strip():
        print("[SaaS Ping] disabled (SUPPORT_SYSTEM_URL unset)")
        return
    await start_ping_service()
    print("[SaaS Ping] Remote ping service started")


register_lifecycle_hooks("saas_ping", _saas_ping_startup, stop_ping_service)
