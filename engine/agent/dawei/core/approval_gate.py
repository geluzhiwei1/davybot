# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Human-in-the-loop approval gate for tool execution (P2.2).

Flow
----
Before a tool runs, ``ToolExecutor`` calls ``approval_gate.request_approval(...)``:

    decide(tool, risk)
      ├─ effective.approval.enabled == False  → ALLOW (default: inert, safe)
      ├─ tool in always_require_approval_tools → NEEDS_APPROVAL
      ├─ risk_at_least(risk, required_for_risk) → NEEDS_APPROVAL
      └─ otherwise                            → ALLOW

    NEEDS_APPROVAL:
      ├─ no publisher registered (no interactive WS channel)
      │     → apply ``no_channel_behavior`` ("allow" | "deny")
      ├─ publisher registered
      │     → register an asyncio.Future, publish ``tool_approval_request``,
      │       await it (timeout → deny); the WS ``tool_approval_response``
      │       handler calls ``resolve(request_id, approved)``.

Safety
------
- Default policy is ``enabled=False`` → the gate is a no-op (auto-allow) until
  explicitly turned on. Zero behavior change on rollout.
- Any internal error in the gate is swallowed (logged) and the tool is allowed,
  so the gate can never *break* execution — only *gate* it when healthy+enabled.
- Audit: every decision is recorded via ``security_auditor`` (``security.tool.decision``).

Wiring the WS channel (next increment)
--------------------------------------
The WebSocket layer registers a publisher::

    approval_gate.set_publisher(async_request_sender)

and a handler for the ``tool_approval_response`` client message calls::

    approval_gate.resolve(request_id, approved)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Awaitable, Callable

from dawei.core.effective_policy import (
    EffectiveApprovalPolicy,
    get_tool_risk,
    risk_at_least,
)
from dawei.core.security_auditor import _redact, security_auditor

logger = logging.getLogger(__name__)

#: Async callback that delivers a ``tool_approval_request`` dict to the client(s).
#: Returns True if delivered to an interactive client, False if no channel is
#: available for this request (e.g. headless / no matching session).
Publisher = Callable[[dict[str, Any]], Awaitable[bool]]
#: Optional override for the effective approval policy (defaults to security_manager).
PolicyProvider = Callable[[], EffectiveApprovalPolicy]


class ApprovalGate:
    """Singleton-friendly approval gate with a pluggable publish/resolve channel."""

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[bool]] = {}
        self._publisher: Publisher | None = None
        self._policy_provider: PolicyProvider | None = None

    # -- configuration ---------------------------------------------------

    def set_publisher(self, publisher: Publisher | None) -> None:
        self._publisher = publisher

    def set_policy_provider(self, provider: PolicyProvider | None) -> None:
        self._policy_provider = provider

    # -- policy resolution ----------------------------------------------

    def _policy(self) -> EffectiveApprovalPolicy:
        """Resolve the effective approval policy (lazy default: security_manager)."""
        try:
            if self._policy_provider is not None:
                policy = self._policy_provider()
                if policy is not None:
                    return policy
            from dawei.core.security_manager import security_manager

            return security_manager.get_policy().approval
        except Exception as e:  # pragma: no cover - never let policy read break flow
            logger.warning(f"ApprovalGate: policy resolution failed ({e}); using safe default")
            return EffectiveApprovalPolicy()

    def decide(self, tool_name: str, risk: str | None = None) -> str:
        """Return ``"allow"`` or ``"needs_approval"`` (never raises)."""
        risk = risk if risk is not None else get_tool_risk(tool_name)
        policy = self._policy()
        if not policy.enabled:
            return "allow"
        if tool_name in policy.always_require_approval_tools:
            return "needs_approval"
        if risk_at_least(risk, policy.required_for_risk):
            return "needs_approval"
        return "allow"

    # -- request / resolve ----------------------------------------------

    async def request_approval(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        *,
        risk: str | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
        task_id: str | None = None,
    ) -> bool:
        """Return True if the tool may proceed, False if it must be blocked."""
        risk = risk if risk is not None else get_tool_risk(tool_name)
        args = args or {}

        if self.decide(tool_name, risk) == "allow":
            return True

        policy = self._policy()

        # Register a pending future, then try to deliver the request to a client.
        request_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._pending[request_id] = future

        request = {
            "request_id": request_id,
            "tool": tool_name,
            "risk": risk,
            "args": _redact(args),
            "timeout_seconds": policy.approval_timeout_seconds,
            "user_id": user_id,
            "workspace_id": workspace_id,
            "task_id": task_id,
        }

        delivered = False
        if self._publisher is not None:
            try:
                delivered = bool(await self._publisher(request))
            except Exception as e:
                logger.warning(f"ApprovalGate: publisher failed for {tool_name}: {e}")
                delivered = False

        # No interactive channel for this request → honor configured fail behavior.
        if not delivered:
            self._pending.pop(request_id, None)
            allow = policy.no_channel_behavior == "allow"
            security_auditor.log(
                "security.tool.decision",
                tool=tool_name,
                risk=risk,
                decision="allowed" if allow else "denied",
                reason="no_channel",
                user_id=user_id,
                workspace_id=workspace_id,
            )
            return allow

        # Delivered → await the user's decision (with timeout).
        try:
            approved = await asyncio.wait_for(future, timeout=policy.approval_timeout_seconds)
            reason = "user_approved" if approved else "user_denied"
        except asyncio.TimeoutError:
            approved = False
            reason = "timeout"

        self._pending.pop(request_id, None)
        security_auditor.log(
            "security.tool.decision",
            tool=tool_name,
            risk=risk,
            decision="allowed" if approved else "denied",
            reason=reason,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        return approved

    def resolve(self, request_id: str, approved: bool) -> bool:
        """Resolve a pending request from the WS ``tool_approval_response`` handler.

        Returns True if a pending request was found and resolved.
        """
        future = self._pending.get(request_id)
        if future is not None and not future.done():
            future.set_result(bool(approved))
            return True
        return False

    def pending_count(self) -> int:
        return len(self._pending)


#: Module-level singleton. ToolExecutor and the WS layer share this instance.
approval_gate = ApprovalGate()
