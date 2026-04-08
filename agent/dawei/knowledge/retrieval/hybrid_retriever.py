# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Hybrid retrieval combining vector, graph, and full-text search"""

import logging
import math
import time
from typing import List, Dict

from dawei.knowledge.base.fulltext_store import FullTextStore
from dawei.knowledge.base.graph_store import GraphStore
from dawei.knowledge.base.vector_store import VectorStore
from dawei.knowledge.embeddings.manager import EmbeddingManager
from dawei.knowledge.models import (
    GraphEntity,
    GraphRelation,
    RetrievalMode,
    RetrievalQuery,
    RetrievalResult,
    HybridSearchResult,
)

logger = logging.getLogger(__name__)


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two vectors"""
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class HybridRetriever:
    """Hybrid retrieval system combining multiple search methods

    Features:
    - Vector search (semantic similarity)
    - Graph search (knowledge graph traversal)
    - Full-text search (keyword matching)
    - Reciprocal Rank Fusion (RRF) for result ranking
    """

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        graph_store: GraphStore | None = None,
        fulltext_store: FullTextStore | None = None,
        embedding_manager: EmbeddingManager | None = None,
    ):
        """Initialize hybrid retriever

        Args:
            vector_store: Vector search implementation
            graph_store: Knowledge graph implementation
            fulltext_store: Full-text search implementation
            embedding_manager: Embedding model manager
        """
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.fulltext_store = fulltext_store
        self.embedding_manager = embedding_manager

    async def retrieve(self, query: RetrievalQuery) -> HybridSearchResult:
        """Retrieve documents using hybrid search

        Args:
            query: Retrieval query configuration

        Returns:
            Hybrid search results
        """
        start_time = time.time()

        # Determine which search methods to use
        use_vector = query.mode in [RetrievalMode.VECTOR, RetrievalMode.HYBRID] and self.vector_store is not None
        use_graph = query.mode in [RetrievalMode.GRAPH, RetrievalMode.HYBRID] and self.graph_store is not None
        use_fulltext = query.mode in [RetrievalMode.FULLTEXT, RetrievalMode.HYBRID] and self.fulltext_store is not None

        # Execute searches
        vector_results: List[RetrievalResult] = []
        graph_results: List[RetrievalResult] = []
        fulltext_results: List[RetrievalResult] = []

        if use_vector:
            vector_results = await self._vector_search(query)

        if use_graph:
            graph_results = await self._graph_search(query)

        if use_fulltext:
            fulltext_results = await self._fulltext_search(query)

        # Combine results using RRF
        if query.mode == RetrievalMode.HYBRID:
            combined_results = self._reciprocal_rank_fusion(
                vector_results=vector_results,
                graph_results=graph_results,
                fulltext_results=fulltext_results,
                vector_weight=query.vector_weight,
                graph_weight=query.graph_weight,
                fulltext_weight=query.fulltext_weight,
            )
        else:
            # Single mode: return results from that mode
            if use_vector:
                combined_results = vector_results
            elif use_graph:
                combined_results = graph_results
            elif use_fulltext:
                combined_results = fulltext_results
            else:
                combined_results = []

        # Apply min_score filter
        combined_results = [r for r in combined_results if r.score >= query.min_score]

        # Limit to top_k
        combined_results = combined_results[: query.top_k]

        latency_ms = (time.time() - start_time) * 1000

        return HybridSearchResult(
            query=query.query,
            results=combined_results,
            total_count=len(combined_results),
            vector_count=len(vector_results),
            graph_count=len(graph_results),
            fulltext_count=len(fulltext_results),
            latency_ms=latency_ms,
            reranked=query.mode == RetrievalMode.HYBRID,
        )

    async def _vector_search(self, query: RetrievalQuery) -> List[RetrievalResult]:
        """Perform vector similarity search

        Args:
            query: Retrieval query

        Returns:
            List of vector search results
        """
        if not self.embedding_manager or not self.vector_store:
            return []

        try:
            # Generate query embedding
            query_embedding = await self.embedding_manager.embed_single(query.query)

            # Search vector store
            vector_results = await self.vector_store.search(
                query_embedding=query_embedding,
                top_k=query.top_k,
                filters=query.filters,
                min_score=query.min_score,
            )

            # Convert to RetrievalResult
            return [
                RetrievalResult(
                    id=result.id,
                    content=result.content,
                    score=result.score,
                    source="vector",
                    metadata=result.metadata,
                )
                for result in vector_results
            ]

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    async def _graph_search(self, query: RetrievalQuery) -> List[RetrievalResult]:
        """Perform knowledge graph search with full traversal

        Strategy:
        1. Find seed entities via embedding-enhanced search
        2. Expand to neighbors with hop-distance decay
        3. Collect relation context for each entity
        4. Apply filters and scoring

        Args:
            query: Retrieval query

        Returns:
            List of graph search results
        """
        if not self.graph_store:
            logger.debug("Graph store not initialized, skipping graph search")
            return []

        try:
            # 1. Find seed entities
            entity_ids = await self._extract_entities(query)
            if not entity_ids:
                logger.debug(f"No entities found for query: {query.query}")
                return []

            entity_type_filter = query.filters.get("entity_type") if query.filters else None
            base_id_filter = query.filters.get("base_id") if query.filters else None
            max_hops = query.filters.get("max_hops", 2) if query.filters else 2

            results: List[RetrievalResult] = []
            seen_ids: set[str] = set()

            for entity_id in entity_ids:
                entity = await self.graph_store.get_entity(entity_id)
                if not entity:
                    continue

                # Apply filters
                if entity_type_filter and entity.type != entity_type_filter:
                    continue
                if base_id_filter and entity.base_id != base_id_filter:
                    continue

                # Get all relations for this seed entity (once, reused below)
                seed_relations = await self.graph_store.get_relations(
                    entity_id=entity_id, direction="both"
                )

                # 2. Add the entity itself as result (distance=0)
                if entity.id not in seen_ids:
                    seen_ids.add(entity.id)
                    score = await self._calculate_graph_relevance(entity, query.query)
                    content = self._build_entity_content(entity, seed_relations)
                    results.append(
                        RetrievalResult(
                            id=entity.id,
                            content=content,
                            score=score,
                            source="graph",
                            metadata={
                                "entity_id": entity.id,
                                "entity_type": entity.type,
                                "entity_name": entity.name,
                                "hop_distance": 0,
                                **entity.properties,
                            },
                        )
                    )

                # 3. Get 1-hop and 2-hop neighbors separately for accurate hop tracking
                hop1_neighbors = await self.graph_store.find_neighbors(
                    entity_id=entity_id, hops=1,
                )
                hop2_neighbors = (
                    await self.graph_store.find_neighbors(entity_id=entity_id, hops=2)
                    if max_hops >= 2 else []
                )
                # Diff: 2-hop minus 1-hop = pure 2-hop entities
                hop1_ids = {n.id for n in hop1_neighbors}
                hop2_only = [n for n in hop2_neighbors if n.id not in hop1_ids]

                for hop, neighbor_group in [(1, hop1_neighbors), (2, hop2_only)]:
                    for neighbor in neighbor_group:
                        if neighbor.id in seen_ids:
                            continue

                        # Apply filters
                        if entity_type_filter and neighbor.type != entity_type_filter:
                            continue
                        if base_id_filter and neighbor.base_id != base_id_filter:
                            continue

                        seen_ids.add(neighbor.id)

                        # Filter relations involving this neighbor
                        related_rels = [
                            r for r in seed_relations
                            if r.from_entity == neighbor.id or r.to_entity == neighbor.id
                        ]
                        content = self._build_entity_content(neighbor, related_rels)

                        # Score with hop-distance decay
                        relevance = await self._calculate_graph_relevance(neighbor, query.query)
                        score = relevance * (0.9 ** hop)

                        results.append(
                            RetrievalResult(
                                id=neighbor.id,
                                content=content,
                                score=score,
                                source="graph",
                                metadata={
                                    "entity_id": neighbor.id,
                                    "entity_type": neighbor.type,
                                    "entity_name": neighbor.name,
                                    "hop_distance": hop,
                                    **neighbor.properties,
                                },
                            )
                        )

            # Sort by score and limit
            results.sort(key=lambda x: x.score, reverse=True)

            logger.info(
                f"Graph search: {len(entity_ids)} seeds → {len(results)} results"
            )
            return results[: query.top_k]

        except Exception as e:
            logger.error(f"Graph search failed: {e}", exc_info=True)
            return []

    async def _fulltext_search(self, query: RetrievalQuery) -> List[RetrievalResult]:
        """Perform full-text search

        Args:
            query: Retrieval query

        Returns:
            List of full-text search results
        """
        if not self.fulltext_store:
            return []

        try:
            # Search full-text index
            results = await self.fulltext_store.search(
                query=query.query,
                top_k=query.top_k,
                filters=query.filters,
            )

            # Convert to RetrievalResult
            retrieval_results = []

            for chunk_id, score in results:
                chunk = await self.fulltext_store.get_chunk(chunk_id)

                if chunk:
                    retrieval_results.append(
                        RetrievalResult(
                            id=chunk.id,
                            content=chunk.content,
                            score=score,
                            source="fulltext",
                            metadata=chunk.metadata,
                        )
                    )

            return retrieval_results

        except Exception as e:
            logger.error(f"Full-text search failed: {e}")
            return []

    def _reciprocal_rank_fusion(
        self,
        vector_results: List[RetrievalResult],
        graph_results: List[RetrievalResult],
        fulltext_results: List[RetrievalResult],
        vector_weight: float = 0.5,
        graph_weight: float = 0.3,
        fulltext_weight: float = 0.2,
        k: int = 60,
    ) -> List[RetrievalResult]:
        """Combine results using Reciprocal Rank Fusion (RRF)

        Args:
            vector_results: Vector search results
            graph_results: Graph search results
            fulltext_results: Full-text search results
            vector_weight: Weight for vector results
            graph_weight: Weight for graph results
            fulltext_weight: Weight for full-text results
            k: RRF constant (default 60)

        Returns:
            Fused and ranked results
        """
        # Score dictionaries: {result_id: score}
        rrf_scores: Dict[str, float] = {}
        result_map: Dict[str, RetrievalResult] = {}

        # Process vector results
        for rank, result in enumerate(vector_results, start=1):
            rrf_score = vector_weight / (k + rank)
            rrf_scores[result.id] = rrf_scores.get(result.id, 0) + rrf_score
            result_map[result.id] = result

        # Process graph results
        for rank, result in enumerate(graph_results, start=1):
            rrf_score = graph_weight / (k + rank)
            rrf_scores[result.id] = rrf_scores.get(result.id, 0) + rrf_score
            result_map[result.id] = result

        # Process fulltext results
        for rank, result in enumerate(fulltext_results, start=1):
            rrf_score = fulltext_weight / (k + rank)
            rrf_scores[result.id] = rrf_scores.get(result.id, 0) + rrf_score
            result_map[result.id] = result

        # Sort by RRF score
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        # Return sorted results
        return [
            RetrievalResult(
                id=result_id,
                content=result_map[result_id].content,
                score=rrf_scores[result_id],
                source="hybrid",
                metadata=result_map[result_id].metadata,
            )
            for result_id in sorted_ids
        ]

    async def _extract_entities(self, query: str) -> List[str]:
        """Find relevant entity IDs from graph using text search + embedding ranking

        Strategy:
        1. search_entities by LIKE matching (fast, broad recall)
        2. Re-rank candidates by embedding cosine similarity (precision)
        3. Return top entity IDs

        Args:
            query: Search query text

        Returns:
            List of entity IDs ranked by relevance
        """
        if not self.graph_store:
            return []

        # Step 1: broad text search
        entity_matches = await self.graph_store.search_entities(
            query=query,
            limit=20,  # over-fetch for re-ranking
        )

        if not entity_matches:
            return []

        # Step 2: re-rank by embedding similarity if available
        if self.embedding_manager:
            try:
                query_embedding = await self.embedding_manager.embed_single(query)

                scored: list[tuple[str, float]] = []
                for entity_id, _like_score in entity_matches:
                    entity = await self.graph_store.get_entity(entity_id)
                    if not entity:
                        continue

                    # Embed entity text (name + description)
                    entity_text = f"{entity.name}. {entity.description or ''}"
                    entity_embedding = await self.embedding_manager.embed_single(entity_text)
                    sim = _cosine_similarity(query_embedding, entity_embedding)

                    # Blend: 40% LIKE match + 60% embedding similarity
                    blended = 0.4 * _like_score + 0.6 * max(sim, 0.0)
                    scored.append((entity_id, blended))

                scored.sort(key=lambda x: x[1], reverse=True)
                return [eid for eid, _s in scored[:10]]

            except Exception as e:
                logger.warning(f"Embedding re-ranking failed, using LIKE order: {e}")

        # Fallback: use LIKE order
        return [eid for eid, _s in entity_matches[:10]]

    async def _calculate_graph_relevance(self, entity: GraphEntity, query: str) -> float:
        """Calculate relevance score combining text matching and embedding similarity

        Args:
            entity: Graph entity
            query: Search query

        Returns:
            Relevance score in [0, 1]
        """
        text_score = self._text_relevance(entity, query)

        # Boost with embedding similarity if available
        if self.embedding_manager:
            try:
                query_emb = await self.embedding_manager.embed_single(query)
                entity_text = f"{entity.name}. {entity.description or ''}"
                entity_emb = await self.embedding_manager.embed_single(entity_text)
                sim = _cosine_similarity(query_emb, entity_emb)
                # Blend: 50% text + 50% embedding
                return 0.5 * text_score + 0.5 * max(sim, 0.0)
            except Exception:
                pass

        return text_score

    def _text_relevance(self, entity: GraphEntity, query: str) -> float:
        """Pure text-based relevance: exact/contains/overlap matching

        Supports both space-separated (English) and character-level (CJK) matching.

        Args:
            entity: Graph entity
            query: Search query

        Returns:
            Text relevance score in [0, 1]
        """
        query_lower = query.lower().strip()
        name_lower = (entity.name or "").lower().strip()
        desc_lower = (entity.description or "").lower().strip()

        # Exact name match
        if query_lower == name_lower:
            return 1.0

        # Name contains query or vice versa
        if name_lower and (query_lower in name_lower or name_lower in query_lower):
            return 0.85

        # Description contains query
        if desc_lower and query_lower in desc_lower:
            return 0.75

        # Token overlap (space-separated words)
        query_words = set(query_lower.split())
        name_words = set(name_lower.split()) if name_lower else set()
        desc_words = set(desc_lower.split()) if desc_lower else set()
        all_entity_words = name_words | desc_words

        if query_words and all_entity_words:
            overlap = len(query_words & all_entity_words)
            if overlap > 0:
                return 0.3 + 0.5 * (overlap / max(len(query_words), len(all_entity_words)))

        # CJK: character-level n-gram overlap for Chinese/Japanese/Korean
        if any('\u4e00' <= c <= '\u9fff' for c in query_lower):
            query_chars = set(query_lower)
            entity_chars = set(name_lower + desc_lower)
            char_overlap = len(query_chars & entity_chars)
            if char_overlap > 0:
                return 0.2 + 0.4 * (char_overlap / max(len(query_chars), len(entity_chars)))

        # Base score for entities found via search_entities (they already matched LIKE)
        return 0.3

    def _build_entity_content(self, entity: GraphEntity, relations: List[GraphRelation]) -> str:
        """Build human-readable content string for an entity with relation context

        Args:
            entity: Graph entity
            relations: Relations involving this entity

        Returns:
            Formatted content string
        """
        parts: list[str] = []

        # Entity header
        header = f"[{entity.type}] {entity.name}"
        if entity.description:
            header += f": {entity.description}"
        parts.append(header)

        # Key properties (skip internal ones)
        _skip_keys = {"content", "description", "confidence", "source", "source_documents", "source_chunks", "source_pages"}
        props = {k: v for k, v in entity.properties.items() if k not in _skip_keys and v}
        if props:
            prop_str = ", ".join(f"{k}={v}" for k, v in list(props.items())[:5])
            parts.append(f"  Properties: {prop_str}")

        # Relation context
        if relations:
            rel_lines = []
            for r in relations[:8]:  # limit to keep concise
                if r.from_entity == entity.id:
                    rel_lines.append(f"  → [{r.relation_type}] → {r.to_entity}")
                else:
                    rel_lines.append(f"  ← [{r.relation_type}] ← {r.from_entity}")
            if rel_lines:
                parts.append("Relations:\n" + "\n".join(rel_lines))

        # Source document provenance
        source_docs = entity.properties.get("source_documents", [])
        source_pages = entity.properties.get("source_pages", [])
        if source_docs:
            source_info = f"Source: doc_id={source_docs[0]}"
            if source_pages:
                source_info += f", page={source_pages[0]}"
            parts.append(source_info)

        return "\n".join(parts)
