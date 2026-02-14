"""技能API端点

提供技能列表、搜索和详情查询
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from dawei.core.validators import validate_dict_key
from dawei.tools.skill_manager import Skill, SkillManager
from dawei.workspace.workspace_manager import workspace_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills", tags=["skills"])


class SkillResponse(BaseModel):
    """技能响应模型"""

    name: str
    description: str
    mode: str | None = None
    scope: str | None = None
    icon: str = "⚡"
    category: str | None = None


class SkillsListResponse(BaseModel):
    """技能列表响应"""

    skills: list[SkillResponse]
    total: int


class SkillSearchResponse(BaseModel):
    """技能搜索响应"""

    query: str
    results: list[SkillResponse]
    total: int


def get_skill_icon(skill_name: str) -> str:
    """根据技能名称返回合适的图标"""
    icons = {
        "pdf": "📄",
        "xlsx": "📊",
        "docx": "📝",
        "pptx": "📽️",
        "canvas": "🎨",
        "frontend-design": "💻",
        "web": "🌐",
        "algorithmic-art": "🎭",
        "brand-guidelines": "🎨",
        "web-artifacts-builder": "🔧",
        "default": "⚡",
    }
    return icons.get(skill_name.lower(), icons["default"])


@router.get("/list", response_model=SkillsListResponse)
async def list_skills(
    mode: str | None = Query(None, description="按模式筛选"),
    scope: str | None = Query(None, description="按范围筛选"),
    workspace_id: str | None = Query(None, description="工作区ID"),
):
    """获取所有可用的技能列表

    返回技能的摘要信息，包括名称、描述、模式和范围
    """
    try:
        from pathlib import Path

        # 构建skills_roots，始终包含全局user目录
        skills_roots = [Path.home()]

        # 如果提供了workspace_id，从workspace_manager获取workspace路径
        if workspace_id:
            workspace_info = workspace_manager.get_workspace_by_id(workspace_id)

            if workspace_info:
                # Fast Fail: 安全提取path字段
                workspace_path = validate_dict_key(workspace_info, "path", "workspace_info")
                if workspace_path:
                    workspace_root = Path(workspace_path)
                    if workspace_root.exists():
                        skills_roots.insert(0, workspace_root)
                        logger.info(
                            f"[SKILLS API] Added workspace skills root: {workspace_root} (workspace_id={workspace_id})",
                        )
                    else:
                        logger.warning(
                            f"[SKILLS API] Workspace path does not exist: {workspace_root}",
                        )
                else:
                    logger.warning(f"[SKILLS API] Workspace info has no path: {workspace_info}")
            else:
                logger.warning(f"[SKILLS API] Workspace not found: {workspace_id}")
        else:
            logger.info("[SKILLS API] No workspace_id provided, using global skills only")

        logger.info(f"[SKILLS API] Initializing SkillManager with roots: {skills_roots}")
        skill_manager = SkillManager(skills_roots=skills_roots)
        skill_manager.discover_skills(force=True)
        skills = skill_manager.get_all_skills() or []

        # 过滤
        if mode:
            skills = [s for s in skills if s.mode == mode]
        if scope:
            skills = [s for s in skills if s.scope == scope]

        # 转换为响应模型
        skill_responses = [
            SkillResponse(
                name=skill.name,
                description=skill.description,
                mode=skill.mode,
                scope=skill.scope,
                icon=get_skill_icon(skill.name),
                category=_categorize_skill(skill),
            )
            for skill in skills
        ]

        return SkillsListResponse(skills=skill_responses, total=len(skill_responses))

    except (OSError, PermissionError) as e:
        # Filesystem error accessing skill directories
        logger.error(f"Failed to access skill directories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to access skill directories: {e!s}")
    except (ValueError, TypeError) as e:
        # Skill data validation error
        logger.error(f"Invalid skill data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Invalid skill data: {e!s}")
    except Exception as e:
        # Unexpected error
        logger.critical(f"Unexpected error listing skills: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/search/{query}", response_model=SkillSearchResponse)
async def search_skills(
    query: str,
    limit: int = Query(10, ge=1, le=50),
    workspace_id: str | None = Query(None, description="工作区ID"),
):
    """搜索匹配的技能

    根据查询字符串搜索相关的技能，按相关性排序
    """
    try:
        if not query or len(query.strip()) == 0:
            return SkillSearchResponse(query=query, results=[], total=0)

        # 构建skills_roots，始终包含全局user目录（与list_skills保持一致）
        from pathlib import Path

        skills_roots = [Path.home()]  # 全局user目录 (~/.dawei/skills/)

        # 如果提供了workspace_id，从workspace_manager获取workspace路径
        if workspace_id:
            workspace_info = workspace_manager.get_workspace_by_id(workspace_id)

            if workspace_info:
                # Fast Fail: 安全提取path字段
                workspace_path = validate_dict_key(workspace_info, "path", "workspace_info")
                if workspace_path:
                    workspace_root = Path(workspace_path)
                    if workspace_root.exists():
                        skills_roots.insert(0, workspace_root)
                        logger.info(
                            f"[SKILLS API] Search: Added workspace skills root: {workspace_root} (workspace_id={workspace_id})",
                        )
                    else:
                        logger.warning(
                            f"[SKILLS API] Search: Workspace path does not exist: {workspace_root}",
                        )
                else:
                    logger.warning(
                        f"[SKILLS API] Search: Workspace info has no path: {workspace_info}",
                    )
            else:
                logger.warning(f"[SKILLS API] Search: Workspace not found: {workspace_id}")
        else:
            logger.info("[SKILLS API] Search: No workspace_id provided, using global skills only")

        logger.info(f"[SKILLS API] Search: Initializing SkillManager with roots: {skills_roots}")
        skill_manager = SkillManager(skills_roots=skills_roots)
        skill_manager.discover_skills(force=True)
        matching_skills = skill_manager.find_matching_skills(query) or []

        # 限制结果数量
        matching_skills = matching_skills[:limit]

        # 转换为响应模型
        results = [
            SkillResponse(
                name=skill.name,
                description=skill.description,
                mode=skill.mode,
                scope=skill.scope,
                icon=get_skill_icon(skill.name),
                category=_categorize_skill(skill),
            )
            for skill in matching_skills
        ]

        return SkillSearchResponse(query=query, results=results, total=len(results))

    except (OSError, PermissionError) as e:
        # Filesystem error accessing skill directories
        logger.error(f"Failed to access skill directories during search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to search skills: {e!s}")
    except (ValueError, TypeError) as e:
        # Skill data validation error
        logger.error(f"Invalid skill data during search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Invalid skill data: {e!s}")
    except Exception as e:
        # Unexpected error
        logger.critical(f"Unexpected error searching skills: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/skill/{skill_name}", response_model=SkillResponse)
async def get_skill(
    skill_name: str,
    workspace_id: str | None = Query(None, description="工作区ID"),
):
    """获取特定技能的详细信息"""
    try:
        # 构建skills_roots，始终包含全局user目录（与list_skills保持一致）
        from pathlib import Path

        skills_roots = [Path.home()]  # 全局user目录 (~/.dawei/skills/)

        # 如果提供了workspace_id，从workspace_manager获取workspace路径
        if workspace_id:
            workspace_info = workspace_manager.get_workspace_by_id(workspace_id)

            if workspace_info:
                # Fast Fail: 安全提取path字段
                workspace_path = validate_dict_key(workspace_info, "path", "workspace_info")
                if workspace_path:
                    workspace_root = Path(workspace_path)
                    if workspace_root.exists():
                        skills_roots.insert(0, workspace_root)
                        logger.info(
                            f"[SKILLS API] Get skill: Added workspace skills root: {workspace_root} (workspace_id={workspace_id})",
                        )
                    else:
                        logger.warning(
                            f"[SKILLS API] Get skill: Workspace path does not exist: {workspace_root}",
                        )
                else:
                    logger.warning(
                        f"[SKILLS API] Get skill: Workspace info has no path: {workspace_info}",
                    )
            else:
                logger.warning(f"[SKILLS API] Get skill: Workspace not found: {workspace_id}")
        else:
            logger.info(
                "[SKILLS API] Get skill: No workspace_id provided, using global skills only",
            )

        logger.info(f"[SKILLS API] Get skill: Initializing SkillManager with roots: {skills_roots}")
        skill_manager = SkillManager(skills_roots=skills_roots)
        skill_manager.discover_skills(force=True)
        skills = skill_manager.get_all_skills() or []

        # 查找匹配的技能
        skill = next((s for s in skills if s.name == skill_name), None)

        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        return SkillResponse(
            name=skill.name,
            description=skill.description,
            mode=skill.mode,
            scope=skill.scope,
            icon=get_skill_icon(skill.name),
            category=_categorize_skill(skill),
        )

    except HTTPException:
        raise
    except (OSError, PermissionError) as e:
        # Filesystem error accessing skill directories
        logger.error(f"Failed to access skill directories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to access skill directories: {e!s}")
    except (ValueError, TypeError) as e:
        # Skill data validation error
        logger.error(f"Invalid skill data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Invalid skill data: {e!s}")
    except Exception as e:
        # Unexpected error
        logger.critical(f"Unexpected error getting skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


def _categorize_skill(skill: Skill) -> str | None:
    """根据技能名称和描述分类"""
    name_lower = skill.name.lower()
    desc_lower = skill.description.lower()

    if any(kw in name_lower or kw in desc_lower for kw in ["pdf", "document"]):
        return "文档处理"
    if any(kw in name_lower or kw in desc_lower for kw in ["xlsx", "excel", "csv", "data"]):
        return "数据处理"
    if any(kw in name_lower or kw in desc_lower for kw in ["pptx", "presentation"]):
        return "演示文稿"
    if any(kw in name_lower or kw in desc_lower for kw in ["canvas", "design", "art"]):
        return "设计创作"
    if any(kw in name_lower or kw in desc_lower for kw in ["web", "frontend", "html"]):
        return "Web开发"
    if any(kw in name_lower or kw in desc_lower for kw in ["browser", "automation"]):
        return "自动化"
    if any(kw in name_lower or kw in desc_lower for kw in ["brand", "style"]):
        return "品牌设计"

    return "通用"
