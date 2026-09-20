# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""nn-kb-searcher proxy routes for knowledge base management.

Provides unified knowledge search, document operations, RAG Q&A, chat,
knowledge graph, analytics, enterprise compliance, expert knowledge,
concepts, and user custom KB CRUD by proxying requests to the
nn-kb-searcher legal-ext service (default :8014).

See upgrade_v2.md §3.7 B & C for design rationale.
Aligned with OpenAPI spec at /api/v1/legal/openapi.json (97 endpoints).
"""

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge-uni"])

# nn-kb-searcher API base URL（E1: 无云端缺省 —— 未配置即 503 关闭）
_UNISEARCHER_API_URL = os.environ.get("UNISEARCHER_API_URL", "").rstrip("/")


# ============================================================================
# HTTP Client Helper
# ============================================================================


async def _proxy_request(
    method: str,
    path: str,
    *,
    json_data: dict | None = None,
    params: dict | None = None,
    timeout: float = 10.0,
) -> httpx.Response:
    """Proxy an HTTP request to nn-kb-searcher.

    Returns the raw httpx.Response so callers can inspect status/body.
    Raises HTTPException 502 on connection errors.
    """
    if not _UNISEARCHER_API_URL:
        raise HTTPException(
            status_code=status.HTTP_SERVICE_UNAVAILABLE,
            detail="knowledge service not configured: set UNISEARCHER_API_URL to enable (E1: no cloud default)",
        )
    url = f"{_UNISEARCHER_API_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.request(
                method, url, json=json_data, params=params
            )
    except httpx.ConnectError:
        logger.warning("nn-kb-searcher unreachable at %s", url)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Knowledge service (nn-kb-searcher) is not available",
        )
    except httpx.TimeoutException:
        logger.warning("nn-kb-searcher timeout at %s", url)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Knowledge service (nn-kb-searcher) timed out",
        )


def _forward_response(resp: httpx.Response) -> JSONResponse:
    """Convert httpx.Response to FastAPI JSONResponse, preserving status code."""
    try:
        body = resp.json()
    except Exception:
        body = {"detail": resp.text}
    return JSONResponse(status_code=resp.status_code, content=body)


# ============================================================================
# Request Models
# ============================================================================


class KnowledgeSearchRequest(BaseModel):
    """Unified knowledge search request body — matches backend LegalSearchRequest."""
    query: str = Field(..., min_length=1, description="Search query text")
    mode: str = Field("hybrid", description="Search mode: hybrid, keyword, vector, graph, field")
    filters: dict[str, Any] | None = Field(None, description="7-dimension taxonomy filters")
    top_k: int = Field(10, ge=1, le=100, description="Number of results to return")
    use_graph: bool = Field(True, description="Include graph results in hybrid search")
    as_of_date: str | None = Field(None, description="Point-in-time query date (ISO format)")
    jurisdiction_boost: str | None = Field(None, description="Jurisdiction boost factor")
    bm25_weight: float | None = Field(None, description="BM25 weight for hybrid search")
    vector_weight: float | None = Field(None, description="Vector weight for hybrid search")
    graph_weight: float | None = Field(None, description="Graph weight for hybrid search")


class LegalAskRequest(BaseModel):
    """RAG Q&A request — matches backend LegalAskRequest."""
    question: str = Field(..., min_length=1, description="Legal question")
    kb_id: str | None = Field(None, description="Limit to specific knowledge base")
    use_graph: bool = Field(True, description="Include graph context")


class LegalChatRequest(BaseModel):
    """Conversational chat request — matches backend LegalChatRequest."""
    question: str = Field(..., min_length=1, description="User message")
    conversation_id: str | None = Field(None, description="Existing conversation ID")
    kb_id: str | None = Field(None, description="Limit to specific knowledge base")
    use_graph: bool = Field(True, description="Include graph context")


class CreateKBRequest(BaseModel):
    """Create a user custom knowledge base."""
    name: str = Field(..., min_length=1, max_length=200, description="Knowledge base name")
    description: str = Field("", max_length=1000, description="Knowledge base description")
    legal_domains: list[str] = Field(default_factory=list, description="Legal domain tags")
    owner: str | None = Field(None, description="Owner user ID (set by middleware)")


class UpdateKBRequest(BaseModel):
    """Update knowledge base metadata."""
    name: str | None = Field(None, description="New name")
    description: str | None = Field(None, description="New description")
    legal_domains: list[str] | None = Field(None, description="New legal domain tags")


class CreateConceptRequest(BaseModel):
    """Create a legal concept."""
    name: str = Field(..., min_length=1, description="Concept name")
    description: str | None = Field(None, description="Concept description")
    jurisdiction: str | None = Field(None, description="Jurisdiction code")
    legal_domain: list[str] | None = Field(None, description="Legal domains")


class CompareConceptsRequest(BaseModel):
    """Compare two legal concepts."""
    concept_a: str = Field(..., description="First concept name or ID")
    concept_b: str = Field(..., description="Second concept name or ID")
    jurisdiction: str | None = Field(None, description="Jurisdiction context")


class UploadExpertRequest(BaseModel):
    """Upload expert knowledge content."""
    title: str = Field(..., min_length=1, description="Document title")
    content: str = Field(..., min_length=1, description="Document content")
    sub_type: str = Field("LEGAL_GUIDE", description="Expert knowledge sub-type")
    kb_id: str = Field("", description="Target knowledge base ID")
    jurisdiction: str = Field("CN", description="Jurisdiction code")
    legal_domain: list[str] = Field(default_factory=list, description="Legal domains")
    author: str = Field("", description="Author name")
    author_title: str = Field("", description="Author title")
    organization: str = Field("", description="Organization")
    tags: list[str] = Field(default_factory=list, description="Tags")
    related_laws: list[str] = Field(default_factory=list, description="Related law IDs")
    related_cases: list[str] = Field(default_factory=list, description="Related case IDs")
    access_level: str = Field("public", description="Access level")
    summary: str = Field("", description="Summary")


class BatchCreateMetadataRequest(BaseModel):
    """Batch create legal metadata."""
    items: list[dict[str, Any]] = Field(..., min_length=1, description="List of metadata items")


class ExtractSubgraphRequest(BaseModel):
    """Extract a subgraph from the knowledge graph."""
    entity_ids: list[str] | None = Field(None, description="Entity IDs to include")
    entity_types: list[str] | None = Field(None, description="Entity types to include")
    max_depth: int = Field(3, ge=1, le=10, description="Max traversal depth")
    limit: int = Field(100, ge=1, le=1000, description="Max entities to return")


class AnalyticsTrendRequest(BaseModel):
    """Regulatory trend analysis request."""
    start_date: str | None = Field(None, description="Start date")
    end_date: str | None = Field(None, description="End date")
    doc_type: str | None = Field(None, description="Document type filter")
    granularity: str = Field("month", description="Time granularity: month, quarter, year")


class AnalyticsLifecycleRequest(BaseModel):
    """Document lifecycle stats request."""
    doc_type: str | None = Field(None, description="Document type filter")
    jurisdiction: str | None = Field(None, description="Jurisdiction filter")


class AnalyticsHeatmapRequest(BaseModel):
    """Jurisdiction heatmap request."""
    doc_type: str | None = Field(None, description="Document type filter")
    legal_domain: str | None = Field(None, description="Legal domain filter")


# ============================================================================
# B. Unified Knowledge Search Endpoint (§3.7B)
# ============================================================================


@router.post("/search")
async def unified_knowledge_search(body: KnowledgeSearchRequest):
    """Search across knowledge bases via nn-kb-searcher.

    This is the unified entry point for both frontend and Agent to search
    knowledge bases. Forwards to nn-kb-searcher POST /api/v1/legal/search.
    Falls back to local KB search if nn-kb-searcher is unavailable.
    """
    # Build nn-kb-searcher request payload
    search_payload: dict[str, Any] = {
        "query": body.query,
        "top_k": body.top_k,
        "mode": body.mode,
        "use_graph": body.use_graph,
    }
    if body.filters:
        search_payload["filters"] = body.filters
    if body.as_of_date:
        search_payload["as_of_date"] = body.as_of_date
    if body.jurisdiction_boost:
        search_payload["jurisdiction_boost"] = body.jurisdiction_boost
    if body.bm25_weight is not None:
        search_payload["bm25_weight"] = body.bm25_weight
    if body.vector_weight is not None:
        search_payload["vector_weight"] = body.vector_weight
    if body.graph_weight is not None:
        search_payload["graph_weight"] = body.graph_weight

    resp = await _proxy_request("POST", "/search", json_data=search_payload, timeout=15.0)

    if resp.status_code == 200:
        return _forward_response(resp)

    # nn-kb-searcher returned an error — try local fallback
    logger.info(
        "nn-kb-searcher search returned %d, trying local fallback",
        resp.status_code,
    )
    return await _local_search_fallback(body)


async def _local_search_fallback(body: KnowledgeSearchRequest) -> JSONResponse:
    """Fall back to local knowledge base search when nn-kb-searcher is unavailable.

    Delegates to the existing knowledge_bases.py search endpoint logic.
    """
    try:
        from dawei.api.knowledge_bases import get_base_manager
        from dawei.knowledge.models import RetrievalMode, RetrievalQuery
        from dawei.knowledge.retrieval.hybrid_retriever import HybridRetriever

        manager = get_base_manager()

        # If kb_id specified, search that specific base
        kb_id = body.filters.get("kb_id") if body.filters else None
        if kb_id:
            kb = manager.get_base(kb_id)
            if not kb:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content={"detail": f"Knowledge base not found: {kb_id}"},
                )
            base_ids = [kb_id]
        else:
            # Search across all bases
            all_bases = manager.list_bases()
            base_ids = [b.id for b in all_bases.bases] if hasattr(all_bases, "bases") else []

        if not base_ids:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "results": [],
                    "total_count": 0,
                    "source": "local_fallback",
                    "message": "No local knowledge bases available",
                },
            )

        all_results = []
        for base_id in base_ids[:5]:  # Limit to 5 bases for performance
            try:
                base_storage = manager._get_storage_path(base_id)
                vector_db = base_storage / "vectors.db"
                if not vector_db.exists():
                    continue

                from dawei.knowledge.models import VectorSearchResult
                from dawei.knowledge.vector.sqlite_vec_store import SQLiteVecVectorStore

                kb = manager.get_base(base_id)
                vs = SQLiteVecVectorStore(
                    db_path=str(vector_db),
                    dimension=kb.settings.embedding_dimension,
                )
                await vs.initialize()

                embedding_mgr = manager.get_embedding_manager(base_id)
                query_embedding = await embedding_mgr.embed_query(body.query)

                results = await vs.search(query_embedding, top_k=body.top_k)
                for r in results:
                    r_dict = {
                        "id": r.id,
                        "content": r.content,
                        "score": r.score,
                        "metadata": r.metadata,
                        "base_id": base_id,
                    }
                    all_results.append(r_dict)
            except Exception as e:
                logger.warning("Local search fallback failed for base %s: %s", base_id, e)
                continue

        all_results.sort(key=lambda x: x["score"], reverse=True)
        all_results = all_results[:body.top_k]

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "results": all_results,
                "total_count": len(all_results),
                "source": "local_fallback",
            },
        )
    except Exception as e:
        logger.exception("Local search fallback error")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "results": [],
                "total_count": 0,
                "source": "local_fallback",
                "error": str(e),
            },
        )


# ============================================================================
# Search Suggest & Facets
# ============================================================================


@router.post("/search/facets")
async def search_facets(body: dict[str, Any]):
    """Faceted search — get dimension counts for filter panel."""
    resp = await _proxy_request("POST", "/search/facets", json_data=body, timeout=10.0)
    return _forward_response(resp)


@router.get("/search/suggest")
async def search_suggest(q: str = Query(..., min_length=1), limit: int = Query(8, ge=1, le=20)):
    """Get search suggestions (autocomplete)."""
    resp = await _proxy_request("GET", "/search/suggest", params={"q": q, "limit": limit})
    return _forward_response(resp)


# ============================================================================
# RAG Q&A & Chat
# ============================================================================


@router.post("/ask")
async def legal_ask(body: LegalAskRequest):
    """RAG Q&A — ask a legal question, get AI answer with citations."""
    payload: dict[str, Any] = {
        "question": body.question,
        "use_graph": body.use_graph,
    }
    if body.kb_id:
        payload["kb_id"] = body.kb_id
    resp = await _proxy_request("POST", "/ask", json_data=payload, timeout=30.0)
    return _forward_response(resp)


@router.post("/chat")
async def legal_chat(body: LegalChatRequest):
    """Conversational chat with legal context and conversation history."""
    payload: dict[str, Any] = {
        "question": body.question,
        "use_graph": body.use_graph,
    }
    if body.conversation_id:
        payload["conversation_id"] = body.conversation_id
    if body.kb_id:
        payload["kb_id"] = body.kb_id
    resp = await _proxy_request("POST", "/chat", json_data=payload, timeout=30.0)
    return _forward_response(resp)


# ============================================================================
# Document Operations
# ============================================================================


@router.get("/documents")
async def list_documents(
    doc_type: str | None = Query(None),
    sub_type: str | None = Query(None),
    legal_domain: str | None = Query(None),
    jurisdiction: str | None = Query(None),
    status: str | None = Query(None),
    industry: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List documents with 7-dimension taxonomy filters."""
    params = {k: v for k, v in {
        "doc_type": doc_type, "sub_type": sub_type, "legal_domain": legal_domain,
        "jurisdiction": jurisdiction, "status": status, "industry": industry,
        "page": page, "page_size": page_size,
    }.items() if v is not None}
    resp = await _proxy_request("GET", "/documents", params=params)
    return _forward_response(resp)


