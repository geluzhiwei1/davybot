# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""AgentENVProvider — kvcache-ai AgentENV 硬件级沙箱 (SaaS 沙箱方案 §3.4)

AgentENV 是 kvcache-ai (月之暗面 Kimi K3 同源) 开源的分布式 Agent 环境平台:
- Firecracker microVM (Linux 6.8+ + KVM)
- E2B-compatible HTTP API (直接复用 e2b Python SDK)
- 无 virtiofs (与 CubeSandbox 关键区别)
- 工作区同步依赖 SDK 的 sandbox.files.write / .read
- 原生支持 fork / pause / resume / snapshot

文件模式:
- SDK 同步: 启动时 push_from_store (增量), 执行后 pull_from_sandbox (拉回 Agent 修改)

复用 CubeSandboxProvider 的安全特性:
- F2: tmpfs 遮蔽 .dawei/
- N1/N2/N3/N4: 配额 / grace / pause / 网络策略 / PII
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
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
from dawei.sandbox.pii_logger import PiiSafeLogger

logger = PiiSafeLogger(logging.getLogger(__name__))


# ================================================================
# 数据结构 (与 CubeSandboxProvider 对齐)
# ================================================================


@dataclass
class AgentENVSandboxSession:
    """单个 AgentENV 沙箱会话状态"""

    sandbox: Any  # E2BSandbox 实例 (AgentENV 兼容)
    user_id: UserId
    workspace_id: str
    workspace_key: str              # 在 WorkspaceStore 中的 key
    mount_mode: str                  # "ro" | "rw"
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
# .dawei/ tmpfs 遮蔽 (复用 CubeSandbox 同款, 保持 P2 细粒度)
# ================================================================

# 与 cubesandbox_provider.py.SENSITIVE_DAWEI_DIRS 对齐
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

SENSITIVE_DAWEI_FILES: tuple[str, ...] = (
    "settings.json",
    "mode_settings.json",
    "team.json",
    "workspace.json",
)


def _build_mount_script() -> str:
    """生成 tmpfs 遮蔽脚本 (在 VM 内运行)

    对每个敏感目录 mount tmpfs, 对每个敏感文件 bind-mount /dev/null
    """
    lines = ["set -e"]

    for d in SENSITIVE_DAWEI_DIRS:
        target = f"/workspace/.dawei/{d}"
        lines.append(f"mkdir -p '{target}'")
        lines.append(f"mount -t tmpfs tmpfs '{target}'")
        lines.append(f"chmod 000 '{target}' 2>/dev/null || true")

    for f in SENSITIVE_DAWEI_FILES:
        target = f"/workspace/.dawei/{f}"
        lines.append(f"touch '{target}'")
        lines.append(f"mount --bind /dev/null '{target}' 2>/dev/null || true")

    return "\n".join(lines) + "\n"


def _build_verify_cmd() -> str:
    """生成验证命令 (启动后检查每个敏感条目)"""
    checks = []
    for d in SENSITIVE_DAWEI_DIRS:
        target = f"/workspace/.dawei/{d}"
        checks.append(
            f"if [ -d '{target}' ] && [ -n \"$(ls -A '{target}' 2>/dev/null)\" ]; then "
            f"echo 'LEAK:{d}'; LEAK=1; fi",
        )
    for f in SENSITIVE_DAWEI_FILES:
        target = f"/workspace/.dawei/{f}"
        checks.append(
            f"if [ -e '{target}' ] && [ -s '{target}' ]; then "
            f"echo 'LEAK:{f}'; LEAK=1; fi",
        )

    script = "LEAK=0\n"
    script += "\n".join(checks)
    script += '\nif [ "$LEAK" -eq 0 ]; then echo OK; fi'
    return script


# ================================================================
# AgentENVProvider
# ================================================================


