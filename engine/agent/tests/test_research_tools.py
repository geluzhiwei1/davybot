# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Gelu research 工具组 —— 测试即规格（设计：gelu-research-flow §4.2）。

M1 注册一致性：RESEARCH_TOOLS == TOOL_GROUPS["research"] == tool_catalog；唯一命名；schema 合法
M2 编队就位（mode-工具解耦后）：准入白名单已退役，编队 SSOT 在 market resources
M3 research_journal_rubric：{journal_profile} 注入块渲染（weight/threshold/origin）
M4 research_review_submit：outputs→gate→complete 顺序回流 + FAST FAIL（400 停止）+ 空载荷拒绝
M5 research_review_run_create：run_id 全量返回 + rubric 快照维度清单
M6 research_journal_suggest：heuristic-v1 推荐渲染（score/journal_id 全量/理由/结构化要求）+ 空结果
M7 research_submission_check：建行→自检调用顺序 + 逐项结论渲染 + FAST FAIL + 参数校验
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dawei.tools.custom_tools import research_tools as rt


@pytest.fixture
def patch_call(monkeypatch):
    """让 _call_research 返回固定 payload（不发出网络请求）。"""

    def _install(payload_by_path: dict, default=None):
        async def fake(method: str, path: str, **kwargs):
            for prefix, payload in payload_by_path.items():
                if path.startswith(prefix):
                    return payload
            return default if default is not None else {}

        monkeypatch.setattr(rt, "_call_research", fake)

    return _install


@pytest.mark.unit
class TestM1Registration:
    def test_tools_group_catalog_consistent(self):
        from dawei.tools.tool_catalog import _CATALOG
        from dawei.tools.tool_manager import TOOL_GROUPS

        names = {t().name for t in rt.RESEARCH_TOOLS}
        assert len(names) == len(rt.RESEARCH_TOOLS), "工具名必须唯一"
        assert all(n.startswith("research_") for n in names)
        group = set(TOOL_GROUPS["research"]["custom_tools"])
        assert group == names, "TOOL_GROUPS['research'] 与 RESEARCH_TOOLS 不一致"
        catalog = {c.name for c in _CATALOG if c.group == "research"}
        assert catalog == names, "tool_catalog research 条目与实现不一致"

    def test_schemas_valid(self):
        for t in rt.RESEARCH_TOOLS:
            inst = t()
            assert len(inst.description) > 20, f"{inst.name} 描述过短"
            if inst.args_schema is not None:
                props = inst.args_schema.model_json_schema().get("properties")
                assert props is not None, inst.name


@pytest.mark.unit
class TestM3Rubric:
    def test_journal_profile_block(self, patch_call):
        patch_call(
            {
                "/api/v1/journals/j1/rubric": {
                    "journal_id": "j1",
                    "dimensions": [
                        {"dimension_key": "novelty", "display_name": "新颖性", "weight": 2.0, "threshold": 9.0, "origin": "override"},
                        {"dimension_key": "clarity", "display_name": "表达清晰度", "weight": 1.0, "threshold": 7.5, "origin": "default"},
                    ],
                }
            }
        )
        out = rt.ResearchJournalRubricTool()._run(journal_id="j1")
        assert out.startswith("{journal_profile}")
        assert "journal_id: j1" in out
        assert "weight=2.00，threshold=9.00 [刊物覆盖]" in out
        assert "weight=1.00，threshold=7.50 [全局默认]" in out
        assert "勿自行加权" in out  # 评审纪律


