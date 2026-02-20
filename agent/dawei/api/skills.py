"""技能API端点

提供技能列表、搜索和详情查询
"""

import logging
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from dawei.config import get_dawei_home
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
    path: str | None = None  # 技能文件路径


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
        # 构建skills_roots，始终包含全局user目录 (DAWEI_HOME)
        dawei_home = Path(get_dawei_home())
        skills_roots = [dawei_home]

        # 如果提供了workspace_id，尝试获取工作区路径
        if workspace_id:
            workspace_path = None

            # 1. 尝试从workspace_manager获取注册的工作区
            workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
            if workspace_info:
                workspace_path = validate_dict_key(workspace_info, "path", "workspace_info")

            # 2. 如果没有注册，尝试从工作区目录下的 .dawei/workspace.json 读取
            if not workspace_path:
                raise ValueError(f"workspace_path cannot be None or empty (workspace_id={workspace_id})")

            # 3. 如果工作区路径存在，添加工作区根目录
            # SkillManager 会在根目录后自动追加 .dawei/configs/skills
            if workspace_path:
                workspace_root = Path(workspace_path)
                if workspace_root.exists():
                    # 插入工作区根目录（SkillManager会自动搜索 .dawei/configs/skills）
                    skills_roots.insert(0, workspace_root)
                    logger.info(
                        f"[SKILLS API] Added workspace root: {workspace_root} (workspace_id={workspace_id})",
                    )

                    # 检查预期的技能目录是否存在
                    workspace_dawei = workspace_root / ".dawei"
                    market_skills_dir = workspace_dawei / "skills"
                    config_skills_dir = workspace_dawei / "configs" / "skills"

                    if not market_skills_dir.exists() and not config_skills_dir.exists():
                        logger.warning(
                            f"[SKILLS API] No skills directory found in workspace: {workspace_dawei}",
                        )
                else:
                    logger.warning(
                        f"[SKILLS API] Workspace path does not exist: {workspace_root}",
                    )
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
                path=str(skill.path) if skill.path else None,
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
        skills_roots = [Path(get_dawei_home())]  # 全局user目录 (DAWEI_HOME)

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
                path=str(skill.path) if skill.path else None,
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
        skills_roots = [Path(get_dawei_home())]  # 全局user目录 (DAWEI_HOME)

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
            path=str(skill.path) if skill.path else None,
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


# ============ 技能编辑和删除 API ============


class SkillUpdateRequest(BaseModel):
    """技能更新请求"""

    name: str | None = None
    description: str | None = None
    content: str | None = None  # 完整的SKILL.md内容


class SkillDeleteResponse(BaseModel):
    """技能删除响应"""

    success: bool
    message: str


@router.delete("/skill/{skill_name}", response_model=SkillDeleteResponse)
async def delete_skill(
    skill_name: str,
    workspace_id: str | None = Query(None, description="工作区ID"),
):
    """删除指定技能"""
    try:
        # 构建skills_roots
        skills_roots = [Path(get_dawei_home())]

        if workspace_id:
            workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
            if workspace_info:
                workspace_path = validate_dict_key(workspace_info, "path", "workspace_info")
                if workspace_path:
                    workspace_root = Path(workspace_path)
                    if workspace_root.exists():
                        skills_roots.insert(0, workspace_root)

        # 初始化SkillManager并发现技能
        skill_manager = SkillManager(skills_roots=skills_roots)
        skill_manager.discover_skills(force=True)

        # 查找技能 - 获取所有匹配的技能（包括重复的）
        skills = skill_manager._skills
        matching_skills = []
        for skill_list in skills.values():
            for skill in skill_list:
                if skill.name == skill_name:
                    matching_skills.append(skill)

        if not matching_skills:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        # 按优先级排序（workspace > user > system）
        priority_order = {"workspace": 3, "user": 2, "system": 1}
        matching_skills.sort(key=lambda s: priority_order.get(s.scope or "", 0), reverse=True)

        # 获取最高优先级的技能（即要删除的）
        skill_to_delete = matching_skills[0]

        # 检查是否有同名的其他技能
        has_duplicates = len(matching_skills) > 1

        # 检查路径安全性 - 只允许删除 workspace 和 user 目录下的技能
        skill_path = skill_to_delete.path
        if not skill_path:
            raise HTTPException(status_code=400, detail="Skill path is invalid")

        # 不允许删除系统级技能
        if skill_to_delete.scope == "system":
            raise HTTPException(status_code=403, detail="Cannot delete system-level skills")

        # 检查文件是否存在
        if not skill_path.exists():
            raise HTTPException(status_code=404, detail=f"Skill file not found: {skill_path}")

        # 删除技能目录
        skill_dir = skill_path.parent
        shutil.rmtree(skill_dir)
        logger.info(f"Deleted skill '{skill_name}' from {skill_to_delete.scope} at {skill_dir}")

        # 构建返回消息
        message = f"Skill '{skill_name}' deleted successfully"
        if has_duplicates:
            other_scopes = [s.scope for s in matching_skills[1:] if s.scope]
            if other_scopes:
                message += f". Note: Skill still exists in {', '.join(set(other_scopes))} scope(s)"

        return SkillDeleteResponse(success=True, message=message)

    except HTTPException:
        raise
    except (OSError, PermissionError) as e:
        logger.error(f"Failed to delete skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete skill: {e!s}")
    except Exception as e:
        logger.critical(f"Unexpected error deleting skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/skill/{skill_name}", response_model=SkillResponse)
