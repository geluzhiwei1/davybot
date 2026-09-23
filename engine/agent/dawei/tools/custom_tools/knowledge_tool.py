# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Knowledge base search tool for Agent integration"""

import logging
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from dawei.core.decorators import safe_tool_operation
from dawei.core import local_context
from dawei.tools.custom_base_tool import CustomBaseTool
from dawei.tools.custom_tools.async_utils import run_async
from dawei.tools.custom_tools._service_client import (
    AuthenticatedServiceClient,
    KB_SEARCHER_BASE_URL,
    ServiceAuthError,
    ServiceUnavailableError,
)

logger = logging.getLogger(__name__)


class KnowledgeSearchInput(BaseModel):
    """Knowledge search tool input schema"""

    query: str = Field(
        ...,
        description="Search query for knowledge base",
    )
    knowledge_base_ids: list[str] = Field(
        default_factory=list,
        description="List of knowledge base IDs to search. If not specified, uses injected IDs or the agent's default knowledge base.",
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
    def _run(
        self,
        query: str,
        knowledge_base_ids: list[str] = None,
        mode: str = "hybrid",
        top_k: int = 5,
    ) -> str:
        """Execute knowledge search (sync wrapper).

        Delegates to _async_run via run_async to keep _run synchronous
        as required by CustomBaseTool's interface contract.
        """
        return run_async(
            self._async_run(query, knowledge_base_ids, mode, top_k),
        )

    async def _async_run(
        self,
        query: str,
        knowledge_base_ids: list[str] = None,
        mode: str = "hybrid",
        top_k: int = 5,
    ) -> str:
        """Execute knowledge search (async implementation).

        Args:
            query: Search query string
            knowledge_base_ids: List of knowledge base IDs to search (optional, overrides injected IDs)
            mode: Retrieval mode (vector/graph/fulltext/hybrid)
            top_k: Number of results to return

        Returns:
            Formatted search results with citations in markdown format
        """
        try:
            from dawei.knowledge.init import get_knowledge_base_manager
            from dawei.knowledge.models import RetrievalMode, RetrievalQuery

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

                    # Get knowledge base config for embedding dimension
                    kb_obj = manager.get_base(kb_id)
                    if not kb_obj:
                        self.logger.warning(f"Knowledge base not found: {kb_id}, skipping")
                        continue

                    # Get vector store
                    base_storage_path = manager.get_base_storage_path(kb_id)
                    from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore

                    vector_store = SQLiteVecVectorStore(
                        db_path=str(base_storage_path / "vectors.db"),
                        dimension=kb_obj.settings.embedding_dimension,
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
        results: list[Any],
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
            "## Knowledge Base Search Results",
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
        description="Knowledge base ID to query. If not specified, uses injected IDs or the agent's default knowledge base.",
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
    def _run(
        self,
        query: str,
        knowledge_base_id: str = None,
        max_context_length: int = 4000,
    ) -> str:
        """Execute RAG query (sync wrapper).

        Delegates to _async_run via run_async to keep _run synchronous
        as required by CustomBaseTool's interface contract.
        """
        return run_async(
            self._async_run(query, knowledge_base_id, max_context_length),
        )

    async def _async_run(
        self,
        query: str,
        knowledge_base_id: str = None,
        max_context_length: int = 4000,
    ) -> str:
        """Execute RAG query (async implementation).

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
            kb_obj = manager.get_base(knowledge_base_id)
            if not kb_obj:
                return f"Error: Knowledge base '{knowledge_base_id}' not found."
            embedding_service = manager.get_embedding_manager(knowledge_base_id)
            base_storage_path = manager.get_base_storage_path(knowledge_base_id)

            from dawei.knowledge.retrieval.hybrid_retriever import HybridRetriever
            from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore

            vector_store = SQLiteVecVectorStore(
                db_path=str(base_storage_path / "vectors.db"),
                dimension=kb_obj.settings.embedding_dimension,
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

    def _format_rag_result(self, result: dict[str, Any], query: str) -> str:
        """Format RAG result

        Args:
            result: RAG query result
            query: Original query

        Returns:
            Formatted RAG context
        """
        lines = [
            "## RAG-Enhanced Knowledge Context",
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


# ============================================================================
# nn-kb-searcher Legal Search Tools (PRD §3.7 — MCP integration)
# ============================================================================

import json

# Authenticated client for nn-kb-searcher legal-ext API.
# Multi-tenant: JWT is injected per-request from local_context (never into LLM).
# API is mounted at {base}/api/v1/legal/* — existing tools call with paths
# relative to /api/v1/legal, so the client base includes that prefix.
_LEGAL_API_BASE = f"{KB_SEARCHER_BASE_URL}/api/v1/legal"
_legal_client = AuthenticatedServiceClient(_LEGAL_API_BASE, service_name="kb-searcher", timeout=20.0)


async def _call_kb_searcher(method: str, path: str, *, json_data: dict = None, params: dict = None, timeout: float = 15.0) -> dict:
    """Call nn-kb-searcher legal-ext API with the current user's JWT injected.

    Returns parsed JSON response body, or {"error": ...} on failure (preserves
    the existing contract used by callers).
    """
    try:
        if method.upper() == "GET":
            return await _legal_client.get(path, params=params, timeout=timeout)
        return await _legal_client.post(path, json_body=json_data, timeout=timeout)
    except ServiceAuthError as e:
        return {"error": "AUTH", "detail": str(e)}
    except ServiceUnavailableError as e:
        return {"error": "UNAVAILABLE", "detail": str(e)}
    except Exception as e:
        return {"error": f"nn-kb-searcher call failed: {e}"}


class LegalSearchInput(BaseModel):
    """Input schema for nn-kb-searcher legal document search."""

    query: str = Field(..., description="Search query — natural language, legal citation, or keywords")
    mode: str = Field("hybrid", description="Search mode: hybrid, keyword, vector, graph, field")
    doc_type: str | None = Field(None, description="Document type: NORMATIVE, CASE, PATENT, STANDARD, ENTERPRISE, EXPERT_KNOWLEDGE, AUXILIARY")
    sub_type: str | None = Field(None, description="Document sub-type, e.g. LAW, REG_ADMIN, CASE_GUIDE, PATENT_INVENTION")
    legal_domain: str | None = Field(None, description="Legal domain, e.g. civil, criminal, administrative, commerce, labor")
    jurisdiction: str | None = Field(None, description="Jurisdiction code, e.g. CN, CN-Beijing, US, EU")
    status: str | None = Field(None, description="Document status: EFFECTIVE, AMENDED, REPEALED, EXPIRED")
    top_k: int = Field(10, ge=1, le=50, description="Number of results to return")
    use_graph: bool = Field(True, description="Include knowledge graph context in results")
    kb_ids: list[str] | None = Field(
        None,
        description="限定检索的知识库 ID 列表（多租户按用户可见库）。省略=跨全部可用库（广撒网，结果带 kb_id 溯源）。"
        "用 list_legal_knowledge_bases 查看可用库及其类别/描述来决定选哪些。",
    )


class LegalSearchTool(CustomBaseTool):
    """Search legal documents via nn-kb-searcher.

    This tool calls nn-kb-searcher's advanced search API with 7-dimension
    taxonomy filtering and multiple search modes. Use this for legal document
    retrieval, law lookups, case searches, patent searches, and more.
    """

    def __init__(self):
        super().__init__()
        self.name = "search_legal_knowledge"
        self.description = (
            "Search the legal knowledge base for laws, regulations, cases, patents, standards, "
            "and other legal documents. Supports 7 filter dimensions (doc_type, sub_type, "
            "legal_domain, jurisdiction, status, authority, industry) and 5 search modes "
            "(hybrid, keyword, vector, graph, field). "
            "Returns ranked results with scores, metadata, and source citations."
        )
        self.args_schema = LegalSearchInput

    @safe_tool_operation("legal_search", fallback_value="Error: Legal search failed")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(
        self,
        query: str,
        mode: str = "hybrid",
        doc_type: str | None = None,
        sub_type: str | None = None,
        legal_domain: str | None = None,
        jurisdiction: str | None = None,
        status: str | None = None,
        top_k: int = 10,
        use_graph: bool = True,
        kb_ids: list[str] | None = None,
    ) -> str:
        filters: dict[str, Any] = {}
        if doc_type:
            filters["doc_type"] = doc_type
        if sub_type:
            filters["sub_type"] = sub_type
        if legal_domain:
            filters["legal_domain"] = legal_domain
        if jurisdiction:
            filters["jurisdiction"] = jurisdiction
        if status:
            filters["status"] = status

        body: dict[str, Any] = {
            "query": query,
            "mode": mode,
            "filters": filters,
            "top_k": top_k,
            "use_graph": use_graph,
        }
        if kb_ids:
            body["kb_ids"] = kb_ids

        result = await _call_kb_searcher("POST", "/search", json_data=body, timeout=15.0)

        if "error" in result:
            return f"Error: {result['error']}" + (f" — {str(result.get('detail'))[:300]}" if result.get("detail") else "")

        results = result.get("results", [])
        total = result.get("total", 0)
        intent = result.get("intent", "")

        if not results:
            return f"## Legal Search Results\n\nNo legal documents found for: '{query}'"

        lines = [
            "## Legal Knowledge Search Results",
            f"**Query:** {query}",
            f"**Mode:** {mode}",
            f"**Total:** {total} documents found",
        ]
        if intent:
            lines.append(f"**Intent:** {intent}")
        lines.extend(["", "---", ""])

        for i, doc in enumerate(results[:top_k], 1):
            title = doc.get("title") or doc.get("name") or "Untitled"
            doc_type_val = doc.get("doc_type", "")
            sub_type_val = doc.get("sub_type", "")
            jurisd = doc.get("jurisdiction", "")
            stat = doc.get("status", "")
            score = doc.get("fused_score") or doc.get("score") or 0
            authority = doc.get("issuing_authority") or doc.get("authority") or ""
            content = doc.get("content", "")
            source = doc.get("source", "")
            source_url = doc.get("source_url", "")
            effective_date = doc.get("effective_date", "")

            lines.append(f"### {i}. {title}")
            lines.append(f"**Score:** {score:.2%}")
            if doc_type_val:
                lines.append(f"**Type:** {doc_type_val}/{sub_type_val}" if sub_type_val else f"**Type:** {doc_type_val}")
            if jurisd:
                lines.append(f"**Jurisdiction:** {jurisd}")
            if stat:
                lines.append(f"**Status:** {stat}")
            if authority:
                lines.append(f"**Authority:** {authority}")
            if effective_date:
                lines.append(f"**Effective:** {effective_date}")
            if source:
                lines.append(f"**Source:** {source}")
            if source_url:
                lines.append(f"**URL:** {source_url}")

            if content:
                preview = content[:500] + "..." if len(content) > 500 else content
                lines.append("")
                lines.append("**Content Preview:**")
                lines.append("```")
                lines.append(preview)
                lines.append("```")

            lines.append("")

        return "\n".join(lines)


class LegalAskInput(BaseModel):
    """Input schema for nn-kb-searcher RAG Q&A."""

    question: str = Field(..., description="Legal question in natural language")
    knowledge_base_id: str | None = Field(None, description="Limit to specific knowledge base ID")
    use_graph: bool = Field(True, description="Include knowledge graph context")


class LegalAskTool(CustomBaseTool):
    """Ask a legal question via nn-kb-searcher RAG pipeline.

    This tool sends a legal question to nn-kb-searcher's RAG Q&A endpoint,
    which retrieves relevant documents and generates a grounded answer with
    citations. Use this for legal consultation, compliance questions, and
    complex legal queries that need contextual answers.
    """

    def __init__(self):
        super().__init__()
        self.name = "ask_legal_question"
        self.description = (
            "Ask a legal question and get an AI-generated answer grounded in legal documents "
            "with citations. The system retrieves relevant laws, regulations, cases, and expert "
            "knowledge to provide accurate, source-backed answers. "
            "Returns the answer text with citation list."
        )
        self.args_schema = LegalAskInput

    @safe_tool_operation("legal_ask", fallback_value="Error: Legal Q&A failed")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(
        self,
        question: str,
        knowledge_base_id: str | None = None,
        use_graph: bool = True,
    ) -> str:
        payload: dict[str, Any] = {"question": question, "use_graph": use_graph}
        if knowledge_base_id:
            payload["kb_id"] = knowledge_base_id

        result = await _call_kb_searcher("POST", "/ask", json_data=payload, timeout=30.0)

        if "error" in result:
            return f"Error: {result['error']}" + (f" — {str(result.get('detail'))[:300]}" if result.get("detail") else "")

        answer = result.get("answer") or result.get("response") or "No answer available."
        citations = result.get("citations") or result.get("sources") or []

        lines = [
            "## Legal Q&A Answer",
            f"**Question:** {question}",
            "",
            answer,
            "",
        ]

        if citations:
            lines.append("### Citations")
            _MAX_CITES = 15  # inner-layer governance: cap citations
            for i, cite in enumerate(citations[:_MAX_CITES], 1):
                title = cite.get("title") or cite.get("name") or cite.get("id", "—")
                relevance = cite.get("relevance") or cite.get("score")
                if relevance is not None:
                    lines.append(f"{i}. {title} ({relevance:.0%})")
                else:
                    lines.append(f"{i}. {title}")
            if len(citations) > _MAX_CITES:
                lines.append(f"... 共 {len(citations)} 条引用，仅显示前 {_MAX_CITES} 条")
            lines.append("")

        return "\n".join(lines)


class LegalDocumentInput(BaseModel):
    """Input schema for getting a single legal document."""

    document_id: str = Field(..., description="Document ID to retrieve")
    include_chunks: bool = Field(False, description="Whether to include parsed document chunks")
    include_similar: bool = Field(False, description="Whether to include similar documents")


class LegalDocumentTool(CustomBaseTool):
    """Get detailed legal document metadata and content via nn-kb-searcher.

    This tool retrieves full document metadata including amendment history,
    version chain, citations, and optionally document chunks or similar documents.
    """

    def __init__(self):
        super().__init__()
        self.name = "get_legal_document"
        self.description = (
            "Get detailed metadata for a legal document by its ID. Returns document type, "
            "jurisdiction, status, authority, amendment history, citations, and optionally "
            "parsed chunks or similar documents. "
            "Use this after search to get full document details."
        )
        self.args_schema = LegalDocumentInput

    @safe_tool_operation("legal_document", fallback_value="Error: Document retrieval failed")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(
        self,
        document_id: str,
        include_chunks: bool = False,
        include_similar: bool = False,
    ) -> str:
        # Get metadata
        result = await _call_kb_searcher("GET", f"/documents/{document_id}/metadata")

        if "error" in result:
            return f"Error: {result['error']}" + (f" — {str(result.get('detail'))[:300]}" if result.get("detail") else "")

        lines = [
            "## Legal Document Detail",
            f"**ID:** {document_id}",
        ]

        # Core metadata
        for key, label in [
            ("title", "Title"), ("name", "Name"), ("doc_type", "Type"),
            ("sub_type", "Sub-type"), ("jurisdiction", "Jurisdiction"),
            ("status", "Status"), ("issuing_authority", "Authority"),
            ("authority", "Authority"), ("doc_number", "Document No."),
            ("promulgation_date", "Promulgated"), ("effective_date", "Effective"),
            ("expiry_date", "Expiry"), ("source_url", "Source URL"),
        ]:
            val = result.get(key)
            if val:
                lines.append(f"**{label}:** {val}")

        # Amendment chain
        amendments = result.get("amendments") or []
        if amendments:
            lines.append("")
            lines.append("### Amendment History")
            for a in amendments:
                lines.append(f"- {a.get('date', '?')}: {a.get('description', '—')}")

        # Versions
        versions = result.get("versions") or []
        if versions:
            lines.append("")
            lines.append("### Version History")
            for v in versions:
                lines.append(f"- {v.get('date', '?')}: {v.get('description', '—')}")

        # Cited by
        cited_by = result.get("cited_by") or []
        if cited_by:
            lines.append("")
            lines.append(f"### Cited By ({len(cited_by)} documents)")
            for c in cited_by[:10]:
                lines.append(f"- {c.get('title') or c.get('name', '—')}")

        # Chunks (optional)
        if include_chunks:
            chunks_result = await _call_kb_searcher("GET", f"/documents/{document_id}/chunks", params={"limit": 5})
            chunks = chunks_result.get("chunks") or []
            if chunks:
                lines.append("")
                lines.append(f"### Document Chunks ({len(chunks)} shown)")
                for i, chunk in enumerate(chunks, 1):
                    content = chunk.get("content", "")
                    preview = content[:300] + "..." if len(content) > 300 else content
                    lines.append(f"\n**Chunk {i}:**")
                    lines.append(preview)

        # Similar (optional)
        if include_similar:
            similar_result = await _call_kb_searcher("GET", f"/documents/{document_id}/similar", params={"top_k": 5})
            similar = similar_result.get("results") or []
            if similar:
                lines.append("")
                lines.append(f"### Similar Documents ({len(similar)} found)")
                for s in similar:
                    title = s.get("title") or s.get("name", "—")
                    score = s.get("score", 0)
                    lines.append(f"- {title} ({score:.0%})")

        lines.append("")
        return "\n".join(lines)


# ============================================================================
# 知识库发现 / catalog（多库路由前提，见 业务工具升级.md §4.1.0 / §5.6）
# ============================================================================


def _normalize_kb(item: dict) -> dict:
    """Robustly extract a compact KB descriptor from a discover/summary item of unknown shape."""
    if not isinstance(item, dict):
        return {}

    def _first(*keys: str) -> str:
        for k in keys:
            v = item.get(k)
            if isinstance(v, list):
                v = v[0] if v else ""
            if v:
                return str(v)
        return ""

    kb_id = item.get("kb_id") or item.get("id") or item.get("key") or item.get("slug")
    return {
        "kb_id": kb_id,
        "name": item.get("name") or item.get("title") or item.get("display_name") or kb_id,
        "category": _first("category", "type", "doc_type", "kb_type", "doc_types"),
        "domain": _first("legal_domain", "domain", "scope", "legal_domains"),
        "doc_count": item.get("doc_count") or item.get("document_count") or item.get("count") or 0,
        "description": (item.get("description") or item.get("desc") or "").strip(),
    }


async def _fetch_kb_items() -> list[dict]:
    """Fetch KB list; prefer /knowledge-bases/discover (richest), fall back to /knowledge-bases."""
    for path, key in (("/knowledge-bases/discover", "knowledge_bases"), ("/knowledge-bases", "items")):
        try:
            data = await _legal_client.get(path, timeout=15.0)
        except Exception:
            continue
        if isinstance(data, dict) and not data.get("_error"):
            items = data.get(key)
            if isinstance(items, list):
                return items
        elif isinstance(data, list):
            return data
    return []


async def get_legal_kb_catalog() -> list[dict]:
    """Fetch the user-visible knowledge-base catalog (for system-prompt injection).

    Multi-tenant: uses the current user's JWT. Returns a compact list of
    {kb_id, name, category, domain, doc_count, description}. New KBs appear
    automatically — no code change needed (see §4.1.0).
    """
    items = await _fetch_kb_items()
    catalog = [_normalize_kb(it) for it in items if isinstance(it, dict)]
    return [c for c in catalog if c.get("kb_id")]


async def get_legal_domains() -> list[dict]:
    """Fetch legal knowledge-graph domains (业务子方向，e.g. labor) with descriptions.

    Domains are a separate routing dimension (used via legal_domain filter /
    graph), surfaced alongside KBs so the agent can route business-subdomain
    questions (e.g. 海外劳务).
    """
    try:
        data = await _legal_client.get("/domains", timeout=15.0)
    except Exception:
        return []
    if isinstance(data, dict) and not data.get("_error"):
        items = data.get("items") or data.get("domains") or []
        if isinstance(items, list):
            out = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                name = it.get("name") or it.get("key")
                if name:
                    out.append({"name": name, "description": (it.get("description") or "").strip()})
            return out
    return []


async def render_legal_kb_catalog_text() -> str:
    """Compact catalog text (KBs + domains) for injecting into the system prompt."""
    catalog = await get_legal_kb_catalog()
    domains = await get_legal_domains()
    if not catalog and not domains:
        return ""
    lines = []
    if catalog:
        lines.append("可用法律知识库（检索用 kb_ids 限定；省略=跨全部库）：")
        for c in catalog:
            parts = [f"`{c['kb_id']}`", c["name"]]
            if c["category"]:
                parts.append(f"[{c['category']}]")
            if c["domain"]:
                parts.append(f"域={c['domain']}")
            if c["doc_count"]:
                parts.append(f"{c['doc_count']}篇")
            if c["description"]:
                parts.append(f"— {c['description'][:60]}")
            lines.append("- " + " ".join(parts))
    if domains:
        lines.append("\n业务子方向域（legal_domain 过滤 / 图谱检索）：")
        for d in domains:
            desc = f" — {d['description'][:60]}" if d["description"] else ""
            lines.append(f"- `{d['name']}`{desc}")
    return "\n".join(lines)


# ── 缓存版 catalog（供 system prompt 注入，按用户 JWT 缓存，TTL 10 分钟）──
import time as _time

_CATALOG_CACHE: dict[str, tuple[float, str]] = {}
_CATALOG_TTL = 600.0


def get_cached_legal_kb_catalog_text() -> str:
    """Sync, per-user TTL-cached catalog text for system-prompt injection (§5.6).

    Cache key = current user JWT. On hit: instant dict lookup. On miss: fetches
    via run_async (which propagates the auth_token contextvar to the worker thread).
    Returns "" if no JWT or fetch fails — never blocks the prompt with an error.
    """
    token = local_context.get_auth_token()
    if not token:
        return ""
    now = _time.time()
    cached = _CATALOG_CACHE.get(token)
    if cached and (now - cached[0]) < _CATALOG_TTL:
        return cached[1]
    try:
        text = run_async(render_legal_kb_catalog_text())
    except Exception as e:
        logger.warning(f"legal KB catalog fetch failed (non-fatal): {e}")
        text = ""
    if text:
        _CATALOG_CACHE[token] = (now, text)
        if len(_CATALOG_CACHE) > 200:  # bound cache size
            oldest = min(_CATALOG_CACHE, key=lambda k: _CATALOG_CACHE[k][0])
            _CATALOG_CACHE.pop(oldest, None)
    return text


class LegalKnowledgeBasesInput(BaseModel):
    refresh: bool = Field(
        False,
        description="强制刷新缓存（新增库后看不到时用）。默认返回缓存catalog。",
    )


class LegalKnowledgeBasesTool(CustomBaseTool):
    """List available legal knowledge bases (the routing catalog).

    kb-searcher 是多知识库的（法律条文/判例/标准/模板/业务子方向库，持续新增）。
    本工具返回当前用户可见的库清单（id/名称/类别/描述），供决定检索时选哪些 kb_ids。
    """

    def __init__(self):
        super().__init__()
        self.name = "list_legal_knowledge_bases"
        self.description = (
            "列出可用的法律知识库与业务子方向域（条文/判例/标准/模板/海外劳务等）。"
            "检索前用它了解有哪些库、各自类别与描述，从而决定 search_legal_knowledge 的 kb_ids 选哪些。"
            "不确定查哪个库时：先跨库检索（kb_ids 省略），再按命中的 kb_id 收窄。"
        )
        self.args_schema = LegalKnowledgeBasesInput

    @safe_tool_operation("list_legal_knowledge_bases", fallback_value="Error: 列出知识库失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, refresh: bool = False) -> str:
        catalog = await get_legal_kb_catalog()
        domains = await get_legal_domains()
        if not catalog and not domains:
            return (
                "⚠️ 暂时无法获取知识库清单（服务不可达或认证失败，请确认已登录）。"
                "可先直接用 search_legal_knowledge 跨库检索。"
            )
        lines = []
        if catalog:
            _MAX_KB_DISPLAY = 30  # inner-layer governance: cap KB listing
            total_kb = len(catalog)
            display = catalog[:_MAX_KB_DISPLAY]
            lines.append(f"## 可用法律知识库（共 {total_kb} 个）\n")
            for c in display:
                parts = [f"- **`{c['kb_id']}`** — {c['name']}"]
                if c["category"]:
                    parts.append(f"`{c['category']}`")
                if c["domain"]:
                    parts.append(f"域:{c['domain']}")
                if c["doc_count"]:
                    parts.append(f"({c['doc_count']} 篇)")
                lines.append(" ".join(parts))
                if c["description"]:
                    lines.append(f"    {c['description']}")
            if total_kb > _MAX_KB_DISPLAY:
                lines.append(f"\n> ⚠️ 仅显示前 {_MAX_KB_DISPLAY} 个库（共 {total_kb} 个），使用检索可缩小范围。")
            lines.append("\n> 检索时把这些 id 传给 `search_legal_knowledge` 的 `kb_ids`；省略则跨全部库。")
        if domains:
            lines.append(f"\n## 业务子方向域（legal_domain 过滤 / 图谱，共 {len(domains)} 个）\n")
            for d in domains:
                desc = f" — {d['description']}" if d["description"] else ""
                lines.append(f"- **`{d['name']}`**{desc}")
        return "\n".join(lines)


# ============================================================================
# 补充法律工具（§4.1.1）：分面 / 图谱 / 分析 / 时间线
# ============================================================================


class LegalSearchFacetsInput(BaseModel):
    query: str = Field(..., description="检索词")
    fields: list[str] | None = Field(None, description="要聚合的分面字段，如 doc_type/jurisdiction/legal_domain/authority；省略=全部")
    doc_type: str | None = Field(None)
    jurisdiction: str | None = Field(None)
    legal_domain: str | None = Field(None)


class LegalSearchFacetsTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "legal_search_facets"
        self.description = (
            "对法律文献做分面聚合（按类型/管辖/领域/发文机关等统计计数），用于了解某个主题的文献分布，"
            "或决定 search_legal_knowledge 该用哪些过滤值。"
        )
        self.args_schema = LegalSearchFacetsInput

    @safe_tool_operation("legal_search_facets", fallback_value="Error: 分面聚合失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, query: str, fields: list[str] | None = None, doc_type: str | None = None,
                         jurisdiction: str | None = None, legal_domain: str | None = None) -> str:
        filters: dict[str, Any] = {}
        if doc_type:
            filters["doc_type"] = doc_type
        if jurisdiction:
            filters["jurisdiction"] = jurisdiction
        if legal_domain:
            filters["legal_domain"] = legal_domain
        body = {"query": query, "filters": filters}
        if fields:
            body["fields"] = fields
        result = await _call_kb_searcher("POST", "/search/facets", json_data=body, timeout=20)
        if "error" in result:
            return f"Error: {result['error']}" + (f" — {str(result.get('detail'))[:300]}" if result.get("detail") else "")
        facets = result.get("facets") or result.get("aggregations") or result
        if not isinstance(facets, dict):
            return "（无分面数据）"
        lines = [f"## 分面聚合：'{query}'\n"]
        for field, buckets in facets.items():
            if not isinstance(buckets, list):
                continue
            top = buckets[:10]
            entries = ", ".join(f"{b.get('value', b.get('key', '?'))}={b.get('count', b.get('doc_count', 0))}" for b in top if isinstance(b, dict))
            lines.append(f"- **{field}**: {entries}")
        return "\n".join(lines) if len(lines) > 1 else "（无分面数据）"


class LegalGraphSearchInput(BaseModel):
    query: str = Field(..., description="实体/概念/关系检索词")
    entity_type: str | None = Field(None, description="实体类型过滤，如 Law/Article/Case/Concept")
    limit: int = Field(10, ge=1, le=30)


class LegalGraphSearchTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "legal_graph_search"
        self.description = (
            "在法律知识图谱中检索实体/概念及其关系（法条-案例-概念关联）。"
            "用于关系挖掘、概念溯源，区别于文档全文检索 search_legal_knowledge。"
        )
        self.args_schema = LegalGraphSearchInput

    @safe_tool_operation("legal_graph_search", fallback_value="Error: 图谱检索失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, query: str, entity_type: str | None = None, limit: int = 10) -> str:
        params: dict[str, Any] = {"q": query, "limit": limit}
        if entity_type:
            params["entity_type"] = entity_type
        result = await _call_kb_searcher("GET", "/graph/entities", params=params, timeout=20)
        if "error" in result:
            return f"Error: {result['error']}" + (f" — {str(result.get('detail'))[:300]}" if result.get("detail") else "")
        items = result.get("entities") or result.get("items") or result.get("results") or []
        if not items:
            return f"图谱中未找到 '{query}' 相关实体。"
        total = len(items)
        lines = [f"## 法律图谱检索：'{query}'（{total} 条）\n"]
        # Inner-layer governance: consistent with list_max_items=20
        _MAX_RENDER = 20
        for i, e in enumerate(items[:_MAX_RENDER], 1):
            name = e.get("name") or e.get("caption") or e.get("label", "?")
            etype = e.get("type") or e.get("entity_type", "")
            rels = e.get("relations") or e.get("relationships") or []
            line = f"{i}. **{name}**"
            if etype:
                line += f" ({etype})"
            if rels:
                line += f" — 关联 {len(rels)}"
            lines.append(line)
        if total > _MAX_RENDER:
            lines.append(f"\n---\n显示 {_MAX_RENDER}/{total} 条。缩小查询范围查看更多。")
        return "\n".join(lines)


class LegalAnalyticsInput(BaseModel):
    metric: str = Field(
        ...,
        description="分析维度：trend(监管趋势)/lifecycle(生命周期)/jurisdiction_heatmap(管辖热力)/top_authorities(高频发文机关)",
    )
    doc_type: str | None = Field(None, description="限定文书类型")
    jurisdiction: str | None = Field(None)
    legal_domain: str | None = Field(None)
    limit: int = Field(10, ge=1, le=30)


class LegalAnalyticsTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "legal_analytics"
        self.description = (
            "法律文献统计分析：监管趋势(regulatory trend)、文书生命周期分布、管辖热力图、高频发文机关。"
            "用于宏观洞察、合规报告，区别于具体文献检索。"
        )
        self.args_schema = LegalAnalyticsInput

    @safe_tool_operation("legal_analytics", fallback_value="Error: 分析失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, metric: str, doc_type: str | None = None, jurisdiction: str | None = None,
                         legal_domain: str | None = None, limit: int = 10) -> str:
        body: dict[str, Any] = {"limit": limit}
        if doc_type:
            body["doc_type"] = doc_type
        if jurisdiction:
            body["jurisdiction"] = jurisdiction
        if legal_domain:
            body["legal_domain"] = legal_domain

        if metric == "top_authorities":
            result = await _call_kb_searcher("GET", "/analytics/top-authorities", params={"limit": limit}, timeout=20)
        elif metric in ("trend", "lifecycle", "jurisdiction_heatmap"):
            result = await _call_kb_searcher("POST", f"/analytics/{metric}", json_data=body, timeout=20)
        else:
            return f"不支持的 metric: {metric}（可选 trend/lifecycle/jurisdiction_heatmap/top_authorities）"
        if "error" in result:
            return f"Error: {result['error']}" + (f" — {str(result.get('detail'))[:300]}" if result.get("detail") else "")

        lines = [f"## 法律分析：{metric}\n"]
        # Generic rendering: show series/buckets/counts if present
        for key in ("series", "buckets", "data", "items", "authorities"):
            v = result.get(key)
            if isinstance(v, list) and v:
                for item in v[:15]:
                    if isinstance(item, dict):
                        label = item.get("label") or item.get("name") or item.get("key") or item.get("date") or "?"
                        count = item.get("count") or item.get("doc_count") or item.get("value") or ""
                        lines.append(f"- {label}: {count}")
                    else:
                        lines.append(f"- {item}")
                break
        else:
            for k, v in result.items():
                if isinstance(v, (str, int, float)):
                    lines.append(f"- {k}: {v}")
        return "\n".join(lines) if len(lines) > 1 else "（无分析数据）"


class LegalDocumentTimelineInput(BaseModel):
    document_id: str = Field(..., description="文档 ID（来自检索结果）")
    as_of: str | None = Field(None, description="point-in-time 日期(YYYY-MM-DD)，给定则返回该日期有效版本")


class LegalDocumentTimelineTool(CustomBaseTool):
    def __init__(self):
        super().__init__()
        self.name = "legal_document_timeline"
        self.description = (
            "查看法律文献的版本时间线/修订历史，可选 point-in-time 取某日期的有效版本。"
            "用于确认法规在某时点的有效表述（历史合规判断）。"
        )
        self.args_schema = LegalDocumentTimelineInput

    @safe_tool_operation("legal_document_timeline", fallback_value="Error: 时间线获取失败")
    def _run(self, **kwargs) -> str:
        return run_async(self._async_run(**kwargs))

    async def _async_run(self, document_id: str, as_of: str | None = None) -> str:
        result = await _call_kb_searcher("GET", f"/documents/{document_id}/timeline", timeout=20)
        if "error" in result:
            return f"Error: {result['error']}" + (f" — {str(result.get('detail'))[:300]}" if result.get("detail") else "")
        versions = result.get("versions") or result.get("timeline") or result.get("items") or []
        lines = [f"## 文献 `{document_id}` 版本时间线（{len(versions)} 个版本）\n"]
        for v in versions[:20] if isinstance(versions, list) else []:
            if isinstance(v, dict):
                date = v.get("date") or v.get("effective_date") or v.get("version", "?")
                desc = v.get("description") or v.get("summary") or v.get("title", "")
                lines.append(f"- {date}: {desc}")
        if as_of:
            pit = await _call_kb_searcher("GET", f"/documents/{document_id}/point-in-time", params={"as_of": as_of}, timeout=20)
            if "error" not in pit:
                content = (pit.get("content") or pit.get("text") or "")[:400]
                lines.append(f"\n**point-in-time @{as_of}:**\n{content}{'…' if content else '（无内容）'}")
        return "\n".join(lines) if len(lines) > 1 else f"文献 {document_id} 无版本时间线数据。"
