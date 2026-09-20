# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Plain text parser — encoding-aware (utf-8 → gbk → latin-1 fallback)."""

import logging
from pathlib import Path

from dawei.knowledge.models import Document, DocumentMetadata, DocumentType
from dawei.knowledge.parsers.base import BaseParser

logger = logging.getLogger(__name__)

# Encodings tried in order; utf-8-sig strips a leading BOM if present.
_TXT_ENCODINGS = ("utf-8", "utf-8-sig", "gbk", "latin-1")


class TxtParser(BaseParser):
    """Parser for .txt / .text files."""

    async def parse(self, file_path: str | Path) -> Document:
        file_path = Path(file_path)
        file_size = file_path.stat().st_size
        sha256_hash = self._calculate_sha256(file_path)

        content: str | None = None
        for enc in _TXT_ENCODINGS:
            try:
                content = file_path.read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        if content is None:
            # Last resort: never raise on encoding — replace undecodable bytes.
            content = file_path.read_bytes().decode("utf-8", errors="replace")

        metadata = DocumentMetadata(
            file_path=str(file_path),
            file_name=file_path.name,
            file_size=file_size,
            file_type=DocumentType.TXT,
            sha256=sha256_hash,
        )
        return Document(id=sha256_hash, metadata=metadata, content=content)

    def supports_file_type(self, file_path: str | Path) -> bool:
        return Path(file_path).suffix.lower() in {".txt", ".text"}
