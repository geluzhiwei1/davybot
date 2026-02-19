# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Skills管理器 - 实现渐进式skills功能

支持渐进式加载：
1. Discovery - 读取frontmatter的name和description
2. Instructions - 加载完整SKILL.md内容
3. Resources - 访问额外资源文件

优先级（从高到低）：

"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """表示一个skill"""

    name: str
    description: str
    path: Path
    content: str | None = None  # 完整的SKILL.md内容（延迟加载）
    mode: str | None = None  # mode-specific skill
    scope: str = "global"  # "global" or "project"
    is_loaded: bool = False  # 是否已加载完整内容
    resources: list[Path] = field(default_factory=list)  # 额外资源文件

    def __hash__(self):
        return hash((self.name, self.mode, self.scope, self.path))

    def __eq__(self, other):
        if not isinstance(other, Skill):
            return False
        return (self.name, self.mode, self.scope, self.path) == (
            other.name,
            other.mode,
            other.scope,
            other.path,
        )

    def load_content(self) -> str:
        """加载完整的SKILL.md内容"""
        if self.is_loaded and self.content:
            return self.content

        try:
            with Path(self.path).open(encoding="utf-8") as f:
                self.content = f.read()
            self.is_loaded = True
            return self.content
        except Exception as e:
            logger.exception(f"Failed to load skill content from {self.path}: {e}")
            return ""

    def get_resources(self) -> dict[str, Path]:
        """获取skill目录下的所有资源文件"""
        if not self.resources:
            skill_dir = self.path.parent
            try:
                self.resources = [f for f in skill_dir.iterdir() if f.is_file() and f.name != "SKILL.md"]
            except OSError as e:
                logger.exception(f"Failed to list resources in skill directory {skill_dir}: {e}")
                self.resources = []
        return {f.stem: f for f in self.resources}


class SkillManager:
    """Skills管理器

    负责发现、管理和加载skills
    """

    def __init__(self, skills_roots: list[Path] | None = None, current_mode: str | None = None):
        """初始化SkillManager - 支持多级加载

        Args:
            skills_roots: 包含.dawei目录的根路径列表（优先级从高到低）
                          例如: [workspace_root, system_root, user_root]
            current_mode: 当前模式（用于mode-specific skills）

        """
        # 默认roots：全局user目录
        self.skills_roots = skills_roots or [Path.home()]
        self.current_mode = current_mode

        # skill注册表: name -> list[Skill]
        # 同一个name可能有多个Skill（不同scope/mode）
        self._skills: dict[str, list[Skill]] = {}

        # 是否已初始化
        self._initialized = False

    def discover_skills(self, force: bool = False) -> None:
        """发现所有skills（只读取frontmatter）

        支持三级加载机制：
        - UserWorkspace级别
        - System级别
        - Current User级别

        每个级别都尝试：
        - .dawei/configs/skills/
        - .dawei/configs/skills-{mode}/

        Args:
            force: 是否强制重新发现

        """
        if self._initialized and not force:
            return

        self._skills.clear()

        # 按优先级顺序遍历所有roots
        for priority, root in enumerate(self.skills_roots):
            logger.debug(f"Scanning skills root (priority {priority}): {root}")

            # 根据优先级确定scope
            if priority == 0:
                scope = "workspace"
            elif priority == len(self.skills_roots) - 1:
                scope = "user"
            else:
                scope = "system"

            # 1. 通用的 .dawei/skills/ (市场安装的技能)
            market_skills_dir = root / ".dawei" / "skills"
            if market_skills_dir.exists() and market_skills_dir.is_dir():
                self._discover_skills_in_dir(market_skills_dir, mode=None, scope=scope)

            # 2. Mode-specific .dawei/skills-{mode}/
            if self.current_mode:
                mode_skills_dir = root / ".dawei" / f"skills-{self.current_mode}"
                if mode_skills_dir.exists() and mode_skills_dir.is_dir():
                    self._discover_skills_in_dir(
                        mode_skills_dir,
                        mode=self.current_mode,
                        scope=scope,
                    )

        self._initialized = True
        logger.info(
            f"Discovered {len(self._skills)} unique skills from {len(self.skills_roots)} root(s)",
        )

    def _discover_skills_in_dir(self, skills_dir: Path, mode: str | None, scope: str) -> None:
        """在指定目录发现skills"""
        if not skills_dir.exists() or not skills_dir.is_dir():
            logger.debug(f"Skills directory not found: {skills_dir}")
            return

        try:
            for skill_path in skills_dir.iterdir():
                if not skill_path.is_dir():
                    continue

                skill_file = skill_path / "SKILL.md"
                if not skill_file.exists():
                    logger.debug(f"No SKILL.md found in {skill_path}")
                    continue

                # 解析frontmatter
                name, description = self._parse_frontmatter(skill_file)
                if not name:
                    logger.warning(f"Invalid frontmatter (missing name) in {skill_file}")
                    continue

                # 允许空的 description，使用默认值
                if not description:
                    description = f"{name} skill"
                    logger.debug(f"Empty description for {name}, using default")

                # 验证name匹配目录名
                if name != skill_path.name:
                    logger.warning(
                        f"Skill name '{name}' does not match directory '{skill_path.name}', skipping",
                    )
                    continue

                skill = Skill(
                    name=name,
                    description=description,
                    path=skill_file,
                    mode=mode,
                    scope=scope,
                )

                # 添加到注册表（使用覆盖逻辑）
                if name not in self._skills:
                    self._skills[name] = []

                # 检查是否已存在相同配置的skill
                exists = any(s.mode == mode and s.scope == scope for s in self._skills[name])
                if not exists:
                    self._skills[name].append(skill)
                    logger.debug(f"Discovered skill: {name} (mode={mode}, scope={scope})")
        except OSError as e:
            logger.exception(f"Failed to iterate skills directory {skills_dir}: {e}")
            return

    def _parse_frontmatter(self, skill_file: Path) -> tuple[str | None, str | None]:
        """解析SKILL.md的frontmatter

        Returns:
            (name, description) 或 (None, None) 如果解析失败

        """
        try:
            with Path(skill_file).open(encoding="utf-8") as f:
                content = f.read(4096)  # 只读取前4KB用于解析frontmatter

            # 匹配frontmatter: ---\nname: xxx\ndescription: xxx\n---
            # description可能跨多行，所以使用非贪婪匹配直到下一个---或文件结束
            match = re.search(
                r"^---\s*\nname:\s*(.+?)\s*\ndescription:\s*(.+?)\s*\n---",
                content,
                re.MULTILINE | re.DOTALL,
            )

            if match:
                name = match.group(1).strip()
                description = match.group(2).strip()
                # 移除description中的换行符，保持单行
                description = " ".join(description.split())
                return name, description

            return None, None

        except Exception as e:
            logger.exception(f"Failed to parse frontmatter from {skill_file}: {e}")
            return None, None

    def get_all_skills(self, reload: bool = False) -> list[Skill]:
        """获取所有可用的skills（只包含元数据）

        Args:
            reload: 是否重新发现skills

        Returns:
            按优先级排序的skill列表（workspace > system > user, mode-specific > generic）

        """
        if reload or not self._initialized:
            self.discover_skills(force=True)

        # 收集所有skills，按优先级排序
        all_skills: list[Skill] = []
        seen: set[tuple[str, str | None]] = set()

        # 按新的三级优先级顺序添加
        # 优先级：workspace > system > user, mode-specific > generic
        priorities = [
            ("workspace", self.current_mode),
            ("system", self.current_mode),
            ("user", self.current_mode),
            ("workspace", None),
            ("system", None),
            ("user", None),
        ]

        for scope, mode in priorities:
            for skill_list in self._skills.values():
                for skill in skill_list:
                    key = (skill.name, skill.mode)
                    if key not in seen and skill.scope == scope and skill.mode == mode:
                        all_skills.append(skill)
                        seen.add(key)

        return all_skills

    def find_matching_skills(self, query: str, reload: bool = False) -> list[Skill]:
        """根据查询语句找到匹配的skills

        Args:
            query: 用户查询语句
            reload: 是否重新发现skills

        Returns:
            匹配的skill列表（按匹配度排序）

        """
        all_skills = self.get_all_skills(reload=reload)
        query_lower = query.lower()

        # 简单的关键词匹配
        # 可以改进为使用更智能的匹配算法（如TF-IDF、embedding等）
        scored_skills = []
        for skill in all_skills:
            desc_lower = skill.description.lower()
            # 计算匹配分数：关键词重叠度
            query_words = set(query_lower.split())
            desc_words = set(desc_lower.split())

            overlap = len(query_words & desc_words)
            if overlap > 0:
                scored_skills.append((skill, overlap))

        # 按分数排序
        scored_skills.sort(key=lambda x: x[1], reverse=True)

        return [skill for skill, _ in scored_skills]

    def get_skill_content(self, skill_name: str) -> str | None:
        """获取指定skill的完整内容

        Args:
            skill_name: skill名称

        Returns:
            SKILL.md的完整内容，如果skill不存在则返回None

        """
        if skill_name not in self._skills:
            return None

        # 获取优先级最高的skill
        skills_list = self._skills[skill_name]
        if not skills_list:
            return None

        # 按优先级排序
        priorities = [
            ("project", self.current_mode),
            ("global", self.current_mode),
            ("project", None),
            ("global", None),
        ]

        for scope, mode in priorities:
            for skill in skills_list:
                if skill.scope == scope and skill.mode == mode:
                    return skill.load_content()

        # 如果没有找到匹配的，返回第一个
        return skills_list[0].load_content()

    def get_skill_resources(self, skill_name: str) -> dict[str, Path]:
        """获取指定skill的资源文件

        Args:
            skill_name: skill名称

        Returns:
            资源文件字典 {filename: Path}

        """
        if skill_name not in self._skills:
            return {}

        skills_list = self._skills[skill_name]
        if not skills_list:
            return {}

        # 获取优先级最高的skill
        priorities = [
            ("project", self.current_mode),
            ("global", self.current_mode),
            ("project", None),
            ("global", None),
        ]

        for scope, mode in priorities:
            for skill in skills_list:
                if skill.scope == scope and skill.mode == mode:
                    return skill.get_resources()

        return {}

    def get_skills_summary(self, reload: bool = False) -> str:
        """获取所有skills的摘要信息

        Args:
            reload: 是否重新发现skills

        Returns:
            格式化的skills摘要

        """
        skills = self.get_all_skills(reload=reload)

        lines = [f"# Available Skills ({len(skills)})", "", "## Skills List", ""]

        for skill in skills:
            mode_str = f" [{skill.mode}]" if skill.mode else ""
            scope_str = f" ({skill.scope}){mode_str}"
            lines.append(f"- **{skill.name}**{scope_str}: {skill.description}")

        return "\n".join(lines)
