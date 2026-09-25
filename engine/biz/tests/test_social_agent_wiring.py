"""社媒 Agent 接线 —— 测试即规格(落盘协议/生成服务/sidecar 路由)。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dawei_biz.bridges.social import service as service_module
from dawei_biz.bridges.social.artifact_schema import (
    ArtifactSchemaError,
    extract_structured_output,
    to_content_payload,
)
from dawei_biz.bridges.social.service import (
    _extract_image,
    build_image_prompt,
    compose_image_prompt,
    generate_variants,
)

# ── 落盘协议 ────────────────────────────────────────────────

VALID = {
    "title": "新品测评",
    "variants": {"xiaohongshu": {"text": "笔记正文…"}, "wechat_mp": {"text": "长文…"}},
    "source": {"session_id": "s-1"},
}


@pytest.mark.unit
class TestArtifactSchema:
    def test_as1_payload_shape(self):
        p = to_content_payload(VALID)
        assert p["brand_id"] == "default"
        assert p["title"] == "新品测评"
        assert p["target_platforms"] == ["xiaohongshu", "wechat_mp"]
        assert p["body"]["schema_version"] == 1
        assert p["body"]["variants"]["xiaohongshu"]["text"] == "笔记正文…"
        assert p["source_ref"]["origin"] == "agent_session"
        assert p["source_ref"]["session_id"] == "s-1"

    def test_as1_missing_title_rejected(self):
        with pytest.raises(ArtifactSchemaError):
            to_content_payload({"variants": {"x": {"text": "t"}}})

    def test_as1_empty_variants_rejected(self):
        with pytest.raises(ArtifactSchemaError):
            to_content_payload({"title": "T", "variants": {}})

    def test_as1_empty_text_rejected(self):
        """空稿件防垃圾入内容库"""
        with pytest.raises(ArtifactSchemaError):
            to_content_payload({"title": "T", "variants": {"x": {"text": "  "}}})

    def test_as1_aigc_label_passthrough(self):
        p = to_content_payload({
            "title": "T",
            "variants": {"x": {"text": "t", "aigc_label": "本文由 AI 辅助生成"}},
        })
        assert p["body"]["variants"]["x"]["aigc_label"] == "本文由 AI 辅助生成"

    def test_as2_extract_from_fenced_json(self):
        msg = '好的,产出如下:\n```json\n{"title": "T", "variants": {"x": {"text": "t"}}}\n```\n以上。'
        out = extract_structured_output(msg)
        assert out and out["title"] == "T"

    def test_as2_no_fence_returns_none(self):
        assert extract_structured_output("直接回答,没有围栏") is None

    def test_as2_bad_json_in_fence_returns_none(self):
        assert extract_structured_output('```json\n{"title": nope}\n```') is None

    def test_as1_non_dict_rejected(self):
        with pytest.raises(ArtifactSchemaError):
            to_content_payload(["not", "a", "dict"])

    def test_as1_invalid_type_rejected(self):
        with pytest.raises(ArtifactSchemaError):
            to_content_payload({"title": "T", "type": "live",
                                "variants": {"x": {"text": "t"}}})

    def test_as1_explicit_platforms_override(self):
        p = to_content_payload({"title": "T", "platforms": ["weibo"],
                                "variants": {"x": {"text": "t"}, "y": {"text": "t2"}}})
        assert p["target_platforms"] == ["weibo"]

    def test_as1_variant_not_dict_rejected(self):
        with pytest.raises(ArtifactSchemaError):
            to_content_payload({"title": "T", "variants": {"x": "裸字符串"}})


# ── 一源多稿服务 ────────────────────────────────────────────

FAKE_REPLY = """改写完成:
```json
{"title": "源标题", "type": "text",
 "variants": {"xiaohongshu": {"text": "小红书版 #标签", "aigc_label": "本文由 AI 辅助生成"},
              "wechat_mp": {"text": "公众号长文版"}}}
```"""


@pytest.mark.unit
class TestGenerateService:
    def test_gs1_structured_output(self):
        out = generate_variants("源内容", ["xiaohongshu", "wechat_mp"], llm_call=lambda s, u: FAKE_REPLY)
        assert out["title"] == "源标题"
        assert set(out["variants"]) == {"xiaohongshu", "wechat_mp"}
        assert out["variants"]["xiaohongshu"]["aigc_label"]

    def test_gs1_empty_source_rejected(self):
        with pytest.raises(ValueError):
            generate_variants(" ", ["x"], llm_call=lambda s, u: FAKE_REPLY)

    def test_gs1_unparseable_reply_rejected(self):
        with pytest.raises(ValueError):
            generate_variants("源", ["x"], llm_call=lambda s, u: "无结构化输出")

    def test_gs1_empty_platforms_rejected(self):
        with pytest.raises(ValueError):
            generate_variants("源", [], llm_call=lambda s, u: FAKE_REPLY)

    def test_gs1_platforms_default_backfilled(self):
        """模型未回 platforms 时以请求平台列表回填。"""
        out = generate_variants("源", ["xhs", "weibo"], llm_call=lambda s, u: FAKE_REPLY)
        assert out["platforms"] == ["xhs", "weibo"]


# ── sidecar 路由(bridge 打桩)──────────────────────────────


@pytest.fixture
def client(monkeypatch):
    from dawei_biz.bridges.social import router as social_router_module

    # LLM 与控制面全部打桩:路由行为测试不依赖外部
    monkeypatch.setattr(
        social_router_module.service, "default_text_call",
        lambda s, u, provider="", auth_token="": FAKE_REPLY,
    )
    captured: dict = {}

    def fake_push(payload, *, tenant_id, **kw):
        captured["payload"] = payload
        captured["tenant_id"] = tenant_id
        return {"id": "c-new-1", "status": "draft", **{k: payload[k] for k in ("title", "brand_id")}}

    monkeypatch.setattr(social_router_module.bridge, "push_artifact", fake_push)
    monkeypatch.setattr(
        social_router_module.bridge, "precheck_rules",
        lambda text, *, tenant_id, **kw: {"passed": False, "violations": [{"rule_id": "adv-abs-zuijia"}]},
    )

    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(social_router_module.router)
    return TestClient(app)


@pytest.mark.unit
class TestSidecarRoutes:
    def test_r1_generate(self, client):
        r = client.post("/api/social/generate", json={"source_text": "源", "platforms": ["xiaohongshu"]})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] and body["structured"]["variants"]["xiaohongshu"]["text"]

    def test_r2_artifact_pushes_to_control(self, client):
        r = client.post("/api/social/artifact", json={
            "structured": VALID, "brand_id": "b9", "tenant_id": "t9",
        })
        assert r.status_code == 200
        assert r.json()["content"]["id"] == "c-new-1"

    def test_r3_precheck_proxies(self, client):
        r = client.post("/api/social/precheck", json={"text": "最佳产品", "tenant_id": "t1"})
        assert r.status_code == 200
        assert r.json()["passed"] is False

    def test_r2_invalid_structured_422(self, client):
        r = client.post("/api/social/artifact", json={"structured": {"title": ""}})
        assert r.status_code == 422


# ── AI 配图(studio-images-ui.md §3)────────────────────────

DATA_URL = "data:image/png;base64,aGVsbG8="


@pytest.mark.unit
class TestImageService:
    def test_img1_build_prompt_extracts(self):
        out = build_image_prompt("正文" * 10, llm_call=lambda s, u: "“夏日办公室,签约文件,自然光”\n")
        assert out == "夏日办公室,签约文件,自然光"

    def test_img1_empty_text_rejected(self):
        with pytest.raises(ValueError):
            build_image_prompt(" ", llm_call=lambda s, u: "x")

    def test_img1_empty_reply_rejected(self):
        with pytest.raises(ValueError):
            build_image_prompt("正文", llm_call=lambda s, u: "  ")

    def test_img2_compose_appends_style_ratio(self):
        out = compose_image_prompt("画一张", style="插画", ratio="3:4")
        assert out == "画一张,插画,构图比例 3:4"

    def test_img2_compose_prompt_only(self):
        assert compose_image_prompt(" 画一张 ") == "画一张"

    def test_img3_extract_openrouter_shape(self):
        data = {"choices": [{"message": {"images": [{"image_url": {"url": DATA_URL}}]}}]}
        assert _extract_image(data) == DATA_URL

    def test_img3_extract_images_api_b64(self):
        assert _extract_image({"data": [{"b64_json": "aGVsbG8="}]}) == DATA_URL

    def test_img3_extract_remote_url(self):
        assert _extract_image({"data": [{"url": "https://cdn.example.com/x.png"}]}) == \
            "https://cdn.example.com/x.png"

    def test_img3_extract_none(self):
        assert _extract_image({"choices": [{"message": {"content": "纯文本"}}]}) is None
        assert _extract_image({}) is None


@pytest.mark.unit
class TestImageRoutes:
    def test_ir1_generate_returns_candidates(self, client, monkeypatch):
        async def fake(prompt, *, count=1, style="", ratio="", reference_b64="", provider="", auth_token=""):
            return [DATA_URL] * max(1, min(count, 4))

        monkeypatch.setattr(service_module, "default_image_generate", fake)
        r = client.post("/api/social/image-generate",
                        json={"prompt": "画一张", "count": 4, "ratio": "3:4"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] and len(body["images"]) == 4

    def test_ir1_count_clamped(self, client, monkeypatch):
        seen = {}

        async def fake(prompt, *, count=1, style="", ratio="", reference_b64="", provider="", auth_token=""):
            seen["count"] = count
            return [DATA_URL]

        monkeypatch.setattr(service_module, "default_image_generate", fake)
        r = client.post("/api/social/image-generate", json={"prompt": "x", "count": 9})
        assert r.status_code == 200
        assert seen["count"] == 4  # 路由边界夹取 [1,4]
        r = client.post("/api/social/image-generate", json={"prompt": "x", "count": 0})
        assert r.status_code == 200
        assert seen["count"] == 1

    def test_ir1_empty_prompt_422(self, client):
        r = client.post("/api/social/image-generate", json={"prompt": "  "})
        assert r.status_code == 422

    def test_ir1_llm_failure_503(self, client, monkeypatch):
        def boom(*a, **kw):
            raise RuntimeError("未配置 LLM 通道")

        monkeypatch.setattr(service_module, "default_image_generate", boom)
        r = client.post("/api/social/image-generate", json={"prompt": "x"})
        assert r.status_code == 503
        assert "生图通道不可用" in r.json()["detail"]

    def test_ir2_prompt_from_text(self, client, monkeypatch):
        monkeypatch.setattr(service_module, "default_image_prompt_call",
                            lambda s, u, provider="", auth_token="": "夏日办公室,自然光")
        r = client.post("/api/social/image-prompt", json={"text": "正文内容"})
        assert r.status_code == 200
        assert r.json()["prompt"] == "夏日办公室,自然光"

    def test_ir2_empty_text_422(self, client):
        r = client.post("/api/social/image-prompt", json={"text": " "})
        assert r.status_code == 422


@pytest.mark.unit
class TestDefaultLlmCall:
    def test_dlc_keyword_message_construction(self, monkeypatch):
        """真实调用形态:消息以关键字构造(pydantic v2),complete 返回 dict。"""
        captured = {}

        class FakeProvider:
            async def complete(self, messages):
                captured["messages"] = messages
                return {"content": "回复文本", "tool_calls": None}

        async def fake_provider():
            return FakeProvider()

        monkeypatch.setattr(service_module, "_provider", fake_provider)
        out = service_module.default_llm_call("系统提示", "用户内容")
        assert out == "回复文本"
        roles = [getattr(getattr(m, "role", None), "value", None) for m in captured["messages"]]
        assert roles == ["system", "user"]
        assert captured["messages"][0].content == "系统提示"

    def test_dlc_event_loop_context(self, monkeypatch):
        """事件循环线程内调用:转独立线程跑,不炸 RuntimeError。"""
        import asyncio

        async def fake_provider():
            class P:
                async def complete(self, messages):
                    return {"content": "循环内OK"}

            return P()

        monkeypatch.setattr(service_module, "_provider", fake_provider)

        async def in_loop():
            return service_module.default_llm_call("s", "u")

        assert asyncio.run(in_loop()) == "循环内OK"


@pytest.mark.unit
class TestProviderSelection:
    def test_pv1_resolve_by_name_then_current_fallback(self):
        import asyncio
        from types import SimpleNamespace

        from dawei_biz.bridges.social.service import _resolve_config

        named = SimpleNamespace(
            config=SimpleNamespace(api_key="k1", base_url="https://a/v1", model_id="m1"))
        current = SimpleNamespace(
            config=SimpleNamespace(api_key="k2", base_url="https://b/v1", model_id="m2"))

        class FakeWrap:
            def get_config(self, name):
                return named if name == "我的服务商" else None

            def get_current_config(self):
                return current

            def get_all_configs(self):
                return {"我的服务商": named, "当前": current}

            def set_gateway_token(self, token):
                pass

            async def _register_gateway_config_async(self, model_id):
                return False  # 网关注册失败 → 回落当前

        w = FakeWrap()
        # _resolve_config 为协程(网关注册路径),异步求值
        assert asyncio.run(_resolve_config(w, "我的服务商")).api_key == "k1"      # 按名命中
        assert asyncio.run(_resolve_config(w, "")).api_key == "k2"  # 空名回落当前
        assert asyncio.run(_resolve_config(w, "不存在的")).api_key == "k2"  # 未知名回落当前

    def test_pv1_gateway_model_registered_on_miss(self):
        """llm-pricing 网关模型:本地未命中 → 动态注册后命中(用户 token 透传)。"""
        import asyncio
        from types import SimpleNamespace

        from dawei_biz.bridges.social.service import _resolve_config

        gw_cfg = SimpleNamespace(
            config=SimpleNamespace(api_key="tok", base_url="https://gw/llm", model_id="glm-4.7"))
        seen = {}

        class GatewayWrap:
            def get_config(self, name):
                # 注册前不在本地(网关模型动态注册的时序)
                if name == "glm-4.7" and seen.get("registered") == name:
                    return gw_cfg
                return None

            def get_current_config(self):
                return None

            def get_all_configs(self):
                return {"glm-4.7": gw_cfg} if seen.get("registered") else {}

            def set_gateway_token(self, token):
                seen["token"] = token

            async def _register_gateway_config_async(self, model_id):
                seen["registered"] = model_id
                return True

        cfg = asyncio.run(_resolve_config(GatewayWrap(), "glm-4.7", "user-jwt"))
        assert cfg.api_key == "tok"
        assert seen == {"token": "user-jwt", "registered": "glm-4.7"}

    def test_pv1_no_config_error_lists_known(self):
        import asyncio

        from dawei_biz.bridges.social.service import _resolve_config

        class EmptyWrap:
            def get_config(self, name):
                return None

            def get_current_config(self):
                return None

            def get_all_configs(self):
                return {}

            def set_gateway_token(self, token):
                pass

            async def _register_gateway_config_async(self, model_id):
                return False

        with pytest.raises(RuntimeError, match="未配置 LLM 通道"):
            asyncio.run(_resolve_config(EmptyWrap(), ""))

    def test_pv2_router_passes_provider(self, client, monkeypatch):
        seen = {}

        async def fake(prompt, *, count=1, style="", ratio="", reference_b64="", provider="", auth_token=""):
            seen["provider"] = provider
            return [DATA_URL]

        monkeypatch.setattr(service_module, "default_image_generate", fake)
        client.post("/api/social/image-generate", json={"prompt": "x", "provider": "我的服务商"})
        assert seen["provider"] == "我的服务商"

    def test_pv3_prompt_uses_provider_channel(self, client, monkeypatch):
        seen = {}

        def fake_call(system, user, provider="", auth_token=""):
            seen["provider"] = provider
            return "夏日办公室,自然光"

        monkeypatch.setattr(service_module, "default_image_prompt_call", fake_call)
        r = client.post("/api/social/image-prompt",
                        json={"text": "正文", "provider": "p2"})
        assert r.status_code == 200
        assert seen["provider"] == "p2"


@pytest.mark.unit
class TestTextGenerateProviderVoice:
    def test_tg1_brand_voice_injected_into_system(self):
        seen = {}

        def llm(system, user):
            seen["system"] = system
            return FAKE_REPLY

        out = generate_variants(
            "源内容", ["xhs"], llm_call=llm,
            brand_voice="专业、克制、不说网络梗",
        )
        assert out["title"]
        assert "品牌 Voice" in seen["system"]
        assert "专业、克制" in seen["system"]
        # 原 SYSTEM_PROMPT 仍在(追加而非替换)
        assert "soc-content-drafter" in seen["system"]

    def test_tg1_no_voice_keeps_pure_system(self):
        seen = {}

        def llm(system, user):
            seen["system"] = system
            return FAKE_REPLY

        generate_variants("源", ["x"], llm_call=llm)
        assert "品牌 Voice" not in seen["system"]

    def test_tg2_router_passes_provider_and_voice(self, client, monkeypatch):
        seen = {}

        def fake_text_call(system, user, provider="", auth_token=""):
            seen["provider"] = provider
            seen["voice"] = "品牌 Voice" in system
            return FAKE_REPLY

        monkeypatch.setattr(service_module, "default_text_call", fake_text_call)
        r = client.post("/api/social/generate", json={
            "source_text": "源", "platforms": ["xiaohongshu"],
            "provider": "我的服务商", "brand_voice": "语气示例",
        })
        assert r.status_code == 200
        assert seen["provider"] == "我的服务商"
        assert seen["voice"] is True
