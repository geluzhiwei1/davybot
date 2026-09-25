# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Internal Agent SSE streaming endpoint — server-to-server integration.

Provides ``POST /api/internal/agent/run/stream`` for trusted internal callers
(notably nn-flow's ``NormFlowOrchestrator``) to dispatch a user message to a
workspace agent and receive a Server-Sent Events stream back.

Authentication
--------------
This endpoint is intended for localhost / service-to-service traffic only.
It accepts either:

1. ``X-Internal-Token`` header matching env var ``DAWEI_INTERNAL_TOKEN`` — when
   set, callers MUST supply it. Recommended for cross-host deployments.
2. If ``DAWEI_INTERNAL_TOKEN`` is unset, the endpoint falls back to allowing
   only loopback (``127.0.0.1`` / ``::1``) clients. This is safe for the
   default single-host deployment where nn-flow and nn-bot share a host.

Event format (SSE)
------------------
Each event is emitted as::

    data: {"type": "<event_type>", "content": "...", ...}\n\n

Terminal events (``task_completed`` / ``task_failed`` / ``error``) are followed
by stream close. The caller MUST consume the full stream to ensure workspace
teardown runs.

Event types mirror ``TaskEventType`` values; the most important are:
- ``llm_stream_content`` — incremental content chunk (field ``content``)
- ``task_completed`` — final assistant reply (field ``content`` / ``result``)
- ``task_failed`` / ``error_occurred`` — error (field ``error_message``)
- ``tool_started`` / ``tool_completed`` — tool call progress (field ``tool_name``)
- ``workflow_step_completed`` — PDCA / TaskGraph progress
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from dawei.core.events import TaskEventType
from dawei.logg.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/internal/agent", tags=["internal-agent-stream"])

# Sentinel pushed onto the queue to signal the consumer that the producer is done.
_STREAM_END: Dict[str, Any] = {"__stream_end__": True}

# Event types that terminate the SSE stream.
_TERMINAL_TYPES = {
    TaskEventType.TASK_COMPLETED.value,
    TaskEventType.TASK_FAILED.value,
    TaskEventType.ERROR_OCCURRED.value,
}


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------


class InternalAgentRunRequest(BaseModel):
    """Body for ``POST /api/internal/agent/run/stream``."""

    workspace_id: str = Field(..., description="Existing workspace UUID to run agent in")
    message: str = Field(..., description="User message to dispatch to the agent")
    session_id: Optional[str] = Field(
        None,
        description="Conversation/session ID; auto-generated when omitted",
    )
    task_id: Optional[str] = Field(
        None,
        description="Optional task ID for tracing; auto-generated when omitted",
    )
    mode: Optional[str] = Field(
        None,
        description="Override Agent mode (orchestrator/plan/do/check/act)",
    )
    llm: Optional[str] = Field(
        None,
        description="Override LLM model name",
    )
    user_id: Optional[str] = Field(
        None,
        description=(
            "Run the agent under this account id (multi-tenant isolation). "
            "Falls back to the request's authenticated user when omitted; "
            "internal callers (nn-flow) should pass the end-user's id so "
            "account-scoped resources (e.g. light-app MCP relay) resolve."
        ),
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def _client_is_loopback(request: Request) -> bool:
    client = request.client
    if client is None:
        return False
    return client.host in ("127.0.0.1", "::1", "localhost")


def _verify_internal_access(request: Request, x_internal_token: Optional[str]) -> None:
    """Raise HTTPException(403) if the caller is not trusted."""
    expected = os.environ.get("DAWEI_INTERNAL_TOKEN", "").strip()
    if expected:
        # Token mode: require exact match.
        if not x_internal_token or x_internal_token.strip() != expected:
            raise HTTPException(status_code=403, detail="invalid or missing X-Internal-Token")
        return
    # No token configured: allow loopback only.
    if not _client_is_loopback(request):
        raise HTTPException(
            status_code=403,
            detail="internal endpoint requires DAWEI_INTERNAL_TOKEN or loopback caller",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _resolve_workspace_path(workspace_id: str) -> str:
    """Look up workspace path from system index. Raises HTTPException(404)."""
    from dawei.storage.storage_provider import StorageProvider

    system_storage = StorageProvider.get_system_storage()
    if not await system_storage.exists("workspaces.json"):
        raise HTTPException(status_code=404, detail=f"workspace {workspace_id} not found")

    content = await system_storage.read_file("workspaces.json")
    data = json.loads(content)
    for ws in data.get("workspaces", []):
        if ws.get("id") == workspace_id:
            path = ws.get("path")
            if not path:
                raise HTTPException(status_code=404, detail=f"workspace {workspace_id} has no path")
            return path
    raise HTTPException(status_code=404, detail=f"workspace {workspace_id} not found")


def _event_to_payload(event: Any) -> Optional[Dict[str, Any]]:
    """Translate a TaskEvent into a flat JSON-serialisable dict for SSE.

    Returns ``None`` for events we deliberately drop (to keep the wire format
    concise for nn-flow's consumption).
    """
    event_type = event.event_type
    # Accept enum or raw value.
    etype_value = event_type.value if hasattr(event_type, "value") else str(event_type)
    data = event.data

    payload: Dict[str, Any] = {"type": etype_value}

    # Normalise data into a dict.
    if hasattr(data, "model_dump"):
        data_dict = data.model_dump()
    elif isinstance(data, dict):
        data_dict = data
    elif hasattr(data, "__dict__"):
        data_dict = {k: v for k, v in vars(data).items() if not k.startswith("_")}
    else:
        data_dict = {"value": str(data)} if data is not None else {}

    # Pick out the most relevant field per event type.
    if etype_value == TaskEventType.LLM_STREAM_CONTENT.value:
        payload["content"] = data_dict.get("content") or data_dict.get("chunk") or ""
    elif etype_value == TaskEventType.TASK_COMPLETED.value:
        payload["content"] = data_dict.get("result") or data_dict.get("content") or ""
        payload["result"] = data_dict.get("result", "")
    elif etype_value in (TaskEventType.TASK_FAILED.value, TaskEventType.ERROR_OCCURRED.value):
        payload["error_message"] = (
            data_dict.get("error_message")
            or data_dict.get("message")
            or data_dict.get("error")
            or str(data_dict)
        )
        payload["error_code"] = data_dict.get("error_code")
    elif etype_value in (TaskEventType.TOOL_STARTED.value, TaskEventType.TOOL_COMPLETED.value):
        payload["tool_name"] = data_dict.get("tool_name") or data_dict.get("name")
        payload["tool_call_id"] = data_dict.get("tool_call_id")
    elif etype_value == TaskEventType.WORKFLOW_STEP_COMPLETED.value:
        payload["step"] = data_dict.get("step") or data_dict.get("node_id")
        payload["status"] = data_dict.get("status")

    # Always include task_id when available for correlation.
    if "task_id" in data_dict:
        payload["task_id"] = data_dict["task_id"]

    return payload


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/run/stream")
async def run_agent_stream(
    body: InternalAgentRunRequest,
    request: Request,
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
):
    """Dispatch ``body.message`` to the workspace agent and stream events via SSE.

    Returns ``StreamingResponse(media_type="text/event-stream")``.
    """
    _verify_internal_access(request, x_internal_token)

    workspace_path = await _resolve_workspace_path(body.workspace_id)

    session_id = body.session_id or f"int-{uuid.uuid4().hex[:12]}"
    task_id = body.task_id or f"task-{uuid.uuid4().hex[:12]}"

    logger.info(
        "[INT_STREAM] dispatch workspace=%s session=%s task=%s msg=%r"
        % (body.workspace_id, session_id, task_id, body.message[:80])
    )

    async def event_source() -> AsyncIterator[str]:
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

        async def _run_agent() -> None:
            """Run agent in background, pushing events onto the queue."""
            try:
                from dawei.agentic.agent import Agent
                from dawei.agentic.agent_execution_service import agent_execution_service
                from dawei.workspace.user_workspace import UserWorkspace

                workspace = UserWorkspace(workspace_path)
                # 注入运行账号（initialize() 之前, context 按 (path, user_id) 分键）：
                # 优先 body.user_id（内部调用方 nn-flow 传终端用户）, 缺省回落请求认证身份。
                # 两者皆无 → FAST FAIL 401：不存在匿名 default_user 运行账号。
                _uid = body.user_id
                if not _uid:
                    try:
                        from dawei.api.auth import get_authenticated_user_id

                        _uid = await get_authenticated_user_id(request)
                    except Exception:
                        _uid = None
                if not _uid:
                    raise HTTPException(
                        status_code=401,
                        detail="internal agent run requires user_id (body) or authenticated caller",
                    )
                workspace.user_id = _uid
                await workspace.initialize()

                agent = await Agent.create_with_default_engine(workspace)
                await agent.initialize()

                event_bus = agent.event_bus
                # Subscribe to all interesting event types.
                subscriptions: list[str] = []
                interesting_types = {
                    TaskEventType.LLM_STREAM_CONTENT,
                    TaskEventType.TASK_COMPLETED,
                    TaskEventType.TASK_FAILED,
                    TaskEventType.ERROR_OCCURRED,
                    TaskEventType.TOOL_STARTED,
                    TaskEventType.TOOL_COMPLETED,
                    TaskEventType.WORKFLOW_STARTED,
                    TaskEventType.WORKFLOW_STEP_COMPLETED,
                    TaskEventType.WORKFLOW_COMPLETED,
                }

                async def _on_event(event: Any) -> None:
                    payload = _event_to_payload(event)
                    if payload is not None:
                        await queue.put(payload)
                        if payload.get("type") in _TERMINAL_TYPES:
                            await queue.put(_STREAM_END)

                for et in interesting_types:
                    try:
                        hid = event_bus.add_handler(et, _on_event)
                        subscriptions.append(hid)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("[INT_STREAM] subscribe %s failed: %s" % (et, exc))

                # Execute via the unified service so we get conversation persistence.
                result = await agent_execution_service.execute_agent_task(
                    workspace=workspace,
                    message=body.message,
                    session_id=session_id,
                    task_id=task_id,
                    task_type="user",
                    llm=body.llm,
                    mode=body.mode,
                )

                # If agent.run() completed without emitting TASK_COMPLETED
                # (e.g. event bus race), synthesize a terminal event from result.
                final_output = result.get("final_output") or ""
                if final_output:
                    # Check if we already emitted completion.
                    # Always emit a completion to be safe — clients dedupe by type.
                    await queue.put(
                        {
                            "type": TaskEventType.TASK_COMPLETED.value,
                            "content": final_output,
                            "result": final_output,
                            "synthesized": True,
                        }
                    )
                    await queue.put(_STREAM_END)

            except Exception as exc:  # noqa: BLE001
                logger.exception("[INT_STREAM] agent execution failed: %s" % exc)
                await queue.put(
                    {
                        "type": TaskEventType.ERROR_OCCURRED.value,
                        "error_message": str(exc),
                    }
                )
                await queue.put(_STREAM_END)
            finally:
                # Defensive: ensure consumers can't block forever.
                await queue.put(_STREAM_END)

        # Launch agent execution concurrently with SSE emission.
        task = asyncio.create_task(_run_agent())

        try:
            while True:
                # Bound the wait so client disconnects don't strand us.
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=600.0)
                except asyncio.TimeoutError:
                    logger.warning("[INT_STREAM] timeout waiting for event; closing stream")
                    yield _sse({"type": "error", "error_message": "stream timeout"})
                    break

                if item is _STREAM_END or item.get("__stream_end__"):
                    break

                yield _sse(item)

                if item.get("type") in _TERMINAL_TYPES:
                    # Drain any trailing sentinel(s) without blocking.
                    break
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            logger.info("[INT_STREAM] closed session=%s task=%s" % (session_id, task_id))

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )


def _sse(payload: Dict[str, Any]) -> str:
    """Serialise a payload as a single SSE ``data:`` line."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


__all__ = ["router"]