async def update_skill(
    skill_name: str,
    request: SkillUpdateRequest,
    workspace_id: str | None = Query(None, description="工作区ID"),
):
    """更新指定技能"""
    try:
        # 构建skills_roots
        skills_roots = [Path(get_dawei_home())]

        if workspace_id:
            workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
            if workspace_info:
                workspace_path = validate_dict_key(workspace_info, "path", "workspace_info")
                if workspace_path:
                    workspace_root = Path(workspace_path)
                    if workspace_root.exists():
                        skills_roots.insert(0, workspace_root)

        # 初始化SkillManager并发现技能
        skill_manager = SkillManager(skills_roots=skills_roots)
        skill_manager.discover_skills(force=True)

        # 查找技能
        skills = skill_manager.get_all_skills() or []
        skill = next((s for s in skills if s.name == skill_name), None)

        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        # 检查路径安全性
        skill_path = skill.path
        if not skill_path:
            raise HTTPException(status_code=400, detail="Skill path is invalid")

        # 不允许修改系统级技能
        if skill.scope == "system":
            raise HTTPException(status_code=403, detail="Cannot modify system-level skills")

        # 检查文件是否存在
        if not skill_path.exists():
            raise HTTPException(status_code=404, detail=f"Skill file not found: {skill_path}")

        # 更新技能内容
        current_content = skill.load_content()

        # 解析frontmatter并更新
        import re

        # 提取frontmatter和正文
        frontmatter_match = re.match(r"^---\n(.*?)\n---\n", current_content, re.DOTALL)
        if frontmatter_match:
            frontmatter_str = frontmatter_match.group(1)
            content_body = current_content[frontmatter_match.end() :]
        else:
            frontmatter_str = ""
            content_body = current_content

        # 更新frontmatter
        frontmatter_lines = []
        if frontmatter_str:
            for line in frontmatter_str.split("\n"):
                if line.startswith("name:"):
                    frontmatter_lines.append(f"name: {request.name if request.name else skill_name}")
                elif line.startswith("description:") and request.description is not None:
                    frontmatter_lines.append(f"description: {request.description}")
                else:
                    frontmatter_lines.append(line)

        # 如果没有name，更新description
        if request.name is not None and not any(l.startswith("name:") for l in frontmatter_lines):
            frontmatter_lines.insert(0, f"name: {request.name}")
        if request.description is not None and not any(l.startswith("description:") for l in frontmatter_lines):
            frontmatter_lines.append(f"description: {request.description}")

        # 更新内容
        new_content = request.content if request.content is not None else content_body

        # 重新组合
        if frontmatter_lines:
            new_full_content = "---\n" + "\n".join(frontmatter_lines) + "\n---\n" + new_content
        else:
            new_full_content = new_content

        # 写入文件
        with open(skill_path, "w", encoding="utf-8") as f:
            f.write(new_full_content)

        logger.info(f"Updated skill '{skill_name}' at {skill_path}")

        # 返回更新后的技能
        return SkillResponse(
            name=request.name if request.name else skill_name,
            description=request.description if request.description else skill.description,
            mode=skill.mode,
            scope=skill.scope,
            icon=get_skill_icon(request.name if request.name else skill_name),
            category=_categorize_skill(skill),
            path=str(skill_path),
        )

    except HTTPException:
        raise
    except (OSError, PermissionError) as e:
        logger.error(f"Failed to update skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update skill: {e!s}")
    except Exception as e:
        logger.critical(f"Unexpected error updating skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/skill/{skill_name}/content")
