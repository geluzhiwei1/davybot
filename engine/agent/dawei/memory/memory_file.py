# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Markdown file-based memory storage (simplified, Codex-inspired).

Replaces SQLite search with direct file read/write:
- User-level:      {DAWEI_HOME}/configs/{user_id}/memory.md
- Workspace-level: {workspace}/.dawei/memory.md

Agent reads both files each turn and injects the full content — no retrieval/search.
"""

import logging
from pathlib import Path

from dawei import get_dawei_home

logger = logging.getLogger(__name__)

_DEFAULT_TEMPLATE = """\
# Memories

<!-- Agent memory file. Edit freely. Lines here are injected into every conversation. -->
"""


def _safe_uid(user_id: str | None) -> str:
    uid = user_id or "default_user"
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in uid)


# ------------------------------------------------------------------
# Path resolution
# ------------------------------------------------------------------

def user_memory_md_path(user_id: str = "default_user") -> Path:
    """Path to the user-level memory.md (shared across workspaces)."""
    return get_dawei_home() / "configs" / _safe_uid(user_id) / "memory.md"


def workspace_memory_md_path(workspace_root: str | Path) -> Path:
    """Path to the workspace-level memory.md."""
    return Path(workspace_root) / ".dawei" / "memory.md"


# ------------------------------------------------------------------
# Read / Write
# ------------------------------------------------------------------

def read_memory_md(path: Path) -> str:
    """Read memory.md content. Returns empty string if file doesn't exist."""
    path = Path(path)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read memory file {path}: {e}")
        return ""


def write_memory_md(path: Path, content: str) -> None:
    """Write content to memory.md, creating parent dirs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def append_memory_md(path: Path, line: str) -> None:
    """Append a single line to memory.md (creates file if needed)."""
    path = Path(path)
    existing = read_memory_md(path)
    if not existing:
        write_memory_md(path, _DEFAULT_TEMPLATE)
    if not line.endswith("\n"):
        line += "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


def ensure_memory_md(path: Path) -> None:
    """Create memory.md with default template if it doesn't exist."""
    path = Path(path)
    if not path.exists():
        write_memory_md(path, _DEFAULT_TEMPLATE)
