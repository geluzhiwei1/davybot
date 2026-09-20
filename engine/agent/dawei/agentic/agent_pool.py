# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Agent Pool — multi-agent collaboration infrastructure.

Phase 1: Basic pool creation, lifecycle management, and task dispatch.
Future phases will add parallel execution and inter-agent messaging.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from dawei.core.datetime_compat import UTC
from typing import Dict, List, Any

from dawei.logg.logging import get_logger

logger = get_logger(__name__)


class AgentPoolEntry:
    """Lightweight entry representing an Agent in the pool."""

    def __init__(
        self,
        agent_id: str,
        mode_slug: str,
        mode_name: str,
        agent: Any,
        event_bus: Any,
    ):
        self.agent_id = agent_id
        self.mode_slug = mode_slug
        self.mode_name = mode_name
        self.agent = agent
        self.event_bus = event_bus
        self.initialized = False
        self.active_tasks: Dict[str, str] = {}  # task_id -> description

    @property
    def is_busy(self) -> bool:
        return len(self.active_tasks) > 0

    def assign_task(self, task_id: str, description: str) -> None:
        self.active_tasks[task_id] = description

    def release_task(self, task_id: str) -> None:
        self.active_tasks.pop(task_id, None)


class AgentPool:
    """Manages multiple Agent instances for parallel/team execution.

    Usage:
        pool = AgentPool(workspace)
        await pool.add_agent("patent-engineer", "专利工程师")
        agent = pool.get_agent("patent-engineer")
        await pool.cleanup()
    """

    def __init__(self, workspace: Any):
        """
        Args:
            workspace: UserWorkspace instance
        """
        self.workspace = workspace
        self._entries: Dict[str, AgentPoolEntry] = {}
        self._default_agent_id: str | None = None
        self._lock = asyncio.Lock()
        self.pool_id = str(uuid.uuid4())
        logger.info(f"[AgentPool] Created pool {self.pool_id[:8]} for workspace={getattr(workspace, 'workspace_id', '?')}")

    @property
    def agents(self) -> List[AgentPoolEntry]:
        """Return all pool entries."""
        return list(self._entries.values())

    @property
    def agent_count(self) -> int:
        return len(self._entries)

    async def add_agent(
        self,
        mode_slug: str,
        mode_name: str = "",
        task_graph: Any = None,
    ) -> AgentPoolEntry:
        """Add an Agent to the pool for a specific mode/specialist.

        Args:
            mode_slug: Expert mode slug (e.g. 'patent-engineer')
            mode_name: Human-readable name
            task_graph: Optional shared TaskGraph; if None, creates a new one

        Returns:
            AgentPoolEntry for the added agent
        """
        async with self._lock:
            if mode_slug in self._entries:
                logger.warning(f"[AgentPool] Agent for mode '{mode_slug}' already exists")
                return self._entries[mode_slug]

            agent_id = str(uuid.uuid4())

            try:
                from .agent import Agent

                # Create a config with the mode preset
                config = {
                    "mode": "orchestrator",
                    "expert_mode": mode_slug,
                }

                agent = await Agent.create_with_default_engine(
                    self.workspace,
                    config=config,
                )

                # Initialize the agent
                if hasattr(agent, "initialize"):
                    await agent.initialize()
                    logger.info(f"[AgentPool] Agent {mode_slug} initialized successfully")

                entry = AgentPoolEntry(
                    agent_id=agent_id,
                    mode_slug=mode_slug,
                    mode_name=mode_name or mode_slug,
                    agent=agent,
                    event_bus=getattr(agent, "event_bus", None),
                )
                entry.initialized = True
                self._entries[mode_slug] = entry

                # Set first agent as default
                if self._default_agent_id is None:
                    self._default_agent_id = agent_id

                logger.info(
                    f"[AgentPool] Added agent: mode={mode_slug}, id={agent_id[:8]}, "
                    f"pool_size={len(self._entries)}"
                )
                return entry

            except Exception as e:
                logger.error(
                    f"[AgentPool] Failed to create agent for mode '{mode_slug}': {e}",
                    exc_info=True,
                )
                raise

    def get_agent(self, mode_slug: str) -> Any | None:
        """Get an Agent instance by mode slug.

        Args:
            mode_slug: The expert mode slug

        Returns:
            Agent instance or None if not found
        """
        entry = self._entries.get(mode_slug)
        return entry.agent if entry else None

    def get_default_agent(self) -> Any | None:
        """Get the default (first added) agent."""
        for entry in self._entries.values():
            if entry.agent_id == self._default_agent_id:
                return entry.agent
        # Fallback: return first available
        entries = list(self._entries.values())
        return entries[0].agent if entries else None

    def get_least_busy_agent(self) -> Any | None:
        """Get the agent with the fewest active tasks."""
        if not self._entries:
            return None
        sorted_entries = sorted(self._entries.values(), key=lambda e: len(e.active_tasks))
        return sorted_entries[0].agent

    async def cleanup(self) -> None:
        """Clean up all agents in the pool."""
        logger.info(f"[AgentPool] Cleaning up pool {self.pool_id[:8]} with {len(self._entries)} agents")

        for mode_slug, entry in list(self._entries.items()):
            try:
                if hasattr(entry.agent, "cleanup"):
                    await entry.agent.cleanup()
                logger.debug(f"[AgentPool] Cleaned up agent: {mode_slug}")
            except Exception as e:
                logger.warning(f"[AgentPool] Error cleaning up agent {mode_slug}: {e}")

        self._entries.clear()
        self._default_agent_id = None

    def to_status_dict(self) -> Dict[str, Any]:
        """Return pool status for WS status messages."""
        return {
            "pool_id": self.pool_id,
            "agent_count": len(self._entries),
            "agents": [
                {
                    "agent_id": e.agent_id,
                    "mode_slug": e.mode_slug,
                    "mode_name": e.mode_name,
                    "initialized": e.initialized,
                    "active_tasks": len(e.active_tasks),
                    "is_busy": e.is_busy,
                }
                for e in self._entries.values()
            ],
        }
