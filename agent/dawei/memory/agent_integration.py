# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Agent Memory Integration
Extends Agent class with memory system capabilities
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timezone
from pathlib import Path

from dawei.agentic.agent import Agent, is_memory_enabled  # ✨ 导入统一配置函数
from dawei.memory.gardener import MemoryGardener
from dawei.memory.memory_graph import MemoryEntry, MemoryGraph, MemoryType
from dawei.memory.virtual_context import VirtualContextManager

logger = logging.getLogger(__name__)


def _get_memory_db_path(workspace_path: str) -> str:
    """Get path to memory database"""
    return str(Path(workspace_path) / ".dawei" / "memory.db")


def setup_memory_system(agent: Agent) -> bool:
    """Setup memory system for agent

    This function should be called during Agent initialization
    to add memory capabilities to the agent.

    Args:
        agent: Agent instance to enhance

    Returns:
        True if memory system was initialized, False otherwise

    """
    try:
        if not is_memory_enabled(agent.user_workspace):
            logger.info("Memory system is disabled")
            return False

        workspace_path = agent.user_workspace.absolute_path
        memory_db = _get_memory_db_path(workspace_path)

        # Initialize MemoryGraph
        agent.memory_graph = MemoryGraph(memory_db, agent.event_bus)

        # Initialize VirtualContextManager
        agent.virtual_context = VirtualContextManager(
            db_path=memory_db,
            page_size=2000,
            max_active_pages=5,
        )

        # Initialize MemoryGardener (optional, requires LLMProvider)
        agent.memory_gardener = None
        try:
            if hasattr(agent, "execution_engine") and hasattr(
                agent.execution_engine,
                "llm_service",
            ):
                agent.memory_gardener = MemoryGardener(
                    memory_graph=agent.memory_graph,
                    llm_provider=agent.execution_engine.llm_service,
                    event_bus=agent.event_bus,
                    consolidation_interval=3600,  # 1 hour
                    decay_rate=0.95,
                    energy_threshold=0.2,
                )

                # Start gardener in background
                asyncio.create_task(agent.memory_gardener.start())
                logger.info("Memory Gardener started")
        except Exception as e:
            logger.warning(f"Failed to initialize MemoryGardener: {e}")

        # Add memory-related methods to agent
        agent._extract_memories_from_conversation = _extract_memories_from_conversation.__get__(
            agent,
            Agent,
        )
        agent._create_context_page = _create_context_page.__get__(agent, Agent)

        logger.info("Memory system initialized")
        return True

    except Exception as e:
        logger.error(f"Failed to setup memory system: {e}", exc_info=True)
        return False


async def _extract_memories_from_conversation(agent: Agent) -> list[MemoryEntry]:
    """Extract structured memories from recent conversation

    This method analyzes recent conversation messages and extracts
    structured facts, preferences, and patterns to store as memories.

    Args:
        agent: Agent instance

    Returns:
        List of extracted MemoryEntry objects

    """
    if not hasattr(agent, "memory_graph") or agent.memory_graph is None:
        return []

    try:
        # Get recent conversation (last 10 messages)
        conversation = agent.user_workspace.current_conversation
        if not conversation or not conversation.messages:
            return []

        recent_messages = conversation.messages[-10:]

        # Format messages for LLM
        messages_text = "\n".join(
            [f"{msg.role.value}: {msg.content}" for msg in recent_messages if hasattr(msg, "content") and msg.content],
        )

        if not messages_text.strip():
            return []

        # Use LLM to extract structured memories
        extraction_prompt = f"""Extract structured facts from this conversation.

Format: One fact per line as: [Subject] [relation] [Object]

Examples:
- User prefers Python
- Project uses FastAPI
- User dislikes JavaScript

Conversation:
{messages_text}

Extract facts:"""

        try:
            llm_service = agent.execution_engine.llm_service
            response = await llm_service.generate(
                messages=[{"role": "user", "content": extraction_prompt}],
                max_tokens=500,
                temperature=0.3,
            )

            if not response or not response.content:
                return []

            # Parse and create memories
            extracted_memories = []
            for line in response.content.strip().split("\n"):
                line = line.strip()
                if not line or line.startswith("-"):
                    line = line.lstrip("-").strip()

                parts = line.split(maxsplit=2)
                if len(parts) == 3:
                    memory = MemoryEntry(
                        id=str(uuid.uuid4()),
                        subject=parts[0],
                        predicate=parts[1],
                        object=parts[2],
                        valid_start=datetime.now(UTC),
                        memory_type=_infer_memory_type(parts[0], parts[1], parts[2]),
                        confidence=0.7,  # Moderate confidence for extracted facts
                        energy=1.0,
                        keywords=_extract_keywords(parts[0], parts[1], parts[2]),
                        metadata={
                            "source": "conversation",
                            "conversation_id": str(conversation.id),
                            "extraction_date": datetime.now(UTC).isoformat(),
                        },
                    )

                    await agent.memory_graph.add_memory(memory)
                    extracted_memories.append(memory)

            logger.info(f"Extracted {len(extracted_memories)} memories from conversation")
            return extracted_memories

        except Exception as e:
            logger.warning(f"Failed to extract memories using LLM: {e}")
            return []

    except Exception as e:
        logger.error(f"Failed to extract memories: {e}", exc_info=True)
        return []