@router.get("/documents/{doc_id}/metadata")
async def get_document_metadata(doc_id: str):
    """Get legal metadata for a document."""
    resp = await _proxy_request("GET", f"/documents/{doc_id}/metadata")
    return _forward_response(resp)


@router.get("/documents/{doc_id}/chunks")
async def get_document_chunks(
    doc_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """Get document chunks (parsed segments)."""
    resp = await _proxy_request("GET", f"/documents/{doc_id}/chunks", params={"skip": skip, "limit": limit})
    return _forward_response(resp)


@router.get("/documents/{doc_id}/similar")
async def get_similar_documents(
    doc_id: str,
    top_k: int = Query(10, ge=1, le=50),
):
    """Get similar documents based on vector similarity."""
    resp = await _proxy_request("GET", f"/documents/{doc_id}/similar", params={"top_k": top_k})
    return _forward_response(resp)


@router.get("/documents/{doc_id}/cited-by")
async def get_cited_by(doc_id: str):
    """Get documents that cite this document."""
    resp = await _proxy_request("GET", f"/documents/{doc_id}/cited-by")
    return _forward_response(resp)


@router.get("/documents/{doc_id}/amendments")
async def get_amendments(doc_id: str):
    """Get amendment chain for a document."""
    resp = await _proxy_request("GET", f"/documents/{doc_id}/amendments")
    return _forward_response(resp)


@router.get("/documents/{doc_id}/versions")
async def get_versions(doc_id: str):
    """Get version history for a document."""
    resp = await _proxy_request("GET", f"/documents/{doc_id}/versions")
    return _forward_response(resp)


@router.get("/documents/{doc_id}/point-in-time")
async def get_point_in_time(
    doc_id: str,
    as_of_date: str = Query(..., description="ISO date for point-in-time query"),
):
    """Point-in-time query — get document state at a specific date."""
    resp = await _proxy_request("GET", f"/documents/{doc_id}/point-in-time", params={"as_of_date": as_of_date})
    return _forward_response(resp)


@router.get("/documents/{doc_id}/diff")
async def get_version_diff(
    doc_id: str,
    from_version: str = Query(...),
    to_version: str = Query(...),
):
    """Get diff between two document versions."""
    resp = await _proxy_request("GET", f"/documents/{doc_id}/diff", params={"from_version": from_version, "to_version": to_version})
    return _forward_response(resp)


@router.get("/documents/{doc_id}/timeline")
async def get_document_timeline(doc_id: str):
    """Get document timeline (key events)."""
    resp = await _proxy_request("GET", f"/documents/{doc_id}/timeline")
    return _forward_response(resp)


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(..., description="Document file to upload"),
    kb_id: str = Form(""),
    doc_type: str = Form(""),
):
    """Upload a document to the legal knowledge base."""
    url = f"{_UNISEARCHER_API_URL}/documents/upload"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"file": (file.filename, await file.read(), file.content_type or "application/octet-stream")}
            data = {}
            if kb_id:
                data["kb_id"] = kb_id
            if doc_type:
                data["doc_type"] = doc_type
            resp = await client.post(url, files=files, data=data)
        return _forward_response(resp)
    except httpx.ConnectError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Knowledge service unavailable")
    except httpx.TimeoutException:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Upload timed out")


