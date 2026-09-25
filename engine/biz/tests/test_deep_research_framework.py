# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Deep Research 通用框架单元测试（PRD §10 #1/#4/#5）。

覆盖:
- #1 Agent Team: industry-research-team modes SSOT = market resources（§8 兜底移除）/ stage-mode 覆盖 / references
- #4 复用扩展: pipelines 注册表 / industry-research 全生命周期（generic router）/ GATE-1 回退
- #5 质量提升: report.html 生成（md_to_html 含 XSS 转义）/ 报告分享 token / dao.md 历史归档

隔离: monkeypatch DAWEI_HOME → tmp_path（service.storage_root 动态读取）。
"""

import json

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("DAWEI_HOME", str(tmp_path))
    yield tmp_path


@pytest.fixture
def client():
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from dawei_biz.routers import deep_research, deep_research_product

    _app = FastAPI()
    _app.include_router(deep_research.router)
    _app.include_router(deep_research_product.router)
    return TestClient(_app)


# ============================================================
# #4 复用扩展: 注册表 + industry-research 全生命周期
# ============================================================


class TestPipelinesRegistry:
    def test_pipelines_listing(self, client):
        resp = client.get("/api/deep-research/pipelines")
        assert resp.status_code == 200
        data = resp.json()
        routes = {p["route"] for p in data["pipelines"]}
        assert {"product", "industry"} <= routes
        product = next(p for p in data["pipelines"] if p["route"] == "product")
        assert product["slug"] == "product-survey"
        assert product["stages"] == 11
        industry = next(p for p in data["pipelines"] if p["route"] == "industry")
        assert industry["stages"] == 7
        assert industry["gates"] == ["GATE-0", "GATE-1"]

    def test_unknown_pipeline_404(self, client):
        assert client.get("/api/deep-research/pipelines/nope/workspaces").status_code == 404


class TestIndustryLifecycle:
    """industry-research 复用框架: 只声明 spec + 2 个 hook，走通用 generic router 全流程。"""

    def test_full_dry_run_lifecycle_with_report_html(self, client, isolated_home):
        # 创建（通用端点）
        resp = client.post(
            "/api/deep-research/pipelines/industry/workspaces",
            json={"topic": "新能源行业"},
        )
        assert resp.status_code == 200
        meta = resp.json()
        wid = meta["workspace_id"]
        assert meta["team"] == "industry-research"
        assert len(meta["stages"]) == 7
        assert meta["dao_path"] == "input/dao.md"

        # GATE-0 通过 → dry-run 推进到 GATE-1 前
        resp = client.post(
            f"/api/deep-research/pipelines/industry/workspaces/{wid}/gates/GATE-0/decide",
            json={"action": "approve"},
        )
        assert resp.status_code == 200
        meta = resp.json()
        assert meta["status"] == "running"
        assert sum(1 for s in meta["stages"] if s["status"] == "completed") == 3  # stage-00..02
        assert meta["gates"][1]["status"] == "pending"

        # GATE-1 通过 → 完成后半程
        resp = client.post(
            f"/api/deep-research/pipelines/industry/workspaces/{wid}/gates/GATE-1/decide",
            json={"action": "approve"},
        )
        assert resp.status_code == 200
        meta = resp.json()
        assert meta["status"] == "completed"
        assert all(s["status"] == "completed" for s in meta["stages"])

        # #5 report.html: 报告定稿汇总 + Web 渲染版
        ws_dir = isolated_home / "industry-research" / wid
        assert (ws_dir / "reports" / "report_final.md").is_file()
        html = (ws_dir / "reports" / "report.html").read_text(encoding="utf-8")
        assert html.startswith("<!DOCTYPE html>")
        assert "<style>" in html
        assert "新能源行业" in html

        # 产物浏览器可见（通用端点）
        resp = client.get(f"/api/deep-research/pipelines/industry/workspaces/{wid}/files", params={"path": "reports"})
        names = {e["name"] for e in resp.json()["entries"]}
        assert {"report_final.md", "report.html"} <= names

        # inline 预览: 无 attachment 头
        resp = client.get(
            f"/api/deep-research/pipelines/industry/workspaces/{wid}/files/download",
            params={"path": "reports/report.html", "inline": "true"},
        )
        assert resp.status_code == 200
        assert "attachment" not in resp.headers.get("content-disposition", "")

    def test_gate1_reject_rollback_and_rescan(self, client):
        resp = client.post(
            "/api/deep-research/pipelines/industry/workspaces", json={"topic": "AI+法律行业"}
        )
        wid = resp.json()["workspace_id"]
        client.post(f"/api/deep-research/pipelines/industry/workspaces/{wid}/gates/GATE-0/decide", json={"action": "approve"})
        resp = client.post(
            f"/api/deep-research/pipelines/industry/workspaces/{wid}/gates/GATE-1/decide",
            json={"action": "reject", "note": "补充政策面资料"},
        )
        assert resp.status_code == 200
        meta = resp.json()
        # 回退 stage-02 补采后再次停在 GATE-1，轮次 +1
        assert meta["status"] == "running"
        gate1 = next(g for g in meta["gates"] if g["id"] == "GATE-1")
        assert gate1["round"] == 1
        assert gate1["status"] == "pending"
        stage02 = next(s for s in meta["stages"] if s["id"] == "stage-02-source-collect")
        assert stage02["status"] == "completed"  # 已补采重跑
        actions = [e["action"] for e in client.get(
            f"/api/deep-research/pipelines/industry/workspaces/{wid}/audit-log"
        ).json()["entries"]]
        assert "gate.rejected_rollback" in actions

    def test_executor_is_shared_generic_class(self):
        """industry 与 product 复用同一个通用执行器类（#4 核心断言）。"""
        from dawei_biz.services.deep_research_framework import ResearchExecutor
        from dawei_biz.services.industry_research_service import industry_research_service
        from dawei_biz.services.product_survey_executor import ProductSurveyExecutor

        assert isinstance(industry_research_service.executor, ResearchExecutor)
        assert ProductSurveyExecutor is ResearchExecutor


