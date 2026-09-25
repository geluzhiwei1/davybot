# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""社媒编辑器 Agent 工具组(设计:高级编辑和资产管理.md A.5)。

创作工场「智能体模式」的 5 个工具:读稿(拉不推)/ 规则检查 / 热点查询 /
改写提案(写会话不写稿件——人是合并者)/ 成稿校验。

鉴权:控制面凭当前用户 JWT(local_context 透明注入,绝不作为工具参数进 LLM 上下文),
权限=当前用户(AM1 角色闸门在服务端生效,403 会以人话返回)。
租户/稿件:session_context(ContextVar,前端 data.social_context 绑定)。
"""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from pydantic import BaseModel, Field

from dawei.core import local_context
from dawei.core.decorators import safe_tool_operation
from dawei_biz.bridges.social import bridge, session_context
from dawei.tools.custom_base_tool import CustomBaseTool


def _base_hash(text: str) -> str:
    """提案冲突检测锚点:当前变体文本 hash(应用时前端比对,稿件被改过则三选)。"""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:10]


def _bridge_error(e: Exception) -> str:
    """把桥接异常翻译成用户/agent 都能懂的人话(可用性域 4.2/11.3)。"""
    import httpx

    status = getattr(e, "response", None) and getattr(e.response, "status_code", None)  # type: ignore[attr-defined]
    if status == 401:
        return "Error: 登录已过期,请重新登录后再试(控制面拒绝了当前凭据)"
    if status == 403:
        return "Error: 当前角色无权执行该操作(需品牌主理人或租户管理员)"
    if status == 404:
        return "Error: 稿件不存在或已被删除"
    if isinstance(e, httpx.HTTPError):
        return "Error: 控制面暂不可达,请稍后重试(云端服务不可达,不影响本地编辑)"
    return f"Error: {e}"


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


# ── 生图候选注册表(A-M2):id → data URL,进程生命周期 ──
# 工具只回 id(避免 base64 灌爆 LLM 上下文),前端经
# GET /api/social/images/{id} 取图渲染候选卡。
IMAGE_REGISTRY: dict[str, str] = {}
IMAGE_REGISTRY_CAP = 40


def register_image(data_url: str) -> str:
    image_id = uuid4().hex[:12]
    IMAGE_REGISTRY[image_id] = data_url
    while len(IMAGE_REGISTRY) > IMAGE_REGISTRY_CAP:
        IMAGE_REGISTRY.pop(next(iter(IMAGE_REGISTRY)))
    return image_id


class _CtxMissingError(Exception):
    """会话未绑定社媒上下文(非智能体模式会话误调工具)。"""


def _require_ctx(*, need_content: bool = True) -> tuple[str, str, str]:
    ctx = session_context.get_social_context()
    if ctx is None or (need_content and not ctx.content_id):
        raise _CtxMissingError(
            "当前会话未关联稿件——请在创作工场「智能体」面板中发起会话,或让用户先打开一篇稿件"
        )
    tenant_id = ctx.tenant_id or "default"
    return ctx.content_id, tenant_id, local_context.get_auth_token() or ""


# ── 1. 读稿(上下文用拉的,不用推的) ─────────────────────────

class SocialReadDraftInput(BaseModel):
    content_id: str = Field(
        "", description="稿件 ID;留空 = 当前会话关联的稿件(推荐)"
    )


class SocialReadDraftTool(CustomBaseTool):
    name: str = "social_read_draft"
    description: str = (
        "读取当前社媒稿件的最新状态(标题/状态/目标平台/各平台正文与字数/合规摘要)。"
        "改稿前必须先调用本工具获取最新文本与其 base_hash(提案时需回传防冲突)。"
        "不接收用户粘贴的稿件全文作为替代——以本工具返回为准。"
    )
    args_schema: type[BaseModel] = SocialReadDraftInput

    @safe_tool_operation("social_read_draft", fallback_value="Error: 读取稿件失败")
    def _run(self, content_id: str = "") -> str:
        try:
            cid, tenant_id, token = _require_ctx()
            cid = content_id or cid
            c = bridge.get_content(cid, tenant_id=tenant_id, auth_token=token or None)
        except _CtxMissingError as e:
            return f"Error: {e}"
        except Exception as e:  # noqa: BLE001
            return _bridge_error(e)

        body = c.get("body") or {}
        variants = (body.get("variants") or {})
        out_variants: dict[str, dict] = {}
        for platform, v in variants.items():
            text = str((v or {}).get("text") or "")
            out_variants[platform] = {
                "chars": len(text),
                "base_hash": _base_hash(text),
                "text": text,
            }
        compliance = c.get("compliance_report") or {}
        return _dump({
            "content_id": c.get("id", cid),
            "title": c.get("title", ""),
            "type": c.get("type", ""),
            "status": c.get("status", ""),
            "brand_id": c.get("brand_id", ""),
            "target_platforms": c.get("target_platforms") or [],
            "variants": out_variants,
            "compliance_passed": compliance.get("passed"),
            "violations_count": len(compliance.get("violations") or []),
        })


# ── 2. 规则检查 ─────────────────────────────────────────────

class SocialRuleCheckInput(BaseModel):
    text: str = Field(..., description="待检查的正文文本")


class SocialRuleCheckTool(CustomBaseTool):
    name: str = "social_rule_check"
    description: str = (
        "对文本执行三层合规规则检查(通用法规/行业包/品牌规则),返回命中条文与替代写法建议。"
        "改写敏感内容(极限词/医疗金融表述)前后都应调用。"
    )
    args_schema: type[BaseModel] = SocialRuleCheckInput

    @safe_tool_operation("social_rule_check", fallback_value="Error: 规则检查失败")
    def _run(self, text: str) -> str:
        try:
            _, tenant_id, token = _require_ctx(need_content=False)
            r = bridge.precheck_rules(text, tenant_id=tenant_id, auth_token=token or None)
        except _CtxMissingError as e:
            return f"Error: {e}"
        except Exception as e:  # noqa: BLE001
            return _bridge_error(e)
        return _dump(r)


# ── 3. 热点查询 ─────────────────────────────────────────────

class SocialLookupTrendingInput(BaseModel):
    platform: str = Field("", description="平台过滤(如 weibo/zhihu);留空 = 全部")
    top: int = Field(10, description="返回条数上限(1-30)")


class SocialLookupTrendingTool(CustomBaseTool):
    name: str = "social_lookup_trending"
    description: str = (
        "查询租户当日采集的热点条目(标题/分类/热度/链接),用于写跟热点的稿或给选题依据。"
    )
    args_schema: type[BaseModel] = SocialLookupTrendingInput

    @safe_tool_operation("social_lookup_trending", fallback_value="Error: 热点查询失败")
    def _run(self, platform: str = "", top: int = 10) -> str:
        try:
            _, tenant_id, token = _require_ctx(need_content=False)
            items = bridge.fetch_trending(tenant_id=tenant_id, auth_token=token or None)
        except _CtxMissingError as e:
            return f"Error: {e}"
        except Exception as e:  # noqa: BLE001
            return _bridge_error(e)
        if platform:
            items = [i for i in items if i.get("platform") == platform]
        items = items[: max(1, min(int(top or 10), 30))]
        return _dump({
            "count": len(items),
            "items": [
                {
                    "title": i.get("title", ""),
                    "platform": i.get("platform", ""),
                    "category": i.get("category"),
                    "url": i.get("url"),
                    "captured_at": i.get("captured_at"),
                }
                for i in items
            ],
        })


# ── 4. 改写提案(写会话不写稿件) ───────────────────────────

class SocialProposeEditInput(BaseModel):
    platform: str = Field(..., description="目标平台 key(如 xiaohongshu / wechat_mp)")
    replacement_text: str = Field(..., description="该平台的完整替换正文(markdown 源文本)")
    rationale: str = Field("", description="一句话说明改了什么、为什么(展示给用户)")
    base_hash: str = Field(
        "", description="social_read_draft 返回的该平台 base_hash(应用时校验稿件未被手改)"
    )


class SocialProposeEditTool(CustomBaseTool):
    name: str = "social_propose_edit"
    description: str = (
        "提交一份改写提案:不会直接修改稿件——用户在界面上点「应用」才生效(人是合并者)。"
        "replacement_text 必须是完整正文(整段替换,非补丁);base_hash 回传读稿时的值。"
    )
    args_schema: type[BaseModel] = SocialProposeEditInput

    @safe_tool_operation("social_propose_edit", fallback_value="Error: 生成提案失败")
    def _run(self, platform: str, replacement_text: str, rationale: str = "", base_hash: str = "") -> str:
        platform = (platform or "").strip()
        replacement_text = (replacement_text or "").strip()
        if not platform:
            return "Error: platform 不能为空(目标平台 key)"
        if not replacement_text:
            return "Error: replacement_text 不能为空(完整替换正文)"
        return _dump({
            "proposal_id": uuid4().hex[:8],
            "platform": platform,
            "chars": len(replacement_text),
            "base_hash": base_hash or _base_hash(replacement_text),
            "rationale": rationale,
            "status": "proposed",
            "note": "提案已生成,等待用户在界面应用或忽略;用户忽略时请勿重复提交同一提案",
        })


# ── 5. 成稿校验(落盘前的门) ───────────────────────────────

class SocialValidateArtifactInput(BaseModel):
    artifact_json: str = Field(
        ..., description='成稿 JSON 字符串:{"title","type","variants":{platform:{"text","aigc_label"}}}'
    )


class SocialValidateArtifactTool(CustomBaseTool):
    name: str = "social_validate_artifact"
    description: str = (
        "校验多平台成稿是否符合落盘契约(标题/各平台正文非空/字数),返回逐项错误。"
        "最终输出成稿时,先本校验,再把 JSON 原样放进回复的 ```json 代码块给用户点「创建」。"
    )
    args_schema: type[BaseModel] = SocialValidateArtifactInput

    @safe_tool_operation("social_validate_artifact", fallback_value="Error: 成稿校验失败")
    def _run(self, artifact_json: str) -> str:
        from dawei_biz.bridges.social.artifact_schema import ArtifactSchemaError, to_content_payload

        try:
            structured = json.loads(artifact_json)
        except json.JSONDecodeError as e:
            return _dump({"ok": False, "errors": [f"JSON 解析失败: {e}"]})
        try:
            payload = to_content_payload(structured)
        except ArtifactSchemaError as e:
            return _dump({"ok": False, "errors": [str(e)]})
        variants = (payload.get("body") or {}).get("variants") or {}
        return _dump({
            "ok": True,
            "title": payload.get("title", ""),
            "platforms": {p: len((v or {}).get("text") or "") for p, v in variants.items()},
        })


# ── 6. 配图生成(A-M2:候选进界面,用户挑选插入) ───────────

class SocialGenerateImagesInput(BaseModel):
    prompt: str = Field(..., description="画面描述(中文即可)")
    count: int = Field(2, description="生成张数(1-4)")
    style: str = Field("", description="风格:实拍感/插画/3D/扁平/国潮")
    ratio: str = Field("", description="比例:3:4 / 1:1 / 16:9;留空随平台")


class SocialGenerateImagesTool(CustomBaseTool):
    name: str = "social_generate_images"
    description: str = (
        "为当前稿件生成配图候选(1-4 张)。生成的图片进入界面候选区,"
        "由用户挑选后插入稿件——不会自动入稿。需要配图或用户要求配图时调用。"
    )
    args_schema: type[BaseModel] = SocialGenerateImagesInput

    @safe_tool_operation("social_generate_images", fallback_value="Error: 生成配图失败")
    def _run(self, prompt: str, count: int = 2, style: str = "", ratio: str = "") -> str:
        import asyncio

        from dawei_biz.bridges.social import service as social_service

        prompt = (prompt or "").strip()
        if not prompt:
            return "Error: prompt 不能为空(画面描述)"
        n = max(1, min(int(count or 2), 4))
        try:
            images = asyncio.run(social_service.default_image_generate(
                prompt, count=n, style=style or "", ratio=ratio or "",
                auth_token=local_context.get_auth_token() or "",
            ))
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "No LLM config" in msg or "通道" in msg:
                return ("Error: 生图通道不可用(未配置模型或在 llm-pricing 管理页配置;"
                        "正文编辑不受影响)")
            return f"Error: 生成配图失败({msg[:120]})"
        ids = [register_image(u) for u in images if u]
        if not ids:
            return "Error: 本次未生成任何图片(通道返回空,可重试或换模型)"
        return _dump({
            "ok": True,
            "count": len(ids),
            "image_ids": ids,
            "note": "候选已生成,等待用户在界面挑选插入;用户未选择时不要重复生成同一提示词",
        })


SOCIAL_DRAFT_TOOLS = [
    SocialReadDraftTool,
    SocialRuleCheckTool,
    SocialLookupTrendingTool,
    SocialProposeEditTool,
    SocialValidateArtifactTool,
    SocialGenerateImagesTool,
]
SOCIAL_DRAFT_TOOL_NAMES: set[str] = {t().name for t in SOCIAL_DRAFT_TOOLS}  # module-level convenience (tests)

__all__ = ["SOCIAL_DRAFT_TOOLS", "SOCIAL_DRAFT_TOOL_NAMES", "IMAGE_REGISTRY"] + [c.__name__ for c in SOCIAL_DRAFT_TOOLS]
