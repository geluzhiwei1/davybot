# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Text chunking strategies for document segmentation"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any

from dawei.knowledge.models import Document, DocumentChunk


class ChunkingStrategy(str, Enum):
    """Chunking strategy types"""

    FIXED_SIZE = "fixed_size"  # Fixed character count
    RECURSIVE = "recursive"  # Recursive character split
    SEMANTIC = "semantic"  # Semantic paragraph/sentence split
    MARKDOWN = "markdown"  # Markdown-specific (headers, code blocks)
    CODE = "code"  # Code-specific (functions, classes)


@dataclass
class ChunkingConfig:
    """Chunking configuration"""

    strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE
    chunk_size: int = 512
    chunk_overlap: int = 50
    separators: List[str] | None = None
    keep_separator: bool = False
    strip_whitespace: bool = True


class TextChunker:
    """Text chunker for splitting documents into smaller pieces"""

    def __init__(self, config: ChunkingConfig | None = None):
        """Initialize chunker

        Args:
            config: Chunking configuration
        """
        self.config = config or ChunkingConfig()

    async def chunk(self, document: Document) -> List[DocumentChunk]:
        """Chunk document into smaller pieces

        Args:
            document: Document to chunk

        Returns:
            List of document chunks
        """
        if not document.content:
            return []

        if self.config.strategy == ChunkingStrategy.FIXED_SIZE:
            return self._fixed_size_chunk(document)
        elif self.config.strategy == ChunkingStrategy.RECURSIVE:
            return self._recursive_chunk(document)
        elif self.config.strategy == ChunkingStrategy.SEMANTIC:
            return self._semantic_chunk(document)
        elif self.config.strategy == ChunkingStrategy.MARKDOWN:
            return self._markdown_chunk(document)
        elif self.config.strategy == ChunkingStrategy.CODE:
            return self._code_chunk(document)
        else:
            return self._recursive_chunk(document)

    def _fixed_size_chunk(self, document: Document) -> List[DocumentChunk]:
        """Fixed-size chunking by character count"""
        chunks = []
        content = document.content
        chunk_size = self.config.chunk_size
        overlap = self.config.chunk_overlap

        start = 0
        chunk_index = 0

        while start < len(content):
            end = start + chunk_size
            chunk_content = content[start:end]

            # Strip whitespace if configured
            if self.config.strip_whitespace:
                chunk_content = chunk_content.strip()

            if chunk_content:  # Skip empty chunks
                chunk = DocumentChunk(
                    id=f"{document.id}_chunk_{chunk_index}",
                    document_id=document.id,
                    chunk_index=chunk_index,
                    content=chunk_content,
                    metadata={
                        **document.metadata.model_dump(),
                        "chunk_start": start,
                        "chunk_end": end,
                    },
                )
                chunks.append(chunk)
                chunk_index += 1

            start = end - overlap

        return chunks

    def _recursive_chunk(self, document: Document) -> List[DocumentChunk]:
        """Recursive character splitting with multiple separators

        Tries different separators in order to create meaningful chunks.
        """
        # Default separators in order of preference
        separators = self.config.separators or [
            "\n\n",  # Paragraph breaks
            "\n",  # Line breaks
            ". ",  # Sentence endings
            "! ",
            "? ",
            "; ",
            ", ",
            " ",  # Words
            "",  # Characters
        ]

        chunks = []
        content = document.content
        chunk_size = self.config.chunk_size
        overlap = self.config.chunk_overlap

        def split_text(text: str, separator_idx: int) -> List[str]:
            """Recursively split text using separators"""
            if separator_idx >= len(separators):
                return [text]

            separator = separators[separator_idx]
            if separator:
                parts = text.split(separator)
            else:
                parts = list(text)

            # Merge parts that are too small
            merged_parts = []
            current = ""

            for part in parts:
                if separator:  # Add separator back if keeping it
                    test_text = current + part + (separator if self.config.keep_separator else "")
                else:
                    test_text = current + part

                if len(test_text) <= chunk_size:
                    current = test_text
                else:
                    if current:
                        merged_parts.append(current)
                    current = part

            if current:
                merged_parts.append(current)

            # Recursively split parts that are still too large
            final_parts = []
            for part in merged_parts:
                if len(part) <= chunk_size:
                    final_parts.append(part)
                else:
                    sub_parts = split_text(part, separator_idx + 1)
                    final_parts.extend(sub_parts)

            return final_parts

        # Split content
        split_chunks = split_text(content, 0)

        # Add overlap
        final_chunks = []
        for i, chunk_content in enumerate(split_chunks):
            if self.config.strip_whitespace:
                chunk_content = chunk_content.strip()

            if chunk_content:
                # Add overlap from previous chunk
                if i > 0 and overlap > 0:
                    prev_chunk = final_chunks[-1].content
                    overlap_text = prev_chunk[-overlap:] if len(prev_chunk) > overlap else prev_chunk
                    chunk_content = overlap_text + "\n\n" + chunk_content

                chunk = DocumentChunk(
                    id=f"{document.id}_chunk_{i}",
                    document_id=document.id,
                    chunk_index=i,
                    content=chunk_content,
                    metadata=document.metadata.model_dump(),
                )
                final_chunks.append(chunk)

        return final_chunks

    def _semantic_chunk(self, document: Document) -> List[DocumentChunk]:
        """Semantic chunking by sentences and paragraphs"""
        # Simplified implementation
        # In production, use spaCy or NLTK for better sentence detection
        import re

        # Split by sentences (simplified)
        sentences = re.split(r"(?<=[.!?])\s+", document.content)

        chunks = []
        current_chunk = ""
        chunk_index = 0

        for sentence in sentences:
            test_chunk = current_chunk + " " + sentence if current_chunk else sentence

            if len(test_chunk) <= self.config.chunk_size:
                current_chunk = test_chunk
            else:
                if current_chunk:
                    chunk = DocumentChunk(
                        id=f"{document.id}_chunk_{chunk_index}",
                        document_id=document.id,
                        chunk_index=chunk_index,
                        content=current_chunk.strip(),
                        metadata=document.metadata.model_dump(),
                    )
                    chunks.append(chunk)
                    chunk_index += 1

                # Start new chunk with overlap
                if self.config.chunk_overlap > 0 and chunks:
                    prev_content = chunks[-1].content
                    words = prev_content.split()
                    overlap_words = words[-self.config.chunk_overlap:] if len(words) > self.config.chunk_overlap else words
                    current_chunk = " ".join(overlap_words) + " " + sentence
                else:
                    current_chunk = sentence

        # Add last chunk
        if current_chunk.strip():
            chunk = DocumentChunk(
                id=f"{document.id}_chunk_{chunk_index}",
                document_id=document.id,
                chunk_index=chunk_index,
                content=current_chunk.strip(),
                metadata=document.metadata.model_dump(),
            )
            chunks.append(chunk)

        return chunks

    def _markdown_chunk(self, document: Document) -> List[DocumentChunk]:
        """Markdown-specific chunking

        Respects headers, code blocks, and other Markdown structures.
        """
        import re

        chunks = []
        chunk_index = 0

        # Split by headers
        sections = re.split(r"(^#{1,6}\s.+?$)", document.content, flags=re.MULTILINE)

        current_content = ""

        for i, section in enumerate(sections):
            if section.strip().startswith("#"):
                # This is a header
                if current_content:
                    chunk = DocumentChunk(
                        id=f"{document.id}_chunk_{chunk_index}",
                        document_id=document.id,
                        chunk_index=chunk_index,
                        content=current_content.strip(),
                        metadata={
                            **document.metadata.model_dump(),
                            "section_header": section.strip(),
                        },
                    )
                    chunks.append(chunk)
                    chunk_index += 1
                    current_content = section + "\n\n"
                else:
                    current_content = section + "\n\n"
            else:
                # Add to current section
                if len(current_content) + len(section) <= self.config.chunk_size:
                    current_content += section
                else:
                    # Section too large, need to split further
                    sub_chunks = self._recursive_chunk(
                        Document(
                            id=document.id,
                            metadata=document.metadata,
                            content=section,
                        )
                    )
                    chunks.extend(sub_chunks)
                    current_content = ""

        # Add final chunk
        if current_content.strip():
            chunk = DocumentChunk(
                id=f"{document.id}_chunk_{chunk_index}",
                document_id=document.id,
                chunk_index=chunk_index,
                content=current_content.strip(),
                metadata=document.metadata.model_dump(),
            )
            chunks.append(chunk)

        return chunks

    def _code_chunk(self, document: Document) -> List[DocumentChunk]:
        """Code-specific chunking

        Preserves functions, classes, and logical code blocks.
        """
        # Simplified implementation
        # In production, use tree-sitter for AST-based chunking
        import re

        # Split by function/class definitions (simplified)
        pattern = r"^(def\s+\w+|class\s+\w+|interface\s+\w+|type\s+\w+).*?$"

        lines = document.content.split("\n")
        chunks = []
        current_chunk = []
        chunk_index = 0

        for line in lines:
            current_chunk.append(line)

            # Check if this is a new definition
            if re.match(pattern, line) and current_chunk:
                chunk_content = "\n".join(current_chunk)

                if len(chunk_content) >= self.config.chunk_size * 0.8:
                    # Save current chunk
                    chunk = DocumentChunk(
                        id=f"{document.id}_chunk_{chunk_index}",
                        document_id=document.id,
                        chunk_index=chunk_index,
                        content=chunk_content,
                        metadata={
                            **document.metadata.model_dump(),
                            "code_language": self._detect_language(document.metadata.file_path),
                        },
                    )
                    chunks.append(chunk)
                    chunk_index += 1
                    current_chunk = [line]  # Start new chunk with this line

        # Add final chunk
        if current_chunk:
            chunk_content = "\n".join(current_chunk)
            chunk = DocumentChunk(
                id=f"{document.id}_chunk_{chunk_index}",
                document_id=document.id,
                chunk_index=chunk_index,
                content=chunk_content,
                metadata={
                    **document.metadata.model_dump(),
                    "code_language": self._detect_language(document.metadata.file_path),
                },
            )
            chunks.append(chunk)

        return chunks

    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension"""
        from pathlib import Path

        ext = Path(file_path).suffix.lower()

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
