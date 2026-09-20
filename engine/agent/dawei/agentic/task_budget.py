# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""子任务超时与 token 预算（P3-3）

纯函数模块（无网络/无状态，便于单测）：
- extract_usage_total: 从 UsageMessage.data 容错提取 token 总数
  （OpenAI 风格 total_tokens / prompt+completion；ollama 风格 input+output）
- build_budget_failure_result: 超限原因 → task_completion 失败 JSON
  （沿用既有 task_completion 契约，父任务 summary 回注 / run_task 提取链路零改动即可见到原因）
- deadline_exceeded: 主循环墙钟 deadline 判定（None/非正数 = 不限制）

计量数据源说明：全局 CostTracker（cost_tools 链路）当前无 producer（从未 record_call），
故 P3-3 采用 executor 内 UsageMessage 实时累加（每子任务独立计数，天然隔离）。
"""

import json
import time


def extract_usage_total(data) -> int:
    """从 UsageMessage.data 容错提取 token 总数。

    识别三种键风格（全部为 int 才计入，任一缺失/类型异常 → 0）：
    - OpenAI: {"total_tokens": N}
    - OpenAI 分列: {"prompt_tokens": N, "completion_tokens": M}
    - ollama: {"input_tokens": N, "output_tokens": M}
    """
    if not isinstance(data, dict):
        return 0
    for keys in (("total_tokens",), ("prompt_tokens", "completion_tokens"), ("input_tokens", "output_tokens")):
        vals = [data.get(k) for k in keys]
        if all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
            return int(sum(vals))
    return 0


def build_budget_failure_result(kind: str, *, used: int, limit) -> str:
    """构造超限失败的 task_completion JSON（status=failed，原因在 result）。

    Args:
        kind: "token_budget" | "timeout"
        used: 已用量（token 数 或 秒数）
        limit: 上限值
    """
    unit = "tokens" if kind == "token_budget" else "seconds"
    reason = f"[{kind}_exceeded] subtask aborted: used {used} {unit} > limit {limit} {unit}"
    return json.dumps(
        {
            "type": "task_completion",
            "status": "failed",
            "result": reason,
            "kind": kind,
            "used": used,
            "limit": limit,
            "message": f"{kind} exceeded; subtask marked FAILED (fast-fail, no retry)",
        },
        ensure_ascii=False,
    )


def deadline_exceeded(started_monotonic: float | None, timeout_seconds) -> bool:
    """墙钟 deadline 判定（timeout_seconds 为 None/非正数 = 不限制）"""
    if started_monotonic is None or not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
        return False
    return (time.monotonic() - started_monotonic) > timeout_seconds
