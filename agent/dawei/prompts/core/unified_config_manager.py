# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""统一配置管理器

整合原有的配置管理功能，提供统一的配置接口。
"""

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from dawei.entity.mode import ModeConfig

logger = logging.getLogger(__name__)


@dataclass
class LanguageConfig:
    """语言配置"""

    name: str
    code: str
    sections: dict[str, dict[str, Any]] = field(default_factory=dict)
    custom_variables: dict[str, Any] = field(default_factory=dict)


class UnifiedConfigManager:
    """统一配置管理器

    整合原有的 ConfigManager 和 ConfigManagerSimple 功能，
    提供统一的配置接口。
    """

    def __init__(self, config_path: str | None = None):
        """初始化统一配置管理器

        Args:
            config_path: 配置文件目录路径

        """
        # 获取默认路径
        base_path = Path(__file__).parent.parent.parent
        self.config_path = Path(config_path or base_path / "prompts" / "config")

        # 配置缓存
        self.template_config: dict[str, Any] = {}
        self.mode_configs: dict[str, ModeConfig] = {}
        self.language_configs: dict[str, LanguageConfig] = {}

        # 线程锁
        self._lock = threading.RLock()

        # 加载配置
        self._load_all_configs()

    def _load_all_configs(self) -> None:
        """加载所有配置文件"""
        with self._lock:
            # 加载模板配置
            self._load_template_config()

            # 加载模式配置
            self._load_mode_configs()

            # 加载语言配置
            self._load_language_configs()

            logger.info("All configurations loaded successfully")

    def _load_template_config(self) -> None:
        """加载模板配置"""
        config_file = self.config_path / "template_config.yaml"

        if not config_file.exists():
            # 创建默认配置
            self.template_config = self._get_default_template_config()
            self._save_template_config()
        else:
            with Path(config_file).open(encoding="utf-8") as f:
                self.template_config = yaml.safe_load(f) or {}

            # 合并默认配置
            default_config = self._get_default_template_config()
            self.template_config = {**default_config, **self.template_config}

    def _get_default_template_config(self) -> dict[str, Any]:
        """获取默认模板配置"""
        return {
            "templates": {
                "base_path": "templates/base/",
                "modes_path": "templates/modes/",
                "languages_path": "templates/languages/",
                "sections_path": "templates/sections/",
            },
            "cache": {"enabled": True, "ttl": 3600, "max_size": 100},
            "rendering": {
                "auto_escape": True,
                "strict_undefined": False,
                "trim_blocks": True,
                "lstrip_blocks": True,
                "keep_trailing_newline": False,
            },
            "features": {"hot_reload": False, "debug_mode": False},
        }

    def _save_template_config(self) -> None:
        """保存模板配置"""
        config_file = self.config_path / "template_config.yaml"
        self.config_path.mkdir(parents=True, exist_ok=True)
        with config_file.open("w", encoding="utf-8") as f:
            yaml.dump(
                self.template_config,
                f,
                default_flow_style=False,
                allow_unicode=True,
                indent=2,
            )

    def _load_mode_configs(self) -> None:
        """加载模式配置"""
        mode_configs_dir = self.config_path / "mode_configs"

        if not mode_configs_dir.exists():
            mode_configs_dir.mkdir(parents=True, exist_ok=True)
            # 创建默认模式配置
            self._create_default_mode_configs()

        # 加载所有模式配置文件
        for config_file in mode_configs_dir.glob("*.yaml"):
            with Path(config_file).open(encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}

            mode_config = self._parse_mode_config(config_data)
            if mode_config:
                self.mode_configs[mode_config.slug] = mode_config
                logger.debug(f"Loaded mode config: {mode_config.slug}")

    def _parse_mode_config(self, config_data: dict[str, Any]) -> ModeConfig | None:
        """解析模式配置"""
        mode_config = config_data.get("mode", {})
        return ModeConfig(
            slug=mode_config.get("slug", ""),
            name=mode_config.get("name", ""),
            role_definition=mode_config.get("role_definition", ""),
            when_to_use=mode_config.get("when_to_use", ""),
            description=mode_config.get("description", ""),
            groups=mode_config.get("groups", []),
            source=mode_config.get("source", ""),
            custom_instructions=mode_config.get("custom_instructions", ""),
            rules=mode_config.get("rules", {}),
        )

    def _create_default_mode_configs(self) -> None:
        """创建默认模式配置"""
        default_modes = [
            {
                "slug": "orchestrator",
                "name": "Orchestrator",
                "description": "协调器模式，用于复杂多步骤项目的协调管理，使用 DAG 任务图管理任务依赖",
                "role_definition": "You are Roo, a strategic workflow orchestrator who excels at breaking down complex tasks into manageable subtasks with proper dependency management. You have deep understanding of task graphs, DAG structures, and how to coordinate specialized modes to accomplish complex objectives efficiently.",
            },
            {
                "slug": "code",
                "name": "Code",
                "description": "代码模式，用于编写、修改和重构代码",
                "role_definition": "You are a skilled software engineer who can write, modify, and refactor code across multiple programming languages.",
            },
            {
                "slug": "ask",
                "name": "Ask",
                "description": "问答模式，用于回答问题和提供解释",
                "role_definition": "You are a knowledgeable assistant who can answer questions and provide clear explanations on various topics.",
            },
            {
                "slug": "debug",
                "name": "Debug",
                "description": "调试模式，用于系统性分析和解决问题",
                "role_definition": "You are a systematic debugger who can analyze issues and identify root causes through methodical investigation.",
            },
        ]

        for mode_data in default_modes:
            config_file = self.config_path / "mode_configs" / f"{mode_data['slug']}.yaml"
            if not config_file.exists():
                config = {
                    "mode": {
                        **mode_data,
                        "when_to_use": "",
                        "groups": [],
                        "source": "default",
                        "custom_instructions": "",
                        "rules": {},
                    },
                }

                with config_file.open("w", encoding="utf-8") as f:
                    yaml.dump(
                        config,
                        f,
                        default_flow_style=False,
                        allow_unicode=True,
                        indent=2,
                    )

    def _load_language_configs(self) -> None:
        """加载语言配置"""
        language_configs_dir = self.config_path / "language_configs"

        if not language_configs_dir.exists():
            language_configs_dir.mkdir(parents=True, exist_ok=True)
            # 创建默认语言配置
            self._create_default_language_configs()

        # 加载所有语言配置文件
        for config_file in language_configs_dir.glob("*.yaml"):
            with Path(config_file).open(encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}

            language_config = self._parse_language_config(config_data)
            if language_config:
                self.language_configs[language_config.code] = language_config
                logger.debug(f"Loaded language config: {language_config.code}")

    def _parse_language_config(self, config_data: dict[str, Any]) -> LanguageConfig | None:
        """解析语言配置"""
        language_config = config_data.get("language", {})
        return LanguageConfig(
            name=language_config.get("name", ""),
            code=language_config.get("code", ""),
            sections=language_config.get("sections", {}),
            custom_variables=language_config.get("custom_variables", {}),
        )

    def _create_default_language_configs(self) -> None:
        """创建默认语言配置"""
        default_languages = [
            {"code": "zh-CN", "name": "简体中文"},
            {"code": "en", "name": "English"},
        ]

        for lang_data in default_languages:
            config_file = self.config_path / "language_configs" / f"{lang_data['code']}.yaml"
            if not config_file.exists():
                config = {"language": {**lang_data, "sections": {}, "custom_variables": {}}}

                with config_file.open("w", encoding="utf-8") as f:
                    yaml.dump(
                        config,
                        f,
                        default_flow_style=False,
                        allow_unicode=True,
                        indent=2,
                    )

    def get_template_config(self) -> dict[str, Any]:
        """获取模板配置

        Returns:
            Dict[str, Any]: 模板配置

        """
        return self.template_config.copy()

    def get_mode_config(self, mode: str) -> ModeConfig | None:
        """获取模式配置

        Args:
            mode: 模式名称

        Returns:
            Optional[ModeConfig]: 模式配置，不存在时返回None

        """
        return self.mode_configs.get(mode)

    def get_language_config(self, language: str) -> LanguageConfig | None:
        """获取语言配置

        Args:
            language: 语言代码

        Returns:
            Optional[LanguageConfig]: 语言配置，不存在时返回None

        """
        return self.language_configs.get(language)

    def get_all_modes(self) -> list[str]:
        """获取所有可用模式

        Returns:
            List[str]: 模式名称列表

        """
        return list(self.mode_configs.keys())

    def get_all_languages(self) -> list[str]:
        """获取所有可用语言

        Returns:
            List[str]: 语言代码列表

        """
        return list(self.language_configs.keys())

    def reload_config(self) -> None:
        """重新加载配置"""
        with self._lock:
            self._load_all_configs()
            logger.info("Configuration reloaded successfully")

    def validate_config(self) -> list[str]:
        """验证配置

        Returns:
            List[str]: 验证错误列表，空列表表示验证通过

        """
        errors = []

        # 验证模板配置
        if not self.template_config:
            errors.append("Template config is missing")

        # 验证模式配置
        for mode, config in self.mode_configs.items():
            if not config.name:
                errors.append(f"Mode {mode} missing name")
            if not config.slug:
                errors.append(f"Mode {mode} missing slug")

        # 验证语言配置
        for lang, config in self.language_configs.items():
            if not config.name:
                errors.append(f"Language {lang} missing name")
            if not config.code:
                errors.append(f"Language {lang} missing code")

        return errors

    def close(self) -> None:
        """关闭配置管理器，清理资源"""
        logger.info("UnifiedConfigManager closed")
