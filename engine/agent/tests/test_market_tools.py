"""市场营销 Agent 工具组 —— 测试即规格(设计:project/MarkkeAgent-prd.md §5)。

M1 注册一致性:MARKET_TOOLS == TOOL_GROUPS["market"] == tool_catalog;唯一命名;schema 合法
M2 编队就位（mode-工具解耦后）:builtin 无业务模式，编队 SSOT 在 market resources
M3 market_dashboard:KPI/漏斗/数据源健康渲染 + 空数据诚实态
M4 market_list_events:who/what/置信度渲染 + 早鸟标注 + AUTH 错误人话化
M5 market_geo_checks:✅/❌ 引用态 + pos/未进引用 + 答案摘录截断
M6 market_get_signal:raw.title 优先、body 截断回退、正文 1200 上限
M7 market_competitor_profile:画像渲染 + 404(未生成)如实透传
"""

from __future__ import annotations

import pytest

from dawei.tools.custom_tools import market_tools as mt


@pytest.fixture
def patch_call(monkeypatch):
    """让 _call_market 返回固定 payload(不发出网络请求)。"""

    def _install(payload_by_path: dict, default=None):
        async def fake(method: str, path: str, **kwargs):
            for prefix, payload in payload_by_path.items():
                if path.startswith(prefix):
                    return payload
            return default if default is not None else {}

        monkeypatch.setattr(mt, "_call_market", fake)

    return _install


@pytest.mark.unit
class TestM1Registration:
    def test_tools_group_catalog_consistent(self):
        from dawei.tools.tool_catalog import _CATALOG
        from dawei.tools.tool_manager import TOOL_GROUPS

        names = {t().name for t in mt.MARKET_TOOLS}
        assert len(names) == len(mt.MARKET_TOOLS), "工具名必须唯一"
        group = set(TOOL_GROUPS["market"]["custom_tools"])
        assert group == names, "TOOL_GROUPS['market'] 与 MARKET_TOOLS 不一致"
        catalog = {c.name for c in _CATALOG if c.group == "market"}
        assert catalog == names, "tool_catalog market 条目与实现不一致"

    def test_schemas_valid(self):
        for t in mt.MARKET_TOOLS:
            inst = t()
            assert inst.name.startswith("market_"), inst.name
            assert len(inst.description) > 20, f"{inst.name} 描述过短"
            if inst.args_schema is not None:
                props = inst.args_schema.model_json_schema().get("properties")
                assert props is not None, inst.name


@pytest.mark.unit
class TestM2TeamModes:
    def test_registry_builtin_has_no_business_modes(self):
        """§8 兜底移除：builtin 仅剩 framework×2，mkt 编队不再随引擎内置
        （SSOT = normos-market-resources，经 market 安装进入 workspace）。"""
        from dawei.entity.mode import KIND_BUSINESS
        from dawei.mode.registry import get_registry

        assert get_registry(None).all(kind=KIND_BUSINESS) == []


