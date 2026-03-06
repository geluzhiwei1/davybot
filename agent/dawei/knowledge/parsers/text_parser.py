# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Text document parser"""

import hashlib
from pathlib import Path

from dawei.knowledge.models import Document, DocumentMetadata, DocumentType
from dawei.knowledge.parsers.base import BaseParser


class TextParser(BaseParser):
    """Text document parser"""

    async def parse(self, file_path: str | Path) -> Document:
        """Parse text document"""
        file_path = Path(file_path)

        # Calculate SHA256
        sha256_hash = self._calculate_sha256(file_path)

        # Read content
        content = file_path.read_text(encoding="utf-8")

        # Create metadata
        metadata = DocumentMetadata(
            file_path=str(file_path),
            file_name=file_path.name,
            file_size=file_path.stat().st_size,
            file_type=DocumentType.TEXT,
            sha256=sha256_hash,
        )

        return Document(id=sha256_hash, metadata=metadata, content=content)

    def supports_file_type(self, file_path: str | Path) -> bool:
        """Check if file is a text file"""
        return Path(file_path).suffix.lower() in [".txt", ".md", ".text"]

    def _calculate_sha256(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file"""
        sha256 = hashlib.sha256()
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
