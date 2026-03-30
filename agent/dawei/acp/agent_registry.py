# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""ACP Agent Registry - local agent discovery and config persistence.

Scans system PATH for known ACP-compatible commands, supports manual
add/remove, and persists the registry to ``{DAWEI_HOME}/configs/acp_agents.json``.

KISS: flat JSON file, no database, no remote sync.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from dawei import get_dawei_home

logger = logging.getLogger(__name__)

# Known ACP agent commands (from ACP Registry).
# Key = executable name, Value = display metadata.
KNOWN_ACP_COMMANDS: dict[str, dict[str, str]] = {
    "codex": {"name": "Codex CLI", "description": "OpenAI Codex coding assistant"},
    "claude": {"name": "Claude Agent", "description": "Anthropic Claude coding agent"},
    "gemini": {"name": "Gemini CLI", "description": "Google Gemini coding assistant"},
    "cline": {"name": "Cline", "description": "Autonomous coding agent CLI"},
    "augment": {"name": "Auggie CLI", "description": "Augment Code agent"},
    "goose": {"name": "Goose", "description": "Open-source AI agent by Block"},
    "opencode": {"name": "OpenCode", "description": "Open source coding agent"},
    "kilo": {"name": "Kilo", "description": "Open source coding agent"},
    "cursor": {"name": "Cursor", "description": "Cursor coding agent"},
    "copilot": {"name": "GitHub Copilot", "description": "GitHub AI pair programmer"},
    "junie": {"name": "Junie", "description": "JetBrains AI coding agent"},
    "amp": {"name": "Amp", "description": "Amp frontier coding agent"},
}


@dataclass
class ACPAgentInfo:
    """Metadata for a single registered ACP agent."""

    command: str
    name: str
    description: str = ""
    available: bool = False  # True if command found on PATH
    manual: bool = False  # True if user added manually
    disabled: bool = False  # True if user explicitly disabled

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ACPAgentInfo:
        return cls(
            command=data.get("command", ""),
            name=data.get("name", data.get("command", "")),
            description=data.get("description", ""),
            available=data.get("available", False),
            manual=data.get("manual", False),
            disabled=data.get("disabled", False),
        )


def _registry_file() -> Path:
    """Return path to ``{DAWEI_HOME}/configs/acp_agents.json``."""
    return get_dawei_home() / "configs" / "acp_agents.json"


def _which(command: str) -> str | None:
    """Find executable on PATH (cross-platform)."""
    return shutil.which(command)


def scan_path_for_agents() -> list[ACPAgentInfo]:
    """Scan system PATH for known ACP agent commands.

    Returns a list of :class:`ACPAgentInfo` for every known command
    that is present on PATH.
    """
    found: list[ACPAgentInfo] = []
    for cmd, meta in KNOWN_ACP_COMMANDS.items():
        resolved = _which(cmd)
        if resolved:
            found.append(
                ACPAgentInfo(
                    command=cmd,
                    name=meta["name"],
                    description=meta["description"],
                    available=True,
                    manual=False,
                )
            )
    return found


def load_registry() -> list[ACPAgentInfo]:
    """Load the persisted agent registry from disk.

    Returns an empty list if the file does not exist.
    """
    path = _registry_file()
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return [ACPAgentInfo.from_dict(item) for item in data.get("agents", [])]
    except Exception as exc:
        logger.warning("Failed to load ACP agent registry: %s", exc)
        return []


def save_registry(agents: list[ACPAgentInfo]) -> None:
    """Persist the agent registry to disk."""
    path = _registry_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"agents": [a.to_dict() for a in agents]}
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.debug("ACP agent registry saved: %s (%d agents)", path, len(agents))


def _merge_scan_with_saved(
    scanned: list[ACPAgentInfo],
    saved: list[ACPAgentInfo],
) -> list[ACPAgentInfo]:
    """Merge scan results with persisted entries.

    Rules:
    - Scanned agents update ``available`` status.
    - Manually added agents are kept even if not in KNOWN_ACP_COMMANDS.
    - ``disabled`` and ``manual`` flags from saved data are preserved.
    - Duplicates (same command) are de-duplicated, saved wins for flags.
    """
    saved_by_cmd: dict[str, ACPAgentInfo] = {a.command: a for a in saved}
    scanned_by_cmd: dict[str, ACPAgentInfo] = {a.command: a for a in scanned}

    merged: list[ACPAgentInfo] = []

    # Start with all scanned agents
    for cmd, info in scanned_by_cmd.items():
        if cmd in saved_by_cmd:
            # Merge: scanned provides availability, saved provides user flags
            existing = saved_by_cmd[cmd]
            existing.available = info.available
            # Update name/description from scan if saved doesn't override
            if not existing.manual:
                existing.name = info.name
                existing.description = info.description
            merged.append(existing)
            del saved_by_cmd[cmd]
        else:
            merged.append(info)

    # Append remaining manually-added agents not found by scan
    for cmd, info in saved_by_cmd.items():
        # Re-check availability for manual agents
        info.available = _which(cmd) is not None
        merged.append(info)

    return merged


def discover_and_merge() -> list[ACPAgentInfo]:
    """One-shot: scan PATH, merge with saved, persist, return result."""
    scanned = scan_path_for_agents()
    saved = load_registry()
    merged = _merge_scan_with_saved(scanned, saved)
    save_registry(merged)
    return merged


def add_agent(command: str, name: str | None = None, description: str = "") -> ACPAgentInfo:
    """Manually add an agent entry.

    Returns the added agent. Raises ValueError if command already registered.
    """
    agents = load_registry()
    if any(a.command == command for a in agents):
        raise ValueError(f"Agent '{command}' already registered")

    resolved = _which(command)
    info = ACPAgentInfo(
        command=command,
        name=name or command,
        description=description,
        available=resolved is not None,
        manual=True,
    )
    agents.append(info)
    save_registry(agents)
    logger.info("Manually added ACP agent: %s", command)
    return info


def remove_agent(command: str) -> bool:
    """Remove an agent from the registry.

    Returns True if removed, False if not found.
    """
    agents = load_registry()
    before = len(agents)
    agents = [a for a in agents if a.command != command]
    if len(agents) == before:
        return False
    save_registry(agents)
    logger.info("Removed ACP agent: %s", command)
    return True


def toggle_agent(command: str, disabled: bool) -> ACPAgentInfo | None:
    """Toggle an agent's disabled flag.

    Returns the updated agent or None if not found.
    """
    agents = load_registry()
    for a in agents:
        if a.command == command:
            a.disabled = disabled
            save_registry(agents)
            return a
    return None


def list_available_agents() -> list[ACPAgentInfo]:
    """Return only agents that are available and not disabled.

    Used by call_acp_agent to build dynamic tool description.
    """
    agents = load_registry()
    return [a for a in agents if a.available and not a.disabled]


def get_tool_description_text() -> str:
    """Build a human-readable summary for the call_acp_agent tool description."""
    agents = list_available_agents()
    if not agents:
        return (
            "调用外部 ACP 兼容 agent。当前无可用 agent，"
            "请先在设置中扫描或手动添加 ACP agent。"
        )
    agent_lines = ", ".join(f"`{a.command}` ({a.name})" for a in agents)
    return (
        f"调用外部 ACP 兼容 agent。当前可用: {agent_lines}。"
        f"参数 command 必须是上述之一。"
    )
