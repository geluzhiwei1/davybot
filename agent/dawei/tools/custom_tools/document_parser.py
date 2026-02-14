# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

from pathlib import Path

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool


class DocumentParsingInput(BaseModel):
    """Input for DocumentParsingTool."""

    file_path: str = Field(..., description="Path to document file (PDF or DOCX).")


class DocumentParsingTool(CustomBaseTool):
    """Tool for parsing PDF and DOCX files."""

    def __init__(self):
        super().__init__()
        self.name = "Document Parsing Tool"
        self.description = "Parses PDF and DOCX files and returns their content as structured Markdown."
        self.args_schema = DocumentParsingInput

    @safe_tool_operation("document_parser", fallback_value="Error: Failed to parse document")
    def _run(self, file_path: str) -> str:
        """Parse the document file."""
        if not Path(file_path).exists():
            return f"Error: File not found at {file_path}"

        extension = Path(file_path).suffix

        if extension.lower() == ".pdf":
            return self._parse_pdf(file_path)
        if extension.lower() == ".docx":
            return self._parse_docx(file_path)
        return "Error: Unsupported file type. Please provide a .pdf or .docx file."

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