@pytest.mark.unit
class TestM4ReviewSubmit:
    def test_outputs_gate_complete_sequence(self, monkeypatch):
        calls: list[str] = []

        async def fake(method: str, path: str, **kwargs):
            calls.append(path)
            jd = kwargs.get("json_data") or {}
            if path.endswith("/reviewer-outputs"):
                return {"reviewer_key": jd.get("reviewer_key"), "overall_score": jd.get("overall_score"), "verdict": jd.get("verdict")}
            if path.endswith("/gate"):
                return {"gate_key": jd.get("gate_key"), "threshold": jd.get("threshold")}
            return {"status": "done"}

        monkeypatch.setattr(rt, "_call_research", fake)
        out = rt.ResearchReviewSubmitTool()._run(
            run_id="r1",
            outputs=[
                {
                    "reviewer_key": "methodologist",
                    "overall_score": 7.5,
                    "verdict": "minor_revision",
                    "dimension_scores": [{"dimension_key": "novelty", "score": 8}],
                }
            ],
            gate={"gate_key": "G1", "threshold": 7.5, "result": {"weighted": 7.6}},
            complete={"status": "done", "summary": {"recommendation": "minor_revision"}},
        )
        assert calls == [
            "/api/v1/internal/review-runs/r1/reviewer-outputs",
            "/api/v1/internal/review-runs/r1/gate",
            "/api/v1/internal/review-runs/r1/complete",
        ]
        assert "✅ overall 7.5 / minor_revision（小修）" in out
        assert "gate G1：✅ 已建门（threshold 7.5，待人审 decide）" in out
        assert "complete：✅ run → done" in out

    def test_fast_fail_on_unknown_dimension(self, monkeypatch):
        async def fake(method: str, path: str, **kwargs):
            return {"_error": "HTTP 400", "detail": "dimension impact_factor_hack not in rubric snapshot"}

        monkeypatch.setattr(rt, "_call_research", fake)
        out = rt.ResearchReviewSubmitTool()._run(
            run_id="r1",
            outputs=[{"reviewer_key": "methodologist"}, {"reviewer_key": "statistician"}],
        )
        assert "❌" in out
        assert "已停止" in out

    def test_requires_at_least_one_payload(self, monkeypatch):
        called: list[int] = []
        monkeypatch.setattr(rt, "_call_research", lambda *_a, **_k: called.append(1))
        out = rt.ResearchReviewSubmitTool()._run(run_id="r1")
        assert out.startswith("Error:")
        assert not called  # 未发任何请求


@pytest.mark.unit
class TestM5RunCreate:
    def test_run_id_full_and_snapshot_dims(self, patch_call):
        patch_call(
            {
                "/api/v1/review-runs": {
                    "id": "run-uuid-full-1234567890",
                    "status": "dispatched",
                    "mode": "peer_review",
                    "reviewer_keys": ["methodologist", "domain_expert", "statistician"],
                    "rubric_snapshot_json": [{"dimension_key": "novelty"}, {"dimension_key": "clarity"}],
                }
            }
        )
        out = rt.ResearchReviewRunCreateTool()._run(journal_id="j1", paper_id="p1", mode="peer_review")
        assert "run-uuid-full-1234567890" in out  # 完整 id 不截断（下游回流需要）
        assert "rubric 快照（2 维）：novelty, clarity" in out
        assert "dimension_scores 只能使用" in out


@pytest.mark.unit
class TestM6JournalSuggest:
    def test_render_score_reasons_requirements(self, patch_call):
        patch_call(
            {
                "/api/v1/journals/suggest": {
                    "method": "heuristic-v1",
                    "items": [
                        {
                            "score": 2.1,
                            "reasons": ["学科精确匹配（computer science）", "最新指标 IF 12.8（JCR 2024）"],
                            "journal": {"id": "j-uuid-full-0987654321", "name": "Nature Medicine"},
                            "requirements": [
                                {
                                    "article_type": "original",
                                    "word_limit": 5000,
                                    "abstract_limit": 300,
                                    "figure_limit": 6,
                                    "reference_style": "GB/T 7714",
                                    "verified_at": "2025-01-01T00:00:00",
                                }
                            ],
                        },
                        {
                            "score": 1.2,
                            "reasons": ["关键词命中：clinical trial"],
                            "journal": {"id": "j2", "name": "JAMA"},
                            "requirements": [],
                        },
                    ],
                }
            }
        )
        out = rt.ResearchJournalSuggestTool()._run(abstract="AI clinical trial", keywords=["clinical trial"])
        assert "## 选刊推荐（heuristic-v1，2 本，得分降序）" in out
        assert "1. **Nature Medicine** — score 2.1（journal_id：j-uuid-full-0987654321）" in out  # id 全量
        assert "- 学科精确匹配（computer science）" in out
        assert "- 最新指标 IF 12.8（JCR 2024）" in out  # 指标理由必须带来源与年份
        assert "- 要求（original，已核证）：词数 ≤5000；摘要 ≤300；图 ≤6；引文 GB/T 7714" in out
        assert "JAMA" in out  # 无 requirements 的候选不臆造要求行
        assert "草稿" not in out

    def test_empty_items_explicit(self, patch_call):
        patch_call({"/api/v1/journals/suggest": {"method": "heuristic-v1", "items": []}})
        out = rt.ResearchJournalSuggestTool()._run(abstract="冷门主题")
        assert "无匹配刊物" in out
        assert "可先在 /research/journals 导入" in out

    def test_error_propagates(self, monkeypatch):
        async def fake(method: str, path: str, **kwargs):
            return {"error": "UNAVAILABLE", "detail": "connection refused"}

        monkeypatch.setattr(rt, "_call_research", fake)
        out = rt.ResearchJournalSuggestTool()._run(abstract="x")
        assert out.startswith("Error: UNAVAILABLE")