@pytest.mark.unit
class TestM3Dashboard:
    def test_renders_kpi_funnel_health(self, patch_call):
        # actions 用生产真实形状:{counts, recent_live}(E2E 实证 2026-08-31)
        patch_call(
            {
                "/api/v1/dashboard": {
                    "kpi": {"pending": 3, "new_events": 4},
                    "actions": {"counts": {"live": 3, "idea": 2}, "recent_live": [{"title": "两站 robots.txt+llms.txt 上线", "action_type": "metadata", "status": "live"}]},
                    "sources_health": {"total": 4, "enabled": 4, "errored": 1, "last_run_at": "2026-08-31T01:00:00"},
                    "competitor_matrix": [{"competitor": "CVAT", "github": 2}],
                    "social_push_enabled": True,
                }
            }
        )
        out = mt.MarketDashboardTool()._run(days=7, brand_id="")
        assert "市场看板" in out
        assert "pending:3" in out
        assert "live:3" in out
        assert "🔗 live：两站 robots.txt+llms.txt 上线" in out  # recent_live 摘要
        assert "总数 4" in out
        assert "异常 1" in out
        assert "已启用" in out  # 社媒推送通道

    def test_competitor_monitoring_matrix_dict_shape(self, patch_call):
        # monitoring_config.platforms 生产形状是 dict(平台→内容类型矩阵,E2E 抓到 KeyError)
        patch_call({"/api/v1/competitors": [{"id": "c-12345678", "name": "Label Studio", "category": "标注", "monitoring_config": {"platforms": {"github": ["release"], "hn": ["story"]}}}]})
        out = mt.MarketListCompetitorsTool()._run()
        assert "Label Studio" in out
        assert "监控:github,hn" in out

    def test_empty_dashboard_honest(self, patch_call):
        patch_call({"/api/v1/dashboard": {}})
        out = mt.MarketDashboardTool()._run(days=7, brand_id="")
        assert "暂无数据" in out


@pytest.mark.unit
class TestM4Events:
    def test_renders_who_what_confidence_emerging(self, patch_call):
        patch_call(
            {
                "/api/v1/events": [
                    {"id": "ev-12345678", "who": "Label Studio", "what": "发布 1.50 版本", "occurred_at": "2026-08-30T10:00:00", "confidence_score": 0.9, "status": "event", "is_emerging": False},
                    {"id": "ev-87654321", "who": "趋势早鸟:开源标注", "what": "提及量上升", "occurred_at": None, "confidence_score": 0.5, "status": "event", "is_emerging": True},
                ]
            }
        )
        out = mt.MarketListEventsTool()._run(limit=20)
        assert "Label Studio" in out
        assert "0.90" in out
        assert "早鸟待确认" in out  # is_emerging 标注

    def test_auth_error_human_friendly(self, patch_call):
        patch_call({"/api/v1/events": {"error": "AUTH", "detail": "market-flow 认证失败（token 缺失/过期或无权限）"}})
        out = mt.MarketListEventsTool()._run(limit=20)
        assert out.startswith("Error: AUTH")
        assert "认证失败" in out


@pytest.mark.unit
class TestM5GeoChecks:
    def test_cited_uncited_render(self, patch_call):
        patch_call(
            {
                "/api/v1/visibility/geo": [
                    {"id": "g1", "engine": "glm", "keyword": "开源标注工具", "cited": False, "position": None, "answer_excerpt": "Label Studio、CVAT 是常用的开源标注工具…"},
                    {"id": "g2", "engine": "deepseek", "keyword": "Yinghuo-OpenLabel", "cited": True, "position": 1, "answer_excerpt": "Yinghuo-OpenLabel 是…"},
                ]
            }
        )
        out = mt.MarketGeoChecksTool()._run(limit=30)
        assert "被引 1" in out
        assert "✅" in out
        assert "pos 1" in out
        assert "❌" in out
        assert "未进引用" in out
        assert "Label Studio、CVAT" in out  # 答案摘录(竞品占据证据)


@pytest.mark.unit
class TestM6SignalDetail:
    def test_title_first_body_fallback_truncated(self, patch_call):
        long_body = "字" * 300
        patch_call({"/api/v1/signals": [{"id": "s1", "source_type": "rss", "platform": "sspai", "raw": {"body": long_body}}, {"id": "s2", "source_type": "rss", "raw": {"title": "有标题信号", "body": "正文"}}]})
        out = mt.MarketListSignalsTool()._run(limit=2)
        assert "有标题信号" in out  # title 优先
        assert "字字字" in out  # body 截断回退
        assert "…" in out  # 省略号
        # 详情:正文 1200 上限
        patch_call({"/api/v1/signals/s1": {"id": "s1", "source_type": "rss", "raw": {"title": "t", "body": "x" * 1500}, "url": "https://example.com/a"}})
        detail = mt.MarketGetSignalTool()._run(signal_id="s1")
        assert "https://example.com/a" in detail
        assert len(detail) < 1500  # 截断生效


