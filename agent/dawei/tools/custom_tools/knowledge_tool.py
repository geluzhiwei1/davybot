# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Knowledge base search tool for Agent integration"""

import logging
from typing import List, Dict, Any

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.tools.custom_base_tool import CustomBaseTool

logger = logging.getLogger(__name__)


class KnowledgeSearchInput(BaseModel):
    """Knowledge search tool input schema"""

    query: str = Field(
        ...,
        description="Search query for knowledge base",
    )
    mode: str = Field(
        default="hybrid",
        description="Retrieval mode: vector, graph, fulltext, or hybrid",
    )
    top_k: int = Field(
        default=5,
        description="Number of results to return",
    )


class KnowledgeSearchTool(CustomBaseTool):
    """Knowledge base search tool - Agent calls this tool to access RAG system

    This tool allows the Agent to search the knowledge base for relevant information
    to enhance its responses with domain-specific knowledge and document citations.
    """

    def __init__(self, knowledge_base_id: str = None):
        """Initialize knowledge search tool

        Args:
            knowledge_base_id: Knowledge base ID to search
        """
        super().__init__()
        self.name = "search_knowledge"
        self.description = (
            "Search the knowledge base for relevant information. "
            "Use this tool when you need to find documents, "
            "look up specific information, or get context for a task. "
            "Returns relevant document chunks with similarity scores and citations."
        )
        self.args_schema = KnowledgeSearchInput
        self.knowledge_base_id = knowledge_base_id

    @safe_tool_operation(
        "knowledge_search",
        fallback_value="Error: Knowledge search failed",
    )
    async def _run(self, query: str, mode: str = "hybrid", top_k: int = 5) -> str:
        """Execute knowledge search

        Args:
            query: Search query string
            mode: Retrieval mode (vector/graph/fulltext/hybrid)
            top_k: Number of results to return

        Returns:
            Formatted search results with citations in markdown format
        """
        try:
            from dawei.knowledge.models import RetrievalMode, RetrievalQuery
            from dawei.knowledge.init import get_knowledge_base_manager

            # Validate and convert mode string to enum
            try:
                mode_enum = RetrievalMode(mode)
            except ValueError:
                valid_modes = [m.value for m in RetrievalMode]
                return f"Error: Invalid retrieval mode '{mode}'. Valid modes: {', '.join(valid_modes)}"

            # Check if knowledge_base_id is available
            if self.knowledge_base_id is None:
                return "Error: Knowledge base is not configured. Please enable knowledge base in configuration."

            # Get knowledge base manager and search
            manager = get_knowledge_base_manager()

            # Get vector store and embedding manager for this knowledge base
            from dawei.knowledge.retrieval.hybrid_retriever import HybridRetriever

            # Get embedding manager
            embedding_service = manager.get_embedding_manager(self.knowledge_base_id, "MINILM")

            # Get vector store
            base_storage_path = manager.get_base_storage_path(self.knowledge_base_id)
            from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore
            vector_store = SQLiteVecVectorStore(
                db_path=str(base_storage_path / "vectors.db"),
                dimension=384,
            )

            # Initialize retriever
            retriever = HybridRetriever(
                vector_store=vector_store,
                embedding_manager=embedding_service,
            )

            # Execute search
            retrieval_query = RetrievalQuery(
                query=query,
                mode=mode_enum,
                top_k=top_k,
            )
            results = await retriever.retrieve(retrieval_query)

            # Format and return results
            return self._format_results(results, query)

        except Exception as e:
            logger.error(f"Knowledge search failed: {e}", exc_info=True)
            return f"Error: Failed to search knowledge base - {str(e)}"

    def _format_results(
        self,
        results: List[Any],
        query: str,
    ) -> str:
        """Format search results for Agent consumption

        Args:
            results: List of search results
            query: Original query string

        Returns:
            Formatted markdown text
        """
        if not results:
            return f"## Knowledge Search Results\n\nNo relevant information found in knowledge base for query: '{query}'"

        lines = [
            f"## Knowledge Base Search Results",
            f"**Query:** {query}",
            f"**Found:** {len(results)} relevant documents",
            "",
            "---",
            "",
        ]

        for i, result in enumerate(results, 1):
            # Extract score
            score = getattr(result, 'score', 0.0)
            source = getattr(result, 'source', 'UNKNOWN')
            content = getattr(result, 'content', '')
            metadata = getattr(result, 'metadata', {})

            lines.append(f"### Result {i}")
            lines.append(f"**Score:** {score:.2%}")
            lines.append(f"**Source:** {source.upper()}")

            # Add metadata
            if "file_name" in metadata:
                lines.append(f"**File:** {metadata['file_name']}")
            if "chunk_index" in metadata:
                lines.append(f"**Chunk:** {metadata['chunk_index']}")
            if "file_type" in metadata:
                lines.append(f"**Type:** {metadata['file_type']}")

            lines.append("")
            lines.append("**Content:**")
            lines.append("```")

            # Truncate content if too long
            max_content_length = 500
            if len(content) > max_content_length:
                content = content[:max_content_length] + "..."

            lines.append(content)
            lines.append("```")
            lines.append("")

        return "\n".join(lines)