class TestIndustryModeTeamRegistered:
    """PRD §10 #1: industry-research-team mode team 的 SSOT = market resources
    （§8 兜底移除后 builtin 仅 framework×2，团队经 market 安装进入工作区）。"""

    def test_industry_team_modes_ssot_in_market(self):
        from dawei.entity.mode import KIND_BUSINESS
        from dawei.mode.registry import get_registry
        from dawei_biz.services.industry_research_service import MODE_TEAM_MODES

        # builtin 无业务模式（ind-* 编队 SSOT = market，装后经 Registry 可见）
        assert get_registry(None).all(kind=KIND_BUSINESS) == []
        for slug in MODE_TEAM_MODES:
            assert slug.startswith("ind-"), f"团队前缀约定违规: {slug}"

    def test_team_modes_cover_all_stage_modes(self):
        """SPEC 每个 stage 的 mode 都在 MODE_TEAM_MODES 名单内（名单 ↔ market yaml
        对齐锚点在 market 仓；缺员时运行时静默降级为通用 mode）。"""
        from dawei_biz.services.industry_research_service import MODE_TEAM_MODES, SPEC

        for stage in SPEC.stages:
            assert stage.mode in MODE_TEAM_MODES, f"stage {stage.id} mode '{stage.mode}' 未入团队名单"

    def test_references_written_on_create(self, client, isolated_home):
        """write_references 对齐 product：创建即落 references/industry-research-mode-team.json。"""
        resp = client.post("/api/deep-research/pipelines/industry/workspaces", json={"topic": "新能源行业"})
        wid = resp.json()["workspace_id"]
        ref = isolated_home / "industry-research" / wid / "references" / "industry-research-mode-team.json"
        assert ref.is_file()
        data = json.loads(ref.read_text(encoding="utf-8"))
        assert data["mode_team"] == "industry-research-team"
        assert set(data["modes"]) == {"ind-research-preparer", "ind-source-collector", "ind-landscape-analyst", "ind-report-writer", "ind-export-finisher"}
        assert data["source"].endswith("industry-research/modes.yaml")


# ============================================================
# #1 真实执行（mock Agent，mode team 已注册 → dry_run=false 可用）
# ============================================================


class _FakeUserWorkspace:
    def __init__(self):
        self.mode = None


