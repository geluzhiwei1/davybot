# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

import re

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool


# Search Files Tool
class SearchFilesInput(BaseModel):
    """Input for SearchFilesTool."""

    path: str = Field(
        ...,
        description="Directory path to search in, relative to workspace. Use '.' for current workspace directory.",
    )
    regex: str = Field(..., description="Regular expression pattern to search for.")
    file_pattern: str | None = Field(
        None,
        description="Glob pattern to filter files (e.g., '*.py').",
    )


class SearchFilesTool(CustomBaseTool):
    """Tool for searching patterns across files."""

    name: str = "search_files"
    description: str = "Performs regex search across files in a specified directory, providing context-rich results. All paths are relative to the current workspace directory."
    args_schema: type[BaseModel] = SearchFilesInput

    @safe_tool_operation("search_files", fallback_value="Error: Failed to search files")
    def _run(self, path: str, regex: str, file_pattern: str | None = None) -> str:
        """Search for regex pattern in files."""
        from pathlib import Path

        path_obj = Path(path)

        if not path_obj.exists():
            return f"Error: Path not found at {path}"

        if not path_obj.is_dir():
            return f"Error: {path} is not a directory"

        pattern = re.compile(regex)
        matches = []

        # Walk through directory
        for root, _dirs, files in Path(path).walk():
            for file in files:
                # Apply file pattern filter if specified
                if file_pattern:
                    import fnmatch

                    if not fnmatch.fnmatch(file.name, file_pattern):
                        continue

                file_path = root / file

                try:
                    with Path(file_path).open(encoding="utf-8") as f:
                        lines = f.readlines()

                    # Search for pattern in each line
                    for line_num, line in enumerate(lines, 1):
                        if pattern.search(line):
                            # Get context (2 lines before and after)
                            start_ctx = max(0, line_num - 3)
                            end_ctx = min(len(lines), line_num + 2)

                            context = []
                            for ctx_line_num in range(start_ctx, end_ctx):
                                prefix = ">>> " if ctx_line_num == line_num else "    "
                                context.append(
                                    f"{prefix}{ctx_line_num} | {lines[ctx_line_num - 1].rstrip()}",
                                )

                            matches.append(f"\n## {file_path}:{line_num}\n" + "\n".join(context))

                except (UnicodeDecodeError, PermissionError):
                    # Skip binary files or files we can't read
                    continue

        if matches:
            return f"Found {len(matches)} matches:\n" + "\n".join(matches)
        return f"No matches found for pattern: {regex}"


# Codebase Search Tool (Mock implementation)
class CodebaseSearchInput(BaseModel):
    """Input for CodebaseSearchTool."""

    query: str = Field(..., description="Semantic search query.")
    path: str | None = Field(".", description="Path to search in (default: current directory).")
    max_results: int = Field(10, description="Maximum number of results to return.")


class CodebaseSearchTool(CustomBaseTool):
    """Tool for semantic codebase search."""

    name: str = "codebase_search"
    description: str = "Performs semantic searches across the indexed codebase."
    args_schema: type[BaseModel] = CodebaseSearchInput

    @safe_tool_operation(
        "codebase_search",
        fallback_value="Error: Failed to perform codebase search",
    )
    def _run(self, query: str, path: str = ".", max_results: int = 10) -> str:
        """Perform semantic search (mock implementation)."""
        # This is a mock implementation
        # In a real implementation, this would use embeddings and vector search

        # For now, do a simple text search as fallback

        results = []
        query_lower = query.lower()

        for root, dirs, files in Path(path).walk():
            # Skip hidden directories and common build directories
            dirs[:] = [d for d in dirs if not d.name.startswith(".") and d.name not in ["node_modules", "__pycache__", "target"]]

            for file in files:
                if file.suffix in (".py", ".js", ".ts", ".jsx", ".tsx", ".md", ".txt"):
                    file_path = root / file

                    try:
                        with Path(file_path).open(encoding="utf-8") as f:
                            content = f.read()

                        # Simple relevance scoring
                        content_lower = content.lower()
                        score = 0

                        # Exact matches get higher score
                        if query in content:
                            score += 10
                        if query_lower in content_lower:
                            score += 5

                        # Word matches
                        query_words = query_lower.split()
                        for word in query_words:
                            if word in content_lower:
                                score += 1

                        if score > 0:
                            # Extract a snippet
                            lines = content.split("\n")
                            snippet_lines = []

                            for i, line in enumerate(lines):
                                if query_lower in line.lower():
                                    # Get context around match
                                    start = max(0, i - 2)
                                    end = min(len(lines), i + 3)
                                    snippet = "\n".join(lines[start:end])
                                    snippet_lines.append(snippet)
                                    if len(snippet_lines) >= 3:  # Limit snippets
                                        break

                            results.append(
                                {
                                    "file": file_path,
                                    "score": score,
                                    "snippet": "\n...\n".join(snippet_lines),
                                },
                            )

                    except (UnicodeDecodeError, PermissionError):
                        continue

        # Sort by score and limit results
        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:max_results]

        if results:
            output = [f"## Semantic Search Results for: '{query}'\n"]
            for i, result in enumerate(results, 1):
                output.append(f"\n{i}. **{result['file']}** (Score: {result['score']})")
                output.append(f"```\n{result['snippet']}\n```")
            return "\n".join(output)
        return f"No results found for query: {query}"
