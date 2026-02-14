# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""DaweiMem - Memory System for zhuan-agent

This package implements an advanced memory management system with:
- Temporal Knowledge Graph (MemoryGraph)
- Virtual Context Paging (VirtualContextManager)
- Background Memory Consolidation (MemoryGardener)

Components:
- memory_graph: Temporal knowledge graph with associative retrieval
- virtual_context: Page-in/Page-out context management
- gardener: Background daemon for memory consolidation and archival
"""

from .agent_integration import AgentWithMemory, setup_memory_system
from .database import (
    cleanup_old_memories,
    get_memory_setting,
    init_memory_database,
    migrate_memory_database,
    set_memory_setting,
)
from .gardener import MemoryGardener
from .memory_graph import MemoryEntry, MemoryGraph, MemoryStats, MemoryType
from .virtual_context import ContextPage, VirtualContextManager

__all__ = [
    # Memory Graph
    "MemoryType",
    "MemoryEntry",
    "MemoryGraph",
    "MemoryStats",
    # Virtual Context
    "ContextPage",
    "VirtualContextManager",
    # Gardener
    "MemoryGardener",
    # Database
    "init_memory_database",
    "migrate_memory_database",
    "get_memory_setting",
    "set_memory_setting",
    "cleanup_old_memories",
    # Integration
    "setup_memory_system",
    "AgentWithMemory",
]
