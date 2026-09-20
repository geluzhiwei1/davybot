# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""LLM Configuration API Routes

LLM提供商和配置管理
"""

import json
import logging
import os
import uuid
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from dawei import get_dawei_home
from dawei.api._llm_test_errors import humanize_llm_test_error
from dawei.workspace.user_workspace import UserWorkspace

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(tags=["workspaces-llm"])


def _user_settings_file(user_id: str) -> Path:
    """用户级 LLM 配置文件路径：configs/{user_id}/settings.json（per-user，不迁移旧全局文件）。"""
    from dawei.llm_api.llm_provider import _safe_uid

    return get_dawei_home() / "configs" / _safe_uid(user_id) / "settings.json"


# --- Security helpers ---

_SENSITIVE_CONFIG_KEYS = {"openAiApiKey", "apiKey", "password", "secret", "token"}


def _sanitize_config_for_response(config: dict) -> dict:
    """Strip sensitive fields (API keys, secrets) from LLM config before returning in API responses.

    NEVER return raw API keys to the frontend — they should only flow
    frontend→backend (on create/update), never backend→frontend (on read).
    """
    return {k: v for k, v in config.items() if k not in _SENSITIVE_CONFIG_KEYS}


def _sanitize_configs_with_source(configs: dict) -> dict:
    """Recursively sanitize the configs-with-source structure returned by llm_provider."""
    sanitized = dict(configs)
    for section in ("user", "workspace", "other"):
        if section in sanitized:
            sanitized[section] = [
                {
                    **item,
                    "config": {
                        **item["config"],
                        "config": _sanitize_config_for_response(item["config"].get("config", {})),
                    },
                }
                if isinstance(item.get("config"), dict) and "config" in item["config"]
                else item
                for item in sanitized[section]
            ]
    return sanitized


# --- Provider 目录（后端单一数据源，前端动态获取，不再写死） ---

LLM_PROVIDER_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "openai",
        "label": "OpenAI兼容",
        "baseUrl": "https://api.openai.com/v1",
        "modelId": "gpt-4o-mini",
        "freeForm": True,
        "description": "任意 OpenAI 兼容 API，可自由填写 Base URL / 模型 ID",
    },
    {
        "id": "glm",
        "label": "GLM (智谱)",
        "baseUrl": "https://open.bigmodel.cn/api/paas/v4",
        "modelId": "glm-4-plus",
        "freeForm": True,
        "description": "智谱 GLM 系列",
    },
    {
        "id": "ollama",
        "label": "Ollama (本地)",
        "baseUrl": "http://localhost:11434/v1",
        "modelId": "qwen2.5:7b",
        "freeForm": True,
        "description": "本地 Ollama，使用 OpenAI 兼容接口",
    },
    {
        "id": "minimax",
        "label": "MiniMax",
        "baseUrl": "https://api.minimax.chat/v1",
        "modelId": "MiniMax-M2.5",
        "freeForm": True,
        "description": "MiniMax 系列（OpenAI 兼容）",
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "baseUrl": "https://api.deepseek.com/v1",
        "modelId": "deepseek-chat",
        "freeForm": True,
        "description": "DeepSeek 系列（OpenAI 兼容）",
    },
    {
        "id": "moonshot",
        "label": "Moonshot (月之暗面)",
        "baseUrl": "https://api.moonshot.cn/v1",
        "modelId": "kimi-k2-0905-preview",
        "freeForm": True,
        "description": "Kimi 系列（OpenAI 兼容）",
    },
    {
        "id": "qwen",
        "label": "通义千问",
        "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "modelId": "qwen-max",
        "freeForm": True,
        "description": "阿里云百炼（OpenAI 兼容）",
    },
]


# --- Pydantic 模型 ---


class LLMSettingsUpdate(BaseModel):
    """更新 LLM 配置的请求模型"""

    currentApiConfigName: str | None = None
    modeApiConfigs: Dict[str, str] | None = Field(default_factory=dict)


class LLMProviderCreate(BaseModel):
    """创建 LLM Provider 的请求模型 - 简化版本，所有 OpenAI 兼容提供商使用统一字段"""

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
    saveLocation: str | None = Field("user", description="保存位置: user 或 workspace")


# --- 依赖注入 ---


# 依赖注入函数从core.py导入
from dawei.api.workspaces._deps import get_user_workspace

@router.get("/{workspace_id}/llm-provider-catalog")
async def get_llm_provider_catalog():
    """获取可用 LLM Provider 目录。前端下拉选项的单一数据源，避免写死。"""
    return {"success": True, "providers": LLM_PROVIDER_CATALOG}


@router.get("/{workspace_id}/llms")
async def get_workspace_llms(workspace: UserWorkspace = Depends(get_user_workspace)):
    """获取指定工作空间所有可用的 LLM 配置列表（名称和模型ID）。"""
    # 确保工作区已初始化
    if not workspace.is_initialized():
        await workspace.initialize()

    logger.info(f"Getting all LLM configs for workspace: {workspace.absolute_path}")

    # 每次都重新创建LLMProvider，确保获取最新配置
    from dawei.workspace.llm_config_manager import WorkspaceLLMConfigManager

    llm_config_manager = WorkspaceLLMConfigManager(workspace_path=workspace.absolute_path, user_id=workspace.user_id)
    await llm_config_manager.initialize()
    llm_provider = llm_config_manager.llm_provider

    # 获取所有配置（合并用户级和工作区级）
    all_configs = llm_provider.get_all_configs()

    if not all_configs:
        logger.warning("No LLM configurations found in workspace")
        return {"success": True, "models": []}

    models_list = []
    for config_name, config_data in all_configs.items():
        # config_data 是 LLMProviderConfig 对象，model_id 在 config.config.model_id
        model_id = None
        if hasattr(config_data, "config") and hasattr(config_data.config, "model_id"):
            model_id = config_data.config.model_id

        if model_id:
            models_list.append({"llm_id": config_name, "model_id": model_id})
        else:
            logger.warning(f"No model ID found for config: {config_name}")

    # Sort by name
    sorted_models_list = sorted(models_list, key=lambda x: x["llm_id"])

    logger.info(f"Found {len(sorted_models_list)} LLM configs.")
    return {"success": True, "models": sorted_models_list}


@router.get("/{workspace_id}/llm-settings-all")
async def get_workspace_llm_settings_all_levels(
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """获取工作区的所有级别 LLM 配置设置（用户级、工作区级）"""
    if not workspace.is_initialized():
        await workspace.initialize()

    # 每次都重新创建LLMProvider，确保获取最新配置
    from dawei.workspace.llm_config_manager import WorkspaceLLMConfigManager

    llm_config_manager = WorkspaceLLMConfigManager(workspace_path=workspace.absolute_path, user_id=workspace.user_id)
    await llm_config_manager.initialize()
    llm_provider = llm_config_manager.llm_provider

    # 获取带来源信息的所有配置
    configs_with_source = llm_provider.get_all_configs_with_source()

    # Sanitize: never return raw API keys in API responses
    return {"success": True, "settings": _sanitize_configs_with_source(configs_with_source)}


@router.get("/{workspace_id}/llm-providers/effective")
async def get_workspace_llm_providers_effective(
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """override-or-inherit 合并 user 默认 + workspace 覆盖的 LLM provider 列表。

    供前端「工作区设置 LLM tab」三态展示（继承默认 / 覆盖 / 来源）。
    LLM 语义为整 provider 覆盖（同名 ws 整体替换 user），非字段级。
    """
    if not workspace.is_initialized():
        await workspace.initialize()
    from dawei.workspace.llm_config_manager import WorkspaceLLMConfigManager

    llm_config_manager = WorkspaceLLMConfigManager(workspace_path=workspace.absolute_path, user_id=workspace.user_id)
    await llm_config_manager.initialize()
    llm_provider = llm_config_manager.llm_provider

    configs_with_source = llm_provider.get_all_configs_with_source()
    current_config_name = configs_with_source.get("current_config")

    def _prov(entry: dict) -> dict:
        return {
            "name": entry["name"],
            "config": _sanitize_config_for_response(entry["config"]["config"]),
        }

    default = [_prov(c) for c in configs_with_source.get("user", [])]
    override = [_prov(c) for c in configs_with_source.get("workspace", [])]

    effective = []
    seen: set[str] = set()
    ws_entries = configs_with_source.get("workspace", [])
    for entry in configs_with_source.get("user", []):
        name = entry["name"]
        seen.add(name)
        ws_match = next((c for c in ws_entries if c["name"] == name), None)
        if ws_match:
            effective.append({**_prov(ws_match), "source": "workspace", "user_overridden": True})
        else:
            effective.append({**_prov(entry), "source": "user", "user_overridden": False})
    for entry in ws_entries:
        if entry["name"] in seen:
            continue
        effective.append({**_prov(entry), "source": "workspace", "user_overridden": False})

    return {
        "success": True,
        "current": current_config_name,
        "default": default,
        "override": override,
        "effective": effective,
    }


@router.get("/{workspace_id}/mode-settings")
@router.get("/{workspace_id}/llm-settings")
async def get_workspace_llm_settings(
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """获取工作区的 LLM 配置设置（合并用户级和工作区级）"""
    if not workspace.is_initialized():
        await workspace.initialize()

    # 每次都重新创建LLMProvider，确保获取最新配置
    from dawei.workspace.llm_config_manager import WorkspaceLLMConfigManager

    llm_config_manager = WorkspaceLLMConfigManager(workspace_path=workspace.absolute_path, user_id=workspace.user_id)
    await llm_config_manager.initialize()
    llm_provider = llm_config_manager.llm_provider

    # 获取带来源信息的所有配置
    configs_with_source = llm_provider.get_all_configs_with_source()

    # 获取当前配置名称
    current_config_name = configs_with_source.get("current_config")

    # 合并所有配置（用户级+工作区级+其他来源，保持与 /llms 一致）
    all_configs = {}
    for config in configs_with_source.get("user", []):
        all_configs[config["name"]] = config["config"]["config"]
    for config in configs_with_source.get("workspace", []):
        all_configs[config["name"]] = config["config"]["config"]
    for config in configs_with_source.get("other", []):
        all_configs[config["name"]] = config["config"]["config"]

    # Sanitize: strip API keys from all configs before returning
    all_configs = {name: _sanitize_config_for_response(cfg) for name, cfg in all_configs.items()}

    # 获取当前配置的详细信息
    current_config = None
    if current_config_name and current_config_name in all_configs:
        current_config = all_configs.get(current_config_name)

    return {
        "success": True,
        "settings": {
            "currentApiConfigName": current_config_name,
            "currentConfig": current_config,
            "allConfigs": all_configs,
            "modeApiConfigs": configs_with_source.get("mode_configs", {}),
        },
    }


@router.post("/{workspace_id}/llm-settings")
async def update_workspace_llm_settings(
    settings_update: LLMSettingsUpdate,
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """更新工作区的 LLM 配置设置 (写入 settings.json)"""
    if not workspace.is_initialized():
        await workspace.initialize()

    settings_file = workspace.user_config_dir / "settings.json"

    # 读取现有配置
    if settings_file.exists():
        with Path(settings_file).open(encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = {"providerProfiles": {}}

    # 更新配置
    provider_profiles = settings.get("providerProfiles", {})

    if settings_update.currentApiConfigName is not None:
        provider_profiles["currentApiConfigName"] = settings_update.currentApiConfigName

    if settings_update.modeApiConfigs is not None:
        mode_configs = provider_profiles.get("modeApiConfigs", {})
        mode_configs.update(settings_update.modeApiConfigs)
        provider_profiles["modeApiConfigs"] = mode_configs

    settings["providerProfiles"] = provider_profiles

    # 写入文件
    with settings_file.open("w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    # 重新加载 LLM 配置（而不是设置为 None，这样所有 Agent 都能立即看到新配置）
    if workspace.llm_manager:
        workspace.llm_manager.reload_configs()
        logger.info(
            f"Reloaded LLM configs after updating settings "
            f"(current={settings_update.currentApiConfigName})"
        )
    else:
        # 如果 llm_manager 已经是 None（已被缓存清除），下次会自动创建新的
        logger.info("LLM manager was None, will create new instance on next access")

    logger.info(f"Updated LLM settings for workspace: {workspace.absolute_path}")

    return {
        "success": True,
        "message": "LLM settings updated successfully",
        "settings": {
            "currentApiConfigName": provider_profiles.get("currentApiConfigName"),
            "modeApiConfigs": settings.get("modeApiConfigs", {}),
        },
    }


@router.post("/{workspace_id}/llm-providers")
async def create_llm_provider(
    provider_data: LLMProviderCreate,
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """创建新的 LLM Provider 配置

    根据 saveLocation 参数决定保存到用户级还是工作区级配置：
    - user: 保存到 ~/.dawei/settings.json
    - workspace: 保存到 {workspace}/.dawei/settings.json
    """
    if not workspace.is_initialized():
        await workspace.initialize()

    # 根据 saveLocation 决定保存位置
    save_location = provider_data.saveLocation or "user"

    if save_location == "user":
        # 保存到用户级配置（per-user）
        settings_file = _user_settings_file(workspace.user_id)
    else:
        # 保存到工作区级配置
        settings_file = workspace.user_config_dir / "settings.json"

    # 读取现有配置
    if settings_file.exists():
        with Path(settings_file).open(encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = {"providerProfiles": {"apiConfigs": {}, "modeApiConfigs": {}}}
        # 确保目录存在
        settings_file.parent.mkdir(parents=True, exist_ok=True)

    provider_profiles = settings.setdefault("providerProfiles", {})
    api_configs = provider_profiles.setdefault("apiConfigs", {})

    # 检查是否已存在同名配置
    if provider_data.name in api_configs:
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{provider_data.name}' already exists in {save_location}-level config",
        )

    # 创建新的 provider 配置
    provider_id = str(uuid.uuid4())[:11]  # 生成短 ID
    provider_config = {
        "id": provider_id,
        "apiProvider": provider_data.apiProvider,
        "diffEnabled": provider_data.diffEnabled,
        "todoListEnabled": provider_data.todoListEnabled,
        "fuzzyMatchThreshold": provider_data.fuzzyMatchThreshold,
        "rateLimitSeconds": provider_data.rateLimitSeconds,
        "consecutiveMistakeLimit": provider_data.consecutiveMistakeLimit,
        "enableReasoningEffort": provider_data.enableReasoningEffort,
        "toolChoice": provider_data.toolChoice,
        "temperature": provider_data.temperature,
        "timeout": provider_data.timeout,
        "maxRetries": provider_data.maxRetries,
        "retryDelay": provider_data.retryDelay,
    }

    if provider_data.openAiBaseUrl:
        provider_config["openAiBaseUrl"] = provider_data.openAiBaseUrl
    if provider_data.openAiApiKey:
        provider_config["openAiApiKey"] = provider_data.openAiApiKey
    if provider_data.openAiModelId:
        provider_config["openAiModelId"] = provider_data.openAiModelId
    if provider_data.openAiLegacyFormat is not None:
        provider_config["openAiLegacyFormat"] = provider_data.openAiLegacyFormat
    if provider_data.openAiCustomModelInfo:
        provider_config["openAiCustomModelInfo"] = provider_data.openAiCustomModelInfo
    provider_config["openAiHeaders"] = provider_data.openAiHeaders if provider_data.openAiHeaders is not None else {}

    # 如果当前没有 currentApiConfigName，则设置为即将创建的 provider
    if "currentApiConfigName" not in provider_profiles or not provider_profiles.get("currentApiConfigName"):
        provider_profiles["currentApiConfigName"] = provider_data.name

    # 保存配置
    api_configs[provider_data.name] = provider_config
    provider_profiles["apiConfigs"] = api_configs
    settings["providerProfiles"] = provider_profiles

    with settings_file.open("w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    # 重新加载 LLM 配置（而不是设置为 None，这样所有 Agent 都能立即看到新配置）
    if workspace.llm_manager:
        workspace.llm_manager.reload_configs()
        logger.info(f"Reloaded LLM configs after creating provider '{provider_data.name}'")
    else:
        # 如果 llm_manager 已经是 None（已被缓存清除），下次会自动创建新的
        logger.info("LLM manager was None, will create new instance on next access")

    location_name = "用户级" if save_location == "user" else "工作区级"
    logger.info(f"Created LLM provider '{provider_data.name}' at {location_name} config: {settings_file}")

    return {
        "success": True,
        "message": f"LLM provider '{provider_data.name}' created successfully at {location_name} level",
        "provider": {
            "name": provider_data.name,
            "id": provider_id,
            "config": _sanitize_config_for_response(provider_config),
            "location": save_location,
        },
    }


@router.put("/{workspace_id}/llm-providers/{provider_name}")
async def update_llm_provider(
    provider_name: str,
    provider_data: LLMProviderCreate,
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """更新 LLM Provider 配置

    支持更新用户级和工作区级的 Provider 配置
    """
    if not workspace.is_initialized():
        await workspace.initialize()

    # 确定 provider 在哪个配置文件中（先工作区，后用户）
    workspace_settings_file = workspace.user_config_dir / "settings.json"
    user_settings_file = _user_settings_file(workspace.user_id)

    # 查找 provider
    settings_file = None
    settings = None

    # 先检查工作区级配置
    if workspace_settings_file.exists():
        with workspace_settings_file.open(encoding="utf-8") as f:
            workspace_settings_data = json.load(f)
        workspace_api_configs = workspace_settings_data.get("providerProfiles", {}).get("apiConfigs", {})
        if provider_name in workspace_api_configs:
            settings_file = workspace_settings_file
            settings = workspace_settings_data

    # 如果工作区级没找到，检查用户级配置
    if not settings_file and user_settings_file.exists():
        with user_settings_file.open(encoding="utf-8") as f:
            user_settings_data = json.load(f)
        user_api_configs = user_settings_data.get("providerProfiles", {}).get("apiConfigs", {})
        if provider_name in user_api_configs:
            settings_file = user_settings_file
            settings = user_settings_data

    # 如果都没找到，报错
    if not settings_file:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

    provider_profiles = settings.get("providerProfiles", {})
    api_configs = provider_profiles.get("apiConfigs", {})

    # 检查 provider 是否存在
    if provider_name not in api_configs:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

    # 更新配置
    existing_config = api_configs[provider_name]
    provider_id = existing_config.get("id", str(uuid.uuid4())[:11])

    provider_config = {
        "id": provider_id,
        "apiProvider": provider_data.apiProvider,
        "diffEnabled": provider_data.diffEnabled,
        "todoListEnabled": provider_data.todoListEnabled,
        "fuzzyMatchThreshold": provider_data.fuzzyMatchThreshold,
        "rateLimitSeconds": provider_data.rateLimitSeconds,
        "consecutiveMistakeLimit": provider_data.consecutiveMistakeLimit,
        "enableReasoningEffort": provider_data.enableReasoningEffort,
        "toolChoice": provider_data.toolChoice,
        "temperature": provider_data.temperature,
        "timeout": provider_data.timeout,
        "maxRetries": provider_data.maxRetries,
        "retryDelay": provider_data.retryDelay,
    }

    if provider_data.openAiBaseUrl:
        provider_config["openAiBaseUrl"] = provider_data.openAiBaseUrl
    # 编辑时前端不回传 API Key（GET 响应已被 _sanitize_config_for_response 剥离），
    # 此时保留 existing_config 里的旧 Key，避免整体替换后 Key 丢失导致下次测试失败。
    if provider_data.openAiApiKey:
        provider_config["openAiApiKey"] = provider_data.openAiApiKey
    elif "openAiApiKey" in existing_config:
        provider_config["openAiApiKey"] = existing_config["openAiApiKey"]
    if provider_data.openAiModelId:
        provider_config["openAiModelId"] = provider_data.openAiModelId
    if provider_data.openAiLegacyFormat is not None:
        provider_config["openAiLegacyFormat"] = provider_data.openAiLegacyFormat
    if provider_data.openAiCustomModelInfo:
        provider_config["openAiCustomModelInfo"] = provider_data.openAiCustomModelInfo
    # 使用前端传来的 openAiHeaders，如果没有则使用现有配置的值
    provider_config["openAiHeaders"] = provider_data.openAiHeaders if provider_data.openAiHeaders is not None else existing_config.get("openAiHeaders", {})

    api_configs[provider_name] = provider_config
    provider_profiles["apiConfigs"] = api_configs
    settings["providerProfiles"] = provider_profiles

    with settings_file.open("w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    # 重新加载 LLM 配置（而不是设置为 None，这样所有 Agent 都能立即看到新配置）
    if workspace.llm_manager:
        workspace.llm_manager.reload_configs()
        logger.info(f"Reloaded LLM configs after updating provider '{provider_name}'")
    else:
        # 如果 llm_manager 已经是 None（已被缓存清除），下次会自动创建新的
        logger.info("LLM manager was None, will create new instance on next access")

    logger.info(f"Updated LLM provider: {provider_name}")

    return {
        "success": True,
        "message": f"LLM provider '{provider_name}' updated successfully",
        "provider": {
            "name": provider_name,
            "id": provider_id,
            "config": _sanitize_config_for_response(provider_config),
        },
    }


async def _probe_llm_nonstream(
    llm_api,
    messages: list,
    tools: list,
    temperature: float,
    tool_choice: str | None,
    model_id: str,
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
        return tool_calls, f"Tool Call 支持正常（非流式, temperature={temperature}, tool_choice={tool_choice or 'auto'}）"

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


def _extract_tool_calls(response_data: object) -> list:
    """从非流式完整响应中提取 tool_calls。"""
    if not isinstance(response_data, dict):
        return []
    choices = response_data.get("choices") or []
    for choice in choices:
        msg = choice.get("message") or {}
        if msg.get("tool_calls"):
            return msg["tool_calls"]
    return []


async def test_llm_provider(
    provider_data: LLMProviderCreate,
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """测试 LLM Provider 是否支持 Tool Call"""
    if not workspace.is_initialized():
        await workspace.initialize()

    try:
        from dawei.llm_api.impl.openai_compatible_api import OpenaiCompatibleClient

        api_provider = provider_data.apiProvider.lower()

        if api_provider == "ollama":
            model_id = provider_data.openAiModelId or "llama3.1"
            base_url = provider_data.openAiBaseUrl or "http://localhost:11434"
            base_url = base_url.rstrip("/")

            config = {
                "apiProvider": "ollama",
                "openAiBaseUrl": base_url,
                "openAiModelId": model_id,
                "openAiApiKey": provider_data.openAiApiKey or "ollama",
                "openAiLegacyFormat": False,
            }
        else:
            # 其他 OpenAI 兼容提供商
            model_id = provider_data.openAiModelId or "gpt-4o"
            config = {
                "apiProvider": api_provider,
                "openAiBaseUrl": provider_data.openAiBaseUrl or "https://api.openai.com/v1",
                "openAiApiKey": provider_data.openAiApiKey or "",
                "openAiModelId": model_id,
                "openAiLegacyFormat": provider_data.openAiLegacyFormat or False,
            }

        llm_api = OpenaiCompatibleClient(config)

        from dawei.entity.lm_messages import UserMessage

        test_messages = [UserMessage(content="call test_function('hello')")]

        # 准备一个简单的 tool
        test_tools = [{"type": "function", "function": {"name": "test_function", "description": "A test function", "parameters": {"type": "object", "properties": {"test_param": {"type": "string", "description": "A test parameter"}}, "required": ["test_param"]}}}]

        # 尝试调用
        try:
            # 使用流式 API 并迭代获取完整响应
            from dawei.entity.stream_message import CompleteMessage

            # 从 UI 获取参数，如果没有设置则使用默认值
            test_temperature = provider_data.temperature if provider_data.temperature is not None else 0.7
            test_tool_choice = provider_data.toolChoice if provider_data.toolChoice else None

            # 第一次测试：使用用户配置的参数（如果有 tool_choice 则使用，否则不强制）
            all_tool_calls = []
            call_kwargs = {
                "messages": test_messages,
                "tools": test_tools,
                "temperature": test_temperature,
            }

            # 如果用户设置了 tool_choice，则使用它
            if test_tool_choice:
                call_kwargs["tool_choice"] = test_tool_choice

            async for chunk in llm_api.create_message(**call_kwargs):
                if isinstance(chunk, CompleteMessage):
                    if chunk.tool_calls:
                        all_tool_calls.extend(chunk.tool_calls)

            has_tool_call = len(all_tool_calls) > 0

            if has_tool_call:
                return {
                    "success": True,
                    "supported": True,
                    "message": f"Tool Call 支持正常 (temperature={test_temperature}, tool_choice={test_tool_choice or 'auto'})",
                    "model": model_id,
                }
            # 没有返回 tool call，可能是模型不支持或没有强制要求
            # 尝试强制要求 tool call（仅在用户没有设置 tool_choice 时）
            if not test_tool_choice:
                try:
                    all_tool_calls_force = []
                    async for chunk in llm_api.create_message(
                        messages=test_messages,
                        tools=test_tools,
                        tool_choice="required",
                        temperature=test_temperature,
                    ):
                        if isinstance(chunk, CompleteMessage):
                            if chunk.tool_calls:
                                all_tool_calls_force.extend(chunk.tool_calls)

                    if all_tool_calls_force:
                        return {
                            "success": True,
                            "supported": True,
                            "message": f"Tool Call 支持正常 (强制模式, temperature={test_temperature})",
                            "model": model_id,
                        }
                except Exception:
                    pass

            return {
                "success": True,
                "supported": False,
                "message": f"该模型不支持 Tool Call 或未返回 tool call (temperature={test_temperature}, tool_choice={test_tool_choice or 'auto'})",
                "model": model_id,
            }

        except Exception as e:
            logger.exception("test_llm_provider stream failed, trying non-stream fallback")
            error_msg = str(e)
            # 判断是否是模型不支持 tool call 的错误
            if "tool" in error_msg.lower() or "function" in error_msg.lower():
                return {
                    "success": True,
                    "supported": False,
                    "message": f"该模型不支持 Tool Call: {error_msg}",
                    "model": model_id,
                }
            # 流式断连等连接错误：自动降级到非流式探测
            if "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                logger.info("流式探测失败，尝试非流式探测...")
                tool_calls, message = await _probe_llm_nonstream(
                    llm_api, test_messages, test_tools, test_temperature, test_tool_choice, model_id
                )
                return {
                    "success": True,
                    "supported": len(tool_calls) > 0,
                    "message": message,
                    "model": model_id,
                }
            # 其他错误（网络、认证等）：翻译成用户可理解的提示（原始 traceback 见日志）
            raise HTTPException(status_code=400, detail=humanize_llm_test_error(e))

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to test LLM provider: ")
        raise HTTPException(status_code=500, detail=humanize_llm_test_error(e))


@router.delete("/{workspace_id}/llm-providers/{provider_name}")
async def delete_llm_provider(
    provider_name: str,
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """删除 LLM Provider 配置

    支持删除用户级和工作区级的 Provider 配置
    """
    if not workspace.is_initialized():
        await workspace.initialize()

    # 确定 provider 在哪个配置文件中
    workspace_settings_file = workspace.user_config_dir / "settings.json"
    user_settings_file = _user_settings_file(workspace.user_id)

    # 查找 provider：先工作区，后用户级
    settings_file = None

    # 检查工作区级配置
    if workspace_settings_file.exists():
        with workspace_settings_file.open(encoding="utf-8") as f:
            workspace_settings = json.load(f)
        workspace_api_configs = workspace_settings.get("providerProfiles", {}).get("apiConfigs", {})
        if provider_name in workspace_api_configs:
            settings_file = workspace_settings_file
            settings = workspace_settings

    # 如果工作区级没找到，检查用户级配置
    if not settings_file and user_settings_file.exists():
        with user_settings_file.open(encoding="utf-8") as f:
            user_settings = json.load(f)
        user_api_configs = user_settings.get("providerProfiles", {}).get("apiConfigs", {})
        if provider_name in user_api_configs:
            settings_file = user_settings_file
            settings = user_settings

    # 如果都没找到，报错
    if not settings_file:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

    provider_profiles = settings.get("providerProfiles", {})
    api_configs = provider_profiles.get("apiConfigs", {})

    # 在删除前获取 provider 的 id
    deleted_provider_id = api_configs[provider_name].get("id")

    # 删除配置
    del api_configs[provider_name]

    # 如果是当前默认配置,清除默认设置
    if provider_profiles.get("currentApiConfigName") == provider_name:
        provider_profiles["currentApiConfigName"] = None

    # 清除 modeApiConfigs 中的引用
    mode_configs = provider_profiles.get("modeApiConfigs", {})
    if deleted_provider_id:
        for mode, config_id in list(mode_configs.items()):
            if config_id == deleted_provider_id:
                mode_configs[mode] = None

    provider_profiles["apiConfigs"] = api_configs
    provider_profiles["modeApiConfigs"] = mode_configs
    settings["providerProfiles"] = provider_profiles

    with settings_file.open("w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    # 重新加载 LLM 配置（而不是设置为 None，这样所有 Agent 都能立即看到新配置）
    if workspace.llm_manager:
        workspace.llm_manager.reload_configs()
        logger.info(f"Reloaded LLM configs after deleting provider '{provider_name}'")
    else:
        # 如果 llm_manager 已经是 None（已被缓存清除），下次会自动创建新的
        logger.info("LLM manager was None, will create new instance on next access")

    logger.info(f"Deleted LLM provider: {provider_name} from {settings_file}")

    return {
        "success": True,
        "message": f"LLM provider '{provider_name}' deleted successfully",
    }
