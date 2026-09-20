# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""e2b SDK 能力检测 — network_policy 参数跨版本兼容

新版 e2b SDK 的 ``Sandbox.create`` 不再接受 ``network_policy`` kwarg
（签名改为 ``network: SandboxNetworkOpts`` / ``allow_internet_access``），
盲注入会触发 ConnectionConfig TypeError，导致沙箱创建整体失败。
旧版 SDK 仍接受 ``network_policy`` —— 检测后按能力注入，两侧兼容。

fail-open 语义：SDK 不支持时跳过注入并告警 —— network_policy 只是
出网限制的额外一层，沙箱隔离本身（MicroVM + F2 遮蔽）不受影响。
"""

from __future__ import annotations

import inspect

_cached: bool | None = None


def e2b_supports_network_policy() -> bool:
    """已安装 e2b SDK 的 ``Sandbox.create`` 是否接受 ``network_policy`` 参数。

    结果缓存（SDK 版本运行期不变）。
    """
    global _cached
    if _cached is not None:
        return _cached
    try:
        from e2b import Sandbox

        _cached = "network_policy" in inspect.signature(Sandbox.create).parameters
    except Exception:  # noqa: BLE001 — SDK 不可用/签名不可读：按不支持处理（调用方跳过注入）
        _cached = False
    return _cached
