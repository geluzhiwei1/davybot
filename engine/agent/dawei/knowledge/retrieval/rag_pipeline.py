# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""RAG Pipeline for retrieval-augmented generation"""

import logging
from typing import List, Dict, Any

from dawei.knowledge.embeddings.manager import EmbeddingService
from dawei.knowledge.models import RetrievalQuery, HybridSearchResult
from dawei.knowledge.retrieval.hybrid_retriever import HybridRetriever

logger = logging.getLogger(__name__)


class RAGPipeline:
    """RAG pipeline for retrieval-augmented generation

    Features:
    - Document retrieval from multiple sources
    - Context building for LLM prompts
    - Query reformulation
    - Citation and attribution
    """

    def __init__(
        self,
        retriever: HybridRetriever,
        embedding_service: EmbeddingService,
    ):
        """Initialize RAG pipeline

        Args:
            retriever: Hybrid retriever instance
            embedding_service: Embedding service instance
        """
        self.retriever = retriever
        self.embedding_service = embedding_service

    async def retrieve_and_build_context(
        self,
        query: str,
        top_k: int = 5,
        mode: str = "hybrid",
        max_context_length: int = 4000,
    ) -> Dict[str, Any]:
        """Retrieve relevant documents and build context

        Args:
            query: User query
            top_k: Number of documents to retrieve
            mode: Retrieval mode ("vector", "graph", "fulltext", "hybrid")
            max_context_length: Maximum context length in characters

        Returns:
            Dictionary containing:
                - context: Formatted context string
                - sources: List of source documents
                - citations: Citation information
        """
        # Create retrieval query
        retrieval_query = RetrievalQuery(
            query=query,
            mode=mode,  # type: ignore
            top_k=top_k,
        )

        # Retrieve documents
        search_results = await self.retriever.retrieve(retrieval_query)

        # Build context
        context = self._build_context(search_results, max_context_length)

        # Extract sources and citations
        sources = self._extract_sources(search_results)
        citations = self._build_citations(search_results)

        return {
            "context": context,
            "sources": sources,
            "citations": citations,
            "metadata": {
                "total_results": search_results.total_count,
                "vector_count": search_results.vector_count,
                "graph_count": search_results.graph_count,
                "fulltext_count": search_results.fulltext_count,
                "latency_ms": search_results.latency_ms,
            },
        }

    def _build_context(
        self,
        search_results: HybridSearchResult,
        max_length: int,
    ) -> str:
        """Build context string from search results

        Args:
            search_results: Hybrid search results
            max_length: Maximum context length

        Returns:
            Formatted context string
        """
        context_parts = []
        current_length = 0

        for i, result in enumerate(search_results.results, start=1):
            # Format document
            doc_part = f"[Document {i}] (Score: {result.score:.3f})\n{result.content}\n\n"

            # Check if adding this would exceed max length
            if current_length + len(doc_part) > max_length:
                # Truncate last document if needed
                remaining = max_length - current_length
                if remaining > 100:  # Only add if we have meaningful space
                    truncated = doc_part[:remaining] + "..."
                    context_parts.append(truncated)
                break

            context_parts.append(doc_part)
            current_length += len(doc_part)

        return "".join(context_parts)

    def _extract_sources(self, search_results: HybridSearchResult) -> List[Dict[str, Any]]:
        """Extract source information

        Args:
            search_results: Hybrid search results

        Returns:
            List of source dictionaries
        """
        sources = []

        for result in search_results.results:
            source = {
                "id": result.id,
                "score": result.score,
                "source_type": result.source,
            }

            # Add metadata fields
            metadata = result.metadata

            if "file_name" in metadata:
                source["file_name"] = metadata["file_name"]
            if "file_path" in metadata:
                source["file_path"] = metadata["file_path"]
            if "title" in metadata:
                source["title"] = metadata["title"]
            if "author" in metadata:
                source["author"] = metadata["author"]
            if "chunk_index" is not None:
                source["chunk_index"] = metadata.get("chunk_index")

            sources.append(source)

        return sources

    def _build_citations(self, search_results: HybridSearchResult) -> List[str]:
        """Build citation strings

        Args:
            search_results: Hybrid search results

        Returns:
            List of citation strings
        """
        citations = []

        for i, result in enumerate(search_results.results, start=1):
            metadata = result.metadata

            # Build citation
            parts = []

            if "title" in metadata:
                parts.append(f'"{metadata["title"]}"')

            if "author" in metadata:
                parts.append(f"by {metadata['author']}")

            if "file_name" in metadata:
                parts.append(f"in {metadata['file_name']}")

            citation = f"[{i}] " + ", ".join(parts) if parts else f"[{i}] {result.id}"
            citations.append(citation)

        return citations

    async def query_with_context(
        self,
        query: str,
        system_prompt: str | None = None,
        max_context_length: int = 4000,
    ) -> Dict[str, Any]:
        """Prepare query with context for LLM

        Args:
            query: User query
            system_prompt: Optional system prompt
            max_context_length: Maximum context length

        Returns:
            Dictionary with prompt and context information
        """
        # Retrieve and build context
        context_data = await self.retrieve_and_build_context(
            query=query,
            top_k=5,
            mode="hybrid",
            max_context_length=max_context_length,
        )

        # Build prompt
        prompt = self._build_rag_prompt(
            query=query,
            context=context_data["context"],
            citations=context_data["citations"],
            system_prompt=system_prompt,
        )

        return {
            "prompt": prompt,
            "context": context_data["context"],
            "sources": context_data["sources"],
            "citations": context_data["citations"],
            "metadata": context_data["metadata"],
        }

    def _build_rag_prompt(
        self,
        query: str,
        context: str,
        citations: List[str],
        system_prompt: str | None = None,
    ) -> str:
        """Build RAG prompt for LLM

        Args:
            query: User query
            context: Retrieved context
            citations: Citation strings
            system_prompt: Optional system prompt

        Returns:
            Formatted prompt
        """
        # Default system prompt
        if system_prompt is None:
            system_prompt = """You are a helpful AI assistant. Use the provided context to answer questions accurately.
When referencing information from the context, include citations."""

        # Build prompt
        prompt = f"""{system_prompt}

## Context

{context}

## Citations

{chr(10).join(citations)}

## Question

{query}

## Answer

"""

        return prompt

    async def retrieve_similar_queries(
        self,
        query: str,
        num_queries: int = 3,
    ) -> List[str]:
        """Generate similar queries for better retrieval

        Args:
            query: Original query
            num_queries: Number of similar queries to generate

        Returns:
            List of similar queries
        """
        # Simplified implementation
        # In production, use LLM to generate query variations

        query_variations = [
            query,  # Original query
            query.replace("?", ""),  # Without question mark
            query.replace("how to", "how do I"),  # Alternative phrasing
        ]

        return query_variations[:num_queries]

    async def multi_query_retrieval(
        self,
        query: str,
        top_k: int = 5,
        num_queries: int = 3,
    ) -> Dict[str, Any]:
        """Perform retrieval with multiple query variations

        Args:
            query: Original query
            top_k: Results per query
            num_queries: Number of query variations

        Returns:
            Combined retrieval results
        """
        # Generate query variations
        queries = await self.retrieve_similar_queries(query, num_queries)

        # Retrieve for each query
        all_results = []

        for q in queries:
            retrieval_query = RetrievalQuery(
                query=q,
                mode="hybrid",  # type: ignore
                top_k=top_k,
            )

            results = await self.retriever.retrieve(retrieval_query)
            all_results.append(results)

        # Merge and deduplicate results
        merged_results = self._merge_results(all_results)

        return merged_results

    def _merge_results(
        self,
        all_results: List[HybridSearchResult],
    ) -> Dict[str, Any]:
        """Merge results from multiple queries

        Args:
            all_results: List of search results

        Returns:
            Merged results
        """
        # Collect all unique results
        seen_ids = set()
        merged = []

        for results in all_results:
            for result in results.results:
                if result.id not in seen_ids:
                    merged.append(result)
                    seen_ids.add(result.id)

        # Sort by score
        merged.sort(key=lambda x: x.score, reverse=True)

        return {
            "results": merged[:10],  # Top 10
            "total_unique": len(merged),
        }
