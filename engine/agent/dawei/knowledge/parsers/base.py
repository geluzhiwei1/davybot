# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Base parser interface"""

import hashlib
from abc import ABC, abstractmethod
from pathlib import Path

from dawei.knowledge.models import Document


class BaseParser(ABC):
    """Abstract base class for document parsers"""

    @abstractmethod
    async def parse(self, file_path: str | Path) -> Document:
        """Parse document and extract content

        Args:
            file_path: Path to document file

        Returns:
            Parsed document with metadata
        """
        pass

    @abstractmethod
    def supports_file_type(self, file_path: str | Path) -> bool:
        """Check if parser supports this file type

        Args:
            file_path: Path to file

        Returns:
            True if supported, False otherwise
        """
        pass

    def _calculate_sha256(self, file_path: str | Path) -> str:
        """Calculate SHA256 hash of a file's bytes.

        Used as the deterministic Document.id so chunk ids
        (`{sha256}_chunk_{i}`) and document deletion are stable across
        re-indexes regardless of file path.
        """
        sha256 = hashlib.sha256()
        with Path(file_path).open("rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
