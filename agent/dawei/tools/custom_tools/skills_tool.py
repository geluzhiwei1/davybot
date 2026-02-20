# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Skills工具 - 将skills能力暴露给agent

允许agent：
1. 查看所有可用的skills
2. 搜索匹配的skills
3. 加载特定skill的内容
4. 访问skill的资源文件
"""

import logging
import os
from pathlib import Path

from dawei.config import get_dawei_home
from dawei.tools.custom_base_tool import CustomBaseTool
from dawei.tools.skill_manager import SkillManager

logger = logging.getLogger(__name__)


class ListSkillsTool(CustomBaseTool):
    """列出所有可用的skills

    返回所有已发现skills的摘要信息，包括name、description、mode和scope
    """

    name = "list_skills"
    description = """List all available skills with their names, descriptions, and metadata.

Use this tool when you need to:
- See what skills are available
- Understand the current system's specialized capabilities
- Find skills that might match the user's request

Returns a formatted list of all skills with their descriptions."""

    def __init__(self, skill_manager: SkillManager):
        super().__init__()
        self.skill_manager = skill_manager

    def _run(self, **_kwargs) -> str:
        """列出所有可用的skills"""
        return self.skill_manager.get_skills_summary(reload=True)


class SearchSkillsTool(CustomBaseTool):
    """搜索匹配的skills

    根据用户查询描述搜索相关的skills
    """

    name = "search_skills"
    description = """Search for skills that match a specific query or task description.

Use this tool when you need to:
- Find skills relevant to a user's request
- Discover specialized capabilities for a task
- Match user intent to available skills

Args:
    query (str): The task description or query to match against skill descriptions

Returns a ranked list of matching skills with their relevance scores."""

    def __init__(self, skill_manager: SkillManager):
        super().__init__()
        self.skill_manager = skill_manager

    def _run(self, query: str, **_kwargs) -> str:
        """搜索匹配的skills"""
        if not query:
            return "Error: query parameter is required"

        try:
            matching_skills = self.skill_manager.find_matching_skills(query, reload=True)

            if not matching_skills:
                return f"No skills found matching query: {query}"

            lines = [
                f"# Matching Skills for: {query}",
                f"Found {len(matching_skills)} relevant skill(s)",
                "",
            ]

            for i, skill in enumerate(matching_skills, 1):
                mode_str = f" [{skill.mode}]" if skill.mode else ""
                scope_str = f" ({skill.scope}){mode_str}"
                lines.append(f"{i}. **{skill.name}**{scope_str}\n   - {skill.description}\n")

            return "\n".join(lines)

        except (AttributeError, KeyError, ValueError, OSError) as e:
            logger.error(f"Failed to search skills: {e}", exc_info=True)
            return f"Error searching skills: {e!s}"


class GetSkillTool(CustomBaseTool):
    """获取特定skill的完整内容

    加载指定skill的完整SKILL.md内容
    """

    name = "get_skill"
    description = """Get the complete content and instructions for a specific skill.

Use this tool when you:
- Have identified a relevant skill and need its detailed instructions
- Need to understand how to perform a specialized task
- Want to follow a skill's workflow or best practices

Args:
    skill_name (str): The name of the skill to load (e.g., 'pdf', 'docx', 'xlsx')

Returns the complete SKILL.md content with all instructions, examples, and workflows."""

    def __init__(self, skill_manager: SkillManager):
        super().__init__()
        self.skill_manager = skill_manager

    def _run(self, skill_name: str, **_kwargs) -> str:
        """获取skill的完整内容"""
        if not skill_name:
            return "Error: skill_name parameter is required"

        try:
            content = self.skill_manager.get_skill_content(skill_name)

            if not content:
                return f"Skill '{skill_name}' not found. Use list_skills to see available skills."

            return content

        except (AttributeError, KeyError, ValueError, OSError) as e:
            logger.error(f"Failed to get skill content: {e}", exc_info=True)
            return f"Error getting skill content: {e!s}"


class ListSkillResourcesTool(CustomBaseTool):
    """列出skill的资源文件

    显示skill目录下的所有额外资源文件
    """

    name = "list_skill_resources"
    description = """List all resource files available for a specific skill.

