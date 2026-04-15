# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""结构化 Diff 引擎。

接收两个 DocxAST，输出一组 DiffOp 操作，描述从旧文档到新文档的差异。
采用两阶段 diff：先段落级 LCS 对齐，再 Run 级细化。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from typing import Literal

from .ast import (
    DocxAST,
    Node,
    Paragraph,
    ParagraphStyle,
    Run,
    RunStyle,
    Table,
)


class DiffType(str, Enum):
    INSERT = "insert"
    DELETE = "delete"
    REPLACE = "replace"
    MODIFY_STYLE = "modify_style"
    MODIFY_RUNS = "modify_runs"


@dataclass
class RunDiffOp:
    """Run 级别的变更。"""

    type: Literal["insert", "delete", "modify"]
    position: int  # 在段落 runs 列表中的位置
    run: Run | None = None  # INSERT: 新 Run；MODIFY: 修改后的 Run
    old_run: Run | None = None  # DELETE/MODIFY: 原始 Run


@dataclass
class DiffOp:
    """文档级别的单条变更操作。"""

    type: DiffType
    position: int  # 目标节点在 nodes 列表中的位置（0-based）

    # INSERT: 要插入的节点
    node: Paragraph | Table | None = None

    # REPLACE: 旧文本和新文本（段落级替换）
    old_text: str | None = None
    new_text: str | None = None

    # MODIFY_STYLE: 样式变更
    old_style: ParagraphStyle | None = None
    new_style: ParagraphStyle | None = None

    # MODIFY_RUNS: Run 级别变更列表
    run_diffs: list[RunDiffOp] | None = None


@dataclass
class DocxDiffResult:
    """Diff 结果。"""

    ops: list[DiffOp]
    summary: str


