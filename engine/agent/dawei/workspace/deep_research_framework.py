# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Deep Research 通用调研框架（PRD §10 #4 复用扩展）。

把「产品调研」流水线中与具体业务无关的任务基础设施抽象为可复用层:

- PipelineSpec            — 流水线声明（stages / gates / 产物契约 / 时限），新调研类型只需声明一份 spec
- DeepResearchServiceBase — 通用工作区服务（脚手架 / 元数据 / 审计 / GATE 状态机 /
                            retry / duplicate / 产物浏览下载 / dao 历史 / 报告分享 / report.html）
- ResearchExecutor        — 通用真实执行器（mode 切换 + LLM Agent + 产物 FAST FAIL + 指数退避重试）
- register_pipeline()     — 流水线注册表（generic router 与分享 token 反查按 route 枚举）

复用方式（以 industry-research 为例）:

    spec = PipelineSpec(slug="industry-research", stages=..., ...)
    class IndustryResearchService(DeepResearchServiceBase):
        def on_stage_completed(self, ...): ...   # 按需覆写 hook
    service = IndustryResearchService(spec)
    service.executor = ResearchExecutor(service)
    register_pipeline("industry", service)

即获得与产品调研完全一致的工作区生命周期、GATE 状态机、dry-run/真实双模式、
REST 面（dawei/api/deep_research.py generic router）与前端可复用的 UI 契约。
"""

from __future__ import annotations

import asyncio
import html as _html
import io
import json
import logging
import random
import re
import secrets
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from dawei import get_dawei_home

logger = logging.getLogger(__name__)

UTC = timezone.utc


class DeepResearchError(Exception):
    """调研框架业务错误（router 转 4xx/5xx）。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_workspace_id() -> str:
    """平台标准 UUID（与 /api/workspaces/create 一致，可直接用于工作区 URL）。"""
    return str(uuid.uuid4())


def _safe_join(root: Path, rel: str) -> Path:
    """相对路径解析，拒绝越界（路径穿越防护）。"""
    if rel in ("", ".", "/"):
        return root
    candidate = (root / rel).resolve()
    root_resolved = root.resolve()
    if not candidate.is_relative_to(root_resolved):
        raise DeepResearchError(f"Illegal path: {rel}", status_code=400)
    return candidate


# ============================================================
# PipelineSpec — 流水线声明
# ============================================================


@dataclass(frozen=True)
class StageDef:
    id: str
    phase: str
    title: str
    mode: str


@dataclass(frozen=True)
class PipelineSpec:
    """一份声明 = 一条可复用全部基础设施的调研流水线。"""

    slug: str  # 存储目录名（DAWEI_HOME/<slug>/）
    name: str  # 展示名（如「产品调研」）
    prompt_label: str  # 执行器提示词头（如「产品调研流水线」）
    team: str
    mode_team: str
    stages: tuple[StageDef, ...]
    phase_labels: Mapping[str, str]
    gate_after_stage: Mapping[str, str]  # stage_id -> gate_id（闸门在该 stage 运行前拦截放行）
    gate_rollback_stage: Mapping[str, str]  # gate_id -> 拒绝时回退到的 stage_id
    gate_labels: Mapping[str, str]
    stage_artifacts: Mapping[str, tuple[str, ...]]  # stage_id -> 契约产物（FAST FAIL 校验）
    stage_minutes: Mapping[str, int]
    entry_gate: str = "GATE-0"  # 需求确认闸（通过后才允许 start）
    max_gate_rounds: int = 3
    gate_timeout_hours: int = 24
    input_doc_path: str = "input/dao.md"
    input_doc_history_dir: str = "input/dao.history"
    required_input_sections: tuple[str, ...] = ()
    final_report_md: str = "reports/report_final.md"
    description: str = ""

    @property
    def stage_ids(self) -> list[str]:
        return [s.id for s in self.stages]

    @property
    def report_html(self) -> str:
        """final_report_md 的 Web 渲染版路径（同目录下固定为 report.html，PRD §10 #5）。"""
        if not self.final_report_md:
            return ""
        from pathlib import PurePosixPath

        return str(PurePosixPath(self.final_report_md).with_name("report.html"))

    @property
    def gate_ids(self) -> list[str]:
        """闸门顺序: entry_gate + 其余按 after_stage 在流水线中的出现顺序。"""
        ids = [self.entry_gate]
        for s in self.stages:
            g = self.gate_after_stage.get(s.id)
            if g and g not in ids:
                ids.append(g)
        return ids


# ============================================================
# Markdown → HTML（report.html Web 渲染版，零依赖）
# ============================================================


def _inline_md(s: str) -> str:
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", r'<img alt="\1" src="\2" loading="lazy">', s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*\s][^*]*)\*(?!\*)", r"<em>\1</em>", s)
    return s


_REPORT_CSS = """body{font-family:-apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;
max-width:860px;margin:0 auto;padding:40px 24px;color:#1f2937;line-height:1.75;background:#fafafa}
h1,h2,h3,h4{color:#111827;line-height:1.3}h1{border-bottom:2px solid #e5e7eb;padding-bottom:.3em}
h2{border-bottom:1px solid #e5e7eb;padding-bottom:.2em;margin-top:1.8em}
code{background:#f3f4f6;padding:.15em .35em;border-radius:4px;font-size:.9em}
pre{background:#f8f9fa;border:1px solid #e5e7eb;border-radius:8px;padding:14px;overflow-x:auto}
pre code{background:none;padding:0}blockquote{border-left:4px solid #d1d5db;margin:1em 0;padding:.2em 1em;color:#4b5563}
table{border-collapse:collapse;width:100%;margin:1em 0}th,td{border:1px solid #e5e7eb;padding:8px 12px;text-align:left}
th{background:#f3f4f6}tr:nth-child(even) td{background:#f9fafb}img{max-width:100%}
hr{border:none;border-top:1px solid #e5e7eb;margin:2em 0}.meta{color:#6b7280;font-size:.9em}"""


