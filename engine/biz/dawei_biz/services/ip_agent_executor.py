# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""
IP Agent Executor — REST-friendly Agent execution inside IP workspace context.

Runs the full Agent engine (PDCA + TaskGraph) inside an IP temp workspace,
captures conversation results, and persists them as structured JSON to
`.dawei/results.json`.

Architecture:
  - load workspace → init workspace → create Agent → init Agent →
  - build prompt → process_message() → wait for completion →
  - extract conversation results → save to workspace file

This is a simplified version of ChatHandler._execute_agent_task() adapted
for REST context (no WebSocket event forwarding).
"""

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dawei.core.datetime_compat import UTC
from dawei.entity.user_input_message import UserInputText
from dawei.workspace.user_workspace import UserWorkspace
from dawei.workspace.workspace_manager import workspace_manager

logger = logging.getLogger(__name__)

# ============================================================================
# Module → patent team prompt builders
# ============================================================================

# Map team_slug to a prompt-building function that takes a params dict
# and returns the initial user prompt the Agent should execute.
_MODULE_PROMPT_BUILDERS: dict[str, Callable[[dict[str, Any]], str]] = {}


def _register(slug: str):
    """Decorator to register a prompt builder for an IP module."""
    def decorator(fn: Callable[[dict[str, Any]], str]):
        _MODULE_PROMPT_BUILDERS[slug] = fn
        return fn
    return decorator


@_register("ip-idea-vault")
def _prompt_idea_vault(params: dict[str, Any]) -> str:
    desc = params.get("description", "")
    return (
        "请对以下技术创意进行专利可专利性和商业价值评估。\n\n"
        "## 评估维度\n"
        "1. 新颖性分析\n"
        "2. 创造性分析\n"
        "3. 产业应用性评估\n"
        "4. 保护策略建议（发明/实用新型/PCT等）\n"
        "5. 总体推荐策略\n\n"
        f"技术描述：{desc}\n\n"
        "## 输出格式（严格按此 JSON 结构）\n"
        "```json\n"
        "{\n"
        '  "patentabilityScore": 75,\n'
        '  "recommendedStrategy": "建议申请发明专利...",\n'
        '  "protectionSuggestions": ["发明保护", "PCT国际申请"],\n'
        '  "points": [\n'
        '    {"id": "novelty", "title": "新颖性", "score": 80, "recommendation": "该技术方案在检索范围内未发现..."},\n'
        '    {"id": "inventiveness", "title": "创造性", "score": 70, "recommendation": "与现有技术相比具有..."},\n'
        '    {"id": "industrial", "title": "产业应用性", "score": 85, "recommendation": "可直接应用于..."}\n'
        "  ],\n"
        '  "prior_arts": [\n'
        '    {"ref": "CN123456A", "relevance": "medium", "abstract": "涉及类似技术..."}\n'
        "  ]\n"
        "}\n"
        "```\n"
        "points 数组中每个元素必须包含 id, title, score(0-100整数), recommendation。\n"
        "prior_arts 数组中每个元素必须包含 ref(专利号), relevance(high/medium/low), abstract。\n"
    )


@_register("ip-disclosure")
def _prompt_disclosure(params: dict[str, Any]) -> str:
    desc = params.get("description", "")
    return (
        "请根据以下技术创意撰写一份完整的专利技术交底书，按以下结构组织：\n"
        "1. 技术领域\n"
        "2. 背景技术（分析现有技术存在的问题）\n"
        "3. 要解决的技术问题\n"
        "4. 技术方案（详细描述实现方式）\n"
        "5. 有益效果\n"
        "6. 具体实施方式\n"
        "7. 附图说明\n"
        "8. 权利要求概要\n\n"
        f"技术创意描述：{desc}\n\n"
        "请以结构化JSON格式输出，sections 对象包含各章节 content 字段。"
    )


@_register("ip-draft")
def _prompt_draft(params: dict[str, Any]) -> str:
    desc = params.get("description", "")
    country = params.get("targetCountry", "CN")
    strategy = params.get("strategy", "balanced")
    country_map = {"CN": "中国", "US": "美国", "EP": "欧洲", "JP": "日本", "KR": "韩国"}
    country_name = country_map.get(country, country)
    return (
        f"请根据以下技术交底书内容撰写面向{country_name}的专利申请文件。策略：{strategy}。\n"
        "输出应包含：\n"
        "1. 权利要求（至少1项独立权利要求+5项从属权利要求，标注类型和编号）\n"
        "2. 说明书（技术领域、背景技术、发明内容、具体实施方式、实施例）\n"
        "3. 合规性检查结果\n\n"
        f"技术交底书内容：{desc}\n\n"
        "请以结构化JSON格式输出，包含 claims 数组、specification 对象、complianceCheck 对象。"
    )


@_register("ip-filing")
def _prompt_filing(params: dict[str, Any]) -> str:
    desc = params.get("description", "")
    markets = params.get("targetMarkets", ["US", "EP"])
    markets_str = "、".join(markets)
    return (
        f"请为目标市场 {markets_str} 制定专利申请路径策略。"
        "分析巴黎公约路径和PCT路径的优劣，输出：\n"
        "1. 推荐路径（paris/pct）\n"
        "2. 路径对比（截止期限、费用估计、优缺点）\n"
        "3. 优先级主张信息\n"
        "4. 各国费用明细\n"
        "5. PCT时间线（如果推荐PCT路径）\n"
        "6. 翻译状态\n\n"
        f"技术描述（可选）：{desc}\n\n"
        "请以结构化JSON格式输出。"
    )


@_register("ip-oa-reply")
def _prompt_oa_reply(params: dict[str, Any]) -> str:
    desc = params.get("description", "")
    country = params.get("country", "CN")
    return (
        f"请针对{country}专利局下发的审查意见通知书，分析驳回理由并制定答复策略。\n"
        "输出应包含：\n"
        "1. 驳回理由分析（新颖性/创造性等）\n"
        "2. 对比文件分析\n"
        "3. 推荐答复策略（直接争辩/修改权利要求/两者结合）\n"
        "4. 具体答复意见（争辩意见+建议的修改）\n"
        "5. 修改后的权利要求\n\n"
        f"审查意见内容：{desc}\n\n"
        "请以结构化JSON格式输出，包含 rejections, comparedDocuments, recommendedStrategy, "
        "strategyAnalysis, replies, amendedClaims 等字段。"
    )


@_register("ip-reverse-detection")
def _prompt_reverse_detection(params: dict[str, Any]) -> str:
    """反向侵权探测 prompt — 检测他人侵犯我方专利"""
    desc = params.get("myTechDescription", params.get("description", ""))
    patents = params.get("myPatentNumbers") or params.get("patentNumbers") or []
    patents_str = "、".join(patents) if patents else "（请根据技术描述自行检索相关专利）"
    markets = params.get("targetMarkets", ["CN"])
    return (
        "请对市场上的产品或技术进行反向侵权检测，识别是否有人侵犯我方的专利权。\n"
        "输出应包含（results 数组）：\n"
        "1. 疑似侵权方名称和产品名称（infringerName, infringerProduct）\n"
        "2. 被侵权的我方专利号（matchedMyPatentNumber）\n"
        "3. 侵权概率评级（infringementProbability: high/medium/low）\n"
        "4. 特征匹配度百分比（featureMatchRate: 0-100）\n"
        "5. 权利要求逐项对比（claimMatches）：\n"
        "   - myClaimNumber: 我方权利要求编号\n"
        "   - myClaimText: 我方权利要求文本\n"
        "   - theirFeature: 对方产品/技术特征\n"
        "   - matchLevel: exact（完全匹配）/ equivalent（等同）/ partial（部分）/ none（不覆盖）\n"
        "   - analysis: 简要分析说明\n"
        "6. 预警信息（alert）：type, title, description, severity(high/medium/low)\n"
        f"我方专利号：{patents_str}\n"
        f"技术描述（可选）：{desc}\n"
        f"目标市场：{', '.join(markets)}\n\n"
        "请以结构化JSON格式输出，包含 type, myPatentNumbers, myTechDescription, targetMarkets, status, results 等字段。"
    )


@_register("ip-portfolio")
def _prompt_portfolio(params: dict[str, Any]) -> str:
    desc = params.get("description", "")
    return (
        "请对IP资产组合进行全面分析，输出：\n"
        "1. 专利列表（id, title, 状态, 价值评分, 产品关联度等）\n"
        "2. 商标列表\n"
        "3. KPI统计（总数、授权数、审查中、放弃、通过率等）\n"
        "4. 健康度评分及子评分（质量、覆盖度、生命周期、商业价值）\n"
        "5. 专利状态分布\n"
        "6. 竞争对手分析\n"
        "7. 续费提醒（未来12个月）\n\n"
        f"分析范围描述（可选）：{desc}\n\n"
        "请以结构化JSON格式输出，包含 patents 数组、trademarks 数组、kpis 对象、"
        "healthScore、competitors、renewals 等字段。"
    )


@_register("ip-application")
def _prompt_ip_application(params: dict[str, Any]) -> str:
    """Patent application prompt — converts jurisdiction-neutral draft to country-specific filing."""
    desc = params.get("description", "")
    country = params.get("targetCountry", "CN")
    country_map = {
        "CN": "中国 (CNIPA)",
        "US": "美国 (USPTO)",
        "EP": "欧洲 (EPO)",
        "JP": "日本 (JPO)",
        "KR": "韩国 (KIPO)",
        "PCT": "PCT 国际申请 (WIPO)",
    }
    country_name = country_map.get(country, country)
    applicant = params.get("applicant_name", "（待填）")
    inventor = params.get("inventor_names", "（待填）")

    # Country-specific format requirements
    format_notes = {
        "CN": (
            "中国发明专利五书格式：请求书、权利要求书、说明书、说明书摘要、说明书附图。\n"
            "权利要求书需符合法第26条第4款，说明书需符合细则第17条。"
        ),
        "US": (
            "USPTO Utility Patent Application: Specification + Claims + Abstract + Drawings。\n"
            "Claims 以 'What is claimed is:' 开头，独立权利要求含 preamble + transitional phrase + body。\n"
            "Abstract 不超过 150 词。需符合 35 U.S.C. § 112 要求。"
        ),
        "PCT": (
            "PCT International Application: PCT Request + Description + Claims + Abstract + Drawings。\n"
            "Description 按 PCT Rule 5 结构排列，Claims 按 PCT Rule 6 编号。\n"
            "Abstract 不超过 150 词，需标注指定国。"
        ),
    }.get(country, "请按照目标国家/地区的标准专利申请格式生成。")

    return (
        f"请根据以下专利草案内容，生成面向{country_name}的专利申请文件。\n\n"
        f"## 申请人信息\n"
        f"- 申请人：{applicant}\n"
        f"- 发明人：{inventor}\n\n"
        f"## 目标格式\n"
        f"{format_notes}\n\n"
        "## 输出要求\n"
        "1. 完整的申请文件（各分册独立输出）\n"
        "2. 格式合规性自检\n"
        "3. 如有格式问题，列出修改建议\n\n"
        f"专利草案内容：{desc}\n\n"
        "请以结构化JSON格式输出，包含 application_type, country, specification, claims, "
        "abstract, drawings_description, compliance_check 等字段。"
    )


@_register("ip-trademark")
def _prompt_trademark(params: dict[str, Any]) -> str:
    name = params.get("name", params.get("description", ""))
    scope = params.get("businessScope", "")
    return (
        f"请为商标'{name}'进行可注册性评估和类别推荐。\n"
        "输出应包含：\n"
        "1. 推荐注册类别（每类含classNumber, className, type(核心/关联/防御), 具体商品/服务项, 理由）\n"
        "2. 可注册性评估（显著性评分、绝对理由审查、相对理由审查、近似商标分析）\n"
        f"经营范围：{scope}\n\n"
        "请以结构化JSON格式输出，包含 recommendedClasses 数组、registrability 对象（含 overallScore, "
        "distinctiveness, absoluteGrounds, relativeGrounds, similarTrademarks, summary）。"
    )


def _build_prompt(slug: str, params: dict[str, Any]) -> str:
    """Build the initial user prompt for a given IP module."""
    builder = _MODULE_PROMPT_BUILDERS.get(slug)
    if builder:
        return builder(params)
    # Generic fallback
    desc = params.get("description", params.get("query", ""))
    return f"请处理以下IP任务:\n{desc}"


# ============================================================================
# Panel metadata extraction — bridges agent output → frontend IP special panel
# ============================================================================

# Fields each module's panel reads from workspace.metadata (see ip-special-panel.tsx)
_PANEL_FIELD_MAP: dict[str, list[str]] = {
    "ip-idea-vault": ["points", "prior_arts", "patentabilityScore", "recommendedStrategy"],
    "ip-disclosure": ["sections"],
    "ip-draft": ["claims", "compliance_issues"],
    "ip-oa-reply": ["strategies", "contrast_docs"],
    "ip-reverse-detection": ["alerts", "monitor_tasks"],
    "ip-trademark": ["recommendedClasses", "registrability"],
}


def _extract_panel_metadata(
    module_slug: str,
    result: dict[str, Any] | str | None,
) -> dict[str, Any]:
    """Extract fields that the frontend IP special panel needs from the agent result.

    Also tries common camelCase ↔ snake_case aliases so we don't miss data
    when the LLM uses a slightly different key name.
    """
    if not isinstance(result, dict):
        return {}

    wanted = _PANEL_FIELD_MAP.get(module_slug, [])
    if not wanted:
        return {}

    meta: dict[str, Any] = {}

    for field in wanted:
        # Direct match
        if field in result:
            meta[field] = result[field]
            continue
        # snake_case alias (e.g. prior_arts ↔ priorArts)
        snake = field.replace("_", "")
        for key in result:
            if key.replace("_", "").lower() == snake.lower():
                meta[field] = result[key]
                break

    # For ip-draft, also extract compliance issues from complianceCheck
    if module_slug == "ip-draft" and "compliance_issues" not in meta:
        cc = result.get("complianceCheck") or result.get("compliance_check")
        if isinstance(cc, dict):
            issues = cc.get("issues", [])
            if issues:
                meta["compliance_issues"] = issues

    # For ip-oa-reply, also try strategyAnalysis
    if module_slug == "ip-oa-reply" and "strategies" not in meta:
        sa = result.get("strategyAnalysis") or result.get("strategy_analysis")
        if isinstance(sa, list):
            meta["strategies"] = sa

    # Always include the overall score if present
    score = result.get("patentabilityScore") or result.get("patentability_score")
    if score is not None:
        meta["score"] = score

    return meta


def _write_panel_metadata(
    ws_path: Path,
    module_slug: str,
    result: dict[str, Any] | str | None,
) -> None:
    """Write extracted panel metadata into workspace.json → ip_metadata.metadata.

    Called after agent execution completes so the frontend IP special panel
    can render the structured results instead of showing the empty placeholder.
    """
    panel_meta = _extract_panel_metadata(module_slug, result)
    if not panel_meta:
        return

    workspace_json = ws_path / ".dawei" / "workspace.json"
    if not workspace_json.exists():
        return

    try:
        with workspace_json.open() as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    ip_meta = config.setdefault("ip_metadata", {})
    meta = ip_meta.setdefault("metadata", {})
    if not isinstance(meta, dict):
        meta = {}
    meta.update(panel_meta)
    ip_meta["metadata"] = meta

    try:
        with workspace_json.open("w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info(
            "[IP-EXEC] Panel metadata written for %s: %s",
            module_slug,
            list(panel_meta.keys()),
        )
    except OSError as e:
        logger.warning("[IP-EXEC] Failed to write panel metadata: %s", e)


# ============================================================================
# Agent execution
# ============================================================================


async def _emit_ip_trace_span(
    workspace_id: str,
    task_id: str,
    span_name: str,
    *,
    phase: str | None = None,
    status: str = "success",
    parent_span_id: str | None = None,
    trace_id: str | None = None,
    input_summary: str | None = None,
    output_summary: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Broadcast an AgentSpanMessage via WebSocket for IP workspace tasks.

    This bridges the gap between the detached IP executor (which has no
    WebSocket session) and the frontend trace UI. It uses broadcast() with
    workspace_id filtering, following the same pattern as task_graph.py.
    """
    import uuid as uuid_mod

    try:
        from dawei.websocket.ws_server import websocket_server
        from dawei.websocket.protocol import AgentSpanMessage

        if websocket_server is None or not websocket_server._is_initialized:
            return

        now_iso = datetime.now(UTC).isoformat()
        span_id = str(uuid_mod.uuid4())

        span_msg = AgentSpanMessage(
            session_id="",
            workspace_id=workspace_id,
            task_node_id=task_id,
            trace_id=trace_id or f"ip-{workspace_id[:8]}",
            span_id=span_id,
            parent_span_id=parent_span_id,
            span_name=span_name,
            phase=phase,
            start_time=now_iso,
            end_time=now_iso if status != "running" else None,
            duration_ms=duration_ms,
            status=status,
            input_summary=input_summary,
            output_summary=output_summary,
            metadata={"source": "ip_executor", "workspace_id": workspace_id},
        )
        await websocket_server.websocket_manager.broadcast(span_msg, workspace_id=workspace_id)
        logger.debug("[IP-EXEC] Emitted trace span: %s (%s) for ws=%s", span_name, status, workspace_id)
    except Exception as e:
        logger.debug("[IP-EXEC] Failed to emit trace span: %s", e)


