# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""MCP 工具管理器 - 实现 user/workspace 二级加载和管理机制
支持同名覆盖，优先级：workspace > user

使用真实的MCP Python SDK实现客户端连接和工具调用。
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from dawei.core.datetime_compat import UTC
from pathlib import Path
from typing import List, Dict, Any

from dawei import get_dawei_home
from dawei.core.decorators import safe_system_operation

# Import MCP SDK (required dependency)
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    ClientSession = None  # type: ignore
    StdioServerParameters = None  # type: ignore
    stdio_client = None  # type: ignore

# 用平台统一 get_logger：stderr + $DAWEI_HOME/logs/agentic/agentic.log 轮转文件。
# 此前裸 getLogger(__name__) 只输出到 stderr，sidecar/--reload 场景下日志丢失，
# MCP 连接失败时无法事后定位（FAST FAIL 违例）。
from dawei.logg.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 进程级 MCPToolManager 共享注册表
#
# 历史 BUG：WorkspaceContext.initialize() 期间创建的 MCP 工具类（use_mcp_tool 等）
# 在 ctx 尚未注册进 WorkspaceService._contexts 时实例化，_get_shared_mcp_manager()
# 查不到共享实例就各自 new 一个私有 manager —— 导致 connect_mcp_server 更新的是
# 实例 A 的状态，而 use_mcp_tool 校验的是实例 B（永远 disconnected）。
# 修复：所有按 (workspace_root, user_id) 的获取都走本注册表，保证同 key 同实例。
# ---------------------------------------------------------------------------
_MANAGER_REGISTRY: dict[tuple[str, str], "MCPToolManager"] = {}


def get_or_create_mcp_manager(workspace_root: "str | None", user_id: str = "default_user") -> "MCPToolManager":
    """按 (workspace_root, user_id) 获取进程内共享的 MCPToolManager（不存在则创建）。

    - workspace_root 为 None 时 key 首元素为 ""（用户级配置管理器）。
    - 与 WorkspaceContext.mcp_tool_manager、MCP 工具类 fallback、REST 层保持
      同 key 同实例，使 connect/disconnect/reload 状态对全体引用方立即可见。
    """
    key = (workspace_root or "", user_id or "default_user")
    mgr = _MANAGER_REGISTRY.get(key)
    if mgr is None:
        mgr = MCPToolManager(workspace_root=workspace_root, user_id=key[1])
        _MANAGER_REGISTRY[key] = mgr
        logger.info(f"MCPToolManager shared instance created: key={key!r}, registry_size={len(_MANAGER_REGISTRY)}")
    return mgr


# TUI 模式下 MCP 子进程 stderr 的落盘文件缓存（per-server，复用句柄避免重连泄漏 FD）
_TUI_MCP_ERRLOG_FILES: Dict[str, Any] = {}


def _tui_mcp_errlog(server_name: str) -> Any:
    """返回 stdio_client 的 errlog 目标。

    TUI 模式：Textual 独占终端，MCP 子进程（如 `uv run duckduckgo-mcp-server`
    的 "Resolving dependencies..." spinner）stderr 直写终端会破坏全屏渲染，
    重定向到 DAWEI_HOME/logs/mcp/<server>.stderr.log。
    非 TUI 模式：保持 SDK 默认（sys.stderr），行为不变。
    """
    import os as _os
    import sys

    if _os.environ.get("DAWEI_TUI_MODE") != "true":
        return sys.stderr

    fh = _TUI_MCP_ERRLOG_FILES.get(server_name)
    if fh is None or fh.closed:
        from dawei.config.logging_config import get_log_dir

        errlog_dir = get_log_dir() / "mcp"
        errlog_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in server_name)
        fh = (errlog_dir / f"{safe_name}.stderr.log").open("a", encoding="utf-8", errors="replace")
        _TUI_MCP_ERRLOG_FILES[server_name] = fh
    return fh


def _reset_manager_registry() -> None:
    """清空共享注册表（仅供测试隔离使用，不参与业务流程）。"""
    _MANAGER_REGISTRY.clear()


def _unwrap_exc_group(exc: BaseException) -> BaseException:
    """逐层剥开 ExceptionGroup，露出真实子异常。

    anyio 结构化并发把单点失败包成 ``ExceptionGroup``，其 str() 只剩
    "unhandled errors in a TaskGroup (1 sub-exception)" —— 真实原因被吞掉。
    连接/调用失败路径必须先 unwrap 再记录与上抛（FAST FAIL）。
    """
    seen: set[int] = set()
    while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        if id(exc) in seen:  # 防御：异常环（理论不可达）
            break
        seen.add(id(exc))
        exc = exc.exceptions[0]
    return exc


