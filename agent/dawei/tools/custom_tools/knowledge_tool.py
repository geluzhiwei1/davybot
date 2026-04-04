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
    knowledge_base_ids: List[str] = Field(
        default_factory=list,
        description="List of knowledge base IDs to search. If not specified, uses the agent's default knowledge base.",
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
    """User knowledge base search tool - Agent calls this tool to search user-created knowledge bases

    This tool allows the Agent to search the user's own knowledge bases for relevant information
    to enhance its responses with domain-specific knowledge and document citations.
    """

    def __init__(self):
        """Initialize user knowledge base search tool"""
        super().__init__()
        self.name = "search_user_knowledge_base"
        self.description = (
            "Search the user's knowledge base for relevant documents and information. "
            "This tool searches through documents that the user has uploaded to their knowledge base. "
            "Use this when you need to find specific documents, look up information from user's content, "
            "or browse document chunks with similarity scores. "
            "Returns a list of relevant document chunks with citations, sorted by relevance."
        )
        self.args_schema = KnowledgeSearchInput

        # 🔧 修复：添加 knowledge_base_id 属性，支持注入
        self.knowledge_base_id = None
        self.knowledge_base_ids = []  # 支持多个知识库 ID

    @safe_tool_operation(
        "knowledge_search",
        fallback_value="Error: Knowledge search failed",
    )
    async def _run(
        self,
        query: str,
        knowledge_base_ids: List[str] = None,
        mode: str = "hybrid",
        top_k: int = 5,
    ) -> str:
        """Execute knowledge search

        Args:
            query: Search query string
            knowledge_base_ids: List of knowledge base IDs to search (optional, overrides injected IDs)
            mode: Retrieval mode (vector/graph/fulltext/hybrid)
            top_k: Number of results to return

        Returns:
            Formatted search results with citations in markdown format
        """
        try:
            from dawei.knowledge.models import RetrievalMode, RetrievalQuery
            from dawei.knowledge.init import get_knowledge_base_manager

            # 🔧 修复：优先使用注入的 knowledge_base_ids，然后是参数，最后是默认值
            # 1. 如果参数明确指定了 knowledge_base_ids，使用参数
            # 2. 否则，如果注入了 knowledge_base_ids，使用注入的
            # 3. 最后，使用默认知识库
            if not knowledge_base_ids:
                if self.knowledge_base_ids and len(self.knowledge_base_ids) > 0:
                    knowledge_base_ids = self.knowledge_base_ids
                    self.logger.info(f"[KnowledgeSearchTool] Using injected knowledge_base_ids: {knowledge_base_ids}")
                elif self.knowledge_base_id:
                    knowledge_base_ids = [self.knowledge_base_id]
                    self.logger.info(f"[KnowledgeSearchTool] Using injected single knowledge_base_id: {knowledge_base_ids}")
                else:
                    # 使用默认知识库
                    manager = get_knowledge_base_manager()
                    default_base = manager.get_default_base()
                    if default_base:
                        knowledge_base_ids = [default_base.id]
                        self.logger.info(f"[KnowledgeSearchTool] Using default knowledge_base_id: {knowledge_base_ids}")
                    else:
                        return "Error: No knowledge base specified and no default knowledge base found."

            self.logger.info(f"[KnowledgeSearchTool] Searching knowledge bases: {knowledge_base_ids}")

            # Validate and convert mode string to enum
            try:
                mode_enum = RetrievalMode(mode)
            except ValueError:
                valid_modes = [m.value for m in RetrievalMode]
                return f"Error: Invalid retrieval mode '{mode}'. Valid modes: {', '.join(valid_modes)}"

            # Get knowledge base manager
            manager = get_knowledge_base_manager()

            # Search all selected knowledge bases and merge results
            all_results = []
            for kb_id in knowledge_base_ids:
                try:
                    # Get embedding manager
                    embedding_service = manager.get_embedding_manager(kb_id)

                    # Get vector store
                    base_storage_path = manager.get_base_storage_path(kb_id)
                    from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore

                    vector_store = SQLiteVecVectorStore(
                        db_path=str(base_storage_path / "vectors.db"),
                        dimension=384,
                    )

                    # Initialize retriever
                    from dawei.knowledge.retrieval.hybrid_retriever import HybridRetriever

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

                    # Add knowledge base info to results
                    for result in results.results:
                        result.metadata["knowledge_base_id"] = kb_id
                        result.metadata["knowledge_base_name"] = manager.get_base(kb_id).name if manager.get_base(kb_id) else kb_id

                    all_results.extend(results.results)
                except Exception as e:
                    logger.warning(f"Failed to search knowledge base {kb_id}: {e}")
                    continue

            if not all_results:
                return f"## Knowledge Search Results\n\nNo relevant information found in selected knowledge bases for query: '{query}'"

            # Sort by score and take top_k
            all_results.sort(key=lambda x: x.score, reverse=True)
            all_results = all_results[:top_k]

            # Format and return results
            return self._format_results(all_results, query)

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
            score = getattr(result, "score", 0.0)
            source = getattr(result, "source", "UNKNOWN")
            content = getattr(result, "content", "")
            metadata = getattr(result, "metadata", {})

            lines.append(f"### Result {i}")
            lines.append(f"**Score:** {score:.2%}")
            lines.append(f"**Source:** {source.upper()}")

            # Add metadata
            if "file_name" in metadata:
                lines.append(f"**File:** {metadata['file_name']}")
            if "page_number" in metadata:
                lines.append(f"**Page:** {metadata['page_number']}")
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
    knowledge_base_id: str = Field(
        default=None,
        description="Knowledge base ID to query. If not specified, uses the agent's default knowledge base.",
    )
    max_context_length: int = Field(
        default=4000,
        description="Maximum context length in characters",
    )


class KnowledgeRAGTool(CustomBaseTool):
    """User knowledge base RAG tool - Get context-enhanced query with citations from user's knowledge bases

    This tool retrieves relevant documents from the user's own knowledge bases and builds
    a complete RAG context for LLM prompt enhancement.
    """

    def __init__(self):
        """Initialize user knowledge base RAG tool"""
        super().__init__()
        self.name = "query_user_knowledge_base"
        self.description = (
            "Query the user's knowledge base to get enhanced context with citations. "
            "This tool retrieves relevant documents from the user's knowledge base and builds "
            "a comprehensive context with proper citations for answering questions. "
            "Use this when you need detailed context from user's documents to answer complex questions. "
            "Returns integrated context with citations and retrieval metadata."
        )
        self.args_schema = KnowledgeRAGInput

        # 🔧 修复：添加 knowledge_base_id 属性，支持注入
        self.knowledge_base_id = None
        self.knowledge_base_ids = []  # 支持多个知识库 ID

    @safe_tool_operation(
        "knowledge_rag",
        fallback_value="Error: RAG query failed",
    )
    async def _run(
        self,
        query: str,
        knowledge_base_id: str = None,
        max_context_length: int = 4000,
    ) -> str:
        """Execute RAG query

        Args:
            query: Query string
            knowledge_base_id: Knowledge base ID to query (optional, overrides injected IDs)
            max_context_length: Maximum context length

        Returns:
            Formatted RAG context with citations
        """
        try:
            from dawei.knowledge.init import get_knowledge_base_manager
            from dawei.knowledge.retrieval.rag_pipeline import RAGPipeline

            # 🔧 修复：优先使用注入的 knowledge_base_ids，然后是参数，最后是默认值
            # 1. 如果参数明确指定了 knowledge_base_id，使用参数
            # 2. 否则，如果注入了 knowledge_base_ids，使用第一个
            # 3. 最后，使用默认知识库
            if not knowledge_base_id:
                if self.knowledge_base_ids and len(self.knowledge_base_ids) > 0:
                    knowledge_base_id = self.knowledge_base_ids[0]
                    self.logger.info(f"[KnowledgeRAGTool] Using injected knowledge_base_id: {knowledge_base_id}")
                elif self.knowledge_base_id:
                    knowledge_base_id = self.knowledge_base_id
                    self.logger.info(f"[KnowledgeRAGTool] Using injected single knowledge_base_id: {knowledge_base_id}")
                else:
                    # 使用默认知识库
                    manager = get_knowledge_base_manager()
                    default_base = manager.get_default_base()
                    if default_base:
                        knowledge_base_id = default_base.id
                        self.logger.info(f"[KnowledgeRAGTool] Using default knowledge_base_id: {knowledge_base_id}")
                    else:
                        return "Error: No knowledge base specified and no default knowledge base found."

            self.logger.info(f"[KnowledgeRAGTool] Querying knowledge base: {knowledge_base_id}")

            # Get knowledge base manager
            manager = get_knowledge_base_manager()

            # Get embedding manager and vector store
            embedding_service = manager.get_embedding_manager(knowledge_base_id)
            base_storage_path = manager.get_base_storage_path(knowledge_base_id)

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