async def execute_ip_task(
    workspace_id: str,
    module_slug: str,
    params: dict[str, Any],
    *,
    task_id: str | None = None,
    template_slug: str | None = None,
    on_status_update: Callable[[dict[str, Any]], Any] | None = None,
    timeout_seconds: int = 600,
) -> dict[str, Any]:
    """Execute an IP task inside its workspace using the full Agent engine.

    NOTE: compliance workspaces use a different auto-start model — the agent
    must stream its opening into the ChatView WebSocket session (a multi-turn
    dialogue), whereas this executor runs a detached agent and writes
    ``.dawei/results.json``. See ``compliance_agent_executor.py`` / the workspace
    optimization plan before reusing this pattern for compliance.

    This is the main entry point. It:
      1. Loads the workspace from the system index
      2. Initializes the UserWorkspace (LLM, tools, etc.)
      3. Creates and initializes the Agent
      4. Builds an appropriate prompt from the module slug and params
         (or uses template instructions if template_slug is provided)
      5. Runs the Agent (blocks until task graph completes)
      6. Extracts conversation messages as the result
      7. Checks deliverables if template_slug is provided
      8. Saves results to workspace .dawei/results.json
      9. Invokes on_status_update on state changes

    Args:
        workspace_id: UUID of the temp workspace created by IPWorkspaceService
        module_slug: e.g. "ip-draft", "ip-reverse-detection"
        params: Raw params from the API request body
        template_slug: Optional template slug for template-driven execution (Path B)
        on_status_update: Optional callback(state_dict) called with status updates
        timeout_seconds: Max execution time before cancellation

    Returns:
        Status dict: {status, result, error, conversation_id, messages_count, ...}
    """
    status: dict[str, Any] = {
        "workspace_id": workspace_id,
        "module": module_slug,
        "status": "running",
        "phase": None,
        "result": None,
        "error": None,
        "conversation_id": None,
        "messages_count": 0,
        "tool_calls_count": 0,
        "started_at": datetime.now(UTC).isoformat(),
    }

    def _notify(extra: dict[str, Any] | None = None) -> None:
        nonlocal status
        if extra:
            status.update(extra)
        if on_status_update:
            try:
                on_status_update(dict(status))
            except Exception:
                pass

    user_workspace: UserWorkspace | None = None
    agent = None

    try:
        # ── 1. Load workspace ──
        ws_info = workspace_manager.get_workspace_by_id(workspace_id)
        if not ws_info:
            raise FileNotFoundError(f"Workspace not found in index: {workspace_id}")
        ws_path_str = ws_info.get("path")
        if not ws_path_str:
            raise ValueError(f"Workspace {workspace_id} missing path field")

        ws_path = Path(ws_path_str).resolve()
        user_workspace = UserWorkspace(str(ws_path))
        logger.info(f"[IP-EXEC] Loaded workspace: {workspace_id} at {ws_path}")

        # ── 2. Initialize workspace ──
        if not user_workspace.is_initialized():
            await user_workspace.initialize()
            # Ensure workspace_manager is reloaded so the temp workspace is visible
            workspace_manager.reload()
            logger.info(f"[IP-EXEC] Workspace initialized: {workspace_id}")

        _notify({"status": "running", "phase": "plan"})
        tid = task_id or workspace_id
        await _emit_ip_trace_span(workspace_id, tid, "plan", phase="plan", status="running",
                                   input_summary=f"module={module_slug}")

        # ── 3. Create & initialize Agent ──
        from dawei.agentic.agent import Agent

        agent = await Agent.create_with_default_engine(user_workspace)
        logger.info(f"[IP-EXEC] Agent created for workspace: {workspace_id}")

        await agent.initialize()
        logger.info(f"[IP-EXEC] Agent initialized: {workspace_id}")

        _notify({"status": "running", "phase": "do"})
        await _emit_ip_trace_span(workspace_id, tid, "plan", phase="plan", status="success",
                                   output_summary="Agent initialized")
        await _emit_ip_trace_span(workspace_id, tid, "do", phase="do", status="running",
                                   input_summary="Agent process_message started")

        # ── 4. Build prompt ──
        if template_slug:
            # Path B: 模板驱动模式 — Agent 读取工作区中的指令文件
            prompt = (
                "请读取本工作区的 `input/AGENT_INSTRUCTIONS.md` 文件，"
                "按照其中的 PDCA 工作流执行分析。"
                "所有参数配置在 `input/task_params.json` 中。"
                "不要跳过分阶段执行，每一步都要向用户汇报进展。"
            )
        else:
            # Path A: 快速模式 — 直接注入 prompt
            prompt = _build_prompt(module_slug, params)
        logger.info(f"[IP-EXEC] Prompt built ({len(prompt)} chars): {prompt[:120]}...")

        # ── 5. Create UserInputMessage ──
        user_input = UserInputText(
            text=prompt,
            metadata={
                "workspaceId": workspace_id,
                "module": module_slug,
                **{k: v for k, v in params.items() if v is not None},
            },
        )

        # ── 6. Execute Agent (blocks until task graph completes) ──
        logger.info(f"[IP-EXEC] Starting agent execution for workspace: {workspace_id}")
        try:
            await asyncio.wait_for(
                agent.process_message(user_input),
                timeout=timeout_seconds,
            )
            logger.info(f"[IP-EXEC] Agent execution completed: {workspace_id}")
        except TimeoutError:
            logger.exception(f"[IP-EXEC] Agent execution timed out after {timeout_seconds}s: {workspace_id}")
            status["status"] = "timeout"
            status["error"] = f"Execution timed out after {timeout_seconds}s"
            await _emit_ip_trace_span(workspace_id, tid, "do", phase="do", status="error",
                                       output_summary=f"Timed out after {timeout_seconds}s")
            return dict(status)

        _notify({"status": "running", "phase": "check"})
        await _emit_ip_trace_span(workspace_id, tid, "do", phase="do", status="success",
                                   output_summary="Agent process_message completed")
        await _emit_ip_trace_span(workspace_id, tid, "check", phase="check", status="running")

        # ── 7. Deliverables check (Path B) ──
        deliverables_status: dict[str, Any] = {}
        if template_slug:
            try:
                from dawei_biz.services.ip_template import ip_template_manager

                template_data = ip_template_manager.load_template(template_slug)
                if template_data:
                    t = template_data.get("template", template_data)
                    deliverables = t.get("deliverables", [])
                    files_dir = ws_path
                    for d in deliverables:
                        expected_file = d.get("file", "")
                        if expected_file:
                            full_path = files_dir / expected_file
                            deliverables_status[expected_file] = full_path.exists()
                    missing = [k for k, v in deliverables_status.items() if not v]
                    if missing:
                        logger.warning(
                            "[IP-EXEC] Missing deliverables for template '%s': %s",
                            template_slug,
                            missing,
                        )
                    else:
                        logger.info(
                            "[IP-EXEC] All deliverables present for template '%s'",
                            template_slug,
                        )
                    status["deliverables"] = deliverables_status
            except Exception as e:
                logger.warning("[IP-EXEC] Deliverables check failed: %s", e)

        # ── 8. Extract results from conversation ──
        conversation = user_workspace.current_conversation
        conv_id = conversation.id if conversation else None
        status["conversation_id"] = conv_id

        messages: list[dict[str, Any]] = []
        if conversation and conversation.messages:
            for msg in conversation.messages:
                role = getattr(msg, "role", "unknown")
                content = getattr(msg, "content", str(msg))
                if content is None:
                    content = ""
                messages.append({
                    "role": str(role),
                    "content": str(content),
                })
        status["messages_count"] = len(messages)

        # Extract tool call count from agent statistics
        tool_calls_total = 0
        if agent and hasattr(agent, "tool_usage"):
            for usage in agent.tool_usage.values():
                tool_calls_total += getattr(usage, "attempts", 0)
        status["tool_calls_count"] = tool_calls_total
        _notify()

        # Build structured result from the last assistant message
        result: dict[str, Any] | str | None = None
        for msg in reversed(messages):
            if msg.get("role") in ("assistant", "agent"):
                content = msg.get("content", "")
                # Try to parse structured JSON
                try:
                    result = json.loads(content)
                except (json.JSONDecodeError, TypeError):
                    result = content
                break

        if result is None and messages:
            result = {"conversation": messages}

        status["result"] = result
        status["status"] = "completed"
        status["phase"] = "completed"
        status["completed_at"] = datetime.now(UTC).isoformat()

        # ── 9. Write structured panel metadata to workspace.json ──
        _write_panel_metadata(ws_path, module_slug, result)

        # Emit check + act completion spans
        await _emit_ip_trace_span(workspace_id, tid, "check", phase="check", status="success",
                                   output_summary=f"Extracted {len(messages)} messages, {status.get('tool_calls_count', 0)} tool calls")
        await _emit_ip_trace_span(workspace_id, tid, "act", phase="act", status="success",
                                   output_summary=f"Task completed: module={module_slug}")

        logger.info(
            f"[IP-EXEC] Task completed: ws={workspace_id} module={module_slug} "
            f"conv={conv_id} msgs={len(messages)}"
        )

    except Exception as e:
        logger.exception(f"[IP-EXEC] Agent execution failed for workspace {workspace_id}: {e}")
        status["status"] = "failed"
        status["phase"] = "error"
        status["error"] = str(e)[:2000]
        tid = task_id or workspace_id
        await _emit_ip_trace_span(workspace_id, tid, "execution", status="error",
                                   output_summary=str(e)[:200])

    # ── 8. Persist results to workspace ──
    if user_workspace and user_workspace.workspace_path:
        try:
            results_path = user_workspace.workspace_path / ".dawei" / "results.json"
            with results_path.open("w", encoding="utf-8") as f:
                json.dump(status, f, indent=2, ensure_ascii=False, default=str)
            logger.info(f"[IP-EXEC] Results saved to {results_path}")
        except OSError as e:
            logger.warning(f"[IP-EXEC] Failed to save results: {e}")

    _notify()
    return dict(status)