@dataclass
class MCPConfig:
    """MCP配置类 - 从 user_workspace.py 转移过来"""

    server_name: str
    command: str
    args: List[str] = field(default_factory=list)
    cwd: str | None = None
    env: Dict[str, str] = field(default_factory=dict)
    transport: str = "stdio"  # stdio | sse | http | local(本机 relay 透传)
    url: str | None = None  # sse/http 传输的端点
    headers: Dict[str, str] = field(default_factory=dict)  # sse/http 自定义头
    always_allow: List[str] = field(default_factory=list)
    timeout: int = 300
    source_level: str = "user"  # user, workspace
    disabled: bool = False  # 禁用的 server 仍加载到 _servers（供展示/统计），但连接层跳过

    @staticmethod
    def _expand_path(value: str) -> str:
        """展开路径串中的 $VAR/${VAR} 与 ~（对齐 MCP 生态惯例）。

        未定义的 $VAR 原样保留（FAST FAIL 时可在错误里看到原始引用）。
        """
        import os
        from pathlib import Path

        return str(Path(os.path.expandvars(value)).expanduser())

    @classmethod
    def from_dict(
        cls,
        server_name: str,
        config_dict: Dict[str, Any],
        source_level: str = "user",
    ) -> "MCPConfig":
        """从字典创建MCP配置（command/args/cwd 展开 $VAR/~，如
        `${PAPER_SEARCH_MCP_HOME}`；env 值原样透传不展开）。"""
        return cls(
            server_name=server_name,
            command=cls._expand_path(config_dict.get("command", "")),
            args=[cls._expand_path(a) if isinstance(a, str) else a for a in config_dict.get("args", [])],
            cwd=cls._expand_path(config_dict["cwd"]) if config_dict.get("cwd") else None,
            env=config_dict.get("env", {}),
            transport=config_dict.get("transport", "stdio"),
            url=config_dict.get("url"),
            headers=config_dict.get("headers", {}),
            always_allow=config_dict.get("alwaysAllow", []),
            timeout=config_dict.get("timeout", 300),
            source_level=source_level,
            disabled=config_dict.get("disabled", False),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "server_name": self.server_name,
            "command": self.command,
            "args": self.args,
            "cwd": self.cwd,
            "env": self.env,
            "transport": self.transport,
            "url": self.url,
            "headers": self.headers,
            "always_allow": self.always_allow,
            "timeout": self.timeout,
            "source_level": self.source_level,
            "disabled": self.disabled,
        }

    def merge_with(self, other: "MCPConfig") -> "MCPConfig":
        """与另一个配置合并，other 的值会覆盖当前值"""
        if not other:
            return self

        # 创建新的配置，other 的非空字段覆盖 self 的字段
        merged = MCPConfig.from_dict(self.server_name, self.to_dict(), self.source_level)

        for key, value in other.to_dict().items():
            if key != "server_name" and value is not None and value not in ("", [], {}):
                setattr(merged, key, value)

        # 更新 source_level 为更高优先级的配置
        merged.source_level = other.source_level

        return merged


@dataclass
class MCPServerInfo:
    """MCP服务器信息"""

    name: str
    config: MCPConfig
    status: str = "disconnected"  # disconnected, connecting, connected, error
    last_error: str | None = None
    tools: List[Dict[str, Any]] = field(default_factory=list)
    resources: List[Dict[str, Any]] = field(default_factory=list)
    connected_at: datetime | None = None
    session: Any = None  # ClientSession instance
    read_stream: Any = None  # Read stream for stdio_client
    write_stream: Any = None  # Write stream for stdio_client
    client_context: Any = None  # stdio_client context manager

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "config": self.config.to_dict(),
            "status": self.status,
            "last_error": self.last_error,
            "tools": self.tools,
            "resources": self.resources,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
        }


