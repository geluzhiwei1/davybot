# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool


class DocumentParsingInput(BaseModel):
    """Input for DocumentParsingTool."""

    file_path: str = Field(..., description="Path to document file (PDF, DOCX, or DOC).")


class DocumentParsingTool(CustomBaseTool):
    """Tool for parsing PDF, DOCX, and DOC files."""

    def __init__(self):
        super().__init__()
        self.name = "Document Parsing Tool"
        self.description = "Parses PDF, DOCX, and DOC files and returns their content as structured Markdown."
        self.args_schema = DocumentParsingInput

    @safe_tool_operation("document_parser", fallback_value="Error: Failed to parse document")
    def _run(self, file_path: str) -> str:
        """Parse the document file."""
        if not Path(file_path).exists():
            return f"Error: File not found at {file_path}"

        extension = Path(file_path).suffix.lower()

        if extension == ".pdf":
            return self._parse_pdf(file_path)
        if extension == ".docx":
            return self._parse_docx(file_path)
        if extension == ".doc":
            return self._parse_doc(file_path)
        return "Error: Unsupported file type. Please provide a .pdf, .docx, or .doc file."

    @safe_tool_operation("pdf_parser", fallback_value="Error: Failed to parse PDF")
    def _parse_pdf(self, file_path: str) -> str:
        """Parse PDF file."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return "Error: PyMuPDF not installed. Please install fitz package."

        doc = fitz.open(file_path)
        content = []
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            content.append(f"## Page {page_num + 1}\n")
            content.append(page.get_text("text"))
        return "\n".join(content)

    @safe_tool_operation("docx_parser", fallback_value="Error: Failed to parse DOCX")
    def _parse_docx(self, file_path: str) -> str:
        """Parse DOCX file."""
        try:
            import docx
        except ImportError:
            return "Error: python-docx not installed. Please install python-docx package."

        doc = docx.Document(file_path)
        content = []
        for para in doc.paragraphs:
            if para.style.name.startswith("Heading 1"):
                content.append(f"# {para.text}")
            elif para.style.name.startswith("Heading 2"):
                content.append(f"## {para.text}")
            elif para.style.name.startswith("Heading 3"):
                content.append(f"### {para.text}")
            else:
                content.append(para.text)
        return "\n".join(content)

    @safe_tool_operation("doc_parser", fallback_value="Error: Failed to parse DOC")
    def _parse_doc(self, file_path: str) -> str:
        """Parse legacy .doc file.

        Tries antiword, catdoc, libreoffice in order.
        Falls back to python-docx2txt if available.
        """
        # Strategy 1: antiword (lightweight, best for simple docs)
        try:
            result = subprocess.run(
                ["antiword", file_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Strategy 2: catdoc
        try:
            result = subprocess.run(
                ["catdoc", file_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Strategy 3: libreoffice headless conversion
        try:
            result = subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--convert-to",
                    "txt:Text",
                    "--outdir",
                    str(Path(file_path).parent),
                    file_path,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                txt_path = Path(file_path).with_suffix(".txt")
                if txt_path.exists():
                    text = txt_path.read_text(encoding="utf-8", errors="replace")
                    txt_path.unlink(missing_ok=True)  # clean up temp file
                    return text
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Strategy 4: python-docx2txt
        try:
            import docx2txt

            text = docx2txt.process(file_path)
            if text.strip():
                return text
        except ImportError:
            pass

        return "Error: Cannot read .doc file. Install one of: antiword (apt install antiword), catdoc (apt install catdoc), libreoffice, or pip install docx2txt"
