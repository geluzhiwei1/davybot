"""一源多稿生成服务 —— soc-content-drafter 专家能力的进程内形态。

llm_call 可注入(单测打桩);生产经 LLMProvider(与 trending_agent 同模式)。
生图为 provider 无关实现:读当前工作区 LLM 配置,走 OpenAI 兼容
chat/completions + modalities(OpenRouter / Gemini 兼容层等支持),
SOCIAL_IMAGE_MODEL 可覆盖生图模型(与聊天模型分离)。
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
from collections.abc import Callable
from typing import Any

SYSTEM_PROMPT = """你是社媒内容多平台改写专家(soc-content-drafter)。
根据源内容为每个目标平台产出独立稿件。要求:
1. 忠于源内容事实,不编造数据与引语
2. 每个平台按其生态风格改写(小红书:亲切+标签;公众号:结构化长文;
   抖音:口播脚本+分镜提示;微博:短平快+话题;X/英文:简洁)
3. 不使用绝对化用语(国家级/最佳/第一)
4. AI 参与生成需在文末附"本文由 AI 辅助生成"标识
输出严格的 JSON 围栏:
```json
{"title": "...", "type": "text",
 "variants": {"<platform>": {"text": "...", "aigc_label": "本文由 AI 辅助生成"}}}
```"""

LlmCall = Callable[[str, str], str]  # (system, user) -> reply


def generate_variants(
    source_text: str,
    platforms: list[str],
    *,
    llm_call: LlmCall,
    brand_voice: str = "",
) -> dict[str, Any]:
    """源内容 × 平台列表 → 结构化多稿(Agent 产出,落盘协议输入)。

    brand_voice:品牌 Voice(治理页 voice_config.voice),非空时注入系统提示词。
    """
    if not source_text.strip():
        raise ValueError("source_text 不能为空")
    if not platforms:
        raise ValueError("platforms 至少一个")

    system = SYSTEM_PROMPT
    if brand_voice.strip():
        system += f"\n\n品牌 Voice(全文语气遵循此约定,优先级高于平台风格):\n{brand_voice.strip()}"

    user = f"目标平台:{', '.join(platforms)}\n\n源内容:\n{source_text.strip()}"
    reply = llm_call(system, user)
    structured = _extract_json(reply)
    if structured is None:
        raise ValueError("模型输出未包含 JSON 围栏,无法结构化")
    structured.setdefault("platforms", platforms)
    return structured


def _extract_json(reply: str) -> dict[str, Any] | None:
    m = re.search(r"```json\s*(\{.*?\})\s*```", reply, re.DOTALL)
    if not m:
        return None
    try:
        out = json.loads(m.group(1))
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        return None


def default_llm_call(system: str, user: str) -> str:
    """生产 LLM 通道:LLMProvider(工作区配置的模型与密钥)。

    complete() 是异步的;同步路由线程无运行循环,asyncio.run 直跑;
    若在事件循环线程内被调(异步路由),转投独立线程跑新循环。
    """
    from dawei.entity.lm_messages import SystemMessage, UserMessage

    async def _run() -> str:
        provider = await _provider()
        # pydantic v2 消息类:必须关键字构造(位置参数会炸 BaseModel.__init__)
        result = await provider.complete(
            [SystemMessage(content=system), UserMessage(content=user)]
        )
        if isinstance(result, dict):
            return result.get("content") or ""
        return getattr(result, "content", "") or str(result)

    return _run_sync(_run())


async def _provider():
    from dawei import get_dawei_home
    from dawei.llm_api import LLMProvider

    return LLMProvider(workspace_root=str(get_dawei_home()))


def _run_sync(coro):
    """在任意上下文(同步线程/事件循环线程)同步求值协程。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


# ── AI 配图(studio-images-ui.md §3)─────────────────────────

IMAGE_PROMPT_SYSTEM = """你是社媒配图提示词专家。把稿件正文提炼成一句可直接用于文生图模型的中文提示词:
1. 抓住正文的主体、场景、情绪与视觉重点,具体到可画(人物/物品/环境/光线/构图)
2. 不出现品牌名、二维码、水印、文字排版类要求(模型画不好文字)
3. 60 字以内,直接输出提示词本身,不要解释、引号或前缀"""


def build_image_prompt(text: str, *, llm_call: LlmCall) -> str:
    """正文 → 生图提示词(「从正文提取灵感」按钮)。"""
    if not text.strip():
        raise ValueError("text 不能为空")
    out = llm_call(IMAGE_PROMPT_SYSTEM, f"正文:\n{text.strip()}")
    out = out.strip().strip('"“”‘’').strip()
    out = out.splitlines()[0].strip() if out else ""
    if not out:
        raise ValueError("模型未返回提示词")
    return out


def compose_image_prompt(prompt: str, style: str = "", ratio: str = "") -> str:
    """画面描述 + 风格 + 比例 → 最终提示词(比例用文字构图指令,模型无关)。"""
    parts = [prompt.strip()]
    if style.strip():
        parts.append(style.strip())
    if ratio.strip():
        parts.append(f"构图比例 {ratio.strip()}")
    return ",".join(p for p in parts if p)


def _extract_image(data: dict[str, Any]) -> str | None:
    """多形态解析:OpenRouter message.images / images API data[].url / b64_json。"""
    try:
        imgs = data.get("choices", [{}])[0].get("message", {}).get("images", [])
        for im in imgs:
            url = (im or {}).get("image_url", {}).get("url", "")
            if url:
                return url
        for it in data.get("data", []) or []:
            if it.get("b64_json"):
                return f"data:image/png;base64,{it['b64_json']}"
            if it.get("url"):
                return it["url"]
    except (IndexError, AttributeError, TypeError):
        return None
    return None