class TestIndustryRealExecution:
    """industry 真实执行路径: monkeypatch agent_execution_service.execute_agent_task。

    _execute_stage（提示词 / 会话持久化 / 产物契约校验）与 GATE 状态机全真实运行。
    """

    def _install_fake_agent(self, monkeypatch, fail_stages=None):
        import pathlib
        import re as _re

        from dawei.agentic import agent_execution_service as aes_module
        from dawei_biz.services.industry_research_service import SPEC

        fail = fail_stages if fail_stages is not None else set()

        async def fake_execute(**kwargs):
            prompt = kwargs["message"]
            # 隐式验证: 提示词含【行业调研流水线 · stage-xx】头 + 契约产物 + 工作区根目录
            sid = _re.search(r"【行业调研流水线 · (stage-\d+-[a-z-]+)", prompt).group(1)
            if sid in fail:
                raise RuntimeError(f"mock agent failure at {sid}")
            section3 = prompt.split("## 3. 本阶段必须产出的文件", 1)[1].split("## 4.", 1)[0]
            stage_prefix = _re.search(r"(output/[\w-]+/[\w-]+)/", section3).group(1)
            root = pathlib.Path(_re.search(r"工作区根目录：(\S+)", prompt).group(1))
            stage_dir = root / stage_prefix
            stage_dir.mkdir(parents=True, exist_ok=True)
            for rel in SPEC.stage_artifacts[sid]:
                f = stage_dir / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                if rel.endswith(".json"):
                    f.write_text('{"ok": true}', encoding="utf-8")
                elif rel.endswith(".jsonl"):
                    f.write_text('{"id": "S001", "type": "market", "title": "Mock source"}', encoding="utf-8")
                else:
                    f.write_text(f"# {sid}/{rel}\n\n内容段落。\n", encoding="utf-8")
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
        return fail

    def test_industry_real_lifecycle(self, monkeypatch, isolated_home):
        import asyncio

        self._install_fake_agent(monkeypatch)
        from dawei_biz.services.industry_research_service import industry_research_service as svc

        meta = asyncio.run(svc.create_workspace(topic="新能源行业", dry_run=False))
        assert meta["dry_run"] is False
        wid = meta["workspace_id"]
        ws_dir = svc.storage_root / wid

        # Task-as-Workspace: 平台工作区结构 + 调研会话已创建
        assert (ws_dir / ".dawei" / "workspace.json").is_file()
        assert (ws_dir / ".dawei" / "deep_research.json").is_file()
        conversation_id = meta["conversation_id"]
        assert conversation_id
        assert (ws_dir / ".dawei" / "conversations" / f"{conversation_id}.json").is_file()

        # GATE-0 通过 → 真实执行至 GATE-1 前（stage-00..02 完成）
        meta = svc.decide_gate(wid, "GATE-0", "approve")
        assert meta["status"] == "running"
        assert sum(1 for s in meta["stages"] if s["status"] == "completed") == 3
        assert meta["gates"][1]["status"] == "pending"
        # 契约产物 + agent 总结已落盘
        assert (ws_dir / "output/phase-01-discovery/stage-02-source-collect/sources.jsonl").is_file()
        assert (ws_dir / "output/phase-01-discovery/stage-02-source-collect/stage_output.md").is_file()

        # GATE-1 通过 → 后半程至完成（stage-05 报告汇总 + report.html 由框架生成）
        meta = svc.decide_gate(wid, "GATE-1", "approve")
        assert meta["status"] == "completed"
        assert all(s["status"] == "completed" for s in meta["stages"])
        assert meta["metrics"]["total_tokens"] > 0
        assert (ws_dir / "reports/report_final.md").is_file()
        html = (ws_dir / "reports/report.html").read_text(encoding="utf-8")
        assert html.startswith("<!DOCTYPE html>")

        # 阶段消息持久化进调研会话（每 stage 1 条用户消息 + 1 条 assistant 总结）
        import json as _json

        conv = _json.loads((ws_dir / ".dawei" / "conversations" / f"{conversation_id}.json").read_text(encoding="utf-8"))
        roles = [m.get("role") for m in conv["messages"]]
        assert roles.count("user") == 7
        assert roles.count("assistant") == 8  # 1 条概览 + 7 条阶段总结

    def test_industry_real_stage_failure(self, monkeypatch):
        import asyncio

        self._install_fake_agent(monkeypatch, fail_stages={"stage-03-landscape"})
        from dawei_biz.services.industry_research_service import industry_research_service as svc

        meta = asyncio.run(svc.create_workspace(topic="AI+法律行业", dry_run=False))
        wid = meta["workspace_id"]
        meta = svc.decide_gate(wid, "GATE-0", "approve")
        meta = svc.decide_gate(wid, "GATE-1", "approve")
        # stage-03 两次重试均失败 → failed，后续 stage 保持 pending
        assert meta["status"] == "failed"
        stage03 = next(s for s in meta["stages"] if s["id"] == "stage-03-landscape")
        assert stage03["status"] == "failed"
        assert "mock agent failure" in stage03["error"]
        stage04 = next(s for s in meta["stages"] if s["id"] == "stage-04-value-chain")
        assert stage04["status"] == "pending"