@pytest.mark.unit
class TestM7Profile:
    def test_profile_renders_with_model_version(self, patch_call):
        patch_call({"/api/v1/competitors/c1/profile": {"positioning": "专业级标注平台", "main_platforms": ["github"], "price_band": None, "content_strategy": "开发者内容为主", "generated_at": "2026-08-28T12:00:00", "model_version": "deepseek-v4-flash"}})
        out = mt.MarketCompetitorProfileTool()._run(competitor_id="c1")
        assert "专业级标注平台" in out
        assert "deepseek-v4-flash" in out
        assert "未识别" in out  # price_band None → 诚实标注

    def test_profile_404_passthrough(self, patch_call):
        patch_call({"/api/v1/competitors/c1/profile": {"_error": "HTTP 404", "detail": "Not Found"}})
        out = mt.MarketCompetitorProfileTool()._run(competitor_id="c1")
        assert out.startswith("Error: HTTP 404")


@pytest.mark.unit
class TestM8WriteTools:
    """L3 白名单写工具(PRD §8.2):幂等/草稿/配额内,渲染结果含人工边界提示。"""

    def test_run_pipeline_renders_summary(self, patch_call):
        patch_call({"/api/v1/pipeline/process": {"processed": 10, "events_created": 1, "events_merged": 2, "filtered": 6, "failed": 1, "llm_error": None}})
        out = mt.MarketRunPipelineTool()._run(limit=10)
        assert "处理 10 条信号" in out
        assert "新事件 1" in out

    def test_run_source_renders_and_error_honest(self, patch_call):
        patch_call({"/api/v1/sources/src1/run": {"source_id": "src1", "fetched": 7, "new_signals": 6, "duplicates": 1, "error": None}})
        out = mt.MarketRunSourceTool()._run(source_id="src1")
        assert "拉取 7 条" in out
        assert "新增 6" in out

    def test_run_geo_quota_and_errors_visible(self, patch_call):
        patch_call({"/api/v1/visibility/geo/run": {"checks": 15, "cited": 0, "quota_skipped": 3, "errors": ["engine glm timeout"], "usage_tokens": 1234}})
        out = mt.MarketRunGeoTool()._run(keyword_set_id="")
        assert "检查 15 项" in out
        assert "配额跳过 3" in out  # 配额治理可见
        assert "glm timeout" in out  # 错误不吞

    def test_generate_report_created_and_skipped(self, patch_call):
        patch_call({"/api/v1/reports/generate": {"created": 1, "skipped_reason": None, "llm_error": None}})
        out = mt.MarketGenerateReportTool()._run(kind="weekly")
        assert "draft 草稿" in out
        assert "/market/reports" in out  # 终态操作指回页面(HITL)
        patch_call({"/api/v1/reports/generate": {"created": 0, "skipped_reason": "already exists", "llm_error": None}})
        out = mt.MarketGenerateReportTool()._run(kind="weekly")
        assert "未生成" in out
        assert "already exists" in out

    def test_draft_action_includes_payload_and_hitl_hint(self, patch_call):
        patch_call({"/api/v1/actions/from-insight/ins1": {"id": "a12345678", "action_type": "backlink", "title": "awesome-lists 收录提交", "target": "github.com/awesome-data-labeling", "payload": "提交文案:Yinghuo-OpenLabel 是一款开源标注工具", "status": "idea"}})
        out = mt.MarketDraftActionTool()._run(insight_id="ins1", action_type="backlink")
        assert "idea 状态" in out
        assert "提交文案" in out  # 可粘贴文案
        assert "/market/actions" in out  # 推进须人工

    def test_evaluate_demand_worth_and_skip(self, patch_call):
        patch_call({"/api/v1/opportunities/demand-signals": {"signal_id": "s1", "lead_id": "l1", "opportunity_id": "o1", "worth_pursuing": True}})
        out = mt.MarketEvaluateDemandTool()._run(source_type="rfq", title="美国玩具买家询价")
        assert "值得跟进" in out
        assert "stage=lead" in out
        patch_call({"/api/v1/opportunities/demand-signals": {"signal_id": "s2", "worth_pursuing": False, "skipped_reason": "intent too low"}})
        out = mt.MarketEvaluateDemandTool()._run(source_type="rfq", title="泛询价")
        assert "不值得追" in out
        assert "intent too low" in out

    def test_insight_feedback_adopt_push_states(self, patch_call):
        patch_call({"/api/v1/insights/i1/adopt": {"status": "adopted", "pushed": True, "push_error": None}})
        out = mt.MarketInsightFeedbackTool()._run(insight_id="i1", action="adopt")
        assert "已采纳" in out
        assert "社媒选题推送" in out
        patch_call({"/api/v1/insights/i1/discard": {}})
        out = mt.MarketInsightFeedbackTool()._run(insight_id="i1", action="discard")
        assert "已驳回" in out

    def test_insight_feedback_rejects_bad_action(self, patch_call):
        out = mt.MarketInsightFeedbackTool()._run(insight_id="i1", action="delete")
        assert out.startswith("Error:")

    def test_post_params_passthrough(self, patch_call):
        """POST 的 query 参数(evaluate/limit/kind)必须透传(本轮修的 client 缺口)。"""
        seen = {}

        async def fake(method, path, *, json_data=None, params=None, timeout=None):
            seen["params"] = params
            return {"processed": 0, "events_created": 0, "events_merged": 0, "filtered": 0, "failed": 0, "llm_error": None}

        mp = pytest.MonkeyPatch()
        mp.setattr(mt, "_call_market", fake)
        try:
            mt.MarketRunPipelineTool()._run(limit=33)
        finally:
            mp.undo()
        assert seen["params"] == {"limit": 33}


