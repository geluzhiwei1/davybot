# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""E2BProvider — CubeSandbox / E2B Cloud 硬件级沙箱 (§沙箱系统升级 v2 — Phase 2)

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

依赖: e2b Python SDK (pip install e2b) — 延迟导入, 不可用时 provider_factory 自动降级
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
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
from dawei.sandbox.e2b_compat import e2b_supports_network_policy
from dawei.sandbox.path_validator import validate_workspace_path
from dawei.sandbox.pii_logger import PiiSafeLogger

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
# E2BProvider
# ================================================================


class E2BProvider(SandboxProvider):
    """CubeSandbox / E2B Cloud 硬件级沙箱 Provider

    隔离级别: HARDWARE (KVM MicroVM)
    适用场景: SaaS 云端 / 本地 CubeSandbox 集群

    文件模式:
    - virtiofs: 本地 CubeSandbox, 零拷贝挂载 (推荐)
    - sdk: 远程 E2B Cloud, SDK 上传 (按需)

    会话生命周期:
    - 按会话复用沙箱 (非每次创建/销毁)
    - 空闲 pause → 超时 destroy
    - WebSocket 断连 → grace 期 → 重连排空队列 / 超时销毁
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

        # E2B SDK 配置
        self.template_id = os.environ.get("DAWEI_SANDBOX_TEMPLATE", "code-interpreter")
        self.api_url = os.environ.get("DAWEI_SANDBOX_API_URL", "")
        # E2B SDK 要求 API key 格式为 e2b_ + hex; CubeSandbox auth 关闭时用占位符
        self.api_key = os.environ.get(
            "E2B_API_KEY",
            os.environ.get("DAWEI_SANDBOX_API_KEY", "e2b_0000000000000000000000000000000000000000"),
        )
        self.sync_strategy = config.get("sync_strategy", "auto")  # virtiofs | sdk | auto

        # 超时配置
        self.default_timeout = config.get("default_timeout", 30)
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
        self.disconnect_grace_seconds = config.get("disconnect_grace", 60)
        self._pending_commands: dict[str, list[CommandQueueEntry]] = {}
        self._scheduled_destroy: dict[str, float] = {}
        self._disconnected: dict[str, bool] = {}

        # N4: 网络策略
        self._network_policy: dict[str, Any] | None = None

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
        timeout: 接口契约参数（facade 强制透传）；E2B 侧超时暂用部署缺省。
        """
        self._check_quota(ctx)
        key = self._session_key(ctx)

        # === 情形 1: 会话存在且活跃 ===
        if key in self._sessions and not self._disconnected.get(key, False):
            return self._execute_on_session(key, command, ctx)

        # === 情形 2: 会话断开但在 grace 期内, 命令入队 ===
        if self._disconnected.get(key, False):
            destroy_at = self._scheduled_destroy.get(key, 0)
            if time.time() < destroy_at:
                return self._enqueue_command(key, command, ctx)
            # grace 期已过
            self._cleanup_disconnected_session(key)

        # === 情形 3: 创建新会话 ===
        return self._create_and_execute(key, command, ctx)

    async def execute_command_async(
        self,
        command: str,
        ctx: TrustedContext,
        timeout: int | None = None,
    ) -> SandboxResult:
        """异步执行命令 — 通过 asyncio.to_thread 包装"""
        return await asyncio.to_thread(self.execute_command, command, ctx, timeout)

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

        # 确定挂载模式
        mount_mode = self.config.get("workspace_mount_mode", "rw")

        # 创建沙箱
        sandbox = self._create_sandbox(validated_path, mount_mode, ctx)

        session = SandboxSession(
            sandbox=sandbox,
            user_id=ctx.user_id,
            workspace_id=str(ctx.workspace_id),
            mount_mode=mount_mode,
        )
        self._sessions[key] = session
        logger.info(
            "[E2B] 沙箱已创建: %s (mode=%s)",
            ctx.workspace_id,
            mount_mode,
        )
        return session

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
            **self._build_mount_config(workspace_path, mount_mode),
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
            "[E2B] virtiofs 沙箱已创建: %s (%s), .dawei/ 细粒度遮蔽已验证 "
            "(敏感: %d 目录 + %d 文件, 放行: files/agents/skills)",
            ctx.workspace_id,
            mount_mode,
            len(self.SENSITIVE_DAWEI_DIRS),
            len(self.SENSITIVE_DAWEI_FILES),
        )

        # === P3: 确保 dawei 源码可用 + 安装缺失依赖 ===
        self._ensure_dawei_available(sandbox, ctx)

        return sandbox

    def _ensure_dawei_available(self, sandbox: Any, ctx: TrustedContext) -> None:
        """P3: 确保沙箱内可以 import dawei 并运行工具

        步骤:
        1. 验证 /opt/dawei-src 挂载存在 (源码可读)
        2. 检查关键 Python 依赖是否已安装, 缺失则 pip install
        3. 验证 dawei 可导入

        失败时不抛异常 (仅 warning), 因为:
        - 工具路由有 host fallback (ToolExecutor 会回退到宿主执行)
        - 非工具命令 (execute_command) 不需要 dawei
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
        import_checks = []
        import_map = {
            "pydantic": "pydantic",
            "pydantic-settings": "pydantic_settings",
            "PyMuPDF": "fitz",
            "python-docx": "docx",
            "openpyxl": "openpyxl",
        }
        for pip_name, import_name in import_map.items():
            import_checks.append(
                f"python3 -c 'import {import_name}' 2>/dev/null || echo 'MISSING:{pip_name}'",
            )

        check_cmd = "; ".join(import_checks)
        dep_result = sandbox.commands.run(check_cmd, timeout=15)
        dep_stdout = getattr(dep_result, "stdout", "")

        missing = [
            line.split("MISSING:")[1].strip()
            for line in dep_stdout.splitlines()
            if "MISSING:" in line
        ]

        if missing:
            deps_str = " ".join(missing)
            logger.info(
                "[E2B] 沙箱内缺失依赖, 正在安装: %s",
                deps_str,
            )
            install_result = sandbox.commands.run(
                f"pip install {deps_str} 2>&1",
                timeout=120,
            )
            install_exit = getattr(install_result, "exit_code", -1)
            if install_exit != 0:
                install_err = getattr(install_result, "stderr", "") or \
                    getattr(install_result, "stdout", "unknown")
                logger.warning(
                    "[E2B] 依赖安装失败 (exit=%s): %s. "
                    "工具沙箱路由将回退到宿主执行",
                    install_exit,
                    str(install_err)[:200],
                )
            else:
                logger.info("[E2B] 依赖安装完成: %s", deps_str)
        else:
            logger.debug("[E2B] 沙箱内依赖完整, 无需安装")

        # 3. 验证 dawei 可导入
        verify_cmd = (
            f"PYTHONPATH={self.DAWEI_SRC_MOUNT_PATH} "
            "python3 -c 'import dawei; print(dawei.__version__)' 2>&1"
        )
        verify_result = sandbox.commands.run(verify_cmd, timeout=10)
        verify_stdout = getattr(verify_result, "stdout", "").strip()
        if "Error" in verify_stdout or "Traceback" in verify_stdout:
            logger.warning(
                "[E2B] 沙箱内 import dawei 失败: %s. "
                "工具沙箱路由将回退到宿主执行",
                verify_stdout[:200],
            )
        else:
            logger.info(
                "[E2B] 沙箱内 dawei 可用 (version=%s)",
                verify_stdout or "unknown",
            )

    # ================================================================
    # P2: F2 细粒度遮蔽配置与脚本生成
    # ================================================================

    # 敏感目录: 沙箱内不可见 (tmpfs 遮蔽)
    # 包含会话历史、对话记录、检查点、调度任务等
    SENSITIVE_DAWEI_DIRS: tuple[str, ...] = (
        "chat-history",
        "conversations",
        "checkpoints",
        "evolution",
        "scheduled_tasks",
        "task_graphs",
        "task_nodes",
        ".locks",
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
                f"if [ -d '{target}' ] && [ -n \"$(ls -A '{target}' 2>/dev/null)\" ]; then "
                f"echo 'LEAK:{d}'; LEAK=1; fi",
            )

        for f in self.SENSITIVE_DAWEI_FILES:
            target = f"/workspace/.dawei/{f}"
            checks.append(
                f"if [ -e '{target}' ] && [ -s '{target}' ]; then "
                f"echo 'LEAK:{f}'; LEAK=1; fi",
            )

        # 组装完整脚本
        script = "LEAK=0\n"
        script += "\n".join(checks)
        script += '\nif [ "$LEAK" -eq 0 ]; then echo OK; fi'
        return script

    # dawei 源码在沙箱内的挂载点
    DAWEI_SRC_MOUNT_PATH = "/opt/dawei-src"

    # 工具依赖的关键 Python 包 (沙箱内可能缺失)
    DAWEI_TOOL_DEPS: tuple[str, ...] = (
        "pydantic",
        "pydantic-settings",
        "PyMuPDF",       # fitz — read_file PDF 支持
        "python-docx",   # docx 系列工具
        "openpyxl",      # Excel 处理
    )

    def _build_mount_config(
        self,
        workspace_path: Path,
        mount_mode: str,
    ) -> dict[str, Any]:
        """构建 CubeSandbox 挂载配置

        CubeSandbox 使用 ``metadata["host-mount"]`` 扩展字段传递挂载描述,
        格式为 JSON-encoded list of ``{hostPath, mountPath, readOnly}``。
        标准 E2B ``mounts=`` 参数不被 CubeSandbox 识别。

        P3: 额外挂载 agent 源码到 /opt/dawei-src (只读),
        使沙箱内可 import dawei 而无需 pip install。
        """
        read_only = mount_mode == "ro"
        mounts: list[dict[str, Any]] = [
            {
                "hostPath": str(workspace_path.resolve()),
                "mountPath": "/workspace",
                "readOnly": read_only,
            },
        ]

        # P3: 挂载 agent 源码 (只读), 使 dawei 在沙箱内可导入
        dawei_src = self._find_dawei_source_path()
        if dawei_src:
            mounts.append({
                "hostPath": str(dawei_src),
                "mountPath": self.DAWEI_SRC_MOUNT_PATH,
                "readOnly": True,
            })
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
        # 【2026-09-12 能力检测】新版 e2b SDK 的 Sandbox.create 不再接受
        # network_policy kwarg（改用 network: SandboxNetworkOpts）→ 盲注入必然
        # ConnectionConfig TypeError，沙箱创建整体失败。SDK 不支持时跳过注入
        # 并告警（fail-open：仅少一层出网限制，MicroVM 隔离本身不受影响）。
        if e2b_supports_network_policy():
            policy = self._load_network_policy()
            if policy:
                config["network_policy"] = policy
        else:
            logger.warning(
                "[E2B] 已装 e2b SDK 不支持 network_policy 参数, 跳过 N4 网络策略注入（沙箱隔离不受影响）",
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
    ) -> SandboxResult:
        """在已有会话上执行命令"""
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
        start_time = time.time()
        try:
            result = session.sandbox.commands.run(
                command,
                cwd="/workspace",
                timeout=self.default_timeout,
            )
            execution_time = int((time.time() - start_time) * 1000)
            session.last_active = time.time()

            exit_code = getattr(result, "exit_code", 0)
            stdout = getattr(result, "stdout", "")
            stderr = getattr(result, "stderr", "")

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
            logger.error("[E2B] 命令执行异常: %s", e, exc_info=True)
            return SandboxResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
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
    ) -> SandboxResult:
        """创建新会话并执行命令"""
        self._get_or_create_session(key, ctx)
        return self._execute_on_session(key, command, ctx)

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

    def _destroy_session_by_key(self, key: str) -> None:
        """销毁指定 key 的沙箱会话"""
        session = self._sessions.pop(key, None)
        if session and session.sandbox:
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
            if not session.is_paused and now - session.last_active > self.idle_pause_seconds:
                try:
                    session.sandbox.pause()
                    session.is_paused = True
                    logger.info("[E2B] 空闲 pause 沙箱: %s", key)
                except Exception as e:
                    logger.warning("[E2B] pause 异常: %s", e)

        # 清理过期的 grace 期会话
        for key in list(self._scheduled_destroy.keys()):
            if time.time() >= self._scheduled_destroy[key]:
                self._cleanup_disconnected_session(key)
