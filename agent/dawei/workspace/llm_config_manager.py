# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Workspace LLM配置管理器

负责工作区的LLM配置加载、管理和查询
"""

import logging
from pathlib import Path

from dawei.entity.llm_config import LLMConfig
from dawei.llm_api.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class WorkspaceLLMConfigManager:
    """工作区LLM配置管理器

    职责：
    - 初始化和管理LLMProvider
    - LLM配置的加载和查询
    - 当前LLM配置的获取和设置
    - 模式特定的LLM配置管理
    """

    def __init__(self, workspace_path: Path):
        """初始化LLM配置管理器

        Args:
            workspace_path: 工作区路径

        """
        self.workspace_path = Path(workspace_path).resolve()
        self.absolute_path = str(self.workspace_path)

        # LLM提供者
        self.llm_provider: LLMProvider | None = None

        # 当前对话（由外部注入，用于更新LLM模型）
        self.current_conversation = None

        logger.info(f"WorkspaceLLMConfigManager created for: {self.absolute_path}")

    # ==================== 初始化方法 ====================

    async def initialize(self):
        """初始化LLM提供者"""
        logger.info("Initializing LLM provider...")

        # 创建 LLM 提供者，传入工作区路径以支持工作区级配置
        self.llm_provider = LLMProvider(workspace_path=self.absolute_path)
        logger.info("LLMProvider created successfully.")

        # 记录 LLM 配置统计信息
        stats = self.llm_provider.get_statistics()
        logger.info(
            f"LLM configurations loaded: {stats['total_configs']} total, user: {stats['user_configs']}, workspace: {stats['workspace_configs']}",
        )
        logger.info(f"Current LLM config: {stats['current_config']}")

    # ==================== LLM配置查询和管理 ====================

    def get_current_llm_config(self) -> LLMConfig | None:
        """获取当前LLM配置

        Returns:
            当前的LLM配置对象，如果未初始化则返回None

        """
        if not self.llm_provider:
            return None

        provider_config = self.llm_provider.get_current_config()
        return provider_config.config if provider_config else None

    def set_current_llm_config(self, config_id: str) -> bool:
        """设置当前LLM配置

        Args:
            config_id: LLM配置ID

        Returns:
            设置成功返回True，失败返回False

        """
        if not self.llm_provider:
            logger.error("LLMProvider not initialized")
            return False

        success = self.llm_provider.set_current_config(config_id)

        # 更新当前对话的LLM模型
        if success and self.current_conversation:
            self.current_conversation.llm_model = config_id
            logger.info(f"Updated conversation LLM model to: {config_id}")

        return success

    def get_all_llm_configs(self) -> dict[str, LLMConfig]:
        """获取所有LLM配置

        Returns:
            字典，键为配置名称，值为LLMConfig对象

        """
        if not self.llm_provider:
            return {}

        all_configs = self.llm_provider.get_all_configs()
        return {name: config.config for name, config in all_configs.items()}

    def get_llm_config(self, config_name: str) -> LLMConfig | None:
        """获取指定名称的LLM配置

        Args:
            config_name: 配置名称

        Returns:
            LLMConfig对象，如果未找到则返回None

        """
        if not self.llm_provider:
            return None

        provider_config = self.llm_provider.get_config(config_name)
        return provider_config.config if provider_config else None

    def get_mode_llm_config(self, mode: str) -> LLMConfig | None:
        """获取模式特定的LLM配置

        Args:
            mode: 模式名称（如"code", "ask"等）

        Returns:
            LLMConfig对象，如果未配置则返回None

        """
        if not self.llm_provider:
            return None

        provider_config = self.llm_provider.get_mode_config(mode)
        return provider_config.config if provider_config else None

    def set_mode_llm_config(self, mode: str, config_name: str) -> bool:
        """设置模式特定的LLM配置

        Args:
            mode: 模式名称
            config_name: LLM配置名称

        Returns:
            设置成功返回True，失败返回False

        """
        if not self.llm_provider:
            logger.error("LLMProvider not initialized")
            return False

        return self.llm_provider.set_mode_config(mode, config_name)

    # ==================== 统计信息 ====================

    def get_statistics(self) -> dict:
        """获取LLM配置统计信息

        Returns:
            包含统计信息的字典

        """
        if not self.llm_provider:
            return {}

        return self.llm_provider.get_statistics()
