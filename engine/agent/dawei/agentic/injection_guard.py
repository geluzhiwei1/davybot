# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""子任务输出注入扫描（P3-7，对标 Claude Code 的 output injection scanning）

子代理（子任务）产出的文本在回注父对话 / 作为 tool_result 返回之前，
必须先经 `sanitize_output()` 中和伪造的系统标签（<system-reminder>、
<command-message> 等），防止子代理输出被父代理误解为宿主注入的指令。

纯函数、无副作用，单测友好。
"""

import re

# 伪造系统标签模式（大小写不敏感、跨行）
_TAG_PATTERNS = [
    re.compile(p, re.IGNORECASE | re.DOTALL)
    for p in (
        r"</?system-reminder>",
        r"</?command-message>",
        r"</?command-name>",
        r"</?command-args>",
        r"</?system-warning>",
        r"</?local-command-stdout>",
    )
]

WARNING_HEADER = "[!可能注入 / POSSIBLE INJECTION] 子任务输出中包含疑似伪造的系统标签，已剥离标签并降级为普通文本：\n"


def detect_injection(text: str) -> bool:
    """是否包含疑似注入的系统标签"""
    return any(p.search(text) for p in _TAG_PATTERNS)


def sanitize_output(text: str) -> str:
    """中和子任务输出中的伪造系统标签。

    - 命中：剥离标签本身（保留内部文本），整段前置 WARNING_HEADER 标注
    - 未命中：原样返回

    Usage:
        safe_text = sanitize_output(raw_result)
    """
    if not detect_injection(text):
        return text
    sanitized = text
    for p in _TAG_PATTERNS:
        sanitized = p.sub("", sanitized)
    return WARNING_HEADER + sanitized
