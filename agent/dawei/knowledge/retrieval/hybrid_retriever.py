# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Hybrid retrieval combining vector, graph, and full-text search"""

import logging
import time
from typing import List, Dict, Any

from dawei.knowledge.base.fulltext_store import FullTextStore
from dawei.knowledge.base.graph_store import GraphStore
from dawei.knowledge.base.vector_store import VectorStore
from dawei.knowledge.embeddings.manager import EmbeddingManager
from dawei.knowledge.models import (
    GraphEntity,
    GraphRelation,
    GraphPath,
    RetrievalMode,
    RetrievalQuery,
    RetrievalResult,
    HybridSearchResult,
)

logger = logging.getLogger(__name__)


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
        """Perform knowledge graph search

        Args:
            query: Retrieval query

        Returns:
            List of graph search results
        """
        if not self.graph_store:
            return []

        try:
            # Extract entities from query (simplified)
            # In production, use NER to extract entities
            entities = self._extract_entities(query.query)

            results = []

            for entity in entities:
                # Find neighbors
                neighbors = await self.graph_store.find_neighbors(
                    entity_id=entity,
                    hops=2,
                )

                # Convert to RetrievalResult
                for neighbor in neighbors:
                    # Score based on proximity and relevance
                    score = self._calculate_graph_relevance(neighbor, query.query)

                    results.append(
                        RetrievalResult(
                            id=neighbor.id,
                            content=neighbor.properties.get("content", neighbor.name),
                            score=score,
                            source="graph",
                            metadata=neighbor.properties,
                        )
                    )

            # Sort by score
            results.sort(key=lambda x: x.score, reverse=True)

            return results[: query.top_k]

        except Exception as e:
            logger.error(f"Graph search failed: {e}")
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

    def _extract_entities(self, query: str) -> List[str]:
        """Extract entities from query (simplified)

        In production, use NER model or regex patterns.
        """
        # Simplified: extract capitalized words
        import re

        words = re.findall(r"\b[A-Z][a-z]+\b", query)
        return list(set(words))

    def _calculate_graph_relevance(self, entity: GraphEntity, query: str) -> float:
        """Calculate relevance score for graph entity

        Args:
            entity: Graph entity
            query: Search query

        Returns:
            Relevance score
        """
        # Simplified: calculate overlap between query and entity name
        query_lower = query.lower()
        entity_lower = entity.name.lower()

        # Exact match
        if query_lower == entity_lower:
            return 1.0

        # Contains match
        if entity_lower in query_lower or query_lower in entity_lower:
            return 0.8

        # Token overlap
        query_words = set(query_lower.split())
        entity_words = set(entity_lower.split())

        overlap = len(query_words & entity_words)
        if overlap > 0:
            return overlap / max(len(query_words), len(entity_words))

        return 0.3  # Base score for graph entities