class KnowledgeRAGInput(BaseModel):
    """Knowledge RAG query input schema"""

    query: str = Field(
        ...,
        description="Query for RAG-enhanced generation",
    )
    max_context_length: int = Field(
        default=4000,
        description="Maximum context length in characters",
    )


class KnowledgeRAGTool(CustomBaseTool):
    """Knowledge RAG tool - Get context-enhanced query with citations

    This tool retrieves relevant documents and builds a complete RAG context
    for LLM prompt enhancement.
    """

    def __init__(self, knowledge_base_id: str = None):
        """Initialize knowledge RAG tool

        Args:
            knowledge_base_id: Knowledge base ID to query
        """
        super().__init__()
        self.name = "query_knowledge_rag"
        self.description = (
            "Query knowledge base with RAG (Retrieval-Augmented Generation). "
            "Retrieves relevant documents and builds enhanced context with citations. "
            "Use this when you need comprehensive context for answering complex questions."
        )
        self.args_schema = KnowledgeRAGInput
        self.knowledge_base_id = knowledge_base_id

    @safe_tool_operation(
        "knowledge_rag",
        fallback_value="Error: RAG query failed",
    )
    async def _run(self, query: str, max_context_length: int = 4000) -> str:
        """Execute RAG query

        Args:
            query: Query string
            max_context_length: Maximum context length

        Returns:
            Formatted RAG context with citations
        """
        try:
            from dawei.knowledge.init import get_knowledge_base_manager
            from dawei.knowledge.retrieval.rag_pipeline import RAGPipeline

            if self.knowledge_base_id is None:
                return "Error: Knowledge base is not configured."

            # Get knowledge base manager
            manager = get_knowledge_base_manager()

            # Get embedding manager and vector store
            embedding_service = manager.get_embedding_manager(self.knowledge_base_id, "MINILM")
            base_storage_path = manager.get_base_storage_path(self.knowledge_base_id)

            from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore
            from dawei.knowledge.retrieval.hybrid_retriever import HybridRetriever

            vector_store = SQLiteVecVectorStore(
                db_path=str(base_storage_path / "vectors.db"),
                dimension=384,
            )

            # Initialize retriever and RAG pipeline
            retriever = HybridRetriever(
                vector_store=vector_store,
                embedding_manager=embedding_service,
            )

            rag_pipeline = RAGPipeline(
                retriever=retriever,
                embedding_service=embedding_service,
            )

            # Query with context
            result = await rag_pipeline.query_with_context(
                query=query,
                max_context_length=max_context_length,
            )

            # Format results
            return self._format_rag_result(result, query)

        except Exception as e:
            logger.error(f"RAG query failed: {e}", exc_info=True)
            return f"Error: RAG query failed - {str(e)}"

    def _format_rag_result(self, result: Dict[str, Any], query: str) -> str:
        """Format RAG result

        Args:
            result: RAG query result
            query: Original query

        Returns:
            Formatted RAG context
        """
        lines = [
            f"## RAG-Enhanced Knowledge Context",
            f"**Query:** {query}",
            "",
            "---",
            "",
        ]

        # Add context
        if "context" in result:
            lines.append("### Retrieved Context")
            lines.append(result["context"])
            lines.append("")

        # Add citations
        if "citations" in result and result["citations"]:
            lines.append("### Citations")
            for i, citation in enumerate(result["citations"], 1):
                lines.append(f"{i}. {citation}")
            lines.append("")

        # Add metadata
        if "metadata" in result:
            metadata = result["metadata"]
            lines.append("### Retrieval Metadata")
            lines.append(f"- Total Results: {metadata.get('total_results', 0)}")
            lines.append(f"- Vector Results: {metadata.get('vector_count', 0)}")
            lines.append(f"- Graph Results: {metadata.get('graph_count', 0)}")
            lines.append(f"- Fulltext Results: {metadata.get('fulltext_count', 0)}")
            lines.append(f"- Latency: {metadata.get('latency_ms', 0)}ms")
            lines.append("")

        return "\n".join(lines)
