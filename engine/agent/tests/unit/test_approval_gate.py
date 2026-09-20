# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Unit tests for the ApprovalGate (P2.2) — human-in-the-loop tool approval.

Tests use asyncio.run() per case (no pytest-asyncio dependency required).
"""

import asyncio

from dawei.core.approval_gate import ApprovalGate
from dawei.core.effective_policy import EffectiveApprovalPolicy


def _gate(policy: EffectiveApprovalPolicy) -> ApprovalGate:
    g = ApprovalGate()
    g.set_policy_provider(lambda: policy)
    return g


def test_decide_disabled_allows():
    g = _gate(EffectiveApprovalPolicy(enabled=False))
    assert g.decide("execute_command") == "allow"  # critical tool, but gate off


def test_decide_risk_threshold():
    g = _gate(EffectiveApprovalPolicy(enabled=True, required_for_risk="high"))
    assert g.decide("execute_command") == "needs_approval"  # critical >= high
    assert g.decide("list_files") == "allow"  # low < high


def test_decide_always_require_overrides_risk():
    g = _gate(
        EffectiveApprovalPolicy(
            enabled=True, always_require_approval_tools=["read_file"]
        )
    )
    assert g.decide("read_file") == "needs_approval"  # low risk, but forced


def test_disabled_request_allows():
    g = _gate(EffectiveApprovalPolicy(enabled=False))
    assert asyncio.run(g.request_approval("execute_command")) is True


def test_no_channel_allow():
    g = _gate(
        EffectiveApprovalPolicy(
            enabled=True, required_for_risk="high", no_channel_behavior="allow"
        )
    )
    g.set_publisher(None)
    assert asyncio.run(g.request_approval("execute_command")) is True


def test_no_channel_deny():
    g = _gate(
        EffectiveApprovalPolicy(
            enabled=True, required_for_risk="high", no_channel_behavior="deny"
        )
    )
    g.set_publisher(None)
    assert asyncio.run(g.request_approval("execute_command")) is False


def test_publisher_resolve_approved():
    g = _gate(
        EffectiveApprovalPolicy(
            enabled=True, required_for_risk="high", approval_timeout_seconds=2
        )
    )

    async def publisher(req):
        g.resolve(req["request_id"], True)
        return True  # delivered

    g.set_publisher(publisher)
    assert asyncio.run(g.request_approval("execute_command", {"cmd": "ls"})) is True


def test_publisher_resolve_denied():
    g = _gate(
        EffectiveApprovalPolicy(enabled=True, required_for_risk="high")
    )

    async def publisher(req):
        g.resolve(req["request_id"], False)
        return True  # delivered

    g.set_publisher(publisher)
    assert asyncio.run(g.request_approval("execute_command")) is False


def test_timeout_denies():
    g = _gate(
        EffectiveApprovalPolicy(
            enabled=True, required_for_risk="high", approval_timeout_seconds=0.2
        )
    )

    async def silent(req):
        return True  # delivered to a client that never responds

    g.set_publisher(silent)
    assert asyncio.run(g.request_approval("execute_command")) is False


def test_publisher_not_delivered_uses_no_channel_behavior():
    """Publisher returns False (no interactive client) → no_channel_behavior."""
    g = _gate(
        EffectiveApprovalPolicy(
            enabled=True, required_for_risk="high", no_channel_behavior="deny"
        )
    )

    async def undelivered(req):
        return False  # no session for this task

    g.set_publisher(undelivered)
    assert asyncio.run(g.request_approval("execute_command")) is False


def test_resolve_unknown_id_is_noop():
    assert ApprovalGate().resolve("does-not-exist", True) is False


def test_provider_failure_fails_open():
    """A policy-provider error must NEVER block execution (fail-open)."""

    def boom():
        raise RuntimeError("policy provider exploded")

    g = ApprovalGate()
    g.set_policy_provider(boom)
    assert asyncio.run(g.request_approval("execute_command")) is True


def test_low_risk_skips_approval_even_when_enabled():
    g = _gate(EffectiveApprovalPolicy(enabled=True, required_for_risk="high"))
    # list_files is low risk — no approval needed even with the gate on
    assert asyncio.run(g.request_approval("list_files")) is True