async def execute_ip_task_background(
    task_store: dict[str, dict[str, Any]],
    task_id: str,
    workspace_id: str,
    module_slug: str,
    params: dict[str, Any],
    *,
    template_slug: str | None = None,
    timeout_seconds: int = 600,
) -> None:
    """Execute an IP task in the background, updating task_store as it progresses.

    This is the async entry point for use from REST endpoints.
    It launches the Agent in an asyncio background task and updates the
    shared _task_store dict on completion/failure.

    Args:
        task_store: The in-memory task store dict (shared mutable reference)
        task_id: Unique task identifier
        workspace_id: UUID of the temp workspace
        module_slug: e.g. "ip-draft"
        params: Raw API request params
        template_slug: Optional template slug for template-driven execution
        timeout_seconds: Max execution time
    """
    def _update_store(exec_status: dict[str, Any]) -> None:
        """Update the in-memory task store with current execution state."""
        task_store[task_id] = {
            "module": module_slug,
            "status": exec_status.get("status", "running"),
            "result": exec_status.get("result"),
            "error": exec_status.get("error"),
            "createdAt": exec_status.get("started_at", datetime.now(UTC).isoformat()),
            "workspaceId": workspace_id,
            "conversationId": exec_status.get("conversation_id"),
            "messagesCount": exec_status.get("messages_count", 0),
            "toolCallsCount": exec_status.get("tool_calls_count", 0),
            "phase": exec_status.get("phase"),
        }

    # Mark as running immediately
    _update_store({"status": "running", "phase": "starting"})

    try:
        result = await execute_ip_task(
            workspace_id=workspace_id,
            module_slug=module_slug,
            params=params,
            task_id=task_id,
            template_slug=template_slug,
            on_status_update=_update_store,
            timeout_seconds=timeout_seconds,
        )
        # Final update
        _update_store(result)
        logger.info(
            f"[IP-EXEC-BG] Task {task_id} completed: "
            f"module={module_slug} status={result.get('status')}"
        )
    except Exception as e:
        logger.exception(f"[IP-EXEC-BG] Unhandled error in background task {task_id}: {e}")
        task_store[task_id] = {
            "module": module_slug,
            "status": "failed",
            "result": None,
            "error": f"Agent execution exception: {str(e)[:2000]}",
            "createdAt": datetime.now(UTC).isoformat(),
            "workspaceId": workspace_id,
            "phase": "error",
        }


# ============================================================================
# Result reading helper
# ============================================================================


async def read_task_result_from_workspace(
    workspace_id: str,
) -> dict[str, Any] | None:
    """Read task results from a workspace's .dawei/results.json.

    Args:
        workspace_id: UUID of the temp workspace

    Returns:
        Results dict or None if not found
    """
    ws_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not ws_info:
        return None

    ws_path_str = ws_info.get("path")
    if not ws_path_str:
        return None

    results_path = Path(ws_path_str) / ".dawei" / "results.json"
    if not results_path.exists():
        return None

    try:
        with results_path.open(encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"[IP-EXEC] Failed to read results for {workspace_id}: {e}")
        return None
