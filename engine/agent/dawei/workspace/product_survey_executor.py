# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""产品调研真实执行器 — 兼容 shim（PRD §10 #4）。

执行器已上移至 Deep Research 通用框架（deep_research_framework.ResearchExecutor），
按 PipelineSpec 驱动任意调研流水线；本模块保留旧导入路径（测试/存量代码引用）。
"""

from dawei.workspace.deep_research_framework import ResearchExecutor

ProductSurveyExecutor = ResearchExecutor  # noqa: F401  向后兼容别名