def md_to_html(md_text: str, title: str = "Report") -> str:
    """极简 Markdown → 独立 HTML（标题/代码块/行内代码/粗斜体/链接/图片/列表/引用/表格/分隔线）。

    先整体 HTML 转义再重组标签，杜绝注入。缺深度嵌套支持，够报告渲染用。
    """
    lines = _html.escape(md_text or "").splitlines()
    out: list[str] = []
    para: list[str] = []
    code_buf: list[str] = []
    list_type: Optional[str] = None  # "ul" | "ol"
    quote_buf: list[str] = []
    in_code = False

    def flush_para():
        if para:
            out.append(f"<p>{_inline_md(' '.join(para))}</p>")
            para.clear()

    def flush_list():
        nonlocal list_type
        if list_type:
            out.append(f"</{list_type}>")
            list_type = None

    def flush_quote():
        if quote_buf:
            out.append(f"<blockquote>{_inline_md('<br>'.join(quote_buf))}</blockquote>")
            quote_buf.clear()

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_para(); flush_list(); flush_quote()
            if not in_code:
                in_code = True
                code_buf.clear()
            else:
                in_code = False
                out.append("<pre><code>" + "\n".join(code_buf) + "</code></pre>")
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue

        if not stripped:
            flush_para(); flush_list(); flush_quote()
            i += 1
            continue

        # GFM 表格: 当前行含 | 且下一行是分隔行
        if "|" in stripped and i + 1 < n and re.fullmatch(r"[\s|:\-]+", lines[i + 1].strip() or "x"):
            flush_para(); flush_list(); flush_quote()
            header = [c.strip() for c in stripped.strip("|").split("|")]
            rows = []
            j = i + 2
            while j < n and "|" in lines[j] and lines[j].strip():
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                j += 1
            out.append(
                "<table><thead><tr>"
                + "".join(f"<th>{_inline_md(c)}</th>" for c in header)
                + "</tr></thead><tbody>"
                + "".join("<tr>" + "".join(f"<td>{_inline_md(c)}</td>" for c in r) + "</tr>" for r in rows)
                + "</tbody></table>"
            )
            i = j
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            flush_para(); flush_list(); flush_quote()
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline_md(m.group(2))}</h{level}>")
            i += 1
            continue

        if re.fullmatch(r"(-{3,}|\*{3,})", stripped):
            flush_para(); flush_list(); flush_quote()
            out.append("<hr>")
            i += 1
            continue

        # 注意: 输入已整体 _html.escape，块引用标记 ">" 已变为 "&gt;"
        m_quote = re.match(r"^(?:&gt;\s*)+(.*)$", stripped)
        if m_quote:
            flush_para(); flush_list()
            quote_buf.append(m_quote.group(1).strip())
            i += 1
            continue

        m = re.match(r"^[-*+]\s+(.*)$", stripped)
        if m:
            flush_para(); flush_quote()
            if list_type != "ul":
                flush_list()
                out.append("<ul>")
                list_type = "ul"
            out.append(f"<li>{_inline_md(m.group(1))}</li>")
            i += 1
            continue

        m = re.match(r"^\d+[.)]\s+(.*)$", stripped)
        if m:
            flush_para(); flush_quote()
            if list_type != "ol":
                flush_list()
                out.append("<ol>")
                list_type = "ol"
            out.append(f"<li>{_inline_md(m.group(1))}</li>")
            i += 1
            continue

        flush_list(); flush_quote()
        para.append(stripped)
        i += 1

    flush_para(); flush_list(); flush_quote()
    if in_code and code_buf:  # 未闭合代码块
        out.append("<pre><code>" + "\n".join(code_buf) + "</code></pre>")

    return (
        f"<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{_html.escape(title)}</title>\n<style>{_REPORT_CSS}</style>\n</head>\n<body>\n"
        + "\n".join(out)
        + "\n</body>\n</html>\n"
    )


# ============================================================
# 通用工作区服务
# ============================================================


