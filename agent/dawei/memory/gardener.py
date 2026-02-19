# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Memory Gardener - Background Memory Consolidation and Maintenance
Implements memory evolution: consolidation, forgetting, and archival
"""

import asyncio
import contextlib
import logging
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from dawei.llm_api.llm_provider import LLMProvider

from .memory_graph import MemoryEntry, MemoryGraph, MemoryType

logger = logging.getLogger(__name__)


class MemoryGardener:
    """Background memory maintenance daemon

    Responsibilities:
    1. Consolidation: Merge related memories into higher-level strategies
    2. Forgetting: Decay low-energy memories and archive them
    3. Error learning: Extract strategies from error patterns

    Usage:
        gardener = MemoryGardener(
            memory_graph=memory_graph,
            llm_provider=llm_provider,
            consolidation_interval=3600  # 1 hour
        )
        await gardener.start()
        # ... later ...
        await gardener.stop()
    """

    def __init__(
        self,
        memory_graph: MemoryGraph,
        llm_provider: LLMProvider | None = None,
        event_bus=None,
        consolidation_interval: int = 3600,  # 1 hour
        decay_rate: float = 0.95,
        energy_threshold: float = 0.2,
        archive_days: int = 30,
    ):
        """Initialize MemoryGardener

        Args:
            memory_graph: MemoryGraph instance to maintain
            llm_provider: LLM provider for consolidation (optional)
            event_bus: Event bus instance (NOTE: CORE_EVENT_BUS has been removed, defaults to None)
            consolidation_interval: Seconds between consolidation runs
            decay_rate: Energy decay rate per run
            energy_threshold: Threshold for archiving low-energy memories
            archive_days: Days after which to archive expired memories

        """
        self.memory_graph = memory_graph
        self.llm_provider = llm_provider
        self.event_bus = event_bus  # Don't default to CORE_EVENT_BUS
        self.consolidation_interval = consolidation_interval
        self.decay_rate = decay_rate
        self.energy_threshold = energy_threshold
        self.archive_days = archive_days

        self.logger = logging.getLogger(__name__)
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        """Start the gardener background task"""
        if self._running:
            self.logger.warning("Memory Gardener is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._gardener_loop())
        self.logger.info("Memory Gardener started")

    async def stop(self):
        """Stop the gardener background task"""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

        self.logger.info("Memory Gardener stopped")

    async def _gardener_loop(self):
        """Main gardener loop"""
        self.logger.info("Gardener loop started")

        while self._running:
            try:
                # Apply energy decay
                await self._decay_memories()

                # Consolidate recent memories
                if self.llm_provider:
                    await self._consolidate_memories()

                # Archive expired memories
                await self._archive_expired()

            except Exception as e:
                self.logger.error(f"Gardener error: {e}", exc_info=True)

            # Wait for next cycle
            try:
                await asyncio.sleep(self.consolidation_interval)
            except asyncio.CancelledError:
                break

        self.logger.info("Gardener loop stopped")

    async def _decay_memories(self):
        """Apply energy decay to all memories"""
        try:
            db_path = self.memory_graph.db_path

            with sqlite3.connect(db_path) as conn:
                cursor = conn.execute(
                    "UPDATE memory_graph SET energy = energy * ? WHERE energy > 0.01",
                    (self.decay_rate,),
                )
                affected = cursor.rowcount

            self.logger.debug(f"Decayed {affected} memories (rate: {self.decay_rate})")

        except sqlite3.Error:
            self.logger.exception("Failed to decay memories: ")

    async def _consolidate_memories(self):
        """Consolidate recent memories into higher-level knowledge

        Looks for patterns and generates strategies/summaries
        """
        try:
            # Get recent memories with high energy and access count
            recent_cutoff = datetime.now(UTC) - timedelta(hours=24)

            with sqlite3.connect(self.memory_graph.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT * FROM memory_graph
                    WHERE created_at >= ?
                      AND energy > ?
                      AND access_count >= 2
                      AND (valid_end IS NULL OR valid_end > datetime('now'))
                    ORDER BY access_count DESC, energy DESC
                    LIMIT 50
                    """,
                    (recent_cutoff.isoformat(), 0.5),
                )
                rows = cursor.fetchall()

            if len(rows) < 3:
                self.logger.debug("Not enough memories for consolidation")
                return

            # Group by subject
            grouped: dict[str, list[MemoryEntry]] = {}
            for row in rows:
                mem = self.memory_graph._row_to_memory(row)
                if mem.subject not in grouped:
                    grouped[mem.subject] = []
                grouped[mem.subject].append(mem)

            # Consolidate each group
            consolidated_count = 0
            for subject, memories in grouped.items():
                if len(memories) < 2:
                    continue

                try:
                    # Emit consolidation start event
                    if self.event_bus:
                        await self.event_bus.publish(
                            "MEMORY_CONSOLIDATION_STARTED",
                            {"subject": subject, "count": len(memories)},
                        )

                    # Use LLM to generate consolidated strategy
                    strategy = await self._generate_consolidation_strategy(subject, memories)

                    if strategy:
                        # Store as strategy memory
                        await self.memory_graph.add_memory(strategy)
                        consolidated_count += 1

                        # Emit consolidation complete event
                        if self.event_bus:
                            await self.event_bus.publish(
                                "MEMORY_CONSOLIDATION_COMPLETED",
                                {
                                    "subject": subject,
                                    "strategy_id": strategy.id,
                                    "consolidated_from": [m.id for m in memories],
                                },
                            )

                except Exception:
                    self.logger.exception("Consolidation failed for {subject}: ")

            if consolidated_count > 0:
                self.logger.info(f"Consolidated {consolidated_count} memory groups")

        except sqlite3.Error:
            self.logger.exception("Failed to consolidate memories: ")

    async def _generate_consolidation_strategy(
        self,
        subject: str,
        memories: list[MemoryEntry],
    ) -> MemoryEntry | None:
        """Generate consolidated strategy from related memories"""
        try:
            memory_descriptions = [f"- {m.predicate}: {m.object} (accessed {m.access_count}x times, confidence: {m.confidence:.2f})" for m in memories]

            prompt = f"""Based on the following memories about '{subject}', extract a high-level strategy, pattern, or learning:

{chr(10).join(memory_descriptions)}

Provide a concise strategy that captures the common pattern or learned best practice.
Response format:
PREFERS: [what the subject prefers/likes]
USES: [tools/methods the subject uses]
LEARNS: [key insights or patterns]
AVOIDS: [things to avoid based on the data]"""

            response = await self.llm_provider.generate(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.3,
            )

            if not response or not response.content:
                return None

            # Create strategy memory
            import uuid

            strategy = MemoryEntry(
                id=str(uuid.uuid4()),
                subject=subject,
                predicate="learned_strategy",
                object=response.content.strip(),
                memory_type=MemoryType.STRATEGY,
                confidence=0.7,
                energy=1.0,
                keywords=self._extract_keywords(response.content),
                metadata={
                    "consolidated_from": [m.id for m in memories],
                    "consolidation_date": datetime.now(UTC).isoformat(),
                },
            )

            self.logger.info(f"Generated strategy for {subject}")
            return strategy

        except Exception:
            self.logger.exception("Failed to generate strategy: ")
            return None

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract keywords from text"""
        # Simple keyword extraction
        import re

        words = re.findall(r"\b[A-Z][a-z]+\b", text)
        # Return unique words, limited to 10
        return list(set(words))[:10]

    async def _archive_expired(self):
        """Archive memories that have expired and low energy"""
        try:
            archive_cutoff = datetime.now(UTC) - timedelta(days=self.archive_days)

            with sqlite3.connect(self.memory_graph.db_path) as conn:
                # Find memories to archive (expired + low energy)
                cursor = conn.execute(
                    """
                    UPDATE memory_graph
                    SET energy = 0
                    WHERE valid_end IS NOT NULL
                      AND valid_end < ?
                      AND energy < ?
                    """,
                    (archive_cutoff.isoformat(), self.energy_threshold),
                )
                archived = cursor.rowcount

            if archived > 0:
                # Emit archive event
                if self.event_bus:
                    await self.event_bus.publish("MEMORY_ENTRY_ARCHIVED", {"count": archived})

                self.logger.info(f"Archived {archived} expired memories")

        except sqlite3.Error:
            self.logger.exception("Failed to archive memories: ")

    async def consolidate_now(self, subject: str | None = None) -> dict[str, Any]:
        """Trigger immediate consolidation

        Args:
            subject: Optional subject to consolidate (all if None)

        Returns:
            Consolidation results

        """
        try:
            if self.event_bus:
                await self.event_bus.publish(
                    "MEMORY_CONSOLIDATION_STARTED",
                    {"subject": subject or "all", "manual": True},
                )

            strategies_created = 0

            if subject:
                # Consolidate specific subject
                memories = await self.memory_graph.query_temporal(subject=subject)
                if len(memories) >= 2 and self.llm_provider:
                    strategy = await self._generate_consolidation_strategy(subject, memories)
                    if strategy:
                        await self.memory_graph.add_memory(strategy)
                        strategies_created += 1
            else:
                # Consolidate all (reuse existing logic)
                await self._consolidate_memories()

            if self.event_bus:
                await self.event_bus.publish(
                    "MEMORY_CONSOLIDATION_COMPLETED",
                    {"strategies_created": strategies_created},
                )

            return {"success": True, "strategies_created": strategies_created}

        except Exception as e:
            self.logger.exception("Manual consolidation failed: ")
            return {"success": False, "error": str(e)}

    async def archive_now(self) -> dict[str, Any]:
        """Trigger immediate archival

        Returns:
            Archival results

        """
        try:
            await self._archive_expired()

            # Get count of archived memories
            with sqlite3.connect(self.memory_graph.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM memory_graph WHERE energy = 0")
                total_archived = cursor.fetchone()[0]

            return {"success": True, "archived": total_archived}

        except Exception as e:
            self.logger.exception("Manual archival failed: ")
            return {"success": False, "error": str(e)}

    async def get_status(self) -> dict[str, Any]:
        """Get gardener status"""
        return {
            "running": self._running,
            "consolidation_interval": self.consolidation_interval,
            "decay_rate": self.decay_rate,
            "energy_threshold": self.energy_threshold,
            "archive_days": self.archive_days,
        }
