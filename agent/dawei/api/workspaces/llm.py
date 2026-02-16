# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""LLM Configuration API Routes

LLM提供商和配置管理
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dawei.workspace.user_workspace import UserWorkspace

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(tags=["workspaces-llm"])


# --- Pydantic 模型 ---


class LLMSettingsUpdate(BaseModel):
    """更新 LLM 配置的请求模型"""

    currentApiConfigName: str | None = None
    modeApiConfigs: dict[str, str] | None = Field(default_factory=dict)


class LLMProviderCreate(BaseModel):
    """创建 LLM Provider 的请求模型"""

    name: str = Field(..., description="Provider 配置名称")
    apiProvider: str = Field(..., description="API 提供商类型 (openai, ollama)")
    openAiBaseUrl: str | None = Field(None, description="OpenAI 兼容 API 基础 URL")
    openAiApiKey: str | None = Field(None, description="OpenAI API 密钥")
    openAiModelId: str | None = Field(None, description="OpenAI 模型 ID")
    openAiLegacyFormat: bool | None = Field(False, description="使用旧版 OpenAI 格式")
    openAiHeaders: dict[str, str] | None = Field(None, description="自定义 HTTP Headers")
    ollamaBaseUrl: str | None = Field(None, description="Ollama 基础 URL")
    ollamaModelId: str | None = Field(None, description="Ollama 模型 ID")
    ollamaApiKey: str | None = Field(None, description="Ollama API 密钥")
    openAiCustomModelInfo: dict[str, Any] | None = Field(None, description="自定义模型信息")
    diffEnabled: bool | None = Field(True, description="启用差异编辑")
    todoListEnabled: bool | None = Field(True, description="启用 TODO 列表")
    fuzzyMatchThreshold: int | None = Field(1, description="模糊匹配阈值")
    rateLimitSeconds: int | None = Field(0, description="速率限制秒数")
    consecutiveMistakeLimit: int | None = Field(3, description="连续错误限制")
    enableReasoningEffort: bool | None = Field(True, description="启用推理强度")


# --- 依赖注入 ---


# 依赖注入函数从core.py导入
def get_user_workspace(workspace_id: str) -> UserWorkspace:
    """Dependency to get a UserWorkspace instance."""
    from dawei.workspace import workspace_manager

    workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
    if not workspace_info:
        raise HTTPException(status_code=404, detail=f"Workspace with ID {workspace_id} not found")

    workspace_path = workspace_info.get("path")
    if not workspace_path:
        raise HTTPException(
            status_code=404,
            detail=f"Workspace path not found for ID {workspace_id}",
        )

    return UserWorkspace(workspace_path=workspace_path)


# --- LLM 配置管理路由 ---


@router.get("/{workspace_id}/llms")
async def get_workspace_llms(workspace: UserWorkspace = Depends(get_user_workspace)):
    """获取指定工作空间所有可用的 LLM 配置列表（名称和模型ID）。"""
    # 确保工作区已初始化
    if not workspace.is_initialized():
        await workspace.initialize()

    logger.info(f"Getting all LLM configs for workspace: {workspace.absolute_path}")

    llm_configs = workspace.get_all_llm_configs()

    if not llm_configs:
        logger.warning("No LLM configurations found in workspace")
        return {"success": True, "models": []}

    models_list = []
    for config_name, config_data in llm_configs.items():
        # config_data 是 LLMConfig 对象，需要访问其属性
        model_id = config_data.model_id if hasattr(config_data, "model_id") else None

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

    try:
        # 直接使用 user_workspace 已有的 llm_manager（包含多级加载逻辑）
        llm_provider = workspace.llm_manager
        if not llm_provider:
            from dawei.workspace.llm_config_manager import WorkspaceLLMConfigManager

            llm_config_manager = WorkspaceLLMConfigManager(workspace_path=workspace.absolute_path)
            await llm_config_manager.initialize()
            llm_provider = llm_config_manager.llm_provider
            workspace.llm_manager = llm_provider

        # 获取带来源信息的所有配置
        configs_with_source = llm_provider.get_all_configs_with_source()

        return {"success": True, "settings": configs_with_source}
    except Exception as e:
        logger.exception("Failed to read all LLM settings: ")
        raise HTTPException(status_code=500, detail=f"Failed to read all LLM settings: {e!s}")


