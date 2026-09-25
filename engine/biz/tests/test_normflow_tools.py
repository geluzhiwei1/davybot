# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Unit tests for normflow business tools (firmAgent升级.md §5).

纯单测：mock AuthenticatedServiceClient 实例方法，不触网。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

import dawei_biz.tools.normflow_tools as nft
from dawei_biz.tools._service_client import ServiceAuthError, ServiceUnavailableError
from dawei_biz.tools.normflow_tools import NORMFLOW_TOOLS
from dawei.tools.tool_catalog import get_catalog
from dawei.tools.tool_manager import get_all_tool_groups

REPO = Path(__file__).resolve().parents[3]  # engine/agent

CASES_RESP = {"items": [{"id": "c1", "name": "张三劳动仲裁", "status": "active", "client_name": "张三"}], "total": 1}
DASHBOARD_RESP = {
    "cases": [{"name": "张三劳动仲裁", "estimated_amount": 50000, "invoiced_amount": 30000, "collected_amount": 20000, "outstanding_amount": 10000, "overdue_amount": 5000}],
    "total_outstanding": 10000,
}


class FakeClient:
    def __init__(self, routes: dict | None = None, exc: Exception | None = None):
        self.routes = routes or {}
        self.exc = exc
        self.calls: list[tuple] = []

    async def get(self, path, params=None, timeout=None):
        self.calls.append(("GET", path, params))
        if self.exc:
            raise self.exc
        return self.routes.get(("GET", path), {})

    async def post(self, path, json_body=None, timeout=None):
        self.calls.append(("POST", path, json_body))
        if self.exc:
            raise self.exc
        return self.routes.get(("POST", path), {})


@pytest.fixture
def fake_client(monkeypatch):
    holder = {}

    def _install(routes=None, exc=None):
        client = FakeClient(routes, exc)
        monkeypatch.setattr(nft, "normflow_client", client)
        holder["client"] = client
        return client

    holder["install"] = _install
    return holder


# ── schema ──────────────────────────────────────────────────────────


def test_input_schemas_require_required_fields():
    with pytest.raises(ValidationError):
        nft.NormflowCaseDetailInput()
    with pytest.raises(ValidationError):
        nft.NormflowCreateFollowUpInput(client_id="x")  # 缺 contact_method/content
    nft.NormflowSearchCasesInput()  # 全可选，OK


# ── happy path: 12 tools wired to correct paths ─────────────────────

CASE_ROUTES = {
    ("GET", "/cases"): CASES_RESP,
    ("GET", "/cases/c1"): {"name": "张三劳动仲裁", "status": "active", "client_name": "张三"},
    ("GET", "/cases/c1/tasks"): {"tasks": [{"title": " 提交答辩状 ", "due_date": "2026-09-01", "status": "open"}]},
    ("GET", "/cases/c1/timesheet-summary"): {"billable_hours": 12.5},
    ("GET", "/documents"): {"documents": [{"name": "委托合同.pdf", "doc_type": "contract"}]},
    ("GET", "/workflows/templates"): {"templates": [{"name": "诉讼标准流程", "category": "litigation"}]},
    ("GET", "/clients"): {"items": [{"name": "张三", "category": "signed"}]},
    ("GET", "/clients/u1"): {"name": "张三", "category": "signed", "tags": ["劳动"]},
    ("GET", "/clients/u1/cases"): CASES_RESP,
    ("GET", "/cases/payment-dashboard"): DASHBOARD_RESP,
}


@pytest.mark.parametrize(
    ("tool_cls", "kwargs", "expected_call", "expected_text"),
    [
        (nft.NormflowSearchCasesTool, {"status": "active"}, ("GET", "/cases"), "张三劳动仲裁"),
        (nft.NormflowCaseDetailTool, {"case_id": "c1"}, ("GET", "/cases/c1"), "张三劳动仲裁"),
        (nft.NormflowCaseTasksTool, {"case_id": "c1"}, ("GET", "/cases/c1/tasks"), "提交答辩状"),
        (nft.NormflowCaseTimesheetTool, {"case_id": "c1"}, ("GET", "/cases/c1/timesheet-summary"), "12.5"),
        (nft.NormflowCaseDocumentsTool, {"case_id": "c1"}, ("GET", "/documents"), "委托合同.pdf"),
        (nft.NormflowWorkflowTemplatesTool, {}, ("GET", "/workflows/templates"), "诉讼标准流程"),
        (nft.NormflowSearchClientsTool, {}, ("GET", "/clients"), "张三"),
        (nft.NormflowClientDetailTool, {"client_id": "u1"}, ("GET", "/clients/u1"), "张三"),
        (nft.NormflowClientCasesTool, {"client_id": "u1"}, ("GET", "/clients/u1/cases"), "张三劳动仲裁"),
        (nft.NormflowPaymentStatusTool, {}, ("GET", "/cases/payment-dashboard"), "10000"),
    ],
)
def test_get_tools_happy_path(fake_client, tool_cls, kwargs, expected_call, expected_text):
    client = fake_client["install"](CASE_ROUTES)
    out = tool_cls()._run(**kwargs)
    assert expected_call in [(m, p) for m, p, _ in client.calls]
    assert expected_text in out


