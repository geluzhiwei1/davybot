# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Diff 解析器 — 将 LLM 输出的扩展 SEARCH/REPLACE 格式解析为 DiffOp 列表。

支持的操作格式:
  <<<<<<< REPLACE [序号]
  旧文本
  =======
  新文本
  >>>>>>> REPLACE

  <<<<<<< INSERT AFTER [序号]
  (样式名) 新文本
  >>>>>>> INSERT

  <<<<<<< INSERT BEFORE [序号]
  (样式名) 新文本
  >>>>>>> INSERT

  <<<<<<< DELETE [序号]
  >>>>>>> DELETE
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .ast import (
    Paragraph,
    ParagraphStyle,
    Run,
    RunStyle,
)
from .differ import DiffOp, DiffType
from .patcher import parse_markdown_runs


@dataclass
class _ParsedBlock:
    """解析后的操作块。"""

    op_type: str  # REPLACE, INSERT AFTER, INSERT BEFORE, DELETE
    position: int  # 原始位置
    old_text: str | None = None  # REPLACE 旧文本
    new_text: str | None = None  # REPLACE/INSERT 新文本
    style_name: str = "Normal"  # INSERT 样式名


class DocxDiffParser:
    """解析 LLM 生成的扩展 SEARCH/REPLACE 格式。"""

    # REPLACE 块正则: <<<<<<< REPLACE [pos] \n old \n ======= \n new \n >>>>>>> REPLACE
    REPLACE_RE = re.compile(
        r"<<<<<<<\s+REPLACE\s+\[(\d+)\]\s*\n"
        r"(.*?)"  # old_text
        r"=======\s*\n"
        r"(.*?)"  # new_text
        r">>>>>>>\s+REPLACE",
        re.DOTALL,
    )

    # INSERT 块正则: <<<<<<< INSERT (AFTER|BEFORE) [pos] \n content \n >>>>>>> INSERT
    INSERT_RE = re.compile(
        r"<<<<<<<\s+INSERT\s+(AFTER|BEFORE)\s+\[(\d+)\]\s*\n"
        r"(.*?)"  # content (样式名) 文本
        r">>>>>>>\s+INSERT",
        re.DOTALL,
    )

    # DELETE 块正则: <<<<<<< DELETE [pos] \n >>>>>>> DELETE
    DELETE_RE = re.compile(
        r"<<<<<<<\s+DELETE\s+\[(\d+)\]\s*\n"
        r".*?"  # 可能有空行
        r">>>>>>>\s+DELETE",
        re.DOTALL,
    )

    def parse(self, diff_text: str, ast_paragraphs: list[Paragraph]) -> tuple[list[DiffOp], list[str]]:
        """解析 LLM 输出的 diff 文本，生成 DiffOp 列表。

        Args:
            diff_text: LLM 输出的 diff 文本
            ast_paragraphs: 当前文档的段落列表（用于验证位置和文本）

        Returns:
            (diff_ops, errors) — DiffOp 列表和错误信息列表
        """
        blocks = self._parse_blocks(diff_text)
        ops, errors = self._blocks_to_diff_ops(blocks, ast_paragraphs)
        return ops, errors

    def _parse_blocks(self, diff_text: str) -> list[_ParsedBlock]:
        """从 diff 文本中解析操作块。使用三种正则分别匹配不同操作类型。"""

        # 收集所有匹配及其位置，按位置排序
        all_matches: list[tuple[int, _ParsedBlock]] = []

        # 1. REPLACE 块
        for m in self.REPLACE_RE.finditer(diff_text):
            position = int(m.group(1))
            old_text = m.group(2).strip()
            new_text = m.group(3).strip()
            all_matches.append(
                (
                    m.start(),
                    _ParsedBlock(
                        op_type="REPLACE",
                        position=position,
                        old_text=old_text,
                        new_text=new_text,
                    ),
                )
            )

        # 2. INSERT 块
        for m in self.INSERT_RE.finditer(diff_text):
            direction = m.group(1)  # AFTER or BEFORE
            position = int(m.group(2))
            content = m.group(3).strip()

            # 解析 (样式名) 前缀
            style_name = "Normal"
            text = content
            style_match = re.match(r"^\(([^)]+)\)\s*(.*)", content, re.DOTALL)
            if style_match:
                style_name = style_match.group(1)
                text = style_match.group(2)

            all_matches.append(
                (
                    m.start(),
                    _ParsedBlock(
                        op_type=f"INSERT {direction}",
                        position=position,
                        new_text=text,
                        style_name=style_name,
                    ),
                )
            )

        # 3. DELETE 块
        for m in self.DELETE_RE.finditer(diff_text):
            position = int(m.group(1))
            all_matches.append(
                (
                    m.start(),
                    _ParsedBlock(
                        op_type="DELETE",
                        position=position,
                    ),
                )
            )

        # 按在文本中出现的位置排序
        all_matches.sort(key=lambda x: x[0])
        return [b for _, b in all_matches]

    def _blocks_to_diff_ops(
        self,
        blocks: list[_ParsedBlock],
        ast_paragraphs: list[Paragraph],
    ) -> tuple[list[DiffOp], list[str]]:
        """将解析后的操作块转换为 DiffOp，处理位置偏移。"""
        ops: list[DiffOp] = []
        errors: list[str] = []
        offset = 0

        for block in blocks:
            original_pos = block.position
            adjusted_pos = original_pos + offset

            # 位置范围验证
            if original_pos < 0 or original_pos > len(ast_paragraphs) - 1:
                errors.append(f"REPLACE/DELETE [{original_pos}]: 序号不存在，有效范围 [0, {len(ast_paragraphs) - 1}]")
                continue

            match block.op_type:
                case "REPLACE":
                    op, err = self._make_replace_op(adjusted_pos, block, ast_paragraphs)
                    if op:
                        ops.append(op)
                    if err:
                        errors.append(err)

                case "INSERT AFTER":
                    para = self._make_paragraph(block.new_text, block.style_name)
                    ops.append(
                        DiffOp(
                            type=DiffType.INSERT,
                            position=adjusted_pos + 1,
                            node=para,
                        )
                    )
                    offset += 1

                case "INSERT BEFORE":
                    para = self._make_paragraph(block.new_text, block.style_name)
                    ops.append(
                        DiffOp(
                            type=DiffType.INSERT,
                            position=adjusted_pos,
                            node=para,
                        )
                    )
                    offset += 1

                case "DELETE":
                    ops.append(
                        DiffOp(
                            type=DiffType.DELETE,
                            position=adjusted_pos,
                        )
                    )
                    offset -= 1

        return ops, errors

    def _make_replace_op(
        self,
        position: int,
        block: _ParsedBlock,
        ast_paragraphs: list[Paragraph],
    ) -> tuple[DiffOp | None, str | None]:
        """生成 REPLACE DiffOp。"""
        if block.old_text is None or block.new_text is None:
            return None, f"REPLACE [{block.position}]: 缺少旧文本或新文本"

        # 获取目标段落
        actual_pos = position
        if actual_pos < 0 or actual_pos >= len(ast_paragraphs):
            return None, f"REPLACE [{block.position}]: 位置 {actual_pos} 超出范围"

        target_para = ast_paragraphs[actual_pos]
        target_text = target_para.text

        # 验证旧文本匹配（去除 Markdown 格式标记后比较）
        stripped_old = _strip_markdown_format(block.old_text)
        stripped_target = _strip_markdown_format(target_text)

        if stripped_old != stripped_target:
            # 生成详细的错误信息
            return None, (f"REPLACE [{block.position}] 旧文本不匹配。\n文档中 [{block.position}] 的实际内容:\n  {target_text}\n你提供的旧文本:\n  {block.old_text}\n请使用完全一致的文本重试（注意保留 **bold** *italic* 等格式标记）。")

        return DiffOp(
            type=DiffType.REPLACE,
            position=position,
            old_text=block.old_text,
            new_text=block.new_text,
        ), None

    @staticmethod
    def _make_paragraph(text: str | None, style_name: str = "Normal") -> Paragraph:
        """从文本创建 Paragraph AST 节点。"""
        if not text:
            return Paragraph(index=-1, style=ParagraphStyle(style_name=style_name))

        runs = parse_markdown_runs(text)
        return Paragraph(
            index=-1,
            style=ParagraphStyle(style_name=style_name),
            runs=runs,
        )


def _strip_markdown_format(text: str) -> str:
    """去除 Markdown 格式标记，返回纯文本。"""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # **bold**
    text = re.sub(r"\*(.+?)\*", r"\1", text)  # *italic*
    text = re.sub(r"~~(.+?)~~", r"\1", text)  # ~~strikethrough~~
    text = re.sub(r"_(.+?)_", r"\1", text)  # _underline_
    text = re.sub(r"`(.+?)`", r"\1", text)  # `code`
    return text.strip()
