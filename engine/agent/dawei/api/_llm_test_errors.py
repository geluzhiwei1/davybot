# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only
"""把 LLM 提供商「测试连接」的底层异常翻译成用户可理解、可行动的提示。

测试端点用流式请求探测模型是否支持 tool call。上游（provider / 网关 / 代理）
在响应中途断连时会抛出 httpcore/aiohttp 的技术性异常（典型如 "Connection closed"），
普通用户无法据此判断原因。这里按关键字归类，给出排查方向。
原始 traceback 仍由调用方 ``logger.exception`` 记录，便于排查。
"""


def humanize_llm_test_error(error: BaseException) -> str:
    """Return a human-readable, actionable hint for an LLM test failure."""
    raw = str(error)
    low = raw.lower()

    if any(
        k in low
        for k in (
            "connection closed",
            "remoteprotocolerror",
            "peer closed",
            "connection reset",
            "connection aborted",
            "unexpectedeof",
        )
    ):
        return (
            "无法从该地址获取完整响应（连接被服务端中途关闭）。"
            "常见原因：① Base URL 不正确或目标服务未运行；"
            "② 填写的是网关/代理地址，该地址对「流式」请求不稳定或不支持；"
            "③ 网络中断。"
        )
    if any(
        k in low
        for k in (
            "connection refused",
            "connect error",
            "cannot connect",
            "name or service not known",
            "nodename nor servname",
            "getaddrinfo failed",
        )
    ):
        return "无法连接到目标地址（连接被拒绝 / 域名无法解析）。请确认 Base URL 正确且服务正在运行。"
    if "timeout" in low or "timed out" in low:
        return "请求超时。目标服务响应过慢或不可达，请检查网络或增大超时时间。"
    if any(k in low for k in ("401", "unauthorized", "incorrect api key", "invalid api key", "authentication")):
        return "认证失败（401）。API Key 不正确或已过期。"
    if "403" in low or "forbidden" in low:
        return "授权被拒（403）。API Key 无权访问该模型或地址。"
    if "404" in low or "not found" in low:
        return "地址或模型不存在（404）。请检查 Base URL 是否完整（通常需含 /v1）以及模型 ID 是否正确。"
    if "model" in low and any(k in low for k in ("not found", "does not exist", "decommissioned", "unavailable")):
        return "模型不存在。请检查「模型 ID」是否为该供应商支持的型号。"
    if "ssl" in low or "certificate" in low:
        return "SSL/证书校验失败。请检查 Base URL 协议（http/https）与证书。"
    return raw or "未知错误"