@router.post("/documents/batch")
async def batch_create_metadata(body: BatchCreateMetadataRequest):
    """Batch create legal document metadata."""
    resp = await _proxy_request("POST", "/documents/batch", json_data={"items": body.items})
    return _forward_response(resp)


# ============================================================================
# Knowledge Graph
# ============================================================================


@router.get("/graph/entities")
async def search_graph_entities(
    query: str | None = Query(None),
    entity_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Search legal knowledge graph for entities."""
    params = {k: v for k, v in {"query": query, "entity_type": entity_type, "limit": limit}.items() if v is not None}
    resp = await _proxy_request("GET", "/graph/entities", params=params)
    return _forward_response(resp)


@router.get("/graph/entities/{entity_id}")
async def get_graph_entity(entity_id: str):
    """Get a single graph entity by ID."""
    resp = await _proxy_request("GET", f"/graph/entities/{entity_id}")
    return _forward_response(resp)


@router.get("/graph/entities/{entity_id}/neighbors")
async def get_graph_neighbors(
    entity_id: str,
    relation_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Get neighbors of a graph entity."""
    params = {k: v for k, v in {"relation_type": relation_type, "limit": limit}.items() if v is not None}
    resp = await _proxy_request("GET", f"/graph/entities/{entity_id}/neighbors", params=params)
    return _forward_response(resp)


@router.post("/graph/subgraph")
async def extract_subgraph(body: ExtractSubgraphRequest):
    """Extract a subgraph from the knowledge graph."""
    payload: dict[str, Any] = {"max_depth": body.max_depth, "limit": body.limit}
    if body.entity_ids:
        payload["entity_ids"] = body.entity_ids
    if body.entity_types:
        payload["entity_types"] = body.entity_types
    resp = await _proxy_request("POST", "/graph/subgraph", json_data=payload)
    return _forward_response(resp)


@router.get("/graph/influential")
async def get_influential(
    top: int = Query(20, ge=1, le=100),
    entity_type: str | None = Query(None),
):
    """Get most influential entities in the knowledge graph."""
    params = {"top": top}
    if entity_type:
        params["entity_type"] = entity_type
    resp = await _proxy_request("GET", "/graph/influential", params=params)
    return _forward_response(resp)


@router.get("/graph/communities")
async def get_communities(entity_type: str | None = Query(None)):
    """Get graph communities (clusters)."""
    params = {}
    if entity_type:
        params["entity_type"] = entity_type
    resp = await _proxy_request("GET", "/graph/communities", params=params or None)
    return _forward_response(resp)


@router.get("/graph/path")
async def get_shortest_path(
    from_id: str = Query(..., alias="from"),
    to_id: str = Query(..., alias="to"),
    max_depth: int = Query(5, ge=1, le=10),
):
    """Find shortest path between two entities."""
    resp = await _proxy_request("GET", "/graph/path", params={"from": from_id, "to": to_id, "max_depth": max_depth})
    return _forward_response(resp)


@router.get("/graph/stats")
async def get_graph_stats():
    """Get knowledge graph statistics."""
    resp = await _proxy_request("GET", "/graph/stats")
    return _forward_response(resp)


# ============================================================================
# Analytics
# ============================================================================


@router.post("/analytics/trend")
async def regulatory_trend(body: AnalyticsTrendRequest):
    """Regulatory trend analysis over time."""
    payload: dict[str, Any] = {"granularity": body.granularity}
    if body.start_date:
        payload["start_date"] = body.start_date
    if body.end_date:
        payload["end_date"] = body.end_date
    if body.doc_type:
        payload["doc_type"] = body.doc_type
    resp = await _proxy_request("POST", "/analytics/trend", json_data=payload)
    return _forward_response(resp)


@router.post("/analytics/lifecycle")
async def lifecycle_stats(body: AnalyticsLifecycleRequest):
    """Document lifecycle statistics."""
    payload: dict[str, Any] = {}
    if body.doc_type:
        payload["doc_type"] = body.doc_type
    if body.jurisdiction:
        payload["jurisdiction"] = body.jurisdiction
    resp = await _proxy_request("POST", "/analytics/lifecycle", json_data=payload)
    return _forward_response(resp)


@router.post("/analytics/jurisdiction-heatmap")
async def jurisdiction_heatmap(body: AnalyticsHeatmapRequest):
    """Jurisdiction heatmap — document density per region."""
    payload: dict[str, Any] = {}
    if body.doc_type:
        payload["doc_type"] = body.doc_type
    if body.legal_domain:
        payload["legal_domain"] = body.legal_domain
    resp = await _proxy_request("POST", "/analytics/jurisdiction-heatmap", json_data=payload)
    return _forward_response(resp)


@router.get("/analytics/subtype-distribution")
async def subtype_distribution(doc_type: str | None = Query(None)):
    """Subtype distribution statistics."""
    params = {"doc_type": doc_type} if doc_type else None
    resp = await _proxy_request("GET", "/analytics/subtype-distribution", params=params)
    return _forward_response(resp)


@router.get("/analytics/top-authorities")
async def top_authorities(
    doc_type: str | None = Query(None),
    top_k: int = Query(20, ge=1, le=100),
):
    """Top issuing authorities by document count."""
    params = {"top_k": top_k}
    if doc_type:
        params["doc_type"] = doc_type
    resp = await _proxy_request("GET", "/analytics/top-authorities", params=params)
    return _forward_response(resp)


# ============================================================================
# Enterprise Compliance
# ============================================================================


@router.get("/enterprises/{name}/compliance-profile")
async def get_enterprise_compliance(name: str):
    """Get compliance profile for an enterprise."""
    resp = await _proxy_request("GET", f"/enterprises/{name}/compliance-profile")
    return _forward_response(resp)


@router.get("/enterprises/violation-stats")
async def get_violation_stats(
    industry: str | None = Query(None),
    jurisdiction: str | None = Query(None),
):
    """Get enterprise violation statistics."""
    params = {k: v for k, v in {"industry": industry, "jurisdiction": jurisdiction}.items() if v is not None}
    resp = await _proxy_request("GET", "/enterprises/violation-stats", params=params or None)
    return _forward_response(resp)


# ============================================================================
# Expert Knowledge
# ============================================================================


@router.post("/expert/upload")
async def upload_expert_knowledge(body: UploadExpertRequest):
    """Upload expert knowledge content."""
    resp = await _proxy_request("POST", "/expert/upload", json_data=body.model_dump())
    return _forward_response(resp)


@router.post("/expert/recommend")
async def recommend_expert_knowledge(body: dict[str, Any]):
    """Get recommended expert knowledge for a query."""
    resp = await _proxy_request("POST", "/expert/recommend", json_data=body)
    return _forward_response(resp)


@router.get("/expert/stats")
async def get_expert_stats():
    """Get expert knowledge statistics."""
    resp = await _proxy_request("GET", "/expert/stats")
    return _forward_response(resp)


# ============================================================================
# Concepts
# ============================================================================


@router.get("/concepts")
async def list_concepts(
    legal_domain: str | None = Query(None),
    jurisdiction: str | None = Query(None),
):
    """List legal concepts."""
    params = {k: v for k, v in {"legal_domain": legal_domain, "jurisdiction": jurisdiction}.items() if v is not None}
    resp = await _proxy_request("GET", "/concepts", params=params or None)
    return _forward_response(resp)


@router.post("/concepts")
async def create_concept(body: CreateConceptRequest):
    """Create a new legal concept."""
    resp = await _proxy_request("POST", "/concepts", json_data=body.model_dump(exclude_none=True))
    return _forward_response(resp)


@router.post("/concepts/compare")
async def compare_concepts(body: CompareConceptsRequest):
    """Compare two legal concepts (e.g., GDPR vs PIPL)."""
    resp = await _proxy_request("POST", "/concepts/compare", json_data=body.model_dump(exclude_none=True))
    return _forward_response(resp)


# ============================================================================
# C. User Custom KB CRUD Proxy Endpoints (§3.7C)
# ============================================================================


@router.get("/uni/bases")
async def list_uni_knowledge_bases(
    owner: str | None = Query(None, description="Filter by owner ('me' for current user)"),
):
    """List knowledge bases from nn-kb-searcher."""
    params = {}
    if owner:
        params["owner"] = owner
    resp = await _proxy_request("GET", "/knowledge-bases", params=params)
    return _forward_response(resp)


@router.post("/uni/bases", status_code=status.HTTP_201_CREATED)
async def create_uni_knowledge_base(body: CreateKBRequest):
    """Create a user custom knowledge base via nn-kb-searcher."""
    payload = {
        "name": body.name,
        "description": body.description,
        "legal_domains": body.legal_domains,
    }
    if body.owner:
        payload["owner"] = body.owner
    resp = await _proxy_request("POST", "/knowledge-bases", json_data=payload)
    return _forward_response(resp)


@router.get("/uni/bases/{kb_id}")
async def get_uni_knowledge_base(kb_id: str):
    """Get knowledge base details from nn-kb-searcher."""
    resp = await _proxy_request("GET", f"/knowledge-bases/{kb_id}")
    return _forward_response(resp)


@router.put("/uni/bases/{kb_id}")
async def update_uni_knowledge_base(kb_id: str, body: UpdateKBRequest):
    """Update knowledge base metadata via nn-kb-searcher."""
    payload = {}
    if body.name is not None:
        payload["name"] = body.name
    if body.description is not None:
        payload["description"] = body.description
    if body.legal_domains is not None:
        payload["legal_domains"] = body.legal_domains
    resp = await _proxy_request("PUT", f"/knowledge-bases/{kb_id}", json_data=payload)
    return _forward_response(resp)


@router.delete("/uni/bases/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_uni_knowledge_base(kb_id: str):
    """Delete knowledge base via nn-kb-searcher."""
    resp = await _proxy_request("DELETE", f"/knowledge-bases/{kb_id}")
    if resp.status_code not in (200, 204):
        return _forward_response(resp)
    return None


@router.get("/uni/bases/{kb_id}/documents")
async def list_uni_kb_documents(
    kb_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """List documents in a nn-kb-searcher knowledge base."""
    params = {"skip": skip, "limit": limit}
    resp = await _proxy_request("GET", f"/knowledge-bases/{kb_id}/documents", params=params)
    return _forward_response(resp)


@router.post("/uni/bases/{kb_id}/documents/upload")
async def upload_uni_kb_document(
    kb_id: str,
    file: UploadFile = File(..., description="Document file to upload"),
):
    """Upload a document to a nn-kb-searcher knowledge base."""
    url = f"{_UNISEARCHER_API_URL}/knowledge-bases/{kb_id}/documents/upload"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"file": (file.filename, await file.read(), file.content_type or "application/octet-stream")}
            resp = await client.post(url, files=files)
        return _forward_response(resp)
    except httpx.ConnectError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Knowledge service unavailable")
    except httpx.TimeoutException:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Upload timed out")


@router.delete("/uni/bases/{kb_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_uni_kb_document(kb_id: str, document_id: str):
    """Delete a document from a nn-kb-searcher knowledge base."""
    resp = await _proxy_request("DELETE", f"/knowledge-bases/{kb_id}/documents/{document_id}")
    if resp.status_code not in (200, 204):
        return _forward_response(resp)
    return None


@router.post("/uni/bases/{kb_id}/search")
async def search_uni_knowledge_base(
    kb_id: str,
    body: KnowledgeSearchRequest,
):
    """Search within a specific nn-kb-searcher knowledge base."""
    payload = {
        "query": body.query,
        "top_k": body.top_k,
        "mode": body.mode,
    }
    resp = await _proxy_request("POST", f"/knowledge-bases/{kb_id}/search", json_data=payload, timeout=15.0)
    return _forward_response(resp)


# ============================================================================
# KB Discovery
# ============================================================================


@router.get("/knowledge-bases/discover")
async def discover_knowledge_bases():
    """Discover available knowledge bases with capabilities."""
    resp = await _proxy_request("GET", "/knowledge-bases/discover")
    return _forward_response(resp)


# ============================================================================
# Monitoring
# ============================================================================


@router.get("/stats")
async def get_legal_stats():
    """System statistics — document counts, entity counts, domain coverage."""
    resp = await _proxy_request("GET", "/stats")
    return _forward_response(resp)


@router.get("/tasks")
async def list_legal_tasks(
    task_status: str | None = Query(None, alias="status"),
    task_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List Celery task artifacts."""
    params = {k: v for k, v in {
        "status": task_status, "task_type": task_type,
        "page": page, "page_size": page_size,
    }.items() if v is not None}
    resp = await _proxy_request("GET", "/tasks", params=params)
    return _forward_response(resp)


@router.get("/tasks/{task_id}")
async def get_legal_task(task_id: str):
    """Get task detail by task_id."""
    resp = await _proxy_request("GET", f"/tasks/{task_id}")
    return _forward_response(resp)


# ============================================================================
# Auth
# ============================================================================


@router.post("/auth/login")
async def legal_auth_login(body: dict[str, str]):
    """Login to nn-kb-searcher legal-ext service."""
    resp = await _proxy_request("POST", "/auth/login", json_data=body)
    return _forward_response(resp)


# ============================================================================
# Health Check
# ============================================================================


@router.get("/uni/health")
async def uni_searcher_health():
    """Check nn-kb-searcher connectivity."""
    try:
        resp = await _proxy_request("GET", "/health", timeout=5.0)
        return {"status": "ok", "kb_searcher": resp.json() if resp.status_code == 200 else "degraded"}
    except HTTPException:
        return {"status": "unavailable", "kb_searcher": None}