class AgentENVProvider(SandboxProvider):
    """kvcache-ai AgentENV 硬件级沙箱 Provider

    隔离级别: HARDWARE (KVM MicroVM, Firecracker)
    适用场景: SaaS 云端 (Linux 6.8+ + KVM 节点集群)
    通信协议: E2B HTTP API (复用 e2b Python SDK)

    与 CubeSandboxProvider 的区别:
    - 文件模式: 仅 SDK 同步 (无 virtiofs 挂载)
    - 启动序列: 同步工作区 → 遮蔽 .dawei/ → 验证
    - 拉回机制: 每个命令后 pull_from_sandbox (S3 持久化)
    """

    # dawei 源码在沙箱内的挂载点 (与 CubeSandbox 一致, 保持 P3 兼容)
    DAWEI_SRC_MOUNT_PATH = "/opt/dawei-src"

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

        # AgentENV 配置 (独立于 CubeSandbox)
        self.template_id = os.environ.get(
            "DAWEI_AGENTENV_TEMPLATE",
            os.environ.get("DAWEI_SANDBOX_TEMPLATE", "code-interpreter"),
        )
        self.api_url = os.environ.get(
            "DAWEI_AGENTENV_API_URL",
            os.environ.get("DAWEI_SANDBOX_API_URL", ""),
        )
        # AgentENV 接受任意非空值 (与 E2B SDK 兼容)
        self.api_key = os.environ.get(
            "DAWEI_AGENTENV_API_KEY",
            os.environ.get("E2B_API_KEY", "dummy"),
        )

        # 超时 / 闲置策略 (与 CubeSandbox 对齐)
        self.default_timeout = self.config.get("default_timeout", 30)
        self.idle_pause_seconds = self.config.get("idle_pause", 300)
        self.idle_destroy_seconds = self.config.get("idle_destroy", 1800)

        # 会话 + 配额
        self._sessions: dict[str, AgentENVSandboxSession] = {}
        self.user_quota = ResourceQuota(
            max_concurrent_sandboxes=self.config.get("max_sessions_per_user", 10),
            max_total_memory_mb=self.config.get("max_memory_per_user_mb", 5120),
            max_sandboxes_per_workspace=self.config.get("max_sandboxes_per_workspace", 1),
            max_commands_per_minute=self.config.get("max_commands_per_minute", 120),
        )
        self.global_quota = GlobalQuota(
            max_total_sandboxes=self.config.get("max_total_sessions", 1000),
            max_total_memory_mb=self.config.get("max_total_memory_mb", 102400),
        )
        self.estimated_memory_per_sandbox_mb = 50  # AgentENV 公开数据 (含 overlaybd)

        # 速率限制
        self._rate_limiter: dict[str, list[float]] = {}

        # Pause 策略
        self.pause_policy = PausePolicy(self.config.get("pause_policy", "auto_resume"))

        # N1: WebSocket grace
        self.disconnect_grace_seconds = self.config.get("disconnect_grace", 60)
        self._pending_commands: dict[str, list[CommandQueueEntry]] = {}
        self._scheduled_destroy: dict[str, float] = {}
        self._disconnected: dict[str, bool] = {}

        # N4: 网络策略 (与 CubeSandbox 复用同一文件)
        self._network_policy: dict[str, Any] | None = None

        # WorkspaceStore (延迟, 失败回退 None)
        self._workspace_store = None
        self._init_workspace_store()

    def _init_workspace_store(self) -> None:
        """初始化 WorkspaceStore (SaaS 模式必需, desktop 模式可空)"""
        try:
            from dawei.sandbox.workspace_store import get_workspace_store

            self._workspace_store = get_workspace_store()
            logger.info("[AGENTENV] WorkspaceStore 已初始化: %s", type(self._workspace_store.backend).__name__)
        except Exception as e:
            logger.warning("[AGENTENV] WorkspaceStore 不可用, 将以空 workspace 启动: %s", e)

    # ================================================================
    # SandboxProvider 接口
    # ================================================================

    def prewarm_session(self, ctx: TrustedContext) -> None:
        key = self._session_key(ctx)
        if key in self._sessions:
            logger.debug("[AGENTENV] prewarm 跳过 (会话已存在): %s", ctx.workspace_id)
            return
        self._get_or_create_session(key, ctx)
        logger.info("[AGENTENV] 沙箱预热完成: %s", ctx.workspace_id)

    def execute_command(self, command: str, ctx: TrustedContext, timeout: int | None = None) -> SandboxResult:
        """同步执行命令（timeout 为接口契约参数，会话型执行暂用部署侧缺省）"""
        self._check_quota(ctx)
        key = self._session_key(ctx)

        if key in self._sessions and not self._disconnected.get(key, False):
            return self._execute_on_session(key, command, ctx)

        if self._disconnected.get(key, False):
            destroy_at = self._scheduled_destroy.get(key, 0)
            if time.time() < destroy_at:
                return self._enqueue_command(key, command, ctx)
            self._cleanup_disconnected_session(key)

        return self._create_and_execute(key, command, ctx)

    async def execute_command_async(
        self, command: str, ctx: TrustedContext, timeout: int | None = None,
    ) -> SandboxResult:
        return await asyncio.to_thread(self.execute_command, command, ctx, timeout)

    def health_check(self) -> bool:
        if not self.api_url:
            return False
        try:
            from dawei.sandbox.provider_factory import _check_e2b_available

            return _check_e2b_available(self.api_url)
        except Exception:
            return False

    def get_capabilities(self) -> SandboxCapabilities:
        """AgentENV 能力声明"""
        return SandboxCapabilities(
            isolation_level=IsolationLevel.HARDWARE,
            supports_network=True,
            supports_filesystem=True,    # 通过 SDK
            supports_resource_limits=True,
            supports_pause=True,
            max_timeout=300,
            cold_start_ms=50,           # AgentENV 公开数据
        )

    # ================================================================
    # 会话管理
    # ================================================================

    def _session_key(self, ctx: TrustedContext) -> str:
        return f"{ctx.user_id}::{ctx.workspace_id}"

    def _get_or_create_session(self, key: str, ctx: TrustedContext) -> AgentENVSandboxSession:
        if key in self._sessions:
            return self._sessions[key]

        # mount_mode 优先级: ctx (来自 JWT) > config > 默认 rw
        mount_mode = (
            ctx.workspace_mount_mode
            or self.config.get("workspace_mount_mode", "rw")
        )

        sandbox = self._create_sandbox(ctx, mount_mode)

        session = AgentENVSandboxSession(
            sandbox=sandbox,
            user_id=ctx.user_id,
            workspace_id=str(ctx.workspace_id),
            workspace_key=ctx.workspace_key,
            mount_mode=mount_mode,
        )
        self._sessions[key] = session
        logger.info("[AGENTENV] 沙箱已创建: %s (mode=%s)", ctx.workspace_id, mount_mode)
        return session

    def _create_sandbox(self, ctx: TrustedContext, mount_mode: str) -> Any:
        """创建 AgentENV 沙箱 + 应用 F2 遮蔽 + 拉取工作区

        启动序列:
        1. e2b SDK 创建沙箱 (AgentENV 兼容)
        2. 在 VM 内创建 /workspace, 应用 tmpfs 遮蔽 .dawei/
        3. 启动后验证遮蔽生效 (fail-closed)
        4. SDK 拉取 WorkspaceStore 工作区到 /workspace
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

        # === 1. 创建沙箱 ===
        # AgentENV 不需要 metadata 挂载字段 (无 virtiofs)
        # e2b SDK 接受任意非空 api_key
        sandbox = E2BSandbox.create(
            template=self.template_id,
            api_key=self.api_key,
        )

        # === 2. .dawei/ tmpfs 遮蔽 (启动后) ===
        mount_script = _build_mount_script()
        try:
            result = sandbox.commands.run(mount_script, timeout=15)
            exit_code = getattr(result, "exit_code", 0)
            if exit_code != 0:
                try:
                    sandbox.kill()
                except Exception:
                    pass
                raise SandboxSecurityError(
                    f"tmpfs 遮蔽失败 (exit={exit_code}): {getattr(result, 'stderr', 'unknown')}",
                )
        except SandboxSecurityError:
            raise
        except Exception as e:
            try:
                sandbox.kill()
            except Exception:
                pass
            raise SandboxSecurityError(f"遮蔽脚本执行异常: {e}") from e

        # === 3. 启动后验证 ===
        verify = sandbox.commands.run(_build_verify_cmd(), timeout=10)
        verify_stdout = getattr(verify, "stdout", "")
        if "OK" not in verify_stdout or "LEAK" in verify_stdout:
            try:
                sandbox.kill()
            except Exception:
                pass
            raise SandboxSecurityError(
                f"遮蔽验证失败, 沙箱已销毁: {verify_stdout}",
            )

        # === 4. 拉取工作区到 VM ===
        # 使用 WorkspaceStore (若有) SDK 同步
        if self._workspace_store:
            try:
                # 初始化 pull marker
                self._workspace_store.init_marker(sandbox)
                # 推送 workspace 内容
                stats = self._workspace_store.push_to_sandbox(
                    sandbox, ctx.workspace_key,
                )
                logger.info(
                    "[AGENTENV] 工作区推送: %s (key=%s)",
                    stats.as_dict(), ctx.workspace_key,
                )
            except Exception as e:
                logger.warning("[AGENTENV] WorkspaceStore 推送失败 (沙箱内可能无文件): %s", e)
        else:
            logger.info("[AGENTENV] 无 WorkspaceStore, 沙箱内 /workspace 为空")

        # === 5. P3: 工具源码挂载 (CubeSandbox P3 同款) ===
        # 注: AgentENV 无 host-mount 能力,源码预装进 OCI 镜像,这里只验证
        self._ensure_dawei_available(sandbox)

        return sandbox

    def _ensure_dawei_available(self, sandbox: Any) -> None:
        """P3: 验证沙箱内可 import dawei (AgentENV 镜像需预装)"""
        try:
            verify = sandbox.commands.run(
                "python3 -c 'import dawei; print(dawei.__version__)' 2>&1",
                timeout=10,
            )
            stdout = getattr(verify, "stdout", "").strip()
            if "Error" in stdout or "Traceback" in stdout:
                logger.warning("[AGENTENV] dawei 不可导入: %s", stdout[:200])
            else:
                logger.info("[AGENTENV] dawei 可用 (version=%s)", stdout or "unknown")
        except Exception as e:
            logger.debug("[AGENTENV] dawei 验证跳过: %s", e)

    # ================================================================
    # 命令执行 + 拉回
    # ================================================================

    def _execute_on_session(self, key: str, command: str, ctx: TrustedContext) -> SandboxResult:
        session = self._sessions[key]

        # === N2: pause 状态 ===
        if session.is_paused:
            policy = self.pause_policy
            if policy == PausePolicy.REJECT:
                raise SandboxPausedError(f"沙箱已暂停: {key}")
            if policy == PausePolicy.QUEUE:
                return self._enqueue_for_resume(key, command, ctx)
            self._resume_sandbox(session)
            logger.info("[AGENTENV] auto-resume: %s", ctx.workspace_id)

        # === N3: 读写分类预拦截 ===
        risk = classify_command(command)
        if session.mount_mode == "ro" and risk in (CommandRisk.WRITE, CommandRisk.UNKNOWN):
            return SandboxResult(
                success=False,
                stdout="",
                stderr=(
                    f"命令需要写权限, 但当前 workspace 以只读模式挂载: {command[:100]}\n"
                    f"分类结果: {risk.value}\n"
                    f"解决方案: 在 .dawei/settings.json 中将 workspace_mount_mode 改为 'rw'"
                ),
                exit_code=77,
                execution_time=0,
                workspace=str(ctx.workspace_id),
                provider="agentenv",
                isolation_level=IsolationLevel.HARDWARE,
            )

        # === 正常执行 ===
        start = time.time()
        try:
            result = session.sandbox.commands.run(
                command,
                cwd="/workspace",
                timeout=self.default_timeout,
            )
            execution_time = int((time.time() - start) * 1000)
            session.last_active = time.time()

            exit_code = getattr(result, "exit_code", 0)
            stdout = getattr(result, "stdout", "")
            stderr = getattr(result, "stderr", "")

            # === 命令成功后拉回 Agent 修改 ===
            if exit_code == 0 and self._workspace_store:
                try:
                    pull_stats = self._workspace_store.pull_from_sandbox(
                        session.sandbox, session.workspace_key,
                    )
                    if pull_stats.downloaded > 0:
                        logger.info("[AGENTENV] 拉回工作区: %s", pull_stats.as_dict())
                except Exception as e:
                    logger.warning("[AGENTENV] 拉回失败 (非致命): %s", e)

            return SandboxResult(
                success=exit_code == 0,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                execution_time=execution_time,
                workspace=str(ctx.workspace_id),
                provider="agentenv",
                isolation_level=IsolationLevel.HARDWARE,
            )
        except Exception as e:
            execution_time = int((time.time() - start) * 1000)
            logger.error("[AGENTENV] 命令执行异常: %s", e, exc_info=True)
            return SandboxResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time=execution_time,
                workspace=str(ctx.workspace_id),
                provider="agentenv",
                isolation_level=IsolationLevel.HARDWARE,
            )

    def _create_and_execute(self, key: str, command: str, ctx: TrustedContext) -> SandboxResult:
        self._get_or_create_session(key, ctx)
        return self._execute_on_session(key, command, ctx)

    # ================================================================
    # 配额检查 (与 CubeSandbox 同款)
    # ================================================================

    def _check_quota(self, ctx: TrustedContext) -> None:
        key = self._session_key(ctx)

        if key in self._sessions and not self._disconnected.get(key, False):
            self._check_rate_limit(ctx)
            return

        user_sessions = [s for s in self._sessions.values() if s.user_id == ctx.user_id]

        if len(user_sessions) >= self.user_quota.max_concurrent_sandboxes:
            user_sessions.sort(key=lambda s: s.last_active)
            evicted = user_sessions[0]
            evict_key = f"{evicted.user_id}::{evicted.workspace_id}"
            self._destroy_session_by_key(evict_key)
            logger.warning(
                "[AGENTENV] 用户 %s 达上限, LRU 淘汰: %s",
                ctx.user_id, evict_key,
            )

        user_memory = len(user_sessions) * self.estimated_memory_per_sandbox_mb
        if user_memory >= self.user_quota.max_total_memory_mb:
            raise QuotaExceededError(
                f"用户内存配额耗尽: {user_memory}MB / {self.user_quota.max_total_memory_mb}MB",
            )

        if len(self._sessions) >= self.global_quota.max_total_sandboxes:
            oldest_key = min(self._sessions, key=lambda k: self._sessions[k].last_active)
            self._destroy_session_by_key(oldest_key)
            logger.warning("[AGENTENV] 全局沙箱数达上限, LRU 淘汰: %s", oldest_key)

        self._check_rate_limit(ctx)

    def _check_rate_limit(self, ctx: TrustedContext) -> None:
        now = time.time()
        timestamps = self._rate_limiter.setdefault(str(ctx.user_id), [])
        timestamps[:] = [t for t in timestamps if now - t < 60]
        if len(timestamps) >= self.user_quota.max_commands_per_minute:
            raise QuotaExceededError(
                f"命令速率超限: {len(timestamps)}/min (用户 {ctx.user_id})",
            )
        timestamps.append(now)

    # ================================================================
    # WebSocket grace + 命令队列
    # ================================================================

    def on_disconnect(self, ctx: TrustedContext) -> None:
        key = self._session_key(ctx)
        self._disconnected[key] = True
        self._scheduled_destroy[key] = time.time() + self.disconnect_grace_seconds
        logger.info("[AGENTENV] 会话断开, 进入 grace (%ss): %s",
                    self.disconnect_grace_seconds, ctx.workspace_id)

    def on_reconnect(self, ctx: TrustedContext) -> None:
        key = self._session_key(ctx)
        if not self._disconnected.pop(key, False):
            return
        self._scheduled_destroy.pop(key, None)

        session = self._sessions.get(key)
        if session and session.is_paused:
            self._resume_sandbox(session)

        pending = self._pending_commands.pop(key, [])
        logger.info("[AGENTENV] 会话重连, 排空队列: %s, queue_size=%s",
                    ctx.workspace_id, len(pending))
        for entry in pending:
            try:
                result = self._execute_on_session(key, entry.command, entry.ctx)
                if not entry.future.done():
                    entry.future.set_result(result)
            except Exception as e:
                if not entry.future.done():
                    entry.future.set_exception(e)

    def _enqueue_command(self, key: str, command: str, ctx: TrustedContext) -> SandboxResult:
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        entry = CommandQueueEntry(
            command=command, ctx=ctx,
            enqueued_at=time.time(), future=future,
        )
        self._pending_commands.setdefault(key, []).append(entry)
        try:
            return loop.run_until_complete(
                asyncio.wait_for(future, timeout=self.disconnect_grace_seconds),
            )
        except TimeoutError:
            raise SandboxTimeoutError(f"grace 期内未重连: {key}")

    def _cleanup_disconnected_session(self, key: str) -> None:
        self._destroy_session_by_key(key)
        self._disconnected.pop(key, None)
        self._scheduled_destroy.pop(key, None)
        pending = self._pending_commands.pop(key, [])
        for entry in pending:
            if not entry.future.done():
                entry.future.set_exception(
                    SandboxTimeoutError(f"grace 期已过: {key}"),
                )

    # ================================================================
    # Pause / Resume
    # ================================================================

    def _resume_sandbox(self, session: AgentENVSandboxSession) -> None:
        try:
            session.sandbox.resume()
        except Exception as e:
            logger.warning("[AGENTENV] resume 异常: %s", e)
        session.is_paused = False

    def _enqueue_for_resume(self, key: str, command: str, ctx: TrustedContext) -> SandboxResult:
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        entry = CommandQueueEntry(
            command=command, ctx=ctx,
            enqueued_at=time.time(), future=future,
        )
        self._pending_commands.setdefault(key, []).append(entry)
        try:
            return loop.run_until_complete(
                asyncio.wait_for(future, timeout=self.default_timeout),
            )
        except TimeoutError:
            raise SandboxTimeoutError(f"pause QUEUE 超时: {key}")

    # ================================================================
    # 网络策略 (复用 CubeSandbox 加载路径)
    # ================================================================

    def _load_network_policy(self) -> dict[str, Any] | None:
        if self._network_policy is not None:
            return self._network_policy

        policy_path = Path(
            os.environ.get(
                "DAWEI_SANDBOX_NETWORK_POLICY",
                "/etc/dawei/sandbox_network_policy.yaml",
            ),
        )

        if not policy_path.exists():
            bundled = Path(__file__).parent / "dawei_sandbox_network_policy.yaml"
            if bundled.exists():
                policy_path = bundled

        if not policy_path.exists():
            return {"default_action": "deny", "rules": []}

        try:
            import yaml

            self._network_policy = yaml.safe_load(policy_path.read_text())
            logger.info("[AGENTENV] 网络策略已加载: %s", policy_path)
            return self._network_policy
        except ImportError:
            return None
        except Exception as e:
            logger.exception("[AGENTENV] 网络策略加载失败: %s", e)
            return {"default_action": "deny", "rules": []}

    # ================================================================
    # 销毁 + 清理
    # ================================================================

    def _destroy_session_by_key(self, key: str) -> None:
        session = self._sessions.pop(key, None)
        if session and session.sandbox:
            try:
                session.sandbox.kill()
            except Exception as e:
                logger.warning("[AGENTENV] kill 异常: %s", e)

    def destroy_session(self, ctx: TrustedContext) -> None:
        key = self._session_key(ctx)
        self._destroy_session_by_key(key)
        self._disconnected.pop(key, None)
        self._scheduled_destroy.pop(key, None)

    def destroy_all_sessions(self) -> None:
        for key in list(self._sessions.keys()):
            self._destroy_session_by_key(key)
        self._pending_commands.clear()
        self._disconnected.clear()
        self._scheduled_destroy.clear()
        logger.info("[AGENTENV] 所有会话已销毁")

    async def cleanup_idle(self) -> None:
        now = time.time()
        for key in list(self._sessions.keys()):
            session = self._sessions[key]

            if now - session.last_active > self.idle_destroy_seconds:
                self._destroy_session_by_key(key)
                logger.info("[AGENTENV] 空闲超时销毁: %s", key)
                continue

            if not session.is_paused and now - session.last_active > self.idle_pause_seconds:
                try:
                    session.sandbox.pause()
                    session.is_paused = True
                    logger.info("[AGENTENV] 空闲 pause: %s", key)
                except Exception as e:
                    logger.warning("[AGENTENV] pause 异常: %s", e)

        for key in list(self._scheduled_destroy.keys()):
            if time.time() >= self._scheduled_destroy[key]:
                self._cleanup_disconnected_session(key)


__all__ = ["AgentENVProvider", "AgentENVSandboxSession", "CommandQueueEntry"]