class MCPConfigLoader:
    """MCP配置加载器"""

    def __init__(self):
        self._cache: Dict[str, Dict[str, MCPConfig]] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        self._cache_ttl = 300  # 5分钟缓存

    def _get_cache_key(self, level: str, path: str | None = None) -> str:
        """获取缓存键"""
        return f"mcp_{level}:{path or 'default'}"

    def _is_cache_valid(self, cache_key: str) -> bool:
        """检查缓存是否有效"""
        if cache_key not in self._cache_timestamps:
            return False

        age = (datetime.now(UTC) - self._cache_timestamps[cache_key]).total_seconds()
        return age < self._cache_ttl

    def _set_cache(self, cache_key: str, configs: Dict[str, MCPConfig]):
        """设置缓存"""
        self._cache[cache_key] = configs
        self._cache_timestamps[cache_key] = datetime.now(UTC)

    def _get_cache(self, cache_key: str) -> Dict[str, MCPConfig] | None:
        """获取缓存"""
        if self._is_cache_valid(cache_key):
            return self._cache.get(cache_key)
        return None

    @safe_system_operation("load_user_mcp_configs", fallback_value={})
    def load_user_mcp_configs(self, user_id: str = "default_user") -> Dict[str, MCPConfig]:
        """加载用户级MCP配置（per-user：configs/{user_id}/mcp.json，不迁移旧全局 mcp.json）。"""
        safe_uid = "".join(c if c.isalnum() or c in "-_" else "_" for c in (user_id or "default_user"))
        dawei_home = get_dawei_home()
        user_config_dir = dawei_home / "configs" / safe_uid

        if not user_config_dir.exists():
            logger.debug(f"User config directory not found: {user_config_dir}")
            return {}

        cache_key = self._get_cache_key(f"user:{safe_uid}", str(user_config_dir))
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        configs = {}
        mcp_config_file = user_config_dir / "mcp.json"

        if mcp_config_file.exists():
            with Path(mcp_config_file).open(encoding="utf-8") as f:
                config_data = json.load(f)

            if "mcpServers" in config_data:
                for server_name, server_config in config_data["mcpServers"].items():
                    configs[server_name] = MCPConfig.from_dict(server_name, server_config, "user")

            logger.info(f"Loaded {len(configs)} user MCP configs from {mcp_config_file}")

        self._set_cache(cache_key, configs)
        return configs

    @safe_system_operation("load_workspace_mcp_configs", fallback_value={})
    def load_workspace_mcp_configs(self, workspace_path: str) -> Dict[str, MCPConfig]:
        """加载工作区级MCP配置"""
        workspace_dir = Path(workspace_path)
        # 保持与用户配置目录一致的路径结构
        user_config_dir = workspace_dir / ".dawei" / "configs"

        if not user_config_dir.exists():
            logger.debug(f"Workspace config directory not found: {user_config_dir}")
            return {}

        cache_key = self._get_cache_key("workspace", str(user_config_dir))
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        configs = {}
        # 使用与用户配置相同的路径结构：mcp.json
        mcp_config_file = user_config_dir / "mcp.json"

        if mcp_config_file.exists():
            with Path(mcp_config_file).open(encoding="utf-8") as f:
                config_data = json.load(f)

            if "mcpServers" in config_data:
                for server_name, server_config in config_data["mcpServers"].items():
                    configs[server_name] = MCPConfig.from_dict(
                        server_name,
                        server_config,
                        "workspace",
                    )

            logger.info(f"Loaded {len(configs)} workspace MCP configs from {mcp_config_file}")

        self._set_cache(cache_key, configs)
        return configs

    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.info("MCP config cache cleared")


