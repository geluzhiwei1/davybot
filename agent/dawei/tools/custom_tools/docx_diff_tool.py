# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""docx 文档对比 Tool。

对比两个 .docx 文件的结构化差异。
输出段落级别的增删改信息和格式变更。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.core.path_security import PathTraversalError, safe_path_join, sanitize_filename
from dawei.tools.custom_base_tool import CustomBaseTool
from dawei.tools.docx_engine.differ import DiffOp, DiffType, DocxDiffer
from dawei.tools.docx_engine.parser import DocxParser

logger = logging.getLogger(__name__)


class DocxDiffInput(BaseModel):
    """Input for DocxDiffTool."""

    file_path_a: str = Field(
        ...,
        description="旧版 docx 文件路径（基准版本）。",
    )
    file_path_b: str = Field(
        ...,
        description="新版 docx 文件路径（修改版本）。",
    )
    output_format: str = Field(
        "summary",
        description=('输出格式。"summary": 人类可读的差异摘要；"detailed": 包含每个变更的具体内容；"json": 结构化 JSON 格式。'),
    )


class DocxDiffTool(CustomBaseTool):
    """对比两个 .docx 文件的结构化差异。"""

    name: str = "docx_diff"
    description: str = "对比两个 .docx 文件的结构化差异。输出段落级别的增删改信息和格式变更。用于审查文档修改或生成修改报告。"
    args_schema: type[BaseModel] = DocxDiffInput

    @safe_tool_operation("docx_diff", fallback_value="Error: Failed to diff docx")
    def _run(
        self,
        file_path_a: str,
        file_path_b: str,
        output_format: str = "summary",
    ) -> str:
        # 获取工作区路径
        workspace_path = None
        if self.context and hasattr(self.context, "user_workspace"):
            workspace_path = self.context.user_workspace.path

        # 路径安全处理
        if workspace_path:
            try:
                path_a = Path(
                    safe_path_join(
                        workspace_path, file_path_a,
                        allow_absolute=False,
                        allowed_extensions={".docx"},
                    ),
                )
                path_b = Path(
                    safe_path_join(
                        workspace_path, file_path_b,
                        allow_absolute=False,
                        allowed_extensions={".docx"},
                    ),
                )
            except (PathTraversalError, ValueError) as e:
                return f"Error: 路径验证失败 - {e}"
        else:
            path_a = Path(file_path_a)
            path_b = Path(file_path_b)

        if path_a.suffix.lower() != ".docx":
            return f"Error: 不支持的文件格式: {path_a.suffix}，仅支持 .docx"
        if path_b.suffix.lower() != ".docx":
            return f"Error: 不支持的文件格式: {path_b.suffix}，仅支持 .docx"

        # 验证文件存在
        if not path_a.exists():
            return f"Error: 文件不存在: {file_path_a}"
        if not path_b.exists():
            return f"Error: 文件不存在: {file_path_b}"

        try:
            old_ast = DocxParser().parse(path_a)
            new_ast = DocxParser().parse(path_b)
            differ = DocxDiffer()
            result = differ.diff(old_ast, new_ast)

            if output_format == "json":
                return self._format_json(result.ops, path_a.name, path_b.name)
            if output_format == "detailed":
                return self._format_detailed(result.ops, path_a.name, path_b.name)
            return f"文档对比: {path_a.name} → {path_b.name}\n\n{result.summary}"

        except Exception as e:
            logger.error("Failed to diff docx: %s", e, exc_info=True)
            return f"Error: 对比失败: {e}"

    @staticmethod
    def _format_detailed(ops: list[DiffOp], name_a: str, name_b: str) -> str:
        """生成详细的对比输出。"""
        lines = [f"文档对比: {name_a} → {name_b}", ""]

        for op in ops:
            match op.type:
                case DiffType.INSERT:
                    text = op.node.text[:80] if op.node else ""
                    lines.append(f"[+] 插入段落 {op.position}: {text}")
                case DiffType.DELETE:
                    lines.append(f"[-] 删除段落 {op.position}")
                case DiffType.REPLACE:
                    lines.append(f"[~] 替换段落 {op.position}:")
                    lines.append(f"    旧: {(op.old_text or '')[:60]}")
                    lines.append(f"    新: {(op.new_text or '')[:60]}")
                case DiffType.MODIFY_STYLE:
                    old_name = op.old_style.style_name if op.old_style else "?"
                    new_name = op.new_style.style_name if op.new_style else "?"
                    lines.append(f"[S] 样式变更 段落 {op.position}: {old_name} → {new_name}")
                case DiffType.MODIFY_RUNS:
                    count = len(op.run_diffs) if op.run_diffs else 0
                    lines.append(f"[R] 内容变更 段落 {op.position}: {count} 处 Run 变更")
                    if op.run_diffs:
                        for rd in op.run_diffs[:5]:  # 最多显示 5 处
                            if rd.type == "insert" and rd.run:
                                lines.append(f'    + 插入 Run: "{rd.run.text[:40]}"')
                            elif rd.type == "delete" and rd.old_run:
                                lines.append(f'    - 删除 Run: "{rd.old_run.text[:40]}"')
                            elif rd.type == "modify" and rd.old_run and rd.run:
                                lines.append(f'    ~ 修改: "{rd.old_run.text[:30]}" → "{rd.run.text[:30]}"')

        return "\n".join(lines)

    @staticmethod
    def _format_json(ops: list[DiffOp], name_a: str, name_b: str) -> str:
        """生成 JSON 格式的对比输出。"""
        ops_data = []
        for op in ops:
            op_dict = {
                "type": op.type.value,
                "position": op.position,
            }
            if op.old_text is not None:
                op_dict["old_text"] = op.old_text
            if op.new_text is not None:
                op_dict["new_text"] = op.new_text
            if op.old_style is not None:
                op_dict["old_style"] = op.old_style.style_name
            if op.new_style is not None:
                op_dict["new_style"] = op.new_style.style_name
            if op.run_diffs:
                op_dict["run_changes"] = len(op.run_diffs)
            ops_data.append(op_dict)

        result = {
            "source": name_a,
            "target": name_b,
            "total_changes": len(ops),
            "changes": ops_data,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
