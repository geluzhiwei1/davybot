# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""docx 结构化读取 Tool。

读取 .docx 文件的结构化内容，返回带段落序号锚点的文本，
保留样式和格式信息。用于在编辑前理解文档结构。
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.core.path_security import PathTraversalError, safe_path_join, sanitize_filename
from dawei.tools.custom_base_tool import CustomBaseTool
from dawei.tools.docx_engine.formatter import DocxASTFormatter
from dawei.tools.docx_engine.parser import DocxParser

logger = logging.getLogger(__name__)


class DocxReadStructuredInput(BaseModel):
    """Input for DocxReadStructuredTool."""

    file_path: str = Field(
        ...,
        description="docx 文件路径，相对于工作区目录。",
    )
    detail_level: str = Field(
        "run",
        description=('输出详细程度。"paragraph": 仅段落文本和样式；"run": 包含行内格式标记（**bold** *italic*）；"full": 包含所有格式属性。'),
    )
    start_paragraph: int | None = Field(
        None,
        description="起始段落序号（0-based），不指定则从开头开始。",
    )
    end_paragraph: int | None = Field(
        None,
        description="结束段落序号（0-based），不指定则到末尾。",
    )


class DocxReadStructuredTool(CustomBaseTool):
    """结构化读取 docx 文件，输出带锚点文本。"""

    name: str = "docx_read_structured"
    description: str = "读取 .docx 文件的结构化内容。返回带段落序号锚点的文本，保留样式和格式信息。用于在编辑前理解文档结构。"
    args_schema: type[BaseModel] = DocxReadStructuredInput

    @safe_tool_operation("docx_read_structured", fallback_value="Error: Failed to read docx")
    def _run(
        self,
        file_path: str,
        detail_level: str = "run",
        start_paragraph: int | None = None,
        end_paragraph: int | None = None,
    ) -> str:
        # 获取工作区路径
        workspace_path = None
        if self.context and hasattr(self.context, "user_workspace"):
            workspace_path = self.context.user_workspace.path

        # 路径安全处理
        if workspace_path:
            try:
                full_path = Path(
                    safe_path_join(
                        workspace_path, file_path,
                        allow_absolute=False,
                        allowed_extensions={".docx"},
                    ),
                )
            except (PathTraversalError, ValueError) as e:
                return f"Error: 路径验证失败 - {e}"
        else:
            full_path = Path(file_path)

        if not full_path.exists():
            return f"Error: 文件不存在: {file_path}"

        if full_path.suffix.lower() != ".docx":
            return f"Error: 不支持的文件格式: {full_path.suffix}，仅支持 .docx"

        try:
            ast = DocxParser().parse(full_path)
            formatter = DocxASTFormatter()
            text = formatter.format(
                ast,
                detail=detail_level,
                start_paragraph=start_paragraph,
                end_paragraph=end_paragraph,
            )

            total_paragraphs = len(ast.paragraphs)
            header = f"文件: {full_path.name} (共 {total_paragraphs} 个段落)\n"
            return header + text
        except Exception as e:
            logger.error("Failed to read docx %s: %s", full_path, e, exc_info=True)
            return f"Error: 解析 docx 失败: {e}"
