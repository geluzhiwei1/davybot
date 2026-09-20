# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""PDF parser via PyMuPDF (fitz).

Tracks real page boundaries as page_offsets ({page_num: char_offset}) so the
chunker can resolve each chunk back to its source page — used by entity
provenance (getEntitySources). Scanned/image-only PDFs yield no text without
OCR (out of scope); the parser logs a warning and returns empty content.
"""

import logging
from pathlib import Path

from dawei.knowledge.models import Document, DocumentMetadata, DocumentType
from dawei.knowledge.parsers.base import BaseParser

logger = logging.getLogger(__name__)


class PdfParser(BaseParser):
    """Parser for .pdf files."""

    async def parse(self, file_path: str | Path) -> Document:
        file_path = Path(file_path)
        file_size = file_path.stat().st_size
        sha256_hash = self._calculate_sha256(file_path)

        # Lazy import — PyMuPDF is heavy and only needed at parse time.
        import fitz  # PyMuPDF

        parts: list[str] = []
        page_offsets: dict[int, int] = {}
        cursor = 0
        page_count = 0
        title = None
        author = None

        doc = fitz.open(str(file_path))
        try:
            # Encrypted PDFs: try empty password; if it fails, text extraction
            # returns nothing — log and proceed (content stays empty).
            if doc.is_encrypted:
                if not doc.authenticate(""):
                    logger.warning(f"PDF is encrypted, text extraction limited: {file_path.name}")

            for i, page in enumerate(doc, start=1):
                page_offsets[i] = cursor
                text = page.get_text() or ""
                parts.append(text)
                # +2 accounts for the "\n\n" join separator between pages.
                cursor += len(text) + 2
            page_count = len(doc)

            try:
                md = doc.metadata or {}
                title = md.get("title") or None
                author = md.get("author") or None
            except Exception:
                pass
        finally:
            doc.close()

        content = "\n\n".join(parts)
        if not content.strip():
            logger.warning(
                f"PDF yielded no extractable text (possibly scanned/image-only): {file_path.name}"
            )

        metadata = DocumentMetadata(
            file_path=str(file_path),
            file_name=file_path.name,
            file_size=file_size,
            file_type=DocumentType.PDF,
            sha256=sha256_hash,
            title=title,
            author=author,
            page_count=page_count or None,
            page_offsets=page_offsets,
        )
        return Document(id=sha256_hash, metadata=metadata, content=content)

    def supports_file_type(self, file_path: str | Path) -> bool:
        return Path(file_path).suffix.lower() == ".pdf"