async def _resolve_config(wrap, provider: str, auth_token: str = ""):
    """按名解析服务商配置;空名回落当前配置。

    解析顺序(支持 llm-pricing 网关模型目录,user-system 管理页配置):
    1. 本地服务商/已注册配置 get_config(名)
    2. 未命中且有名 → 按【网关模型】动态注册(set_gateway_token 透传用户登录态,
       _register_gateway_config_async 落 _configs[name=model_id])后取
    3. 回落当前配置
    全部失败 → RuntimeError(路由转 503 引导文案)。
    """
    name = provider.strip()
    cfg_wrap = wrap.get_config(name) if name else None
    if cfg_wrap is None and name:
        try:
            wrap.set_gateway_token(auth_token or None)
            if await wrap._register_gateway_config_async(name):
                cfg_wrap = wrap.get_config(name)
        except Exception:
            cfg_wrap = None
    if cfg_wrap is None:
        cfg_wrap = wrap.get_current_config()
    cfg = getattr(cfg_wrap, "config", None)
    if cfg is None or not cfg.api_key or not cfg.base_url:
        raise RuntimeError(
            f"未配置 LLM 通道(provider={provider or '当前'};"
            "网关模型由 llm-pricing 管理页配置,或在设置中配置自己的服务商。"
            "请确认已登录(网关模型走用户积分)后重试)"
        )
    return cfg


async def _chat_once(system: str, user: str, provider: str = "", auth_token: str = "") -> str:
    """直连 OpenAI 兼容 chat(非流式)——生图提示词提取用,不依赖全局 current 切换。"""
    import aiohttp

    wrap = await _provider()
    cfg = await _resolve_config(wrap, provider, auth_token)
    body = {
        "model": cfg.model_id,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(trust_env=True) as session, \
            session.post(f"{cfg.base_url.rstrip('/')}/chat/completions",
                         json=body,
                         headers={"Authorization": f"Bearer {cfg.api_key}",
                                  "Content-Type": "application/json"},
                         timeout=timeout) as resp:
        data = await resp.json(content_type=None)
        if resp.status != 200:
            detail = data.get("error", {}).get("message") if isinstance(data, dict) else ""
            raise RuntimeError(f"LLM 通道 HTTP {resp.status}: {detail or '模型或密钥不可用'}")
        try:
            return str(data["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"模型响应不可解析: {e}") from e


def default_image_prompt_call(system: str, user: str, provider: str = "",
                              auth_token: str = "") -> str:
    """「从正文提取灵感」生产通道:_chat_once 的同步包装(路由线程无循环)。"""
    return _run_sync(_chat_once(system, user, provider, auth_token))


def default_text_call(system: str, user: str, provider: str = "", auth_token: str = "") -> str:
    """文字生成(一源多稿)生产通道:网关模型/本地服务商同构解析 + 直连调用。"""
    return _run_sync(_chat_once(system, user, provider, auth_token))


async def default_image_generate(
    prompt: str,
    *,
    count: int = 1,
    style: str = "",
    ratio: str = "",
    reference_b64: str = "",
    provider: str = "",
    auth_token: str = "",
) -> list[str]:
    """生产生图通道:网关模型/本地服务商 → OpenAI 兼容 chat/completions + modalities。

    provider 可为 llmApi 服务商名或 llm-pricing 网关模型 id(按名注册后直连)。
    返回 data URL 列表(远程 URL 会取回转 base64,前端统一走 media 上传入库)。
    SOCIAL_IMAGE_MODEL 可覆盖模型;当前模型不支持图像输出时由上游报错文案引导。
    """
    import aiohttp

    wrap = await _provider()
    cfg = await _resolve_config(wrap, provider, auth_token)

    model = os.environ.get("SOCIAL_IMAGE_MODEL", "").strip() or cfg.model_id
    final_prompt = compose_image_prompt(prompt, style, ratio)
    content: Any = final_prompt
    if reference_b64.strip():
        content = [
            {"type": "text", "text": final_prompt},
            {"type": "image_url", "image_url": {"url": reference_b64.strip()}},
        ]
    body = {"model": model, "modalities": ["image", "text"],
            "messages": [{"role": "user", "content": content}]}
    headers = {"Authorization": f"Bearer {cfg.api_key}",
               "Content-Type": "application/json"}

    async def _one() -> str:
        timeout = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(trust_env=True) as session, \
                session.post(f"{cfg.base_url.rstrip('/')}/chat/completions",
                             json=body, headers=headers, timeout=timeout) as resp:
            data = await resp.json(content_type=None)
            if resp.status != 200:
                detail = data.get("error", {}).get("message") if isinstance(data, dict) else ""
                raise RuntimeError(f"生图通道 HTTP {resp.status}: {detail or '模型或密钥不可用'}")
            url = _extract_image(data)
            if not url:
                raise RuntimeError("模型未返回图像(当前模型可能不支持图像输出,可在设置中换用支持生图的模型)")
            if url.startswith("data:"):
                return url
            async with session.get(url) as r:  # 远程 URL → 统一转 data URL
                raw = await r.read()
                mime = r.headers.get("Content-Type", "image/png").split(";")[0]
                return f"data:{mime};base64,{base64.b64encode(raw).decode()}"

    n = max(1, min(int(count), 4))
    return list(await asyncio.gather(*[_one() for _ in range(n)]))


__all__ = [
    "generate_variants", "default_llm_call", "default_image_generate",
    "build_image_prompt", "compose_image_prompt", "SYSTEM_PROMPT", "IMAGE_PROMPT_SYSTEM",
]
