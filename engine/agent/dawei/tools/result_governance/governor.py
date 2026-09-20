# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""L7 — 外层兜底 Governor（最关键的新增）

Governor 在 tool_executor 中：
- tool.run() 之前调用 check_input()（D 类 Echo 输入侧检查）
- tool.run() 之后调用 govern()（输出侧兜底）
- 被截断时调用 save_snapshot()（缓存原始结果）

GovernedResult 是 Governor 输出的信封对象（v7 最终版，含 X1-X5 修复）。
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .budget import TokenBudget
from .formatters import BlobWindow
from .metrics import get_metrics
from .policy import OutputPolicy, ToolOutputType, get_policy
from .store import ResultSnapshotStore, get_snapshot_store
from .token_estimator import TokenEstimator, get_token_estimator

logger = logging.getLogger(__name__)


@dataclass
class GovernedResult:
    """Governor 输出的信封对象——v7 最终版（含 X1-X5 修复）。

    数据流：
      to_llm_content()  -> ToolMessage.content -> LLM（截断版，无元数据）
      to_event_payload() -> WS event.result    -> 前端（截断版 + 元数据）
      raw_result         -> SnapshotStore       -> REST API（脱敏版）
      governance_meta    -> ToolMessage._governance_meta -> 会话持久化（元数据）
    """

    # ── 治理后的数据 ──
    data: Any  # BlobWindow dict / ListPageEnvelope dict / 原始小结果

    # ── 大小与格式 ──
    original_size: int  # 原始字节数
    governed_size: int  # 治理后字节数
    was_truncated: bool  # 是否截断
    format_type: str  # "raw" | "blob_window" | "list_page" | "summary_tier"

    # ── 快照引用 ──
    snapshot_id: str | None = None  # UUID v4（截断时非 None）

    # ── 原始结果（仅内存中保留，X4 用）──
    _raw_result: Any = None  # 原始未截断结果（不序列化）

    # ── 归属信息（X2 用）──
    _user_id: str = ""
    _workspace_id: str = ""

    # ── LLM 消费 ──
    def to_llm_content(self) -> str:
        """序列化为 LLM ToolMessage content——仅含治理后数据。"""
        if isinstance(self.data, (dict, list)):
            return json.dumps(self.data, ensure_ascii=False, default=str)
        return str(self.data)

    # ── 前端消费 ──
    def to_event_payload(self) -> dict:
        """序列化为 WebSocket TOOL_CALL_RESULT 载荷——含元数据。"""
        return {
            "data": self.data,
            "_governance": {
                "original_size": self.original_size,
                "governed_size": self.governed_size,
                "was_truncated": self.was_truncated,
                "format_type": self.format_type,
                "snapshot_id": self.snapshot_id,
            },
        }

    # ── 会话持久化（X1 修复）──
    def to_governance_meta(self) -> dict | None:
        """生成 ToolMessage._governance_meta——随会话持久化。"""
        if not self.was_truncated:
            return None
        return {
            "was_truncated": True,
            "original_size": self.original_size,
            "governed_size": self.governed_size,
            "format_type": self.format_type,
            "snapshot_id": self.snapshot_id,
        }

    # ── 执行历史（X4 修复）──
    def to_history_record(self) -> dict:
        """生成 execution_record 的 result 相关字段。"""
        return {
            "result": self.data,  # 治理后数据
            "result_original_size": self.original_size,
            "result_governed_size": self.governed_size,
            "result_was_truncated": self.was_truncated,
            "result_snapshot_id": self.snapshot_id,
        }


