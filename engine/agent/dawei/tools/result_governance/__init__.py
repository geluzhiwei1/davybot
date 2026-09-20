# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工具结果治理框架（Token Governance）

七层组件：
  L1 TokenEstimator — token 估算
  L2 ResultSnapshotStore — 截断结果快照缓存
  L3 TokenBudget — 渲染期运行预算
  L4 OutputPolicy — 按工具配置的输出策略
  L5 Formatters — BlobWindow / ListPageEnvelope / StructuredRenderer
  L7 OutputGovernor — executor 级外层兜底

核心入口：
  get_governor() → OutputGovernor 单例
  get_policy(tool_name) → OutputPolicy
  GovernedResult — 信封对象（to_llm_content / to_event_payload / to_governance_meta / to_history_record）
"""

from .budget import TokenBudget
from .formatters import BlobWindow, ListPageEnvelope, StructuredRenderer
from .governor import GovernedResult, OutputGovernor, get_governor
from .metrics import GovernanceMetrics, get_metrics
from .policy import OutputPolicy, ToolOutputType, get_policy
from .sanitizer import sanitize_tool_output
from .store import ResultSnapshotStore, ToolResultSnapshot, get_snapshot_store
from .token_estimator import TokenEstimator, get_token_estimator

__all__ = [
    # L1
    "TokenEstimator",
    "get_token_estimator",
    # L2
    "ResultSnapshotStore",
    "ToolResultSnapshot",
    "get_snapshot_store",
    # L3
    "TokenBudget",
    # L4
    "OutputPolicy",
    "ToolOutputType",
    "get_policy",
    # L5
    "BlobWindow",
    "ListPageEnvelope",
    "StructuredRenderer",
    # L7
    "OutputGovernor",
    "GovernedResult",
    "get_governor",
    # Metrics
    "GovernanceMetrics",
    "get_metrics",
    # X3
    "sanitize_tool_output",
]
