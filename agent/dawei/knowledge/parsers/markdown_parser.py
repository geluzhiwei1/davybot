# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Markdown document parser"""

import hashlib
from pathlib import Path

from dawei.knowledge.models import Document, DocumentMetadata, DocumentType
from dawei.knowledge.parsers.base import BaseParser


class MarkdownParser(BaseParser):
    """Markdown document parser"""

    async def parse(self, file_path: str | Path) -> Document:
        """Parse markdown document"""
        file_path = Path(file_path)

        # Calculate SHA256
        sha256_hash = self._calculate_sha256(file_path)

        # Read content
        content = file_path.read_text(encoding="utf-8")

        # Extract metadata from frontmatter if present
        import re
        title = None

        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
        if frontmatter_match:
            frontmatter = frontmatter_match.group(1)
            # Extract title from frontmatter
            title_match = re.search(r'^title:\s*(.+)$', frontmatter, re.MULTILINE)
            if title_match:
                title = title_match.group(1).strip().strip('"').strip("'")

        # Create metadata
        metadata = DocumentMetadata(
            file_path=str(file_path),
            file_name=file_path.name,
            file_size=file_path.stat().st_size,
            file_type=DocumentType.MARKDOWN,
            sha256=sha256_hash,
            title=title,
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