@router.get("/{workspace_id}/mode-settings")
@router.get("/{workspace_id}/llm-settings")
async def get_workspace_llm_settings(
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """获取工作区的 LLM 配置设置 (从 settings.json 读取)"""
    if not workspace.is_initialized():
        await workspace.initialize()

    try:
        settings_file = workspace.user_config_dir / "settings.json"
        if not settings_file.exists():
            return {
                "success": True,
                "settings": {
                    "currentApiConfigName": None,
                    "allConfigs": {},
                    "modeApiConfigs": {},
                },
            }

        with Path(settings_file).open(encoding="utf-8") as f:
            settings = json.load(f)

        # 提取 LLM 相关的配置信息
        provider_profiles = settings.get("providerProfiles", {})
        current_config_name = provider_profiles.get("currentApiConfigName", "")

        # 获取当前配置的详细信息
        current_config = None
        all_configs = provider_profiles.get("apiConfigs", {})
        if current_config_name and current_config_name in all_configs:
            current_config = all_configs.get(current_config_name)

        return {
            "success": True,
            "settings": {
                "currentApiConfigName": current_config_name,
                "currentConfig": current_config,
                "allConfigs": all_configs,
                "modeApiConfigs": provider_profiles.get("modeApiConfigs", {}),
            },
        }
    except Exception as e:
        logger.exception("Failed to read LLM settings: ")
        raise HTTPException(status_code=500, detail=f"Failed to read LLM settings: {e!s}")


@router.post("/{workspace_id}/llm-settings")
async def update_workspace_llm_settings(
    settings_update: LLMSettingsUpdate,
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """更新工作区的 LLM 配置设置 (写入 settings.json)"""
    if not workspace.is_initialized():
        await workspace.initialize()

    try:
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

        logger.info(f"Updated LLM settings for workspace: {workspace.absolute_path}")

        return {
            "success": True,
            "message": "LLM settings updated successfully",
            "settings": {
                "currentApiConfigName": provider_profiles.get("currentApiConfigName"),
                "modeApiConfigs": settings.get("modeApiConfigs", {}),
            },
        }
    except Exception as e:
        logger.exception("Failed to update LLM settings: ")
        raise HTTPException(status_code=500, detail=f"Failed to update LLM settings: {e!s}")


@router.post("/{workspace_id}/llm-providers")
async def create_llm_provider(
    provider_data: LLMProviderCreate,
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """创建新的 LLM Provider 配置"""
    if not workspace.is_initialized():
        await workspace.initialize()

    try:
        settings_file = workspace.user_config_dir / "settings.json"

        # 读取现有配置
        if settings_file.exists():
            with Path(settings_file).open(encoding="utf-8") as f:
                settings = json.load(f)
        else:
            settings = {"providerProfiles": {"apiConfigs": {}, "modeApiConfigs": {}}}

        provider_profiles = settings.setdefault("providerProfiles", {})
        api_configs = provider_profiles.setdefault("apiConfigs", {})

        # 检查是否已存在同名配置
        if provider_data.name in api_configs:
            raise HTTPException(
                status_code=400,
                detail=f"Provider '{provider_data.name}' already exists",
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
        }

        # 添加 OpenAI 特定配置
        if provider_data.apiProvider == "openai":
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

        # 添加 Ollama 特定配置
        elif provider_data.apiProvider == "ollama":
            if provider_data.ollamaBaseUrl:
                provider_config["ollamaBaseUrl"] = provider_data.ollamaBaseUrl
            if provider_data.ollamaModelId:
                provider_config["ollamaModelId"] = provider_data.ollamaModelId
            if provider_data.ollamaApiKey:
                provider_config["ollamaApiKey"] = provider_data.ollamaApiKey

        # 保存配置
        api_configs[provider_data.name] = provider_config
        provider_profiles["apiConfigs"] = api_configs
        settings["providerProfiles"] = provider_profiles

        with settings_file.open("w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

        logger.info(f"Created LLM provider: {provider_data.name}")

        return {
            "success": True,
            "message": f"LLM provider '{provider_data.name}' created successfully",
            "provider": {
                "name": provider_data.name,
                "id": provider_id,
                "config": provider_config,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to create LLM provider: ")
        raise HTTPException(status_code=500, detail=f"Failed to create LLM provider: {e!s}")


@router.put("/{workspace_id}/llm-providers/{provider_name}")
async def update_llm_provider(
    provider_name: str,
    provider_data: LLMProviderCreate,
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """更新 LLM Provider 配置"""
    if not workspace.is_initialized():
        await workspace.initialize()

    try:
        settings_file = workspace.user_config_dir / "settings.json"

        if not settings_file.exists():
            raise HTTPException(status_code=404, detail="Settings file not found")

        with Path(settings_file).open(encoding="utf-8") as f:
            settings = json.load(f)

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
        }

        if provider_data.apiProvider == "openai":
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
            # 使用前端传来的 openAiHeaders，如果没有则使用现有配置的值
            provider_config["openAiHeaders"] = provider_data.openAiHeaders if provider_data.openAiHeaders is not None else existing_config.get("openAiHeaders", {})

        elif provider_data.apiProvider == "ollama":
            if provider_data.ollamaBaseUrl:
                provider_config["ollamaBaseUrl"] = provider_data.ollamaBaseUrl
            if provider_data.ollamaModelId:
                provider_config["ollamaModelId"] = provider_data.ollamaModelId
            if provider_data.ollamaApiKey:
                provider_config["ollamaApiKey"] = provider_data.ollamaApiKey

        api_configs[provider_name] = provider_config
        provider_profiles["apiConfigs"] = api_configs
        settings["providerProfiles"] = provider_profiles

        with settings_file.open("w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

        logger.info(f"Updated LLM provider: {provider_name}")

        return {
            "success": True,
            "message": f"LLM provider '{provider_name}' updated successfully",
            "provider": {
                "name": provider_name,
                "id": provider_id,
                "config": provider_config,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update LLM provider: ")
        raise HTTPException(status_code=500, detail=f"Failed to update LLM provider: {e!s}")


@router.post("/{workspace_id}/llm-providers/test")
async def test_llm_provider(
    provider_data: LLMProviderCreate,
    workspace: UserWorkspace = Depends(get_user_workspace),
):
    """测试 LLM Provider 是否支持 Tool Call"""
    if not workspace.is_initialized():
        await workspace.initialize()

    try:
        from dawei.llm_api.impl.openai_compatible_api import OpenaiCompatibleClient

        # 构建 provider 配置
        api_provider = provider_data.apiProvider

        # 构建 config dict
        if api_provider == "ollama":
            model_id = provider_data.ollamaModelId or "llama3.1:latest"
            config = {
                "apiProvider": "ollama",
                "ollamaBaseUrl": provider_data.ollamaBaseUrl or "http://localhost:11434",
                "ollamaApiKey": provider_data.ollamaApiKey or "ollama",
                "ollamaModelId": model_id,
            }
        else:
            # OpenAI 兼容格式
            model_id = provider_data.openAiModelId or "gpt-4o"
            config = {
                "apiProvider": api_provider,
                "openAiBaseUrl": provider_data.openAiBaseUrl or "https://api.openai.com/v1",
                "openAiApiKey": provider_data.openAiApiKey or "",
                "openAiModelId": model_id,
                "openAiLegacyFormat": provider_data.openAiLegacyFormat or False,
            }

        # 创建 API 实例
        llm_api = OpenaiCompatibleClient(config)

        # 准备测试消息 - 带一个简单的 tool 定义
        from dawei.entity.lm_messages import UserMessage

        test_messages = [UserMessage(content="Hello")]

        # 准备一个简单的 tool
        test_tools = [{"type": "function", "function": {"name": "test_function", "description": "A test function", "parameters": {"type": "object", "properties": {"test_param": {"type": "string", "description": "A test parameter"}}, "required": ["test_param"]}}}]

        # 尝试调用
        try:
            # 使用流式 API 并迭代获取完整响应
            from dawei.entity.stream_message import CompleteMessage

            all_tool_calls = []
            async for chunk in llm_api.create_message(
                messages=test_messages,
                tools=test_tools,
                temperature=0.7,
            ):
                if isinstance(chunk, CompleteMessage):
                    if chunk.tool_calls:
                        all_tool_calls.extend(chunk.tool_calls)

            has_tool_call = len(all_tool_calls) > 0

            if has_tool_call:
                return {
                    "success": True,
                    "supported": True,
                    "message": "Tool Call 支持正常",
                    "model": model_id,
                }
            else:
                # 没有返回 tool call，可能是模型不支持或没有强制要求
                # 尝试强制要求 tool call
                try:
                    all_tool_calls_force = []
                    async for chunk in llm_api.create_message(
                        messages=test_messages,
                        tools=test_tools,
                        tool_choice="required",
                        temperature=0.7,
                    ):
                        if isinstance(chunk, CompleteMessage):
                            if chunk.tool_calls:
                                all_tool_calls_force.extend(chunk.tool_calls)

                    if all_tool_calls_force:
                        return {
                            "success": True,
                            "supported": True,
                            "message": "Tool Call 支持正常 (强制模式)",
                            "model": model_id,
                        }
                except Exception:
                    pass

                return {
                    "success": True,
                    "supported": False,
                    "message": "该模型不支持 Tool Call 或未返回 tool call",
                    "model": model_id,
                }

        except Exception as e:
            error_msg = str(e)
            # 判断是否是模型不支持 tool call 的错误
            if "tool" in error_msg.lower() or "function" in error_msg.lower():
                return {
                    "success": True,
                    "supported": False,
                    "message": f"该模型不支持 Tool Call: {error_msg}",
                    "model": model_id,
                }
            # 其他错误（网络、认证等）
            raise HTTPException(status_code=400, detail=f"API 调用失败: {error_msg}")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to test LLM provider: ")
        raise HTTPException(status_code=500, detail=f"测试失败: {e!s}")


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

    try:
        from pathlib import Path as PathlibPath
        import os

        # 首先尝试从工作区级配置中删除
        settings_file = workspace.user_config_dir / "settings.json"

        if not settings_file.exists():
            # 如果工作区配置不存在，尝试用户级配置
            user_settings_file = PathlibPath.home() / ".dawei" / "configs" / "settings.json"
            if not user_settings_file.exists():
                raise HTTPException(status_code=404, detail="Settings file not found")
            settings_file = user_settings_file
        else:
            # 先检查工作区配置是否存在该 provider
            with Path(settings_file).open(encoding="utf-8") as f:
                settings = json.load(f)

            provider_profiles = settings.get("providerProfiles", {})
            api_configs = provider_profiles.get("apiConfigs", {})

            if provider_name in api_configs:
                # 在工作区配置中找到，直接删除
                pass
            else:
                # 工作区配置中没有，尝试用户级配置
                user_settings_file = PathlibPath.home() / ".dawei" / "configs" / "settings.json"
                if user_settings_file.exists():
                    settings_file = user_settings_file
                    with Path(settings_file).open(encoding="utf-8") as f:
                        settings = json.load(f)
                    provider_profiles = settings.get("providerProfiles", {})
                    api_configs = provider_profiles.get("apiConfigs", {})

        # 检查 provider 是否存在
        if provider_name not in api_configs:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

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

        logger.info(f"Deleted LLM provider: {provider_name} from {settings_file}")

        return {
            "success": True,
            "message": f"LLM provider '{provider_name}' deleted successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete LLM provider: ")
        raise HTTPException(status_code=500, detail=f"Failed to delete LLM provider: {e!s}")