async def get_skill_content(
    skill_name: str,
    workspace_id: str | None = Query(None, description="工作区ID"),
):
    """获取技能的完整内容（包括SKILL.md全文）"""
    try:
        # 构建skills_roots
        skills_roots = [Path(get_dawei_home())]

        if workspace_id:
            workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
            if workspace_info:
                workspace_path = validate_dict_key(workspace_info, "path", "workspace_info")
                if workspace_path:
                    workspace_root = Path(workspace_path)
                    if workspace_root.exists():
                        skills_roots.insert(0, workspace_root)

        # 初始化SkillManager并发现技能
        skill_manager = SkillManager(skills_roots=skills_roots)
        skill_manager.discover_skills(force=True)

        # 查找技能
        skills = skill_manager.get_all_skills() or []
        skill = next((s for s in skills if s.name == skill_name), None)

        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        # 加载完整内容
        content = skill.load_content()

        return {
            "name": skill.name,
            "description": skill.description,
            "content": content,
            "path": str(skill.path) if skill.path else None,
            "mode": skill.mode,
            "scope": skill.scope,
        }

    except HTTPException:
        raise
    except (OSError, PermissionError) as e:
        logger.error(f"Failed to get skill content: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get skill content: {e!s}")
    except Exception as e:
        logger.critical(f"Unexpected error getting skill content: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ============ 技能创建 API ============


class SkillCreateRequest(BaseModel):
    """技能创建请求"""

    name: str
    description: str = ""
    content: str = ""  # 完整的SKILL.md内容
    scope: str = "workspace"  # "workspace" or "user"


@router.post("/skill", response_model=SkillResponse)
async def create_skill(
    request: SkillCreateRequest,
    workspace_id: str | None = Query(None, description="工作区ID"),
):
    """创建新技能"""
    try:
        # 验证技能名称
        if not request.name or len(request.name.strip()) == 0:
            raise HTTPException(status_code=400, detail="Skill name cannot be empty")

        # 清理技能名称（用于目录名）
        skill_name = request.name.strip()
        # 替换不允许的字符
        import re
        skill_dir_name = re.sub(r'[<>:"/\\|?*]', '_', skill_name)

        # 确定创建路径
        if request.scope == "user":
            # 用户级技能：创建在全局用户目录
            skills_root = Path(get_dawei_home())
        else:
            # 工作区级技能：需要 workspace_id
            if not workspace_id:
                raise HTTPException(status_code=400, detail="workspace_id is required for workspace-level skills")

            workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
            if not workspace_info:
                raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' not found")

            workspace_path = validate_dict_key(workspace_info, "path", "workspace_info")
            if not workspace_path:
                raise HTTPException(status_code=400, detail="Workspace path is invalid")

            skills_root = Path(workspace_path)
            if not skills_root.exists():
                raise HTTPException(status_code=404, detail=f"Workspace path does not exist: {skills_root}")

        # 创建技能目录
        skills_dir = skills_root / ".dawei" / "skills" / skill_dir_name
        if skills_dir.exists():
            raise HTTPException(status_code=409, detail=f"Skill '{skill_name}' already exists")

        # 创建目录
        skills_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created skill directory: {skills_dir}")

        # 生成 SKILL.md 内容
        skill_content = f"""---
name: {skill_name}
description: {request.description}
---

# {skill_name}

{request.content}
"""

        # 写入 SKILL.md 文件
        skill_file = skills_dir / "SKILL.md"
        with open(skill_file, "w", encoding="utf-8") as f:
            f.write(skill_content)

        logger.info(f"Created skill '{skill_name}' at {skill_file}")

        # 返回创建的技能
        return SkillResponse(
            name=skill_name,
            description=request.description,
            mode=None,
            scope=request.scope,
            icon=get_skill_icon(skill_name),
            category=_categorize_skill_by_name(skill_name),
            path=str(skill_file),
        )

    except HTTPException:
        raise
    except (OSError, PermissionError) as e:
        logger.error(f"Failed to create skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create skill: {e!s}")
    except Exception as e:
        logger.critical(f"Unexpected error creating skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


def _categorize_skill_by_name(skill_name: str) -> str | None:
    """根据技能名称分类"""
    name_lower = skill_name.lower()

    if any(kw in name_lower for kw in ["pdf", "document"]):
        return "文档处理"
    if any(kw in name_lower for kw in ["xlsx", "excel", "csv", "data"]):
        return "数据处理"
    if any(kw in name_lower for kw in ["pptx", "presentation"]):
        return "演示文稿"
    if any(kw in name_lower for kw in ["canvas", "design", "art"]):
        return "设计创作"
    if any(kw in name_lower for kw in ["web", "frontend", "html"]):
        return "Web开发"
    if any(kw in name_lower for kw in ["browser", "automation"]):
        return "自动化"
    if any(kw in name_lower for kw in ["brand", "style"]):
        return "品牌设计"

    return "通用"


# ============ 技能文件树 API ============


class FileTreeItem(BaseModel):
    """文件树项模型"""

    name: str
    path: str
    type: str  # 'file' or 'folder'
    level: int = 0
    children: list["FileTreeItem"] = []


FileTreeItem.model_rebuild()


def _build_skill_file_tree(skill_dir: Path) -> list[FileTreeItem]:
    """构建技能目录的文件树"""

    def _scan_dir(dir_path: Path, level: int = 0) -> list[FileTreeItem]:
        items = []
        try:
            for item in sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name)):
                # 跳过隐藏文件（除了 .dawei）
                if item.name.startswith(".") and item.name != ".dawei":
                    continue

                if item.is_dir():
                    children = _scan_dir(item, level + 1)
                    items.append(
                        FileTreeItem(
                            name=item.name,
                            path=str(item.relative_to(skill_dir)),
                            type="folder",
                            level=level,
                            children=children,
                        )
                    )
                else:
                    items.append(
                        FileTreeItem(
                            name=item.name,
                            path=str(item.relative_to(skill_dir)),
                            type="file",
                            level=level,
                            children=[],
                        )
                    )
        except PermissionError:
            pass
        return items

    return _scan_dir(skill_dir)


