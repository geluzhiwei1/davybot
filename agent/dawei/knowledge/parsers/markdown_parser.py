# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Markdown document parser

Supports:
- YAML frontmatter metadata extraction
- Page marker parsing: ``<--- Page N --->``
"""

import hashlib
import re
from pathlib import Path
from typing import Any

from dawei.knowledge.models import Document, DocumentMetadata, DocumentType
from dawei.knowledge.parsers.base import BaseParser

# Regex patterns
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_PAGE_MARKER_RE = re.compile(r"^<---\s*Page\s+(\d+)\s*--->\s*$", re.MULTILINE)

def _parse_frontmatter_yaml(text: str) -> dict[str, Any]:
    """Minimal YAML frontmatter parser (handles scalars and simple lists).

    Not a full YAML parser — just enough for our markdown metadata format.
    """
    result: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[str] | None = None

    for line in text.split("\n"):
        # Key-value pair
        m = re.match(r"^(\w[\w-]*):\s*(.*?)\s*$", line)
        if m:
            # Flush previous list
            if current_key and current_list is not None:
                result[current_key] = current_list
                current_list = None

            key, val = m.group(1), m.group(2)
            if val == "":
                # Could be start of a list block
                current_key = key
                current_list = []
            else:
                result[key] = val.strip("\"'")
                current_key = None
                current_list = None
            continue

        # List item (indented dash)
        if current_list is not None and current_key:
            m_list = re.match(r"^\s+-\s+(.+)$", line)
            if m_list:
                current_list.append(m_list.group(1).strip())
                continue

    # Flush last list
    if current_key and current_list is not None:
        result[current_key] = current_list

    return result


class MarkdownParser(BaseParser):
    """Markdown document parser"""

    async def parse(self, file_path: str | Path) -> Document:
        """Parse markdown document"""
        file_path = Path(file_path)

        # Calculate SHA256
        sha256_hash = self._calculate_sha256(file_path)

        # Read content
        content = file_path.read_text(encoding="utf-8")

        # --- 1. Parse frontmatter ---
        fm: dict[str, Any] = {}
        body = content
        fm_match = _FRONTMATTER_RE.match(content)
        if fm_match:
            fm = _parse_frontmatter_yaml(fm_match.group(1))
            body = fm_match.group(2)

        # --- 2. Parse page markers (<--- Page N --->) ---
        page_offsets: dict[int, int] = {}
        for pm in _PAGE_MARKER_RE.finditer(body):
            page_num = int(pm.group(1))
            page_offsets[page_num] = pm.start()
        page_count = max(page_offsets.keys()) if page_offsets else None

        # --- 3. Collect keywords as tags ---
        keywords = fm.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        tags: list[str] = keywords if isinstance(keywords, list) else []

        # --- 4. Build extra metadata dict ---
        # Known frontmatter keys that map to DocumentMetadata fields directly
        _KNOWN_KEYS = {
            "title", "title-zh", "file-name", "file-path", "file-type",
            "file-size", "language", "keywords", "year", "description",
            "publisher", "author",
        }
        extra: dict[str, Any] = {}
        for k, v in fm.items():
            if k not in _KNOWN_KEYS:
                extra[k] = v

        # --- 5. Create metadata ---
        metadata = DocumentMetadata(
            file_path=fm.get("file-path", str(file_path)),
            file_name=fm.get("file-name", file_path.name),
            file_size=file_path.stat().st_size,
            file_type=DocumentType.MARKDOWN,
            sha256=sha256_hash,
            title=fm.get("title"),
            author=fm.get("author") or fm.get("publisher"),
            language=fm.get("language"),
            tags=tags,
            page_count=page_count,
            page_offsets=page_offsets,
            metadata=extra,
        )

        return Document(id=sha256_hash, metadata=metadata, content=content)

    def supports_file_type(self, file_path: str | Path) -> bool:
        """Check if file is markdown"""
        return Path(file_path).suffix.lower() in [".md", ".markdown"]

    def _calculate_sha256(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file"""
        sha256 = hashlib.sha256()
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
