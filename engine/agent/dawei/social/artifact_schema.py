"""落盘协议 —— 专家会话结构化产出 → social-control 内容工件(PRD §7.6)。

会话是引擎,工件是资产:Agent 产出必须落盘、可溯源、可审计。
本模块定义会话产出 → POST /api/v1/contents 载荷的规范与校验。
"""

from __future__ import annotations

from typing import Any

REQUIRED_VARIANT_KEYS = {"text"}


class ArtifactSchemaError(ValueError):
    """产出不符合落盘协议(防垃圾入内容库)"""


def to_content_payload(structured: dict[str, Any], *, brand_id: str = "default") -> dict:
    """规范化会话产出为内容载荷。

    输入契约(Agent 结构化输出):
      title: str(必填)
      type: text|article|video_script|image_set(缺省 text)
      platforms: list[str](缺省取 variants 键)
      variants: {platform: {text: str, aigc_label?: str}}(至少 1 个)
      source: 溯源元数据(会话 id/热点 id/父内容 id)
    """
    if not isinstance(structured, dict):
        raise ArtifactSchemaError("产出必须是对象")

    title = str(structured.get("title", "")).strip()
    if not title:
        raise ArtifactSchemaError("title 必填")

    variants_raw = structured.get("variants") or {}
    if not isinstance(variants_raw, dict) or not variants_raw:
        raise ArtifactSchemaError("variants 至少包含一个平台稿件")

    variants: dict[str, dict] = {}
    for platform, v in variants_raw.items():
        if not isinstance(v, dict) or not str(v.get("text", "")).strip():
            raise ArtifactSchemaError(f"variants.{platform}.text 必填且非空")
        variants[str(platform)] = {
            "text": str(v["text"]),
            **({"aigc_label": str(v["aigc_label"])} if v.get("aigc_label") else {}),
        }

    platforms = structured.get("platforms") or list(variants.keys())
    type_ = structured.get("type") or "text"
    if type_ not in {"text", "article", "video_script", "image_set"}:
        raise ArtifactSchemaError(f"非法 type: {type_}")

    return {
        "brand_id": brand_id,
        "title": title,
        "type": type_,
        "target_platforms": [str(p) for p in platforms],
        "body": {"schema_version": 1, "headline": title, "variants": variants},
        "source_ref": {
            **(structured.get("source") or {}),
            "origin": "agent_session",
        },
    }


def extract_structured_output(message_text: str) -> dict[str, Any] | None:
    """从会话消息中提取 ```json 围栏结构化产出;无围栏返回 None。"""
    import json
    import re

    m = re.search(r"```json\s*(\{.*?\})\s*```", message_text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


__all__ = ["to_content_payload", "extract_structured_output", "ArtifactSchemaError"]
