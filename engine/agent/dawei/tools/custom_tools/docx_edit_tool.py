# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""docx 增量编辑 Tool。

对 .docx 文件进行增量编辑（段落增删改、格式修改）。
使用扩展的 SEARCH/REPLACE 格式，通过段落序号锚点定位。
支持启用 Word 原生修订追踪（Track Changes）。
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from docx import Document
from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.core.path_security import PathTraversalError, safe_path_join, sanitize_filename
from dawei.tools.custom_base_tool import CustomBaseTool
from dawei.tools.docx_engine.diff_parser import DocxDiffParser
from dawei.tools.docx_engine.parser import DocxParser
from dawei.tools.docx_engine.patcher import DocxPatcher
from dawei.tools.docx_engine.revision import RevisionManager

logger = logging.getLogger(__name__)


class DocxEditInput(BaseModel):
    """Input for DocxEditTool."""

    file_path: str = Field(
        ...,
        description="要编辑的 docx 文件路径。",
    )
    diff: str = Field(
        ...,
        description=("编辑操作，使用扩展 SEARCH/REPLACE 格式。支持 REPLACE [序号]、INSERT AFTER [序号]、INSERT BEFORE [序号]、DELETE [序号]。"),
    )
    track_changes: bool = Field(
        False,
        description="是否启用 Word 修订追踪（Track Changes）。启用后修改会在 Word 中显示为修订痕迹。",
    )


class DocxEditTool(CustomBaseTool):
    """对 .docx 文件进行增量编辑。"""

    name: str = "docx_edit"
    description: str = (
        "对 .docx 文件进行增量编辑（段落增删改、格式修改）。"
        "使用扩展的 SEARCH/REPLACE 格式，通过段落序号锚点定位。"
        "支持启用 Word 原生修订追踪（Track Changes）。\n\n"
        "**使用前请先用 docx_read_structured 读取文档结构。**\n\n"
        "支持的操作格式：\n"
        "<<<<<<< REPLACE [序号]\n旧文本\n=======\n新文本\n>>>>>>> REPLACE\n\n"
        "<<<<<<< INSERT AFTER [序号]\n(样式名) 新文本\n>>>>>>> INSERT\n\n"
        "<<<<<<< INSERT BEFORE [序号]\n(样式名) 新文本\n>>>>>>> INSERT\n\n"
        "<<<<<<< DELETE [序号]\n>>>>>>> DELETE"
    )
    args_schema: type[BaseModel] = DocxEditInput

    @safe_tool_operation("docx_edit", fallback_value="Error: Failed to edit docx")
    def _run(
        self,
        file_path: str,
        diff: str,
        track_changes: bool = False,
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

        # 备份原文件
        backup_path = full_path.with_suffix(f".backup{full_path.suffix}")
        try:
            shutil.copy2(full_path, backup_path)
        except Exception as e:
            return f"Error: 无法创建备份文件: {e}"

        try:
            # 1. 解析 AST
            ast = DocxParser().parse(full_path)

            # 2. 解析 LLM 输出的 diff
            diff_parser = DocxDiffParser()
            diff_ops, errors = diff_parser.parse(diff, ast.paragraphs)

            if errors:
                # 有解析错误
                if diff_ops:
                    # 部分成功
                    pass
                else:
                    # 全部失败
                    error_text = "\n".join(f"✗ {e}" for e in errors)
                    return f"Error: 解析失败。\n\n{error_text}\n\n请修正后重试。"

            # 3. 打开 docx 并应用 patch
            doc = Document(str(full_path))
            patcher = DocxPatcher()
            results = patcher.apply(doc, diff_ops)

            # 4. 如果需要修订追踪
            if track_changes:
                revision_mgr = RevisionManager()
                revision_mgr.apply_revisions(doc, diff_ops, ast)

            # 5. 保存
            doc.save(str(full_path))

            # 6. 构建结果
            all_results = results + [f"✗ {e}" for e in errors]
            success_count = sum(1 for r in results if r.startswith("✓"))
            fail_count = len(all_results) - success_count

            if fail_count == 0:
                header = f"成功编辑 {full_path.name}，应用 {success_count} 处修改：\n"
            else:
                header = f"编辑 {full_path.name}，{success_count}/{len(all_results)} 处成功：\n"

            return header + "\n".join(all_results)

        except Exception as e:
            logger.error("Failed to edit docx %s: %s", full_path, e, exc_info=True)
            # 恢复备份
            try:
                shutil.copy2(backup_path, full_path)
            except Exception:
                pass
            return f"Error: 编辑失败，已恢复备份: {e}"

        finally:
            # 删除备份
            try:
                backup_path.unlink(missing_ok=True)
            except Exception:
                pass
