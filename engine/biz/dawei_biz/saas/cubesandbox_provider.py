# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""CubeSandboxProvider — CubeSandbox (腾讯 MicroVM) 硬件级沙箱 (§沙箱系统升级 v2 — Phase 2)

原名 E2BProvider — SaaS 沙箱方案 §3.3 重命名为 CubeSandboxProvider,
保留 E2BProvider 作为别名以保证后向兼容 (Phase 1d 重命名)。

特性:
- F1: TrustedContext 强制校验
- F2: tmpfs 遮蔽 .dawei/ — fail-closed + 启动后验证
- F3: workspace_path 三层白名单校验 (委托 path_validator.py)
- §4: per-user / 全局配额 + LRU 淘汰
- N1: WebSocket 断连 grace 期 + 命令队列
- N2: pause 策略 (auto_resume / reject / queue)
- N3: 命令读写分类 (ro 模式预拦截)
- N4: eBPF 网络策略加载
- N6: PiiSafeLogger 集成
- SaaS: WorkspaceStore SDK 同步 (rustfs; 2026-09-22 实装: 本地↔Store↔沙箱
  双向同步替代 s3fs 挂载方案, 工作区 host-mount 不再是硬依赖)

依赖: e2b Python SDK (pip install e2b) — 延迟导入, 不可用时 provider_factory 自动降级
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dawei.core.exceptions import (
    QuotaExceededError,
    SandboxPausedError,
    SandboxSecurityError,
    SandboxTimeoutError,
)
from dawei.sandbox.base import (
    GlobalQuota,
    IsolationLevel,
    PausePolicy,
    ResourceQuota,
    SandboxCapabilities,
    SandboxProvider,
    SandboxResult,
    TrustedContext,
    UserId,
)
from dawei.sandbox.command_classifier import CommandRisk, classify_command
from dawei_biz.saas.e2b_compat import e2b_supports_network_policy
from dawei.sandbox.path_validator import validate_workspace_path
from dawei.sandbox.pii_logger import PiiSafeLogger

# WorkspaceStore 是可选依赖 (SaaS), 缺类时不挂载
try:
    from dawei.sandbox.workspace_store import get_workspace_store  # noqa: F401

    _HAS_WORKSPACE_STORE = True
except ImportError:
    _HAS_WORKSPACE_STORE = False

logger = PiiSafeLogger(logging.getLogger(__name__))


# ================================================================
# 数据结构
# ================================================================


@dataclass
class SandboxSession:
    """单个沙箱会话状态"""

    sandbox: Any  # E2BSandbox 实例 (e2b SDK 对象)
    user_id: UserId
    workspace_id: str
    mount_mode: str  # "ro" | "rw"
    # rustfs 链路 (2026-09-22): 销毁时兜底回拉需要 Store key 与本地路径;
    # virtiofs 链路不填, 保持空串
    workspace_key: str = ""
    workspace_path: str = ""
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    is_paused: bool = False


@dataclass
class CommandQueueEntry:
    """grace 期内排队的命令"""

    command: str
    ctx: TrustedContext
    enqueued_at: float
    future: asyncio.Future


# ================================================================
# CubeSandboxProvider
# ================================================================


