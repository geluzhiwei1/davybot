# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""用户级 Skills/Tools 配置 API。

提供 user 级 Skills/Tools 默认开关（per-user），存
``{DAWEI_HOME}/configs/{user_id}/skills_tools.json``。workspace 级配置
（``config.json`` 的 skills/tools 段）仍保留，可覆盖 user 默认。

是 Skills/Tools 分层（user 默认 + workspace 覆盖）的基础入口；
effective merge 端点与前端三态接入同 MCP/LLM 模式，可后续扩展。
"""

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from dawei import get_dawei_home
from dawei.api.auth import get_authenticated_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/skills-tools", tags=["User Skills/Tools"])

_DEFAULTS: dict[str, dict[str, Any]] = {
    "skills": {"enabled": True, "auto_discovery": True},
    "tools": {
        "builtin_tools_enabled": True,
        "system_tools_enabled": True,
        "user_tools_enabled": True,
        "workspace_tools_enabled": True,
    },
}


def _safe_uid(user_id: str | None) -> str:
    uid = user_id or "default_user"
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in uid)


def _config_file(user_id: str = "default_user") -> Path:
    return get_dawei_home() / "configs" / _safe_uid(user_id) / "skills_tools.json"


def _load(user_id: str = "default_user") -> dict[str, Any]:
    path = _config_file(user_id)
    if not path.exists():
        return {"skills": dict(_DEFAULTS["skills"]), "tools": dict(_DEFAULTS["tools"])}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load user skills/tools config: %s", e)
        return {"skills": dict(_DEFAULTS["skills"]), "tools": dict(_DEFAULTS["tools"])}


def _save(cfg: dict[str, Any], user_id: str = "default_user") -> None:
    path = _config_file(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def load_user_skills_tools(user_id: str = "default_user") -> dict[str, Any]:
    """供 effective merge 端点 / agent 桥接复用：读取 user 级 Skills/Tools 默认（per-user）。"""
    return _load(user_id)


class SkillsToolsConfig(BaseModel):
    skills: dict[str, Any] = Field(default_factory=lambda: dict(_DEFAULTS["skills"]))
    tools: dict[str, Any] = Field(default_factory=lambda: dict(_DEFAULTS["tools"]))


@router.get("", response_model=SkillsToolsConfig)
async def get_user_skills_tools(current_user: str = Depends(get_authenticated_user_id)):
    """获取用户级 Skills/Tools 默认配置"""
    cfg = _load(current_user)
    return SkillsToolsConfig(
        skills=cfg.get("skills", dict(_DEFAULTS["skills"])),
        tools=cfg.get("tools", dict(_DEFAULTS["tools"])),
    )


@router.put("", response_model=SkillsToolsConfig)
async def update_user_skills_tools(
    config: SkillsToolsConfig, current_user: str = Depends(get_authenticated_user_id)
):
    """更新用户级 Skills/Tools 默认配置"""
    _save(config.model_dump(), current_user)
    logger.info("User skills/tools config updated (user=%s)", current_user)
    return config
