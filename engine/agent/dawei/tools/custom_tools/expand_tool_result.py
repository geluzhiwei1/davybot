# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""expand_tool_result — 钻取被截断的工具结果

当 Governor 截断工具结果时，LLM 可调本工具从快照中取回完整数据，
而无需重新调用原始工具（避免上游 API 被轰炸）。
"""

import json
import logging

from pydantic import BaseModel, Field

from dawei.tools.custom_base_tool import CustomBaseTool

logger = logging.getLogger(__name__)


class ExpandToolResultInput(BaseModel):
    snapshot_id: str = Field(..., description="截断结果中提供的快照 ID")
    item_idx: int | None = Field(None, ge=0, description="列表类结果中要展开的条目索引（从0开始）")
    detail_level: str = Field("summary", description="展开级别：summary(概要) / full(完整) / metadata(仅元数据)")


class ExpandToolResultTool(CustomBaseTool):
    """从快照存储中取回被截断的工具结果。"""

    name: str = "expand_tool_result"
    description: str = (
        "展开之前被截断的工具结果。当工具返回结果中包含 snapshot_id 时，"
        "可用本工具获取完整数据，无需重新调用原始工具。"
    )
    args_schema = ExpandToolResultInput

    def __init__(self):
        super().__init__()

    def _run(self, snapshot_id: str, item_idx: int | None = None, detail_level: str = "summary", **kwargs) -> str:
        from dawei.tools.result_governance import get_snapshot_store

        store = get_snapshot_store()
        snapshot = store.get(snapshot_id)

        if snapshot is None:
            return json.dumps(
                {"error": "快照不存在或已过期", "snapshot_id": snapshot_id},
                ensure_ascii=False,
            )

        raw = snapshot.redacted_result if snapshot.redacted_result is not None else snapshot.raw_result

        if detail_level == "metadata":
            return json.dumps(
                {
                    "tool_name": snapshot.tool_name,
                    "original_size": len(str(snapshot.raw_result).encode("utf-8")) if snapshot.raw_result else 0,
                    "created_at": snapshot.timestamp.isoformat() if snapshot.timestamp else None,
                },
                ensure_ascii=False,
            )

        # If item_idx specified, drill into list items
        if item_idx is not None and isinstance(raw, (list, dict)):
            items = None
            if isinstance(raw, list):
                items = raw
            elif isinstance(raw, dict):
                for key in ("items", "results", "entities", "hits", "data"):
                    if key in raw and isinstance(raw[key], list):
                        items = raw[key]
                        break

            if items and 0 <= item_idx < len(items):
                return json.dumps(
                    {"item": items[item_idx], "index": item_idx, "total": len(items)},
                    ensure_ascii=False,
                    default=str,
                )
            return json.dumps(
                {"error": f"索引 {item_idx} 超出范围", "total": len(items) if items else 0},
                ensure_ascii=False,
            )

        # Full or summary
        if detail_level == "full":
            result_str = json.dumps(raw, ensure_ascii=False, default=str) if not isinstance(raw, str) else raw
            # Still apply a generous limit to avoid re-explosion
            _MAX_EXPAND = 50000
            if len(result_str) > _MAX_EXPAND:
                result_str = result_str[:_MAX_EXPAND] + f"\n...(展开结果仍然过大，已截断至 {_MAX_EXPAND} 字符)"
            return result_str

        # Summary: first N items or first N chars
        if isinstance(raw, list):
            items = raw[:10]
            return json.dumps(
                {"items": items, "total": len(raw), "shown": min(10, len(raw))},
                ensure_ascii=False,
                default=str,
            )
        if isinstance(raw, dict):
            summary = {k: (v if not isinstance(v, list) else f"[{len(v)} items]") for k, v in raw.items()}
            return json.dumps(summary, ensure_ascii=False, default=str)
        text = str(raw)
        return text[:2000] + ("..." if len(text) > 2000 else "")
