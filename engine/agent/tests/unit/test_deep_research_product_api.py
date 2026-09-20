# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""深度研究 · 产品调研 API 单元测试。

覆盖: 模板列表/详情、dao.md 渲染、工作区创建（脚手架 §6.8 / 元数据 §6.7）、
GATE-0/GATE-1 状态机（含 3 轮拒绝上限）、dry-run 推进、retry、duplicate、
审计日志、产物浏览/下载、路径穿越防护、mode team builtin 注册。

隔离: monkeypatch DAWEI_HOME → tmp_path（service.storage_root 动态读取）。
"""

import asyncio
import json

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("DAWEI_HOME", str(tmp_path))
    yield tmp_path


@pytest.fixture
def app():
    from fastapi import FastAPI

    from dawei.api import deep_research_product

    _app = FastAPI()
    _app.include_router(deep_research_product.router)
    return _app


@pytest.fixture
def client(app):
    from starlette.testclient import TestClient

    return TestClient(app)


# ============================================================
# Templates
# ============================================================

class TestTemplates:
    def test_list_templates(self, client):
        resp = client.get("/api/deep-research/product/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 6
        slugs = {t["slug"] for t in data["templates"]}
        assert "ai-short-video" in slugs
        # 空白模板：不预设方向（default_topic 为空）
        assert "blank" in slugs
        detail = client.get("/api/deep-research/product/templates/blank").json()
        assert detail["default_topic"] == ""
        assert len(detail["dimensions"]) == 4
        tpl = next(t for t in data["templates"] if t["slug"] == "ai-short-video")
        # §6.3 契约字段
        for field in ("slug", "name", "category", "estimated_products", "estimated_dimensions", "estimated_minutes", "tags", "is_builtin", "default_dao_path"):
            assert field in tpl
        assert tpl["estimated_dimensions"] == 8

    def test_get_template_detail(self, client):
        resp = client.get("/api/deep-research/product/templates/ai-legal-tools")
        assert resp.status_code == 200
        tpl = resp.json()
        assert tpl["name"] == "AI 法律工具"
        assert len(tpl["dimensions"]) == 6
        assert all({"key", "name", "description"} <= set(d) for d in tpl["dimensions"])

    def test_get_template_404(self, client):
        resp = client.get("/api/deep-research/product/templates/nope")
        assert resp.status_code == 404

    def test_render_dao_preview(self, client):
        resp = client.post(
            "/api/deep-research/product/templates/ai-short-video/render-dao",
            json={"topic": "AI 短视频生成", "user_input": "调研全球赛道"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["validation"]["valid"] is True
        assert "## Overview" in data["dao_md"]
        assert "AI 短视频生成" in data["dao_md"]


# ============================================================
# Workspace lifecycle
# ============================================================

class TestWorkspaceLifecycle:
    def test_create_workspace_scaffold(self, client, isolated_home):
        resp = client.post(
            "/api/deep-research/product/workspaces",
            json={"template_slug": "ai-short-video", "topic": "AI 短视频生成", "mode": "wizard", "user_input": "调研全球赛道"},
        )
        assert resp.status_code == 200
        meta = resp.json()
        wid = meta["workspace_id"]

        assert meta["status"] == "created"
        assert meta["team"] == "product-survey"
        assert meta["mode_team"] == "product-survey-team"
        assert meta["dao_path"] == "input/dao.md"
        assert len(meta["stages"]) == 11  # 6 phase × 11 stage
        assert all(s["status"] == "pending" for s in meta["stages"])
        assert [g["id"] for g in meta["gates"]] == ["GATE-0", "GATE-1"]
        assert meta["gates"][0]["status"] == "pending"  # GATE-0 必走

        ws_dir = isolated_home / "product-survey" / wid
        assert (ws_dir / "input" / "dao.md").exists()
        assert (ws_dir / "input" / "task_parameters.json").exists()
        assert (ws_dir / "AGENT_INSTRUCTIONS.md").exists()
        assert (ws_dir / "references" / "product-survey-mode-team.json").exists()
        # §6.8 phase 目录树
        assert (ws_dir / "output" / "phase-05-export" / "stage-10-export").is_dir()

        # Task-as-Workspace: 平台工作区结构 + 调研会话 + 系统索引注册
        assert (ws_dir / ".dawei" / "workspace.json").exists()  # 平台 WorkspaceInfo
        assert (ws_dir / ".dawei" / "deep_research.json").exists()  # 调研元数据（新位置）
        assert meta["conversation_id"]
        assert (ws_dir / ".dawei" / "conversations" / f"{meta['conversation_id']}.json").exists()
        system_ws = json.loads((isolated_home / "workspaces.json").read_text(encoding="utf-8"))
        entry = next(w for w in system_ws["workspaces"] if w["id"] == wid)
        assert entry["workspace_type"] == "deep-research"
        assert entry["lifecycle"] == "persistent"

    def test_start_blocked_before_gate0(self, client):
        wid = client.post(
            "/api/deep-research/product/workspaces",
            json={"template_slug": "ai-short-video", "topic": "t"},
        ).json()["workspace_id"]
        resp = client.post(f"/api/deep-research/product/workspaces/{wid}/start")
        assert resp.status_code == 409  # 任何跳过 GATE-0 的请求被拒绝

    def test_auto_start_rejected_without_gate0(self, client):
        resp = client.post(
            "/api/deep-research/product/workspaces",
            json={"template_slug": "ai-short-video", "topic": "t", "auto_start": True},
        )
        assert resp.status_code == 409

    def test_create_workspace_invalid_mode(self, client):
        resp = client.post(
            "/api/deep-research/product/workspaces",
            json={"template_slug": "ai-short-video", "topic": "t", "mode": "hack"},
        )
        assert resp.status_code == 422  # pydantic pattern

    def test_list_workspaces(self, client):
        client.post("/api/deep-research/product/workspaces", json={"template_slug": "ai-short-video", "topic": "a"})
        client.post("/api/deep-research/product/workspaces", json={"template_slug": "ai-translation", "topic": "b"})
        resp = client.get("/api/deep-research/product/workspaces")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert all("stages_completed" in w and "pending_gate" in w for w in data["workspaces"])


# ============================================================
# GATE state machine
# ============================================================

def _create(client, topic="AI 短视频生成", slug="ai-short-video"):
    return client.post(
        "/api/deep-research/product/workspaces",
        json={"template_slug": slug, "topic": topic},
    ).json()


def _decide(client, wid, gate, action, **kw):
    return client.post(
        f"/api/deep-research/product/workspaces/{wid}/gates/{gate}/decide",
        json={"action": action, **kw},
    )


class TestDeleteWorkspace:
    """删除工作区：product 专用端点（目录 + 系统索引注册一并清理）。"""

    def test_delete_removes_dir_and_registry(self, client, isolated_home):
        wid = _create(client, topic="产品删除验证")["workspace_id"]
        assert (isolated_home / "product-survey" / wid).is_dir()
        registry = json.loads((isolated_home / "workspaces.json").read_text(encoding="utf-8"))
        assert any(w["id"] == wid for w in registry["workspaces"])

        resp = client.delete(f"/api/deep-research/product/workspaces/{wid}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        assert not (isolated_home / "product-survey" / wid).exists()
        registry = json.loads((isolated_home / "workspaces.json").read_text(encoding="utf-8"))
        assert not any(w["id"] == wid for w in registry["workspaces"])
        listing = client.get("/api/deep-research/product/workspaces").json()
        assert all(w["workspace_id"] != wid for w in listing["workspaces"])
        # FAST FAIL: 详情 / 二次删除 → 404
        assert client.get(f"/api/deep-research/product/workspaces/{wid}").status_code == 404
        assert client.delete(f"/api/deep-research/product/workspaces/{wid}").status_code == 404


class TestGateStateMachine:
    def test_happy_path_gate0_gate1_complete(self, client):
        wid = _create(client)["workspace_id"]

        # GATE-0 通过 → 推进 stage 00-03，停在 GATE-1
        resp = _decide(client, wid, "GATE-0", "approve")
        assert resp.status_code == 200
        meta = resp.json()
        assert meta["status"] == "running"
        assert sum(1 for s in meta["stages"] if s["status"] == "completed") == 3
        gate1 = next(g for g in meta["gates"] if g["id"] == "GATE-1")
        assert gate1["status"] == "pending"
        # GATE-1 维度覆盖预览
        assert meta["gate1_preview"]["products_collected"] > 0
        assert len(meta["gate1_preview"]["dimensions"]) == 8

        # GATE-1 通过 → 完成全部 11 stage
        resp = _decide(client, wid, "GATE-1", "approve", note="通过")
        assert resp.status_code == 200
        meta = resp.json()
        assert meta["status"] == "completed"
        assert all(s["status"] == "completed" for s in meta["stages"])
        assert meta["metrics"]["products_deep_carded"] > 0
        assert meta["metrics"]["total_tokens"] > 0

    def test_gate0_reject_regenerates_dao(self, client, isolated_home):
        meta = _create(client)
        wid = meta["workspace_id"]
        dao_before = (isolated_home / "product-survey" / wid / "input" / "dao.md").read_text()

        resp = _decide(client, wid, "GATE-0", "reject", note="聚焦海外产品")
        assert resp.status_code == 200
        dao_after = (isolated_home / "product-survey" / wid / "input" / "dao.md").read_text()
        assert dao_before != dao_after
        assert "聚焦海外产品" in dao_after  # 补充说明附加
        body = resp.json()
        gate0 = next(g for g in body["gates"] if g["id"] == "GATE-0")
        assert gate0["status"] == "pending" and gate0["round"] == 1

    def test_gate0_edit_requires_valid_sections(self, client):
        wid = _create(client)["workspace_id"]
        resp = _decide(client, wid, "GATE-0", "edit", dao_md="# bad\n\n缺四段结构")
        assert resp.status_code == 400
        # dao.md 未被覆盖
        resp = _decide(client, wid, "GATE-0", "edit", dao_md="# dao.md\n\n## Overview\n\no\n\n## Goals\n\n- g\n\n### 必须\n\n- m\n\n### 优选\n\n- p\n\n## 约定\n\n- c\n")
        assert resp.status_code == 200

    def test_gate0_three_round_limit(self, client):
        wid = _create(client)["workspace_id"]
        for i in range(3):
            resp = _decide(client, wid, "GATE-0", "reject", note=f"r{i+1}")
            assert resp.status_code == 200  # 3 次重新生成均允许
        # 第 4 次 → needs_manual
        resp = _decide(client, wid, "GATE-0", "reject", note="r4")
        assert resp.status_code == 409
        meta = client.get(f"/api/deep-research/product/workspaces/{wid}").json()
        assert meta["status"] == "needs_manual"

    def test_gate1_reject_rolls_back_to_stage02(self, client):
        wid = _create(client)["workspace_id"]
        _decide(client, wid, "GATE-0", "approve")
        resp = _decide(client, wid, "GATE-1", "reject", note="补采硬件/外设")
        assert resp.status_code == 200
        meta = resp.json()
        gate1 = next(g for g in meta["gates"] if g["id"] == "GATE-1")
        assert gate1["round"] == 1
        assert gate1["status"] == "pending"  # 补采后重新打开
        # 自动补采：stage 02-03 重新完成，仍停在 GATE-1
        assert sum(1 for s in meta["stages"] if s["status"] == "completed") == 3
        stage02 = next(s for s in meta["stages"] if s["id"] == "stage-02-product-collect")
        assert stage02["status"] == "completed"

    def test_gate1_reject_round_limit(self, client):
        wid = _create(client)["workspace_id"]
        _decide(client, wid, "GATE-0", "approve")
        for i in range(3):
            resp = _decide(client, wid, "GATE-1", "reject", note=f"r{i+1}")
            assert resp.status_code == 200
        resp = _decide(client, wid, "GATE-1", "reject", note="r4")
        assert resp.status_code == 409

    def test_decide_invalid_action(self, client):
        wid = _create(client)["workspace_id"]
        resp = client.post(
            f"/api/deep-research/product/workspaces/{wid}/gates/GATE-0/decide",
            json={"action": "skip"},
        )
        assert resp.status_code == 422

    def test_decide_unknown_gate_404(self, client):
        wid = _create(client)["workspace_id"]
        resp = _decide(client, wid, "GATE-9", "approve")
        assert resp.status_code == 404


# ============================================================
# Retry / Duplicate / Audit
# ============================================================

class TestRetryDuplicateAudit:
    def test_retry_from_stage(self, client):
        wid = _create(client)["workspace_id"]
        _decide(client, wid, "GATE-0", "approve")
        _decide(client, wid, "GATE-1", "approve")
        resp = client.post(
            f"/api/deep-research/product/workspaces/{wid}/retry",
            params={"from_stage": "stage-05-market-landscape"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"  # 重跑后再次完成

    def test_retry_unknown_stage_404(self, client):
        wid = _create(client)["workspace_id"]
        resp = client.post(
            f"/api/deep-research/product/workspaces/{wid}/retry",
            params={"from_stage": "stage-99"},
        )
        assert resp.status_code == 404

    def test_duplicate_skips_gate0(self, client):
        wid = _create(client)["workspace_id"]
        _decide(client, wid, "GATE-0", "approve")
        resp = client.post(f"/api/deep-research/product/workspaces/{wid}/duplicate")
        assert resp.status_code == 200
        dup = resp.json()
        assert dup["workspace_id"] != wid
        assert "副本" in dup["topic"]
        gate0 = next(g for g in dup["gates"] if g["id"] == "GATE-0")
        assert gate0["status"] == "passed"  # 跳过 GATE-0

    def test_audit_log_records_decisions(self, client):
        wid = _create(client)["workspace_id"]
        _decide(client, wid, "GATE-0", "approve")
        _decide(client, wid, "GATE-1", "approve")
        resp = client.get(f"/api/deep-research/product/workspaces/{wid}/audit-log")
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        actions = [e["action"] for e in entries]
        assert "workspace.created" in actions
        assert "gate.approved" in actions
        assert "pipeline.completed" in actions
        # 每条含操作人/时间戳
        assert all({"at", "actor", "action", "detail"} <= set(e) for e in entries)


# ============================================================
# Files
# ============================================================

class TestFiles:
    def _completed(self, client):
        wid = _create(client)["workspace_id"]
        _decide(client, wid, "GATE-0", "approve")
        _decide(client, wid, "GATE-1", "approve")
        return wid

    def test_list_files_root(self, client):
        wid = self._completed(client)
        resp = client.get(f"/api/deep-research/product/workspaces/{wid}/files")
        assert resp.status_code == 200
        names = [e["name"] for e in resp.json()["entries"]]
        assert {"input", "output", "reports", "references"} <= set(names)

    def test_list_files_reports_after_completion(self, client):
        wid = self._completed(client)
        resp = client.get(f"/api/deep-research/product/workspaces/{wid}/files", params={"path": "reports"})
        names = [e["name"] for e in resp.json()["entries"]]
        assert "report_final.md" in names
        assert "report.pdf" in names

    def test_download_file(self, client):
        wid = self._completed(client)
        resp = client.get(
            f"/api/deep-research/product/workspaces/{wid}/files/download",
            params={"path": "input/dao.md"},
        )
        assert resp.status_code == 200
        assert "## Overview" in resp.text

    def test_download_all_zip(self, client):
        wid = self._completed(client)
        resp = client.get(f"/api/deep-research/product/workspaces/{wid}/files/download-all")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert resp.content[:2] == b"PK"

    def test_path_traversal_blocked(self, client):
        wid = _create(client)["workspace_id"]
        for evil in ("../", "../../etc/passwd", "input/../../../etc"):
            resp = client.get(
                f"/api/deep-research/product/workspaces/{wid}/files/download",
                params={"path": evil},
            )
            assert resp.status_code in (400, 404), f"traversal not blocked: {evil}"

    def test_files_404_unknown_workspace(self, client):
        resp = client.get("/api/deep-research/product/workspaces/workspace_zzz/files")
        assert resp.status_code == 404


# ============================================================
# Mode team SSOT（market resources；§8 兜底移除后 builtin 仅 framework×2）
# ============================================================

class TestModeTeamRegistered:
    def test_product_survey_team_modes_ssot_in_market(self):
        from dawei.entity.mode import KIND_BUSINESS
        from dawei.mode.registry import get_registry
        from dawei.workspace.product_survey_service import MODE_TEAM_MODES, SPEC

        # builtin 无业务模式（survey-* 编队 SSOT = market，装后经 Registry 可见）
        assert get_registry(None).all(kind=KIND_BUSINESS) == []
        for slug in MODE_TEAM_MODES:
            assert slug.startswith("survey-"), f"团队前缀约定违规: {slug}"
        # SPEC 每个 stage 的 mode 都在团队名单内（缺员时运行时静默降级为通用 mode）
        for stage in SPEC.stages:
            assert stage.mode in MODE_TEAM_MODES, f"stage {stage.id} mode '{stage.mode}' 未入团队名单"


# ============================================================
# Real execution (Phase 2 — mock Agent，保留产物校验/状态机真实逻辑)
# ============================================================


class _FakeUserWorkspace:
    """轻量假 UserWorkspace（仅承接 mode 切换）。"""

    def __init__(self):
        self.mode = None


class TestRealExecution:
    """真实执行路径: monkeypatch agent_execution_service.execute_agent_task。

    _execute_stage（提示词 / 会话持久化 / 产物校验 / token 估算）与 GATE 状态机全真实运行。
    """

    @staticmethod
    def _svc():
        from dawei.workspace.product_survey_service import product_survey_service

        return product_survey_service

    def _install_fake_agent(self, monkeypatch, fail_stages=None, candidates=None):
        """安装假执行服务：模拟 agent 写契约产物 + 消息持久化（可注入失败 stage / 真实 candidates）。"""
        from dawei.agentic import agent_execution_service as aes_module
        from dawei.workspace.product_survey_service import STAGE_ARTIFACTS

        fail = fail_stages if fail_stages is not None else set()

        async def fake_execute(**kwargs):
            import pathlib
            import re as _re2

            prompt = kwargs["message"]
            # 从提示词解析 stage（隐式验证提示词含 stage 头与契约产物路径）
            sid = _re2.search(r"【产品调研流水线 · (stage-\d+-[a-z-]+)", prompt).group(1)
            if sid in fail:
                raise RuntimeError(f"mock agent failure at {sid}")
            # 锚定「## 3. 本阶段必须产出的文件」小节内的路径（避免误取上游产物）
            section3 = prompt.split("## 3. 本阶段必须产出的文件", 1)[1].split("## 4.", 1)[0]
            stage_prefix = _re2.search(r"(output/[\w-]+/[\w-]+)/", section3).group(1)
            root = pathlib.Path(_re2.search(r"工作区根目录：(\S+)", prompt).group(1))
            stage_dir = root / stage_prefix
            stage_dir.mkdir(parents=True, exist_ok=True)
            for rel in STAGE_ARTIFACTS[sid]:
                f = stage_dir / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                if sid == "stage-02-product-collect" and rel == "candidates.jsonl" and candidates:
                    f.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in candidates), encoding="utf-8")
                elif rel.endswith(".json"):
                    f.write_text('{"ok": true}', encoding="utf-8")
                elif rel.endswith(".jsonl"):
                    f.write_text('{"dimension": "D1", "product_name": "Mock"}', encoding="utf-8")
                else:
                    f.write_text(f"# real-ish {sid}/{rel}\n\n内容段落。\n", encoding="utf-8")
            if sid == "stage-10-export":
                (stage_dir / "report.pdf").write_bytes(b"%PDF-1.4 mock-real")
            # 模拟 agent_execution_service 的消息持久化契约（用户提示词 + assistant 总结）
            from dawei.conversation.conversation_history_manager import ConversationHistoryManager
            from dawei.entity.lm_messages import AssistantMessage, UserMessage

            mgr = ConversationHistoryManager(workspace_path=str(root))
            conv = await mgr.get_by_id(kwargs["session_id"])
            conv.messages.append(UserMessage(id=f"u-{sid}", content=prompt))
            conv.messages.append(AssistantMessage(id=f"a-{sid}", content="本阶段完成（mock 总结）"))
            conv.message_count = len(conv.messages)
            await mgr.save_by_id(conv.id, conv)
            return {"final_output": "本阶段完成（mock 总结）"}

        # 框架在 _execute_stage 内惰性导入单例 → 补丁必须落在单例实例上
        monkeypatch.setattr(aes_module.agent_execution_service, "execute_agent_task", fake_execute)
        return fail  # 可变 set：测试中途 clear 实现故障恢复

    # ---- 全流程：GATE-0 → 停在 GATE-1 → GATE-1 通过 → 完成 ----

    def test_real_lifecycle_gate1_pause_and_complete(self, monkeypatch):
        import asyncio

        self._install_fake_agent(monkeypatch)
        svc = self._svc()
        meta = asyncio.run(svc.create_workspace(template_slug="ai-short-video", topic="AI 短视频生成", dry_run=False))
        wid = meta["workspace_id"]
        assert meta["dry_run"] is False

        # GATE-0 通过 → 真实执行（同步上下文 → asyncio.run 内联跑完）
        meta = svc.decide_gate(wid, "GATE-0", "approve")
        assert meta["status"] == "running"
        assert sum(1 for s in meta["stages"] if s["status"] == "completed") == 3  # stage-00..03
        assert meta["gates"][1]["status"] == "pending"  # GATE-1 等待
        # 每个 stage 有 agent 总结 + mode 已切换记录
        ws_dir = svc.storage_root / wid
        assert (ws_dir / "output/phase-00-prepare/stage-00-scope-init/stage_output.md").is_file()
        assert (ws_dir / "output/phase-00-prepare/stage-00-scope-init/scope.md").is_file()

        # GATE-1 通过 → 后半程至完成
        meta = svc.decide_gate(wid, "GATE-1", "approve")
        assert meta["status"] == "completed"
        assert all(s["status"] == "completed" for s in meta["stages"])
        assert meta["metrics"]["total_tokens"] > 0
        # stage-10 真实 PDF 汇总到 reports/
        assert (ws_dir / "reports/report.pdf").read_bytes() == b"%PDF-1.4 mock-real"
        assert (ws_dir / "reports/report_final.md").is_file()

    # ---- stage 失败 → failed + retry 恢复 ----

    def test_real_stage_failure_and_retry_recovery(self, monkeypatch):
        fail = self._install_fake_agent(monkeypatch, fail_stages={"stage-05-market-landscape"})
        svc = self._svc()
        meta = asyncio.run(svc.create_workspace(template_slug="ai-translation", topic="AI 翻译", dry_run=False))
        wid = meta["workspace_id"]

        meta = svc.decide_gate(wid, "GATE-0", "approve")
        meta = svc.decide_gate(wid, "GATE-1", "approve")
        # stage-05 两次重试均失败 → failed
        assert meta["status"] == "failed"
        stage05 = next(s for s in meta["stages"] if s["id"] == "stage-05-market-landscape")
        assert stage05["status"] == "failed"
        assert "mock agent failure" in stage05["error"]
        actions = [e["action"] for e in svc.get_audit_log(wid)]
        assert "stage.failed" in actions
        # 失败后停在该 stage（后续 stage 仍 pending）
        stage06 = next(s for s in meta["stages"] if s["id"] == "stage-06-trend-insight")
        assert stage06["status"] == "pending"

        # 故障清除 → 从失败 stage 重试 → 完成
        fail.clear()
        meta = svc.retry(wid, "stage-05-market-landscape")
        assert meta["status"] == "completed"
        assert all(s["status"] == "completed" for s in meta["stages"])

    # ---- 并发互斥 / executor 未绑定 FAST FAIL ----

    def test_real_launch_mutex(self):
        svc = self._svc()
        ex = svc.executor
        assert ex is not None
        ex._running.add("workspace_dummy")
        try:
            assert ex.launch("workspace_dummy") is False  # 已在执行 → 拒绝
        finally:
            ex._running.discard("workspace_dummy")

    def test_real_without_executor_fast_fail(self):
        from dawei.workspace.product_survey_service import ProductSurveyError, ProductSurveyService

        svc = ProductSurveyService()  # 独立实例：executor 未绑定
        assert svc.executor is None
        meta = asyncio.run(svc.create_workspace(template_slug="ai-short-video", topic="X", dry_run=False))
        wid = meta["workspace_id"]
        # GATE-0 approve 内部即调 start() → 503 FAST FAIL
        with pytest.raises(ProductSurveyError) as ei:
            svc.decide_gate(wid, "GATE-0", "approve")
        assert ei.value.status_code == 503
        gate0 = next(g for g in svc.get_workspace(wid)["gates"] if g["id"] == "GATE-0")
        assert gate0["status"] == "passed"

    # ---- GATE-1 预览读取真实 candidates.jsonl ----

    def test_gate1_preview_from_real_candidates(self, monkeypatch):
        # 12 × D1（china: i=3,6,9,12 → 4 条）+ 4 × D2
        candidates = (
            [
                {"dimension": "D1", "market": "china" if i % 3 == 0 else "overseas", "pricing_model": "订阅" if i % 2 == 0 else ""}
                for i in range(1, 13)
            ]
            + [{"dimension": "D2", "market": "overseas", "pricing_model": "免费增值"} for _ in range(4)]
        )
        self._install_fake_agent(monkeypatch, candidates=candidates)
        svc = self._svc()
        meta = asyncio.run(svc.create_workspace(template_slug="ai-short-video", topic="AI 短视频", dry_run=False))
        wid = meta["workspace_id"]
        meta = svc.decide_gate(wid, "GATE-0", "approve")

        preview = svc.get_workspace(wid)["gate1_preview"]
        by_dim = {d["dimension"]: d for d in preview["dimensions"]}
        assert preview["products_collected"] == 16
        assert by_dim["内容生成"]["count"] == 12 and by_dim["内容生成"]["ok"] is True
        assert by_dim["视频编辑"]["count"] == 4 and by_dim["视频编辑"]["ok"] is False
        assert preview["region"]["china"] == 4
        assert preview["region"]["overseas"] == 12
        assert preview["pricing_completeness"] == 0.62  # 10/16