# ============================================================
# #5 质量提升: 分享 / dao 历史 / md_to_html
# ============================================================


class TestReportShare:
    def _completed_product_ws(self, client):
        resp = client.post(
            "/api/deep-research/product/workspaces",
            json={"template_slug": "ai-short-video", "topic": "AI 短视频生成"},
        )
        wid = resp.json()["workspace_id"]
        client.post(f"/api/deep-research/product/workspaces/{wid}/gates/GATE-0/decide", json={"action": "approve"})
        client.post(f"/api/deep-research/product/workspaces/{wid}/gates/GATE-1/decide", json={"action": "approve"})
        return wid

    def test_share_requires_completed(self, client):
        resp = client.post(
            "/api/deep-research/product/workspaces",
            json={"template_slug": "ai-short-video", "topic": "AI 翻译"},
        )
        wid = resp.json()["workspace_id"]
        assert client.post(f"/api/deep-research/product/workspaces/{wid}/share").status_code == 409

    def test_share_token_public_lookup_and_audit(self, client):
        wid = self._completed_product_ws(client)
        resp = client.post(f"/api/deep-research/product/workspaces/{wid}/share")
        assert resp.status_code == 200
        token = resp.json()["token"]
        assert len(token) == 16

        # 公开端点（跨流水线反查）
        resp = client.get(f"/api/deep-research/share/{token}")
        assert resp.status_code == 200
        shared = resp.json()
        assert shared["pipeline"]["slug"] == "product-survey"
        assert shared["topic"] == "AI 短视频生成"
        assert shared["report_md"]  # 报告全文
        assert "<!DOCTYPE html>" in shared["report_html"]

        # 审计记录
        actions = [e["action"] for e in client.get(f"/api/deep-research/product/workspaces/{wid}/audit-log").json()["entries"]]
        assert "report.shared" in actions

        # 未知 token → 404
        assert client.get("/api/deep-research/share/deadbeefdeadbeef").status_code == 404

        # 分享索引文件不污染工作区列表
        listing = client.get("/api/deep-research/product/workspaces").json()
        assert all(w["workspace_id"] for w in listing["workspaces"])

    def test_share_industry_report_cross_pipeline(self, client):
        resp = client.post("/api/deep-research/pipelines/industry/workspaces", json={"topic": "新能源行业"})
        wid = resp.json()["workspace_id"]
        client.post(f"/api/deep-research/pipelines/industry/workspaces/{wid}/gates/GATE-0/decide", json={"action": "approve"})
        client.post(f"/api/deep-research/pipelines/industry/workspaces/{wid}/gates/GATE-1/decide", json={"action": "approve"})
        token = client.post(f"/api/deep-research/pipelines/industry/workspaces/{wid}/share").json()["token"]
        shared = client.get(f"/api/deep-research/share/{token}").json()
        assert shared["pipeline"]["name"] == "行业调研"