@router.get("/skill/{skill_name}/tree")
async def get_skill_file_tree(
    skill_name: str,
    workspace_id: str | None = Query(None, description="工作区ID"),
):
    """获取技能的文件树结构"""
    try:
        # 构建skills_roots
        skills_roots = [Path(get_dawei_home())]

        if workspace_id:
            workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
            if workspace_info:
                workspace_path = validate_dict_key(workspace_info, "path", "workspace_info")
                if workspace_path:
                    workspace_root = Path(workspace_path)
                    if workspace_root.exists():
                        skills_roots.insert(0, workspace_root)

        # 初始化SkillManager并发现技能
        skill_manager = SkillManager(skills_roots=skills_roots)
        skill_manager.discover_skills(force=True)

        # 查找技能
        skills = skill_manager.get_all_skills() or []
        skill = next((s for s in skills if s.name == skill_name), None)

        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        # 检查路径安全性
        skill_path = skill.path
        if not skill_path or not skill_path.exists():
            raise HTTPException(status_code=404, detail=f"Skill file not found: {skill_path}")

        # 获取技能目录
        skill_dir = skill_path.parent

        # 构建文件树
        tree = _build_skill_file_tree(skill_dir)

        return {
            "name": skill.name,
            "path": str(skill_dir),
            "tree": tree,
        }

    except HTTPException:
        raise
    except (OSError, PermissionError) as e:
        logger.error(f"Failed to get skill file tree: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get skill file tree: {e!s}")
    except Exception as e:
        logger.critical(f"Unexpected error getting skill file tree: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/skill/{skill_name}/file")