class DeepResearchServiceBase:
    """通用调研工作区服务。业务差异全部通过 hook 注入（见各 def _hook）。

    元数据落盘 workspace.json（§6.7 契约），存储布局:
      DAWEI_HOME/<spec.slug>/<workspace_id>/
        input/dao.md(+dao.history/)  output/<phase>/<stage>/  reports/  references/
    """

    def __init__(self, spec: PipelineSpec, storage_root: Optional[Path] = None):
        self.spec = spec
        self._storage_root = storage_root
        self.executor: Optional["ResearchExecutor"] = None  # 底部延迟绑定，避免循环导入

    # --------------------------------------------------------
    # 业务 hook（子类按需覆写）
    # --------------------------------------------------------

    def render_input_doc(self, params: dict[str, Any]) -> str:
        """生成需求文档（dao.md）。默认渲染四段结构骨架。"""
        topic = params.get("topic", "")
        dims = params.get("dimensions") or []
        dim_lines = "\n".join(
            f"{i + 1}. **{d.get('key', f'D{i + 1}')}**: {d.get('name', '')} — {d.get('description', '')}"
            for i, d in enumerate(dims)
        ) or "-（未指定细分维度，按主题整体调研）"
        return f"""# dao.md

## Overview

对 **{topic}** 开展系统性深度调研，产出结构化、来源可追溯的全景报告。

## Goals

- 建立主题全景索引（关键实体、格局、数据）
- 梳理核心结论与可验证事实（每条标注来源 URL）
- 产出面向决策者的报告

### 必须

- 所有事实性信息标注来源 URL
- 缺失字段留空，绝不编造

### 优选

- 包含市场规模/增速等量化数据
- 识别趋势与空白地带

## 约定

- 信息优先来源：官方网站 > 权威报告 > 权威评测 > 社区讨论
- 覆盖中国与海外市场
"""

    def validate_input_doc(self, content: str) -> dict[str, Any]:
        """需求文档四段结构校验摘要。"""
        checks = []
        for section in self.spec.required_input_sections:
            idx = content.find(section)
            present = idx >= 0
            non_empty = False
            if present:
                tail = content[idx + len(section):]
                nxt = re.search(r"^#{2,3} ", tail, flags=re.MULTILINE)
                body = tail[: nxt.start()] if nxt else tail
                non_empty = bool(re.sub(r"[\s\-*>`#]", "", body))
            checks.append({"section": section, "present": present, "non_empty": non_empty})
        return {"valid": all(c["present"] and c["non_empty"] for c in checks), "checks": checks}

    def build_task_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """input/task_parameters.json 内容。默认剔除内部字段后原样落盘。"""
        return {
            k: v for k, v in params.items() if not k.startswith("_") and k != "input_doc"
        }

    def write_references(self, ws_dir: Path, params: dict[str, Any]) -> None:
        """references/ 附加文件（mode team 元数据等）。默认无操作。"""

    def render_agent_instructions(self, params: dict[str, Any]) -> str:
        """AGENT_INSTRUCTIONS.md。"""
        topic = params.get("topic", "")
        stage_lines = "\n".join(
            f"- {s.phase} {s.id} {s.title}（mode: {s.mode}）" for s in self.spec.stages
        )
        return f"""# {topic} — Agent 工作指令

你已加入 {self.spec.name}工作区（mode team: {self.spec.mode_team}），按流水线逐 stage 执行。

## 输入

1. `{self.spec.input_doc_path}` — 需求文档（闸门确认后的唯一权威输入）
2. `input/task_parameters.json` — 用户提交的参数

## 流水线

{stage_lines}

## 约定

- 数据源优先级：官方网站 > 权威报告 > 权威评测 > 社区讨论
- 所有事实性信息标注来源 URL；缺失字段留空不编造
- 产物写入 `output/<phase>/<stage>/`，最终交付物写入 `reports/`
"""

    def initial_metrics(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"total_tokens": 0, "total_minutes": 0}

    def stub_artifact(self, meta: dict[str, Any], stage: dict[str, Any], rel: str) -> str:
        """dry-run 占位产物。"""
        topic = meta.get("topic", "")
        sid = stage["id"]
        if rel.endswith(".json") or rel.endswith(".jsonl"):
            return json.dumps({"_dry_run": True, "stage": sid, "topic": topic, "generated_at": _now_iso()}, ensure_ascii=False)
        if rel.endswith(".yaml"):
            return f"# dry-run stub ({sid})\ntopic: {topic}\n"
        return f"# {topic} — {stage['title']}（dry-run 占位）\n\n真实执行将填充本产物。\n"

    def on_stage_completed(self, ws_dir: Path, meta: dict[str, Any], stage: dict[str, Any], stage_dir: Path) -> None:
        """stage 成功收尾 hook（指标累计 / reports 汇总等业务逻辑）。"""

    def enrich_detail(self, ws_dir: Path, meta: dict[str, Any]) -> None:
        """get_workspace 详情增强 hook（如 GATE-1 维度覆盖预览）。"""

    def regenerate_input_doc(self, ws_dir: Path, meta: dict[str, Any], gate: dict[str, Any], note: str) -> None:
        """entry gate 拒绝后重新生成需求文档（写入 spec.input_doc_path）。"""
        raise DeepResearchError(f"reject not supported for {gate['id']} in {self.spec.slug}", status_code=400)

    def duplicate_extras(self, src_ws: Path, dst_ws: Path) -> None:
        """duplicate 时额外复制的产物文件。"""

    @property
    def default_template_slug(self) -> str:
        """task_parameters 缺 template_slug 时的兜底。"""
        return ""

    # --------------------------------------------------------
    # 存储布局
    # --------------------------------------------------------

    @property
    def storage_root(self) -> Path:
        # 动态读取（DAWEI_HOME 可被测试 monkeypatch）
        return self._storage_root if self._storage_root else get_dawei_home() / self.spec.slug

    def _ws_dir(self, workspace_id: str) -> Path:
        d = self.storage_root / workspace_id
        if not d.is_dir():
            raise DeepResearchError(f"Workspace not found: {workspace_id}", status_code=404)
        return d

    # --------------------------------------------------------
    # 工作区 CRUD
    # --------------------------------------------------------

    async def create_workspace(
        self,
        topic: str,
        mode: str = "direct",
        background: str = "",
        audience: str = "",
        user_input: str = "",
        scope: Optional[dict[str, Any]] = None,
        dimensions: Optional[list[dict[str, Any]]] = None,
        success_criteria: Optional[dict[str, Any]] = None,
        input_doc: Optional[str] = None,
        template_slug: Optional[str] = None,
        template_name: Optional[str] = None,
        user_id: str = "anonymous",
        tenant_id: str = "default",
        skip_gate0: bool = False,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """通用创建入口（产品调研等复杂模板体系可在子类扩展签名后转调本方法）。"""
        if mode not in ("direct", "wizard"):
            raise DeepResearchError(f"Invalid mode: {mode}")
        if not topic or not topic.strip():
            raise DeepResearchError("topic is required")
        params: dict[str, Any] = {
            "template_slug": template_slug,
            "template_name": template_name or template_slug,
            "topic": topic,
            "mode": mode,
            "background": background,
            "audience": audience,
            "user_input": user_input,
            "scope": scope,
            "dimensions": dimensions,
            "success_criteria": success_criteria,
            "input_doc": input_doc,
        }
        return await self._create_workspace_internal(
            params, user_id=user_id, tenant_id=tenant_id, skip_gate0=skip_gate0, dry_run=dry_run
        )

    async def _create_workspace_internal(
        self,
        params: dict[str, Any],
        user_id: str = "anonymous",
        tenant_id: str = "default",
        skip_gate0: bool = False,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """创建一个真实的平台工作区（Task-as-Workspace）+ 调研脚手架 + 调研会话。

        1. 目录 = 平台标准布局（.dawei/ + 调研产物目录），注册进 workspaces.json
           → 复用工作区文件 API / 消息 API / 前端工作区管理 UI
        2. 调研流水线元数据 → .dawei/deep_research.json（旧版根目录 workspace.json 兼容读取）
        3. 创建调研会话（conversation，即前端"任务"）并写入概览首条消息
           → 执行阶段消息全部落入该会话，/app-ui/workspace/{id}/task/{conversation_id} 可直接查看
        """
        spec = self.spec
        topic = params["topic"]
        workspace_id = _new_workspace_id()
        ws_dir = self.storage_root / workspace_id
        ws_dir.mkdir(parents=True, exist_ok=False)

        # ---- 平台工作区结构: .dawei/ ----
        dawei_dir = ws_dir / ".dawei"
        for sub in ("chat-history", "checkpoints", "task_graphs", "conversations"):
            (dawei_dir / sub).mkdir(parents=True, exist_ok=True)
        now = _now_iso()
        (dawei_dir / "workspace.json").write_text(
            json.dumps(
                {
                    "id": workspace_id,
                    "name": f"{spec.slug}-{workspace_id[:8]}",
                    "display_name": topic[:60],
                    "description": params.get("template_name") or spec.name,
                    "created_at": now,
                    "workspace_type": "deep-research",
                    "lifecycle": "persistent",
                    "deep_research": {"pipeline": spec.slug, "topic": topic},
                    "last_accessed_at": now,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        # ---- 调研脚手架: output/<phase>/<stage>/ + reports/references/input ----
        for s in spec.stages:
            (ws_dir / "output" / s.phase / s.id).mkdir(parents=True, exist_ok=True)
        for sub in ("reports", "references", "input"):
            (ws_dir / sub).mkdir(parents=True, exist_ok=True)

        # ---- input/task_parameters.json ----
        (ws_dir / "input" / "task_parameters.json").write_text(
            json.dumps(self.build_task_params(params), ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # ---- input/dao.md（唯一权威位置）----
        dao_content = params.get("input_doc") or self.render_input_doc(params)
        (ws_dir / spec.input_doc_path).write_text(dao_content, encoding="utf-8")

        self.write_references(ws_dir, params)
        (ws_dir / "AGENT_INSTRUCTIONS.md").write_text(self.render_agent_instructions(params), encoding="utf-8")

        # ---- 调研元数据 → .dawei/deep_research.json ----
        gates = []
        for gid in spec.gate_ids:
            is_entry = gid == spec.entry_gate
            gates.append(
                {
                    "id": gid,
                    "label": spec.gate_labels.get(gid, gid),
                    "status": "passed" if (is_entry and skip_gate0) else "pending",
                    "round": 0,
                    "pending_since": None if (is_entry and skip_gate0) else (now if is_entry else None),
                    "decided_at": now if (is_entry and skip_gate0) else None,
                    **({"note": "复制任务，跳过需求确认"} if (is_entry and skip_gate0) else {}),
                }
            )
        meta = {
            "workspace_id": workspace_id,
            "slug": params.get("template_slug"),
            "template_name": params.get("template_name") or params.get("template_slug"),
            "topic": topic,
            "team": spec.team,
            "mode_team": spec.mode_team,
            "status": "created",
            "created_at": now,
            "updated_at": now,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "dao_path": spec.input_doc_path,
            "dry_run": dry_run,
            "stages": [
                {"id": s.id, "phase": s.phase, "title": s.title, "mode": s.mode, "status": "pending"}
                for s in spec.stages
            ],
            "gates": gates,
            "metrics": self.initial_metrics(params),
        }

        # ---- 调研会话（前端任务）: 概览首条消息 ----
        conversation_id = await self._create_research_conversation(ws_dir, meta)
        meta["conversation_id"] = conversation_id
        self._save_meta(ws_dir, meta)

        # ---- 注册进系统索引（~/.normnomos/workspaces.json）----
        await self._register_in_workspace_index(ws_dir, meta)

        self._append_audit(
            ws_dir,
            "workspace.created",
            {"template": params.get("template_slug"), "topic": topic, "mode": params.get("mode", "direct")},
        )
        return meta

    async def _create_research_conversation(self, ws_dir: Path, meta: dict[str, Any]) -> str:
        """创建调研会话并写入概览首条消息（会话 ID = 前端任务 ID）。"""
        from dawei.conversation.conversation import Conversation
        from dawei.conversation.conversation_history_manager import ConversationHistoryManager
        from dawei.entity.lm_messages import AssistantMessage

        conversation_id = str(uuid.uuid4())
        stage_lines = "\n".join(f"- {s['title']}（{s['id']}）" for s in meta["stages"])
        overview = (
            f"## {meta.get('topic', '')} — {self.spec.name}\n\n"
            f"本任务由深度调研流水线驱动（{len(meta['stages'])} 个 stage），"
            f"执行进度与产物将实时更新在本会话与工作区文件中。\n\n"
            f"### 流水线\n{stage_lines}\n\n"
            f"### 下一步\n"
            f"- 待 {self.spec.entry_gate} 需求确认（`{self.spec.input_doc_path}`）\n"
            f"- 确认通过后流水线自动启动；产物目录 `output/`，最终报告 `reports/`"
        )
        conversation = Conversation(
            id=conversation_id,
            title=meta.get("topic", self.spec.name)[:60],
            task_type="user",
            agent_mode=meta["stages"][0]["mode"] if meta["stages"] else None,
            messages=[
                AssistantMessage(id=str(uuid.uuid4()), content=overview, timestamp=datetime.now(UTC))
            ],
            metadata={
                "deep_research": {
                    "pipeline": self.spec.slug,
                    "workspace_id": meta["workspace_id"],
                }
            },
        )
        conversation.message_count = 1
        manager = ConversationHistoryManager(workspace_path=str(ws_dir))
        await manager.add_conversation(conversation)
        return conversation_id

    async def _register_in_workspace_index(self, ws_dir: Path, meta: dict[str, Any]) -> None:
        """注册到系统级索引 workspaces.json（与 /api/workspaces/create 同源）。"""
        from dawei.storage.storage_provider import StorageProvider
        from dawei.workspace.models import WorkspaceLifecycle
        from dawei.workspace.workspace_manager import workspace_manager

        system_storage = StorageProvider.get_system_storage()
        try:
            content = await system_storage.read_file("workspaces.json")
            data = json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {"workspaces": []}

        # 幂等：同 id 已注册则跳过
        if any(w.get("id") == meta["workspace_id"] for w in data.get("workspaces", [])):
            return

        # 身份归一化：索引默认身份为 default_user/personal（anonymous/default 为调研侧遗留默认值）
        owner_user_id = meta.get("user_id") or "default_user"
        if owner_user_id == "anonymous":
            owner_user_id = "default_user"
        tenant_id = meta.get("tenant_id") or "personal"
        if tenant_id == "default":
            tenant_id = "personal"

        data["workspaces"].append(
            {
                "id": meta["workspace_id"],
                "name": f"{self.spec.slug}-{meta['workspace_id'][:8]}",
                "display_name": meta.get("topic", self.spec.name)[:60],
                "path": str(ws_dir.resolve()),
                "created_at": _now_iso(),
                "is_active": True,
                "lifecycle": WorkspaceLifecycle.PERSISTENT.value,
                "workspace_type": "deep-research",
                "owner_user_id": owner_user_id,
                "tenant_id": tenant_id,
                "deep_research": {"pipeline": self.spec.slug},
            }
        )
        await system_storage.write_file(
            "workspaces.json", json.dumps(data, indent=2, ensure_ascii=False)
        )
        StorageProvider.clear_system_storage_cache()
        workspace_manager.reload()

    def list_workspaces(self) -> list[dict[str, Any]]:
        root = self.storage_root
        if not root.is_dir():
            return []
        result = []
        for ws_dir in sorted(root.iterdir()):
            if not ws_dir.is_dir() or ws_dir.name.startswith("."):
                continue
            meta = self._load_meta(ws_dir)
            if not meta:
                continue
            self._apply_gate_timeout(ws_dir, meta)
            result.append(self._summary(meta))
        result.sort(key=lambda m: m.get("created_at", ""), reverse=True)
        return result

    def get_workspace(self, workspace_id: str) -> dict[str, Any]:
        ws_dir = self._ws_dir(workspace_id)
        meta = self._load_meta(ws_dir)
        if not meta:
            raise DeepResearchError(f"Workspace metadata broken: {workspace_id}", status_code=500)
        self._apply_gate_timeout(ws_dir, meta)
        meta["phase_labels"] = dict(self.spec.phase_labels)
        meta["gate_after_stage"] = dict(self.spec.gate_after_stage)
        self.enrich_detail(ws_dir, meta)
        return meta

    async def delete_workspace(self, workspace_id: str, actor: str = "user") -> dict[str, Any]:
        """删除调研工作区（不可恢复）：磁盘目录 + 系统索引注册 + 分享 token。

        - running 中的工作区拒绝删除（FAST FAIL 409，防止执行器写已删除目录）
        - 镜像 _register_in_workspace_index：从 workspaces.json 移除并 reload
        """
        import shutil

        if self.executor and workspace_id in self.executor._running:
            raise DeepResearchError("Workspace is running; wait for completion before delete", status_code=409)

        ws_dir = self._ws_dir(workspace_id)  # 不存在 → 404
        meta = self._load_meta(ws_dir) or {}

        # 1) 清理该工作区的分享 token（.shares.json）
        token = (meta.get("share") or {}).get("token")
        if token:
            shares = self._load_shares()
            if shares.pop(token, None) is not None:
                self._shares_index_path().write_text(
                    json.dumps({"tokens": shares}, ensure_ascii=False, indent=2), encoding="utf-8"
                )

        # 2) 删除磁盘目录（含 .dawei 元数据 / 会话 / 审计 / 产物）
        shutil.rmtree(ws_dir)

        # 3) 系统级索引 workspaces.json 移除注册（与 _register_in_workspace_index 镜像）
        from dawei.storage.storage_provider import StorageProvider
        from dawei.workspace.workspace_manager import workspace_manager

        system_storage = StorageProvider.get_system_storage()
        try:
            content = await system_storage.read_file("workspaces.json")
            data = json.loads(content)
            remaining = [w for w in data.get("workspaces", []) if w.get("id") != workspace_id]
            if len(remaining) != len(data.get("workspaces", [])):
                await system_storage.write_file(
                    "workspaces.json", json.dumps({"workspaces": remaining}, indent=2, ensure_ascii=False)
                )
        except (FileNotFoundError, json.JSONDecodeError):
            pass  # 索引缺失 = 无需反注册（目录已删，FAST FAIL 不阻断）
        StorageProvider.clear_system_storage_cache()
        workspace_manager.reload()

        logger.info("Deep-research workspace deleted: %s/%s (actor=%s)", self.spec.slug, workspace_id, actor)
        return {"workspace_id": workspace_id, "deleted": True, "topic": meta.get("topic")}

    @staticmethod
    def _summary(meta: dict[str, Any]) -> dict[str, Any]:
        return {
            "workspace_id": meta["workspace_id"],
            "slug": meta.get("slug"),
            "template_name": meta.get("template_name"),
            "topic": meta.get("topic"),
            "team": meta.get("team"),
            "mode_team": meta.get("mode_team"),
            "status": meta["status"],
            "created_at": meta.get("created_at"),
            "updated_at": meta.get("updated_at"),
            "stages_completed": sum(1 for s in meta["stages"] if s["status"] == "completed"),
            "stages_total": len(meta["stages"]),
            "pending_gate": next((g["id"] for g in meta["gates"] if g["status"] == "pending"), None),
            "metrics": meta.get("metrics"),
            "conversation_id": meta.get("conversation_id"),
        }

    # --------------------------------------------------------
    # 元数据读写 / 审计
    # --------------------------------------------------------

    @staticmethod
    def _meta_path(ws_dir: Path) -> Path:
        return ws_dir / ".dawei" / "deep_research.json"

    def _load_meta(self, ws_dir: Path) -> Optional[dict[str, Any]]:
        p = self._meta_path(ws_dir)
        if not p.exists():
            # 旧版布局：元数据在工作区根目录 workspace.json（Task-as-Workspace 之前）
            p = ws_dir / "workspace.json"
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load workspace meta %s: %s", p, e)
            return None

    def _save_meta(self, ws_dir: Path, meta: dict[str, Any]) -> None:
        meta["updated_at"] = _now_iso()
        self._meta_path(ws_dir).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def _append_audit(self, ws_dir: Path, action: str, detail: dict[str, Any], actor: str = "user") -> None:
        entry = {"at": _now_iso(), "actor": actor, "action": action, "detail": detail}
        with (ws_dir / "audit_log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_audit_log(self, workspace_id: str) -> list[dict[str, Any]]:
        ws_dir = self._ws_dir(workspace_id)
        log_file = ws_dir / "audit_log.jsonl"
        if not log_file.exists():
            return []
        entries = []
        for line in log_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries

    @staticmethod
    def _gate(meta: dict[str, Any], gate_id: str) -> dict[str, Any]:
        for g in meta["gates"]:
            if g["id"] == gate_id:
                return g
        raise DeepResearchError(f"Gate not found: {gate_id}", status_code=404)

    def _apply_gate_timeout(self, ws_dir: Path, meta: dict[str, Any]) -> None:
        """GATE 等待超过时限 → 任务自动暂停。"""
        if meta["status"] not in ("created", "running"):
            return
        changed = False
        for g in meta["gates"]:
            if g["status"] == "pending" and g.get("pending_since"):
                try:
                    since = datetime.fromisoformat(g["pending_since"])
                except ValueError:
                    continue
                if datetime.now(UTC) - since > timedelta(hours=self.spec.gate_timeout_hours):
                    meta["status"] = "paused"
                    g["timeout"] = True
                    changed = True
        if changed:
            self._save_meta(ws_dir, meta)
            self._append_audit(ws_dir, "gate.timeout", {"status": "paused"})

    # --------------------------------------------------------
    # 流水线推进
    # --------------------------------------------------------

    def start(self, workspace_id: str, dry_run: bool = True) -> dict[str, Any]:
        """启动/继续流水线。要求 entry gate 已通过。

        dry_run=True  → 同步占位推进（可演示/可测试）
        dry_run=False → 真实执行（ResearchExecutor 后台跑 LLM Agent）
        """
        spec = self.spec
        ws_dir = self._ws_dir(workspace_id)
        meta = self._load_meta(ws_dir)
        gate0 = self._gate(meta, spec.entry_gate)
        if gate0["status"] != "passed":
            raise DeepResearchError("GATE-0 not passed; pipeline refused to start", status_code=409)
        if meta["status"] in ("completed",):
            raise DeepResearchError("Workspace already completed", status_code=409)
        meta["status"] = "running"
        meta["dry_run"] = dry_run
        self._save_meta(ws_dir, meta)
        self._append_audit(ws_dir, "pipeline.started", {"dry_run": dry_run})
        if dry_run:
            return self._advance(ws_dir, meta)
        # ---- 真实执行 ----
        if self.executor is None:
            raise DeepResearchError("Real execution not available (executor not attached)", status_code=503)
        launched = self.executor.launch(workspace_id)
        if not launched:
            self._append_audit(ws_dir, "pipeline.launch_ignored", {"reason": "already running"})
        return self.get_workspace(workspace_id)

    def _advance(self, ws_dir: Path, meta: dict[str, Any]) -> dict[str, Any]:
        """顺序推进 pending stage，在未通过的闸门前或全部完成后停止。"""
        for stage in meta["stages"]:
            if stage["status"] != "pending":
                continue
            gate_id = self.spec.gate_after_stage.get(stage["id"])
            if gate_id:
                gate = self._gate(meta, gate_id)
                if gate["status"] != "passed":
                    self._save_meta(ws_dir, meta)
                    return meta
            self._run_stage(ws_dir, meta, stage)
        meta["status"] = "completed"
        self._save_meta(ws_dir, meta)
        self._append_audit(ws_dir, "pipeline.completed", {"metrics": meta["metrics"]})
        return meta

    def _run_stage(self, ws_dir: Path, meta: dict[str, Any], stage: dict[str, Any]) -> None:
        """dry-run：落占位产物 + 收尾（真实执行由 ResearchExecutor 调 _finalize_stage）。"""
        stage_dir = ws_dir / "output" / stage["phase"] / stage["id"]
        stage_dir.mkdir(parents=True, exist_ok=True)
        for rel in self.spec.stage_artifacts.get(stage["id"], ()):
            fpath = stage_dir / rel
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(self.stub_artifact(meta, stage, rel), encoding="utf-8")
        self._finalize_stage(ws_dir, meta, stage, random.randint(400, 1800))

    def _finalize_stage(self, ws_dir: Path, meta: dict[str, Any], stage: dict[str, Any], tokens: int) -> None:
        """stage 执行成功后的统一收尾（dry-run 与真实执行共用）。

        时间戳/tokens/指标累计/reports 汇总/report.html 生成/开闸。
        """
        spec = self.spec
        now = _now_iso()
        stage["status"] = "completed"
        stage["ended_at"] = now
        if not stage.get("started_at"):
            stage["started_at"] = now
        stage["tokens"] = tokens
        stage.pop("error", None)

        stage_dir = ws_dir / "output" / stage["phase"] / stage["id"]
        metrics = meta["metrics"]
        metrics["total_tokens"] = metrics.get("total_tokens", 0) + stage["tokens"]
        metrics["total_minutes"] = metrics.get("total_minutes", 0) + spec.stage_minutes.get(stage["id"], 5)

        # 业务 hook（指标累计 / reports 汇总等）
        self.on_stage_completed(ws_dir, meta, stage, stage_dir)

        # 最终 stage → 由 final_report_md 生成 report.html（Web 渲染版，PRD §10 #5）
        if spec.final_report_md and stage["id"] == spec.stage_ids[-1]:
            md_path = ws_dir / spec.final_report_md
            if md_path.is_file():
                html_path = ws_dir / spec.report_html
                html_path.write_text(
                    md_to_html(md_path.read_text(encoding="utf-8"), title=meta.get("topic", spec.name)),
                    encoding="utf-8",
                )

        # 完成带闸门的 stage 后，打开对应闸门等待决策
        gate_id = spec.gate_after_stage.get(stage["id"])
        if gate_id:
            gate = self._gate(meta, gate_id)
            if gate["status"] == "pending" and not gate.get("pending_since"):
                gate["pending_since"] = _now_iso()

    # --------------------------------------------------------
    # GATE 决策
    # --------------------------------------------------------

    def decide_gate(
        self,
        workspace_id: str,
        gate_id: str,
        action: str,
        note: str = "",
        dao_md: str = "",
        actor: str = "user",
    ) -> dict[str, Any]:
        """GATE 决策。

        action:
          approve — 通过
          reject  — 拒绝（entry gate → 重新生成需求文档；其余 → 回退补采）
          edit    — （仅 entry gate）编辑后重新解析
        轮次上限 spec.max_gate_rounds，超过 → needs_manual。
        """
        spec = self.spec
        if action not in ("approve", "reject", "edit"):
            raise DeepResearchError(f"Invalid action: {action}")
        ws_dir = self._ws_dir(workspace_id)
        meta = self._load_meta(ws_dir)
        gate = self._gate(meta, gate_id)
        if gate["status"] == "passed":
            raise DeepResearchError(f"{gate_id} already passed", status_code=409)
        if meta["status"] == "needs_manual":
            raise DeepResearchError("GATE rounds exhausted; manual dao.md required", status_code=409)
        if gate_id == spec.entry_gate and action == "edit":
            if not dao_md.strip():
                raise DeepResearchError("dao_md content required for edit action")
            validation = self.validate_input_doc(dao_md)
            if not validation["valid"]:
                raise DeepResearchError(
                    f"dao.md sections incomplete: {[c['section'] for c in validation['checks'] if not (c['present'] and c['non_empty'])]}"
                )

        gate["round"] += 1
        if gate["round"] > spec.max_gate_rounds:
            meta["status"] = "needs_manual"
            self._save_meta(ws_dir, meta)
            self._append_audit(ws_dir, "gate.rounds_exhausted", {"gate": gate_id})
            raise DeepResearchError(
                f"{gate_id} rejected {spec.max_gate_rounds} times; please write dao.md manually", status_code=409
            )

        if action == "approve":
            gate["status"] = "passed"
            gate["decided_at"] = _now_iso()
            gate["pending_since"] = None
            gate.pop("timeout", None)
            if note:
                gate["note"] = note
            self._save_meta(ws_dir, meta)
            self._append_audit(ws_dir, "gate.approved", {"gate": gate_id, "round": gate["round"], "note": note}, actor)
            if gate_id == spec.entry_gate:
                # 需求确认通过 → 启动流水线（推进到下一闸门前）
                self.start(workspace_id, dry_run=meta.get("dry_run", True))
                return self.get_workspace(workspace_id)
            # 其余闸门通过 → 继续推进剩余 stage 至完成
            meta["status"] = "running"
            self._save_meta(ws_dir, meta)
            if meta.get("dry_run", True):
                self._advance(ws_dir, meta)
            else:
                self.executor.launch(workspace_id)
            return self.get_workspace(workspace_id)

        # ---- reject / edit ----
        gate["status"] = "pending"
        gate["pending_since"] = _now_iso()
        if note:
            gate["note"] = note
        if gate_id == spec.entry_gate:
            self._archive_input_doc(ws_dir, gate)  # #5 diff 视图数据源
            if action == "edit":
                (ws_dir / spec.input_doc_path).write_text(dao_md, encoding="utf-8")
                self._append_audit(ws_dir, "gate.dao_edited", {"gate": gate_id, "round": gate["round"]}, actor)
            else:
                self.regenerate_input_doc(ws_dir, meta, gate, note)
                self._append_audit(ws_dir, "gate.rejected_dao_regenerated", {"gate": gate_id, "round": gate["round"], "note": note}, actor)
            self._save_meta(ws_dir, meta)
            return self.get_workspace(workspace_id)

        # 其余闸门拒绝 → 回退补采
        if action == "reject":
            rollback_to = spec.gate_rollback_stage.get(gate_id)
            if not rollback_to:
                raise DeepResearchError(f"action '{action}' not supported for {gate_id}")
            idx = spec.stage_ids.index(rollback_to)
            for stage in meta["stages"][idx:]:
                stage["status"] = "pending"
                stage.pop("started_at", None)
                stage.pop("ended_at", None)
                stage.pop("tokens", None)
                stage.pop("error", None)
            meta["status"] = "running"
            gate["pending_since"] = None
            self._save_meta(ws_dir, meta)
            self._append_audit(
                ws_dir, "gate.rejected_rollback", {"gate": gate_id, "round": gate["round"], "rollback_to": rollback_to, "note": note}, actor
            )
            # 自动补采：重新推进至该闸门（真实模式走 executor）
            if meta.get("dry_run", True):
                self._advance(ws_dir, meta)
            else:
                self.executor.launch(workspace_id)
            return self.get_workspace(workspace_id)

        raise DeepResearchError(f"action '{action}' not supported for {gate_id}")

    # --------------------------------------------------------
    # 需求文档历史（PRD §10 #5 diff 视图数据源）
    # --------------------------------------------------------

    def _archive_input_doc(self, ws_dir: Path, gate: dict[str, Any]) -> None:
        """覆写需求文档前归档当前版本 → input/dao.history/<GATE>-r<round>-<ts>.md"""
        spec = self.spec
        doc = ws_dir / spec.input_doc_path
        if not doc.is_file():
            return
        hist_dir = ws_dir / spec.input_doc_history_dir
        hist_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        name = f"{gate['id']}-r{gate.get('round', 0)}-{ts}.md"
        (hist_dir / name).write_text(doc.read_text(encoding="utf-8"), encoding="utf-8")

    def get_input_doc_history(self, workspace_id: str) -> dict[str, Any]:
        """当前 dao.md + 历史版本列表（按时间正序）。"""
        spec = self.spec
        ws_dir = self._ws_dir(workspace_id)
        hist_dir = ws_dir / spec.input_doc_history_dir
        history = []
        if hist_dir.is_dir():
            for f in sorted(hist_dir.glob("*.md")):
                m = re.match(r"^(GATE-\d+)-r(\d+)-(.+)\.md$", f.name)
                try:
                    at = datetime.strptime(m.group(3).split("T")[0], "%Y%m%d").replace(tzinfo=UTC).isoformat() if m else datetime.fromtimestamp(f.stat().st_mtime, UTC).isoformat()
                except ValueError:
                    at = datetime.fromtimestamp(f.stat().st_mtime, UTC).isoformat()
                history.append(
                    {
                        "file": f.name,
                        "gate": m.group(1) if m else "",
                        "round": int(m.group(2)) if m else 0,
                        "at": at,
                        "content": f.read_text(encoding="utf-8"),
                    }
                )
        doc = ws_dir / spec.input_doc_path
        return {
            "path": spec.input_doc_path,
            "current": doc.read_text(encoding="utf-8") if doc.is_file() else None,
            "history": history,
        }

    # --------------------------------------------------------
    # retry / duplicate
    # --------------------------------------------------------

    def retry(self, workspace_id: str, from_stage: str, actor: str = "user") -> dict[str, Any]:
        """从指定 stage 重跑：该 stage 及其后置为 pending，重新推进。"""
        spec = self.spec
        stage_ids = spec.stage_ids
        if from_stage not in stage_ids:
            raise DeepResearchError(f"Unknown stage: {from_stage}", status_code=404)
        ws_dir = self._ws_dir(workspace_id)
        meta = self._load_meta(ws_dir)
        if meta["status"] == "needs_manual":
            raise DeepResearchError("GATE rounds exhausted; manual dao.md required", status_code=409)
        idx = stage_ids.index(from_stage)
        for stage in meta["stages"][idx:]:
            stage["status"] = "pending"
            stage.pop("started_at", None)
            stage.pop("ended_at", None)
            stage.pop("tokens", None)
            stage.pop("error", None)
        # 重跑范围覆盖某闸门的审核点（该闸门 after_stage）→ 闸门重新打开
        for after_stage_id, gid in spec.gate_after_stage.items():
            if idx <= stage_ids.index(after_stage_id):
                gate = self._gate(meta, gid)
                if gate["status"] == "passed":
                    gate["status"] = "pending"
                    gate["pending_since"] = None
        meta["status"] = "running"
        self._save_meta(ws_dir, meta)
        self._append_audit(ws_dir, "pipeline.retry", {"from_stage": from_stage}, actor)
        if meta.get("dry_run", True):
            return self._advance(ws_dir, meta)
        self.executor.launch(workspace_id)
        return self.get_workspace(workspace_id)

    async def duplicate(self, workspace_id: str, actor: str = "user") -> dict[str, Any]:
        """复制为新任务：需求文档 + task_parameters 复用，跳过 entry gate。"""
        spec = self.spec
        src = self._ws_dir(workspace_id)
        params = self._read_task_params(src)
        src_meta = self._load_meta(src) or {}
        doc_path = src / spec.input_doc_path
        doc_content = doc_path.read_text(encoding="utf-8") if doc_path.exists() else ""
        new_meta = await self._create_workspace_internal(
            {
                **params,
                "template_slug": params.get("template_slug") or self.default_template_slug or None,
                "template_name": params.get("template_name"),
                "topic": f"{params.get('topic', spec.name)}（副本）",
                "input_doc": doc_content or None,
            },
            user_id=actor,
            skip_gate0=True,
            dry_run=src_meta.get("dry_run", True),
        )
        new_dir = self.storage_root / new_meta["workspace_id"]
        self.duplicate_extras(src, new_dir)
        self._append_audit(new_dir, "workspace.duplicated_from", {"source": workspace_id}, actor)
        return new_meta

    @staticmethod
    def _read_task_params(ws_dir: Path) -> dict[str, Any]:
        p = ws_dir / "input" / "task_parameters.json"
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    # --------------------------------------------------------
    # 产物浏览 / 下载
    # --------------------------------------------------------

    def list_files(self, workspace_id: str, path: str = "") -> dict[str, Any]:
        ws_dir = self._ws_dir(workspace_id)
        target = _safe_join(ws_dir, path)
        if not target.exists():
            raise DeepResearchError(f"Path not found: {path}", status_code=404)
        if target.is_file():
            return {
                "path": path,
                "type": "file",
                "size": target.stat().st_size,
                "entries": [],
            }
        entries = []
        for child in sorted(target.iterdir()):
            if child.name == ".dawei":
                continue  # 平台内部状态（会话/配置），不作为调研产物暴露
            rel = str(child.relative_to(ws_dir))
            entries.append(
                {
                    "name": child.name,
                    "path": rel,
                    "type": "dir" if child.is_dir() else "file",
                    "size": child.stat().st_size if child.is_file() else None,
                    "modified": datetime.fromtimestamp(child.stat().st_mtime, UTC).isoformat(),
                }
            )
        entries.sort(key=lambda e: (e["type"] != "dir", e["name"]))
        return {"path": path, "type": "dir", "entries": entries}

    def file_path(self, workspace_id: str, path: str) -> Path:
        """下载用：校验并返回绝对路径。"""
        ws_dir = self._ws_dir(workspace_id)
        fpath = _safe_join(ws_dir, path)
        if ".dawei" in fpath.relative_to(ws_dir).parts:
            raise DeepResearchError(f"Access denied: {path}", status_code=403)
        if not fpath.is_file():
            raise DeepResearchError(f"File not found: {path}", status_code=404)
        return fpath

    def zip_bytes(self, workspace_id: str) -> bytes:
        """整个工作区打包（download-all，不含 .dawei 内部状态）。"""
        ws_dir = self._ws_dir(workspace_id)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(ws_dir.rglob("*")):
                if not f.is_file():
                    continue
                rel_parts = f.relative_to(ws_dir).parts
                if ".dawei" in rel_parts or "audit_log.jsonl" == f.name:
                    continue
                zf.write(f, f.relative_to(ws_dir))
        return buf.getvalue()

    # --------------------------------------------------------
    # 报告分享（PRD §10 #5）
    # --------------------------------------------------------

    def _shares_index_path(self) -> Path:
        return self.storage_root / ".shares.json"

    def _load_shares(self) -> dict[str, str]:
        p = self._shares_index_path()
        if not p.is_file():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("tokens", {})
        except (json.JSONDecodeError, OSError):
            return {}

    def create_share(self, workspace_id: str, actor: str = "user") -> dict[str, Any]:
        """生成只读分享 token（仅 completed 工作区；公开端点按 token 反查报告）。"""
        ws_dir = self._ws_dir(workspace_id)
        meta = self._load_meta(ws_dir)
        if meta["status"] != "completed":
            raise DeepResearchError("Share requires a completed workspace", status_code=409)
        token = secrets.token_hex(8)
        meta["share"] = {"token": token, "created_at": _now_iso()}
        self._save_meta(ws_dir, meta)
        self._append_audit(ws_dir, "report.shared", {"token": token[:6] + "…"}, actor)
        shares = self._load_shares()
        shares[token] = workspace_id
        self._shares_index_path().write_text(
            json.dumps({"tokens": shares}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {"token": token, "workspace_id": workspace_id, "created_at": meta["share"]["created_at"]}

    def get_shared(self, token: str) -> dict[str, Any]:
        """按 token 返回只读报告载荷（不含 workspace 内部路径）。"""
        wid = self._load_shares().get(token)
        if not wid:
            raise DeepResearchError("Share token not found", status_code=404)
        ws_dir = self._ws_dir(wid)
        meta = self._load_meta(ws_dir)
        if not meta or meta.get("share", {}).get("token") != token:
            raise DeepResearchError("Share token not found", status_code=404)
        report_md = ""
        if self.spec.final_report_md:
            p = ws_dir / self.spec.final_report_md
            if p.is_file():
                report_md = p.read_text(encoding="utf-8")
        html_path = ws_dir / self.spec.report_html if self.spec.report_html else None
        report_html = html_path.read_text(encoding="utf-8") if html_path and html_path.is_file() else md_to_html(report_md, meta.get("topic", self.spec.name))
        return {
            "pipeline": {"slug": self.spec.slug, "name": self.spec.name, "team": self.spec.team},
            "workspace_id": wid,
            "topic": meta.get("topic"),
            "template_name": meta.get("template_name"),
            "status": meta.get("status"),
            "created_at": meta.get("created_at"),
            "updated_at": meta.get("updated_at"),
            "shared_at": meta.get("share", {}).get("created_at"),
            "metrics": meta.get("metrics"),
            "report_md": report_md,
            "report_html": report_html,
        }


# ============================================================
# 通用真实执行器
# ============================================================


class ResearchExecutor:
    """逐 stage 真实执行调研流水线（LLM Agent 驱动），对任意 PipelineSpec 通用。

    参考 EvolutionCycleManager（dawei/evolution/evolution_manager.py）的成熟模式:
    - 后台 asyncio 顺序执行 pending stage（HTTP 立即返回，前端轮询 workspace 状态）
    - 每个 stage 切换 workspace mode → 系统提示词注入该 mode 的契约
    - 通过 agent_execution_service 统一执行（与 UI 聊天/定时任务同一入口），
      阶段消息全部持久化进调研会话 → /app-ui/workspace/{id}/task/{conversation_id} 可见
    - stage 失败指数退避重试，最终失败 → stage/workspace 标记 failed，可 retry
    """

    MAX_STAGE_RETRIES = 2
    STAGE_TIMEOUT_SECONDS = 1800  # 单 stage 30 分钟上限

    def __init__(self, service: DeepResearchServiceBase):
        self._service = service
        self._running: set[str] = set()  # 内存级互斥：同一工作区不并发执行

    # --------------------------------------------------------
    # 启动入口
    # --------------------------------------------------------

    def launch(self, workspace_id: str) -> bool:
        """启动后台执行。

        - 服务器（async 上下文）: asyncio.create_task 立即返回
        - 同步调用方（如单测）: asyncio.run 内联跑完
        Returns: False 表示已有执行中的任务（拒绝并发）
        """
        if workspace_id in self._running:
            return False
        self._running.add(workspace_id)
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                loop.create_task(self._run_locked(workspace_id), name=f"deep-research-{workspace_id}")
            else:
                asyncio.run(self._run_locked(workspace_id))
            return True
        except Exception:
            self._running.discard(workspace_id)
            raise

    async def _run_locked(self, workspace_id: str) -> None:
        try:
            await self.run(workspace_id)
        except Exception as e:
            logger.exception("[DEEP-RESEARCH-EXEC] pipeline %s crashed: %s", workspace_id, e)
        finally:
            self._running.discard(workspace_id)

    # --------------------------------------------------------
    # 主循环
    # --------------------------------------------------------

    async def run(self, workspace_id: str) -> None:
        """顺序执行 pending stage，在未通过的闸门前停止；stage 失败 → failed。"""
        service = self._service
        spec = service.spec
        ws_dir = service.storage_root / workspace_id
        if not ws_dir.is_dir():
            logger.error("[DEEP-RESEARCH-EXEC] workspace missing: %s", workspace_id)
            return
        meta = service._load_meta(ws_dir)
        if not meta or meta.get("status") != "running":
            return  # 只有 running 状态才继续推进（paused/failed/needs_manual 均停）

        user_workspace = None  # 惰性创建，跨 stage 复用
        try:
            for stage in meta["stages"]:
                if stage["status"] != "pending":
                    continue
                # 闸门检查：未通过 → 停在闸门前（等待人工决策后重新 launch）
                gate_id = spec.gate_after_stage.get(stage["id"])
                if gate_id and service._gate(meta, gate_id)["status"] != "passed":
                    service._save_meta(ws_dir, meta)
                    return

                ok = False
                for attempt in range(1, self.MAX_STAGE_RETRIES + 1):
                    stage["status"] = "running"
                    stage["started_at"] = _now_iso()
                    service._save_meta(ws_dir, meta)
                    try:
                        if user_workspace is None:
                            user_workspace = await self._open_workspace(ws_dir)
                        tokens = await self._execute_stage(ws_dir, meta, stage, user_workspace)
                        service._finalize_stage(ws_dir, meta, stage, tokens)
                        service._save_meta(ws_dir, meta)
                        ok = True
                        break
                    except Exception as e:
                        logger.warning(
                            "[DEEP-RESEARCH-EXEC] stage %s attempt %d/%d failed: %s",
                            stage["id"], attempt, self.MAX_STAGE_RETRIES, e,
                        )
                        if attempt < self.MAX_STAGE_RETRIES:
                            await asyncio.sleep(2 ** (attempt - 1))
                        else:
                            self._mark_stage_failed(ws_dir, meta, stage, e)
                            return
                if not ok:
                    return

            meta["status"] = "completed"
            service._save_meta(ws_dir, meta)
            service._append_audit(ws_dir, "pipeline.completed", {"metrics": meta["metrics"]}, actor="agent")
        except Exception as e:
            meta["status"] = "failed"
            meta["error"] = str(e)[:500]
            service._save_meta(ws_dir, meta)
            service._append_audit(ws_dir, "pipeline.failed", {"error": str(e)[:500]}, actor="agent")

    def _mark_stage_failed(self, ws_dir: Path, meta: dict[str, Any], stage: dict[str, Any], err: Exception) -> None:
        stage["status"] = "failed"
        stage["error"] = str(err)[:500]
        meta["status"] = "failed"
        self._service._save_meta(ws_dir, meta)
        self._service._append_audit(
            ws_dir, "stage.failed", {"stage": stage["id"], "error": str(err)[:500]}, actor="agent"
        )
        logger.error(
            "[DEEP-RESEARCH-EXEC] stage %s failed after %d attempts", stage["id"], self.MAX_STAGE_RETRIES
        )

    # --------------------------------------------------------
    # Agent 执行
    # --------------------------------------------------------

    async def _open_workspace(self, ws_dir: Path):
        """在调研工作区目录上构建 UserWorkspace（初始化一次，跨 stage 复用）。"""
        from dawei.workspace.user_workspace import UserWorkspace

        uw = UserWorkspace(str(ws_dir.resolve()))
        if not uw.is_initialized():
            await uw.initialize()
        return uw

    async def _execute_stage(
        self, ws_dir: Path, meta: dict[str, Any], stage: dict[str, Any], user_workspace
    ) -> int:
        """执行单个 stage：切 mode → 构建提示词 → agent_execution_service 统一执行 → 产物校验。

        阶段消息（用户提示词 + assistant 总结）持久化进调研会话（meta.conversation_id），
        前端 /app-ui/workspace/{id}/task/{conversation_id} 与消息 API 均可查看。

        Returns: token 估算值（(prompt+output)/4，与 dry-run 口径一致供指标累计）。
        Raises: 产物缺失/超时/Agent 异常 → 由调用方重试。
        """
        spec = self._service.spec
        stage_dir = ws_dir / "output" / stage["phase"] / stage["id"]
        stage_dir.mkdir(parents=True, exist_ok=True)

        # 旧工作区（Task-as-Workspace 之前创建）无会话 → 首次执行时补建
        conversation_id = meta.get("conversation_id")
        if not conversation_id:
            conversation_id = await self._service._create_research_conversation(ws_dir, meta)
            meta["conversation_id"] = conversation_id
            self._service._save_meta(ws_dir, meta)

        prompt = self._build_stage_prompt(ws_dir, meta, stage)

        from dawei.agentic.agent_execution_service import agent_execution_service

        result = await asyncio.wait_for(
            agent_execution_service.execute_agent_task(
                workspace=user_workspace,
                message=prompt,
                session_id=conversation_id,
                task_id=f"{meta['workspace_id']}:{stage['id']}",
                task_type="user",
                mode=stage["mode"],  # mode 决定系统提示词（stage 契约）与工具组，服务内落到 workspace.mode
            ),
            timeout=self.STAGE_TIMEOUT_SECONDS,
        )
        output = (result or {}).get("final_output") or ""
        if not output:
            output = f"[{stage['id']}] {stage['title']} completed（agent 无文本总结，产物见文件）"
        (stage_dir / "stage_output.md").write_text(output, encoding="utf-8")

        # FAST FAIL：契约产物必须落盘，缺失即视为 stage 失败
        missing = [
            rel
            for rel in spec.stage_artifacts.get(stage["id"], ())
            if not (stage_dir / rel).is_file() or (stage_dir / rel).stat().st_size == 0
        ]
        if missing:
            raise RuntimeError(f"stage artifacts missing/empty after agent run: {missing}")

        return (len(prompt) + len(output)) // 4  # token 估算

    # --------------------------------------------------------
    # 提示词
    # --------------------------------------------------------

    def _build_stage_prompt(self, ws_dir: Path, meta: dict[str, Any], stage: dict[str, Any]) -> str:
        """构建 stage 用户提示词（契约细节由 mode customInstructions 承载，此处只给上下文）。"""
        spec = self._service.spec
        stage_ids = spec.stage_ids

        # 上游产物（磁盘上实际存在的）
        upstream: list[str] = []
        idx = stage_ids.index(stage["id"])
        for prev in spec.stages[:idx]:
            for rel in spec.stage_artifacts.get(prev.id, ()):
                p = ws_dir / "output" / prev.phase / prev.id / rel
                if p.is_file():
                    upstream.append(str(p.relative_to(ws_dir)))

        stage_rel = f"output/{stage['phase']}/{stage['id']}"
        expected = spec.stage_artifacts.get(stage["id"], ())
        expected_lines = "\n".join(f"- `{stage_rel}/{rel}`" for rel in expected) or "-（无强制契约文件）"
        upstream_lines = "\n".join(f"- `{u}`" for u in upstream) or "-（无，本阶段为首个 stage）"

        return f"""【{spec.prompt_label} · {stage['id']} {stage['title']}】

调研主题：{meta.get('topic', '')}
负责 mode：{stage['mode']}（系统提示词已注入该 mode 的阶段契约，严格遵守）

工作区根目录：{ws_dir.resolve()}

## 1. 必读输入
- `{spec.input_doc_path}` — 需求文档（唯一权威输入，含成功标准与约定）
- `AGENT_INSTRUCTIONS.md` — 工作指令
- `input/task_parameters.json` — 用户提交的调研参数（维度/范围/成功标准）

## 2. 上游产物（按需读取）
{upstream_lines}

## 3. 本阶段必须产出的文件
{expected_lines}

## 4. 执行要求
- 检索一律使用 Web Search / 浏览器能力，禁止使用检索类 MCP
- 遵守需求文档约定：来源 URL 可追溯、关键数据标注采集日期、覆盖中国与海外市场、缺失字段留空绝不编造
- JSON/YAML 产物必须可解析、非空；每写完一个文件自查格式
- 完成后对话中仅回复 ≤200 字执行总结（产物一律写文件，不要贴正文）
"""


# ============================================================
# 流水线注册表
# ============================================================

PIPELINE_REGISTRY: dict[str, DeepResearchServiceBase] = {}


def register_pipeline(route: str, service: DeepResearchServiceBase) -> None:
    """注册流水线（route = generic URL 段，如 "product" / "industry"）。"""
    PIPELINE_REGISTRY[route] = service


def get_pipeline(route: str) -> DeepResearchServiceBase:
    service = PIPELINE_REGISTRY.get(route)
    if service is None:
        raise DeepResearchError(f"Unknown pipeline: {route}", status_code=404)
    return service


def list_pipelines() -> list[dict[str, Any]]:
    """已注册流水线清单（generic router / 前端展示）。"""
    result = []
    for route, svc in PIPELINE_REGISTRY.items():
        result.append(
            {
                "route": route,
                "slug": svc.spec.slug,
                "name": svc.spec.name,
                "team": svc.spec.team,
                "mode_team": svc.spec.mode_team,
                "description": svc.spec.description,
                "stages": len(svc.spec.stages),
                "gates": svc.spec.gate_ids,
            }
        )
    return result


def find_shared(token: str) -> dict[str, Any]:
    """跨流水线按 token 反查只读报告（公开分享端点）。"""
    for route in PIPELINE_REGISTRY:
        try:
            return PIPELINE_REGISTRY[route].get_shared(token)
        except DeepResearchError:
            continue
    raise DeepResearchError("Share token not found", status_code=404)