Use this tool when you:
- Need to see what additional resources a skill provides
- Want to access reference materials, templates, or examples
- Are looking for supplementary documentation

Args:
    skill_name (str): The name of the skill

Returns a list of available resource files with their descriptions."""

    def __init__(self, skill_manager: SkillManager):
        super().__init__()
        self.skill_manager = skill_manager

    def _run(self, skill_name: str, **_kwargs) -> str:
        """列出skill的资源文件"""
        if not skill_name:
            return "Error: skill_name parameter is required"

        try:
            resources = self.skill_manager.get_skill_resources(skill_name)

            if not resources:
                return f"No resources found for skill '{skill_name}'"

            lines = [
                f"# Resources for skill: {skill_name}",
                f"Found {len(resources)} resource file(s)",
                "",
            ]

            for name, path in resources.items():
                lines.append(f"- **{name}**: `{path.name}`")

            return "\n".join(lines)

        except (AttributeError, KeyError, ValueError, OSError) as e:
            logger.error(f"Failed to list skill resources: {e}", exc_info=True)
            return f"Error listing skill resources: {e!s}"


class ReadSkillResourceTool(CustomBaseTool):
    """读取skill的资源文件内容

    读取指定skill的特定资源文件
    """

    name = "read_skill_resource"
    description = """Read the content of a specific resource file from a skill.

Use this tool when you:
- Need detailed information from a skill's reference material
- Want to see examples or templates provided by the skill
- Are accessing supplementary documentation

Args:
    skill_name (str): The name of the skill
    resource_name (str): The name of the resource file (without extension)

Returns the complete content of the resource file."""

    def __init__(self, skill_manager: SkillManager):
        super().__init__()
        self.skill_manager = skill_manager

    def _run(self, skill_name: str, resource_name: str, **_kwargs) -> str:
        """读取skill的资源文件内容"""
        if not skill_name or not resource_name:
            return "Error: both skill_name and resource_name parameters are required"

        try:
            resources = self.skill_manager.get_skill_resources(skill_name)

            if not resources:
                return f"No resources found for skill '{skill_name}'"

            # 查找匹配的资源文件（支持不区分大小写）
            matching_path = None
            for name, path in resources.items():
                if name.lower() == resource_name.lower():
                    matching_path = path
                    break

            if not matching_path:
                available = ", ".join(resources.keys())
                return f"Resource '{resource_name}' not found. Available: {available}"

            # 读取文件内容
            with Path(matching_path).open(encoding="utf-8") as f:
                return f.read()

        except (AttributeError, KeyError, ValueError, OSError, UnicodeDecodeError) as e:
            logger.error(f"Failed to read skill resource: {e}", exc_info=True)
            return f"Error reading skill resource: {e!s}"


def create_skills_tools(
    skills_roots: list[Path] | None = None,
    current_mode: str | None = None,
) -> list[CustomBaseTool]:
    """创建所有skills相关的工具 - 支持多级加载

    Args:
        skills_roots: 包含.dawei目录的根路径列表（优先级从高到低）
        current_mode: 当前模式

    Returns:
        skills工具列表

    """
    # 如果没有提供roots，使用默认的global root (DAWEI_HOME)
    if not skills_roots:
        skills_roots = [Path(get_dawei_home())]

    skill_manager = SkillManager(skills_roots=skills_roots, current_mode=current_mode)

    # 初始化发现skills
    skill_manager.discover_skills()

    # 打印发现结果（调试用）
    import logging

    logger = logging.getLogger(__name__)
    all_skills = skill_manager.get_all_skills()
    logger.info(
        f"SkillManager discovered {len(all_skills)} skills from {len(skills_roots)} root(s): {[s.name for s in all_skills]}",
    )

    return [
        ListSkillsTool(skill_manager),
        SearchSkillsTool(skill_manager),
        GetSkillTool(skill_manager),
        ListSkillResourcesTool(skill_manager),
        ReadSkillResourceTool(skill_manager),
    ]
