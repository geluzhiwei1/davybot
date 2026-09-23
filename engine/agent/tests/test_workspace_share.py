# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""工作区分享功能测试 — 方案 §10 (project/docs/工作区分享功能方案.md)

覆盖: 有效期枚举 422 / 提取码哈希+回显 / verify 防爆破 / 只读端点 sanitize /
路径守卫 / token 隔离 / clone 白名单+配额 / close-open / 续期复活 / 撤销 / owner 隔离。

全部走最小 FastAPI 应用 (只挂 shares + owner share 两个 router),
workspace_manager 与索引注册均 monkeypatch — 不触碰真实 ~/.normnomos。
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import dawei.api.auth as auth_module
import dawei.api.shares as shares_api
from dawei.config.settings import get_settings
from dawei.workspace import workspace_manager
from dawei.workspace.workspace_share_manager import (
    ShareError,
    ShareNeedsExpiryError,
    ShareRevokedError,
    WorkspaceShareManager,
    decode_share_token,
)

pytestmark = pytest.mark.unit

OWNER_A = "user-a"
USER_B = "user-b"
TENANT = "personal"
WS_ID = "ws-share-test"


# ================================================================
# fixtures
# ================================================================


def _build_source_workspace(src: Path) -> None:
    """源工作区: 用户文件 + 对话/任务 (两处对话存储) + 必须被排除的敏感内容"""
    src.mkdir(parents=True, exist_ok=True)
    (src / "README.md").write_text("hello share", encoding="utf-8")
    (src / "docs").mkdir()
    (src / "docs" / "note.txt").write_text("note", encoding="utf-8")

    dawei = src / ".dawei"
    conv = dawei / "conversations"
    conv.mkdir(parents=True)
    (conv / "c1.json").write_text(
        json.dumps(
            {
                "id": "c1",
                "title": "对话一",
                "messages": [
                    {"role": "user", "content": "m1"},
                    {"role": "assistant", "content": "m2"},
                    {"role": "user", "content": "m3"},
                ],
                "createdAt": "2026-09-01T00:00:00+00:00",
                "updatedAt": "2026-09-02T00:00:00+00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (dawei / "chat-history").mkdir()
    (dawei / "chat-history" / "c1.agent.json").write_text("{}", encoding="utf-8")
    (dawei / "task_graphs").mkdir()
    (dawei / "task_graphs" / "g1.json").write_text(
        json.dumps(
            {
                "task_graph_id": "g1",
                "name": "图一",
                "timestamp": "2026-09-01T00:00:00+00:00",
                "nodes": {"n1": {"id": "n1", "description": "任务", "status": "done", "mode": "plan", "todos": [{"text": "t", "done": False}]}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # 以下内容分享/克隆都必须 fail-closed 排除
    (dawei / "settings.json").write_text('{"llm_key": "SECRET"}', encoding="utf-8")
    (dawei / "scheduled_tasks").mkdir()
    (dawei / "scheduled_tasks" / "s1.json").write_text("{}", encoding="utf-8")
    (src / ".git").mkdir()
    (src / ".git" / "config").write_text("[core]", encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    """隔离环境: auth 走 JWT / 分享索引进 tmp / workspace_manager 假索引 / 克隆根受限"""
    monkeypatch.setattr(auth_module, "_has_auth_capability", lambda: True)
    monkeypatch.delenv("DAWEI_SERVER_PASSWORD", raising=False)
    monkeypatch.delenv("WORKSPACE_STORE_BACKEND", raising=False)  # 克隆后 rustfs 同步直接跳过
    monkeypatch.setenv("DAWEI_WORKSPACE_BASE_DIR", str(tmp_path / "web_workspaces"))
    monkeypatch.delenv("DAWEI_SHARE_CLONE_MAX_BYTES", raising=False)
    monkeypatch.delenv("DAWEI_SHARE_CLONE_MAX_FILES", raising=False)

    import dawei.workspace.workspace_share_manager as wsm

    shares_file = tmp_path / "workspace_shares.json"
    monkeypatch.setattr(wsm, "_manager", WorkspaceShareManager(shares_file))
    monkeypatch.setattr(shares_api, "_limiter", shares_api._VerifyLimiter())  # 每测重置防爆破状态

    src = tmp_path / "src_ws"
    _build_source_workspace(src)
    records = {
        WS_ID: {
            "id": WS_ID,
            "name": "源工作区",
            "display_name": "源工作区",
            "description": "分享描述",
            "path": str(src),
            "created_at": "2026-09-01T00:00:00+00:00",
            "owner_user_id": OWNER_A,
            "tenant_id": TENANT,
        },
    }
    monkeypatch.setattr(workspace_manager, "get_workspace_by_id", records.get)

    registrations: list[dict] = []

    async def fake_register(**kwargs):
        registrations.append(kwargs)
        records[kwargs["workspace_id"]] = {
            "id": kwargs["workspace_id"],
            "name": kwargs["name"],
            "display_name": kwargs["name"],
            "path": kwargs["path"],
            "owner_user_id": kwargs["owner_user_id"],
            "tenant_id": kwargs["tenant_id"],
            "cloned_from": kwargs.get("cloned_from"),
        }

    monkeypatch.setattr(shares_api, "_register_clone_in_index", fake_register)

    return SimpleNamespace(tmp_path=tmp_path, src=src, shares_file=shares_file, records=records, registrations=registrations)


@pytest.fixture
def client(env):
    from dawei.api.shares import router as shares_router
    from dawei.api.workspaces.share import router as owner_router

    app = FastAPI()
    app.include_router(shares_router)
    app.include_router(owner_router)
    return TestClient(app)


# ================================================================
# helpers
# ================================================================


def _secret() -> str:
    return get_settings().security.jwt_secret


def _algo() -> str:
    return get_settings().security.jwt_algorithm


def _bearer(uid: str, tid: str = TENANT) -> dict[str, str]:
    token = pyjwt.encode({"sub": uid, "tid": tid}, _secret(), algorithm=_algo())
    return {"Authorization": f"Bearer {token}"}


def _owner_headers() -> dict[str, str]:
    return _bearer(OWNER_A)


def _create_share(client: TestClient, expires: int = 3, password: str | None = None) -> dict:
    body: dict = {"expires_in_days": expires}
    if password is not None:
        body["password"] = password
    r = client.post(f"/api/workspaces/{WS_ID}/share", json=body, headers=_owner_headers())
    assert r.status_code == 200, r.text
    return r.json()


def _verify(client: TestClient, share_id: str, password: str) -> dict:
    r = client.post(f"/api/shares/{share_id}/verify", json={"password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _force_expire(env, share_id: str) -> None:
    data = json.loads(env.shares_file.read_text(encoding="utf-8"))
    data["shares"][share_id]["expires_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    env.shares_file.write_text(json.dumps(data), encoding="utf-8")


# ================================================================
# unit: ShareManager
# ================================================================


class TestShareManager:
    def test_expiry_enum_only(self, tmp_path):
        manager = WorkspaceShareManager(tmp_path / "s.json")
        for bad in (0, 2, 5, 30, -1):
            with pytest.raises(ShareError):
                manager.create_share("ws", "u", "t", expires_in_days=bad)
        for good in (1, 3, 7):
            share = manager.create_share("ws", "u", "t", expires_in_days=good)
            assert share["expires_at"]

    def test_custom_password_rules(self, tmp_path):
        manager = WorkspaceShareManager(tmp_path / "s.json")
        with pytest.raises(ShareError):  # 太短
            manager.create_share("ws", "u", "t", password="ab", expires_in_days=1)
        with pytest.raises(ShareError):  # 太长
            manager.create_share("ws", "u", "t", password="a" * 33, expires_in_days=1)
        share = manager.create_share("ws", "u", "t", password="ab23", expires_in_days=1)
        assert share["password"] == "ab23"
        assert "ab23" not in json.dumps({k: v for k, v in share.items() if k != "password"})  # 落盘字段不含明文

    def test_verify_and_reveal(self, tmp_path):
        manager = WorkspaceShareManager(tmp_path / "s.json")
        share = manager.create_share("ws", "u", "t", password="ab23", expires_in_days=3)
        sid = share["share_id"]
        assert manager.verify_password(sid, "ab23") is True
        assert manager.verify_password(sid, "ab23 ") is False
        assert manager.verify_password(sid, "wrong") is False
        assert manager.reveal_password(sid) == "ab23"  # owner 随时回显

    def test_rotation_replaces_old_share(self, tmp_path):
        manager = WorkspaceShareManager(tmp_path / "s.json")
        first = manager.create_share("ws", "u", "t", expires_in_days=1)
        second = manager.create_share("ws", "u", "t", expires_in_days=1)
        assert first["share_id"] != second["share_id"]
        assert manager.get_share(first["share_id"]) is None  # 旧链接立即失效
        assert manager.get_share_for_workspace("ws")["share_id"] == second["share_id"]

    def test_state_machine(self, tmp_path):
        manager = WorkspaceShareManager(tmp_path / "s.json")
        share = manager.create_share("ws", "u", "t", expires_in_days=1)
        wid, sid = "ws", share["share_id"]

        manager.close_share_for_workspace(wid)
        assert manager.get_share(sid)["status"] == "closed"
        manager.open_share_for_workspace(wid)
        assert manager.get_share(sid)["status"] == "active"

        # 过期: open 不带天数 → 409 语义; 带天数一步复活
        data = json.loads((tmp_path / "s.json").read_text())
        data["shares"][sid]["expires_at"] = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        (tmp_path / "s.json").write_text(json.dumps(data))
        assert manager.is_expired(manager.get_share(sid)) is True
        with pytest.raises(ShareNeedsExpiryError):
            manager.open_share_for_workspace(wid)
        manager.open_share_for_workspace(wid, expires_in_days=7)
        assert manager.is_expired(manager.get_share(sid)) is False

        # PUT 对 closed 也可续期 (只改 expires_at 不改 status)
        manager.close_share_for_workspace(wid)
        updated = manager.update_expiry_for_workspace(wid, expires_in_days=3)
        assert updated["status"] == "closed"

        # 撤销: open/PUT 均拒绝
        manager.revoke_share_for_workspace(wid)
        with pytest.raises(ShareRevokedError):
            manager.open_share_for_workspace(wid)
        with pytest.raises(ShareRevokedError):
            manager.update_expiry_for_workspace(wid, expires_in_days=1)

    def test_token_scope_isolation(self, tmp_path):
        manager = WorkspaceShareManager(tmp_path / "s.json")
        share = manager.create_share("ws", "u", "t", password="ab23", expires_in_days=3)
        token, expires_at = manager.issue_share_token(manager.get_share(share["share_id"]))
        payload = decode_share_token(token)
        assert payload["sid"] == share["share_id"]
        assert payload["scope"] == "workspace-share"

        # 用户 JWT 拿来当 share-token → 拒绝 (scope 不符); 反向同理
        user_jwt = pyjwt.encode({"sub": "u", "tid": "t"}, _secret(), algorithm=_algo())
        with pytest.raises(ValueError, match="scope"):
            decode_share_token(user_jwt)
        # 篡改签名 → 拒绝
        with pytest.raises(ValueError, match="invalid share token"):
            decode_share_token(token[:-3] + "xxx")
        assert expires_at  # exp = 分享有效期


# ================================================================
# integration: owner 端点
# ================================================================


class TestOwnerEndpoints:
    def test_create_expiry_validation_422(self, client):
        for bad in (0, 2, 30):
            r = client.post(f"/api/workspaces/{WS_ID}/share", json={"expires_in_days": bad}, headers=_owner_headers())
            assert r.status_code == 422
        r = client.post(f"/api/workspaces/{WS_ID}/share", json={}, headers=_owner_headers())  # 缺失
        assert r.status_code == 422

    def test_create_and_get_reveal_password(self, client):
        created = _create_share(client, expires=3, password="ab23")
        assert created["password"] == "ab23"
        assert created["url"] == f"/share/{created['share_id']}"

        r = client.get(f"/api/workspaces/{WS_ID}/share", headers=_owner_headers())
        assert r.status_code == 200
        data = r.json()
        assert data["password"] == "ab23"  # 随时回显, 忘记码无需轮换
        assert data["status"] == "active"
        assert data["view_count"] == 0
        assert data["clone_count"] == 0

    def test_get_without_share_404(self, client):
        r = client.get(f"/api/workspaces/{WS_ID}/share", headers=_owner_headers())
        assert r.status_code == 404

    def test_owner_isolation_403(self, client):
        _create_share(client)
        # 用户 B 访问 A 的 owner 端点 → 403 (require_workspace_access)
        r = client.get(f"/api/workspaces/{WS_ID}/share", headers=_bearer(USER_B))
        assert r.status_code == 403
        r = client.post(f"/api/workspaces/{WS_ID}/share/close", headers=_bearer(USER_B))
        assert r.status_code == 403

    def test_unauthenticated_owner_401(self, client):
        r = client.get(f"/api/workspaces/{WS_ID}/share")
        assert r.status_code == 401


# ================================================================
# integration: viewer verify + 只读端点
# ================================================================


class TestViewerEndpoints:
    def test_verify_wrong_password_401(self, client):
        created = _create_share(client, password="ab23")
        r = client.post(f"/api/shares/{created['share_id']}/verify", json={"password": "wrong"})
        assert r.status_code == 401

    def test_verify_bruteforce_lock(self, client):
        created = _create_share(client, password="ab23")
        for _ in range(5):
            r = client.post(f"/api/shares/{created['share_id']}/verify", json={"password": "nope"})
            assert r.status_code == 401
        # 第 6 次即使密码正确也 429 (锁定 10 分钟)
        r = client.post(f"/api/shares/{created['share_id']}/verify", json={"password": "ab23"})
        assert r.status_code == 429
        assert "Retry-After" in r.headers

    def test_verify_success_shape_and_view_count(self, client):
        created = _create_share(client, password="ab23")
        data = _verify(client, created["share_id"], "ab23")
        assert data["share_token"]
        assert data["workspace"]["display_name"] == "源工作区"
        assert data["workspace"]["description"] == "分享描述"
        assert data["stats"]["files"] == 2  # README.md + docs/note.txt (dot 排除)
        assert data["stats"]["conversations"] == 1
        assert data["stats"]["tasks"] == 1

        r = client.get(f"/api/workspaces/{WS_ID}/share", headers=_owner_headers())
        assert r.json()["view_count"] == 1  # 一次验证 = 一次浏览

    def test_unknown_share_404_unified(self, client):
        r = client.post("/api/shares/nonexistent/verify", json={"password": "x"})
        assert r.status_code == 404
        assert r.json()["detail"] == "share not found or revoked"

    def test_read_endpoints_require_token(self, client):
        created = _create_share(client, password="ab23")
        for method, path in (
            ("get", f"/api/shares/{created['share_id']}/meta"),
            ("get", f"/api/shares/{created['share_id']}/file-tree"),
            ("get", f"/api/shares/{created['share_id']}/conversations"),
            ("get", f"/api/shares/{created['share_id']}/tasks"),
            ("post", f"/api/shares/{created['share_id']}/clone"),
        ):
            r = getattr(client, method)(path)
            assert r.status_code == 401, (method, path, r.status_code)

    def test_user_jwt_as_share_token_rejected(self, client):
        created = _create_share(client, password="ab23")
        r = client.get(f"/api/shares/{created['share_id']}/meta", headers={"X-Share-Token": _bearer(USER_B)["Authorization"][7:]})
        assert r.status_code == 401

    def test_meta_and_file_tree(self, client):
        created = _create_share(client, password="ab23")
        token = _verify(client, created["share_id"], "ab23")["share_token"]
        headers = {"X-Share-Token": token}

        r = client.get(f"/api/shares/{created['share_id']}/meta", headers=headers)
        assert r.status_code == 200
        body = r.text
        assert OWNER_A not in body  # sanitize: 无 owner uid
        assert "owner_user_id" not in body
        assert "src_ws" not in body  # 无绝对路径

        r = client.get(f"/api/shares/{created['share_id']}/file-tree", headers=headers)
        assert r.status_code == 200
        paths = [item["path"] for item in r.json()["fileTree"]]
        assert "README.md" in paths
        assert "docs" in paths
        assert "docs/note.txt" in paths
        assert not any(p.startswith((".dawei", ".git")) or "/." in p for p in paths)

    def test_conversations_sanitized_and_paginated(self, client):
        created = _create_share(client, password="ab23")
        sid = created["share_id"]
        token = _verify(client, sid, "ab23")["share_token"]
        headers = {"X-Share-Token": token}

        r = client.get(f"/api/shares/{sid}/conversations", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert "path" not in data["conversations"][0]  # 绝对路径不外泄
        assert data["conversations"][0]["title"] == "对话一"

        r = client.get(f"/api/shares/{sid}/conversations/c1", headers=headers, params={"order": "desc", "limit": 2})
        assert r.status_code == 200
        conv = r.json()["conversation"]
        assert conv["messageCount"] == 3
        assert len(conv["messages"]) == 2
        assert [m["content"] for m in conv["messages"]] == ["m2", "m3"]  # desc 取尾部但保持时序 (对齐 api/conversations.py)
        assert conv["pagination"]["hasMore"] is True

    def test_tasks_endpoint(self, client):
        created = _create_share(client, password="ab23")
        token = _verify(client, created["share_id"], "ab23")["share_token"]
        r = client.get(f"/api/shares/{created['share_id']}/tasks", headers={"X-Share-Token": token})
        assert r.status_code == 200
        graphs = r.json()["graphs"]
        assert len(graphs) == 1
        assert graphs[0]["total_tasks"] == 1
        assert graphs[0]["tasks"][0]["todos"] == [{"text": "t", "done": False}]

    def test_download_and_path_guards(self, client):
        created = _create_share(client, password="ab23")
        sid = created["share_id"]
        token = _verify(client, sid, "ab23")["share_token"]
        headers = {"X-Share-Token": token}

        r = client.get(f"/api/shares/{sid}/files/download", headers=headers, params={"path": "README.md"})
        assert r.status_code == 200
        assert r.content == b"hello share"
        assert "attachment" in r.headers["content-disposition"]

        # preview=1 → inline + 安全 mimetype
        r = client.get(f"/api/shares/{sid}/files/download", headers=headers, params={"path": "README.md", "preview": 1})
        assert r.status_code == 200
        assert "inline" in r.headers["content-disposition"]

        # dot 路径 / 穿越 / 绝对路径 → 403
        for bad_path in (".dawei/settings.json", "../etc/passwd", "/etc/passwd", "docs/../../etc/passwd"):
            r = client.get(f"/api/shares/{sid}/files/download", headers=headers, params={"path": bad_path})
            assert r.status_code == 403, bad_path

        # 不存在 → 404
        r = client.get(f"/api/shares/{sid}/files/download", headers=headers, params={"path": "nope.txt"})
        assert r.status_code == 404

        # 目录 → zip
        r = client.get(f"/api/shares/{sid}/files/download", headers=headers, params={"path": "docs"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"


# ================================================================
# integration: close / open / 续期 / 撤销
# ================================================================


class TestShareLifecycle:
    def test_close_invalidates_everything_instantly(self, client):
        created = _create_share(client, password="ab23")
        sid = created["share_id"]
        token = _verify(client, sid, "ab23")["share_token"]

        r = client.post(f"/api/workspaces/{WS_ID}/share/close", headers=_owner_headers())
        assert r.status_code == 200
        assert r.json()["status"] == "closed"

        # verify 404; 已签发 token 同样即时失效 (meta 404)
        r = client.post(f"/api/shares/{sid}/verify", json={"password": "ab23"})
        assert r.status_code == 404
        r = client.get(f"/api/shares/{sid}/meta", headers={"X-Share-Token": token})
        assert r.status_code == 404

    def test_open_reuses_same_link_and_password(self, client):
        created = _create_share(client, password="ab23")
        sid = created["share_id"]
        client.post(f"/api/workspaces/{WS_ID}/share/close", headers=_owner_headers())
        r = client.post(f"/api/workspaces/{WS_ID}/share/open", headers=_owner_headers())
        assert r.status_code == 200
        assert r.json()["status"] == "active"
        # 原链接+原提取码继续可用
        data = _verify(client, sid, "ab23")
        assert data["share_token"]

    def test_expired_share_recovery(self, client, env):
        created = _create_share(client, password="ab23")
        sid = created["share_id"]
        _force_expire(env, sid)

        assert client.post(f"/api/shares/{sid}/verify", json={"password": "ab23"}).status_code == 404
        # open 不带有效期 → 409 提示选择有效期
        r = client.post(f"/api/workspaces/{WS_ID}/share/open", headers=_owner_headers(), json={})
        assert r.status_code == 409
        # PUT 续期复活 — 不换链接不换码
        r = client.put(f"/api/workspaces/{WS_ID}/share", headers=_owner_headers(), json={"expires_in_days": 3})
        assert r.status_code == 200
        assert _verify(client, sid, "ab23")["share_token"]
        # open 带有效期一步恢复 (再过期一次)
        _force_expire(env, sid)
        r = client.post(f"/api/workspaces/{WS_ID}/share/open", headers=_owner_headers(), json={"expires_in_days": 7})
        assert r.status_code == 200
        assert _verify(client, sid, "ab23")["share_token"]

    def test_revoke_is_permanent(self, client):
        created = _create_share(client, password="ab23")
        sid = created["share_id"]
        r = client.delete(f"/api/workspaces/{WS_ID}/share", headers=_owner_headers())
        assert r.status_code == 200
        assert r.json()["revoked"] is True

        assert client.post(f"/api/shares/{sid}/verify", json={"password": "ab23"}).status_code == 404
        assert client.post(f"/api/workspaces/{WS_ID}/share/open", headers=_owner_headers(), json={}).status_code == 409
        assert client.put(f"/api/workspaces/{WS_ID}/share", headers=_owner_headers(), json={"expires_in_days": 1}).status_code == 409
        # owner GET 仍可见 (revoked 状态展示)
        r = client.get(f"/api/workspaces/{WS_ID}/share", headers=_owner_headers())
        assert r.json()["revoked"] is True


# ================================================================
# integration: clone
# ================================================================


class TestClone:
    def test_clone_requires_login(self, client):
        created = _create_share(client, password="ab23")
        token = _verify(client, created["share_id"], "ab23")["share_token"]
        r = client.post(f"/api/shares/{created['share_id']}/clone", headers={"X-Share-Token": token})
        assert r.status_code == 401  # 缺用户 JWT

    def test_clone_whitelist_copy(self, client, env):
        created = _create_share(client, password="ab23")
        token = _verify(client, created["share_id"], "ab23")["share_token"]

        r = client.post(
            f"/api/shares/{created['share_id']}/clone",
            headers={"X-Share-Token": token, **_bearer(USER_B)},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        new_id = data["workspace_id"]
        assert data["name"] == "源工作区（副本）"

        dest = env.tmp_path / "web_workspaces" / USER_B / TENANT / new_id
        assert dest.is_dir()
        # ✔ 用户文件 + 对话(两处) + 任务图
        assert (dest / "README.md").read_text(encoding="utf-8") == "hello share"
        assert (dest / "docs" / "note.txt").exists()
        assert (dest / ".dawei" / "conversations" / "c1.json").exists()
        assert (dest / ".dawei" / "chat-history" / "c1.agent.json").exists()
        assert (dest / ".dawei" / "task_graphs" / "g1.json").exists()
        # ✘ 配置/凭据/自动化/git 一律不拷
        assert not (dest / ".dawei" / "settings.json").exists()
        assert not (dest / ".dawei" / "scheduled_tasks" / "s1.json").exists()
        assert not (dest / ".git").exists()
        # 全新 workspace.json (id=新 id, 不含源配置)
        ws_json = json.loads((dest / ".dawei" / "workspace.json").read_text(encoding="utf-8"))
        assert ws_json["id"] == new_id
        assert "llm_key" not in json.dumps(ws_json)

        # 注册: owner=cloner, 附加 cloned_from
        assert len(env.registrations) == 1
        reg = env.registrations[0]
        assert reg["owner_user_id"] == USER_B
        assert reg["cloned_from"]["share_id"] == created["share_id"]

        # owner GET: clone_count + 脱敏 clone_log
        r = client.get(f"/api/workspaces/{WS_ID}/share", headers=_owner_headers())
        owner_view = r.json()
        assert owner_view["clone_count"] == 1
        assert owner_view["clone_log"][0]["user"] == "#user"  # user-b 前 4 位, 不泄完整 uid
        assert USER_B not in json.dumps(owner_view["clone_log"])

    def test_clone_quota_413(self, client, monkeypatch):
        created = _create_share(client, password="ab23")
        token = _verify(client, created["share_id"], "ab23")["share_token"]
        monkeypatch.setenv("DAWEI_SHARE_CLONE_MAX_BYTES", "1")  # 1 字节上限 → 必超
        r = client.post(
            f"/api/shares/{created['share_id']}/clone",
            headers={"X-Share-Token": token, **_bearer(USER_B)},
        )
        assert r.status_code == 413

    def test_clone_blocked_when_closed(self, client):
        created = _create_share(client, password="ab23")
        token = _verify(client, created["share_id"], "ab23")["share_token"]
        client.post(f"/api/workspaces/{WS_ID}/share/close", headers=_owner_headers())
        r = client.post(
            f"/api/shares/{created['share_id']}/clone",
            headers={"X-Share-Token": token, **_bearer(USER_B)},
        )
        assert r.status_code == 404
