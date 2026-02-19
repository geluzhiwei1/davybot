# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""模式管理器 - 重构版本
支持三级配置加载：builtin, user, workspace
使用统一的模式定义格式：modes 有 mode 列表，.dawei 目录下是自定义的 rules markdown 文件
"""

import logging
import os
from datetime import UTC, datetime, timezone
from pathlib import Path

import yaml

from dawei.config import get_workspaces_root
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
        # 对于 builtin: config_dir = builtin/agents, 查找 rules-*
        # 对于 user: config_dir = ~/.dawei/agents, 查找 rules-*
        if config_dir.exists():
            modes.update(self._load_dawei_directory(config_dir))

        # 然后加载 modes 文件（这样可以覆盖规则加载器创建的默认配置）
        # 对于 builtin: config_dir/modes.yaml = builtin/agents/modes.yaml
        # 对于 user: config_dir/modes.yaml = ~/.dawei/agents/modes.yaml
        modes_file = config_dir / "modes.yaml"
        if modes_file.exists():
            modes.update(self._load_modes_file(modes_file, modes))

        self._set_cache(cache_key, modes)
        logger.info(f"Loaded {len(modes)} {level} modes from {config_dir}")
        return modes

    def load_builtin_modes(self) -> dict[str, ModeConfig]:
        """加载内置模式"""
        # 获取 builtin/agents 目录路径（与 user 级别保持一致）
        builtin_dir = Path(__file__).parent / "builtin" / "agents"
        return self._load_modes_from_directory(builtin_dir, "builtin")

    def load_user_modes(self) -> dict[str, ModeConfig]:
        """加载用户级模式配置"""
        user_config_dir = Path(get_workspaces_root()) / "agents"
        return self._load_modes_from_directory(user_config_dir, "user")

    def load_workspace_modes(self, workspace_path: str) -> dict[str, ModeConfig]:
        """加载工作区级模式配置

        支持两个加载路径：
        1. {workspace}/.dawei/agents/ - 直接存放的 agents
        2. {workspace}/.dawei/agents/{team-name}/ - 团队目录下的 agents

        Args:
            workspace_path: 工作区路径

        Returns:
            Dict[str, ModeConfig]: 加载的模式配置
        """
        workspace_dir = Path(workspace_path)
        modes = {}

        # 路径1: {workspace}/.dawei/agents/
        agents_dir = workspace_dir / ".dawei" / "agents"
        if agents_dir.exists():
            modes.update(self._load_modes_from_directory(agents_dir, "workspace"))

        # 路径2: {workspace}/.dawei/agents/{team-name}/
        # 扫描所有团队目录
        if agents_dir.exists():
            for team_dir in agents_dir.iterdir():
                if team_dir.is_dir() and not team_dir.name.startswith('.'):
                    # 加载团队目录下的 modes
                    team_modes = self._load_modes_from_directory(team_dir, "workspace")
                    modes.update(team_modes)
                    logger.debug(f"Loaded {len(team_modes)} modes from team directory: {team_dir.name}")

        return modes

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
                        # 使用文件名（含扩展名）作为 key
                        file_key = rules_file.name
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

    def delete_mode(self, mode_slug: str, level: str = "workspace") -> bool:
        """删除指定级别的自定义模式

        Args:
            mode_slug: 要删除的模式 slug
            level: 配置级别 ("user" 或 "workspace"，默认 "workspace")

        Returns:
            bool: 删除成功返回 True，失败返回 False

        Raises:
            ValueError: 如果尝试删除内置模式或级别无效
            OSError: 如果文件系统操作失败

        """
        # 验证级别
        if level not in ("user", "workspace"):
            raise ValueError(f"Invalid level: {level}. Must be 'user' or 'workspace'")

        # 检查是否为内置模式
        if mode_slug in self._builtin_modes:
            raise ValueError(f"Cannot delete builtin mode: {mode_slug}")

        # 确定配置目录
        if level == "user":
            config_dir = Path(get_workspaces_root()) / "agents"
        else:  # workspace
            if not self.workspace_path:
                raise ValueError("Workspace path not set for workspace-level mode deletion")
            config_dir = Path(self.workspace_path) / ".dawei" / "agents"

        # 删除规则目录 (rules-{mode_slug})
        rules_dir = config_dir / f"rules-{mode_slug}"
        if rules_dir.exists():
            import shutil

            shutil.rmtree(rules_dir)
            logger.info(f"Deleted rules directory: {rules_dir}")

        # 从 modes.yaml 中删除模式定义（支持 customModes 和直接列表）
        modes_file = config_dir / "modes.yaml"
        mode_removed = False

        if modes_file.exists():
            try:
                with modes_file.open(encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}

                # 处理 customModes 格式
                if "customModes" in data and isinstance(data["customModes"], list):
                    # 过滤掉要删除的模式
                    original_count = len(data["customModes"])
                    data["customModes"] = [
                        mode for mode in data["customModes"]
                        if mode.get("slug") != mode_slug
                    ]

                    # 如果有删除，写回文件
                    if len(data["customModes"]) < original_count:
                        with modes_file.open("w", encoding="utf-8") as f:
                            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
                        logger.info(f"Removed mode {mode_slug} from customModes in {modes_file}")
                        mode_removed = True
                    else:
                        logger.debug(f"Mode {mode_slug} not found in customModes in {modes_file}")

                # 处理直接列表格式（市场安装的代理可能使用这种格式）
                elif isinstance(data, list):
                    original_count = len(data)
                    data = [mode for mode in data if mode.get("slug") != mode_slug]

                    if len(data) < original_count:
                        with modes_file.open("w", encoding="utf-8") as f:
                            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
                        logger.info(f"Removed mode {mode_slug} from modes list in {modes_file}")
                        mode_removed = True
                    else:
                        logger.debug(f"Mode {mode_slug} not found in modes list in {modes_file}")

            except (yaml.YAMLError, OSError) as e:
                logger.error(f"Failed to update modes file {modes_file}: {e}")
                raise

        # 如果在主 modes.yaml 中没有找到，检查市场安装的代理包
        if not mode_removed and config_dir.exists():
            for agent_dir in config_dir.iterdir():
                if agent_dir.is_dir() and (agent_dir / "modes.yaml").exists():
                    agent_modes_file = agent_dir / "modes.yaml"
                    try:
                        with agent_modes_file.open(encoding="utf-8") as f:
                            agent_data = yaml.safe_load(f) or {}

                        # 检查 customModes 格式
                        if isinstance(agent_data, dict) and "customModes" in agent_data:
                            custom_modes = agent_data["customModes"]
                            if isinstance(custom_modes, list):
                                original_count = len(custom_modes)
                                agent_data["customModes"] = [
                                    mode for mode in custom_modes
                                    if mode.get("slug") != mode_slug
                                ]

                                if len(agent_data["customModes"]) < original_count:
                                    with agent_modes_file.open("w", encoding="utf-8") as f:
                                        yaml.dump(agent_data, f, allow_unicode=True, default_flow_style=False)
                                    logger.info(f"Removed mode {mode_slug} from market agent package customModes: {agent_modes_file}")
                                    mode_removed = True
                                    break

                        # 检查是否是直接列表格式
                        elif isinstance(agent_data, list):
                            original_count = len(agent_data)
                            agent_data = [mode for mode in agent_data if mode.get("slug") != mode_slug]

                            if len(agent_data) < original_count:
                                with agent_modes_file.open("w", encoding="utf-8") as f:
                                    yaml.dump(agent_data, f, allow_unicode=True, default_flow_style=False)
                                logger.info(f"Removed mode {mode_slug} from market agent package: {agent_modes_file}")
                                mode_removed = True
                                break
                    except Exception as e:
                        logger.warning(f"Failed to check agent package {agent_dir}: {e}")

        # 删除对应的 rules 目录（可能在市场包中）
        if not mode_removed and config_dir.exists():
            for agent_dir in config_dir.iterdir():
                if agent_dir.is_dir():
                    agent_rules_dir = agent_dir / f"rules-{mode_slug}"
                    if agent_rules_dir.exists():
                        import shutil
                        shutil.rmtree(agent_rules_dir)
                        logger.info(f"Deleted rules directory from market agent package: {agent_rules_dir}")
                        mode_removed = True
                        break

        # 清除缓存并重新加载配置
        self.loader.clear_cache()
        self._load_all_configs()

        if not mode_removed:
            logger.warning(f"Mode {mode_slug} was not found in any configuration files")

        logger.info(f"Successfully deleted mode {mode_slug} from {level} level")
        return True

    def update_mode(
        self,
        mode_slug: str,
        mode_data: dict,
        level: str = "workspace"
    ) -> ModeConfig:
        """更新指定级别的自定义模式

        Args:
            mode_slug: 要更新的模式 slug
            mode_data: 模式数据字典（包含 name, description, roleDefinition 等）
            level: 配置级别 ("user" 或 "workspace"，默认 "workspace")

        Returns:
            ModeConfig: 更新后的模式配置

        Raises:
            ValueError: 如果尝试更新内置模式或级别无效
            OSError: 如果文件系统操作失败

        """
        # 验证级别
        if level not in ("user", "workspace"):
            raise ValueError(f"Invalid level: {level}. Must be 'user' or 'workspace'")

        # 检查是否为内置模式
        if mode_slug in self._builtin_modes:
            raise ValueError(f"Cannot update builtin mode: {mode_slug}")

        # 确定配置目录
        if level == "user":
            config_dir = Path(get_workspaces_root()) / "agents"
        else:  # workspace
            if not self.workspace_path:
                raise ValueError("Workspace path not set for workspace-level mode update")
            config_dir = Path(self.workspace_path) / ".dawei" / "agents"

        # 确保配置目录存在
        config_dir.mkdir(parents=True, exist_ok=True)

        # 加载或创建 modes.yaml
        modes_file = config_dir / "modes.yaml"
        if modes_file.exists():
            try:
                with modes_file.open(encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except (yaml.YAMLError, OSError) as e:
                logger.error(f"Failed to load modes file {modes_file}: {e}")
                raise
        else:
            data = {"customModes": []}

        # 确保 customModes 存在
        if "customModes" not in data or not isinstance(data["customModes"], list):
            data["customModes"] = []

        # 查找并更新或添加模式
        mode_found = False
        for i, mode in enumerate(data["customModes"]):
            if isinstance(mode, dict) and mode.get("slug") == mode_slug:
                # 更新现有模式
                data["customModes"][i] = mode_data
                mode_found = True
                logger.info(f"Updating existing mode {mode_slug} in {modes_file}")
                break

        if not mode_found:
            # 添加新模式
            data["customModes"].append(mode_data)
            logger.info(f"Adding new mode {mode_slug} to {modes_file}")

        # 写回文件
        try:
            with modes_file.open("w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
            logger.info(f"Successfully updated modes file: {modes_file}")
        except (yaml.YAMLError, OSError) as e:
            logger.error(f"Failed to write modes file {modes_file}: {e}")
            raise

        # 清除缓存并重新加载配置
        self.loader.clear_cache()
        self._load_all_configs()

        # 返回更新后的配置
        return self._merged_modes.get(mode_slug)

    def update_mode_rules(
        self,
        mode_slug: str,
        rules_content: str,
        rules_filename: str = "mode",
        level: str = "workspace"
    ) -> bool:
        """更新指定级别的模式规则文件

        Args:
            mode_slug: 模式 slug
            rules_content: 规则内容（markdown 字符串）
            rules_filename: 规则文件名（默认 "mode"，会保存为 mode.md）
            level: 配置级别 ("user" 或 "workspace"，默认 "workspace")

        Returns:
            bool: 更新成功返回 True

        Raises:
            ValueError: 如果尝试更新内置模式的规则或级别无效
            OSError: 如果文件系统操作失败

        """
        # 验证级别
        if level not in ("user", "workspace"):
            raise ValueError(f"Invalid level: {level}. Must be 'user' or 'workspace'")

        # 检查是否为内置模式
        if mode_slug in self._builtin_modes:
            raise ValueError(f"Cannot update rules for builtin mode: {mode_slug}")

        # 确定配置目录
        if level == "user":
            config_dir = Path(get_workspaces_root()) / "agents"
        else:  # workspace
            if not self.workspace_path:
                raise ValueError("Workspace path not set for workspace-level mode update")
            config_dir = Path(self.workspace_path) / ".dawei" / "agents"

        # 创建或更新规则目录
        rules_dir = config_dir / f"rules-{mode_slug}"
        rules_dir.mkdir(parents=True, exist_ok=True)

        # 写入规则文件
        rules_file = rules_dir / f"{rules_filename}.md"
        try:
            with rules_file.open("w", encoding="utf-8") as f:
                f.write(rules_content)
            logger.info(f"Successfully updated rules file: {rules_file}")
        except OSError as e:
            logger.error(f"Failed to write rules file {rules_file}: {e}")
            raise

        # 清除缓存并重新加载配置
        self.loader.clear_cache()
        self._load_all_configs()

        return True

    def get_mode_rules(self, mode_slug: str, rules_filename: str = "mode") -> str | None:
        """获取模式的规则文件内容

        Args:
            mode_slug: 模式 slug
            rules_filename: 规则文件名（默认 "mode"，读取 mode.md）

        Returns:
            str | None: 规则文件内容，如果不存在返回 None

        """
        content, _ = self.get_mode_rules_with_path(mode_slug, rules_filename)
        return content

    def get_mode_rules_with_path(self, mode_slug: str, rules_filename: str = "mode") -> tuple[str | None, str | None]:
        """获取模式的规则文件内容和路径

        Args:
            mode_slug: 模式 slug
            rules_filename: 规则文件名（默认 "mode"，读取 mode.md）

        Returns:
            tuple[str | None, str | None]: (规则文件内容, 规则文件路径)，如果不存在返回 (None, None)

        """
        # 从合并后的配置中获取规则
        mode_info = self._merged_modes.get(mode_slug)
        if not mode_info or not mode_info.rules:
            return None, None

        # 返回指定的规则文件内容
        content = mode_info.rules.get(rules_filename)
        if content is None:
            return None, None

        # 查找规则文件的实际路径
        rules_path = self._find_rules_file_path(mode_slug, rules_filename)

        return content, rules_path

    def _find_rules_file_path(self, mode_slug: str, rules_filename: str) -> str | None:
        """查找规则文件的实际路径

        Args:
            mode_slug: 模式 slug
            rules_filename: 规则文件名

        Returns:
            str | None: 规则文件的绝对路径，如果找不到返回 None

        """
        # 构建可能的规则目录名称
        rules_dir_name = f"rules-{mode_slug}"
        rules_file_name = f"{rules_filename}.md"

        # 按优先级搜索：workspace > user > builtin
        search_paths = []

        # 1. 工作区级别的 agents 目录
        if self.workspace_path:
            workspace_agents = Path(self.workspace_path) / ".dawei" / "agents"
            # 工作区根目录的 rules-{mode}
            search_paths.append(workspace_agents / rules_dir_name / rules_file_name)
            # 市场包的 rules-{mode}
            if workspace_agents.exists():
                for agent_dir in workspace_agents.iterdir():
                    if agent_dir.is_dir():
                        search_paths.append(agent_dir / rules_dir_name / rules_file_name)

        # 2. 用户级别的 agents 目录
        user_agents = Path(get_workspaces_root()) / "agents"
        search_paths.append(user_agents / rules_dir_name / rules_file_name)
        # 用户级别的市场包
        if user_agents.exists():
            for agent_dir in user_agents.iterdir():
                if agent_dir.is_dir():
                    search_paths.append(agent_dir / rules_dir_name / rules_file_name)

        # 3. 内置模式
        builtin_agents = Path(__file__).parent / "builtin" / "agents"
        if builtin_agents.exists():
            search_paths.append(builtin_agents / rules_dir_name / rules_file_name)

        # 返回第一个存在的文件路径
        for path in search_paths:
            if path.exists() and path.is_file():
                return str(path.absolute())

        return None

    def _find_rules_directory(self, mode_slug: str) -> str | None:
        """查找规则目录的路径

        Args:
            mode_slug: 模式 slug

        Returns:
            str | None: 规则目录的绝对路径，如果找不到返回 None

        """
        # 构建可能的规则目录名称
        rules_dir_name = f"rules-{mode_slug}"

        # 按优先级搜索：workspace > user > builtin
        search_dirs = []

        # 1. 工作区级别的 agents 目录
        if self.workspace_path:
            workspace_agents = Path(self.workspace_path) / ".dawei" / "agents"
            # 工作区根目录的 rules-{mode}
            search_dirs.append(workspace_agents / rules_dir_name)
            # 市场包的 rules-{mode}
            if workspace_agents.exists():
                for agent_dir in workspace_agents.iterdir():
                    if agent_dir.is_dir():
                        search_dirs.append(agent_dir / rules_dir_name)

        # 2. 用户级别的 agents 目录
        user_agents = Path(get_workspaces_root()) / "agents"
        search_dirs.append(user_agents / rules_dir_name)
        # 用户级别的市场包
        if user_agents.exists():
            for agent_dir in user_agents.iterdir():
                if agent_dir.is_dir():
                    search_dirs.append(agent_dir / rules_dir_name)

        # 3. 内置模式
        builtin_agents = Path(__file__).parent / "builtin" / "agents"
        if builtin_agents.exists():
            search_dirs.append(builtin_agents / rules_dir_name)

        # 返回第一个存在的目录路径
        for dir_path in search_dirs:
            if dir_path.exists() and dir_path.is_dir():
                return str(dir_path.absolute())

        return None