class OutputGovernor:
    """executor 级别的输出安全网。

    无状态方法集合（不持有 last_* 实例属性），避免并发调用时的线程安全问题。
    govern() 内部 catch all 异常，保证治理层永远不破坏工具执行。
    """

    def __init__(
        self,
        estimator: TokenEstimator | None = None,
        snapshot_store: ResultSnapshotStore | None = None,
    ):
        self._est = estimator or get_token_estimator()
        self._store = snapshot_store or get_snapshot_store()

    def check_input(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        policy: OutputPolicy,
    ) -> str | None:
        """输入侧检查（D 类 Echo）。返回非 None = 阻止执行。"""
        output_type = policy.output_type
        if isinstance(output_type, str):
            if output_type != ToolOutputType.ECHO.value:
                return None
        elif output_type != ToolOutputType.ECHO:
            return None

        if policy.echo_max_input_chars <= 0:
            return None  # 0 = 不检查

        content = tool_input.get("content", "")
        if len(content) > policy.echo_max_input_chars:
            return (
                f"⚠️ 内容过长（{len(content)} 字 > 上限 {policy.echo_max_input_chars}）。"
                f"写入已阻止。请拆分为多次写入：先 write_text_file 写前半部分，"
                f"再用 insert_text_content 追加后续内容。"
            )
        return None

    def govern(
        self,
        tool_name: str,
        result: Any,
        policy: OutputPolicy | None = None,
        *,
        call_id: str = "",
        user_id: str = "",
        workspace_id: str = "",
    ) -> GovernedResult:
        """输出侧治理。永不抛异常——出错时 passthru 原始结果。

        Args:
            tool_name: 工具名称
            result: 原始结果（str, dict, list, 或其他）
            policy: 输出策略（None 时按 tool_name 查找）
            call_id: 工具调用 ID（用于快照关联）
            user_id: 用户 ID（X2 归属）
            workspace_id: 工作区 ID（X2 归属）

        Returns:
            GovernedResult 信封对象
        """
        if policy is None:
            policy = get_policy(tool_name)

        try:
            # 序列化为字符串进行估算
            if isinstance(result, str):
                result_str = result
            elif isinstance(result, (dict, list)):
                result_str = json.dumps(result, ensure_ascii=False, default=str)
            else:
                result_str = str(result)

            original_size = len(result_str.encode("utf-8"))
            tokens = self._est.estimate(result_str)

            # 在预算内 → 直接通过
            if tokens <= policy.max_output_tokens:
                get_metrics().record_call(
                    tool_name=tool_name,
                    original_bytes=original_size,
                    governed_bytes=original_size,
                    was_truncated=False,
                    format_type="raw",
                )
                return GovernedResult(
                    data=result,
                    original_size=original_size,
                    governed_size=original_size,
                    was_truncated=False,
                    format_type="raw",
                    _raw_result=result,
                    _user_id=user_id,
                    _workspace_id=workspace_id,
                )

            # 超预算 → 按类型兜底截断
            logger.info(
                f"Governor truncating {tool_name}: tokens={tokens} > budget={policy.max_output_tokens}",
            )

            # 获取输出类型
            output_type = policy.output_type
            if isinstance(output_type, str):
                output_type_str = output_type
            else:
                output_type_str = output_type.value if hasattr(output_type, "value") else str(output_type)

            if output_type_str == ToolOutputType.BLOB.value:
                governed_data, format_type = self._govern_blob(result_str, policy, tool_name)
            elif output_type_str == ToolOutputType.LIST.value:
                governed_data, format_type = self._govern_list(result, policy, tool_name)
            elif output_type_str == ToolOutputType.STRUCTURED.value:
                governed_data, format_type = self._govern_structured(result, policy, tool_name)
            else:
                governed_data, format_type = self._hard_truncate(result_str, policy), "raw"

            # 计算治理后大小
            if isinstance(governed_data, (dict, list)):
                governed_str = json.dumps(governed_data, ensure_ascii=False, default=str)
            else:
                governed_str = str(governed_data)
            governed_size = len(governed_str.encode("utf-8"))

            # 存快照
            snapshot_id = self.save_snapshot(
                result,
                call_id,
                tool_name,
                policy,
                user_id=user_id,
                workspace_id=workspace_id,
            )

            # 记录指标
            tokens_after = self._est.estimate(governed_str)
            get_metrics().record_call(
                tool_name=tool_name,
                original_bytes=original_size,
                governed_bytes=governed_size,
                was_truncated=True,
                format_type=format_type,
                tokens_saved=tokens - tokens_after,
            )

            return GovernedResult(
                data=governed_data,
                original_size=original_size,
                governed_size=governed_size,
                was_truncated=True,
                format_type=format_type,
                snapshot_id=snapshot_id,
                _raw_result=result,
                _user_id=user_id,
                _workspace_id=workspace_id,
            )

        except Exception as e:
            # M7：治理层永不破坏工具执行——出错时返回原始结果
            logger.error(f"OutputGovernor error for {tool_name}: {e}", exc_info=True)
            get_metrics().record_error()
            try:
                orig_size = len(str(result).encode("utf-8"))
            except Exception:
                orig_size = 0
            return GovernedResult(
                data=result,
                original_size=orig_size,
                governed_size=orig_size,
                was_truncated=False,
                format_type="raw",
                _raw_result=result,
            )

    def save_snapshot(
        self,
        original_result: Any,
        call_id: str,
        tool_name: str,
        policy: OutputPolicy,
        *,
        user_id: str = "",
        workspace_id: str = "",
    ) -> str | None:
        """将被截断的原始结果存入快照存储。"""
        try:
            snapshot_id = self._store.put(
                tool_name,
                original_result,
                user_id=user_id,
                workspace_id=workspace_id,
                policy_name=tool_name,
            )
            get_metrics().record_snapshot(success=True)
            return snapshot_id
        except Exception as e:
            logger.warning(f"Snapshot save failed for {tool_name}: {e}")
            get_metrics().record_snapshot(success=False)
            return None

    def _govern_blob(self, text: str, policy: OutputPolicy, tool_name: str) -> tuple[Any, str]:
        """head + tail 截断，保留首尾。"""
        # S3 修复：execute_command/shell_command 返回 JSON，
        # 不能做 head+tail 行截断——会破坏 JSON 结构
        if tool_name in ("execute_command", "shell_command"):
            return self._hard_truncate(text, policy), "raw"

        lines = text.split("\n")
        if len(lines) <= policy.blob_max_lines:
            return self._hard_truncate(text, policy), "raw"

        budget = TokenBudget(policy.max_output_tokens, self._est)
        blob_data = BlobWindow.render(text, policy, budget, total_lines=len(lines))
        return blob_data, "blob_window"

    def _govern_list(self, result: Any, policy: OutputPolicy, tool_name: str) -> tuple[Any, str]:
        """列表类兜底：保留前 N 项 + 截断指示器。"""
        # 尝试解析为 list
        items = None
        if isinstance(result, list):
            items = result
        elif isinstance(result, dict):
            # 尝试从 dict 中提取 list
            for key in ("items", "results", "entities", "hits", "data", "documents", "records"):
                if key in result and isinstance(result[key], list):
                    items = result[key]
                    break

        if items is not None and len(items) > policy.list_max_items:
            # 截取前 N 项
            truncated_items = items[: policy.list_max_items]
            total = len(items)
            return {
                "type": "list_page",
                "items": truncated_items,
                "total": total,
                "offset": 0,
                "limit": policy.list_max_items,
                "has_more": total > policy.list_max_items,
                "next_offset": policy.list_max_items,
                "summary": f"显示前 {policy.list_max_items}/{total} 条",
            }, "list_page"

        # 无法识别为 list，做 hard truncate
        if isinstance(result, str):
            result_str = result
        elif isinstance(result, (dict, list)):
            result_str = json.dumps(result, ensure_ascii=False, default=str)
        else:
            result_str = str(result)
        return self._hard_truncate(result_str, policy), "raw"

    def _govern_structured(self, result: Any, policy: OutputPolicy, tool_name: str) -> tuple[Any, str]:
        """结构化对象兜底：字段级截断。"""
        if isinstance(result, dict):
            # 限制嵌套数组大小
            max_array = policy.structured_array_max
            truncated = {}
            for k, v in result.items():
                if isinstance(v, list) and len(v) > max_array:
                    truncated[k] = v[:max_array]
                    truncated[f"{k}_total"] = len(v)
                    truncated[f"{k}_truncated"] = True
                elif isinstance(v, dict):
                    # 递归一层
                    sub_truncated = {}
                    for sk, sv in v.items():
                        if isinstance(sv, list) and len(sv) > max_array:
                            sub_truncated[sk] = sv[:max_array]
                            sub_truncated[f"{sk}_total"] = len(sv)
                        else:
                            sub_truncated[sk] = sv
                    truncated[k] = sub_truncated
                else:
                    truncated[k] = v
            return truncated, "raw"

        # 非 dict，hard truncate
        if isinstance(result, str):
            result_str = result
        elif isinstance(result, (dict, list)):
            result_str = json.dumps(result, ensure_ascii=False, default=str)
        else:
            result_str = str(result)
        return self._hard_truncate(result_str, policy), "raw"

    def _hard_truncate(self, text: str, policy: OutputPolicy) -> str:
        """硬截断到预算内，尾部追加指示器。"""
        budget = TokenBudget(policy.max_output_tokens, self._est)
        truncated = budget.truncate_to_budget(text)
        if len(truncated) < len(text):
            truncated += "\n" + policy.truncation_notice
        return truncated


# 单例
_governor: OutputGovernor | None = None


def get_governor() -> OutputGovernor:
    """获取全局 OutputGovernor 单例。"""
    global _governor
    if _governor is None:
        _governor = OutputGovernor()
    return _governor
