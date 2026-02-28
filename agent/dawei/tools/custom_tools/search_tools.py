# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Search Tools - File pattern search and full-text search"""

import re
from pathlib import Path

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool


# Search Files Tool (Regex-based)
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
    """Tool for searching patterns across files using regex."""

    name: str = "search_files"
    description: str = "Performs regex search across files in a specified directory, providing context-rich results. All paths are relative to the current workspace directory."
    args_schema: type[BaseModel] = SearchFilesInput

    @safe_tool_operation("search_files", fallback_value="Error: Failed to search files")
    def _run(self, path: str, regex: str, file_pattern: str | None = None) -> str:
        """Search for regex pattern in files."""
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
                    with Path(file_path).open(encoding="utf-8", errors="replace") as f:
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


# Full-Text Search Tool
class FullTextSearchInput(BaseModel):
    """Input for FullTextSearchTool."""

    query: str = Field(..., description="Text query to search for in file contents.")
    path: str = Field(".", description="Directory path to search in (default: current directory).")
    max_results: int = Field(10, description="Maximum number of results to return.")
    file_extensions: list[str] | None = Field(
        None,
        description="List of file extensions to search (e.g., ['.py', '.js']). Searches common text files if not specified.",
    )


class FullTextSearchTool(CustomBaseTool):
    """Tool for full-text search across source code files."""

    name: str = "fulltext_search"
    description: str = (
        "Performs full-text search across files using keyword matching and relevance scoring. "
        "Returns ranked results with context snippets showing matched lines. "
        "Supports multiple file extensions and provides smart relevance scoring."
    )
    args_schema: type[BaseModel] = FullTextSearchInput

    @safe_tool_operation(
        "fulltext_search",
        fallback_value="Error: Failed to perform full-text search",
    )
    def _run(self, query: str, path: str = ".", max_results: int = 10, file_extensions: list[str] | None = None) -> str:
        """Perform full-text search with relevance scoring."""
        # Default file extensions to search
        if file_extensions is None:
            file_extensions = [".py", ".js", ".ts", ".jsx", ".tsx", ".md", ".txt", ".json", ".yaml", ".yml"]

        results = []
        query_lower = query.lower()
        query_words = [w.lower() for w in query.split() if len(w) > 2]  # Filter short words

        for root, dirs, files in Path(path).walk():
            # Skip hidden and build directories
            dirs[:] = [d for d in dirs if not d.name.startswith(".") and d.name not in ["node_modules", "__pycache__", "target", "dist", "build"]]

            for file in files:
                if file.suffix not in file_extensions:
                    continue

                file_path = root / file

                try:
                    with Path(file_path).open(encoding="utf-8", errors="replace") as f:
                        content = f.read()

                    # Calculate relevance score
                    score = self._calculate_relevance_score(content, query, query_lower, query_words)

                    if score > 0:
                        # Extract context snippets around matches
                        snippet = self._extract_snippet(content, query_lower)

                        results.append(
                            {
                                "file": str(file_path.relative_to(path) if path != "." else str(file_path)),
                                "score": score,
                                "snippet": snippet,
                            },
                        )

                except (UnicodeDecodeError, PermissionError, OSError):
                    # Skip files that can't be read
                    continue

        # Sort by score (descending) and limit results
        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:max_results]

        # Format results
        if results:
            output = [f"## Full-Text Search Results for: '{query}'\n"]
            output.append(f"Found {len(results)} result(s) in directory: {path}\n")

            for i, result in enumerate(results, 1):
                output.append(f"\n{i}. **{result['file']}** (Relevance: {result['score']})")
                output.append(f"```\n{result['snippet']}\n```")

            return "\n".join(output)

        return f"No results found for query: '{query}' in directory: {path}"

    def _calculate_relevance_score(self, content: str, query: str, query_lower: str, query_words: list[str]) -> int:
        """Calculate relevance score for a file.

        Scoring factors:
        - Exact case-sensitive match: +10 points (first occurrence), +1 per additional occurrence
        - Case-insensitive match: +5 points (first occurrence), +1 per additional occurrence
        - Word-level matches: +1 point per occurrence (capped at 10 to avoid dominating)

        Args:
            content: File content
            query: Original query (case-sensitive)
            query_lower: Lowercase query
            query_words: List of query words (lowercase, filtered)

        Returns:
            Relevance score (higher = more relevant)
        """
        score = 0
        content_lower = content.lower()

        # Check for exact match (highest priority)
        if query in content:
            # Count occurrences
            exact_count = content.count(query)
            score += 10 + max(0, exact_count - 1)  # First match: 10, additional: +1 each

        # Check for case-insensitive match (if exact match not found)
        elif query_lower in content_lower:
            # Count occurrences
            lower_count = content_lower.count(query_lower)
            score += 5 + max(0, lower_count - 1)  # First match: 5, additional: +1 each

        # Word-level matches (only if no phrase match yet)
        if score == 0 and query_words:
            word_matches = 0
            for word in query_words:
                if word in content_lower:
                    word_count = content_lower.count(word)
                    word_matches += word_count

            # Add word match score (capped to avoid dominating)
            score += min(word_matches, 10)

        return score

    def _extract_snippet(self, content: str, query_lower: str, max_snippets: int = 3, context_lines: int = 2) -> str:
        """Extract context snippets around matches.

        Args:
            content: File content
            query_lower: Lowercase query to find
            max_snippets: Maximum number of snippets to extract
            context_lines: Number of lines before/after match to include

        Returns:
            Formatted snippet with context
        """
        lines = content.split("\n")
        snippet_lines = []
        snippets_found = 0

        for i, line in enumerate(lines):
            if query_lower in line.lower():
                # Get context around match
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)

                # Add line numbers
                for j in range(start, end):
                    prefix = ">>> " if j == i else "    "
                    snippet_lines.append(f"{prefix}{j+1}:{lines[j]}")

                snippet_lines.append("...")  # Separator between snippets
                snippets_found += 1

                if snippets_found >= max_snippets:
                    break

        return "\n".join(snippet_lines).rstrip()
