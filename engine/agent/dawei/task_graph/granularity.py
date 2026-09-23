# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""子任务粒度契约探测（§3.1 L1 粒度契约：R1-R3 硬闸 + R4 观察线）。

事故背景（demo.normnomos.com 2026-09-22 子任务 c5d42736）：一份 message
涵盖 6 份法律文件 × 4 个检查维度的"巨子任务"，最终轮单次 LLM 长生成被
网关 300s 流超时杀死 → 504 → 子任务/父任务/整图三级失败。根因在创建层：
整条派发链路只有数量维度护栏（并发/深度/去重），没有任何"单任务大小"
维度的约束。

设计原则：**宁可漏报不可误伤** —— R2 只拦"处理类动词 + 数字(≥2) + 量词
+ 文书类名词"的紧组合；漏网的靠 R4（TaskValidator warning）埋点观察后
收紧。合法单任务（产出仍是单一交付物）不得被拦，例如
"整理 3 个章节成 1 份报告"（章节是产出构件，不是 N 份同类输入文书）。

置于 task_graph 包（叶子层）：workflow_tools（工具层）与 task_validator
（同包）都要用，granularity 本身无任何 agentic 依赖。
"""

import re

# R1: message 硬顶（字符）。单一交付物指令 + 输出规范 ≪ 800；超长几乎
# 必然是"把 N 份同类工作写进一个子任务"（事故 message 400+ 字涵盖 6 份文件）。
MAX_SUBTASK_MESSAGE_CHARS = 800
# R4: 观察线（TaskValidator warning）。500-800 之间不阻断，进 metrics 观察。
SUBTASK_MESSAGE_WARN_CHARS = 500

# 处理类动词（中英）。只拦"动词 + 数量 + 文书"组合，动词单独出现不拦。
_VERB = (
    r"(?:审查|审核|检查|起草|撰写|编写|翻译|分析|处理|整理|修改|修订|核对|评估|审阅|"
    r"review|draft|write|translate|analyze|process|check|audit|proofread)"
)
# 数字：2-9、两位数以上、或中文数字（≥2）。不含"1/一"——"1 份报告"是单一交付物。
_NUM = r"(?:[2-9]|\d{2,}|[两三四五六七八九十]{1,3})"
# 量词
_MEASURE = r"(?:份|个|篇)"
# 文书类名词。章节/要点等产出构件不算（"整理 3 个章节成 1 份报告"合法）。
_DOC_NOUN = (
    r"(?:文件|文档|报告|合同|协议|文书|卷宗|裁决|判决|说明书|意见书|"
    r"documents?|files?|papers?|docs|reports?|contracts?)"
)

# 中文形：动词 …(≤24 非句界字符)… N 份 …(≤6 非句界字符)… 文书名词。
# 第二段间隙收紧到 6：挡住"…3 个[章节成 1 份]报告"这类"合并成一份"语义
# （章节成 1 份 = 7 字符 > 6 不命中），同时不伤"审查 6 份[法律]文件"（间隙 2）。
_RE_ZH = re.compile(
    rf"{_VERB}[^。；;\n]{{0,24}}?{_NUM}\s*{_MEASURE}[^。；;\n]{{0,6}}?{_DOC_NOUN}",
    re.IGNORECASE,
)
# 英文形：verb …(≤32)… N (documents|files|…)
_RE_EN = re.compile(
    rf"{_VERB}\b[^。\n]{{0,32}}?\b{_NUM}\s+(?:{_DOC_NOUN})",
    re.IGNORECASE,
)
# R3: 验收标准里的复数信号 —— "每份/逐份/全部 N 份/所有 N 份"意味着
# 验收对象本身就是 N 份，单子任务必然串行 N 件工作。
_RE_ACCEPTANCE_PLURAL = re.compile(
    r"(每份|逐份|全部\s*[2-9一二两三四五六七八九十\d]*\s*份|所有\s*\d+\s*(?:份|个|篇|documents?|files?))",
    re.IGNORECASE,
)


def detect_plural_deliverables(text: str | None) -> str | None:
    """R2：探测 message 中的"N 份同类文书工作"信号。

    Returns:
        命中的证据片段（供 error 提示回显给 LLM 定位）；未命中返回 None。
    """
    if not text:
        return None
    for pattern in (_RE_ZH, _RE_EN):
        matched = pattern.search(text)
        if matched:
            return matched.group(0)
    return None


def acceptance_implies_plural(text: str | None) -> str | None:
    """R3：验收标准含"每份/逐份/全部N份/所有N份"→ 目标本身就是复数交付。

    Returns:
        命中的证据片段；未命中返回 None。
    """
    if not text:
        return None
    matched = _RE_ACCEPTANCE_PLURAL.search(text)
    return matched.group(0) if matched else None
