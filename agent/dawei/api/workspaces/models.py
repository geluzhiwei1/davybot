# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Workspace API Pydantic Models

所有与Workspace API相关的数据模型定义
"""

from typing import Any

from pydantic import BaseModel, Field

# 导入UserWorkspace和WorkspaceInfo类型
from dawei.workspace.user_workspace import WorkspaceInfo


class FileContent(BaseModel):
    path: str
    content: str


# Pydantic models for workspace management
class WorkspaceList(BaseModel):
    workspaces: list[WorkspaceInfo]


# --- 依赖注入 ---
class FileTreeItem(BaseModel):
    name: str
    path: str
    type: str  # 'file' or 'folder'
    level: int
    children: list["FileTreeItem"] = []


# 解决前向引用
FileTreeItem.model_rebuild()


class LLMSettingsUpdate(BaseModel):
    """更新 LLM 配置的请求模型"""

    currentApiConfigName: str | None = None
    modeApiConfigs: dict[str, str] | None = None


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


class GraphExecuteRequest(BaseModel):
    """执行任务图的请求模型"""

    task_id: str | None = Field(None, description="指定执行的任务ID,为空则执行根任务")
    input_data: dict[str, Any] | None = Field(None, description="执行输入数据")


# ==================== 任务 API 模型 ====================
class CheckpointInfo(BaseModel):
    """检查点信息模型"""

    checkpoint_id: str
    task_id: str
    timestamp: str
    nodes: dict[str, Any]
    root_node_id: str | None = None


# ==================== 任务图 API 端点 ====================
class UIContextUpdate(BaseModel):
    """更新用户UI上下文信息的请求模型"""

    open_files: list[str] | None = Field(None, description="打开的文件列表")
    active_applications: list[str] | None = Field(None, description="活动应用程序列表")
    user_preferences: dict[str, Any] | None = Field(None, description="用户偏好设置")
    current_file: str | None = Field(None, description="当前文件路径")
    current_selected_content: str | None = Field(None, description="当前选中的内容")
    current_mode: str | None = Field(None, description="当前模式")
    current_llm_id: str | None = Field(None, description="当前LLM模型ID")
    conversation_id: str | None = Field(None, description="对话ID")


class SubTaskCreate(BaseModel):
    """创建子任务的请求模型"""

    parent_task_id: str
    child_task_id: str
    description: str
    mode: str = "orchestrator"


class RenameFileRequest(BaseModel):
    """重命名文件请求"""

    old_path: str = Field(..., description="原文件路径")
    new_path: str = Field(..., description="新文件路径")


class McpServerConfig(BaseModel):
    """MCP 服务器配置模型"""

    command: str = Field(..., description="启动命令")
    args: list[str] = Field(default_factory=list, description="命令参数")
    cwd: str | None = Field(None, description="工作目录")
    alwaysAllow: list[str] | None = Field(None, description="始终允许的工具列表")
    timeout: int | None = Field(None, description="超时时间(秒)")


class McpSettingsData(BaseModel):
    """MCP 设置数据模型"""

    mcpServers: dict[str, McpServerConfig] = Field(
        default_factory=dict,
        description="MCP 服务器配置",
    )