class MCPToolManager:
    """MCP工具管理器 - 实现二级加载和管理机制 (user, workspace)"""

    def __init__(self, workspace_root: str | None = None, user_id: str = "default_user"):
        self.workspace_root = workspace_root
        self.user_id = user_id or "default_user"
        self.loader = MCPConfigLoader()

        # 二级配置缓存
        self._user_configs: Dict[str, MCPConfig] = {}
        self._workspace_configs: Dict[str, MCPConfig] = {}
        # 本机 relay stub 配置（dawei/tools/mcp_relay.py，light-app 壳注册面；
        # transport="local"，优先级最低：user/workspace 同名配置可覆盖）
        self._local_configs: dict[str, MCPConfig] = {}

        # 合并后的配置
        self._merged_configs: Dict[str, MCPConfig] = {}

        # 服务器信息
        self._servers: Dict[str, MCPServerInfo] = {}

        # 连接宿主 task（bug#5 修复）：anyio 要求 transport/session 上下文的
        # 进入与退出发生在同一 task；长连接由常驻 owner task 持有，
        # connect 只等 ready 事件，disconnect 只发 stop 信号。
        self._owner_tasks: Dict[str, Any] = {}
        self._stop_events: Dict[str, Any] = {}

        # 初始化配置
        self._load_all_configs()

    @safe_system_operation("load_all_mcp_configs")
    def _load_all_configs(self):
        """加载所有级别的配置"""
        # 按优先级顺序加载（用户级 per-user）
        self._user_configs = self.loader.load_user_mcp_configs(self.user_id)

        if self.workspace_root:
            self._workspace_configs = self.loader.load_workspace_mcp_configs(self.workspace_root)

        # 本机 relay stub（light-app 壳注册的本机 server 影子配置）。
        # 注册表是进程内存态，读取零 IO；失败静默（无壳在线 = 空 face）。
        try:
            from dawei.tools.mcp_relay import get_relay_registry

            self._local_configs = get_relay_registry().get_stub_configs(self.user_id)
        except Exception:  # noqa: BLE001 — stub 面获取失败不阻断文件配置加载
            logger.debug("relay stub configs unavailable", exc_info=True)
            self._local_configs = {}

        # 合并配置
        self._merge_configs()

        # 初始化服务器信息
        self._initialize_servers()

        logger.info(f"MCPToolManager initialized with {len(self._merged_configs)} total servers")

    def _merge_configs(self):
        """合并二级配置，支持同名服务器的完全覆盖"""
        self._merged_configs.clear()

        # 按优先级顺序合并：user -> workspace -> local relay stub
        # 后面的会完全覆盖前面的同名配置。

        # 1. 从 user 开始
        for name, config in self._user_configs.items():
            self._merged_configs[name] = config
            logger.debug(f"Added user MCP config: {name}")

        # 2. 合并 workspace 配置（完全覆盖 user）
        for name, config in self._workspace_configs.items():
            if name in self._merged_configs:
                logger.debug(f"Overriding MCP config '{name}' with workspace config")
            else:
                logger.debug(f"Added workspace MCP config: {name}")
            self._merged_configs[name] = config

        # 3. 本机 relay stub 优先级最高（完全覆盖同名配置）。
        # 产品决策：SaaS 端不运行 MCP 进程，本机 MCP 唯一运行时是 light-app 壳。
        # 壳在线（注册了 stub）时，user/workspace 的同名 stdio 配置一律让位——
        # 否则 market 资源包落盘的占位符命令（如 ${PAPER_SEARCH_MCP_HOME}）
        # 会在后端被当 stdio 启动并秒败（Connection closed）。
        # 壳离线时 stub 为空，user/workspace 配置自然生效（离线回退）。
        for name, config in self._local_configs.items():
            if name in self._merged_configs:
                logger.debug(f"Overriding MCP config '{name}' with local relay stub")
            self._merged_configs[name] = config

        # 统计覆盖情况
        override_count = 0
        for name in self._merged_configs:
            sources = self.get_config_sources(name)
            if sum(sources.values()) > 1:  # 如果配置存在于多个级别
                override_count += 1

        logger.info(
            f"Merged MCP configurations: {len(self._merged_configs)} servers, {override_count} overridden",
        )

    def _initialize_servers(self):
        """初始化服务器信息"""
        self._servers.clear()

        for name, config in self._merged_configs.items():
            self._servers[name] = MCPServerInfo(name=name, config=config, status="disconnected")

    def _refresh_relay_stubs(self) -> None:
        """connect 前重取 relay stub，修复共享管理器的陈旧配置快照。

        共享管理器按 (workspace_root, user_id) 进程级长存，构造时 light-app
        壳可能尚未注册（或晚注册）本机 server——快照里同名配置停留在
        user/workspace 的 stdio 版本。此处零 IO 重取注册表，并以最高优先级
        覆盖（对齐 _merge_configs 的 stub 优先语义），不依赖管理器重建时机。
        已连接的 server 不动（避免撕裂活跃会话）。
        """
        try:
            from dawei.tools.mcp_relay import get_relay_registry

            stubs = get_relay_registry().get_stub_configs(self.user_id)
        except Exception:  # noqa: BLE001 — 刷新失败保持现状，不阻断 connect
            logger.debug("relay stub refresh unavailable", exc_info=True)
            return

        self._local_configs = stubs
        changed = False
        for name, cfg in stubs.items():
            info = self._servers.get(name)
            if info is None:
                self._merged_configs[name] = cfg
                self._servers[name] = MCPServerInfo(name=name, config=cfg, status="disconnected")
                changed = True
            elif info.status != "connected" and info.config is not cfg and info.config.transport != "local":
                self._merged_configs[name] = cfg
                info.config = cfg
                changed = True
        if changed:
            logger.info(f"Relay stubs refreshed (local-priority applied): {sorted(stubs)}")

    def set_workspace_root(self, workspace_root: str):
        """设置工作区路径并重新加载配置"""
        self.workspace_root = workspace_root
        self._workspace_configs = self.loader.load_workspace_mcp_configs(workspace_root)
        self._merge_configs()
        self._initialize_servers()
        logger.info(f"Workspace root set to {workspace_root}, MCP configs reloaded")

    def get_all_configs(self) -> Dict[str, MCPConfig]:
        """获取所有合并后的MCP配置"""
        return self._merged_configs.copy()

    def get_config(self, server_name: str) -> MCPConfig | None:
        """获取指定服务器的MCP配置"""
        return self._merged_configs.get(server_name)

    def get_config_sources(self, server_name: str) -> Dict[str, bool]:
        """获取MCP配置来源信息"""
        return {
            "local": server_name in self._local_configs,
            "user": server_name in self._user_configs,
            "workspace": server_name in self._workspace_configs,
        }

    def get_config_override_info(self, server_name: str) -> Dict[str, Any]:
        """获取MCP配置覆盖的详细信息"""
        sources = self.get_config_sources(server_name)
        active_source = None

        # 确定当前活跃的来源（按优先级：local relay stub > workspace > user）
        if sources["local"]:
            active_source = "local"
        elif sources["workspace"]:
            active_source = "workspace"
        elif sources["user"]:
            active_source = "user"

        # 获取各级配置
        configs = {}
        if sources["local"]:
            configs["local"] = self._local_configs[server_name].to_dict()
        if sources["user"]:
            configs["user"] = self._user_configs[server_name].to_dict()
        if sources["workspace"]:
            configs["workspace"] = self._workspace_configs[server_name].to_dict()

        return {
            "server_name": server_name,
            "sources": sources,
            "active_source": active_source,
            "configs": configs,
            "is_overridden": sum(sources.values()) > 1,
        }

    def get_all_override_info(self) -> List[Dict[str, Any]]:
        """获取所有MCP配置的覆盖信息"""
        override_info = []

        for server_name in self._merged_configs:
            info = self.get_config_override_info(server_name)
            if info["is_overridden"]:
                override_info.append(info)

        return override_info

    def get_server_info(self, server_name: str) -> MCPServerInfo | None:
        """获取服务器信息"""
        return self._servers.get(server_name)

    def get_all_servers(self) -> Dict[str, MCPServerInfo]:
        """获取所有服务器信息"""
        return self._servers.copy()

    def get_servers_by_status(self, status: str) -> List[MCPServerInfo]:
        """按状态获取服务器"""
        return [server for server in self._servers.values() if server.status == status]

    @safe_system_operation("connect_mcp_server", fallback_value=False)
    async def connect_server(self, server_name: str) -> bool:
        """连接MCP服务器"""
        if not MCP_AVAILABLE:
            logger.error("MCP SDK is not installed. Install with: pip install mcp")
            return False

        # 陈旧快照修复：共享管理器长存，壳注册晚于构造时在此补齐/覆盖，
        # 再判断 server 是否存在（晚注册的 relay server 也应可连）。
        self._refresh_relay_stubs()

        if server_name not in self._servers:
            logger.error(f"Server '{server_name}' not found")
            return False

        server_info = self._servers[server_name]
        config = server_info.config

        if config.disabled:
            logger.info(f"MCP server '{server_name}' is disabled, skip connecting")
            return False

        logger.info(f"Connecting to MCP server: {server_name}")
        server_info.status = "connecting"
        server_info.last_error = None

        try:
            # Build filtered environment for MCP subprocess (strip sensitive keys)
            import os as _os
            _SENSITIVE_PREFIXES = (
                "DAWEI_SUPER_MODE", "JWT_SECRET", "JWT_", "API_KEY",
                "OPENAI_API_KEY", "DASHSCOPE_API_KEY", "ANTHROPIC_API_KEY",
                "LLM_EMBEDDING_API_KEY", "DATABASE_URL", "REDIS_URL",
                "REDIS_PASSWORD", "MONGODB_URI", "MONGODB_PASSWORD",
                "NEO4J_PASSWORD", "SECRET", "TOKEN", "PASSWORD",
                "CREDENTIAL", "PRIVATE_KEY", "AWS_ACCESS_KEY", "AWS_SECRET_KEY",
            )
            _mcp_env = {}
            for _k, _v in _os.environ.items():
                if not _k.upper().startswith(_SENSITIVE_PREFIXES):
                    _mcp_env[_k] = _v
            # 叠加 per-server config.env（用户显式配置，全量传，不剥敏感前缀，覆盖进程值）
            if config.env:
                _mcp_env = {**_mcp_env, **config.env}

            # 按 transport 选择 client context（stdio 用 command+env；sse/http 用
            # url+headers；local 经本机 relay 透传，不 spawn/直连任何进程）
            transport = (config.transport or "stdio").lower()
            if transport == "stdio":
                server_params = StdioServerParameters(
                    command=config.command,
                    args=config.args,
                    cwd=config.cwd,
                    env=_mcp_env,
                )
            elif transport not in ("sse", "http", "local"):
                raise ValueError(f"Unsupported MCP transport: {transport}")

            # 重连前先清理旧 owner（若有）
            await self._teardown_owner(server_name, reason="reconnect")

            import asyncio as _asyncio

            ready = _asyncio.Event()
            stop = _asyncio.Event()
            conn: Dict[str, Any] = {}

            async def _owner():
                """连接宿主 task（bug#5 修复核心）。

                anyio 结构化并发要求 transport/session 上下文的进入与退出发生在
                同一 task：由本 task 独占持有上下文直至 stop 事件。旧实现手动
                __aenter__ 后从未进入 ClientSession 上下文（receive loop 未启动，
                initialize 永远等不到响应），且跨 task __aexit__ 触发
                "cancel scope exited in a different task"。失败原因写入 conn。
                """
                try:
                    if transport == "stdio":
                        from mcp.client.stdio import stdio_client as _stdio_client

                        cm = _stdio_client(server_params, errlog=_tui_mcp_errlog(server_name))
                    elif transport == "sse":
                        from mcp.client.sse import sse_client

                        cm = sse_client(config.url, headers=config.headers or None)
                    elif transport == "local":
                        # 本机 relay：JSON-RPC 帧经 claim/result 长轮询透传给
                        # light-app 壳里的 stdio 子进程（dawei/tools/mcp_relay.py）。
                        # 壳离线时 __aenter__ 即抛 ConnectionError（FAST FAIL）。
                        from dawei.tools.mcp_relay import local_relay_client

                        cm = local_relay_client(server_name, self.user_id, timeout=config.timeout)
                    else:
                        from mcp.client.streamable_http import streamable_http_client

                        cm = streamable_http_client(config.url, headers=config.headers or None)

                    async with cm as (read_stream, write_stream):
                        async with ClientSession(read_stream, write_stream) as session:
                            await session.initialize()
                            conn["session"] = session
                            ready.set()
                            await stop.wait()
                except Exception as e:  # 初始化失败：记录原因，让上下文在本 task 内正常退出
                    # FAST FAIL：anyio 会把失败包成 ExceptionGroup（str 只剩
                    # "unhandled errors in a TaskGroup"），先剥开拿到真实原因，
                    # 再带完整 traceback 落日志（get_logger → agentic.log 持久化）。
                    real = _unwrap_exc_group(e)
                    conn["error"] = real
                    logger.error(
                        f"MCP connect '{server_name}' initialization failed: {real!r}",
                        exc_info=True,
                    )
                    ready.set()

            owner_task = _asyncio.create_task(_owner())
            self._owner_tasks[server_name] = owner_task
            self._stop_events[server_name] = stop

            # 有界等待 initialize 完成（FAST FAIL：默认 30s）
            connect_timeout = 30
            try:
                await _asyncio.wait_for(ready.wait(), timeout=connect_timeout)
            except _asyncio.TimeoutError:
                server_info.status = "error"
                server_info.last_error = f"connect timeout after {connect_timeout}s (initialize no response)"
                logger.error(f"MCP connect '{server_name}' timed out after {connect_timeout}s")
                await self._teardown_owner(server_name, reason="connect-timeout")
                return False

            if "error" in conn:
                raise conn["error"]

            session = conn["session"]
            server_info.session = session
            server_info.status = "connected"
            server_info.connected_at = datetime.now(UTC)

            # List available tools（有界）
            tools_response = await _asyncio.wait_for(session.list_tools(), timeout=15)
            server_info.tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                }
                for tool in tools_response.tools
            ]

            # List available resources（有界，失败不阻断连接）
            try:
                resources_response = await _asyncio.wait_for(session.list_resources(), timeout=15)
                server_info.resources = [
                    {
                        "uri": resource.uri,
                        "name": resource.name,
                        "description": resource.description,
                        "mime_type": resource.mimeType,
                    }
                    for resource in resources_response.resources
                ]
            except Exception as e:
                logger.warning(f"Failed to list resources for {server_name}: {e}")
                server_info.resources = []

            logger.info(f"Successfully connected to MCP server: {server_name} ({len(server_info.tools)} tools, {len(server_info.resources)} resources)")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to MCP server {server_name}: {e}", exc_info=True)
            server_info.status = "error"
            server_info.last_error = str(e)

            # Clean up owner task on error（上下文退出由 owner task 自身完成）
            try:
                await self._teardown_owner(server_name, reason="connect-error")
            except Exception:
                pass
            server_info.session = None
            server_info.read_stream = None
            server_info.write_stream = None
            server_info.client_context = None

            return False

    async def _teardown_owner(self, server_name: str, reason: str = "teardown"):
        """停掉并回收连接宿主 task（上下文退出在 owner task 自身完成）。

        先发 stop 事件让上下文正常退出；超时（5s）则 cancel task。
        所有异常内部吞掉（清理路径不抛错）。
        """
        import asyncio as _asyncio

        task = self._owner_tasks.pop(server_name, None)
        stop = self._stop_events.pop(server_name, None)

        if stop is not None:
            try:
                stop.set()
            except Exception:
                pass

        if task is None or task.done():
            return

        logger.debug(f"Tearing down MCP owner task for '{server_name}' ({reason})")
        try:
            await _asyncio.wait_for(task, timeout=5)
        except _asyncio.TimeoutError:
            task.cancel()
            try:
                await _asyncio.wait_for(task, timeout=5)
            except BaseException:
                pass
        except _asyncio.CancelledError:
            # 本方法自身被取消：确保 owner task 也被取消再传播
            task.cancel()
            raise
        except BaseException:
            pass  # owner task 内部异常已在 conn 记录；避免 "exception never retrieved"

        if not task.cancelled() and task.done():
            try:
                _ = task.exception()
            except BaseException:
                pass

    @safe_system_operation("disconnect_mcp_server", fallback_value=False)
    async def disconnect_server(self, server_name: str) -> bool:
        """断开MCP服务器连接"""
        if not MCP_AVAILABLE:
            logger.error("MCP SDK is not installed. Install with: pip install mcp")
            return False

        if server_name not in self._servers:
            logger.error(f"Server '{server_name}' not found")
            return False

        server_info = self._servers[server_name]

        logger.info(f"Disconnecting from MCP server: {server_name}")

        try:
            # 停掉 owner task：上下文（transport/session）在其自身 task 内退出，
            # 不再跨 task 调 __aexit__（旧实现触发 anyio "cancel scope in a
            # different task" + BrokenResourceError）
            await self._teardown_owner(server_name, reason="disconnect")

            # Clear streams and session
            server_info.read_stream = None
            server_info.write_stream = None
            server_info.session = None
            server_info.client_context = None

            # Update status
            server_info.status = "disconnected"
            server_info.connected_at = None
            server_info.tools.clear()
            server_info.resources.clear()

            logger.info(f"Successfully disconnected from MCP server: {server_name}")
            return True

        except Exception as e:
            logger.error(f"Error disconnecting from MCP server {server_name}: {e}", exc_info=True)
            server_info.last_error = str(e)
            return False

    async def connect_all_servers(self) -> Dict[str, bool]:
        """连接所有服务器"""
        results = {}

        for server_name in self._servers:
            results[server_name] = await self.connect_server(server_name)

        return results

    async def auto_connect_all(self) -> None:
        """自动连接全部未连接且未 disabled 的 server（best-effort，不抛出）。

        背景（2026-09-18）：MCP 工具一级注入（mcp__ 前缀）依赖 server 处于
        connected 状态；此前无任何自动连接路径（仅 agent 手动
        connect_mcp_server / REST 端点），导致已配置 server（如 paper-search）
        的工具永不进入会话工具面。已连接的跳过（connect_server 会重连，
        避免无谓 churn）。

        FAST FAIL：connect_server 内部吞掉全部异常（safe_system_operation +
        catch-all，落 status="error"/last_error 后返回 False），因此必须检查
        返回值——否则会出现"失败却记 auto-connected"的假成功日志。
        """
        # 循环快照前先刷新 relay stub：本方法常在会话工具面构建时触发，
        # 此时壳可能刚注册（如 paper-search），陈旧快照会把同名 server
        # 当 stdio 连接而秒败。
        self._refresh_relay_stubs()
        for server_name, info in list(self._servers.items()):
            cfg = self._merged_configs.get(server_name)
            if cfg is None or getattr(cfg, "disabled", False):
                continue
            if getattr(info, "status", "") == "connected":
                continue
            try:
                ok = await self.connect_server(server_name)
            except Exception as e:  # noqa: BLE001 — 理论不可达（connect_server 不抛），双保险
                logger.warning(f"[MCP] auto-connect '{server_name}' raised: {e}")
                continue
            if ok:
                logger.info(f"[MCP] auto-connected '{server_name}'")
            else:
                logger.warning(f"[MCP] auto-connect '{server_name}' failed: {getattr(info, 'last_error', None) or 'see error logs above'}")

    async def disconnect_all_servers(self) -> Dict[str, bool]:
        """断开所有服务器连接"""
        results = {}

        for server_name in self._servers:
            results[server_name] = await self.disconnect_server(server_name)

        return results

    def reload_configs(self):
        """重新加载所有配置（同步，不清理已连接子进程）。

        注意：同步版本无法 await disconnect，已连接 server 的子进程引用会被 _initialize_servers
        清空丢弃。推荐在 async 上下文（如 API 端点）使用 areload_configs()。
        """
        # best-effort：同步路径无法等待 owner task 退出，至少发 cancel
        # 让上下文在下一轮 loop 迭代退出，避免孤儿连接 task。
        for name, task in list(self._owner_tasks.items()):
            if not task.done():
                task.cancel()
        self._owner_tasks.clear()
        self._stop_events.clear()
        self.loader.clear_cache()
        self._load_all_configs()
        logger.info("All MCP configurations reloaded")

    async def areload_configs(self):
        """重新加载所有配置（async 版本，先断开已连接 server 再重载，避免孤儿子进程）。

        供 MCP CRUD 端点调用——改配置后让本 manager（及其所有引用方）立即看到新配置。
        """
        try:
            await self.disconnect_all_servers()
        except Exception as e:
            logger.warning(f"disconnect before reload failed (best-effort): {e}")
        self.loader.clear_cache()
        self._load_all_configs()
        logger.info("All MCP configurations reloaded (async, disconnected stale first)")

    def get_statistics(self) -> Dict[str, Any]:
        """获取MCP统计信息"""
        # 统计覆盖情况
        override_info = self.get_all_override_info()
        overridden_configs = len(override_info)

        # 统计服务器状态
        status_counts = {}
        for server in self._servers.values():
            status = server.status
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_servers": len(self._merged_configs),
            "overridden_configs": overridden_configs,
            "by_source_level": {
                "local": len(self._local_configs),
                "user": len(self._user_configs),
                "workspace": len(self._workspace_configs),
            },
            "by_status": status_counts,
            "override_summary": {
                "total_overridden": overridden_configs,
                "override_details": override_info[:5],  # 只显示前5个覆盖详情
            },
        }

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用MCP工具

        Args:
            server_name: MCP服务器名称
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP SDK is not installed. Install with: pip install mcp")

        # MCP 安全策略（域6）：allow/deny 服务器（override-or-inherit）。
        # MCP 工具本身为 critical 风险，审批门在 ToolExecutor 层覆盖；此处仅门控服务器。
        try:
            from dawei.core.security_manager import security_manager

            mcp_policy = security_manager.get_policy().mcp
            if server_name in mcp_policy.denied_mcp_servers:
                try:
                    from dawei.core.security_auditor import security_auditor

                    security_auditor.log(
                        "security.mcp.denied",
                        server=server_name,
                        tool=tool_name,
                        reason="denied_servers",
                    )
                except Exception:
                    pass
                raise PermissionError(
                    f"MCP server '{server_name}' denied by security policy (denied_mcp_servers)"
                )
            if mcp_policy.allowed_mcp_servers and server_name not in mcp_policy.allowed_mcp_servers:
                raise PermissionError(
                    f"MCP server '{server_name}' not in allowed MCP servers"
                )
        except PermissionError:
            raise
        except Exception as e:
            logger.warning(f"MCP policy check failed for {server_name}: {e}; allowing")

        server_info = self.get_server_info(server_name)
        if not server_info:
            raise ValueError(f"MCP server '{server_name}' not found")

        if server_info.status != "connected":
            raise RuntimeError(f"MCP server '{server_name}' is not connected (status: {server_info.status})")

        if not server_info.session:
            raise RuntimeError(f"MCP server '{server_name}' has no active session")

        try:
            logger.info(f"Calling MCP tool: {server_name}.{tool_name} with arguments: {arguments}")

            # Call the tool（有界超时：config.timeout 秒，防挂起拖垮会话）
            import asyncio as _asyncio

            call_timeout = max(1, int(getattr(server_info.config, "timeout", 300) or 300))
            result = await _asyncio.wait_for(
                server_info.session.call_tool(tool_name, arguments), timeout=call_timeout
            )

            # 结果转 JSON 安全结构（CallToolResult 是 pydantic 对象，直接
            # json.dumps 会 TypeError——历史上调用从未成功过，故未暴露）
            try:
                result_payload = result.model_dump(mode="json")
            except Exception:
                result_payload = repr(result)

            logger.info(f"MCP tool {server_name}.{tool_name} executed successfully")
            return {
                "server_name": server_name,
                "tool_name": tool_name,
                "arguments": arguments,
                "status": "success",
                "result": result_payload,
            }

        except Exception as e:
            logger.error(f"Failed to call MCP tool {server_name}.{tool_name}: {e}", exc_info=True)
            err_text = str(e)
            # 自愈重试(2026-09-20):壳/子进程在引擎会话存活期间重启时,新子进程
            # 未收到 initialize,严格 MCP SDK 把未初始化请求一律误报为
            # -32602 "Invalid request parameters"(与真实参数错误同文案,线上
            # task 42c05231 根因;壳侧已加生命周期门禁,此处为纵深防御)。
            # 断开重连一次(全新 ClientSession 会重新 initialize 并刷新工具面),
            # 重试一次;仍失败才返回错误。FAST FAIL:只重试一次,不做重试风暴。
            if any(
                s in err_text
                for s in ("Invalid request parameters", "not initialized", "Not initialized")
            ):
                logger.warning(
                    f"[MCP] '{server_name}' lifecycle-style error ({err_text}); reconnecting once and retrying"
                )
                try:
                    await self.disconnect_server(server_name)
                    await self.connect_server(server_name)
                    server_info = self.get_server_info(server_name)
                    if server_info and server_info.session:
                        result = await _asyncio.wait_for(
                            server_info.session.call_tool(tool_name, arguments), timeout=call_timeout
                        )
                        try:
                            result_payload = result.model_dump(mode="json")
                        except Exception:
                            result_payload = repr(result)
                        logger.info(
                            f"MCP tool {server_name}.{tool_name} succeeded after reconnect-retry"
                        )
                        return {
                            "server_name": server_name,
                            "tool_name": tool_name,
                            "arguments": arguments,
                            "status": "success",
                            "result": result_payload,
                        }
                except Exception as e2:
                    logger.error(f"Reconnect-retry for {server_name}.{tool_name} failed: {e2}")
            return {
                "server_name": server_name,
                "tool_name": tool_name,
                "arguments": arguments,
                "status": "error",
                "error": err_text,
            }

    async def access_resource(self, server_name: str, uri: str) -> Dict[str, Any]:
        """访问MCP资源

        Args:
            server_name: MCP服务器名称
            uri: 资源URI

        Returns:
            资源内容
        """
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP SDK is not installed. Install with: pip install mcp")

        server_info = self.get_server_info(server_name)
        if not server_info:
            raise ValueError(f"MCP server '{server_name}' not found")

        if server_info.status != "connected":
            raise RuntimeError(f"MCP server '{server_name}' is not connected (status: {server_info.status})")

        if not server_info.session:
            raise RuntimeError(f"MCP server '{server_name}' has no active session")

        try:
            logger.info(f"Accessing MCP resource: {server_name}:{uri}")

            # Read the resource（有界超时，防挂起）
            import asyncio as _asyncio

            result = await _asyncio.wait_for(server_info.session.read_resource(uri), timeout=60)

            # 结果转 JSON 安全结构（同 call_tool）
            try:
                resource_payload = result.model_dump(mode="json")
            except Exception:
                resource_payload = repr(result)

            logger.info(f"MCP resource {server_name}:{uri} accessed successfully")
            return {
                "server_name": server_name,
                "uri": uri,
                "status": "success",
                "resource": resource_payload,
            }

        except Exception as e:
            logger.error(f"Failed to access MCP resource {server_name}:{uri}: {e}", exc_info=True)
            return {
                "server_name": server_name,
                "uri": uri,
                "status": "error",
                "error": str(e),
            }

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "workspace_root": self.workspace_root,
            "configs": {name: config.to_dict() for name, config in self._merged_configs.items()},
            "servers": {name: server.to_dict() for name, server in self._servers.items()},
            "statistics": self.get_statistics(),
        }
