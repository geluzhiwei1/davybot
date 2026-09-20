# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""A2 — Conversation persistence (backend core).

Conversations are HTTP + file-persisted under .dawei/chat-history/.
Create → list → get → save → delete round-trip against the live server.
"""

import uuid

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.asyncio
async def test_conversation_create_list_get_delete(client: httpx.AsyncClient, workspace):
    """A2.1 — full CRUD on a conversation within a workspace."""
    ws_id = workspace["id"]
    base = f"/api/workspaces/{ws_id}/conversations"

    # Create
    title = f"it-conv-{uuid.uuid4().hex[:6]}"
    create = await client.post(base, json={"title": title})
    assert create.status_code in (200, 201), create.text
    conv = create.json()
    conv_id = conv.get("id") or conv.get("conversation_id")
    assert conv_id, f"no conversation id in response: {conv}"

    try:
        # List contains it
        listing = (await client.get(base)).json()
        items = listing if isinstance(listing, list) else listing.get("conversations", listing.get("items", []))
        assert any((c.get("id") == conv_id) for c in items), "created conversation not in list"

        # Get by id
        one = await client.get(f"{base}/{conv_id}")
        assert one.status_code == 200, one.text
    finally:
        # Delete
        dele = await client.delete(f"{base}/{conv_id}")
        assert dele.status_code in (200, 204), dele.text

    # Gone from list
    listing2 = (await client.get(base)).json()
    items2 = listing2 if isinstance(listing2, list) else listing2.get("conversations", listing2.get("items", []))
    assert not any((c.get("id") == conv_id) for c in items2), "conversation still present after delete"


@pytest.mark.asyncio
async def test_conversation_save_persists_messages(client: httpx.AsyncClient, workspace):
    """A2.2 — POST /{conv_id} saves messages; re-read returns them."""
    ws_id = workspace["id"]
    base = f"/api/workspaces/{ws_id}/conversations"

    create = await client.post(base, json={"title": f"it-save-{uuid.uuid4().hex[:6]}"})
    conv_id = create.json().get("id")
    try:
        payload = {
            "title": "saved",
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ],
            "messageCount": 2,
        }
        save = await client.post(f"{base}/{conv_id}", json=payload)
        assert save.status_code == 200, save.text
        assert save.json().get("success") is True

        reread = (await client.get(f"{base}/{conv_id}")).json()
        # GET wraps the conversation under a "conversation" key
        conv_data = reread.get("conversation", reread)
        msgs = conv_data.get("messages", [])
        assert len(msgs) >= 2, f"messages not persisted: {reread}"
        assert any(m.get("content") == "hi there" for m in msgs)
    finally:
        await client.delete(f"{base}/{conv_id}")
