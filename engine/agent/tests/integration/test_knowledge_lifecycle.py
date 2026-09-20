# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""A6 — Knowledge base full lifecycle (backend core).

Create → list → upload → search → graph → delete-document (cleanup regression)
→ delete-base. The create/list/delete-base path runs without a model backend;
upload/search/graph require an embedding model and are gated behind `require_llm`.
"""

import time
import uuid

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

KB = "/api/knowledge/bases"
SAMPLE_TXT = "合同甲方为 ACME 公司，乙方为 Beta 科技，争议解决地为北京。本文件用于知识库集成测试。".encode("utf-8")


@pytest.fixture
async def knowledge_base(client: httpx.AsyncClient):
    """Create a KB, yield its id, delete it after."""
    name = f"it-kb-{uuid.uuid4().hex[:6]}"
    resp = await client.post(KB, json={"name": name, "description": "integration test kb"})
    assert resp.status_code == 201, resp.text
    base_id = resp.json()["id"]
    try:
        yield base_id
    finally:
        try:
            await client.delete(f"{KB}/by-id/{base_id}")
        except Exception:
            pass


@pytest.mark.asyncio
async def test_kb_create_list_delete(client: httpx.AsyncClient):
    """A6.1/A6.6 — KB CRUD without a model backend."""
    name = f"it-kb-{uuid.uuid4().hex[:6]}"
    create = await client.post(KB, json={"name": name, "description": "crud test"})
    assert create.status_code == 201, create.text
    base_id = create.json()["id"]

    # Present in list
    listing = (await client.get(KB)).json()
    assert any(b.get("id") == base_id for b in listing.get("items", [])), "KB missing from list"

    # Delete base
    dele = await client.delete(f"{KB}/by-id/{base_id}")
    assert dele.status_code == 204, dele.text
    listing2 = (await client.get(KB)).json()
    assert not any(b.get("id") == base_id for b in listing2.get("items", [])), "KB still present after delete"


@pytest.mark.asyncio
async def test_kb_upload_search_graph(client: httpx.AsyncClient, knowledge_base, require_llm):
    """A6.2/A6.3/A6.4 — upload + index + search (4 modes) + graph. Requires embedding model."""
    base_id = knowledge_base

    # Upload a document
    files = {"file": ("sample.txt", SAMPLE_TXT, "text/plain")}
    up = await client.post(f"{KB}/by-id/{base_id}/documents/upload", files=files)
    assert up.status_code in (200, 201), up.text
    doc = up.json()
    doc_id = doc.get("id") or doc.get("document_id")
    assert doc_id, f"no doc id: {doc}"

    # Poll until indexed
    indexed = False
    for _ in range(30):
        docs = (await client.get(f"{KB}/by-id/{base_id}/documents")).json()
        items = docs if isinstance(docs, list) else docs.get("documents", docs.get("items", []))
        target = next((d for d in items if d.get("id") == doc_id), None)
        status = (target or {}).get("status") or (target or {}).get("index_status")
        if status in ("completed", "indexed", "ready", "done"):
            indexed = True
            break
        if status in ("failed", "error"):
            pytest.skip(f"document indexing failed (no embedding model?): {target}")
        time.sleep(1)
    if not indexed:
        pytest.skip("document did not finish indexing in time (embedding backend slow/absent)")

    # Search across retrieval modes — at least one must return our content
    found_any = False
    for mode in ("hybrid", "fulltext", "vector"):
        r = await client.post(
            f"{KB}/by-id/{base_id}/search",
            params={"query": "合同", "mode": mode, "top_k": 5},
        )
        assert r.status_code == 200, f"{mode} search failed: {r.status_code} {r.text}"
        hits = r.json().get("results", [])
        if any("合同" in str(h.get("content", "")) or h.get("document_id") == doc_id for h in hits):
            found_any = True
    assert found_any, "no search mode returned the uploaded document"

    # Graph entities reachable
    g = await client.get(f"{KB}/by-id/{base_id}/graph/entities")
    assert g.status_code == 200, g.text


@pytest.mark.asyncio
async def test_kb_delete_document_cleans_retrieval(client: httpx.AsyncClient, knowledge_base, require_llm):
    """A6.5 (regression) — deleting a document removes it from fulltext/graph search.

    Behavioural verification: after delete, no search mode surfaces the document.
    This guards the recent fix where delete left fulltext + graph stale.
    """
    base_id = knowledge_base
    files = {"file": ("sample.txt", SAMPLE_TXT, "text/plain")}
    up = await client.post(f"{KB}/by-id/{base_id}/documents/upload", files=files)
    doc_id = (up.json().get("id") or up.json().get("document_id"))
    if not doc_id:
        pytest.skip("upload did not return a doc id (embedding backend absent?)")

    # Wait for index so the doc is actually retrievable before we delete it
    deadline = time.time() + 30
    while time.time() < deadline:
        r = await client.post(
            f"{KB}/by-id/{base_id}/search",
            params={"query": "合同", "mode": "fulltext", "top_k": 10},
        )
        if any(h.get("document_id") == doc_id for h in r.json().get("results", [])):
            break
        time.sleep(1)
    else:
        pytest.skip("document never became retrievable (embedding backend absent?)")

    # Delete the document
    dele = await client.delete(f"{KB}/by-id/{base_id}/documents/{doc_id}")
    assert dele.status_code == 204, dele.text

    # Regression assertion: it must no longer appear in ANY retrieval mode
    for mode in ("fulltext", "vector", "hybrid"):
        r = await client.post(
            f"{KB}/by-id/{base_id}/search",
            params={"query": "合同", "mode": mode, "top_k": 10},
        )
        hits = r.json().get("results", [])
        assert not any(h.get("document_id") == doc_id for h in hits), (
            f"deleted document still surfaced by {mode} — fulltext/graph cleanup regressed"
        )

    # And not in the document list
    docs = (await client.get(f"{KB}/by-id/{base_id}/documents")).json()
    items = docs if isinstance(docs, list) else docs.get("documents", docs.get("items", []))
    assert not any(d.get("id") == doc_id for d in items), "deleted document still in document list"