async def get_skill_file_content(
    skill_name: str,
    file_path: str = Query(..., description="文件路径（相对于技能目录）"),
    workspace_id: str | None = Query(None, description="工作区ID"),
):
    """获取技能目录中指定文件的内容"""
    try:
        # 构建skills_roots
        skills_roots = [Path(get_dawei_home())]

        if workspace_id:
            workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
            if workspace_info:
                workspace_path = validate_dict_key(workspace_info, "path", "workspace_info")
                if workspace_path:
                    workspace_root = Path(workspace_path)
                    if workspace_root.exists():
                        skills_roots.insert(0, workspace_root)

        # 初始化SkillManager并发现技能
        skill_manager = SkillManager(skills_roots=skills_roots)
        skill_manager.discover_skills(force=True)

        # 查找技能
        skills = skill_manager.get_all_skills() or []
        skill = next((s for s in skills if s.name == skill_name), None)

        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        # 检查路径安全性
        skill_path = skill.path
        if not skill_path or not skill_path.exists():
            raise HTTPException(status_code=404, detail=f"Skill file not found: {skill_path}")

        # 获取技能目录
        skill_dir = skill_path.parent

        # 构建目标文件路径（防止路径遍历）
        target_file = (skill_dir / file_path).resolve()
        try:
            target_file.relative_to(skill_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied: path outside skill directory")

        if not target_file.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

        if not target_file.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")

        # 读取文件内容
        try:
            content = target_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Cannot decode file content (binary file)")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read file: {e!s}")

        return {
            "name": target_file.name,
            "path": file_path,
            "content": content,
            "size": target_file.stat().st_size,
        }

    except HTTPException:
        raise
    except (OSError, PermissionError) as e:
        logger.error(f"Failed to get skill file content: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get file content: {e!s}")
    except Exception as e:
        logger.critical(f"Unexpected error getting skill file content: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


class SkillFileUpdateRequest(BaseModel):
    """技能文件更新请求"""

    content: str


@router.put("/skill/{skill_name}/file")
async def update_skill_file_content(
    skill_name: str,
    file_path: str = Query(..., description="文件路径（相对于技能目录）"),
    workspace_id: str | None = Query(None, description="工作区ID"),
    request: SkillFileUpdateRequest | None = None,
):
    """更新技能目录中指定文件的内容"""
    try:
        # 验证请求体
        if request is None:
            raise HTTPException(status_code=400, detail="Request body is required")

        # 构建skills_roots
        skills_roots = [Path(get_dawei_home())]

        if workspace_id:
            workspace_info = workspace_manager.get_workspace_by_id(workspace_id)
            if workspace_info:
                workspace_path = validate_dict_key(workspace_info, "path", "workspace_info")
                if workspace_path:
                    workspace_root = Path(workspace_path)
                    if workspace_root.exists():
                        skills_roots.insert(0, workspace_root)

        # 初始化SkillManager并发现技能
        skill_manager = SkillManager(skills_roots=skills_roots)
        skill_manager.discover_skills(force=True)

        # 查找技能
        skills = skill_manager.get_all_skills() or []
        skill = next((s for s in skills if s.name == skill_name), None)

        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        # 检查路径安全性
        skill_path = skill.path
        if not skill_path or not skill_path.exists():
            raise HTTPException(status_code=404, detail=f"Skill file not found: {skill_path}")

        # 不允许修改系统级技能
        if skill.scope == "system":
            raise HTTPException(status_code=403, detail="Cannot modify system-level skills")

        # 获取技能目录
        skill_dir = skill_path.parent

        # 构建目标文件路径（防止路径遍历）
        target_file = (skill_dir / file_path).resolve()
        try:
            target_file.relative_to(skill_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied: path outside skill directory")

        if not target_file.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

        if not target_file.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")

        # 写入文件内容
        try:
            target_file.write_text(request.content, encoding="utf-8")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to write file: {e!s}")

        logger.info(f"Updated skill file '{skill_name}/{file_path}'")

        return {
            "success": True,
            "message": f"File '{file_path}' updated successfully",
        }

    except HTTPException:
        raise
    except (OSError, PermissionError) as e:
        logger.error(f"Failed to update skill file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update file: {e!s}")
    except Exception as e:
        logger.critical(f"Unexpected error updating skill file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
