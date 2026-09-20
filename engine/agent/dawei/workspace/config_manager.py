# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Configuration Manager

管理工作区配置的加载、保存和验证
"""

import json
import logging
from pathlib import Path
from typing import Any

from dawei.logg.logging import get_logger

logger = get_logger(__name__)


class ConfigurationValidator:
    """配置验证器 - Fast Fail 原则"""

    @staticmethod
    def validate_workspace_config(config: dict) -> tuple[bool, str | None]:
        """验证工作区配置

        Args:
            config: 配置字典

        Returns:
            (is_valid, error_message)

        """
        # Fast Fail: 检查必需字段
        required_fields = ["id", "name", "path"]
        for field in required_fields:
            if field not in config:
                return False, f"Missing required field: {field}"

        # Fast Fail: 验证字段类型
        if not isinstance(config["id"], str):
            return False, "Field 'id' must be a string"
        if not isinstance(config["name"], str):
            return False, "Field 'name' must be a string"
        if not isinstance(config["path"], str):
            return False, "Field 'path' must be a string"

        return True, None

    @staticmethod
    def validate_settings(settings: dict) -> tuple[bool, str | None]:
        """验证设置配置

        Args:
            settings: 设置字典

        Returns:
            (is_valid, error_message)

        """
        if not isinstance(settings, dict):
            return False, "Settings must be a dictionary"

        # 验证可选字段类型
        if "defaultMode" in settings and not isinstance(settings["defaultMode"], str):
            return False, "Field 'defaultMode' must be a string"

        if "defaultLLM" in settings and not isinstance(settings["defaultLLM"], str):
            return False, "Field 'defaultLLM' must be a string"

        return True, None


class ConfigurationFileManager:
    """配置文件管理器

    负责配置文件的读写操作
    """

    def __init__(self, workspace_path: Path):
        """初始化配置文件管理器

        Args:
            workspace_path: 工作区路径

        """
        self.workspace_path = workspace_path
        self.user_config_dir = workspace_path / ".dawei"
        self.settings_file = self.user_config_dir / "settings.json"
        self.workspace_info_file = workspace_path / ".dawei" / "workspace.json"
        self.logger = get_logger(__name__)

    def ensure_config_directories(self):
        """确保配置目录存在"""
        try:
            self.user_config_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Config directory ensured: {self.user_config_dir}")
        except OSError as e:
            self.logger.error(f"Failed to create config directory: {e}", exc_info=True)
            raise

    def read_workspace_info(self) -> dict | None:
        """读取工作区信息

        Returns:
            工作区信息字典，如果文件不存在返回 None

        Raises:
            IOError: 读取失败
            ValueError: JSON 格式无效

        """
        if not self.workspace_info_file.exists():
            self.logger.info(f"Workspace info file not found: {self.workspace_info_file}")
            return None

        try:
            with self.workspace_info_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            # Fast Fail: 验证配置
            is_valid, error_msg = ConfigurationValidator.validate_workspace_config(data)
            if not is_valid:
                raise ValueError(f"Invalid workspace config: {error_msg}")

            self.logger.info(f"Loaded workspace info from {self.workspace_info_file}")
            return data

        except (OSError, json.JSONDecodeError) as e:
            self.logger.error(f"Failed to read workspace info: {e}", exc_info=True)
            raise

    def write_workspace_info(self, info: dict):
        """写入工作区信息

        Args:
            info: 工作区信息字典

        Raises:
            IOError: 写入失败
            ValueError: 配置无效

        """
        try:
            # Fast Fail: 验证配置
            is_valid, error_msg = ConfigurationValidator.validate_workspace_config(info)
            if not is_valid:
                raise ValueError(f"Invalid workspace config: {error_msg}")

            # 确保目录存在
            self.ensure_config_directories()

            # 写入文件
            with self.workspace_info_file.open("w", encoding="utf-8") as f:
                json.dump(info, f, indent=2, ensure_ascii=False)

            self.logger.info(f"Saved workspace info to {self.workspace_info_file}")

        except (OSError, ValueError) as e:
            self.logger.error(f"Failed to write workspace info: {e}", exc_info=True)
            raise

    def read_settings(self) -> dict | None:
        """读取设置

        Returns:
            设置字典，如果文件不存在返回 None

        Raises:
            IOError: 读取失败
            ValueError: JSON 格式无效

        """
        if not self.settings_file.exists():
            self.logger.info(f"Settings file not found: {self.settings_file}")
            return None

        try:
            with self.settings_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            # Fast Fail: 验证设置
            is_valid, error_msg = ConfigurationValidator.validate_settings(data)
            if not is_valid:
                raise ValueError(f"Invalid settings: {error_msg}")

            self.logger.info(f"Loaded settings from {self.settings_file}")
            return data

        except (OSError, json.JSONDecodeError) as e:
            self.logger.error(f"Failed to read settings: {e}", exc_info=True)
            raise

    def write_settings(self, settings: dict):
        """写入设置

        Args:
            settings: 设置字典

        Raises:
            IOError: 写入失败
            ValueError: 设置无效

        """
        try:
            # Fast Fail: 验证设置
            is_valid, error_msg = ConfigurationValidator.validate_settings(settings)
            if not is_valid:
                raise ValueError(f"Invalid settings: {error_msg}")

            # 确保目录存在
            self.ensure_config_directories()

            # 写入文件
            with self.settings_file.open("w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)

            self.logger.info(f"Saved settings to {self.settings_file}")

        except (OSError, ValueError) as e:
            self.logger.error(f"Failed to write settings: {e}", exc_info=True)
            raise

    def backup_settings(self):
        """备份当前设置"""
        if not self.settings_file.exists():
            return

        try:
            backup_file = self.settings_file.with_suffix(".bak")
            backup_file.write_text(self.settings_file.read_text(encoding="utf-8"), encoding="utf-8")
            self.logger.info(f"Settings backed up to {backup_file}")
        except OSError as e:
            self.logger.warning(f"Failed to backup settings: {e}", exc_info=True)
