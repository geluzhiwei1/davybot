# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0 only

"""用户级 LLM Provider 配置 API

读写 {DAWEI_HOME}/configs/{user_id}/settings.json，提供用户全局 LLM Provider CRUD。
与 workspace 级 LLM API（/{workspace_id}/llm-providers）对应，支持用户级配置管理。
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dawei.api.auth import get_authenticated_user_id
from dawei.api._llm_test_errors import humanize_llm_test_error
from dawei import get_dawei_home

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/llm-providers", tags=["User LLM"])


# --- Models (与 workspaces/llm.py 保持一致) ---


class LLMProviderCreate(BaseModel):
    """创建 LLM Provider 的请求模型"""

    name: str = Field(..., description="Provider 配置名称")
    apiProvider: str = Field(..., description="API 提供商类型 (openai, ollama, deepseek)")
    openAiBaseUrl: str | None = Field(None, description="OpenAI 兼容 API 基础 URL")
    openAiApiKey: str | None = Field(None, description="OpenAI API 密钥")
    openAiModelId: str | None = Field(None, description="OpenAI 模型 ID")
    openAiLegacyFormat: bool | None = Field(False, description="使用旧版 OpenAI 格式")
    openAiHeaders: dict[str, str] | None = Field(None, description="自定义 HTTP Headers")
    openAiCustomModelInfo: dict[str, Any] | None = Field(None, description="自定义模型信息")
    diffEnabled: bool | None = Field(True, description="启用差异编辑")
    todoListEnabled: bool | None = Field(True, description="启用 TODO 列表")
    fuzzyMatchThreshold: int | None = Field(1, description="模糊匹配阈值")
    rateLimitSeconds: int | None = Field(0, description="速率限制秒数")
    consecutiveMistakeLimit: int | None = Field(3, description="连续错误限制")
    enableReasoningEffort: bool | None = Field(True, description="启用推理强度")
    toolChoice: str | None = Field(None, description="Tool Choice 设置 (auto, required, none)")
    temperature: float | None = Field(1.0, description="Temperature 参数 (0.0-2.0)")
    timeout: int | None = Field(600, description="HTTP 请求超时时间（秒）")
    maxRetries: int | None = Field(3, description="最大重试次数")
    retryDelay: float | None = Field(2.0, description="重试延迟时间（秒）")


class LLMProviderUpdate(BaseModel):
    """更新 LLM Provider 的请求模型"""

    apiProvider: str | None = None
    openAiBaseUrl: str | None = None
    openAiApiKey: str | None = None
    openAiModelId: str | None = None
    openAiLegacyFormat: bool | None = None
    openAiHeaders: dict[str, str] | None = None
    openAiCustomModelInfo: dict[str, Any] | None = None
    diffEnabled: bool | None = None
    todoListEnabled: bool | None = None
    fuzzyMatchThreshold: int | None = None
    rateLimitSeconds: int | None = None
    consecutiveMistakeLimit: int | None = None
    enableReasoningEffort: bool | None = None
    toolChoice: str | None = None
    temperature: float | None = None
    timeout: int | None = None
    maxRetries: int | None = None
    retryDelay: float | None = None


class LLMProviderResponse(BaseModel):
    """LLM Provider 操作响应"""

    success: bool
    message: str
    provider: dict | None = None


class LLMProviderTestResponse(BaseModel):
    """LLM Provider 测试响应"""

    success: bool
    supported: bool
    message: str
    model: str


# --- Helpers (与 workspaces/llm.py 共用) ---


def _safe_uid(user_id: str | None) -> str:
    uid = user_id or "default_user"
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in uid)


def _user_settings_file(user_id: str | None) -> Path:
    """用户级 LLM 配置文件路径：configs/{user_id}/settings.json"""
    return get_dawei_home() / "configs" / _safe_uid(user_id) / "settings.json"


_SENSITIVE_CONFIG_KEYS = {"openAiApiKey", "apiKey", "password", "secret", "token"}


def _sanitize_config_for_response(config: dict) -> dict:
    """Strip sensitive fields (API keys, secrets) from LLM config before returning in API responses."""
    return {k: v for k, v in config.items() if k not in _SENSITIVE_CONFIG_KEYS}


def _load_user_settings(user_id: str) -> dict:
    """加载用户级 LLM 配置"""
    settings_file = _user_settings_file(user_id)
    if not settings_file.exists():
        return {"providerProfiles": {"apiConfigs": {}, "modeApiConfigs": {}}}
    try:
        with settings_file.open(encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, PermissionError, OSError) as e:
        logger.error(f"Failed to load user LLM settings from {settings_file}: {e}")
        return {"providerProfiles": {"apiConfigs": {}, "modeApiConfigs": {}}}


def _save_user_settings(user_id: str, settings: dict) -> None:
    """保存用户级 LLM 配置"""
    settings_file = _user_settings_file(user_id)
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    with settings_file.open("w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def _reload_all_workspace_llm(user_id: str) -> None:
    """用户级 LLM 配置变更后，遍历该 user 的已初始化 WorkspaceContext 逐个 reload。

    best-effort，失败仅告警。不 reload 其他 user 的 context。
    """
    try:
        from dawei.workspace.workspace_service import WorkspaceService

        uid = user_id or "default_user"
        for key, ctx in WorkspaceService.get_all_contexts().items():
            if len(key) == 2 and key[1] != uid:
                continue
            mgr = getattr(ctx, "llm_manager", None) or getattr(ctx, "llm_manager_", None)
            if mgr is not None and hasattr(mgr, "reload_configs"):
                try:
                    mgr.reload_configs()
                except Exception as e:
                    logger.warning(f"reload LLM configs for {ctx.workspace_id} failed: {e}")
    except Exception as e:
        logger.warning(f"_reload_all_workspace_llm failed: {e}")


# --- API Endpoints ---


@router.get("", response_model=dict)
async def list_user_llm_providers(current_user: str = Depends(get_authenticated_user_id)):
    """获取用户级所有 LLM Provider 配置"""
    settings = _load_user_settings(current_user)
    provider_profiles = settings.get("providerProfiles", {})
    api_configs = provider_profiles.get("apiConfigs", {})
    current_name = provider_profiles.get("currentApiConfigName")

    providers = []
    for name, cfg in api_configs.items():
        providers.append({
            "name": name,
            "id": cfg.get("id", ""),
            "config": _sanitize_config_for_response(cfg),
            "location": "user",
            "isDefault": name == current_name,
        })

    return {
        "success": True,
        "settings": {
            "current_config": current_name,
            "user": providers,
            "workspace": [],
        },
    }


@router.post("", response_model=LLMProviderResponse, status_code=201)
async def create_user_llm_provider(
    data: LLMProviderCreate,
    current_user: str = Depends(get_authenticated_user_id),
):
    """创建用户级 LLM Provider 配置"""
    settings = _load_user_settings(current_user)
    provider_profiles = settings.setdefault("providerProfiles", {})
    api_configs = provider_profiles.setdefault("apiConfigs", {})

    if data.name in api_configs:
        raise HTTPException(status_code=400, detail=f"Provider '{data.name}' already exists")

    provider_id = str(uuid.uuid4())[:11]
    provider_config = {
        "id": provider_id,
        "apiProvider": data.apiProvider,
        "diffEnabled": data.diffEnabled,
        "todoListEnabled": data.todoListEnabled,
        "fuzzyMatchThreshold": data.fuzzyMatchThreshold,
        "rateLimitSeconds": data.rateLimitSeconds,
        "consecutiveMistakeLimit": data.consecutiveMistakeLimit,
        "enableReasoningEffort": data.enableReasoningEffort,
        "toolChoice": data.toolChoice,
        "temperature": data.temperature,
        "timeout": data.timeout,
        "maxRetries": data.maxRetries,
        "retryDelay": data.retryDelay,
    }
    if data.openAiBaseUrl:
        provider_config["openAiBaseUrl"] = data.openAiBaseUrl
    if data.openAiApiKey:
        provider_config["openAiApiKey"] = data.openAiApiKey
    if data.openAiModelId:
        provider_config["openAiModelId"] = data.openAiModelId
    if data.openAiLegacyFormat is not None:
        provider_config["openAiLegacyFormat"] = data.openAiLegacyFormat
    if data.openAiCustomModelInfo:
        provider_config["openAiCustomModelInfo"] = data.openAiCustomModelInfo
    provider_config["openAiHeaders"] = data.openAiHeaders if data.openAiHeaders is not None else {}

    if "currentApiConfigName" not in provider_profiles or not provider_profiles.get("currentApiConfigName"):
        provider_profiles["currentApiConfigName"] = data.name

    api_configs[data.name] = provider_config
    _save_user_settings(current_user, settings)
    _reload_all_workspace_llm(current_user)

    logger.info(f"Created user-level LLM provider '{data.name}' (user={current_user})")
    return LLMProviderResponse(
        success=True,
        message=f"LLM provider '{data.name}' created successfully at user level",
        provider={
            "name": data.name,
            "id": provider_id,
            "config": _sanitize_config_for_response(provider_config),
            "location": "user",
        },
    )


@router.put("/{provider_name}", response_model=LLMProviderResponse)
async def update_user_llm_provider(
    provider_name: str,
    data: LLMProviderUpdate,
    current_user: str = Depends(get_authenticated_user_id),
):
    """更新用户级 LLM Provider 配置"""
    settings = _load_user_settings(current_user)
    provider_profiles = settings.get("providerProfiles", {})
    api_configs = provider_profiles.get("apiConfigs", {})

    if provider_name not in api_configs:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

    existing = api_configs[provider_name]
    provider_id = existing.get("id", str(uuid.uuid4())[:11])

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if value is not None:
            existing[key] = value
    existing["id"] = provider_id

    api_configs[provider_name] = existing
    _save_user_settings(current_user, settings)
    _reload_all_workspace_llm(current_user)

    logger.info(f"Updated user-level LLM provider '{provider_name}' (user={current_user})")
    return LLMProviderResponse(
        success=True,
        message=f"LLM provider '{provider_name}' updated successfully",
        provider={
            "name": provider_name,
            "id": provider_id,
            "config": _sanitize_config_for_response(existing),
        },
    )


@router.delete("/{provider_name}", response_model=LLMProviderResponse)
async def delete_user_llm_provider(
    provider_name: str,
    current_user: str = Depends(get_authenticated_user_id),
):
    """删除用户级 LLM Provider 配置"""
    settings = _load_user_settings(current_user)
    provider_profiles = settings.get("providerProfiles", {})
    api_configs = provider_profiles.get("apiConfigs", {})

    if provider_name not in api_configs:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

    deleted_id = api_configs[provider_name].get("id")
    del api_configs[provider_name]

    if provider_profiles.get("currentApiConfigName") == provider_name:
        provider_profiles["currentApiConfigName"] = None

    mode_configs = provider_profiles.get("modeApiConfigs", {})
    if deleted_id:
        for mode, config_id in list(mode_configs.items()):
            if config_id == deleted_id:
                mode_configs[mode] = None

    _save_user_settings(current_user, settings)
    _reload_all_workspace_llm(current_user)

    logger.info(f"Deleted user-level LLM provider '{provider_name}' (user={current_user})")
    return LLMProviderResponse(
        success=True,
        message=f"LLM provider '{provider_name}' deleted successfully",
        provider=None,
    )


async def _probe_tool_call_stream(
    llm_api,
    messages: list,
    tools: list,
    temperature: float,
    tool_choice: str | None,
) -> tuple[list, str]:
    """流式探测：迭代 create_message 收集 tool_calls。"""
    from dawei.entity.stream_message import CompleteMessage

    all_tool_calls: list = []
    call_kwargs: dict = {"messages": messages, "tools": tools, "temperature": temperature}
    if tool_choice:
        call_kwargs["tool_choice"] = tool_choice

    async for chunk in llm_api.create_message(**call_kwargs):
        if isinstance(chunk, CompleteMessage) and chunk.tool_calls:
            all_tool_calls.extend(chunk.tool_calls)

    if all_tool_calls:
        return all_tool_calls, (
            f"Tool Call 支持正常（流式, temperature={temperature}, tool_choice={tool_choice or 'auto'}）"
        )

    # 未返回 tool call：尝试强制（仅当用户未指定 tool_choice）
    if not tool_choice:
        forced: list = []
        async for chunk in llm_api.create_message(
            messages=messages,
            tools=tools,
            tool_choice="required",
            temperature=temperature,
        ):
            if isinstance(chunk, CompleteMessage) and chunk.tool_calls:
                forced.extend(chunk.tool_calls)
        if forced:
            return forced, f"Tool Call 支持正常（流式·强制, temperature={temperature}）"

    return [], (
        f"该模型不支持 Tool Call 或未返回 tool call（流式, temperature={temperature}, "
        f"tool_choice={tool_choice or 'auto'}）"
    )


def _extract_tool_calls(response_data: object) -> list:
    """从非流式完整响应中提取 tool_calls。"""
    if not isinstance(response_data, dict):
        return []
    choices = response_data.get("choices") or []
    if not choices:
        return []
    return choices[0].get("message", {}).get("tool_calls") or []


async def _probe_tool_call_nonstream(
    llm_api,
    messages: list,
    tools: list,
    temperature: float,
    tool_choice: str | None,
) -> tuple[list, str]:
    """非流式探测：stream=False 请求，避开流式中途断连问题。"""
    params = llm_api._prepare_request_params(messages, tools=tools, temperature=temperature)
    params["stream"] = False
    params.pop("tool_stream", None)
    if tool_choice:
        params["tool_choice"] = tool_choice

    data = await llm_api._make_http_request("chat/completions", params)
    tool_calls = _extract_tool_calls(data)
    if tool_calls:
        return tool_calls, (
            f"Tool Call 支持正常（非流式, temperature={temperature}, tool_choice={tool_choice or 'auto'}）"
        )

    if not tool_choice:
        forced = _extract_tool_calls(
            await llm_api._make_http_request("chat/completions", {**params, "tool_choice": "required"})
        )
        if forced:
            return forced, f"Tool Call 支持正常（非流式·强制, temperature={temperature}）"

    return [], (
        f"该模型不支持 Tool Call 或未返回 tool call（非流式, temperature={temperature}, "
        f"tool_choice={tool_choice or 'auto'}）"
    )


async def _probe_tool_call_nonstream(
    llm_api,
    messages: list,
    tools: list,
    temperature: float,
    tool_choice: str | None,
) -> tuple[list, str]:
    """非流式探测：stream=False 请求一次，从完整响应提取 tool_calls。

    非流式由服务端发完完整响应再断开，能避开流式中途断连（Connection closed）。
    _prepare_request_params 会硬编码 stream=True / tool_stream=True，这里覆盖为非流式。
    """
    params = llm_api._prepare_request_params(messages, tools=tools, temperature=temperature)
    params["stream"] = False
    params.pop("tool_stream", None)
    if tool_choice:
        params["tool_choice"] = tool_choice

    data = await llm_api._make_http_request("chat/completions", params)
    tool_calls = _extract_tool_calls(data)
    if tool_calls:
        return tool_calls, (
            f"Tool Call 支持正常（非流式, temperature={temperature}, tool_choice={tool_choice or 'auto'}）"
        )

    if not tool_choice:
        forced = _extract_tool_calls(
            await llm_api._make_http_request("chat/completions", {**params, "tool_choice": "required"})
        )
        if forced:
            return forced, f"Tool Call 支持正常（非流式·强制, temperature={temperature}）"

    return [], (
        f"该模型不支持 Tool Call 或未返回 tool call（非流式, temperature={temperature}, "
        f"tool_choice={tool_choice or 'auto'}）"
    )


@router.post("/test", response_model=LLMProviderTestResponse)
async def test_user_llm_provider(
    data: LLMProviderCreate,
    mode: str = "non-stream",
    current_user: str = Depends(get_authenticated_user_id),
):
    """测试 LLM Provider 是否支持 Tool Call（与工作区无关，直接用配置直连 provider）。

    Args:
        mode: ``non-stream``（默认，非流式，稳定，避开流式中途断连）/ ``stream``（流式）。
    """
    try:
        from dawei.llm_api.impl.openai_compatible_api import OpenaiCompatibleClient
        from dawei.entity.lm_messages import UserMessage

        # 编辑场景：GET 响应已剥离 API Key，表单回传的 Key 为空。
        # 此时回退到磁盘已保存的同名 provider 的 Key，避免空 Key 导致 401。
        api_key = data.openAiApiKey
        if not api_key and data.name:
            try:
                saved = (
                    _load_user_settings(current_user)
                    .get("providerProfiles", {})
                    .get("apiConfigs", {})
                    .get(data.name, {})
                )
                if saved.get("openAiApiKey"):
                    api_key = saved["openAiApiKey"]
                    logger.info(f"test_user_llm_provider: 表单未带 Key，回退到磁盘已保存 Key (provider='{data.name}')")
            except Exception:
                logger.warning(f"test_user_llm_provider: 回退磁盘 Key 失败 (provider='{data.name}')", exc_info=True)

        api_provider = data.apiProvider.lower()

        if api_provider == "ollama":
            model_id = data.openAiModelId or "llama3.1"
            base_url = (data.openAiBaseUrl or "http://localhost:11434").rstrip("/")
            config = {
                "apiProvider": "ollama",
                "openAiBaseUrl": base_url,
                "openAiModelId": model_id,
                "openAiApiKey": api_key or "ollama",
                "openAiLegacyFormat": False,
            }
        else:
            model_id = data.openAiModelId or "gpt-4o"
            config = {
                "apiProvider": api_provider,
                "openAiBaseUrl": data.openAiBaseUrl or "https://api.openai.com/v1",
                "openAiApiKey": api_key or "",
                "openAiModelId": model_id,
                "openAiLegacyFormat": data.openAiLegacyFormat or False,
            }

        llm_api = OpenaiCompatibleClient(config)
        test_messages = [UserMessage(content="call test_function('hello')")]
        test_tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_function",
                    "description": "A test function",
                    "parameters": {
                        "type": "object",
                        "properties": {"test_param": {"type": "string"}},
                        "required": ["test_param"],
                    },
                },
            }
        ]

        test_temperature = data.temperature if data.temperature is not None else 0.7
        test_tool_choice = data.toolChoice if data.toolChoice else None

        if mode == "stream":
            tool_calls, message = await _probe_tool_call_stream(
                llm_api, test_messages, test_tools, test_temperature, test_tool_choice
            )
        else:
            tool_calls, message = await _probe_tool_call_nonstream(
                llm_api, test_messages, test_tools, test_temperature, test_tool_choice
            )

        return LLMProviderTestResponse(
            success=True,
            supported=len(tool_calls) > 0,
            message=message,
            model=model_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("test_user_llm_provider failed")
        low = str(e).lower()
        if "tool" in low or "function" in low:
            return LLMProviderTestResponse(
                success=True,
                supported=False,
                message=f"该模型不支持 Tool Call: {e}",
                model=data.openAiModelId or "",
            )
        # 流式断连等连接错误：自动降级到非流式探测
        if "connection" in low or "timeout" in low or "closed" in low:
            if mode == "stream":
                logger.info("流式探测失败，尝试非流式探测...")
                tool_calls, message = await _probe_tool_call_nonstream(
                    llm_api, test_messages, test_tools, test_temperature, test_tool_choice
                )
                return LLMProviderTestResponse(
                    success=True,
                    supported=len(tool_calls) > 0,
                    message=message,
                    model=model_id,
                )
        raise HTTPException(status_code=400, detail=humanize_llm_test_error(e))