async def _create_context_page(
    agent: Agent,
    content: str,
    summary: str,
    source_type: str = "conversation",
) -> str | None:
    """Create a context page from content

    Args:
        agent: Agent instance
        content: Full content to page
        summary: Short summary
        source_type: Type of content source

    Returns:
        Page ID if created, None otherwise

    """
    if not hasattr(agent, "virtual_context") or agent.virtual_context is None:
        return None

    try:
        session_id = str(agent.user_workspace.conversation_id)

        page_id = await agent.virtual_context.create_page(
            session_id=session_id,
            content=content,
            summary=summary,
            source_type=source_type,
        )

        logger.info(f"Created context page: {page_id}")
        return page_id

    except Exception:
        logger.exception("Failed to create context page: ")
        return None


def _infer_memory_type(subject: str, predicate: str, object: str) -> MemoryType:
    """Infer memory type from content"""
    # Preference indicators
    if any(word in predicate.lower() for word in ["prefers", "likes", "loves", "wants", "enjoys"]):
        return MemoryType.PREFERENCE

    # Procedure indicators
    if any(word in predicate.lower() for word in ["uses", "requires", "needs", "follows"]):
        return MemoryType.PROCEDURE

    # Strategy indicators
    if any(word in predicate.lower() for word in ["learned", "discovered", "figured out", "realized"]):
        return MemoryType.STRATEGY

    # Default to fact
    return MemoryType.FACT


def _extract_keywords(subject: str, predicate: str, object: str) -> list[str]:
    """Extract keywords from memory components"""
    import re

    keywords = []

    # Extract proper nouns (capitalized words)
    for text in [subject, predicate, object]:
        words = re.findall(r"\b[A-Z][a-z]+\b", text)
        keywords.extend(words)

    # Extract technical terms
    technical = re.findall(r"\b[A-Z]{2,}\b|\b\w+\.\w+\b", object)
    keywords.extend(technical)

    # Return unique keywords, limited to 5
    return list(set(keywords))[:5]


# Monkey-patch Agent.run() to include memory extraction
original_run = None


def wrap_agent_run_with_memory():
    """Wrap Agent.run() to include memory extraction"""
    from dawei.agentic import agent as agent_module

    global original_run
    if original_run is None:
        original_run = agent_module.Agent.run

    async def run_with_memory(self, user_input):
        """Enhanced run method that includes memory extraction"""
        # Call original run
        try:
            result = await original_run(self, user_input)
        except Exception:
            logger.exception("Error in agent.run: ")
            raise

        # Extract memories after completion (if memory system enabled)
        if hasattr(self, "memory_graph") and self.memory_graph is not None:
            try:
                await self._extract_memories_from_conversation()
            except Exception as e:
                logger.warning(f"Failed to extract memories: {e}")

        return result

    # Replace the method
    agent_module.Agent.run = run_with_memory


async def cleanup_memory_system(agent: Agent):
    """Cleanup memory system resources"""
    try:
        if hasattr(agent, "memory_gardener") and agent.memory_gardener is not None:
            await agent.memory_gardener.stop()
            logger.info("Memory Gardener stopped")

        if hasattr(agent, "virtual_context") and agent.virtual_context is not None:
            # Save any pending context
            logger.info("Virtual context cleaned up")

    except Exception:
        logger.exception("Failed to cleanup memory system: ")


# ============================================================================
# Agent Extensions
# ============================================================================


class AgentWithMemory(Agent):
    """Agent subclass with built-in memory support

    This extends the base Agent class with memory system capabilities.
    Use this class instead of Agent when memory features are needed.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Memory components (initialized later)
        self.memory_graph: MemoryGraph | None = None
        self.virtual_context: VirtualContextManager | None = None
        self.memory_gardener: MemoryGardener | None = None

    async def initialize(self) -> bool:
        """Initialize agent with memory system"""
        # Call parent initialize
        result = await super().initialize()

        if not result:
            return False

        # Setup memory system
        if setup_memory_system(self):
            self.logger.info("Agent with memory initialized")
        else:
            self.logger.info("Memory system not enabled")

        return True

    async def cleanup(self):
        """Cleanup resources including memory system"""
        await cleanup_memory_system(self)
        # Parent cleanup if exists
        if hasattr(super(), "cleanup"):
            await super().cleanup()

    async def query_memory(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        object: str | None = None,
    ) -> list[MemoryEntry]:
        """Query memory graph"""
        if not self.memory_graph:
            return []

        return await self.memory_graph.query_temporal(
            subject=subject,
            predicate=predicate,
            object=object,
            only_valid=True,
        )

    async def add_memory(
        self,
        subject: str,
        predicate: str,
        object: str,
        memory_type: str = "fact",
        confidence: float = 0.8,
        keywords: list[str] | None = None,
    ) -> MemoryEntry | None:
        """Add a memory to the graph"""
        if not self.memory_graph:
            return None

        memory = MemoryEntry(
            id=str(uuid.uuid4()),
            subject=subject,
            predicate=predicate,
            object=object,
            valid_start=datetime.now(UTC),
            memory_type=MemoryType(memory_type),
            confidence=confidence,
            energy=1.0,
            keywords=keywords or [],
            metadata={"source": "manual"},
        )

        await self.memory_graph.add_memory(memory)
        return memory

    async def get_memory_stats(self):
        """Get memory statistics"""
        if not self.memory_graph:
            return None

        return await self.memory_graph.get_stats()