class DocxDiffer:
    """结构化 docx diff 引擎。"""

    # 段落级文本相似度阈值
    PARA_SIMILARITY_THRESHOLD: float = 0.6
    # Run 级文本相似度阈值
    RUN_SIMILARITY_THRESHOLD: float = 0.8

    def diff(self, old_ast: DocxAST, new_ast: DocxAST) -> DocxDiffResult:
        """对比两个 DocxAST，生成结构化差异。

        Args:
            old_ast: 旧文档 AST
            new_ast: 新文档 AST

        Returns:
            DocxDiffResult 包含 DiffOp 列表和可读摘要
        """
        alignments = self._align_paragraphs(old_ast.nodes, new_ast.nodes)
        ops = self._generate_diff_ops(alignments)
        summary = self._summarize(ops)
        return DocxDiffResult(ops=ops, summary=summary)

    # ------------------------------------------------------------------
    # Phase 1: 段落级 LCS 对齐
    # ------------------------------------------------------------------

    def _align_paragraphs(
        self,
        old_nodes: list[Node],
        new_nodes: list[Node],
    ) -> list[tuple[Node | None, Node | None]]:
        """基于文本相似度的 LCS 对齐。

        Returns:
            对齐结果列表：[(old_node_or_None, new_node_or_None), ...]
        """
        m, n = len(old_nodes), len(new_nodes)

        # LCS DP 表
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                sim = self._node_similarity(old_nodes[i - 1], new_nodes[j - 1])
                if sim >= self.PARA_SIMILARITY_THRESHOLD:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

        # 回溯生成对齐
        alignments: list[tuple[Node | None, Node | None]] = []
        i, j = m, n
        while i > 0 or j > 0:
            if i > 0 and j > 0:
                sim = self._node_similarity(old_nodes[i - 1], new_nodes[j - 1])
                if sim >= self.PARA_SIMILARITY_THRESHOLD and dp[i][j] == dp[i - 1][j - 1] + 1:
                    alignments.append((old_nodes[i - 1], new_nodes[j - 1]))
                    i -= 1
                    j -= 1
                    continue
            if i > 0 and dp[i][j] == dp[i - 1][j]:
                alignments.append((old_nodes[i - 1], None))
                i -= 1
            else:
                alignments.append((None, new_nodes[j - 1]))
                j -= 1

        alignments.reverse()
        return alignments

    @staticmethod
    def _node_similarity(a: Node, b: Node) -> float:
        """计算两个节点的文本相似度（0.0 ~ 1.0）。"""
        text_a = a.text if isinstance(a, Paragraph) else ""
        text_b = b.text if isinstance(b, Paragraph) else ""
        if not text_a and not text_b:
            return 1.0
        if not text_a or not text_b:
            return 0.0
        return SequenceMatcher(None, text_a, text_b).ratio()

    # ------------------------------------------------------------------
    # Phase 2: 生成 DiffOp
    # ------------------------------------------------------------------

    def _generate_diff_ops(
        self,
        alignments: list[tuple[Node | None, Node | None]],
    ) -> list[DiffOp]:
        """遍历对齐结果，生成 DiffOp 列表。"""
        ops: list[DiffOp] = []
        position = 0

        for old_node, new_node in alignments:
            if old_node is None and new_node is not None:
                # 插入
                ops.append(DiffOp(type=DiffType.INSERT, position=position, node=new_node))
                position += 1
            elif old_node is not None and new_node is None:
                # 删除
                ops.append(DiffOp(type=DiffType.DELETE, position=position))
                # 不递增 position
            elif old_node is not None and new_node is not None:
                # 对齐的节点对 — 做细化 diff
                if isinstance(old_node, Paragraph) and isinstance(new_node, Paragraph):
                    op = self._diff_paragraph_pair(old_node, new_node, position)
                    if op is not None:
                        ops.append(op)
                elif isinstance(old_node, Table) and isinstance(new_node, Table):
                    # 表格: 简化为文本替换
                    if old_node.text != new_node.text:
                        ops.append(
                            DiffOp(
                                type=DiffType.REPLACE,
                                position=position,
                                old_text=old_node.text[:100],
                                new_text=new_node.text[:100],
                            )
                        )
                position += 1

        return ops

    def _diff_paragraph_pair(
        self,
        old_para: Paragraph,
        new_para: Paragraph,
        position: int,
    ) -> DiffOp | None:
        """对比两个已对齐的段落，生成 DiffOp 或 None。"""
        # 先检查文本是否变化
        old_text = old_para.text
        new_text = new_para.text

        if old_text == new_text:
            # 文本没变，检查样式
            if old_para.style != new_para.style:
                return DiffOp(
                    type=DiffType.MODIFY_STYLE,
                    position=position,
                    old_style=old_para.style,
                    new_style=new_para.style,
                )
            return None

        # 文本变化了 — 做 Run 级 diff
        run_diffs = self._diff_runs(old_para, new_para)
        if run_diffs:
            return DiffOp(
                type=DiffType.MODIFY_RUNS,
                position=position,
                run_diffs=run_diffs,
            )

        # Run diff 没产生有意义的变更，退化为段落级替换
        return DiffOp(
            type=DiffType.REPLACE,
            position=position,
            old_text=old_text,
            new_text=new_text,
        )

    # ------------------------------------------------------------------
    # Run 级 diff
    # ------------------------------------------------------------------

    def _diff_runs(
        self,
        old_para: Paragraph,
        new_para: Paragraph,
    ) -> list[RunDiffOp]:
        """对比两个段落的 runs 列表，生成 Run 级变更。"""
        old_runs = old_para.runs
        new_runs = new_para.runs

        if not old_runs and not new_runs:
            return []
        if not old_runs:
            return [RunDiffOp(type="insert", position=i, run=r) for i, r in enumerate(new_runs)]
        if not new_runs:
            return [RunDiffOp(type="delete", position=i, old_run=r) for i, r in enumerate(old_runs)]

        # 使用 LCS 对齐 runs
        m, n = len(old_runs), len(new_runs)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if old_runs[i - 1].text == new_runs[j - 1].text:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

        # 回溯
        matched_old: set[int] = set()
        matched_new: set[int] = set()
        i, j = m, n
        while i > 0 and j > 0:
            if old_runs[i - 1].text == new_runs[j - 1].text and dp[i][j] == dp[i - 1][j - 1] + 1:
                matched_old.add(i - 1)
                matched_new.add(j - 1)
                i -= 1
                j -= 1
            elif dp[i - 1][j] >= dp[i][j - 1]:
                i -= 1
            else:
                j -= 1

        # 生成 RunDiffOp
        ops: list[RunDiffOp] = []
        old_idx = 0
        new_idx = 0

        for i in range(m + n):
            # 取下一个匹配的 pair
            next_old = next((k for k in sorted(matched_old) if k >= old_idx), None)
            next_new = next((k for k in sorted(matched_new) if k >= new_idx), None)

            if next_old is not None and next_new is not None and next_old == sorted(matched_old)[list(matched_old).index(next_old)] if next_old in matched_old else False:
                pass

            # 简化：按顺序处理
            if old_idx in matched_old:
                # 这个 old run 被匹配了
                matched_new_idx = self._find_matched_new(old_idx, matched_old, matched_new, old_runs, new_runs)
                if matched_new_idx is not None:
                    # 检查格式是否变化
                    if old_runs[old_idx].style != new_runs[matched_new_idx].style:
                        ops.append(
                            RunDiffOp(
                                type="modify",
                                position=matched_new_idx,
                                run=new_runs[matched_new_idx],
                                old_run=old_runs[old_idx],
                            )
                        )
                    old_idx += 1
                    # 跳过已匹配的 new runs
                    while new_idx <= matched_new_idx:
                        new_idx += 1
                else:
                    old_idx += 1
            elif new_idx in matched_new:
                # 这个 new run 被匹配了，但对应的 old 已经处理过
                new_idx += 1
            # 未匹配
            elif old_idx < m and (new_idx >= n or old_idx < next((k for k in sorted(matched_old) if k >= old_idx), m + 1)):
                ops.append(
                    RunDiffOp(
                        type="delete",
                        position=new_idx,
                        old_run=old_runs[old_idx],
                    )
                )
                old_idx += 1
            elif new_idx < n:
                ops.append(
                    RunDiffOp(
                        type="insert",
                        position=new_idx,
                        run=new_runs[new_idx],
                    )
                )
                new_idx += 1
            else:
                old_idx += 1

        return ops

    def _find_matched_new(
        self,
        old_idx: int,
        matched_old: set[int],
        matched_new: set[int],
        old_runs: list[Run],
        new_runs: list[Run],
    ) -> int | None:
        """找到与 old_runs[old_idx] 匹配的 new_runs 索引。"""
        if old_idx not in matched_old:
            return None
        old_text = old_runs[old_idx].text
        for ni in sorted(matched_new):
            if new_runs[ni].text == old_text:
                return ni
        return None

    # ------------------------------------------------------------------
    # 摘要生成
    # ------------------------------------------------------------------

    @staticmethod
    def _summarize(ops: list[DiffOp]) -> str:
        """生成人类可读的 diff 摘要。"""
        stats = {
            "insert": 0,
            "delete": 0,
            "replace": 0,
            "modify_style": 0,
            "modify_runs": 0,
        }
        details: list[str] = []

        for op in ops:
            stats[op.type.value] += 1
            match op.type:
                case DiffType.INSERT:
                    text_preview = ""
                    if op.node and isinstance(op.node, Paragraph):
                        text_preview = op.node.text[:50]
                    elif op.node and isinstance(op.node, Table):
                        text_preview = "(表格)"
                    details.append(f"  [+] 插入段落 {op.position}: {text_preview}...")
                case DiffType.DELETE:
                    details.append(f"  [-] 删除段落 {op.position}")
                case DiffType.REPLACE:
                    old_preview = (op.old_text or "")[:30]
                    new_preview = (op.new_text or "")[:30]
                    details.append(f'  [~] 替换段落 {op.position}: "{old_preview}" → "{new_preview}"')
                case DiffType.MODIFY_STYLE:
                    old_name = op.old_style.style_name if op.old_style else "?"
                    new_name = op.new_style.style_name if op.new_style else "?"
                    details.append(f"  [S] 修改样式 段落 {op.position}: {old_name} → {new_name}")
                case DiffType.MODIFY_RUNS:
                    count = len(op.run_diffs) if op.run_diffs else 0
                    details.append(f"  [R] 修改内容 段落 {op.position}: {count} 处变更")

        total_modified = stats["replace"] + stats["modify_style"] + stats["modify_runs"]
        summary = "文档对比结果：\n"
        summary += f"  插入 {stats['insert']} 段，删除 {stats['delete']} 段，修改 {total_modified} 段\n"
        if details:
            summary += "\n".join(details)
        return summary
