# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""ToolIndex — 工具语义索引。

对所有注册工具建立轻量语义索引，支持自然语言检索。
索引来源：tool.name + tool.description + args_schema 的字段名和描述。
无需 embedding——用关键词匹配 + BM25 简化版，因为工具描述是结构化短文本。
"""

import logging
import math
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 简单中英文停用词
_STOPWORDS = frozenset({
    # English
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "can", "shall", "to", "of", "in",
    "for", "on", "with", "as", "by", "at", "from", "up", "about", "into",
    "through", "during", "before", "after", "above", "below", "and", "or",
    "not", "no", "but", "if", "then", "else", "when", "where", "why",
    "how", "all", "each", "every", "both", "few", "more", "most", "other",
    "some", "such", "only", "own", "same", "so", "than", "too", "very",
    # Chinese
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
    "一", "上", "也", "很", "到", "说", "要", "去", "会", "着", "没",
    "看", "好", "自", "己", "这",
})


@dataclass
class ToolDoc:
    """工具文档条目。"""

    name: str
    description: str  # 完整描述（用于检索）
    brief_desc: str  # 一句话摘要（≤60 字，用于展示）
    keywords: set[str] = field(default_factory=set)  # 提取的关键词
    param_summary: str = ""  # 参数概要
    group: str = ""  # 所属 TOOL_GROUPS key

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.brief_desc,
            "keywords": sorted(self.keywords),
            "param_summary": self.param_summary,
            "group": self.group,
        }


def _tokenize(text: str) -> list[str]:
    """简单分词：英文按空格/标点，中文按字符。"""
    # 英文单词
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text.lower())
    # 中文字符（2-gram）
    chinese_chars = re.findall(r"[\u4e00-\u9fff]+", text)
    for seg in chinese_chars:
        if len(seg) >= 2:
            for i in range(len(seg) - 1):
                tokens.append(seg[i : i + 2])
        else:
            tokens.append(seg)
    # 过滤停用词
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


class ToolIndex:
    """对所有注册工具建立轻量语义索引，支持自然语言检索。"""

    def __init__(self):
        self._docs: dict[str, ToolDoc] = {}  # tool_name → ToolDoc
        # BM25 索引
        self._doc_tokens: dict[str, list[str]] = {}  # tool_name → token list
        self._avg_doc_len: float = 0.0
        self._df: dict[str, int] = {}  # token → document frequency

    def register(
        self,
        name: str,
        description: str = "",
        brief_desc: str = "",
        keywords: set[str] | None = None,
        param_summary: str = "",
        group: str = "",
    ) -> None:
        """注册工具到索引。

        Args:
            name: 工具名称
            description: 完整描述
            brief_desc: 一句话摘要（≤60字）。留空则从 description 截取。
            keywords: 关键词集合
            param_summary: 参数概要
            group: 所属分组
        """
        if not brief_desc:
            brief_desc = self._make_brief(description)

        doc = ToolDoc(
            name=name,
            description=description,
            brief_desc=brief_desc,
            keywords=keywords or set(),
            param_summary=param_summary,
            group=group,
        )
        self._docs[name] = doc

        # 构建 BM25 索引
        index_text = f"{name} {description} {' '.join(keywords or [])} {param_summary} {group}"
        tokens = _tokenize(index_text)
        self._doc_tokens[name] = tokens

        # 更新 document frequency
        unique_tokens = set(tokens)
        for t in unique_tokens:
            self._df[t] = self._df.get(t, 0) + 1

        # 更新平均文档长度
        total_docs = len(self._doc_tokens)
        total_len = sum(len(toks) for toks in self._doc_tokens.values())
        self._avg_doc_len = total_len / total_docs if total_docs > 0 else 0.0

        logger.debug(f"ToolIndex registered: {name} ({len(tokens)} tokens)")

    def register_from_tool(self, tool, group: str = "") -> None:
        """从 CustomBaseTool 实例注册。

        Args:
            tool: CustomBaseTool 实例（有 .name, .description, .args_schema）
            group: 所属分组
        """
        name = getattr(tool, "name", "")
        description = getattr(tool, "description", "")
        keywords = self._extract_keywords(tool)
        param_summary = self._summarize_params(tool)

        self.register(
            name=name,
            description=description,
            keywords=keywords,
            param_summary=param_summary,
            group=group,
        )

    def search(self, query: str, top_k: int = 5) -> list[ToolDoc]:
        """BM25 + 关键词匹配，返回 top_k 最相关工具。

        Args:
            query: 搜索关键词（中英文）
            top_k: 返回数量

        Returns:
            匹配的工具文档列表（按相关度排序）
        """
        if not self._docs:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return list(self._docs.values())[:top_k]

        scored: list[tuple[float, str]] = []
        n_docs = len(self._doc_tokens)

        for name, doc_tokens in self._doc_tokens.items():
            score = self._bm25_score(query_tokens, doc_tokens, n_docs)
            # 额外：名称精确包含加分
            query_lower = query.lower().strip()
            if query_lower and query_lower in name.lower():
                score += 10.0
            # 关键词双向匹配加分
            doc = self._docs[name]
            for kw in doc.keywords:
                kw_lower = kw.lower()
                if query_lower in kw_lower or kw_lower in query_lower:
                    score += 3.0

            if score > 0:
                scored.append((score, name))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._docs[name] for _, name in scored[:top_k]]

    def get_doc(self, name: str) -> ToolDoc | None:
        """获取工具文档。"""
        return self._docs.get(name)

    def list_all(self) -> list[ToolDoc]:
        """返回所有已注册工具。"""
        return list(self._docs.values())

    def _bm25_score(
        self,
        query_tokens: list[str],
        doc_tokens: list[str],
        n_docs: int,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> float:
        """简化版 BM25 评分。"""
        if not doc_tokens:
            return 0.0

        doc_len = len(doc_tokens)
        doc_freq: dict[str, int] = {}
        for t in doc_tokens:
            doc_freq[t] = doc_freq.get(t, 0) + 1

        score = 0.0
        for qt in query_tokens:
            if qt not in doc_freq:
                continue
            tf = doc_freq[qt]
            df = self._df.get(qt, 0)
            if df == 0:
                continue
            idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
            norm_tf = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / max(self._avg_doc_len, 1)))
            score += idf * norm_tf

        return score

    @staticmethod
    def _make_brief(desc: str, max_len: int = 60) -> str:
        """从完整描述生成一句话摘要。"""
        if not desc:
            return ""
        first = desc.split("。", 1)[0].split(". ", 1)[0].split("\n", 1)[0]
        return first[:max_len]

    @staticmethod
    def _extract_keywords(tool) -> set[str]:
        """从 description + 参数描述提取关键词（去停用词）。"""
        text_parts = [getattr(tool, "description", "")]

        args_schema = getattr(tool, "args_schema", None)
        if args_schema:
            try:
                if hasattr(args_schema, "model_fields"):
                    for _field_name, field_info in args_schema.model_fields.items():
                        text_parts.append(_field_name)
                        desc = getattr(field_info, "description", None) or getattr(field_info, "alias", None)
                        if desc:
                            text_parts.append(str(desc))
                elif hasattr(args_schema, "__fields__"):
                    for _fname, finfo in args_schema.__fields__.items():
                        text_parts.append(_fname)
            except Exception:
                pass

        full_text = " ".join(text_parts)
        tokens = _tokenize(full_text)
        return set(tokens)

    @staticmethod
    def _summarize_params(tool) -> str:
        """生成参数一句话摘要：'(name: str, limit: int)'。"""
        args_schema = getattr(tool, "args_schema", None)
        if not args_schema:
            return ""

        try:
            if hasattr(args_schema, "model_fields"):
                fields = args_schema.model_fields
            elif hasattr(args_schema, "__fields__"):
                fields = args_schema.__fields__
            else:
                return ""

            parts = []
            for fname, finfo in fields.items():
                annotation = getattr(finfo, "annotation", str)
                type_str = getattr(annotation, "__name__", str(annotation))
                parts.append(f"{fname}: {type_str}")

            return f"({', '.join(parts[:5])})" if parts else ""
        except Exception:
            return ""
