# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

import ast
import logging
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.core.path_security import (
    PathTraversalError,
    safe_path_join,
    sanitize_filename,
)
from dawei.tools.custom_base_tool import CustomBaseTool

logger = logging.getLogger(__name__)


# Read File Tool
class ReadFileInput(BaseModel):
    """Input for ReadFileTool."""

    file_path: str = Field(
        ...,
        description="Path to the file to read, relative to workspace directory.",
    )
    start_line: int | None = Field(None, description="Starting line number (1-based).")
    end_line: int | None = Field(None, description="Ending line number (1-based).")


class ReadFileTool(CustomBaseTool):
    """Tool for reading file contents."""

    name: str = "read_file"
    description: str = "Reads the contents of files. Supports plain text files (with line numbers) and binary document formats (PDF, DOCX, DOC → extracted as plain text). All file paths are relative to the current workspace directory."
    args_schema: type[BaseModel] = ReadFileInput

    # Binary document extensions that need special parsing
    DOCUMENT_EXTENSIONS: set[str] = {".pdf", ".docx", ".doc"}

    @safe_tool_operation("read_file", fallback_value="Error: Failed to read file")
    def _run(
        self,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        """Read file contents with optional line range."""
        # 获取工作区路径
        workspace_path = None
        if self.context and hasattr(self.context, "user_workspace"):
            workspace_path = self.context.user_workspace.path

        # 处理路径：如果以 @ 开头，去掉 @
        clean_path = file_path.lstrip("@") if file_path.startswith("@") else file_path

        # ✅ Fast fail: Handle special case where path is "." (current directory)
        # Path(".").name returns "", which breaks the sanitization logic
        if clean_path in (".", "", "./"):
            return "Error: Cannot read directory, please specify a file path"

        # Sanitize filename to prevent directory traversal
        sanitized_filename = sanitize_filename(Path(clean_path).name)

        # Reconstruct path with sanitized filename
        dir_name = str(Path(clean_path).parent) if Path(clean_path).parent != Path() else ""
        clean_path = str(Path(dir_name) / sanitized_filename) if dir_name else sanitized_filename

        # 如果有工作区路径，使用安全路径连接
        if workspace_path:
            try:
                # Allow common file extensions for reading
                allowed_extensions: set[str] = {
                    ".py",
                    ".js",
                    ".ts",
                    ".tsx",
                    ".jsx",
                    ".vue",
                    ".html",
                    ".css",
                    ".json",
                    ".xml",
                    ".yaml",
                    ".yml",
                    ".md",
                    ".txt",
                    ".csv",
                    ".sql",
                    ".sh",
                    ".bat",
                    ".ps1",
                    ".toml",
                    ".ini",
                    ".cfg",
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".gif",
                    ".svg",
                    ".pdf",
                    ".doc",
                    ".docx",
                }
                full_path = safe_path_join(
                    workspace_path,
                    clean_path,
                    allow_absolute=False,
                    allowed_extensions=allowed_extensions,
                )
            except (PathTraversalError, ValueError) as e:
                logger.exception("Path validation failed: ")
                return f"Error: Invalid file path - {e!s}"
        else:
            full_path = clean_path

        if not Path(full_path).exists():
            return f"Error: File not found at {Path(full_path).name}"

        # Dispatch: binary documents vs plain text
        extension = Path(full_path).suffix.lower()
        if extension in self.DOCUMENT_EXTENSIONS:
            return self._read_document(full_path, extension)

        return self._read_text_file(full_path, start_line, end_line)

    def _read_text_file(
        self,
        full_path: str | Path,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        """Read plain text file with optional line range and line numbers."""
        with Path(full_path).open(encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        # Apply line range if specified
        if start_line is not None or end_line is not None:
            start = (start_line - 1) if start_line else 0
            end = end_line or len(lines)
            lines = lines[start:end]

        # Add line numbers
        numbered_lines = []
        start_num = start_line or 1
        for i, line in enumerate(lines, start=start_num):
            numbered_lines.append(f"{i} | {line.rstrip()}")

        return "\n".join(numbered_lines)

    def _read_document(self, full_path: str | Path, extension: str) -> str:
        """Read binary document (PDF/DOCX/DOC) and return extracted text."""
        if extension == ".pdf":
            return self._read_pdf(full_path)
        if extension == ".docx":
            return self._read_docx(full_path)
        if extension == ".doc":
            return self._read_doc(full_path)
        return f"Error: Unsupported document format: {extension}"

    @safe_tool_operation("read_pdf", fallback_value="Error: Failed to read PDF")
    def _read_pdf(self, file_path: str | Path) -> str:
        """Extract text from PDF file using PyMuPDF."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return "Error: PyMuPDF (fitz) not installed. Install with: pip install PyMuPDF"

        doc = fitz.open(str(file_path))
        pages = []
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text("text")
            pages.append(f"--- Page {page_num + 1} ---\n{text}")
        return "\n".join(pages)

    @safe_tool_operation("read_docx", fallback_value="Error: Failed to read DOCX")
    def _read_docx(self, file_path: str | Path) -> str:
        """Extract text from DOCX file using python-docx."""
        try:
            import docx
        except ImportError:
            return "Error: python-docx not installed. Install with: pip install python-docx"

        doc = docx.Document(str(file_path))
        paragraphs = []
        for para in doc.paragraphs:
            if para.style.name.startswith("Heading 1"):
                paragraphs.append(f"# {para.text}")
            elif para.style.name.startswith("Heading 2"):
                paragraphs.append(f"## {para.text}")
            elif para.style.name.startswith("Heading 3"):
                paragraphs.append(f"### {para.text}")
            else:
                paragraphs.append(para.text)
        return "\n".join(paragraphs)

    @safe_tool_operation("read_doc", fallback_value="Error: Failed to read DOC")
    def _read_doc(self, file_path: str | Path) -> str:
        """Extract text from legacy .doc file.

        Tries antiword, catdoc, libreoffice in order.
        Falls back to python-docx2txt if available.
        """
        # Strategy 1: antiword (lightweight, best for simple docs)
        try:
            result = subprocess.run(
                ["antiword", str(file_path)],
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
                ["catdoc", str(file_path)],
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
                    str(file_path),
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

        # Strategy 4: python-docx2txt (handles both .doc and .docx)
        try:
            import docx2txt

            text = docx2txt.process(str(file_path))
            if text.strip():
                return text
        except ImportError:
            pass

        return "Error: Cannot read .doc file. Install one of: antiword (apt install antiword), catdoc (apt install catdoc), libreoffice, or pip install docx2txt"


# List Files Tool
class ListFilesInput(BaseModel):
    """Input for ListFilesTool."""

    path: str = Field(
        ...,
        description="Directory path relative to workspace. Use '.' for current workspace directory.",
    )
    recursive: bool = Field(False, description="Whether to list files recursively.")


class ListFilesTool(CustomBaseTool):
    """Tool for listing directory contents."""

    name: str = "list_files"
    description: str = "Lists files and directories within the specified directory. All paths are relative to the current workspace directory."
    args_schema: type[BaseModel] = ListFilesInput

    @safe_tool_operation("list_files", fallback_value="Error: Failed to list directory")
    def _run(self, path: str, recursive: bool = False) -> str:
        """List directory contents."""
        # 获取工作区路径
        workspace_path = None
        if self.context and hasattr(self.context, "user_workspace"):
            workspace_path = self.context.user_workspace.path

        # 处理路径：如果以 @ 开头，去掉 @
        clean_path = path.lstrip("@") if path.startswith("@") else path

        # ✅ Fast fail: Handle special case where path is "." (current directory)
        # Path(".").name returns "", which breaks the sanitization logic
        if clean_path in (".", "", "./"):
            # Use workspace root directly
            full_path = workspace_path if workspace_path else "."
        else:
            # Sanitize path to prevent directory traversal
            sanitized_filename = sanitize_filename(Path(clean_path).name)

            # Reconstruct path with sanitized filename
            dir_name = str(Path(clean_path).parent) if Path(clean_path).parent != Path() else ""
            clean_path = str(Path(dir_name) / sanitized_filename) if dir_name else sanitized_filename

            # 如果有工作区路径，使用安全路径连接
            if workspace_path:
                try:
                    # Don't restrict extensions for directory listing
                    full_path = safe_path_join(
                        workspace_path,
                        clean_path,
                        allow_absolute=False,
                        allowed_extensions=None,
                    )
                except (PathTraversalError, ValueError) as e:
                    logger.exception("Path validation failed: ")
                    return f"Error: Invalid path - {e!s}"
            else:
                full_path = clean_path

        if not Path(full_path).exists():
            return f"Error: Path not found at {Path(full_path).name}"

        if not Path(full_path).is_dir():
            return f"Error: {Path(full_path).name} is not a directory"

        exclude_dirs = {".dawei", ".roo"}
        result = []

        if recursive:
            for root, dirs, files in Path(full_path).walk():
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                # ✅ Cross-platform: Use Path.parts for platform-independent path depth calculation
                # Calculate relative path depth for proper indentation
                try:
                    relative = root.relative_to(full_path)
                    level = len(relative.parts) - 1 if relative.parts else 0
                except ValueError:
                    # root is not relative to full_path (shouldn't happen)
                    level = 0
                indent = " " * 2 * level
                result.append(f"{indent}{root.name}/")
                subindent = " " * 2 * (level + 1)
                for file in files:
                    # Ensure file is a Path object
                    file_path = file if isinstance(file, Path) else Path(file)
                    result.append(f"{subindent}{file_path.name}")
        else:
            items = sorted(Path(full_path).iterdir())
            for item in items:
                if item.name in exclude_dirs:
                    continue
                if item.is_dir():
                    result.append(f"{item.name}/")
                else:
                    result.append(item.name)

        return "\n".join(result) if result else "Directory is empty"


# List Code Definition Names Tool
class ListCodeDefinitionsInput(BaseModel):
    """Input for ListCodeDefinitionsTool."""

    path: str = Field(
        ...,
        description="Path to the file or directory to analyze, relative to workspace directory.",
    )


class ListCodeDefinitionsTool(CustomBaseTool):
    """Tool for listing code definitions."""

    name: str = "list_code_definition_names"
    description: str = "Lists definition names (classes, functions, methods, etc.) from source code. All paths are relative to the current workspace directory."
    args_schema: type[BaseModel] = ListCodeDefinitionsInput

    @safe_tool_operation(
        "list_code_definitions",
        fallback_value="Error: Failed to extract code definitions",
    )
    def _run(self, path: str) -> str:
        """List code definitions from file or directory."""
        # 获取工作区路径
        workspace_path = None
        if self.context and hasattr(self.context, "user_workspace"):
            workspace_path = self.context.user_workspace.path

        # 处理路径：如果以 @ 开头，去掉 @
        clean_path = path.lstrip("@") if path.startswith("@") else path

        # ✅ Fast fail: Handle special case where path is "." (current directory)
        # Path(".").name returns "", which breaks the sanitization logic
        if clean_path in (".", "", "./"):
            # Use workspace root directly
            full_path = workspace_path if workspace_path else "."
        else:
            # Sanitize filename to prevent directory traversal
            sanitized_filename = sanitize_filename(Path(clean_path).name)

            # Reconstruct path with sanitized filename
            dir_name = str(Path(clean_path).parent) if Path(clean_path).parent != Path() else ""
            clean_path = str(Path(dir_name) / sanitized_filename) if dir_name else sanitized_filename

            # 如果有工作区路径，使用安全路径连接
            if workspace_path:
                try:
                    # Only allow Python files for code definitions
                    allowed_extensions: set[str] = {".py"}
                    full_path = safe_path_join(
                        workspace_path,
                        clean_path,
                        allow_absolute=False,
                        allowed_extensions=allowed_extensions,
                    )
                except (PathTraversalError, ValueError) as e:
                    logger.exception("Path validation failed: ")
                    return f"Error: Invalid file path - {e!s}"
            else:
                full_path = clean_path

        if not Path(full_path).exists():
            return f"Error: Path not found at {Path(full_path).name}"

        definitions = []

        if Path(full_path).is_file():
            definitions = self._extract_definitions(full_path)
        elif Path(full_path).is_dir():
            # Process all Python files in directory
            for root, _dirs, files in Path(full_path).walk():
                for file in files:
                    # Get file extension
                    if Path(file).suffix == ".py":
                        file_path = str(root / file)
                        file_defs = self._extract_definitions(file_path)
                        if file_defs:
                            definitions.append(f"\n# {file_path}")
                            definitions.extend(file_defs)

        return "\n".join(definitions) if definitions else "No code definitions found"

    @safe_tool_operation("extract_definitions", fallback_value="Error: Failed to parse file")
    def _extract_definitions(self, file_path: str) -> list[str]:
        """Extract definitions from a Python file."""
        definitions = []

        with Path(file_path).open(encoding="utf-8", errors="replace") as f:
            content = f.read()

        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                definitions.append(f"Class: {node.name} (line {node.lineno})")
            elif isinstance(node, ast.FunctionDef):
                definitions.append(f"Function: {node.name} (line {node.lineno})")
            elif isinstance(node, ast.AsyncFunctionDef):
                definitions.append(f"Async Function: {node.name} (line {node.lineno})")

        return definitions
