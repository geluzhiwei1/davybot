# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Agent Profile 注册表（P3-0，对标 Codex `.codex/agents/` 与 Claude Code `.claude/agents/`）

- 内置角色：default（无限制）/ worker（执行）/ explorer（只读）
- 文件角色：`workspace/.dawei/agents/*.{json,toml}` > `~/.dawei/agents/*.{json,toml}`
  （JSON 为主，toml 兼容读取）
- resolve() 三层解析（高 > 低）：工具调用参数 > profile 文件 > 父任务配置
- 无 LLM / 无网络，纯数据模块，便于单测
"""

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from dawei.logg.logging import get_logger

logger = get_logger(__name__)

# explorer 角色禁用的写入/执行类工具（走 F4 既有过滤路径 + P3-1+ 运行时强制）
# 名字必须是注册表真实工具名（2026-09-17 核对：write_to_file/insert_content/
# smart_file_edit 为臆造名，实际注册名是 write_text_file/insert_text_content/
# smart_text_edit——此前 3/5 条目静默失效，只读约束部分为 no-op）
_EXPLORER_DENYLIST = [
    "execute_command",
    "shell_command",
    "write_text_file",
    "insert_text_content",
    "smart_text_edit",
    # 写入/执行面兜底：历史臆造名保留（防注册名回退/别名层）
    "write_to_file",
    "insert_content",
    "smart_file_edit",
]


@dataclass(frozen=True)
class AgentProfile:
    """子代理角色描述"""

    name: str
    description: str = ""
    developer_instructions: str = ""
    mode: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    sandbox_mode: str | None = None  # e.g. "read-only"
    tools_allowlist: list[str] | None = None
    tools_denylist: list[str] | None = None
    mcp_servers: list[str] | None = None
    skills: list[str] | None = None
    builtin: bool = False

    def to_metadata(self) -> dict[str, Any]:
        """写入 TaskData.metadata 的精简视图（None 字段省略）"""
        out: dict[str, Any] = {"agent": self.name}
        for key in (
            "mode",
            "model",
            "reasoning_effort",
            "sandbox_mode",
            "tools_allowlist",
            "tools_denylist",
            "mcp_servers",
            "skills",
        ):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        if self.developer_instructions:
            out["developer_instructions"] = self.developer_instructions
        return out


def _builtin_profiles() -> dict[str, AgentProfile]:
    return {
        "default": AgentProfile(name="default", description="无限制的通用子代理", builtin=True),
        "worker": AgentProfile(
            name="worker",
            description="执行型子代理（默认角色，无工具限制）",
            builtin=True,
        ),
        "explorer": AgentProfile(
            name="explorer",
            description="只读探索子代理：禁止一切写入/执行类工具",
            sandbox_mode="read-only",
            tools_denylist=list(_EXPLORER_DENYLIST),
            builtin=True,
        ),
    }


BUILTIN_PROFILES = _builtin_profiles()

# 文件加载缓存：{(agents_dir): (mtime_ns, {name: AgentProfile})}
_profile_cache: dict[str, tuple[int, dict[str, AgentProfile]]] = {}


def _parse_profile_file(path: Path) -> AgentProfile | None:
    """解析单个 profile 文件（json / toml）。失败返回 None（fast-fail 由调用方记录日志）。"""
    try:
        if path.suffix == ".json":
            raw = json.loads(path.read_text(encoding="utf-8"))
        else:  # toml 兼容
            import tomllib

            with path.open("rb") as f:
                raw = tomllib.load(f)
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Failed to parse agent profile {path}: {e}")
        return None

    if not isinstance(raw, dict) or not raw.get("name"):
        logger.error(f"Agent profile {path} missing required field 'name'")
        return None

    known = set(AgentProfile.__dataclass_fields__)
    data = {k: v for k, v in raw.items() if k in known}
    data["name"] = str(data["name"])
    if "description" not in data:
        data["description"] = ""
    if "developer_instructions" not in data:
        data["developer_instructions"] = ""
    try:
        return AgentProfile(**data)
    except TypeError as e:
        logger.exception(f"Invalid agent profile {path}: {e}")
        return None


def load_profiles(agents_dir: str | Path) -> dict[str, AgentProfile]:
    """加载某目录下全部 profile 文件（带 mtime 缓存），与内置角色合并（文件可覆盖内置）。"""
    agents_dir = Path(agents_dir)
    key = str(agents_dir)
    try:
        mtime = agents_dir.stat().st_mtime_ns
    except OSError:
        return dict(BUILTIN_PROFILES)

    cached = _profile_cache.get(key)
    if cached and cached[0] == mtime:
        return dict(cached[1])

    profiles = dict(BUILTIN_PROFILES)
    for f in sorted(agents_dir.iterdir()):
        if f.suffix not in (".json", ".toml") or not f.is_file():
            continue
        profile = _parse_profile_file(f)
        if profile:
            if profile.name in BUILTIN_PROFILES and not profile.builtin:
                logger.warning(f"Agent profile {f} overrides builtin '{profile.name}'")
            profiles[profile.name] = profile

    _profile_cache[key] = (mtime, dict(profiles))
    return profiles


def _home_agents_dir() -> Path:
    from dawei import get_dawei_home

    return Path(get_dawei_home()) / "agents"


def discover_profile_dirs(workspace_root: str | Path | None) -> list[Path]:
    """4 层优先级中的 agents 目录：workspace > user home。"""
    dirs = []
    if workspace_root:
        dirs.append(Path(workspace_root) / ".dawei" / "agents")
    dirs.append(_home_agents_dir())
    return dirs


def load_all_profiles(workspace_root: str | Path | None) -> dict[str, AgentProfile]:
    """按 workspace > home 优先级合并全部 profile。"""
    merged = dict(BUILTIN_PROFILES)
    for d in reversed(discover_profile_dirs(workspace_root)):
        merged.update(load_profiles(d))
    return merged


def apply_task_tool_filter(
    tools: list[dict],
    allow: list[str] | None = None,
    deny: list[str] | None = None,
) -> list[dict]:
    """P3-1: 对工具字典列表应用 profile 裁剪（走既有过滤链的最后一段）。

    - allowlist 非空 → 只保留白名单内工具（优先于 deny）
    - 否则 denylist 非空 → 剥离黑名单工具
    - 两者皆空 → 原样返回
    """
    if allow:
        allow_set = set(allow)
        return [t for t in tools if t.get("name") in allow_set]
    if deny:
        deny_set = set(deny)
        return [t for t in tools if t.get("name") not in deny_set]
    return tools


def task_tool_filter_from_metadata(metadata: dict[str, Any] | None) -> dict[str, list[str]] | None:
    """从 TaskData.metadata 提取 AgentProfile 写入的裁剪配置。

    Returns:
        {"allow": [...]} / {"deny": [...]}；未配置（空/缺失）返回 None。
    """
    if not metadata:
        return None
    allow = metadata.get("tools_allowlist")
    deny = metadata.get("tools_denylist")
    if allow:
        return {"allow": list(allow)}
    if deny:
        return {"deny": list(deny)}
    return None


def resolve(
    agent_name: str,
    call_args: dict[str, Any] | None = None,
    parent_task: Any = None,
    workspace_root: str | Path | None = None,
) -> AgentProfile:
    """三层解析：工具调用参数 > profile 文件 > 父任务配置。

    - 未知 agent 名：FAST FAIL 抛 ValueError（由工具层转为 LLM 可见错误）
    - call_args 可覆盖 model / reasoning_effort / sandbox_mode
    - parent_task（TaskNode）的 metadata.model / reasoning_effort 作为最低层默认
    """
    profiles = load_all_profiles(workspace_root)
    profile = profiles.get(agent_name)
    if profile is None:
        raise ValueError(
            f"Unknown agent '{agent_name}'. Available: {sorted(profiles.keys())}",
        )

    overrides: dict[str, Any] = {}

    # 第 3 层：父任务配置（最低优先级）
    if parent_task is not None:
        parent_meta = getattr(getattr(parent_task, "data", None), "metadata", None) or {}
        for key in ("model", "reasoning_effort", "sandbox_mode"):
            if getattr(profile, key) is None and parent_meta.get(key) is not None:
                overrides[key] = parent_meta[key]

    # 第 2 层：profile 文件（已含于 profile）

    # 第 1 层：工具调用参数（最高优先级）
    if call_args:
        for key in ("model", "reasoning_effort", "sandbox_mode", "mode"):
            if call_args.get(key) is not None:
                overrides[key] = call_args[key]

    return replace(profile, **overrides) if overrides else profile