class CubeSandboxProvider(SandboxProvider):
    """CubeSandbox (腾讯) 硬件级沙箱 Provider

    隔离级别: HARDWARE (KVM MicroVM)
    适用场景: SaaS 云端 / 本地 CubeSandbox 集群

    文件模式:
    - virtiofs: 本地 CubeSandbox, 零拷贝挂载 (推荐)
    - SDK 上传: 备用, 远程 E2B Cloud 不可挂载时使用
    - SaaS virtiofs: workspace_path = s3fs 挂载点 (Phase 1a)

    会话生命周期:
    - 按会话复用沙箱 (非每次创建/销毁)
    - 空闲 pause → 超时 destroy
    - WebSocket 断连 → grace 期 → 重连排空队列 / 超时销毁
    """

    def __init__(self, config: dict[str, Any] | None = None):
        # None-safe: __init__ 内多处直接用 config.get (签名允许 None, 2026-09-23 冒烟踩雷)
        config = config or {}
        self.config = config

        # E2B SDK 配置
        self.template_id = os.environ.get("DAWEI_SANDBOX_TEMPLATE", "code-interpreter")
        self.api_url = os.environ.get("DAWEI_SANDBOX_API_URL", "")
        # E2B SDK 要求 API key 格式为 e2b_ + hex; CubeSandbox auth 关闭时用占位符
        self.api_key = os.environ.get(
            "E2B_API_KEY",
            os.environ.get("DAWEI_SANDBOX_API_KEY", "e2b_0000000000000000000000000000000000000000"),
        )
        self.sync_strategy = self.config.get("sync_strategy", "auto")  # virtiofs | sdk | auto

        # 超时配置 (env DAWEI_SANDBOX_COMMAND_TIMEOUT 可覆盖缺省 30s;
        # SandboxFacade 不传 config, 长命令 pip/npm 需在部署侧调高)
        self.default_timeout = config.get(
            "default_timeout",
            int(os.environ.get("DAWEI_SANDBOX_COMMAND_TIMEOUT", "30")),
        )
        # 单命令超时上限: 工具入参 timeout 只能在此范围内生效 (防任意大值)
        self.max_timeout = config.get(
            "max_timeout",
            int(os.environ.get("DAWEI_SANDBOX_COMMAND_TIMEOUT_MAX", "600")),
        )

        # === Option B (2026-09-14): 沙箱内 agent 命令以非 root 运行 ===
        # virtiofs 不做 uid 映射, VM 内 uid 原样落到宿主: VM root 写的文件
        # 在宿主是 root:root, backend (非 root) 无法删除/覆盖 → 2026-09-14
        # "删除文件 500" 事故 (shutil.rmtree EACCES on unzip_out)。
        # DAWEI_SANDBOX_RUN_USER 为空 = 关闭 (root, 旧行为);
        # uid/gid 缺省与 backend 进程自身对齐 (os.getuid/getgid)。
        # 创建期探针失败会自动禁用并回退 root (大声 warning)。
        self.run_user = os.environ.get("DAWEI_SANDBOX_RUN_USER", "").strip()
        self.run_uid = int(
            os.environ.get("DAWEI_SANDBOX_RUN_UID", str(getattr(os, "getuid", lambda: 1000)())),
        )
        self.run_gid = int(
            os.environ.get("DAWEI_SANDBOX_RUN_GID", str(getattr(os, "getgid", lambda: 1000)())),
        )
        if self.run_user and not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", self.run_user):
            logger.warning(
                "[E2B] DAWEI_SANDBOX_RUN_USER=%r 不是合法用户名, 非 root 运行已禁用",
                self.run_user,
            )
            self.run_user = ""
        self.idle_pause_seconds = config.get("idle_pause", 300)  # 5 min → pause
        self.idle_destroy_seconds = config.get("idle_destroy", 1800)  # 30 min → destroy

        # 会话管理
        self._sessions: dict[str, SandboxSession] = {}

        # 配额
        self.user_quota = ResourceQuota(
            max_concurrent_sandboxes=config.get("max_sessions_per_user", 10),
            max_total_memory_mb=config.get("max_memory_per_user_mb", 5120),
            max_sandboxes_per_workspace=config.get("max_sandboxes_per_workspace", 1),
            max_commands_per_minute=config.get("max_commands_per_minute", 120),
        )
        self.global_quota = GlobalQuota(
            max_total_sandboxes=config.get("max_total_sessions", 1000),
            max_total_memory_mb=config.get("max_total_memory_mb", 102400),
        )
        self.estimated_memory_per_sandbox_mb = 5  # CubeSandbox 公开数据

        # 速率限制: user_id → [timestamps]
        self._rate_limiter: dict[str, list[float]] = {}

        # Pause 策略
        self.pause_policy = PausePolicy(
            config.get("pause_policy", "auto_resume"),
        )

        # N1: WebSocket grace 期
        # 【2026-09-23 demo.normnomos.com 事故修复】默认 60s 过短: 用户切 tab/
        # 网络抖动断开 60s 后沙箱即被销毁, 下次工具调用重建沙箱 + pip 重装依赖
        # (~126s) → 叠加 330s 工具等待上限, 任务必死 (list_files 338.68s 超时被杀)。
        # 新默认 600s ≥ ws_manager 的 300s 重连取消窗口 (DAWEI_WS_TASK_CANCEL_DELAY),
        # 保证"断开→重连"全程沙箱存活, 重连后依赖免重装、排空队列即恢复。
        # env DAWEI_SANDBOX_DISCONNECT_GRACE 可覆盖; 0 = 立即销毁 (旧行为)。
        try:
            _grace_env = float(os.environ.get("DAWEI_SANDBOX_DISCONNECT_GRACE", "600"))
        except ValueError:
            _grace_env = 600
        self.disconnect_grace_seconds = config.get("disconnect_grace", _grace_env)
        self._pending_commands: dict[str, list[CommandQueueEntry]] = {}
        self._scheduled_destroy: dict[str, float] = {}
        self._disconnected: dict[str, bool] = {}

        # N4: 网络策略
        self._network_policy: dict[str, Any] | None = None

        # === rustfs 链路 (2026-09-22): SaaS 工作区走 Store SDK 同步 ===
        # WorkspaceStore 就绪且后端非 local (rustfs/minio/s3) 时:
        # 沙箱不再 host-mount 工作区 (dawei-src 只读挂载保留),
        # 创建后 本地→Store→沙箱 推送, 命令成功后 沙箱→Store→本地 回拉。
        # 显式配置 S3 后端但初始化失败 → 大声 ERROR + 回退 virtiofs
        # (BASE_DIR 守卫保证 virtiofs 路径在 CubeMaster 白名单内, 降级可见非静默)。
        self._workspace_store = None
        self._use_store_sync = False
        self._init_workspace_store()

    def _init_workspace_store(self) -> None:
        """初始化 WorkspaceStore; 仅非 local 后端启用 SDK 同步链路"""
        try:
            from dawei.sandbox.workspace_store import LocalBackend, get_workspace_store

            store = get_workspace_store()
        except Exception as e:
            logger.exception(
                "[E2B] WorkspaceStore 初始化失败 (WORKSPACE_STORE_* 配置异常?), 工作区回退 virtiofs host-mount: %s",
                e,
            )
            return
        if isinstance(store.backend, LocalBackend):
            logger.info(
                "[E2B] WorkspaceStore 后端为 local, 工作区走 virtiofs host-mount",
            )
            return
        self._workspace_store = store
        self._use_store_sync = True
        logger.info(
            "[E2B] WorkspaceStore 就绪 (backend=%s), 工作区走 Store SDK 同步 (rustfs)",
            type(store.backend).__name__,
        )

    # ================================================================
    # SandboxProvider 接口实现
    # ================================================================

    def prewarm_session(self, ctx: TrustedContext) -> None:
        """预热沙箱会话 (P1)

        在首次 execute_command 之前主动创建沙箱, 消除冷启动延迟。
        - 幂等: 已存在则直接返回
        - 失败: 抛异常, 由 SandboxFacade 决定是否回退 lazy
        - 不执行任何用户命令
        """
        key = self._session_key(ctx)
        if key in self._sessions:
            logger.debug("[E2B] prewarm 跳过 (会话已存在): %s", ctx.workspace_id)
            return
        # 触发与 execute_command 相同的创建路径
        self._get_or_create_session(key, ctx)
        logger.info("[E2B] 沙箱预热完成: %s", ctx.workspace_id)

    def execute_command(
        self,
        command: str,
        ctx: TrustedContext,
        timeout: int | None = None,
    ) -> SandboxResult:
        """同步执行命令

        流程: 配额检查 → 会话获取/创建 → pause 策略 → 命令分类 → 执行

        timeout: 工具层传入的每命令超时 (秒); None = 用部署侧缺省。
            用户 security.json 显式配置 commandExecutionTimeout 时，
            对显式入参取 min 作为 per-user 上限 (2026-09-22 接活前端
            「执行超时」字段; 未配置 = 不限制, 不会把无配置用户扣到
            模型缺省 30s)。最终仍受部署侧 max_timeout clamp。
        """
        timeout = self._cap_timeout_by_policy(timeout, ctx)
        self._check_quota(ctx)
        key = self._session_key(ctx)

        # === 情形 1: 会话存在且活跃 ===
        if key in self._sessions and not self._disconnected.get(key, False):
            return self._execute_on_session(key, command, ctx, timeout=timeout)

        # === 情形 2: 会话断开但在 grace 期内 → 直接在存活沙箱上执行 ===
        # 【2026-09-23 修复】旧逻辑: 入队死等重连 (wait_for future, 最长 grace 秒),
        # grace 期内不重连则整段等待作废 (SandboxTimeoutError) — grace 提到 600s 后
        # 这等于让工具任务干等 10 分钟然后失败。命令执行本身不依赖 WS
        # (结果同步返回 tool_executor), 只有进度推送依赖; WS 侧已有
        # 断开延迟取消 + 重连接管 (websocket/manager._rebind_workspace_tasks)。
        # 因此 grace 期内沙箱还活着就直接执行, FAST FAIL 优于排队干等。
        if self._disconnected.get(key, False):
            destroy_at = self._scheduled_destroy.get(key, 0)
            if time.time() < destroy_at and key in self._sessions:
                logger.info(
                    "[E2B] grace 期内命令直接执行 (沙箱存活): %s", key,
                )
                return self._execute_on_session(key, command, ctx, timeout=timeout)
            # grace 期已过
            self._cleanup_disconnected_session(key)

        # === 情形 3: 创建新会话 ===
        return self._create_and_execute(key, command, ctx, timeout=timeout)

    async def execute_command_async(
        self,
        command: str,
        ctx: TrustedContext,
        timeout: int | None = None,
    ) -> SandboxResult:
        """异步执行命令 — 通过 asyncio.to_thread 包装"""
        return await asyncio.to_thread(self.execute_command, command, ctx, timeout)

    def _resolve_timeout(self, timeout: int | None) -> int:
        """合并工具入参 timeout 与部署缺省, 并 clamp 到 [1, max_timeout]"""
        effective = int(timeout) if timeout and int(timeout) > 0 else self.default_timeout
        return max(1, min(effective, self.max_timeout))

    def _cap_timeout_by_policy(self, timeout: int | None, ctx: TrustedContext) -> int | None:
        """按用户显式配置的 commandExecutionTimeout 收紧入参 timeout。

        - timeout 为 None/<=0: 不动 (走部署缺省, 无配置用户零影响)
        - 读取失败: 不限制 (与 _resolve_mount_mode 同为静默降级, 只留日志)
        """
        if not timeout or int(timeout) <= 0:
            return timeout
        try:
            from dawei.core.security_manager import security_manager

            cap = security_manager.get_user_command_timeout_cap(ctx.user_id)
            if cap > 0 and int(timeout) > cap:
                logger.info(
                    "[E2B] 用户 %s 显式超时上限 %ss 生效 (请求 %ss → %ss)",
                    ctx.user_id,
                    cap,
                    timeout,
                    cap,
                )
                return cap
        except Exception as e:
            logger.warning("[E2B] 读取用户超时上限失败 (user=%s), 不限制: %s", ctx.user_id, e)
        return timeout

    def health_check(self) -> bool:
        """健康检查 — 探测 E2B API 是否可达"""
        if not self.api_url:
            return False
        try:
            from dawei.sandbox.provider_factory import _check_e2b_available

            return _check_e2b_available(self.api_url)
        except Exception:
            return False

    def get_capabilities(self) -> SandboxCapabilities:
        """能力声明"""
        return SandboxCapabilities(
            isolation_level=IsolationLevel.HARDWARE,
            supports_network=True,
            supports_filesystem=True,
            supports_resource_limits=True,
            supports_pause=True,
            max_timeout=300,
            cold_start_ms=60,
        )

    # ================================================================
    # 会话管理
    # ================================================================

    def _session_key(self, ctx: TrustedContext) -> str:
        """生成会话 key: user_id::workspace_id"""
        return f"{ctx.user_id}::{ctx.workspace_id}"

    def _get_or_create_session(self, key: str, ctx: TrustedContext) -> SandboxSession:
        """获取或创建沙箱会话"""
        if key in self._sessions:
            return self._sessions[key]

        # F3: 校验 workspace_path
        validated_path = validate_workspace_path(ctx.workspace_path, str(ctx.workspace_id))

        # 确定挂载模式: 按 ctx.user_id 每会话解析 (2026-09-13 修复)
        # Provider 是进程级单例, 若在无用户上下文的请求中创建 (如 providers 探测端点),
        # provider_factory 的兜底 "ro" 会被烤进单例 config, 此后所有会话都变只读挂载
        # (症状: F2 mount_script touch /workspace/.dawei/settings.json → Read-only file system)
        mount_mode = self._resolve_mount_mode(ctx)

        # 创建沙箱
        sandbox = self._create_sandbox(validated_path, mount_mode, ctx)

        session = SandboxSession(
            sandbox=sandbox,
            user_id=ctx.user_id,
            workspace_id=str(ctx.workspace_id),
            mount_mode=mount_mode,
            workspace_key=ctx.workspace_key,
            workspace_path=str(validated_path),
        )
        self._sessions[key] = session
        logger.info(
            "[E2B] 沙箱已创建: %s (mode=%s)",
            ctx.workspace_id,
            mount_mode,
        )
        return session

    def _resolve_mount_mode(self, ctx: TrustedContext) -> str:
        """按用户解析工作区挂载模式 (ro/rw/none)。

        显式传 user_id 读取 per-user security.json, 不依赖 contextvar;
        读取失败时回退 Provider 创建时的 config (fail-closed 语义不变)。
        """
        try:
            from dawei.core.security_manager import security_manager

            settings = security_manager.get_user_settings(user_id=ctx.user_id)
            mode = (settings.workspace_mount_mode or "").lower()
            if mode in ("ro", "rw", "none"):
                return mode
            logger.warning(
                "[E2B] 用户 %s 配置了未知挂载模式 %r, 回退 Provider config",
                ctx.user_id,
                mode,
            )
        except Exception as e:
            logger.warning(
                "[E2B] 读取用户挂载模式失败 (user=%s), 回退 Provider config: %s",
                ctx.user_id,
                e,
            )
        return self.config.get("workspace_mount_mode", "rw")

    def _create_sandbox(
        self,
        workspace_path: Path,
        mount_mode: str,
        ctx: TrustedContext,
    ) -> Any:
        """创建 E2B 沙箱实例

        选择策略: virtiofs (本地) / sdk (远程)
        """
        return self._create_with_virtiofs(workspace_path, mount_mode, ctx)

    def _create_with_virtiofs(
        self,
        workspace_path: Path,
        mount_mode: str,
        ctx: TrustedContext,
    ) -> Any:
        """通过 virtiofs 挂载创建沙箱 (F2: tmpfs fail-closed, P2: 细粒度遮蔽)

        P2 变更: 不再全遮蔽 .dawei/, 改为对敏感子目录/文件分别遮蔽。
        - 敏感目录 (chat-history/conversations/checkpoints/evolution 等): tmpfs 遮蔽
        - 敏感文件 (settings.json/team.json 等): /dev/null bind-mount 覆盖
        - 放行: .dawei/files/ (用户上传), .dawei/agents/, .dawei/skills/

        步骤:
        1. 创建 MicroVM, 挂载 workspace 到 /workspace
        2. 对每个敏感目录 mount tmpfs; 对每个敏感文件 bind-mount /dev/null
        3. 启动后验证每个敏感条目都被遮蔽
        """
        try:
            from e2b import Sandbox as E2BSandbox
        except ImportError:
            try:
                from e2b_sandbox import Sandbox as E2BSandbox
            except ImportError as e:
                raise SandboxSecurityError(
                    "E2B SDK 不可用, 请安装: pip install e2b",
                ) from e

        # 创建沙箱 + virtiofs 挂载
        sandbox = E2BSandbox.create(
            template=self.template_id,
            api_key=self.api_key,
            **self._build_mount_config(workspace_path, mount_mode, ctx),
        )

        # === P2/F2 步骤 1: 细粒度遮蔽 (fail-closed) ===
        mount_script = self._build_f2_mount_script()
        result = sandbox.commands.run(mount_script, timeout=15)
        if hasattr(result, "exit_code") and result.exit_code != 0:
            try:
                sandbox.kill()
            except Exception:
                pass
            stderr = getattr(result, "stderr", "unknown")
            raise SandboxSecurityError(
                f"P2 细粒度遮蔽失败 (exit={result.exit_code}): {stderr}",
            )

        # === P2/F2 步骤 2: 启动后立即验证每个敏感条目 ===
        verify_cmd = self._build_f2_verify_cmd()
        verify = sandbox.commands.run(verify_cmd, timeout=10)
        verify_stdout = getattr(verify, "stdout", "")
        if "OK" not in verify_stdout or "LEAK" in verify_stdout:
            try:
                sandbox.kill()
            except Exception:
                pass
            raise SandboxSecurityError(
                f"P2 遮蔽验证失败, 沙箱已销毁: {verify_stdout}",
            )

        # === P2/F2 步骤 3: 验证 tmpfs 实际挂载 (抽查首个敏感目录) ===
        first_sensitive_dir = self.SENSITIVE_DAWEI_DIRS[0]
        mount_check = sandbox.commands.run(
            f"mount | grep -E 'tmpfs on /workspace/.dawei/{first_sensitive_dir}' || echo NOT_MOUNTED",
            timeout=5,
        )
        check_stdout = getattr(mount_check, "stdout", "")
        if "NOT_MOUNTED" in check_stdout:
            try:
                sandbox.kill()
            except Exception:
                pass
            raise SandboxSecurityError(
                f"tmpfs 实际未挂载到 /workspace/.dawei/{first_sensitive_dir}, 沙箱已销毁",
            )

        logger.info(
            "[E2B] virtiofs 沙箱已创建: %s (%s), .dawei/ 细粒度遮蔽已验证 (敏感: %d 目录 + %d 文件, 放行: files/agents/skills)",
            ctx.workspace_id,
            mount_mode,
            len(self.SENSITIVE_DAWEI_DIRS),
            len(self.SENSITIVE_DAWEI_FILES),
        )

        # === P3: 确保 dawei 源码可用 + 安装缺失依赖 ===
        self._ensure_dawei_available(sandbox, ctx)

        # === Fix #2 (2026-09-14): 补装常用命令 (模板缺 zip/bzip2/xz/wget/git/file/jq) ===
        self._install_common_tools(sandbox)

        # === rustfs 链路 (2026-09-22): 本地 → Store → 沙箱 推送 ===
        # 必须在 _setup_run_user 之前: SDK files.write 以 envd 身份(root)落盘,
        # 随后的 uid 归档治理 (chown heal) 才能把推送产物归到 run-user 名下。
        if self._use_store_sync:
            self._sync_workspace_into_sandbox(sandbox, workspace_path, ctx)

        # === Option B (2026-09-14): 建 run-user + 历史文件归档治理 (uid 对齐) ===
        self._setup_run_user(sandbox, mount_mode)

        return sandbox

    def _sync_workspace_into_sandbox(
        self,
        sandbox: Any,
        workspace_path: Path,
        ctx: TrustedContext,
    ) -> None:
        """rustfs 链路: 本地 → Store → 沙箱 (无 host-mount)

        顺序: 先推送后打 marker —— 推送产物 mtime 早于 marker,
        pull (find -newer marker) 只捕获会话内新变更, 避免全量回传。

        FAST FAIL: 本地有文件但一个都没推上去 (errors>0 且 uploaded==0)
        时抛异常 —— rustfs 显式启用却静默空工作区跑任务 = 错数据。
        """
        store = self._workspace_store
        up_stats = store.sync_local_to_store(ctx.workspace_key, workspace_path)
        push_stats = store.push_to_sandbox(sandbox, ctx.workspace_key)
        store.init_marker(sandbox)
        logger.info(
            "[E2B] 工作区 Store 同步完成 (key=%s): local→store=%s, store→sandbox=%s",
            ctx.workspace_key,
            up_stats.as_dict(),
            push_stats.as_dict(),
        )
        if up_stats.errors > 0:
            logger.warning(
                "[E2B] local→store 存在失败文件 (%d 个), 沙箱内可能缺文件",
                up_stats.errors,
            )
            if up_stats.uploaded == 0:
                raise RuntimeError(
                    f"WorkspaceStore 同步完全失败 (uploaded=0, errors={up_stats.errors}): workspace_key={ctx.workspace_key}, 检查 WORKSPACE_STORE_* 配置与 rustfs 可用性",
                )

    def _ensure_dawei_available(self, sandbox: Any, ctx: TrustedContext) -> None:
        """P3: 确保沙箱内可以 import dawei 并运行工具

        步骤:
        1. 验证 /opt/dawei-src 挂载存在 (源码可读)
        2. 检查关键 Python 依赖是否已安装, 缺失则 pip install
        3. 验证 dawei 可导入

        失败时不抛异常 (仅 warning), 因为:
        - 非工具命令 (execute_command) 不需要 dawei
        - 工具路由失败在 saas 模式下 fail-fast (ToolExecutor 不再回落宿主),
          错误信息会作为 tool 结果返回给 LLM 自行调整
        ⚠️ 所有 commands.run 必须保证 exit 0 (哨兵化): e2b SDK 对非零
        退出码直接抛 CommandExitException, 会穿透本函数的不阻断设计。
        """
        # 1. 验证源码挂载
        check_mount = sandbox.commands.run(
            f"test -f {self.DAWEI_SRC_MOUNT_PATH}/dawei/__init__.py && echo OK || echo MISSING",
            timeout=5,
        )
        if "MISSING" in getattr(check_mount, "stdout", ""):
            logger.warning(
                "[E2B] %s/dawei/__init__.py 不存在, 源码挂载可能失败",
                self.DAWEI_SRC_MOUNT_PATH,
            )
            return

        # 2. 检查并安装缺失依赖
        # 构建检查命令: 对每个包尝试 import, 收集缺失的
        # 2026-09-14 实测闭包 (web02 探针): import dawei 需要以下全部包;
        # 模板 tpl-e7ea6ec5 只预装了 pydantic/fitz/openpyxl 之外的基础件
        import_checks = []
        import_map = {
            "python-dotenv": "dotenv",
            "pydantic": "pydantic",
            "pydantic-settings": "pydantic_settings",
            "aiohttp": "aiohttp",
            "aiofiles": "aiofiles",
            "PyMuPDF": "fitz",
            "python-docx": "docx",
            "openpyxl": "openpyxl",
        }
        for pip_name, import_name in import_map.items():
            import_checks.append(
                f"python3 -c 'import {import_name}' 2>/dev/null || echo 'MISSING:{pip_name}'",
            )

        check_cmd = "; ".join(import_checks)
        dep_result = sandbox.commands.run(check_cmd, timeout=30)
        dep_stdout = getattr(dep_result, "stdout", "")

        missing = [line.split("MISSING:")[1].strip() for line in dep_stdout.splitlines() if "MISSING:" in line]

        if missing:
            deps_str = " ".join(missing)
            logger.info(
                "[E2B] 沙箱内缺失依赖, 正在安装: %s",
                deps_str,
            )
            # 哨兵化保证 exit 0: e2b SDK 对非零退出码直接抛 CommandExitException,
            # 会穿透整个创建链路 (设计本意是 warning + 不阻断, 见 docstring)
            # 【2026-09-14 镜像修复】部署网络实测 pypi.org 完全不可达 (25s 超时),
            # aliyun 镜像 1.4s 可达 —— 不加 -i 时 pip 挂死直至 e2b 180s 超时,
            # 连带工具任务 60s 超时连环失败 (2026-09-14 E2E 实测三次重试全灭)。
            install_result = sandbox.commands.run(
                f"pip install -i https://mirrors.aliyun.com/pypi/simple/ {deps_str} 2>&1 || echo __PIP_FAILED__",
                timeout=180,
            )
            install_stdout = getattr(install_result, "stdout", "")
            if "__PIP_FAILED__" in install_stdout:
                logger.warning(
                    "[E2B] 依赖安装失败: %s. 工具沙箱路由将不可用",
                    install_stdout[-300:],
                )
            else:
                logger.info("[E2B] 依赖安装完成: %s", deps_str)
        else:
            logger.debug("[E2B] 沙箱内依赖完整, 无需安装")

        # 3. 验证 dawei 可导入 (哨兵化: 失败仅 warning, 不抛异常)
        # python -c 内用双引号, 避免与外层单引号冲突
        verify_cmd = f"PYTHONPATH={self.DAWEI_SRC_MOUNT_PATH} python3 -c \"import dawei, dawei.sandbox.tool_runner; print('IMPORT_OK')\" 2>&1 || echo __IMPORT_FAILED__"
        verify_result = sandbox.commands.run(verify_cmd, timeout=15)
        verify_stdout = getattr(verify_result, "stdout", "").strip()
        if "__IMPORT_FAILED__" in verify_stdout or "Error" in verify_stdout or "Traceback" in verify_stdout:
            logger.warning(
                "[E2B] 沙箱内 import dawei 失败: %s. 工具沙箱路由将回退到宿主执行",
                verify_stdout[:200],
            )
        else:
            logger.info(
                "[E2B] 沙箱内 dawei 可用 (tool_runner import ok)",
            )

    # ================================================================
    # Fix #2 (2026-09-14): 常用命令补装
    # ================================================================

    # Debian 12 模板 (tpl-e7ea6ec5) 预装 unzip/zipinfo/tar/gzip/gunzip/curl;
    # 缺以下命令 (2026-09-14 探针实测)。默认 apt 源不可达 (同 pypi.org 症状),
    # aliyun 镜像可达 —— 与 pip 同策略。
    COMMON_APT_TOOLS: str = "zip bzip2 xz-utils wget git file jq"
    _APT_ALIYUN_LIST = "/etc/apt/sources.list.d/dawei-aliyun.list"

    def _install_common_tools(self, sandbox: Any) -> None:
        """best-effort 补装常用命令 (zip/bzip2/xz/wget/git/file/jq)

        - 全部已装则跳过 (幂等, 常见路径只花一次 command -v 的 ~0.2s)
        - 失败仅 warning 不阻断 (哨兵化保证 exit 0, 同 _ensure_dawei_available);
          缺命令时 agent 会收到真实 "command not found" 可自行兜底
          (如 python3 -m zipfile), 比误报好得多
        """
        try:
            probe = sandbox.commands.run(
                f"command -v {' '.join(self.COMMON_APT_TOOLS.split())} >/dev/null 2>&1 && echo ALL_PRESENT || echo SOME_MISSING",
                timeout=5,
            )
            if "ALL_PRESENT" in getattr(probe, "stdout", ""):
                logger.debug("[E2B] 常用命令齐全, 跳过 apt 安装")
                return

            install_cmd = f"sh -c 'echo \"deb https://mirrors.aliyun.com/debian/ bookworm main\" > {self._APT_ALIYUN_LIST} && apt-get update -qq && apt-get install -y -qq {self.COMMON_APT_TOOLS}' 2>&1 || echo __TOOLS_FAILED__"
            result = sandbox.commands.run(install_cmd, timeout=180)
            stdout = getattr(result, "stdout", "")
            if "__TOOLS_FAILED__" in stdout:
                logger.warning(
                    "[E2B] 常用命令补装失败 (不阻断): %s",
                    stdout[-300:],
                )
            else:
                logger.info("[E2B] 常用命令补装完成: %s", self.COMMON_APT_TOOLS)
        except Exception as e:
            logger.warning("[E2B] 常用命令补装异常 (不阻断): %s", e)

    # ================================================================
    # Option B (2026-09-14): 非 root 运行 + uid 对齐
    # ================================================================

    def _setup_run_user(self, sandbox: Any, mount_mode: str) -> None:
        """沙箱内以非 root 用户运行 agent 命令, uid/gid 与宿主 backend 对齐

        根因: virtiofs 无 uid 映射, VM uid 原样落宿主。此前 agent 命令以
        root 跑, 产物 (unzip_out 等) 在宿主是 root:root, backend (work/1001)
        删除/覆盖即 EACCES (2026-09-14 "删除文件 500" 事故)。

        本方法在 root 引导 (F2 遮蔽 / pip / apt) 完成后执行:
        1. VM 内建用户: uid/gid 取 self.run_uid/run_gid (缺省 = backend 自身);
           若该 uid 已存在 (如模板预装 user@1000) 则直接复用其用户名
        2. 归档治理: /workspace 下非该 uid 的历史文件就地 chown (仅 rw 挂载)
        3. SDK 探针: commands.run("id -u", user=...) 验证 e2b user 参数真实生效
           (防 envd 静默忽略 user 仍以 root 执行)

        任一步失败 → 禁用 (self.run_user="") + 大声 warning, 回退 root 旧行为。
        代价 (有意为之): agent 的 apt install 等需 root 的命令会收到真实
        EACCES —— fail-fast, 由 LLM 自行换路 (如 pip --user)。
        """
        if not self.run_user:
            return
        try:
            # --- 步骤 1: 建/复用 uid 对齐用户 (哨兵化保证 exit 0) ---
            setup_cmd = (
                f"RUN_UID={self.run_uid}; RUN_GID={self.run_gid}; RUN_USER={self.run_user}; "
                'EXISTS=$(getent passwd "$RUN_UID" | cut -d: -f1); '
                'if [ -n "$EXISTS" ]; then echo "RUN_USER_READY:$EXISTS"; exit 0; fi; '
                'groupadd -g "$RUN_GID" "$RUN_USER" 2>/dev/null; '
                'useradd -m -u "$RUN_UID" -g "$RUN_GID" -s /bin/bash "$RUN_USER" 2>&1; '
                'AFTER=$(getent passwd "$RUN_UID" | cut -d: -f1); '
                'if [ -n "$AFTER" ]; then echo "RUN_USER_READY:$AFTER"; '
                "else echo __RUN_USER_FAILED__; fi"
            )
            result = sandbox.commands.run(setup_cmd, timeout=15)
            stdout = getattr(result, "stdout", "")
            ready_name = ""
            for line in stdout.splitlines():
                if line.startswith("RUN_USER_READY:"):
                    ready_name = line.split(":", 1)[1].strip()
            if not ready_name:
                self.run_user = ""
                logger.warning(
                    "[E2B] run-user 创建失败, 非 root 运行已禁用 (回退 root): %s",
                    stdout[-300:],
                )
                return
            if ready_name != self.run_user:
                logger.info(
                    "[E2B] uid %d 已有用户 %r, 复用 (不叫 %r)",
                    self.run_uid,
                    ready_name,
                    self.run_user,
                )
                self.run_user = ready_name

            # --- 步骤 2: 历史文件归档治理 (仅 rw; ro 挂载 chown 必 EROFS) ---
            if mount_mode == "rw":
                heal_cmd = f"find /workspace -xdev -not -uid {self.run_uid} -exec chown -h {self.run_uid}:{self.run_gid} {{}} + 2>/dev/null; echo HEAL_DONE"
                sandbox.commands.run(heal_cmd, timeout=60)
                logger.info(
                    "[E2B] workspace 历史 root 落盘文件已 chown → uid %d (归档治理)",
                    self.run_uid,
                )

            # --- 步骤 3: SDK user 参数探针 (防 envd 静默忽略) ---
            probe = sandbox.commands.run(
                "id -u && id -g",
                user=self.run_user,
                timeout=10,
            )
            probe_stdout = getattr(probe, "stdout", "").split()
            if probe_stdout[:2] == [str(self.run_uid), str(self.run_gid)]:
                logger.info(
                    "[E2B] agent 命令将以 %r (uid=%d) 运行, 与宿主 backend 对齐",
                    self.run_user,
                    self.run_uid,
                )
            else:
                self.run_user = ""
                logger.warning(
                    "[E2B] user 参数探针不匹配 (期望 uid/gid=%d/%d, 实际 %r), 非 root 运行已禁用 (回退 root) —— 检查 CubeSandbox envd 是否支持 exec user",
                    self.run_uid,
                    self.run_gid,
                    probe_stdout,
                )
        except Exception as e:
            self.run_user = ""
            logger.warning(
                "[E2B] run-user 初始化异常, 非 root 运行已禁用 (回退 root): %s",
                e,
            )

    def _run_user_kwargs(self) -> dict[str, str]:
        """commands.run 的 user= 参数 (未启用时为空 dict, 行为与旧版完全一致)"""
        if not self.run_user:
            return {}
        return {"user": self.run_user}

    # ================================================================
    # P2: F2 细粒度遮蔽配置与脚本生成
    # ================================================================

    # 敏感目录: 沙箱内不可见 (tmpfs 遮蔽)
    # 包含会话历史、对话记录、检查点、调度任务等
    # configs/ (2026-09-14): 含 mcp.json 等凭据文件, 沙箱内命令可直接读取 → 必须遮蔽
    SENSITIVE_DAWEI_DIRS: tuple[str, ...] = (
        "chat-history",
        "conversations",
        "checkpoints",
        "evolution",
        "scheduled_tasks",
        "task_graphs",
        "task_nodes",
        ".locks",
        "configs",
    )

    # 敏感文件: 沙箱内不可读 (/dev/null bind-mount 覆盖)
    # 包含安全策略、模式配置、团队配置、workspace 元数据
    SENSITIVE_DAWEI_FILES: tuple[str, ...] = (
        "settings.json",
        "mode_settings.json",
        "team.json",
        "workspace.json",
    )

    # 放行目录: Agent 在沙箱内需要访问的业务文件
    # - files/: 用户上传的文件 (read_file 需要读取)
    # - agents/: Agent 定义 (Agent 可能读取自身配置)
    # - skills/: Skill 定义 (Agent 可能读取 skill 说明)
    PASSTHROUGH_DAWEI_DIRS: tuple[str, ...] = (
        "files",
        "agents",
        "skills",
    )

    def _build_f2_mount_script(self) -> str:
        """生成 P2 细粒度 F2 mount 脚本

        对敏感目录 mount tmpfs, 对敏感文件 bind-mount /dev/null。
        放行 files/agents/skills 等业务目录。
        """
        lines = ["set -e"]

        # 敏感目录: tmpfs 遮蔽
        for d in self.SENSITIVE_DAWEI_DIRS:
            target = f"/workspace/.dawei/{d}"
            lines.append(f"mkdir -p '{target}'")
            lines.append(f"mount -t tmpfs tmpfs '{target}'")
            lines.append(f"chmod 000 '{target}' 2>/dev/null || true")

        # 敏感文件: /dev/null bind-mount 覆盖
        for f in self.SENSITIVE_DAWEI_FILES:
            target = f"/workspace/.dawei/{f}"
            # 文件可能不存在, 创建空文件用于 mount 点
            lines.append(f"touch '{target}'")
            lines.append(f"mount --bind /dev/null '{target}' 2>/dev/null || true")

        return "\n".join(lines) + "\n"

    def _build_f2_verify_cmd(self) -> str:
        """生成 P2 细粒度验证命令

        检查每个敏感目录为空 + 每个敏感文件大小为 0。
        全部通过 → echo OK; 任一泄露 → echo LEAK:<name>
        """
        checks = []

        for d in self.SENSITIVE_DAWEI_DIRS:
            target = f"/workspace/.dawei/{d}"
            checks.append(
                f"if [ -d '{target}' ] && [ -n \"$(ls -A '{target}' 2>/dev/null)\" ]; then echo 'LEAK:{d}'; LEAK=1; fi",
            )

        for f in self.SENSITIVE_DAWEI_FILES:
            target = f"/workspace/.dawei/{f}"
            checks.append(
                f"if [ -e '{target}' ] && [ -s '{target}' ]; then echo 'LEAK:{f}'; LEAK=1; fi",
            )

        # 组装完整脚本
        script = "LEAK=0\n"
        script += "\n".join(checks)
        script += '\nif [ "$LEAK" -eq 0 ]; then echo OK; fi'
        return script

    # dawei 源码在沙箱内的挂载点
    DAWEI_SRC_MOUNT_PATH = "/opt/dawei-src"

    # 工具依赖的关键 Python 包 (沙箱内可能缺失)
    # 2026-09-14 web02 实测: import dawei 完整闭包
    DAWEI_TOOL_DEPS: tuple[str, ...] = (
        "python-dotenv",  # dawei/__init__.py 顶层 import
        "pydantic",
        "pydantic-settings",
        "aiohttp",
        "aiofiles",
        "PyMuPDF",  # fitz — read_file PDF 支持
        "python-docx",  # docx 系列工具
        "openpyxl",  # Excel 处理
    )

    def _build_mount_config(
        self,
        workspace_path: Path,
        mount_mode: str,
        ctx: TrustedContext | None = None,
    ) -> dict[str, Any]:
        """构建 CubeSandbox 挂载配置

        CubeSandbox 使用 ``metadata["host-mount"]`` 扩展字段传递挂载描述,
        格式为 JSON-encoded list of ``{hostPath, mountPath, readOnly}``。
        标准 E2B ``mounts=`` 参数不被 CubeSandbox 识别。

        P3: 额外挂载 agent 源码到 /opt/dawei-src (只读),
        使沙箱内可 import dawei 而无需 pip install。
        """
        read_only = mount_mode == "ro"
        mounts: list[dict[str, Any]] = []

        # rustfs 链路 (2026-09-22): 工作区不 host-mount —— hostPath 不再
        # 依赖 CubeMaster allowed_host_mount_prefixes, 内容走 Store SDK 同步。
        # dawei-src 只读挂载保留 (服务端控制的路径, 在白名单内)。
        if not self._use_store_sync:
            mounts.append(
                {
                    "hostPath": str(workspace_path.resolve()),
                    "mountPath": "/workspace",
                    "readOnly": read_only,
                },
            )
        else:
            # 本地工作区目录兜底创建 (sync_local_to_store 需要; 沙箱侧
            # /workspace 由 F2 mount script 与 init_marker 自行 mkdir)
            try:
                workspace_path.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            logger.info(
                "[E2B] Store SDK 同步模式: 工作区 %s 不做 host-mount, 内容走 WorkspaceStore",
                getattr(ctx, "workspace_id", workspace_path.name),
            )

        # P3: 挂载 agent 源码 (只读), 使 dawei 在沙箱内可导入
        dawei_src = self._find_dawei_source_path()
        if dawei_src:
            mounts.append(
                {
                    "hostPath": str(dawei_src),
                    "mountPath": self.DAWEI_SRC_MOUNT_PATH,
                    "readOnly": True,
                }
            )
            logger.info(
                "[E2B] agent 源码挂载: %s → %s (只读)",
                dawei_src,
                self.DAWEI_SRC_MOUNT_PATH,
            )
        else:
            logger.warning(
                "[E2B] 无法定位 agent 源码路径, 沙箱内 tool_runner 将无法 import dawei",
            )

        config: dict[str, Any] = {
            "metadata": {
                "host-mount": json.dumps(mounts),
            },
        }

        # N4: 注入网络策略
        # 【2026-09-12 能力检测】与 e2b_provider 同源：新版 SDK 不接受
        # network_policy kwarg → 盲注入必然 ConnectionConfig TypeError。
        # SDK 不支持时跳过注入并告警（fail-open，沙箱隔离不受影响）。
        if e2b_supports_network_policy():
            policy = self._load_network_policy()
            if policy:
                config["network_policy"] = policy
        else:
            logger.warning(
                "[CubeSandbox] 已装 SDK 不支持 network_policy 参数, 跳过 N4 网络策略注入（沙箱隔离不受影响）",
            )

        return config

    @staticmethod
    def _find_dawei_source_path() -> Path | None:
        """定位 agent 源码根目录 (包含 dawei/ 的目录)

        优先级:
        1. 环境变量 DAWEI_AGENT_SRC_DIR
        2. dawei 包的 __file__ 反推
        """
        # 1. 环境变量显式指定
        env_src = os.environ.get("DAWEI_AGENT_SRC_DIR", "")
        if env_src and Path(env_src, "dawei", "__init__.py").exists():
            return Path(env_src)

        # 2. 从已安装的 dawei 包反推
        try:
            import dawei

            pkg_file = Path(dawei.__file__).resolve()
            # .../agent/dawei/__init__.py → .../agent
            agent_root = pkg_file.parent.parent
            if (agent_root / "dawei" / "__init__.py").exists():
                return agent_root
        except Exception:
            pass

        return None

    def _execute_on_session(
        self,
        key: str,
        command: str,
        ctx: TrustedContext,
        _allow_rebuild: bool = True,
        timeout: int | None = None,
    ) -> SandboxResult:
        """在已有会话上执行命令

        _allow_rebuild: 平台侧回收沙箱 (not found) 时允许清引用重建一次;
        重试内部传 False 防循环。
        timeout: 工具层传入的每命令超时 (秒)。
        """
        session = self._sessions[key]

        # === N2: pause 状态处理 ===
        if session.is_paused:
            policy = self.pause_policy
            if policy == PausePolicy.REJECT:
                raise SandboxPausedError(
                    f"沙箱已暂停, 需显式 resume: {key}",
                )
            if policy == PausePolicy.QUEUE:
                return self._enqueue_for_resume(key, command, ctx)
            # AUTO_RESUME
            self._resume_sandbox(session)
            logger.info("[E2B] auto-resume 沙箱: %s", ctx.workspace_id)

        # === N3: 命令读写分类 ===
        risk = classify_command(command)
        if session.mount_mode == "ro" and risk in (CommandRisk.WRITE, CommandRisk.UNKNOWN):
            return SandboxResult(
                success=False,
                stdout="",
                stderr=(f"命令需要写权限, 但当前 workspace 以只读模式挂载: {command[:100]}\n分类结果: {risk.value}\n解决方案: 在 .dawei/settings.json 中将 workspace_mount_mode 改为 'rw'"),
                exit_code=77,
                execution_time=0,
                workspace=str(ctx.workspace_id),
                provider="e2b",
                isolation_level=IsolationLevel.HARDWARE,
            )

        # === 正常执行 ===
        effective_timeout = self._resolve_timeout(timeout)
        start_time = time.time()
        try:
            # Option B: user= 使 agent 命令以 uid 对齐的非 root 用户运行,
            # virtiofs 产物在宿主归 backend 所有 (未启用时 kwargs 为空, 行为不变)
            result = session.sandbox.commands.run(
                command,
                cwd="/workspace",
                timeout=effective_timeout,
                **self._run_user_kwargs(),
            )
            execution_time = int((time.time() - start_time) * 1000)
            session.last_active = time.time()

            exit_code = getattr(result, "exit_code", 0)
            stdout = getattr(result, "stdout", "")
            stderr = getattr(result, "stderr", "")

            # === rustfs 链路 (2026-09-22): 命令成功后 沙箱→Store→本地 回拉 ===
            # (与 AgentENVProvider 同款挂载点; ro 模式沙箱内不应有产物, 跳过)
            if exit_code == 0 and self._use_store_sync and session.mount_mode == "rw":
                self._sync_sandbox_back(session)

            return SandboxResult(
                success=exit_code == 0,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                execution_time=execution_time,
                workspace=str(ctx.workspace_id),
                provider="e2b",
                isolation_level=IsolationLevel.HARDWARE,
            )
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            # 2026-09-14: 平台侧 lifetime 到期回收沙箱后, 本地 session 成死引用
            # ("Sandbox ... not found"), 同 workspace 复用会持续失败 →
            # 清理死引用并重建沙箱重试一次 (仅一次, 防循环)。
            if "not found" in str(e).lower() and _allow_rebuild:
                logger.warning(
                    "[E2B] 沙箱已被平台回收, 清理死引用并重建: %s",
                    key,
                )
                self._destroy_session_by_key(key)
                try:
                    self._get_or_create_session(key, ctx)
                    return self._execute_on_session(
                        key,
                        command,
                        ctx,
                        _allow_rebuild=False,
                        timeout=timeout,
                    )
                except Exception as e2:
                    logger.warning("[E2B] 重建会话后执行仍失败: %s", e2)
                    return SandboxResult(
                        success=False,
                        stdout="",
                        stderr=f"沙箱已回收且重建失败: {e} → {e2}",
                        exit_code=-1,
                        execution_time=int((time.time() - start_time) * 1000),
                        workspace=str(ctx.workspace_id),
                        provider="e2b",
                        isolation_level=IsolationLevel.HARDWARE,
                    )
            # e2b SDK 对非零退出码抛 CommandExitException (携带 exit_code/stdout/stderr),
            # 超时抛 TimeoutException —— 均需提取真实属性透传, 不能只取 str(e)
            # (2026-09-14 smoke #7: 旧代码丢属性 + 日志包装器 bug → 工具误报 success:false)
            ex_exit = getattr(e, "exit_code", None)
            ex_stdout = getattr(e, "stdout", "") or ""
            ex_stderr = getattr(e, "stderr", "") or ""
            if ex_exit is None:
                ex_exit = -1
                ex_type = type(e).__name__
                ex_stderr = f"{ex_type}: {e}" if not ex_stderr else f"{ex_type}: {e}\n{ex_stderr}"
            logger.error(
                "[E2B] 命令执行异常 (exit=%s): %s",
                ex_exit,
                e,
                exc_info=True,
            )
            return SandboxResult(
                success=False,
                stdout=str(ex_stdout),
                stderr=str(ex_stderr),
                exit_code=int(ex_exit) if isinstance(ex_exit, int) else -1,
                execution_time=execution_time,
                workspace=str(ctx.workspace_id),
                provider="e2b",
                isolation_level=IsolationLevel.HARDWARE,
            )

    def _create_and_execute(
        self,
        key: str,
        command: str,
        ctx: TrustedContext,
        timeout: int | None = None,
    ) -> SandboxResult:
        """创建新会话并执行命令"""
        self._get_or_create_session(key, ctx)
        return self._execute_on_session(key, command, ctx, timeout=timeout)

    # ================================================================
    # §4: 配额检查 + LRU 淘汰
    # ================================================================

    def _check_quota(self, ctx: TrustedContext) -> None:
        """执行前配额检查, 超限则按策略拒绝或淘汰"""
        key = self._session_key(ctx)

        # 已有会话则跳过配额检查 (会话已存在不重复创建)
        if key in self._sessions and not self._disconnected.get(key, False):
            self._check_rate_limit(ctx)
            return

        user_sessions = [s for s in self._sessions.values() if s.user_id == ctx.user_id]

        # 用户级: 沙箱数
        if len(user_sessions) >= self.user_quota.max_concurrent_sandboxes:
            user_sessions.sort(key=lambda s: s.last_active)
            evicted = user_sessions[0]
            evict_key = f"{evicted.user_id}::{evicted.workspace_id}"
            self._destroy_session_by_key(evict_key)
            logger.warning(
                "[E2B] 用户 %s 达沙箱数上限, LRU 淘汰: %s",
                ctx.user_id,
                evict_key,
            )

        # 用户级: 内存
        user_memory = len(user_sessions) * self.estimated_memory_per_sandbox_mb
        if user_memory >= self.user_quota.max_total_memory_mb:
            raise QuotaExceededError(
                f"用户内存配额耗尽: {user_memory}MB / {self.user_quota.max_total_memory_mb}MB",
            )

        # 全局级: 沙箱数
        if len(self._sessions) >= self.global_quota.max_total_sandboxes:
            oldest_key = min(self._sessions, key=lambda k: self._sessions[k].last_active)
            self._destroy_session_by_key(oldest_key)
            logger.warning("[E2B] 全局沙箱数达上限, LRU 淘汰: %s", oldest_key)

        self._check_rate_limit(ctx)

    def _check_rate_limit(self, ctx: TrustedContext) -> None:
        """每用户每分钟命令数速率限制"""
        now = time.time()
        timestamps = self._rate_limiter.setdefault(str(ctx.user_id), [])
        timestamps[:] = [t for t in timestamps if now - t < 60]
        if len(timestamps) >= self.user_quota.max_commands_per_minute:
            raise QuotaExceededError(
                f"命令速率超限: {len(timestamps)}/min (用户 {ctx.user_id})",
            )
        timestamps.append(now)

    # ================================================================
    # N1: WebSocket 断连 grace 期 + 命令队列
    # ================================================================

    def on_disconnect(self, ctx: TrustedContext) -> None:
        """WebSocket 断开 — 不立即销毁, 进入 grace 期"""
        key = self._session_key(ctx)
        self._disconnected[key] = True
        self._scheduled_destroy[key] = time.time() + self.disconnect_grace_seconds
        logger.info(
            "[E2B] 会话断开, 进入 grace 期 (%ss): %s",
            self.disconnect_grace_seconds,
            ctx.workspace_id,
        )

    def on_reconnect(self, ctx: TrustedContext) -> None:
        """WebSocket 重连 — 恢复沙箱, 排空队列"""
        key = self._session_key(ctx)
        if not self._disconnected.pop(key, False):
            return

        self._scheduled_destroy.pop(key, None)

        session = self._sessions.get(key)
        if session and session.is_paused:
            self._resume_sandbox(session)

        pending = self._pending_commands.pop(key, [])
        logger.info(
            "[E2B] 会话重连, 排空队列: %s, queue_size=%s",
            ctx.workspace_id,
            len(pending),
        )
        for entry in pending:
            try:
                result = self._execute_on_session(key, entry.command, entry.ctx)
                if not entry.future.done():
                    entry.future.set_result(result)
            except Exception as e:
                if not entry.future.done():
                    entry.future.set_exception(e)

    def _enqueue_command(
        self,
        key: str,
        command: str,
        ctx: TrustedContext,
    ) -> SandboxResult:
        """grace 期内命令入队, 同步等待结果"""
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        entry = CommandQueueEntry(
            command=command,
            ctx=ctx,
            enqueued_at=time.time(),
            future=future,
        )
        self._pending_commands.setdefault(key, []).append(entry)
        logger.info(
            "[E2B] 命令入队 (grace 期内): %s, queue_size=%s",
            ctx.workspace_id,
            len(self._pending_commands[key]),
        )
        try:
            return loop.run_until_complete(
                asyncio.wait_for(future, timeout=self.disconnect_grace_seconds),
            )
        except TimeoutError:
            raise SandboxTimeoutError(
                f"grace 期内未重连, 命令超时: {key}",
            )

    def _cleanup_disconnected_session(self, key: str) -> None:
        """grace 期已过, 真正销毁"""
        self._destroy_session_by_key(key)
        self._disconnected.pop(key, None)
        self._scheduled_destroy.pop(key, None)
        pending = self._pending_commands.pop(key, [])
        for entry in pending:
            if not entry.future.done():
                entry.future.set_exception(
                    SandboxTimeoutError(f"grace 期已过, 沙箱已销毁: {key}"),
                )
        logger.info("[E2B] grace 期已过, 销毁沙箱: %s", key)

    # ================================================================
    # N2: Pause 策略
    # ================================================================

    def _resume_sandbox(self, session: SandboxSession) -> None:
        """恢复暂停的沙箱"""
        try:
            session.sandbox.resume()
        except Exception as e:
            logger.warning("[E2B] resume 异常: %s", e)
        session.is_paused = False

    def _enqueue_for_resume(
        self,
        key: str,
        command: str,
        ctx: TrustedContext,
    ) -> SandboxResult:
        """QUEUE 策略: 排队等待下次活跃周期"""
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        entry = CommandQueueEntry(
            command=command,
            ctx=ctx,
            enqueued_at=time.time(),
            future=future,
        )
        self._pending_commands.setdefault(key, []).append(entry)
        try:
            return loop.run_until_complete(
                asyncio.wait_for(future, timeout=self.default_timeout),
            )
        except TimeoutError:
            raise SandboxTimeoutError(
                f"pause QUEUE 超时: {key}",
            )

    # ================================================================
    # N4: 网络策略加载
    # ================================================================

    def _load_network_policy(self) -> dict[str, Any] | None:
        """加载 eBPF 网络策略 YAML"""
        if self._network_policy is not None:
            return self._network_policy

        policy_path = Path(
            os.environ.get(
                "DAWEI_SANDBOX_NETWORK_POLICY",
                "/etc/dawei/sandbox_network_policy.yaml",
            ),
        )

        # 尝试包内默认模板
        if not policy_path.exists():
            bundled = Path(__file__).parent / "dawei_sandbox_network_policy.yaml"
            if bundled.exists():
                policy_path = bundled

        if not policy_path.exists():
            logger.warning(
                "[E2B] 网络策略文件不存在: %s, 使用默认 deny-all",
                policy_path,
            )
            return {"default_action": "deny", "rules": []}

        try:
            import yaml

            self._network_policy = yaml.safe_load(policy_path.read_text())
            logger.info("[E2B] 网络策略已加载: %s", policy_path)
            return self._network_policy
        except ImportError:
            logger.warning("[E2B] PyYAML 未安装, 网络策略禁用")
            return None
        except Exception as e:
            logger.exception("[E2B] 网络策略加载失败: %s", e)
            return {"default_action": "deny", "rules": []}

    # ================================================================
    # 会话销毁
    # ================================================================

    def _sync_sandbox_back(self, session: SandboxSession) -> None:
        """rustfs 链路: 沙箱 → Store → 本地 (命令成功后/销毁前回拉)

        非致命: 回拉失败仅 warning (沙箱产物下次 push 前以本地为准),
        与 AgentENVProvider 语义一致。
        """
        store = self._workspace_store
        if not store or not session.workspace_key:
            return
        try:
            pull_stats = store.pull_from_sandbox(session.sandbox, session.workspace_key)
            if pull_stats.downloaded > 0 and session.workspace_path:
                store.sync_store_to_local(session.workspace_key, session.workspace_path)
            if pull_stats.downloaded > 0:
                logger.info(
                    "[E2B] 沙箱产物回拉 (key=%s): %s",
                    session.workspace_key,
                    pull_stats.as_dict(),
                )
        except Exception as e:
            logger.warning("[E2B] 沙箱→Store 回拉失败 (非致命): %s", e)

    def _destroy_session_by_key(self, key: str) -> None:
        """销毁指定 key 的沙箱会话"""
        session = self._sessions.pop(key, None)
        if session and session.sandbox:
            # rustfs 链路: 销毁前兜底回拉 (exit≠0 命令/后台进程的产物)
            if self._use_store_sync and session.mount_mode == "rw":
                self._sync_sandbox_back(session)
            try:
                session.sandbox.kill()
            except Exception as e:
                logger.warning("[E2B] kill 沙箱异常: %s", e)

    def destroy_session(self, ctx: TrustedContext) -> None:
        """销毁指定会话"""
        key = self._session_key(ctx)
        self._destroy_session_by_key(key)
        self._disconnected.pop(key, None)
        self._scheduled_destroy.pop(key, None)

    def destroy_all_sessions(self) -> None:
        """销毁所有会话"""
        for key in list(self._sessions.keys()):
            self._destroy_session_by_key(key)
        self._pending_commands.clear()
        self._disconnected.clear()
        self._scheduled_destroy.clear()
        logger.info("[E2B] 所有会话已销毁")

    async def cleanup_idle(self) -> None:
        """清理空闲沙箱 (后台任务)"""
        now = time.time()
        for key in list(self._sessions.keys()):
            session = self._sessions[key]

            # 超过 idle_destroy → 销毁
            if now - session.last_active > self.idle_destroy_seconds:
                self._destroy_session_by_key(key)
                logger.info("[E2B] 空闲超时, 销毁沙箱: %s", key)
                continue

            # 超过 idle_pause → pause
            # 2026-09-14: 平台侧 lifetime (~300s, 未续租) 常先于 idle_pause 回收
            # 沙箱 → pause 404 "not found"。此时 session 已是死引用, 直接清掉
            # 本地记录 (kill 的 404 由 _destroy_session_by_key 吞掉),
            # 避免每轮 60s 对同一死沙箱无效重试。
            if not session.is_paused and now - session.last_active > self.idle_pause_seconds:
                try:
                    session.sandbox.pause()
                    session.is_paused = True
                    logger.info("[E2B] 空闲 pause 沙箱: %s", key)
                except Exception as e:
                    if "not found" in str(e).lower():
                        self._destroy_session_by_key(key)
                        logger.info("[E2B] 沙箱平台侧已回收, 清理本地会话: %s", key)
                        continue
                    logger.warning("[E2B] pause 异常: %s", e)

        # 清理过期的 grace 期会话
        for key in list(self._scheduled_destroy.keys()):
            if time.time() >= self._scheduled_destroy[key]:
                self._cleanup_disconnected_session(key)


# ================================================================
# 后向兼容别名 (Phase 1d 重命名)
# ================================================================

# 旧代码 / 旧测试可能仍引用 E2BProvider
# 保留 alias 以免破坏现有 import (e.g. dawei.sandbox.e2b_provider.E2BProvider)
E2BProvider = CubeSandboxProvider

__all__ = [
    "CubeSandboxProvider",
    "E2BProvider",  # alias for back-compat
    "SandboxSession",
    "CommandQueueEntry",
]
