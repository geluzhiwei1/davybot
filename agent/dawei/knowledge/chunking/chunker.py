# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Text chunking strategies for document segmentation

Provides chunking for vector store and full-text search.
Knowledge graph extraction should use the FULL document, not chunks.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional

from dawei.knowledge.models import Document, DocumentChunk

logger = logging.getLogger(__name__)


class ChunkingStrategy(str, Enum):
    """Available chunking strategies"""

    FIXED_SIZE = "fixed_size"
    RECURSIVE = "recursive"
    SEMANTIC = "semantic"
    MARKDOWN = "markdown"
    CODE = "code"


@dataclass
class ChunkingConfig:
    """Chunking configuration"""

    strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE
    chunk_size: int = 1000
    chunk_overlap: int = 200
    separators: Optional[List[str]] = None
    keep_separator: bool = True
    strip_whitespace: bool = True


class TextChunker:
    """Text chunker with multiple strategies

    Splits documents into chunks suitable for vector store and full-text search.
    For knowledge graph extraction, use the full document content instead of chunks.
    """

    def __init__(self, config: ChunkingConfig | None = None):
        self.config = config or ChunkingConfig()

    async def chunk(self, document: Document) -> List[DocumentChunk]:
        """Chunk a document into smaller pieces

        Args:
            document: Document to chunk

        Returns:
            List of DocumentChunk objects
        """
        if not document.content:
            return []

        strategy = self.config.strategy
        if strategy == ChunkingStrategy.MARKDOWN:
            chunks = self._markdown_chunk(document)
        elif strategy == ChunkingStrategy.CODE:
            chunks = self._code_chunk(document)
        else:
            # RECURSIVE, FIXED_SIZE, SEMANTIC all use recursive splitting
            chunks = self._recursive_chunk(document)

        # Annotate page numbers from document metadata
        if document.metadata.page_offsets:
            self._annotate_page_numbers(chunks, document.content, document.metadata.page_offsets)

        logger.info(f"Chunked document into {len(chunks)} chunks (strategy={strategy.value})")
        return chunks

    # ------------------------------------------------------------------
    # Recursive splitting (default)
    # ------------------------------------------------------------------

    def _recursive_chunk(self, document: Document) -> List[DocumentChunk]:
        """Recursive text splitting with overlap — default strategy"""
        text = document.content

        # Separators in order of preference (coarse → fine)
        separators = self.config.separators or [
            "\n\n",  # paragraph
            "\n",  # line
            "。",  # Chinese period
            ". ",  # English period
            "；",  # Chinese semicolon
            "; ",  # English semicolon
            "，",  # Chinese comma
            ", ",  # English comma
            " ",  # space
            "",  # char-level fallback
        ]

        raw_chunks = self._split_text_recursive(text, separators, self.config.chunk_size)

        # Build DocumentChunk objects with overlap
        result: List[DocumentChunk] = []
        for i, content in enumerate(raw_chunks):
            if self.config.strip_whitespace:
                content = content.strip()
            if not content:
                continue

            result.append(
                DocumentChunk(
                    id=f"{document.id}_chunk_{i}",
                    document_id=document.id,
                    chunk_index=i,
                    content=content,
                    metadata=self._base_metadata(document),
                )
            )
        return result

    def _split_text_recursive(
        self,
        text: str,
        separators: List[str],
        chunk_size: int,
    ) -> List[str]:
        """Split text by trying separators from coarse to fine"""
        if len(text) <= chunk_size:
            return [text]

        separator = separators[0] if separators else ""

        if not separator:
            # Character-level split as last resort
            return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

        # Split by current separator
        parts = text.split(separator)

        # Merge parts into chunks ≤ chunk_size
        chunks: List[str] = []
        current = ""

        for part in parts:
            candidate = current + separator + part if current else part

            if len(candidate) <= chunk_size:
                current = candidate
            else:
                # Flush current chunk
                if current:
                    chunks.append(current)

                # If part itself is too large, recurse with next separator
                if len(part) > chunk_size and len(separators) > 1:
                    chunks.extend(self._split_text_recursive(part, separators[1:], chunk_size))
                    current = ""
                else:
                    current = part

        if current:
            chunks.append(current)

        return chunks

    # ------------------------------------------------------------------
    # Markdown chunking — hierarchy-aware
    # ------------------------------------------------------------------

    def _markdown_chunk(self, document: Document) -> List[DocumentChunk]:
        """Markdown chunking — respects header hierarchy

        Improvements over flat splitting:
        1. Header chain tracking — each chunk knows its full breadcrumb path
        2. Sibling merging — small sections under the same parent are merged
        3. Header prefix — parent headers prepended for LLM context
        """
        content = document.content
        chunk_size = self.config.chunk_size

        # Step 1: parse into structured sections
        sections = self._parse_md_sections(content)

        # No headers found — fallback to recursive
        if not sections or all(s["level"] == 0 for s in sections):
            return self._recursive_chunk(document)

        # Step 2: merge small siblings under the same parent
        merged = self._merge_md_siblings(sections, chunk_size)

        # Step 3: build chunks with header context
        chunks: List[DocumentChunk] = []
        for sec in merged:
            # Prepend header chain for context
            header_prefix = ""
            if sec["headers"]:
                header_prefix = "\n".join(sec["headers"]) + "\n\n"
            text = (header_prefix + sec["content"]).strip()

            if not text:
                continue

            extra = {"header_chain": sec["headers"], "header_level": sec["level"]}

            if len(text) <= chunk_size:
                chunks.append(
                    self._make_chunk(document, len(chunks), text, extra=extra)
                )
            else:
                # Oversized section — recursive split, keeping header context
                for sub in self._split_to_size(text):
                    chunks.append(
                        self._make_chunk(document, len(chunks), sub, extra=extra)
                    )

        return chunks

    # ---- Markdown helpers ----

    def _parse_md_sections(self, content: str) -> List[Dict[str, Any]]:
        """Parse markdown into sections with header-chain tracking.

        Returns list of dicts::

            {
                "headers": ["# Title", "## Sub"],   # breadcrumb path
                "level":    2,                       # heading level (0 = pre-header)
                "content":  "...",                   # body text (excluding heading)
            }
        """
        sections: List[Dict[str, Any]] = []
        header_stack: List[tuple] = []  # [(level, line), ...]
        lines_buffer: List[str] = []

        def _flush() -> None:
            body = "\n".join(lines_buffer).strip()
            chain = [line for _, line in header_stack]
            level = header_stack[-1][0] if header_stack else 0
            sections.append({"headers": chain, "level": level, "content": body})
            lines_buffer.clear()

        for line in content.split("\n"):
            m = re.match(r"^(#{1,6})\s+.+$", line)
            if m:
                _flush()
                level = len(m.group(1))
                # Pop same-level or deeper headers from the stack
                while header_stack and header_stack[-1][0] >= level:
                    header_stack.pop()
                header_stack.append((level, line))
            else:
                lines_buffer.append(line)

        _flush()

        # Keep only sections that have actual body content
        return [s for s in sections if s["content"]]

    def _merge_md_siblings(
        self, sections: List[Dict[str, Any]], chunk_size: int
    ) -> List[Dict[str, Any]]:
        """Merge adjacent small sections sharing the same parent header chain."""
        if not sections:
            return sections

        result: List[Dict[str, Any]] = []
        i = 0

        while i < len(sections):
            cur: Dict[str, Any] = {**sections[i]}  # shallow copy

            parent_chain = cur["headers"][:-1] if cur["headers"] else []
            header_prefix = (
                "\n".join(cur["headers"]) + "\n\n" if cur["headers"] else ""
            )

            # Greedily merge subsequent siblings that fit
            j = i + 1
            while j < len(sections):
                nxt = sections[j]
                nxt_parent = nxt["headers"][:-1] if nxt["headers"] else []
                if nxt_parent != parent_chain:
                    break

                # Build the addition (include the sibling's own heading)
                addition = "\n\n"
                if nxt["headers"]:
                    addition += nxt["headers"][-1] + "\n\n"
                addition += nxt["content"]

                if len(header_prefix + cur["content"] + addition) <= chunk_size:
                    cur["content"] += addition
                    j += 1
                else:
                    break

            result.append(cur)
            i = j

        return result

    # ------------------------------------------------------------------
    # Code chunking
    # ------------------------------------------------------------------

    def _code_chunk(self, document: Document) -> List[DocumentChunk]:
        """Code chunking — tries to preserve function/class boundaries"""
        lines = document.content.split("\n")
        pattern = r"^\s*(def\s+\w+|class\s+\w+|function\s+\w+|interface\s+\w+|type\s+\w+|pub\s+fn\s+\w+)"

        chunks: List[DocumentChunk] = []
        current_lines: List[str] = []
        chunk_index = 0

        for line in lines:
            if re.match(pattern, line) and current_lines:
                content = "\n".join(current_lines)
                if len(content) >= self.config.chunk_size * 0.8:
                    chunks.append(
                        self._make_chunk(
                            document,
                            chunk_index,
                            content,
                            extra={"code_language": self._detect_language(document.metadata.file_path)},
                        )
                    )
                    chunk_index += 1
                    current_lines = [line]
                else:
                    current_lines.append(line)
            else:
                current_lines.append(line)

        if current_lines:
            content = "\n".join(current_lines)
            chunks.append(
                self._make_chunk(
                    document,
                    chunk_index,
                    content,
                    extra={"code_language": self._detect_language(document.metadata.file_path)},
                )
            )

        return chunks

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _split_to_size(self, text: str) -> List[str]:
        """Split text to fit within chunk_size"""
        if len(text) <= self.config.chunk_size:
            return [text]
        return self._split_text_recursive(
            text,
            ["\n\n", "\n", "。", ". ", " ", ""],
            self.config.chunk_size,
        )

    def _make_chunk(
        self,
        document: Document,
        index: int,
        content: str,
        extra: Dict[str, Any] | None = None,
    ) -> DocumentChunk:
        """Create a DocumentChunk"""
        meta = self._base_metadata(document)
        if extra:
            meta.update(extra)
        return DocumentChunk(
            id=f"{document.id}_chunk_{index}",
            document_id=document.id,
            chunk_index=index,
            content=content.strip() if self.config.strip_whitespace else content,
            metadata=meta,
        )

    def _base_metadata(self, document: Document) -> Dict[str, Any]:
        """Extract base metadata dict for a chunk"""
        return {
            "file_name": document.metadata.file_name,
            "file_path": document.metadata.file_path,
            "document_id": document.id,
        }

    def _annotate_page_numbers(
        self,
        chunks: List[DocumentChunk],
        full_text: str,
        page_offsets: Dict[int, int],
    ) -> None:
        """Best-effort page number annotation for chunks"""
        if not page_offsets or not full_text:
            return

        # Build sorted list: [(char_offset, page_num), ...]
        sorted_pages = sorted(page_offsets.items(), key=lambda x: x[1])

        # Track cumulative position in the original text
        search_start = 0
        for chunk in chunks:
            # Find chunk content in original text
            pos = full_text.find(chunk.content[:80], search_start)
            if pos == -1:
                pos = search_start  # fallback

            # Determine page: find the last page whose offset <= pos
            page_num = 1
            for pn, offset in sorted_pages:
                if offset <= pos:
                    page_num = pn
                else:
                    break

            chunk.metadata["page_number"] = page_num
            search_start = pos + len(chunk.content)

    @staticmethod
    def _detect_language(file_path: str) -> str:
        """Detect programming language from file extension"""
        ext = Path(file_path).suffix.lower() if file_path else ""
        language_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".php": "php",
            ".cs": "csharp",
        }
        return language_map.get(ext, "unknown")
