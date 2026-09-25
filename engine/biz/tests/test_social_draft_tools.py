"""社媒编辑器 Agent 工具组 —— 测试即规格(设计:高级编辑和资产管理.md A.3/A.5)。

  S1 session_context:绑定/读取/清除语义
  S2 social_read_draft:拉取最新稿(base_hash 供提案防冲突)/ 未关联稿件人话 / 401 翻译
  S3 social_rule_check:auth_token 透传(local_context,绝不进工具参数)
  S4 social_lookup_trending:平台过滤 + 条数夹取
  S5 social_propose_edit:提案形状(整段替换 + base_hash 回传)/ 空值拒绝
  S6 social_validate_artifact:契约校验(对齐 to_content_payload)
  S7 工具组注册与内置专家:TOOL_GROUPS["social"] 与实现一致;3 专家 modes 就位
"""

from __future__ import annotations

import json

import pytest

from dawei.core import local_context
from dawei_biz.bridges.social import bridge as bridge_module
from dawei_biz.bridges.social import session_context
from dawei_biz.tools import social_draft_tools as sdt

CONTENT = {
    "id": "c-1",
    "title": "新品测评",
    "type": "text",
    "status": "draft",
    "brand_id": "b-1",
    "target_platforms": ["xiaohongshu", "wechat_mp"],
    "body": {
        "schema_version": 1,
        "variants": {
            "xiaohongshu": {"text": "笔记正文,共十个字。"},
            "wechat_mp": {"text": "长文正文"},
        },
    },
    "compliance_report": {"passed": False, "violations": [{"rule_id": "ad_law_9"}]},
}


@pytest.fixture(autouse=True)
def _clean_ctx():
    session_context.set_social_context(None)
    local_context.set_auth_token(None)
    yield
    session_context.set_social_context(None)
    local_context.set_auth_token(None)


@pytest.mark.unit
class TestSessionContext:
    def test_s1_bind_and_read(self):
        bound = session_context.set_social_context(
            {"content_id": "c-1", "tenant_id": "t-1"})
        assert bound is not None
        assert bound.content_id == "c-1"
        assert bound.tenant_id == "t-1"
        ctx = session_context.get_social_context()
        assert ctx is not None
        assert ctx.content_id == "c-1"

    def test_s1_garbage_clears(self):
        session_context.set_social_context({"content_id": "c-1"})
        assert session_context.get_social_context() is not None
        session_context.set_social_context("not-a-dict")
        assert session_context.get_social_context() is None
        session_context.set_social_context({})
        assert session_context.get_social_context() is None


@pytest.mark.unit
class TestReadDraft:
    def test_s2_pull_latest_with_base_hash(self, monkeypatch):
        captured = {}

        def fake_get(content_id, *, tenant_id, auth_token=None, base_url=None):
            captured["cid"] = content_id
            captured["tenant"] = tenant_id
            captured["token"] = auth_token
            return CONTENT

        monkeypatch.setattr(bridge_module, "get_content", fake_get)
        session_context.set_social_context({"content_id": "c-1", "tenant_id": "t-1"})
        local_context.set_auth_token("jwt-abc")

        out = json.loads(sdt.SocialReadDraftTool()._run())
        assert captured["cid"] == "c-1"
        assert captured["tenant"] == "t-1"
        assert captured["token"] == "jwt-abc"
        assert out["title"] == "新品测评"
        assert out["variants"]["xiaohongshu"]["chars"] == len("笔记正文,共十个字。")
        # base_hash 是提案防冲突锚点:同文本稳定,异文本不同
        assert out["variants"]["xiaohongshu"]["base_hash"] == sdt._base_hash("笔记正文,共十个字。")
        assert out["variants"]["xiaohongshu"]["base_hash"] != out["variants"]["wechat_mp"]["base_hash"]
        assert out["violations_count"] == 1

    def test_s2_no_context_human_copy(self):
        assert "未关联稿件" in sdt.SocialReadDraftTool()._run()

    def test_s2_401_translated(self, monkeypatch):
        import httpx

        def boom(*a, **k):
            raise httpx.HTTPStatusError(
                "401", request=httpx.Request("GET", "x"),
                response=httpx.Response(401))

        monkeypatch.setattr(bridge_module, "get_content", boom)
        session_context.set_social_context({"content_id": "c-1", "tenant_id": "t-1"})
        assert "重新登录" in sdt.SocialReadDraftTool()._run()


@pytest.mark.unit
class TestRuleCheck:
    def test_s3_token_passthrough(self, monkeypatch):
        seen = {}

        def fake_pre(text, *, tenant_id, auth_token=None, base_url=None):
            seen.update({"text": text, "tenant": tenant_id, "token": auth_token})
            return {"passed": True, "violations": []}

        monkeypatch.setattr(bridge_module, "precheck_rules", fake_pre)
        session_context.set_social_context({"content_id": "c-1", "tenant_id": "t-9"})
        local_context.set_auth_token("jwt-xyz")
        out = json.loads(sdt.SocialRuleCheckTool()._run(text="国家级最佳"))
        assert seen["token"] == "jwt-xyz"
        assert seen["tenant"] == "t-9"
        assert out["passed"] is True


@pytest.mark.unit
class TestLookupTrending:
    def test_s4_filter_and_clamp(self, monkeypatch):
        items = [{"platform": p, "title": f"t{i}"} for i, p in
                 enumerate(["weibo"] * 12 + ["zhihu"] * 3)]
        monkeypatch.setattr(bridge_module, "fetch_trending", lambda **_k: items)
        session_context.set_social_context({"content_id": "c-1", "tenant_id": "t-1"})
        out = json.loads(sdt.SocialLookupTrendingTool()._run(platform="zhihu", top=99))
        assert out["count"] == 3
        assert all(i["platform"] == "zhihu" for i in out["items"])


