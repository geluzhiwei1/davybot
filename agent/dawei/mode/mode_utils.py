# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""模式工具函数 - 提供模式相关的实用功能"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dawei.mode.mode_manager import ModeManager


def get_builtin_modes() -> list[str]:
    """获取内置模式列表

    内置模式是 PDCA 循环的五个阶段：
    - orchestrator: 协调者模式（优先级最高）
    - plan: 计划模式
    - do: 执行模式
    - check: 检查模式
    - act: 改进模式

    Returns:
        list[str]: 内置模式的 slug 列表，按优先级排序
    """
    return ["orchestrator", "pdca"]


def get_default_mode() -> str:
    """获取默认模式

    默认使用 orchestrator 模式，因为它是 PDCA 循环的协调者模式。

    Returns:
        str: 默认模式的 slug
    """
    return "orchestrator"


def is_builtin_mode(mode_slug: str) -> bool:
    """检查是否为内置模式

    Args:
        mode_slug: 模式 slug

    Returns:
        bool: 如果是内置模式返回 True，否则返回 False
    """
    return mode_slug in get_builtin_modes()


def get_valid_modes(workspace_path: str | None = None) -> list[str]:
    """获取所有有效的模式（包括内置和自定义）

    Args:
        workspace_path: 工作区路径（可选），用于加载工作区级自定义模式

    Returns:
        list[str]: 所有有效模式的 slug 列表，内置模式在前，自定义模式在后
    """
    try:
        from dawei.mode.mode_manager import ModeManager

        mode_manager = ModeManager(workspace_path=workspace_path)
        all_modes = mode_manager.get_all_modes()

        # 内置模式在前，自定义模式在后
        builtin = get_builtin_modes()
        custom = [slug for slug in all_modes.keys() if slug not in builtin]

        return builtin + custom

    except Exception:
        # 如果加载失败，返回内置模式
        return get_builtin_modes()


def validate_mode(mode_slug: str, workspace_path: str | None = None) -> bool:
    """验证模式是否有效

    Args:
        mode_slug: 要验证的模式 slug
        workspace_path: 工作区路径（可选）

    Returns:
        bool: 如果模式有效返回 True，否则返回 False
    """
    valid_modes = get_valid_modes(workspace_path)
    return mode_slug in valid_modes


def get_mode_order(workspace_path: str | None = None) -> list[str]:
    """获取模式的显示顺序

    内置模式按 PDCA 优先级排序，自定义模式按字母顺序排在后面。

    Args:
        workspace_path: 工作区路径（可选）

    Returns:
        list[str]: 排序后的模式 slug 列表
    """
    valid_modes = get_valid_modes(workspace_path)

    # 内置模式保持固定顺序
    builtin_order = get_builtin_modes()
    custom_modes = [m for m in valid_modes if m not in builtin_order]

    # 自定义模式按字母顺序排序
    custom_modes.sort()

    return builtin_order + custom_modes


def get_all_mode_info(workspace_path: str | None = None) -> dict[str, dict]:
    """获取所有模式的详细信息

    Args:
        workspace_path: 工作区路径（可选）

    Returns:
        dict[str, dict]: 模式详细信息字典，key 为 slug，value 为模式信息的字典
    """
    try:
        from dawei.mode.mode_manager import ModeManager
        from dawei.entity.mode import ModeConfig

        mode_manager = ModeManager(workspace_path=workspace_path)
        all_modes = mode_manager.get_all_modes()

        # 转换为字典格式
        mode_info = {}
        for slug, config in all_modes.items():
            mode_info[slug] = {
                "slug": slug,
                "name": config.name,
                "description": config.description,
                "role_definition": config.role_definition,
                "when_to_use": config.when_to_use,
                "groups": config.groups,
                "source": config.source,
                "is_builtin": is_builtin_mode(slug),
            }

        return mode_info

    except Exception:
        # 如果加载失败，返回内置模式的基本信息
        return {
            slug: {
                "slug": slug,
                "name": slug.title(),
                "description": f"Built-in {slug} mode",
                "is_builtin": True,
            }
            for slug in get_builtin_modes()
        }