@pytest.mark.unit
class TestM7SubmissionCheck:
    def _capture_fake(self, monkeypatch, create_result: dict, check_result: dict):
        calls: list[tuple[str, str, dict]] = []

        async def fake(method: str, path: str, *, json_data: dict = None, **_k):
            calls.append((method, path, json_data or {}))
            if path == "/api/v1/submissions":
                return create_result
            return check_result

        monkeypatch.setattr(rt, "_call_research", fake)
        return calls

    def test_create_then_check_order_and_render(self, monkeypatch):
        calls = self._capture_fake(
            monkeypatch,
            create_result={"id": "sub-uuid-full-1234", "status": "preparing"},
            check_result={
                "format_check_json": {
                    "passed": False,
                    "passed_count": 1,
                    "checked_count": 2,
                    "source": "payload",
                    "items": [
                        {"item": "词数", "limit": 5000, "actual": 4200, "passed": True, "note": "4200/5000 词"},
                        {"item": "摘要", "limit": 300, "actual": 450, "passed": False, "note": "450 > 300 词"},
                    ],
                    "requirement": {"article_type": "original", "word_limit": 5000, "abstract_limit": 300},
                }
            },
        )
        out = rt.ResearchSubmissionCheckTool()._run(journal_id="j1", paper_id="p1", text="word " * 4200, article_type="original")
        # 建行 → 自检 顺序；text 随自检请求上送
        assert calls == [
            ("POST", "/api/v1/submissions", {"journal_id": "j1", "paper_id": "p1"}),
            ("POST", "/api/v1/submissions/sub-uuid-full-1234/format-check", {"article_type": "original", "text": "word " * 4200}),
        ]
        assert "## 格式自检（submission：sub-uuid-full-1234）" in out
        assert "- 结论：❌ 存在未达标项（1/2 项通过；正文来源：payload）" in out
        assert "- ✅ 词数：4200/5000 词" in out
        assert "- ❌ 摘要：450 > 300 词" in out
        assert "依据：刊物 original 要求 — 词数 5000 / 摘要 300 / 图 未配置 / 引文风格 未配置" in out

    def test_existing_submission_single_call(self, monkeypatch):
        calls = self._capture_fake(
            monkeypatch,
            create_result={},
            check_result={"format_check_json": {"passed": None, "passed_count": 0, "checked_count": 0, "source": "paper_abstract", "items": []}},
        )
        out = rt.ResearchSubmissionCheckTool()._run(submission_id="sub-9")
        assert calls == [("POST", "/api/v1/submissions/sub-9/format-check", {"article_type": "original"})]
        assert "⚠️ 无可检项" in out  # 无要求时如实说明
        assert "不臆造结论" in out

    def test_fast_fail_on_create_error(self, monkeypatch):
        calls = self._capture_fake(
            monkeypatch,
            create_result={"_error": "HTTP 409", "detail": "duplicate submission for journal+paper"},
            check_result={},
        )
        out = rt.ResearchSubmissionCheckTool()._run(journal_id="j1", paper_id="p1")
        assert out.startswith("Error: HTTP 409")
        assert len(calls) == 1  # 建行失败即停，不再发 format-check

    def test_validation_no_calls(self, monkeypatch):
        called: list[int] = []
        monkeypatch.setattr(rt, "_call_research", lambda *_a, **_k: called.append(1))
        assert rt.ResearchSubmissionCheckTool()._run().startswith("Error:")  # 缺 id/journal/稿件
        assert rt.ResearchSubmissionCheckTool()._run(journal_id="j1").startswith("Error:")  # 缺稿件指向
        out = rt.ResearchSubmissionCheckTool()._run(journal_id="j1", manuscript_kb_doc_id="kb-1")  # manuscript 路径缺 title
        assert out == "Error: manuscript 路径建台账行需要 title"
        assert not called