@pytest.mark.unit
class TestProposeEdit:
    def test_s5_shape(self):
        out = json.loads(sdt.SocialProposeEditTool()._run(
            platform="xiaohongshu", replacement_text="改后正文",
            rationale="更口语化", base_hash="abc1234567"))
        assert out["status"] == "proposed"
        assert out["platform"] == "xiaohongshu"
        assert out["base_hash"] == "abc1234567"
        assert out["chars"] == 4
        assert len(out["proposal_id"]) == 8

    def test_s5_empty_rejected(self):
        assert "platform" in sdt.SocialProposeEditTool()._run(
            platform="", replacement_text="x")
        assert "replacement_text" in sdt.SocialProposeEditTool()._run(
            platform="weibo", replacement_text="  ")


@pytest.mark.unit
class TestValidateArtifact:
    def test_s6_ok(self):
        art = {"title": "T", "variants": {"xiaohongshu": {"text": "正文"}}}
        out = json.loads(sdt.SocialValidateArtifactTool()._run(json.dumps(art, ensure_ascii=False)))
        assert out["ok"] is True
        assert out["platforms"]["xiaohongshu"] == 2

    def test_s6_bad_json_and_schema(self):
        assert json.loads(sdt.SocialValidateArtifactTool()._run("not-json"))["ok"] is False
        bad = {"variants": {"x": {"text": "t"}}}  # 缺 title
        assert json.loads(sdt.SocialValidateArtifactTool()._run(json.dumps(bad)))["ok"] is False


@pytest.mark.unit
class TestRegistration:
    def test_s7_group_matches_tools(self):
        from dawei.tools.tool_manager import get_all_tool_groups

        group = get_all_tool_groups().get("social", {}).get("custom_tools", [])
        assert set(group) == {
            "social_read_draft", "social_rule_check", "social_lookup_trending",
            "social_propose_edit", "social_validate_artifact", "social_generate_images",
        }

    def test_s7_experts_not_builtin_ssot_in_market(self):
        """§8 兜底移除：社媒专家不再内置（SSOT = market social-team/social-tools，
        经 market 安装进入 workspace）；builtin 仅剩 framework×2。"""
        from dawei.entity.mode import FRAMEWORK_SLUGS
        from dawei.mode.mode_manager import ModeConfigLoader

        modes = ModeConfigLoader().load_builtin_modes()
        assert set(modes) == set(FRAMEWORK_SLUGS)
        for slug in ("soc-content-drafter", "soc-content-guardian", "soc-trend-spotter"):
            assert slug not in modes, f"{slug} 不应再随 builtin 内置"


@pytest.mark.unit
class TestProgressiveDisclosureTier:
    def test_s8_social_experts_tools_in_tier0(self):
        """渐进式披露(SessionToolPool)只放行 Tier-0/1——社媒专家的 5 工具必须
        在 MODE_CORE_OVERRIDES 常驻,否则永远到不了 LLM 工具面(2026-08-29 E2E 实锤)。"""
        from dawei.tools.tool_discovery.core_tools import get_core_tools_for_mode

        drafter = get_core_tools_for_mode("soc-content-drafter")
        assert {
            "social_read_draft", "social_rule_check", "social_lookup_trending",
            "social_propose_edit", "social_validate_artifact",
        } <= drafter
        guardian = get_core_tools_for_mode("soc-content-guardian")
        assert {"social_read_draft", "social_rule_check", "social_propose_edit"} <= guardian
        spotter = get_core_tools_for_mode("soc-trend-spotter")
        assert {"social_read_draft", "social_lookup_trending", "social_propose_edit"} <= spotter


@pytest.mark.unit
class TestGenerateImages:
    def test_m2_tool_registers_ids_and_endpoint_serves(self, monkeypatch):
        import asyncio

        from dawei_biz.bridges.social import router as router_mod
        from dawei_biz.bridges.social import service as svc
        from dawei_biz.tools import social_draft_tools as sdt2

        async def fake_gen(prompt, *, count=1, style="", ratio="", reference_b64="", provider="", auth_token=""):
            return [f"data:image/png;base64,IMG{i}" for i in range(count)]

        # 桩与被替身同 async 形状(第二十九轮教训)
        monkeypatch.setattr(svc, "default_image_generate", fake_gen)
        sdt2.IMAGE_REGISTRY.clear()

        out = json.loads(sdt2.SocialGenerateImagesTool()._run(prompt="夏日办公室", count=3))
        assert out["ok"] is True
        assert out["count"] == 3
        assert len(out["image_ids"]) == 3

        # 端点取图(最小 FastAPI,只挂 social router——不拉全量 app 的 WS/调度器)
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from dawei_biz.bridges.social.router import router as social_router

        app = FastAPI()
        app.include_router(social_router)
        with TestClient(app) as c:
            r = c.get(f"/api/social/images/{out['image_ids'][0]}")
            assert r.status_code == 200
            assert r.json()["url"].startswith("data:image/png")
            assert c.get("/api/social/images/nope").status_code == 404

    def test_m2_empty_prompt_rejected(self):
        assert "prompt" in sdt.SocialGenerateImagesTool()._run(prompt="  ")

    def test_m2_drafter_tier_includes_images(self):
        from dawei.tools.tool_discovery.core_tools import get_core_tools_for_mode

        assert "social_generate_images" in get_core_tools_for_mode("soc-content-drafter")
        assert "social_generate_images" not in get_core_tools_for_mode("soc-content-guardian")
