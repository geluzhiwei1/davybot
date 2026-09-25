"""
Unit tests for IP template API endpoints (FastAPI TestClient).

Tests cover:
  - GET /api/ip/templates — list all, filter by module, i18n
  - GET /api/ip/templates/{slug} — get template detail, 404
  - GET /api/ip/templates/versions/all — version listing
  - GET /api/ip/templates/reuse/{workspace_id} — reuse params (404 case)
  - POST /api/ip/templates/{slug}/create-workspace — validation errors
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

pytestmark = pytest.mark.unit


@pytest.fixture
def app():
    """Create a FastAPI test app with IP template routes."""
    from fastapi import FastAPI
    from dawei_biz.routers.ip_templates import router
    _app = FastAPI()
    _app.include_router(router)
    return _app


@pytest.fixture
def client(app):
    """Create a test client."""
    from httpx import AsyncClient, ASGITransport
    # For sync tests, use TestClient
    from starlette.testclient import TestClient
    return TestClient(app)


class TestListTemplatesAPI:
    """Tests for GET /api/ip/templates."""

    def test_returns_templates_list(self, client):
        response = client.get("/api/ip/templates")
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert "total" in data
        assert data["total"] >= 18

    def test_filter_by_module(self, client):
        response = client.get("/api/ip/templates?module=ip-application")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 9

    def test_filter_by_nonexistent_module(self, client):
        response = client.get("/api/ip/templates?module=nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["templates"] == []

    def test_lang_parameter_en(self, client):
        response = client.get("/api/ip/templates?module=ip-application&lang=en")
        assert response.status_code == 200
        data = response.json()
        # Templates with i18n should show English names
        templates = data["templates"]
        cn = next((t for t in templates if t["slug"] == "cn-invention"), None)
        if cn:
            assert cn["name"] == "CN Invention Patent Application"

    def test_lang_parameter_zh(self, client):
        response = client.get("/api/ip/templates?module=ip-application&lang=zh")
        assert response.status_code == 200
        data = response.json()
        cn = next((t for t in data["templates"] if t["slug"] == "cn-invention"), None)
        assert cn is not None
        assert "中国" in cn["name"]


class TestGetTemplateDetailAPI:
    """Tests for GET /api/ip/templates/{template_slug}."""

    def test_returns_template_detail(self, client):
        response = client.get("/api/ip/templates/patent-draft")
        assert response.status_code == 200
        data = response.json()
        assert data["template"]["slug"] == "patent-draft"
        assert "data_requirements" in data["template"]
        assert "phases" in data["template"]

    def test_returns_404_for_missing_template(self, client):
        response = client.get("/api/ip/templates/nonexistent-template")
        assert response.status_code == 404

    def test_cn_invention_has_target_country(self, client):
        response = client.get("/api/ip/templates/cn-invention")
        assert response.status_code == 200
        data = response.json()
        assert data["template"].get("target_country") == "CN"

    def test_us_utility_has_target_country(self, client):
        response = client.get("/api/ip/templates/us-utility")
        assert response.status_code == 200
        data = response.json()
        assert data["template"].get("target_country") == "US"


class TestListVersionsAPI:
    """Tests for GET /api/ip/templates/versions/all."""

    def test_returns_versions_list(self, client):
        response = client.get("/api/ip/templates/versions/all")
        assert response.status_code == 200
        data = response.json()
        assert "versions" in data
        assert "total" in data
        assert data["total"] >= 18

    def test_filter_by_module(self, client):
        response = client.get("/api/ip/templates/versions/all?module=ip-application")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 9
        for v in data["versions"]:
            assert v["category"] == "ip-application"

    def test_all_versions_are_not_unknown(self, client):
        response = client.get("/api/ip/templates/versions/all")
        data = response.json()
        unknowns = [v for v in data["versions"] if v["version"] == "unknown"]
        assert unknowns == []


class TestReuseParamsAPI:
    """Tests for GET /api/ip/templates/reuse/{workspace_id}."""

    def test_returns_404_for_missing_workspace(self, client):
        response = client.get("/api/ip/templates/reuse/nonexistent-ws-id")
        assert response.status_code == 404


class TestCreateWorkspaceAPI:
    """Tests for POST /api/ip/templates/{template_slug}/create-workspace."""

    def test_returns_404_for_missing_template(self, client):
        response = client.post(
            "/api/ip/templates/nonexistent/create-workspace",
            json={
                "module": "ip-application",
                "template_slug": "nonexistent",
                "form_data": {},
            },
        )
        assert response.status_code == 404
