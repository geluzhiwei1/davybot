# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""模式管理器 - 重构版本
支持三级配置加载：builtin, user, workspace
使用统一的模式定义格式：modes 有 mode 列表，.dawei 目录下是自定义的 rules markdown 文件
"""

import logging
from datetime import UTC, datetime, timezone
from pathlib import Path

import yaml

from dawei.entity.mode import ModeConfig

logger = logging.getLogger(__name__)


class ModeConfigLoader:
    """模式配置加载器 - 重构版本"""

    def __init__(self):
        self._cache: dict[str, dict[str, ModeConfig]] = {}
        self._cache_timestamps: dict[str, datetime] = {}
        # 从配置系统读取缓存TTL，默认5分钟
        from dawei.config.settings import get_settings

        settings = get_settings()
        self._cache_ttl = settings.agent_execution.mode_cache_ttl

    def _get_cache_key(self, level: str, path: str | None = None) -> str:
        """获取缓存键"""
        return f"{level}:{path or 'default'}"

    def _is_cache_valid(self, cache_key: str) -> bool:
        """检查缓存是否有效"""
        if cache_key not in self._cache_timestamps:
            return False

        age = (datetime.now(UTC) - self._cache_timestamps[cache_key]).total_seconds()
        return age < self._cache_ttl

    def _set_cache(self, cache_key: str, configs: dict[str, ModeConfig]):
        """设置缓存"""
        self._cache[cache_key] = configs
        self._cache_timestamps[cache_key] = datetime.now(UTC)

    def _get_cache(self, cache_key: str) -> dict[str, ModeConfig] | None:
        """获取缓存"""
        if self._is_cache_valid(cache_key):
            return self._cache.get(cache_key)
        return None

    def _load_modes_from_directory(self, config_dir: Path, level: str) -> dict[str, ModeConfig]:
        """通用的模式加载函数，从指定目录加载模式配置

        Args:
            config_dir: 配置目录路径
            level: 配置级别 (builtin/user/workspace)

        Returns:
            Dict[str, ModeConfig]: 加载的模式配置

        """
        if not config_dir.exists():
            logger.debug(f"{level.title()} config directory not found: {config_dir}")
            return {}

        cache_key = self._get_cache_key(level, str(config_dir))
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        modes = {}

        # 先加载 rules-* 规则目录
        # 对于 builtin: config_dir = builtin/configs, 查找 rules-*
        # 对于 user: config_dir = ~/.dawei/configs, 查找 rules-*
        if config_dir.exists():
            modes.update(self._load_dawei_directory(config_dir))

        # 然后加载 modes 文件（这样可以覆盖规则加载器创建的默认配置）
        # 对于 builtin: config_dir/modes.yaml = builtin/configs/modes.yaml
        # 对于 user: config_dir/modes.yaml = ~/.dawei/configs/modes.yaml
        modes_file = config_dir / "modes.yaml"
        if modes_file.exists():
            modes.update(self._load_modes_file(modes_file, modes))

        self._set_cache(cache_key, modes)
        logger.info(f"Loaded {len(modes)} {level} modes from {config_dir}")
        return modes

    def load_builtin_modes(self) -> dict[str, ModeConfig]:
        """加载内置模式"""
        # 获取 builtin/configs 目录路径（与 user 级别保持一致）
        builtin_dir = Path(__file__).parent / "builtin" / "configs"
        return self._load_modes_from_directory(builtin_dir, "builtin")

    def load_user_modes(self) -> dict[str, ModeConfig]:
        """加载用户级模式配置"""
        user_home = Path.home()
        user_config_dir = user_home / ".dawei" / "configs"
        return self._load_modes_from_directory(user_config_dir, "user")

    def load_workspace_modes(self, workspace_path: str) -> dict[str, ModeConfig]:
        """加载工作区级模式配置"""
        workspace_dir = Path(workspace_path)
        workspace_config_dir = workspace_dir / ".dawei"
        return self._load_modes_from_directory(workspace_config_dir, "workspace")

    def _load_modes_file(
        self,
        file_path: Path,
        existing_modes: dict[str, ModeConfig] | None = None,
    ) -> dict[str, ModeConfig]:
        """加载 modes 文件"""
        modes = {}
        try:
            with Path(file_path).open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError:
            logger.exception("YAML parsing error in {file_path}: ")
            return {}

        if data and "customModes" in data and data["customModes"]:
            # 确保 customModes 是一个列表
            custom_modes = data["customModes"]
            if isinstance(custom_modes, list):
                for mode_data in custom_modes:
                    if mode_data and "slug" in mode_data:
                        mode_config = ModeConfig.from_dict(mode_data)
                        # 如果已存在该模式，保留其规则
                        if existing_modes and mode_config.slug in existing_modes:
                            mode_config.rules = existing_modes[mode_config.slug].rules
                        modes[mode_config.slug] = mode_config
            else:
                logger.warning(f"customModes in {file_path} is not a list: {type(custom_modes)}")

        logger.debug(f"Loaded {len(modes)} modes from {file_path}")

        return modes

    def _load_dawei_directory(self, dawei_dir: Path) -> dict[str, ModeConfig]:
        """加载 .dawei 目录下的规则"""
        modes = {}

        # 查找 rules-{mode} 目录
        for rules_dir in dawei_dir.glob("rules-*"):
            mode_slug = rules_dir.name.replace("rules-", "")
            rules_files = list(rules_dir.glob("*.md"))

            if rules_files:
                try:
                    rules_dict = {}
                    # 从多个 .md 文件加载规则
                    for rules_file in rules_files:
                        with Path(rules_file).open(encoding="utf-8") as f:
                            rules_content = f.read()
                        # 使用文件名（不含扩展名）作为 key
                        file_key = rules_file.stem
                        rules_dict[file_key] = rules_content
                        logger.debug(
                            f"Loaded rules file {file_key} for mode {mode_slug} from {rules_file}",
                        )

                    # 如果模式已存在，添加规则；否则创建新模式
                    if mode_slug in modes:
                        existing_config = modes[mode_slug]
                        # 合并规则到现有配置
                        existing_config.rules.update(rules_dict)
                        modes[mode_slug] = existing_config
                    else:
                        # 创建一个临时的模式配置，等待 modes 文件来覆盖
                        mode_config = ModeConfig(
                            slug=mode_slug,
                            name=mode_slug.replace("-", " ").title(),
                            description=f"Custom mode: {mode_slug}",
                            role_definition="",
                            when_to_use="",
                            groups=[],
                            source="custom",
                            custom_instructions="",
                            rules=rules_dict,
                        )
                        modes[mode_slug] = mode_config

                    logger.debug(f"Loaded {len(rules_dict)} rules files for mode {mode_slug}")

                except (OSError, UnicodeDecodeError):
                    logger.exception("Failed to load rules from {rules_dir}: ")
                except yaml.YAMLError:
                    logger.exception("Failed to parse YAML rules from {rules_dir}: ")
                except KeyError:
                    logger.exception("Missing required key in rules from {rules_dir}: ")
                except ValueError:
                    logger.exception("Invalid value in rules from {rules_dir}: ")

        return modes

    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.info("Mode config cache cleared")

    def set_cache_ttl(self, ttl_seconds: int):
        """设置缓存TTL

        Args:
            ttl_seconds: 缓存过期时间（秒）
        """
        if ttl_seconds < 60:
            logger.warning(f"Cache TTL too small ({ttl_seconds}s), using minimum 60s")
            ttl_seconds = 60
        self._cache_ttl = ttl_seconds
        logger.info(f"Mode config cache TTL set to {ttl_seconds}s")


class ModeManager:
    """模式管理器 - 重构版本"""

    def __init__(self, workspace_path: str | None = None):
        self.loader = ModeConfigLoader()
        self.workspace_path = workspace_path

        # 三级配置缓存
        self._builtin_modes: dict[str, ModeConfig] = {}
        self._user_modes: dict[str, ModeConfig] = {}
        self._workspace_modes: dict[str, ModeConfig] = {}

        # 合并后的模式配置
        self._merged_modes: dict[str, ModeConfig] = {}

        # 初始化配置
        self._load_all_configs()

    def _load_all_configs(self):
        """加载所有级别的配置"""
        # 按优先级顺序加载
        self._builtin_modes = self.loader.load_builtin_modes()
        self._user_modes = self.loader.load_user_modes()

        if self.workspace_path:
            self._workspace_modes = self.loader.load_workspace_modes(self.workspace_path)

        # 合并配置
        self._merge_configs()

        logger.info(f"ModeManager initialized with {len(self._merged_modes)} total modes")

    def _merge_configs(self):
        """合并三级配置，支持同名 slug 的完全覆盖"""
        self._merged_modes.clear()

        # 按优先级顺序合并：builtin -> user -> workspace
        # 后面的会完全覆盖前面的同名配置

        # 1. 从 builtin 开始
        for slug, config in self._builtin_modes.items():
            self._merged_modes[slug] = config

        # 2. 合并 user 配置（完全覆盖）
        for slug, config in self._user_modes.items():
            self._merged_modes[slug] = config

        # 3. 合并 workspace 配置（完全覆盖）
        for slug, config in self._workspace_modes.items():
            self._merged_modes[slug] = config

        logger.debug(f"Merged configurations: {len(self._merged_modes)} modes")

    def set_workspace_path(self, workspace_path: str):
        """设置工作区路径并重新加载配置"""
        self.workspace_path = workspace_path
        self._workspace_modes = self.loader.load_workspace_modes(workspace_path)
        self._merge_configs()
        logger.info(f"Workspace path set to {workspace_path}, configs reloaded")

    def get_mode_info(self, mode_slug: str) -> ModeConfig:
        """获取模式信息，包含规则"""
        if mode_slug in self._merged_modes:
            return self._merged_modes[mode_slug]
        # 返回默认模式信息，符合新的字段结构
        return ModeConfig(
            slug=mode_slug,
            name=mode_slug,
            role_definition=f"You are operating in {mode_slug} mode.",
            when_to_use="",
            description=f"Mode: {mode_slug}",
            groups=[],
            source="default",
            custom_instructions=f"You are operating in {mode_slug} mode.",
            rules={},
        )

    def get_all_modes(self) -> dict[str, ModeConfig]:
        """获取所有可用模式，包含规则"""
        return dict(self._merged_modes.items())

    def is_valid_mode(self, mode_slug: str) -> bool:
        """检查模式是否有效"""
        return mode_slug in self._merged_modes

    def get_mode_groups(self, mode_slug: str) -> list[str]:
        """获取模式所属的工具组"""
        mode_info = self.get_mode_info(mode_slug)
        return getattr(mode_info, "groups", [])

    def reload_configs(self):
        """重新加载所有配置"""
        self.loader.clear_cache()
        self._load_all_configs()
        logger.info("All mode configurations reloaded")

    def get_config_sources(self, mode_slug: str) -> dict[str, bool]:
        """获取模式配置来源信息"""
        return {
            "builtin": mode_slug in self._builtin_modes,
            "user": mode_slug in self._user_modes,
            "workspace": mode_slug in self._workspace_modes,
        }

    def get_mode_by_level(self, mode_slug: str, level: str) -> ModeConfig | None:
        """获取指定级别的模式配置"""
        level_configs = {
            "builtin": self._builtin_modes,
            "user": self._user_modes,
            "workspace": self._workspace_modes,
        }

        return level_configs.get(level, {}).get(mode_slug)

    def get_provider_for_mode(self, mode: str) -> str | None:
        """获取与指定模式关联的 LLM 提供者名称

        Args:
            mode: 模式名称

        Returns:
            LLM 提供者名称，如果没有关联的提供者则返回 None

        """
        # 获取模式信息
        mode_info = self.get_mode_info(mode)

        # 检查模式信息中是否有关联的 LLM 提供者
        if hasattr(mode_info, "llm_provider") and mode_info.llm_provider:
            return mode_info.llm_provider

        # 如果模式信息中没有直接指定提供者，返回 None
        # 调用方需要使用其他逻辑来确定合适的提供者
        return None
