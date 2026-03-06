# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""PDF document parser using PyMuPDF (fitz)"""

import hashlib
import logging
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from dawei.knowledge.models import Document, DocumentMetadata, DocumentType
from dawei.knowledge.parsers.base import BaseParser

logger = logging.getLogger(__name__)


class PDFParser(BaseParser):
    """PDF document parser"""

    @staticmethod
    def _parse_pdf_date(pdf_date_string: str) -> datetime | None:
        """Parse PDF date string to datetime object

        PDF date format: D:YYYYMMDDHHmmSSOHH'mm'
        Where:
            D: - Literal prefix
            YYYY - Year
            MM - Month (01-12)
            DD - Day (01-31)
            HH - Hour (00-23)
            mm - Minute (00-59)
            SS - Second (00-59)
            O - Relationship to UTC (+, -, or Z)
            HH' - Hour offset for timezone
            mm' - Minute offset for timezone

        Example: D:20250128151046+05'30' means 2025-01-28 15:10:46 UTC+05:30

        Args:
            pdf_date_string: PDF date string (e.g., "D:20250128151046+05'30'")

        Returns:
            datetime object or None if parsing fails
        """
        try:
            # Remove the 'D:' prefix if present
            if pdf_date_string.startswith("D:"):
                pdf_date_string = pdf_date_string[2:]

            # PDF date string format: YYYYMMDDHHmmSS+HH'mm' or YYYYMMDDHHmmSS-HH'mm'
            # Remove quotes from timezone part
            pdf_date_string = pdf_date_string.replace("'", "")

            # Parse the basic date/time part (first 14 characters)
            if len(pdf_date_string) < 14:
                logger.warning(f"PDF date string too short: {pdf_date_string}")
                return None

            date_part = pdf_date_string[:14]  # YYYYMMDDHHmmSS

            # Parse timezone offset if present
            timezone_offset = None
            if len(pdf_date_string) > 14:
                tz_part = pdf_date_string[14:]  # +HHmm or -HHmm
                if tz_part.startswith(("+", "-")):
                    sign = 1 if tz_part.startswith("+") else -1
                    tz_part = tz_part[1:]  # Remove sign

                    if len(tz_part) >= 4:  # HHmm format
                        try:
                            tz_hours = int(tz_part[:2])
                            tz_minutes = int(tz_part[2:4])
                            timezone_offset = timedelta(hours=sign * tz_hours, minutes=sign * tz_minutes)
                        except ValueError:
                            logger.warning(f"Invalid timezone offset in PDF date: {pdf_date_string}")
                            timezone_offset = None

            # Parse the datetime part (create naive datetime)
            dt = datetime.strptime(date_part, "%Y%m%d%H%M%S")

            # Apply timezone offset if present
            if timezone_offset:
                tz = timezone(timezone_offset)
                dt = dt.replace(tzinfo=tz)
            else:
                # Assume UTC if no timezone specified
                dt = dt.replace(tzinfo=UTC)

            return dt

        except Exception as e:
            logger.warning(f"Failed to parse PDF date string '{pdf_date_string}': {e}")
            return None

    async def parse(self, file_path: str | Path) -> Document:
        """Parse PDF document"""
        file_path = Path(file_path)

        # Calculate SHA256
        sha256_hash = self._calculate_sha256(file_path)

        # Extract PDF content
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("PyMuPDF (fitz) is required for PDF parsing. Install with: pip install pymupdf")

        doc = fitz.open(file_path)
        content_parts = []

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text("text")
            content_parts.append(text)

        full_content = "\n\n".join(content_parts)

        # Create metadata
        metadata = DocumentMetadata(
            file_path=str(file_path),
            file_name=file_path.name,
            file_size=file_path.stat().st_size,
            file_type=DocumentType.PDF,
            sha256=sha256_hash,
            page_count=len(doc),
        )

        # Extract PDF metadata if available
        if doc.metadata:
            if doc.metadata.get("title"):
                metadata.title = doc.metadata["title"]
            if doc.metadata.get("author"):
                metadata.author = doc.metadata["author"]
            if doc.metadata.get("creationDate"):
                parsed_date = self._parse_pdf_date(doc.metadata["creationDate"])
                if parsed_date:
                    metadata.created_at = parsed_date
                else:
                    logger.debug(f"Could not parse PDF creation date: {doc.metadata['creationDate']}")

        doc.close()

        return Document(id=sha256_hash, metadata=metadata, content=full_content)

    def supports_file_type(self, file_path: str | Path) -> bool:
        """Check if file is a PDF"""
        return Path(file_path).suffix.lower() == ".pdf"

    def _calculate_sha256(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file"""
        sha256 = hashlib.sha256()
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
