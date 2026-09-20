"""值班 Agent 编排 —— soc-trend-spotter:当日热点 × 品牌画像 → 选题卡(PRD §6.10/§11.1 第 3 层)。

llm_call 可注入;产出经校验后批量推送控制面(POST /trending/ideas)。
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from dawei.social.service import LlmCall

DUTY_PROMPT = """你是社媒选题策划专家(soc-trend-spotter 值班任务)。
根据当日热点与品牌画像,筛选并生成选题推荐。要求:
1. 只推荐与品牌业务相关的热点(相关度 < 0.5 的丢弃)
2. timeliness 判定:rising(升温)/ peak(高峰)/ declining(回落)
3. angle 给出品牌切入角度;reasoning 说明推荐理由
4. 不编造热点外的事实
输出严格 JSON 围栏:
```json
{"ideas": [{"title": "...", "angle": "...", "reasoning": "...",
  "relevance_score": 0.85, "timeliness": "rising",
  "trending_item_ids": ["<hash>"]}]}
```"""


def run_duty(
    trending_items: list[dict[str, Any]],
    brand_profile: dict[str, Any],
    *,
    llm_call: LlmCall | Callable[[str, str], str],
) -> list[dict[str, Any]]:
    """热点 × 画像 → 校验后的选题卡载荷列表。"""
    if not trending_items:
        return []

    lines = "\n".join(
        f"- [{it.get('platform', '?')}] {it.get('title', '')}(hash:{it.get('content_hash', '')})"
        for it in trending_items[:30]
    )
    user = (
        f"品牌画像:\n{json.dumps(brand_profile, ensure_ascii=False)}\n\n"
        f"当日热点:\n{lines}"
    )
    reply = llm_call(DUTY_PROMPT, user)
    parsed = _extract(reply)
    if parsed is None:
        raise ValueError("值班产出未包含 JSON 围栏")
    return [i for i in parsed.get("ideas", []) if _valid_idea(i)]


def _extract(reply: str) -> dict[str, Any] | None:
    m = re.search(r"```json\s*(\{.*?\})\s*```", reply, re.DOTALL)
    if not m:
        return None
    try:
        out = json.loads(m.group(1))
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        return None


def _valid_idea(idea: Any) -> bool:
    """落盘闸门:字段齐全 + 分数合法 —— 防垃圾选题入库。"""
    if not isinstance(idea, dict):
        return False
    if not str(idea.get("title", "")).strip():
        return False
    score = idea.get("relevance_score")
    if not isinstance(score, (int, float)) or not 0.0 <= float(score) <= 1.0:
        return False
    if idea.get("timeliness") not in {"rising", "peak", "declining"}:
        return False
    return bool(str(idea.get("angle", "")).strip())


def run_duty_pipeline(
    trending_items: list[dict[str, Any]],
    brand_profile: dict[str, Any],
    *,
    llm_call: LlmCall | Callable[[str, str], str],
    brand_id: str,
    tenant_id: str,
    push: Callable[..., Any] | None = None,
    generate: Callable[..., Any] | None = None,
    max_drafts: int = 1,
    draft_platforms: list[str] | None = None,
) -> dict[str, int]:
    """值班全链(热点 → 选题 → 成稿 → 落盘 draft 工件)。PRD §6.10 L3:自动成稿 + 人工批准。

    成稿以 draft 状态入内容库等待审批(审批关卡硬性,§5.2 不变量);
    单稿失败不阻断批次。push/generate 可注入(单测打桩)。
    """
    from dawei.social.artifact_schema import to_content_payload

    ideas = run_duty(trending_items, brand_profile, llm_call=llm_call)
    if push is None:
        from dawei.social import bridge
        push = bridge.push_artifact
    if generate is None:
        from dawei.social.service import generate_variants
        generate = generate_variants

    drafts = 0
    for idea in ideas[:max_drafts]:
        try:
            source = "\n".join(filter(None, [
                str(idea.get("title", "")), str(idea.get("angle", "")),
                str(idea.get("reasoning", "")),
            ]))
            structured = generate(source, draft_platforms or ["xiaohongshu"], llm_call=llm_call)
            payload = to_content_payload(structured, brand_id=brand_id)
            push(payload, tenant_id=tenant_id)
            drafts += 1
        except Exception:
            continue  # 单稿失败不阻断批次(选题仍在,人工可再生成)
    return {"created_ideas": len(ideas), "created_drafts": drafts}


__all__ = ["run_duty", "run_duty_pipeline", "DUTY_PROMPT"]