@pytest.mark.unit
class TestM9AttributionRendering:
    """P3:market_list_actions 回显归因证据摘要(Agent 引证据答的原料)。"""

    def test_attribution_summary_rendered(self, patch_call):
        patch_call(
            {
                "/api/v1/actions": [
                    {
                        "id": "a-12345678",
                        "status": "live",
                        "action_type": "launch",
                        "title": "Show HN 发布",
                        "target": "news.ycombinator.com",
                        "social_content_ids": [
                            {"content_id": "c1", "platform": "hn", "matched_by": "explicit"},
                            {"content_id": "c2", "platform": "xhs", "matched_by": "inferred"},
                        ],
                        "attribution": {
                            "verdict": "suggest_verify",
                            "confidence": 0.65,
                            "observations": [
                                {"kind": "geo", "engine": "glm", "keyword": "开源标注工具",
                                 "change": "cited", "position": 2, "baseline_checks": 4}
                            ],
                            "concurrent": [{"id": "x", "title": "并发外链", "action_type": "backlink"}],
                            "notes": "发布后窗口内出现 1 项方向性变化",
                        },
                    }
                ]
            }
        )
        out = mt.MarketListActionsTool()._run()
        assert "关联内容 2(确认 1)" in out  # inferred 与确认区分
        assert "归因:suggest_verify/0.65" in out  # verdict+置信
        assert "观察 1,并发 1" in out
        assert "开源标注工具@glm:发布后被引用 pos 2" in out  # 观察明细可引
        assert "基线 4 次" in out
        assert "方向性变化" in out  # notes 摘要

    def test_no_attribution_no_noise(self, patch_call):
        patch_call({"/api/v1/actions": [{"id": "a2", "status": "idea", "action_type": "backlink", "title": "t"}]})
        out = mt.MarketListActionsTool()._run()
        assert "归因:" not in out and "关联内容" not in out  # 无数据不加噪音