def test_search_cases_active_filter_passed(fake_client):
    client = fake_client["install"](CASE_ROUTES)
    nft.NormflowSearchCasesTool()._run(status="active", page=2, page_size=10)
    ((_, _, params),) = [c for c in client.calls if c[1] == "/cases"]
    assert params["status"] == "active"
    assert params["page"] == 2
    assert params["page_size"] == 10


def test_search_cases_empty_result(fake_client):
    fake_client["install"]({("GET", "/cases"): {"items": [], "total": 0}})
    out = nft.NormflowSearchCasesTool()._run()
    assert "未找到" in out


def test_create_follow_up_post_body(fake_client):
    client = fake_client["install"]({("POST", "/clients/u1/follow-ups"): {"id": "f1"}})
    out = nft.NormflowCreateFollowUpTool()._run(client_id="u1", contact_method="phone", content="沟通记录")
    assert client.calls[0][:2] == ("POST", "/clients/u1/follow-ups")
    body = client.calls[0][2]
    assert body == {"contact_method": "phone", "content": "沟通记录"}
    assert "跟进记录" in out


def test_advance_workflow_post_body(fake_client):
    client = fake_client["install"]({("POST", "/workflows/instances/wf1/advance-to"): {"ok": True}})
    nft.NormflowAdvanceWorkflowTool()._run(instance_id="wf1", target_node_id="n2")
    assert client.calls[0][2] == {"target_node_id": "n2"}


def test_payment_dashboard_renders(fake_client):
    fake_client["install"](CASE_ROUTES)
    out = nft.NormflowPaymentStatusTool()._run()
    for key in ("50000", "30000", "20000", "10000", "5000"):
        assert key in out


# ── error branches ──────────────────────────────────────────────────


def test_auth_error_returns_friendly_text(fake_client):
    fake_client["install"](exc=ServiceAuthError("normflow 认证失败"))
    out = nft.NormflowSearchCasesTool()._run()
    assert out.startswith("Error: AUTH")


def test_unavailable_error_returns_friendly_text(fake_client):
    fake_client["install"](exc=ServiceUnavailableError("normflow 不可达"))
    out = nft.NormflowSearchCasesTool()._run()
    assert out.startswith("Error: UNAVAILABLE")


def test_http_4xx_detail_truncated(fake_client):
    fake_client["install"]({("GET", "/cases"): {"_error": "HTTP 400", "detail": "x" * 1000}})
    out = nft.NormflowSearchCasesTool()._run()
    assert "HTTP 400" in out
    assert len(out) < 400


# ── registration consistency ────────────────────────────────────────


def test_tool_groups_match_tool_classes():
    group_names = set(get_all_tool_groups()["normflow"]["custom_tools"])
    class_names = {t().name for t in NORMFLOW_TOOLS}
    assert group_names == class_names
    assert len(group_names) == 12


def test_catalog_entries_match_tools():
    cat = {e.name for e in get_catalog() if e.group == "normflow"}
    assert cat == {t().name for t in NORMFLOW_TOOLS}
    for e in get_catalog():
        if e.group == "normflow":
            assert e.short_desc
            assert any("\u4e00" <= ch <= "\u9fff" for ch in e.short_desc)


# ── isolation（§3.2d；mode-工具解耦后改为退役守护）──────────────────


def test_restricted_groups_admission_retired():
    """mode-工具解耦（方案 D3/D5）：RESTRICTED_GROUPS 准入白名单已整体删除。

    normflow 工具不再按 mode 准入——安装即可见，执行管控走 workspace allow/deny。
    """
    import dawei.tools.tool_manager as tm

    assert not hasattr(tm, "RESTRICTED_GROUPS")
    assert not hasattr(tm, "derive_restricted_groups")


def test_mcp_server_removed():
    assert not (REPO / "dawei" / "mcp_servers" / "normflow_server.py").exists()