class TestDeleteWorkspace:
    """删除工作区：目录 + 系统索引注册 + 分享 token 一并清理（FAST FAIL 404/409）。"""

    def _create_industry(self, client, topic="删除验证调研"):
        resp = client.post("/api/deep-research/pipelines/industry/workspaces", json={"topic": topic})
        assert resp.status_code == 200
        return resp.json()["workspace_id"]

    def test_delete_removes_dir_and_registry(self, client, isolated_home):
        import json as _json

        wid = self._create_industry(client)
        assert (isolated_home / "industry-research" / wid).is_dir()
        registry = _json.loads((isolated_home / "workspaces.json").read_text(encoding="utf-8"))
        assert any(w["id"] == wid for w in registry["workspaces"])

        resp = client.delete(f"/api/deep-research/pipelines/industry/workspaces/{wid}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # 目录 + 系统索引注册一并移除
        assert not (isolated_home / "industry-research" / wid).exists()
        registry = _json.loads((isolated_home / "workspaces.json").read_text(encoding="utf-8"))
        assert not any(w["id"] == wid for w in registry["workspaces"])
        # 列表不再包含；详情/二次删除 FAST FAIL 404
        listing = client.get("/api/deep-research/pipelines/industry/workspaces").json()
        assert all(w["workspace_id"] != wid for w in listing["workspaces"])
        assert client.get(f"/api/deep-research/pipelines/industry/workspaces/{wid}").status_code == 404
        assert client.delete(f"/api/deep-research/pipelines/industry/workspaces/{wid}").status_code == 404

    def test_delete_clears_share_token(self, client, isolated_home):
        import json as _json

        wid = self._create_industry(client, topic="分享后删除调研")
        client.post(f"/api/deep-research/pipelines/industry/workspaces/{wid}/gates/GATE-0/decide", json={"action": "approve"})
        client.post(f"/api/deep-research/pipelines/industry/workspaces/{wid}/gates/GATE-1/decide", json={"action": "approve"})
        token = client.post(f"/api/deep-research/pipelines/industry/workspaces/{wid}/share").json()["token"]
        assert client.get(f"/api/deep-research/share/{token}").status_code == 200

        assert client.delete(f"/api/deep-research/pipelines/industry/workspaces/{wid}").status_code == 200

        # token 失效 + .shares.json 清空
        assert client.get(f"/api/deep-research/share/{token}").status_code == 404
        shares = _json.loads((isolated_home / "industry-research" / ".shares.json").read_text(encoding="utf-8"))
        assert token not in shares["tokens"]

    def test_delete_running_workspace_409(self, client):
        from dawei_biz.services.industry_research_service import industry_research_service as svc

        wid = self._create_industry(client)
        svc.executor._running.add(wid)  # 模拟执行中
        try:
            resp = client.delete(f"/api/deep-research/pipelines/industry/workspaces/{wid}")
            assert resp.status_code == 409
            assert (svc.storage_root / wid).is_dir()  # 目录未动
        finally:
            svc.executor._running.discard(wid)


class TestDaoHistory:
    def test_reject_archives_and_history_endpoint(self, client, isolated_home):
        from dawei_biz.services.product_survey_service import product_survey_service as svc

        resp = client.post(
            "/api/deep-research/product/workspaces",
            json={"template_slug": "ai-short-video", "topic": "AI 短视频生成"},
        )
        wid = resp.json()["workspace_id"]

        # 初次拒绝 → 归档 v1 + 重新生成
        client.post(
            f"/api/deep-research/product/workspaces/{wid}/gates/GATE-0/decide",
            json={"action": "reject", "note": "聚焦海外"},
        )
        ws_dir = isolated_home / "product-survey" / wid
        archived = list((ws_dir / "input" / "dao.history").glob("*.md"))
        assert len(archived) == 1
        assert archived[0].name.startswith("GATE-0-r1-")

        resp = client.get(f"/api/deep-research/product/workspaces/{wid}/dao-history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["history"][0]["gate"] == "GATE-0"
        assert data["history"][0]["round"] == 1
        assert data["current"] and data["current"] != data["history"][0]["content"]
        assert "聚焦海外" in data["current"]  # 拒绝备注附加到再生成版本

        # edit 动作同样归档
        client.post(
            f"/api/deep-research/product/workspaces/{wid}/gates/GATE-0/decide",
            json={"action": "edit", "dao_md": svc.render_dao_md("ai-short-video", "AI 短视频生成") + "\n<!-- 手工补充 -->\n"},
        )
        assert len(list((ws_dir / "input" / "dao.history").glob("*.md"))) == 2
        data = client.get(f"/api/deep-research/product/workspaces/{wid}/dao-history").json()
        assert data["history"][1]["round"] == 2


class TestMdToHtml:
    def test_structure_and_escaping(self):
        from dawei_biz.services.deep_research_framework import md_to_html

        md = "# 标题\n\n**粗体** 与 `code` 和 [链接](https://example.com)\n\n- 甲\n- 乙\n\n> 引用\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n<script>alert(1)</script>\n"
        html = md_to_html(md, title="测试")
        assert html.startswith("<!DOCTYPE html>")
        assert "<h1>标题</h1>" in html
        assert "<strong>粗体</strong>" in html
        assert "<code>code</code>" in html
        assert '<a href="https://example.com"' in html
        assert "<ul>" in html and "<li>甲</li>" in html
        assert "<blockquote>" in html
        assert "<table>" in html and "<th>A</th>" in html
        # XSS: 脚本标签被转义
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "<title>测试</title>" in html
