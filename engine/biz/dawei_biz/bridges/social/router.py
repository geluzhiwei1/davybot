"""社媒 sidecar 路由 —— 桌面端 Agent 能力的 HTTP 面。

POST /api/social/generate        一源多稿(进程内 soc-content-drafter)
POST /api/social/artifact        会话产出落盘 → 推送 social-control
POST /api/social/precheck        文本合规预检(控制面规则引擎代理)
POST /api/social/image-generate  AI 生图(N 张 data URL,studio-images-ui §3)
POST /api/social/image-prompt    正文 → 生图提示词(「从正文提取灵感」)
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from dawei_biz.bridges.social import bridge, duty_orchestrator, service
from dawei_biz.bridges.social.artifact_schema import ArtifactSchemaError, to_content_payload

router = APIRouter(prefix="/api/social", tags=["social"])


class GenerateRequest(BaseModel):
    source_text: str
    platforms: list[str] = ["xiaohongshu", "wechat_mp", "weibo"]
    provider: str = ""       # llmApi 服务商名(空=引擎当前配置);文字生成模型选择
    brand_voice: str = ""    # 品牌 Voice(治理页 voice_config.voice;注入系统提示词)


class ArtifactRequest(BaseModel):
    structured: dict[str, Any]
    brand_id: str = "default"
    tenant_id: str = "default"


class PrecheckRequest(BaseModel):
    text: str
    tenant_id: str = "default"


class DutyRequest(BaseModel):
    tenant_id: str = "default"
    brand_id: str = "default"
    brand_profile: dict[str, Any] = {}
    draft_count: int = 0  # >0:选题后自动成稿 N 篇入内容库(L3 自动成稿+人工批准)


class BrowserTrackStartRequest(BaseModel):
    tenant_id: str = "default"
    platforms: list[str] = ["xiaohongshu"]
    poll_seconds: float = 15.0
    auth_token: str = ""  # 控制面 Bearer(桌面登录用户 JWT);空则回落 SOCIAL_AUTH_TOKEN/SOCIAL_API_KEY
    api_key: str = ""     # 控制面服务账号(优先于 auth_token)
    collect: bool = True  # 联动启动热点采集轨(claim→连接器抓取→回报)
    auto_confirm: bool = False  # True:本地不再二次人工确认(云端审批为唯一关卡;light-app 用)


class PlatformRequest(BaseModel):
    platform: str


class ConfirmRequest(BaseModel):
    approved: bool = True


class DutyScheduleRequest(BaseModel):
    brand_id: str = "default"
    interval_minutes: float = 60.0
    enabled: bool = True
    tenant_id: str = "default"
    draft_count: int = 0  # >0:每轮值班选题后自动成稿 N 篇入内容库(L3,与 /duty 同语义)


class ImageGenerateRequest(BaseModel):
    prompt: str
    count: int = 4        # 候选张数,夹取 [1,4]
    style: str = ""       # 风格 chip(实拍感/插画/3D…)追加到提示词
    ratio: str = ""       # 构图比例(3:4/1:1/16:9)文字指令
    reference_b64: str = ""  # 图生图参考(data URL/base64;空=纯文生图)
    provider: str = ""    # llmApi 服务商名(空=引擎当前配置)


class ImagePromptRequest(BaseModel):
    text: str
    platform: str = "xiaohongshu"
    provider: str = ""    # 同上


@router.post("/generate")
def generate(req: GenerateRequest, authorization: str = Header(default="")) -> dict:
    """一源多稿;provider 支持网关模型 id(llm-pricing 目录)或本地服务商名。
    Authorization Bearer(桌面登录态)透传供网关模型鉴权(用户积分)。"""
    auth_token = authorization.removeprefix("Bearer ").strip() or None
    try:
        # 文字生成按名解析(本地服务商→网关模型注册→当前);直连不动全局 current
        llm_call = lambda s, u: service.default_text_call(s, u, req.provider, auth_token or "")  # noqa: E731
        structured = service.generate_variants(
            req.source_text, req.platforms, llm_call=llm_call, brand_voice=req.brand_voice,
        )
        return {"ok": True, "structured": structured}
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:  # LLM 通道故障(密钥/网络)→ 503 降级提示
        raise HTTPException(503, f"LLM 通道不可用: {e}") from e


@router.post("/artifact")
def artifact(req: ArtifactRequest) -> dict:
    """落盘协议:结构化产出 → 内容工件 → 控制面。"""
    try:
        payload = to_content_payload(req.structured, brand_id=req.brand_id)
    except ArtifactSchemaError as e:
        raise HTTPException(422, f"落盘协议校验失败: {e}") from e
    try:
        content = bridge.push_artifact(payload, tenant_id=req.tenant_id)
    except Exception as e:
        raise HTTPException(502, f"控制面不可达: {e}") from e
    return {"ok": True, "content": content}


@router.post("/precheck")
def precheck(req: PrecheckRequest) -> dict:
    try:
        return bridge.precheck_rules(req.text, tenant_id=req.tenant_id)
    except Exception as e:
        raise HTTPException(502, f"控制面不可达: {e}") from e


@router.post("/image-generate")
async def image_generate(
    req: ImageGenerateRequest, authorization: str = Header(default="")
) -> dict:
    """AI 生图:count 张候选(data URL);前端选中后经控制面 media 通道入库。
    provider 支持网关模型 id;Bearer 透传供网关鉴权。"""
    if not req.prompt.strip():
        raise HTTPException(422, "prompt 不能为空")
    n = max(1, min(req.count, 4))  # 候选张数夹取 [1,4]
    auth_token = authorization.removeprefix("Bearer ").strip() or None
    try:
        # 服务是协程:路由必须 async/await(同步路由会把协序列化成 500)
        images = await service.default_image_generate(
            req.prompt, count=n, style=req.style,
            ratio=req.ratio, reference_b64=req.reference_b64,
            provider=req.provider, auth_token=auth_token or "",
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:  # LLM 通道故障(密钥/模型不支持/网络)→ 503 降级提示
        raise HTTPException(503, f"生图通道不可用: {e}") from e
    return {"ok": True, "images": images}


@router.post("/image-prompt")
def image_prompt(req: ImagePromptRequest, authorization: str = Header(default="")) -> dict:
    """正文 → 生图提示词;provider 可为网关模型 id/服务商名,LLM 故障同 503 降级。"""
    auth_token = authorization.removeprefix("Bearer ").strip() or None
    try:
        prompt = service.build_image_prompt(
            req.text,
            llm_call=lambda s, u: service.default_image_prompt_call(
                s, u, req.provider, auth_token or ""),
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        raise HTTPException(503, f"LLM 通道不可用: {e}") from e
    return {"ok": True, "prompt": prompt}


__all__ = ["router"]


@router.post("/duty")
def duty(req: DutyRequest, authorization: str = Header(default="")) -> dict:
    """值班任务:拉热点 → soc-trend-spotter 评分 → 选题卡入库;draft_count>0 时续跑成稿(L3)。

    authorization:桌面 UI 透传的登录 JWT(Bearer),供 bridge 调 prod 控制面鉴权;
    缺省回落 SOCIAL_AUTH_TOKEN / SOCIAL_API_KEY 环境变量(见 bridge._headers)。
    """
    auth_token = authorization.removeprefix("Bearer ").strip() or None
    try:
        items = bridge.fetch_trending(tenant_id=req.tenant_id, auth_token=auth_token)
    except Exception as e:
        raise HTTPException(502, f"控制面不可达: {e}") from e
    try:
        ideas = duty_orchestrator.run_duty(
            items, req.brand_profile, llm_call=service.default_llm_call,
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        raise HTTPException(503, f"LLM 通道不可用: {e}") from e

    created = []
    for idea in ideas:
        try:
            created.append(bridge.post_idea(idea, brand_id=req.brand_id, tenant_id=req.tenant_id,
                                            auth_token=auth_token))
        except Exception:
            continue  # 单条失败不阻断批次

    drafts = 0
    if req.draft_count > 0 and ideas:
        try:
            out = duty_orchestrator.run_duty_pipeline(
                items, req.brand_profile, llm_call=service.default_llm_call,
                brand_id=req.brand_id, tenant_id=req.tenant_id,
                max_drafts=req.draft_count,
            )
            drafts = out["created_drafts"]
        except Exception:
            drafts = 0  # 成稿失败不影响选题结果(选题已入库)
    return {"ok": True, "analyzed": len(items), "created": len(created),
            "created_drafts": drafts, "ideas": created}


# ── 浏览器轨闭环 HTTP 面(PRD §11.2)────────────────────────
# 使用场景(重要):本组端点只服务本机"执行端" ——
#   1. 桌面端 dawei sidecar(前端 UI 调 /api/social/browser-track/*);
#   2. davy-light-app 壳经 inject.js 拦截同名前端请求转发到本地引擎。
# 端点无鉴权是 loopback 设计的前提;SaaS 公网部署(DAWEI_DEPLOYMENT_MODE=saas)
# 下挂出即裸奔 —— 故 start/login* 在 saas 模式 FAST FAIL(403),
# status/pending/confirm 等观测-处置端点保留(无副作用,且 captcha/confirm
# 由 HumanGate 内存态驱动,云引擎上无执行轨自然恒空)。
# 本机执行权互斥:TrackLock(DAWEI_HOME/browser-track.lock)防 sidecar 与壳双 claim。

_track_client: Any = None
_collect_client: Any = None


def _get_track_client() -> Any:
    global _track_client
    if _track_client is None:
        from dawei_biz.bridges.social.browser_track import BrowserTrackClient
        _track_client = BrowserTrackClient()
    return _track_client


def _reject_saas_executors() -> None:
    """SaaS 云引擎不执行浏览器轨:FAST FAIL(FAST FAIL 原则;云端只编排不执行)。"""
    from dawei.runtime import deployment_class  # 唯一合法 mode 读取点

    if deployment_class() == "saas":
        raise HTTPException(
            403, "SaaS 引擎不执行浏览器轨:社媒浏览器任务由本机执行端"
                 "(桌面 sidecar / light-app 壳)claim 执行,云端只负责编排下发")


@router.post("/browser-track/start")
async def browser_track_start(req: BrowserTrackStartRequest) -> dict:
    """启动浏览器轨轮询(claim → 执行 → 回报;人工确认默认开)。幂等。

    collect=True 时联动启动热点采集轨(TrendingCollectClient,独立循环;
    采集无人工关卡,平台取连接器 trending 能力面)。
    TrackLock:本机已有其他执行端(壳/另一 sidecar)持锁 → 409 FAST FAIL。
    """
    global _track_client, _collect_client
    _reject_saas_executors()
    from dawei_biz.bridges.social.browser_track import BrowserTrackClient, TrackLockHeldError, acquire_track_lock
    from dawei_biz.bridges.social.trending_track import TrendingCollectClient

    try:
        acquire_track_lock(tenant_id=req.tenant_id, platforms=req.platforms,
                           holder="dawei-engine")
    except TrackLockHeldError as e:
        raise HTTPException(409, f"本机浏览器轨执行权被占用: {e}(先停另一执行端或等待其退出)") from e

    if _track_client is None or _track_client.tenant_id != req.tenant_id \
            or _track_client.platforms != req.platforms \
            or _track_client.auto_confirm != req.auto_confirm:
        if _track_client is not None:
            await _track_client.stop()
        _track_client = BrowserTrackClient(
            tenant_id=req.tenant_id, platforms=req.platforms,
            poll_interval=max(5.0, req.poll_seconds),
            auth_token=req.auth_token, api_key=req.api_key,
            auto_confirm=req.auto_confirm,
        )
    started = _track_client.start()

    collect_started = False
    if req.collect:
        if _collect_client is None or _collect_client.tenant_id != req.tenant_id:
            if _collect_client is not None:
                await _collect_client.stop()
            _collect_client = TrendingCollectClient(
                tenant_id=req.tenant_id,
                poll_interval=max(15.0, req.poll_seconds * 4),
                auth_token=req.auth_token, api_key=req.api_key,
            )
        collect_started = _collect_client.start()
    elif _collect_client is not None:
        await _collect_client.stop()

    return {"ok": True, "started": started,
            "platforms": _track_client.platforms,
            "poll_seconds": _track_client.poll_interval,
            "collect_started": collect_started,
            "collect_platforms": _collect_client.platforms if _collect_client else []}


@router.post("/browser-track/stop")
async def browser_track_stop() -> dict:
    global _collect_client
    from dawei_biz.bridges.social.browser_track import release_track_lock

    stopped_any = False
    if _track_client is not None:
        await _track_client.stop()
        stopped_any = True
    if _collect_client is not None:
        await _collect_client.stop()
        stopped_any = True
    release_track_lock()
    return {"ok": True, "stopped": stopped_any}


@router.post("/browser-track/login")
def browser_track_login(req: PlatformRequest) -> dict:
    """打开平台登录窗口(headful Chrome 独立存活;扫码/密码由用户完成,登录态持久化到平台 profile)。"""
    _reject_saas_executors()
    from dawei_biz.bridges.social import login_helper

    try:
        port = login_helper.open_login(req.platform)
    except SystemExit as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:  # Chrome 缺失/启动失败
        raise HTTPException(500, f"登录窗口启动失败: {e}") from e
    return {"ok": True, "platform": req.platform, "cdp_port": port,
            "profile": login_helper.profile_dir(req.platform)}


@router.post("/browser-track/login/verify")
def browser_track_login_verify(req: PlatformRequest) -> dict:
    """校验平台登录态(走 recipe login_check;未开过登录窗口 → 422 引导)。"""
    _reject_saas_executors()
    from dawei_biz.bridges.social import login_helper

    try:
        logged_in = login_helper.verify_login(req.platform)
    except SystemExit as e:
        raise HTTPException(422, str(e)) from e
    return {"ok": True, "platform": req.platform, "logged_in": bool(logged_in)}


@router.get("/browser-track/status")
def browser_track_status() -> dict:
    """浏览器轨/采集轨运行状态(桌面 UI 与运维观测;含本机执行权持有者)。"""
    from dawei_biz.bridges.social.browser_track import read_track_lock

    lock = read_track_lock()
    lock_held_by_other = bool(lock and int(lock.get("pid") or 0) not in (0, os.getpid()))
    return {
        "publish": {
            "running": bool(_track_client and _track_client._running),
            "platforms": _track_client.platforms if _track_client else [],
            "tenant_id": _track_client.tenant_id if _track_client else "",
        },
        "collect": {
            "running": bool(_collect_client and _collect_client._running),
            "platforms": _collect_client.platforms if _collect_client else [],
            "tenant_id": _collect_client.tenant_id if _collect_client else "",
        },
        "track_lock": {"held_by": lock, "held_by_other_process": lock_held_by_other},
    }


@router.get("/browser-track/pending")
def browser_track_pending() -> dict:
    """人工关卡待办(确认/验证码)——桌面 UI 轮询此端点渲染处置界面。"""
    from dawei_biz.bridges.social.browser_track import shared_human_gate

    return {"items": shared_human_gate().pending()}


@router.get("/images/{image_id}")
def get_agent_image(image_id: str) -> dict:
    """A-M2:智能体轨生图候选取图(id 注册表;进程生命周期,未命中 404 可重新生成)。"""
    from dawei_biz.tools.social_draft_tools import IMAGE_REGISTRY

    url = IMAGE_REGISTRY.get(image_id)
    if not url:
        raise HTTPException(404, "候选图不存在或已过期——请让智能体重新生成")
    return {"id": image_id, "url": url}


@router.post("/duty-schedule")
async def duty_schedule(req: DutyScheduleRequest) -> dict:
    """值班 Agent 定时启停(§6.10:按品牌策略定时执行;桌面在线才跑)。"""
    from dawei_biz.bridges.social.duty_schedule import shared_scheduler

    try:
        cfg = shared_scheduler().set(
            req.brand_id, interval_minutes=req.interval_minutes,
            enabled=req.enabled, tenant_id=req.tenant_id, draft_count=req.draft_count)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"ok": True, **cfg}


@router.get("/duty-schedule/status")
def duty_schedule_status() -> dict:
    from dawei_biz.bridges.social.duty_schedule import shared_scheduler

    return {"items": shared_scheduler().status()}


@router.post("/browser-track/confirm/{request_id}")
def browser_track_confirm(request_id: str, req: ConfirmRequest) -> dict:
    """发布前人工确认放行/终止(§11.2 人工确认关卡)。"""
    from dawei_biz.bridges.social.browser_track import shared_human_gate

    ok = shared_human_gate().resolve(request_id, req.approved)
    if not ok:
        raise HTTPException(404, "无此待办(可能已超时移除)")
    return {"ok": True, "resolved": req.approved}


@router.post("/browser-track/captcha/{request_id}/solve")
def browser_track_captcha_solve(request_id: str) -> dict:
    """验证码已由用户在本机 Chrome 解决 → 放行对应任务。"""
    from dawei_biz.bridges.social.browser_track import shared_human_gate

    if not shared_human_gate().resolve(request_id, True):
        raise HTTPException(404, "无此待办(可能已超时移除)")
    return {"ok": True, "solved": True}
