# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Two-phase memory consolidation (Codex-inspired).

Phase 1 (Extract): Already handled by batch_extractor / real-time extractor.
Phase 2 (Merge):   This module — deduplicates, updates, and merges candidates
                   against the existing memory store using LLM reasoning.

When no LLM is available, falls back to exact dedup only.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone

from dawei.core.datetime_compat import UTC
from dawei.memory.memory_graph import MemoryEntry, MemoryGraph, MemoryType

logger = logging.getLogger(__name__)


class MemoryConsolidator:
    """Merge new memory candidates with existing memories.

    Usage:
        consolidator = MemoryConsolidator(memory_graph, llm_provider)
        result = await consolidator.consolidate(candidates)
        # result = {"added": 3, "updated": 1, "skipped": 2}
    """

    def __init__(
        self,
        memory_graph: MemoryGraph,
        llm_provider=None,
    ):
        self.graph = memory_graph
        self.llm = llm_provider

    async def _call_llm(self, prompt: str, max_tokens: int = 500, temperature: float = 0.3) -> str:
        """Call LLM and return text content, handling both interface variants.

        Supports:
        - process_message(messages=...) → {"content": str}  (agent.py style)
        - generate(messages=...) → ChatResult with .content  (batch_extractor style)

        Returns empty string on any failure.
        """
        if not self.llm:
            return ""

        messages = [{"role": "user", "content": prompt}]
        try:
            # Try process_message first (standard interface)
            if hasattr(self.llm, "process_message"):
                resp = await self.llm.process_message(
                    messages=messages, max_tokens=max_tokens, temperature=temperature,
                )
                if isinstance(resp, dict):
                    return resp.get("content", "") or ""
                if hasattr(resp, "content"):
                    return resp.content or ""
                if hasattr(resp, "text"):
                    return resp.text or ""

            # Fall back to generate (batch_extractor/gardener style)
            if hasattr(self.llm, "generate"):
                resp = await self.llm.generate(
                    messages=messages, max_tokens=max_tokens, temperature=temperature,
                )
                if hasattr(resp, "content"):
                    return resp.content or ""
                if isinstance(resp, dict):
                    return resp.get("content", "") or ""
                if hasattr(resp, "text"):
                    return resp.text or ""

        except Exception as e:
            logger.debug(f"LLM call failed: {e}")

        return ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def consolidate(self, candidates: list[MemoryEntry]) -> dict:
        """Merge candidates into the memory graph.

        Returns:
            {"added": int, "updated": int, "skipped": int}
        """
        if not candidates:
            return {"added": 0, "updated": 0, "skipped": 0}

        stats = {"added": 0, "updated": 0, "skipped": 0}

        # --- Phase 0: cheap exact dedup (no LLM) ---
        unique: list[MemoryEntry] = []
        batch_seen: set[str] = set()  # dedup within same batch
        for mem in candidates:
            # Check against DB + within-batch
            triple_key = f"{mem.subject.lower()}|{mem.predicate.lower()}|{mem.object.lower()}"
            if triple_key in batch_seen or await self._is_exact_duplicate(mem):
                stats["skipped"] += 1
                logger.debug(f"Skip exact duplicate: {mem.subject} {mem.predicate} {mem.object}")
            else:
                unique.append(mem)
                batch_seen.add(triple_key)

        if not unique:
            return stats

        # --- Phase 1: LLM-driven merge (if LLM available) ---
        if self.llm:
            try:
                merge_stats = await self._llm_merge(unique)
                stats["added"] += merge_stats["added"]
                stats["updated"] += merge_stats["updated"]
                stats["skipped"] += merge_stats["skipped"]
            except Exception as e:
                logger.warning(f"LLM merge failed, falling back to direct add: {e}")
                # Fallback — add all unique candidates
                for mem in unique:
                    await self.graph.add_memory(mem)
                    stats["added"] += 1
        else:
            # No LLM — add all unique candidates
            for mem in unique:
                await self.graph.add_memory(mem)
                stats["added"] += 1

        # --- Phase 2: Refresh rolling summary (if anything changed) ---
        if self.llm and (stats["added"] > 0 or stats["updated"] > 0):
            try:
                summary = await self.generate_summary()
                if summary:
                    await self.graph.save_summary(summary)
            except Exception as e:
                logger.debug(f"Summary refresh skipped: {e}")

        return stats

    # ------------------------------------------------------------------
    # Internal: exact dedup
    # ------------------------------------------------------------------

    async def _is_exact_duplicate(self, mem: MemoryEntry) -> bool:
        """Check if (subject, predicate, object) already exists (case-insensitive)."""
        try:
            with sqlite3.connect(self.graph.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT 1 FROM memory_graph
                    WHERE LOWER(subject) = ? AND LOWER(predicate) = ? AND LOWER(object) = ?
                    LIMIT 1
                    """,
                    (mem.subject.lower(), mem.predicate.lower(), mem.object.lower()),
                )
                return cursor.fetchone() is not None
        except sqlite3.Error:
            return False

    # ------------------------------------------------------------------
    # Internal: LLM-driven merge
    # ------------------------------------------------------------------

    async def _llm_merge(self, candidates: list[MemoryEntry]) -> dict:
        """Use LLM to decide ADD / UPDATE / SKIP for each candidate."""
        stats = {"added": 0, "updated": 0, "skipped": 0}

        # Group candidates by normalized subject for batch processing
        groups: dict[str, list[tuple[int, MemoryEntry]]] = {}
        for idx, mem in enumerate(candidates):
            key = mem.subject.strip().lower()
            groups.setdefault(key, []).append((idx, mem))

        for subject_key, group_items in groups.items():
            # Fetch existing memories with same subject
            existing = await self._fetch_by_subject(subject_key)

            # Build LLM prompt
            prompt = self._build_merge_prompt(group_items, existing)
            raw = await self._call_llm(prompt, max_tokens=800, temperature=0.1)

            if not raw:
                # LLM failed — just add all
                for _, mem in group_items:
                    await self.graph.add_memory(mem)
                    stats["added"] += 1
                continue

            # Parse LLM decisions
            decisions = self._parse_decisions(raw)

            if not decisions:
                # Unparseable — add all
                for _, mem in group_items:
                    await self.graph.add_memory(mem)
                    stats["added"] += 1
                continue

            # Apply decisions
            existing_map = {e.id: e for e in existing}
            for decision in decisions:
                idx = decision.get("index")
                action = decision.get("action", "ADD").upper()

                # Find the candidate by group-local index
                match = None
                for gi, mem in group_items:
                    if gi == idx:
                        match = mem
                        break

                if not match:
                    continue

                if action == "SKIP":
                    stats["skipped"] += 1
                    logger.debug(f"LLM SKIP: {match.subject} {match.predicate} {match.object}")

                elif action == "UPDATE":
                    existing_id = decision.get("existing_id")
                    new_object = decision.get("new_object", match.object)
                    if existing_id and existing_id in existing_map:
                        await self.graph.delete_memory(existing_id)
                    match.object = new_object
                    await self.graph.add_memory(match)
                    stats["updated"] += 1
                    logger.debug(f"LLM UPDATE: {match.subject} → {new_object}")

                else:  # ADD
                    await self.graph.add_memory(match)
                    stats["added"] += 1

        return stats

    async def _fetch_by_subject(self, subject: str) -> list[MemoryEntry]:
        """Fetch all memories matching subject (case-insensitive)."""
        try:
            with sqlite3.connect(self.graph.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT * FROM memory_graph
                    WHERE LOWER(subject) = ?
                    ORDER BY created_at DESC
                    LIMIT 20
                    """,
                    (subject.lower(),),
                )
                rows = cursor.fetchall()
                return [self.graph._row_to_memory(row) for row in rows]
        except sqlite3.Error:
            return []

    def _build_merge_prompt(
        self,
        candidates: list[tuple[int, MemoryEntry]],
        existing: list[MemoryEntry],
    ) -> str:
        """Build the LLM merge prompt."""
        lines_existing = []
        for i, mem in enumerate(existing):
            lines_existing.append(
                f"[E{i}] id={mem.id}  {mem.subject} {mem.predicate} {mem.object}"
            )

        lines_new = []
        for idx, mem in candidates:
            lines_new.append(
                f"[N{idx}]  {mem.subject} {mem.predicate} {mem.object}"
            )

        return f"""你是一个记忆合并系统。对于每条新记忆，判断是新增、更新还是跳过。

现有记忆（同一主体）：
{chr(10).join(lines_existing) if lines_existing else "(无)"}

新记忆候选：
{chr(10).join(lines_new)}

规则：
- ADD: 新信息，现有记忆中没有
- UPDATE: 更新了现有记忆中的旧信息（例如偏好改变）。提供 existing_id 和 new_object
- SKIP: 与现有记忆完全重复

请用 JSON 数组回答，每个元素：
{{"index": <候选编号>, "action": "ADD"|"UPDATE"|"SKIP", "existing_id": "<现有记忆ID，UPDATE时需要>", "new_object": "<新值，UPDATE时需要>"}}

只输出 JSON，不要其他文字。"""

    def _parse_decisions(self, raw: str) -> list[dict]:
        """Parse LLM JSON response into decision list."""
        import re

        # Extract JSON array from response
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return []

        try:
            decisions = json.loads(match.group())
            if isinstance(decisions, list):
                return decisions
        except json.JSONDecodeError:
            pass

        return []

    # ------------------------------------------------------------------
    # Summary generation
    # ------------------------------------------------------------------

    async def generate_summary(self, max_memories: int = 50) -> str:
        """Generate a rolling natural-language summary of the memory store.

        This is always injected into agent context first (before search results).
        Returns empty string if LLM unavailable or no memories.
        """
        if not self.llm:
            return ""

        # Fetch high-energy memories
        try:
            with sqlite3.connect(self.graph.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT subject, predicate, object, memory_type, energy
                    FROM memory_graph
                    WHERE energy > 0.1
                    ORDER BY energy DESC, access_count DESC
                    LIMIT ?
                    """,
                    (max_memories,),
                )
                rows = cursor.fetchall()
        except sqlite3.Error:
            return ""

        if not rows:
            return ""

        memory_lines = [
            f"- {row['subject']} {row['predicate']} {row['object']}"
            for row in rows
        ]

        prompt = f"""将以下记忆条目总结为3-5句关键信息，按重要性排列。
重点关注：用户偏好、工作习惯、项目技术栈。

记忆条目：
{chr(10).join(memory_lines)}

摘要（直接输出，不要前言）："""

        try:
            raw = await self._call_llm(prompt, max_tokens=300, temperature=0.3)
            if raw:
                return raw.strip()
        except Exception as e:
            logger.warning(f"Summary generation failed: {e}")

        return ""
