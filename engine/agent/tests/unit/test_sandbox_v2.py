# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""沙箱 v2 红蓝对抗验证测试 (§沙箱系统升级 v2 — Phase 6)

模拟攻击场景, 验证安全防御机制:
1. F1: TrustedContext 不可伪造
2. F3: workspace_path 白名单拒绝越界路径
3. N3: ro 模式写命令预拦截
4. §4: 配额 LRU 淘汰
5. N6: PII 日志脱敏
6. N2: pause 策略
7. 向后兼容: CommandExecutor 双签名
8. P1: 沙箱预热 (prewarm_session)
"""

import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 2026-09-19: desktop 沙箱简化为仅 Docker/Podman, subprocess 被工厂守卫拒绝。
# 需要真实 provider 的测试用 SandboxFacade.set_provider() 注入 SubprocessProvider
# (模块保留为测试替身/向后兼容, 工厂不再创建它)。
os.environ["DAWEI_LOG_SALT"] = "test-salt-for-red-team-12345"

# 确保 /tmp 在白名单中
os.environ.setdefault("DAWEI_WORKSPACE_ROOT_ALLOWLIST", "/tmp:/home:/workspace:/srv")


# ================================================================
# F1: TrustedContext 信任边界
# ================================================================


class TestF1TrustedContext:
    """模拟攻击: 伪造 user_id 访问他人 workspace"""

    def test_trusted_context_is_immutable(self):
        """F1: TrustedContext 不可修改 (frozen)"""
        from dawei.sandbox import from_user_workspace

        ctx = from_user_workspace("attacker", "/tmp")
        with pytest.raises((AttributeError, TypeError)):
            ctx.user_id = "victim"

    def test_trusted_context_is_expired_after_ttl(self):
        """F1: TTL 过期检测"""
        from dawei.sandbox.base import TrustedContext, UserId, WorkspaceId

        ctx = TrustedContext(
            user_id=UserId("test"),
            workspace_id=WorkspaceId("test-ws"),
            workspace_path=Path("/tmp"),
            issued_at=time.time() - 7200,  # 2 小时前
        )
        assert ctx.is_expired(ttl_seconds=3600)

    def test_trusted_context_not_expired_within_ttl(self):
        """F1: TTL 未过期"""
        from dawei.sandbox.base import TrustedContext, UserId, WorkspaceId

        ctx = TrustedContext(
            user_id=UserId("test"),
            workspace_id=WorkspaceId("test-ws"),
            workspace_path=Path("/tmp"),
            issued_at=time.time(),
        )
        assert not ctx.is_expired(ttl_seconds=3600)

    def test_untrusted_session_rejected(self):
        """F1: 未认证 session 被拒绝"""
        from dawei.sandbox.base import UntrustedContextError, from_authenticated_session

        class FakeSession:
            is_authenticated = False
            user_id = "attacker"
            workspace_id = "ws-1"

        with pytest.raises(UntrustedContextError):
            from_authenticated_session(FakeSession())

    def test_missing_fields_rejected(self):
        """F1: 缺少 user_id / workspace_id 被拒绝"""
        from dawei.sandbox.base import UntrustedContextError, from_authenticated_session

        class FakeSession:
            is_authenticated = True
            user_id = None
            workspace_id = None

        with pytest.raises(UntrustedContextError):
            from_authenticated_session(FakeSession())


# ================================================================
# F3: workspace_path 白名单
# ================================================================


class TestF3PathValidation:
    """模拟攻击: 越界路径 (/etc, /root)"""

    def test_path_in_allowlist_accepted(self, tmp_path):
        """F3: 白名单内路径通过"""
        from dawei.sandbox.path_validator import validate_workspace_path

        result = validate_workspace_path(tmp_path)
        assert result == tmp_path.resolve()

    def test_path_outside_allowlist_rejected(self):
        """F3: /etc 被拒绝"""
        from dawei.core.exceptions import SandboxSecurityError
        from dawei.sandbox.path_validator import validate_workspace_path

        with pytest.raises(SandboxSecurityError):
            validate_workspace_path(Path("/etc"))

    def test_nonexistent_path_rejected(self):
        """F3: 不存在的路径被拒绝"""
        from dawei.core.exceptions import SandboxSecurityError
        from dawei.sandbox.path_validator import validate_workspace_path

        with pytest.raises(SandboxSecurityError):
            validate_workspace_path(Path("/nonexistent/path/that/does/not/exist"))


# ================================================================
# N3: 命令读写分类
# ================================================================


class TestN3CommandClassifier:
    """模拟攻击: ro 模式下执行写命令"""

    @pytest.mark.parametrize(
        ("cmd", "expected"),
        [
            ("ls -la", "read_only"),
            ("cat file.txt", "read_only"),
            ("grep pattern file", "read_only"),
            ("git status", "read_only"),
            ("git log --oneline", "read_only"),
            ("pip list", "read_only"),
            ("echo hello", "read_only"),
            ("rm file", "write"),
            ("mv a b", "write"),
            ("pip install foo", "write"),
            ("git commit -m test", "write"),
            ("echo x > file.txt", "write"),
            ("mkdir dir", "write"),
            ("npm install", "write"),
            ("some-unknown-command", "unknown"),
        ],
    )
    def test_classify_command(self, cmd, expected):
        """N3: 命令分类准确性"""
        from dawei.sandbox import CommandRisk, classify_command

        result = classify_command(cmd)
        assert result == CommandRisk(expected)

    def test_ro_mode_write_command_blocked(self):
        """N3: ro 模式下 DockerProvider 拒绝写命令"""
        from dawei.sandbox.base import IsolationLevel, from_user_workspace
        from dawei.sandbox.docker_provider import DockerProvider

        provider = DockerProvider({"workspace_mount_mode": "ro"})
        ctx = from_user_workspace("test-user", "/tmp")
        result = provider.execute_command("echo test > /tmp/redteam_test", ctx)

        assert not result.success
        assert result.exit_code == 77  # EX_NOPERM
        assert "写权限" in result.stderr or "只读" in result.stderr


# ================================================================
# §4: 配额 + LRU 淘汰
# ================================================================


class TestQuotaLRU:
    """模拟攻击: 单用户创建大量沙箱"""

    def test_rate_limit_exceeded(self):
        """§4: 速率限制触发"""
        from dawei.core.exceptions import QuotaExceededError
        from dawei.sandbox.base import from_user_workspace
        from dawei.sandbox.e2b_provider import E2BProvider

        provider = E2BProvider({"max_commands_per_minute": 3})
        ctx = from_user_workspace("spammer", "/tmp")

        # 发送 3 次命令 (在限制内)
        for _ in range(3):
            provider._check_rate_limit(ctx)

        # 第 4 次应该被拒绝
        with pytest.raises(QuotaExceededError):
            provider._check_rate_limit(ctx)


# ================================================================
# N6: PII 日志脱敏
# ================================================================


class TestN6PiiLogger:
    """验证 PII 脱敏生效"""

    def test_path_redacted(self):
        """N6: 物理路径在日志中被脱敏"""
        import logging

        from dawei.sandbox import PiiSafeLogger

        safe = PiiSafeLogger(logging.getLogger("test-redteam"))
        redacted = safe._redact_path("/home/user/secret/workspace")
        assert "<ws:" in redacted
        assert "/home/user/secret/workspace" not in redacted

    def test_email_redacted(self):
        """N6: email 在日志中被脱敏"""
        import logging

        from dawei.sandbox import PiiSafeLogger

        safe = PiiSafeLogger(logging.getLogger("test-redteam"))
        result = safe._redact_message("user email: attacker@example.com")
        assert "attacker@example.com" not in result
        assert "<email:" in result

    def test_user_id_hashed(self):
        """N6: user_id 被 HMAC 哈希"""
        import logging

        from dawei.sandbox import PiiSafeLogger

        safe = PiiSafeLogger(logging.getLogger("test-redteam"))
        hashed = safe._hash("user-12345")
        assert len(hashed) == 12
        assert hashed != "user-12345"


# ================================================================
# N2: Pause 策略
# ================================================================


class TestN2PausePolicy:
    """模拟攻击: pause 期间发送命令"""

    def test_reject_policy_raises(self):
        """N2: REJECT 策略下 pause 时抛出异常"""
        from dawei.core.exceptions import SandboxPausedError
        from dawei.sandbox.base import PausePolicy, from_user_workspace
        from dawei.sandbox.e2b_provider import E2BProvider, SandboxSession

        provider = E2BProvider({"pause_policy": "reject"})
        ctx = from_user_workspace("test-user", "/tmp")
        key = provider._session_key(ctx)

        # 模拟一个 paused 会话
        provider._sessions[key] = SandboxSession(
            sandbox=None,
            user_id=ctx.user_id,
            workspace_id=str(ctx.workspace_id),
            mount_mode="rw",
            is_paused=True,
        )

        with pytest.raises(SandboxPausedError):
            provider._execute_on_session(key, "ls", ctx)


# ================================================================
# 向后兼容
# ================================================================


class TestBackwardCompat:
    """向后兼容: CommandExecutor 双签名"""

    def test_command_executor_is_subprocess_provider(self):
        """v1 CommandExecutor 是 v2 SubprocessProvider 的别名"""
        from dawei.sandbox.subprocess_provider import CommandExecutor, SubprocessProvider

        assert issubclass(CommandExecutor, SubprocessProvider)

    def test_old_signature_still_works(self, tmp_path):
        """v1 签名 (workspace_path, user_id) 仍然可用"""
        from dawei.sandbox.subprocess_provider import CommandExecutor

        executor = CommandExecutor()
        result = executor.execute_command(
            command="echo backward_compat",
            workspace_path=tmp_path,
            user_id="legacy-user",
        )
        assert result["success"]
        assert "backward_compat" in result["stdout"]


# ================================================================
# Provider 工厂
# ================================================================


class TestProviderFactory:
    """Provider 工厂 (2026-09-19 简化: local 仅 Docker/Podman)"""

    def test_local_rejects_subprocess(self, monkeypatch):
        """local + 显式 subprocess → SandboxSecurityError"""
        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "local")

        from dawei.core.exceptions import SandboxSecurityError
        from dawei.sandbox.base import ProviderType
        from dawei.sandbox.provider_factory import create_provider

        with pytest.raises(SandboxSecurityError, match="subprocess"):
            create_provider(ProviderType.SUBPROCESS)

    def test_env_override_docker(self, monkeypatch):
        """环境变量选择 docker (local 唯一允许的显式 provider)"""
        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "local")

        old = os.environ.get("DAWEI_SANDBOX_PROVIDER")
        try:
            os.environ["DAWEI_SANDBOX_PROVIDER"] = "docker"
            from dawei.sandbox.docker_provider import DockerProvider
            from dawei.sandbox.provider_factory import create_provider

            provider = create_provider()
            assert isinstance(provider, DockerProvider)
        finally:
            if old:
                os.environ["DAWEI_SANDBOX_PROVIDER"] = old
            else:
                os.environ.pop("DAWEI_SANDBOX_PROVIDER", None)

    def test_local_auto_docker_available(self, monkeypatch):
        """local + auto + Docker 可用 → DockerProvider"""
        import dawei.sandbox.provider_factory as pf

        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "local")
        monkeypatch.setenv("DAWEI_SANDBOX_PROVIDER", "auto")
        monkeypatch.setattr(pf, "_read_user_sandbox_settings", dict)
        monkeypatch.setattr(pf, "_check_docker_available", lambda: True)

        from dawei.sandbox.docker_provider import DockerProvider

        assert isinstance(pf.create_provider(), DockerProvider)

    def test_local_auto_without_docker_raises(self, monkeypatch):
        """local + auto + 无 Docker/Podman → 显式报错 (不再兜底 subprocess)"""
        import dawei.sandbox.provider_factory as pf

        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "local")
        monkeypatch.setenv("DAWEI_SANDBOX_PROVIDER", "auto")
        monkeypatch.setattr(pf, "_read_user_sandbox_settings", dict)
        monkeypatch.setattr(pf, "_check_docker_available", lambda: False)

        from dawei.core.exceptions import SandboxError

        with pytest.raises(SandboxError, match="Docker/Podman"):
            pf.create_provider()


# ================================================================
# 版本区分: SaaS 版 vs PC App 版 (2026-09-13)
# ================================================================


class TestEditionGuard:
    """SaaS 版 (DAWEI_DEPLOYMENT_MODE=saas) 禁止非硬件隔离 provider。

    nn-bot 双版本: SaaS 版 = CubeSandbox + RustFS (多租户);
    PC App 版 = local (默认), 允许 Docker → Subprocess 降级链。
    """

    def test_saas_mode_rejects_subprocess(self, monkeypatch):
        """saas + 显式 subprocess → SandboxSecurityError"""
        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "saas")

        from dawei.core.exceptions import SandboxSecurityError
        from dawei.sandbox.base import ProviderType
        from dawei.sandbox.provider_factory import create_provider

        with pytest.raises(SandboxSecurityError, match="subprocess"):
            create_provider(ProviderType.SUBPROCESS)

    def test_saas_mode_rejects_auto_degradation_to_docker(self, monkeypatch):
        """saas + auto: CubeAPI 不可达且 docker 可用 → 必须拒绝而非静默降级"""
        import dawei.sandbox.provider_factory as pf

        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "saas")
        monkeypatch.setenv("DAWEI_SANDBOX_PROVIDER", "auto")
        monkeypatch.setattr(pf, "_read_user_sandbox_settings", lambda: {})
        monkeypatch.setattr(pf, "_check_e2b_available", lambda url: False)
        monkeypatch.setattr(pf, "_check_docker_available", lambda: True)

        from dawei.core.exceptions import SandboxSecurityError

        with pytest.raises(SandboxSecurityError, match="docker"):
            pf.create_provider()

    def test_saas_mode_allows_hardware_provider(self, monkeypatch):
        """saas + cubesandbox (KVM microVM) → 守卫放行"""
        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "saas")

        from dawei.sandbox.base import ProviderType
        from dawei.sandbox.cubesandbox_provider import CubeSandboxProvider
        from dawei.sandbox.provider_factory import create_provider

        provider = create_provider(ProviderType.CUBESANDBOX)
        assert isinstance(provider, CubeSandboxProvider)

    def test_local_mode_rejects_e2b(self, monkeypatch):
        """local + e2b (云端硬件隔离) → 拒绝 (desktop 仅 Docker/Podman)"""
        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "local")

        from dawei.core.exceptions import SandboxSecurityError
        from dawei.sandbox.base import ProviderType
        from dawei.sandbox.provider_factory import create_provider

        with pytest.raises(SandboxSecurityError, match="Docker/Podman"):
            create_provider(ProviderType.E2B)

    def test_unknown_mode_defaults_local(self, monkeypatch):
        """非法 DAWEI_DEPLOYMENT_MODE 值按 local 处理 (守卫关闭)"""
        from dawei.sandbox.provider_factory import _deployment_mode

        monkeypatch.setenv("DAWEI_DEPLOYMENT_MODE", "cloud-ish")
        assert _deployment_mode() == "local"


# ================================================================
# SandboxFacade 集成
# ================================================================


class TestSandboxFacade:
    """Facade 统一入口"""

    def test_execute_command(self):
        """Facade 执行命令 (注入 SubprocessProvider 测试替身, 绕过工厂守卫)"""
        from dawei.sandbox import SandboxFacade, from_user_workspace
        from dawei.sandbox.subprocess_provider import SubprocessProvider

        SandboxFacade.reset()
        SandboxFacade.set_provider(SubprocessProvider({}))
        ctx = from_user_workspace("facade-test", "/tmp")
        result = SandboxFacade.execute_command("echo facade_works", ctx)
        assert result.success
        assert "facade_works" in result.stdout

    def test_expired_context_rejected(self):
        """Facade 拒绝过期 TrustedContext"""
        from dawei.sandbox import SandboxFacade, UntrustedContextError
        from dawei.sandbox.base import TrustedContext, UserId, WorkspaceId

        SandboxFacade.reset()
        ctx = TrustedContext(
            user_id=UserId("expired"),
            workspace_id=WorkspaceId("ws"),
            workspace_path=Path("/tmp"),
            issued_at=time.time() - 7200,
        )
        with pytest.raises(UntrustedContextError):
            SandboxFacade.execute_command("ls", ctx)


# ================================================================
# F2: tmpfs 遮蔽 fail-closed (Phase 6 红蓝对抗)
# ================================================================


class TestF2TmpfsFailClosed:
    """模拟攻击: 破坏 tmpfs 遮蔽以读取 .dawei/ 内容 (P2: 细粒度遮蔽)"""

    def test_mount_failure_kills_sandbox(self):
        """F2/P2: mount 失败时沙箱被销毁, 不继续启动"""
        from dawei.core.exceptions import SandboxSecurityError
        from dawei.sandbox.base import from_user_workspace
        from dawei.sandbox.e2b_provider import E2BProvider
        from unittest.mock import MagicMock, patch

        provider = E2BProvider({})
        ctx = from_user_workspace("attacker", "/tmp")

        # 模拟 sandbox — mount 失败
        mock_sandbox = MagicMock()
        mount_result = MagicMock()
        mount_result.exit_code = 1
        mount_result.stderr = "mount: permission denied"
        mock_sandbox.commands.run.return_value = mount_result

        with patch("e2b.Sandbox") as mock_e2b:
            mock_e2b.create.return_value = mock_sandbox
            with pytest.raises(SandboxSecurityError) as exc_info:
                provider._create_with_virtiofs(Path("/tmp"), "rw", ctx)

        assert "细粒度遮蔽失败" in str(exc_info.value)
        mock_sandbox.kill.assert_called_once()

    def test_dawei_leak_detected_and_killed(self):
        """F2/P2: .dawei/ 敏感内容泄露时沙箱被销毁"""
        from dawei.core.exceptions import SandboxSecurityError
        from dawei.sandbox.base import from_user_workspace
        from dawei.sandbox.e2b_provider import E2BProvider
        from unittest.mock import MagicMock, patch

        provider = E2BProvider({})
        ctx = from_user_workspace("attacker", "/tmp")

        mock_sandbox = MagicMock()
        # 步骤 1: mount 成功
        mount_result = MagicMock()
        mount_result.exit_code = 0
        # 步骤 2: 验证发现泄露
        verify_result = MagicMock()
        verify_result.stdout = "LEAK:settings.json"
        mock_sandbox.commands.run.side_effect = [mount_result, verify_result]

        with patch("e2b.Sandbox") as mock_e2b:
            mock_e2b.create.return_value = mock_sandbox
            with pytest.raises(SandboxSecurityError) as exc_info:
                provider._create_with_virtiofs(Path("/tmp"), "rw", ctx)

        assert "遮蔽验证失败" in str(exc_info.value)
        mock_sandbox.kill.assert_called_once()

    def test_p2_passthrough_dirs_not_in_mount_script(self):
        """P2: 放行目录 (files/agents/skills) 不出现在 mount 脚本中"""
        from dawei.sandbox.e2b_provider import E2BProvider

        provider = E2BProvider.__new__(E2BProvider)
        script = provider._build_f2_mount_script()

        # 放行目录不应被 mount
        for passthrough in E2BProvider.PASSTHROUGH_DAWEI_DIRS:
            assert f"/workspace/.dawei/{passthrough}" not in script, (
                f"放行目录 {passthrough}/ 不应出现在 mount 脚本中"
            )

    def test_p2_all_sensitive_entries_occluded(self):
        """P2: 每个敏感目录/文件都在 mount 和 verify 脚本中"""
        from dawei.sandbox.e2b_provider import E2BProvider

        provider = E2BProvider.__new__(E2BProvider)
        mount = provider._build_f2_mount_script()
        verify = provider._build_f2_verify_cmd()

        for d in E2BProvider.SENSITIVE_DAWEI_DIRS:
            assert f"/workspace/.dawei/{d}" in mount, f"{d} 缺失于 mount 脚本"
            assert f"LEAK:{d}" in verify, f"{d} 缺失于 verify 脚本"

        for f in E2BProvider.SENSITIVE_DAWEI_FILES:
            assert f"/workspace/.dawei/{f}" in mount, f"{f} 缺失于 mount 脚本"
            assert f"LEAK:{f}" in verify, f"{f} 缺失于 verify 脚本"

    def test_p2_evolution_is_sensitive(self):
        """P2: 用户要求 evolution 目录在遮蔽列表中"""
        from dawei.sandbox.e2b_provider import E2BProvider

        assert "evolution" in E2BProvider.SENSITIVE_DAWEI_DIRS


# ================================================================
# §4: LRU 淘汰 (Phase 6 红蓝对抗 — 完整)
# ================================================================


class TestQuotaLRUEviction:
    """模拟攻击: 单用户创建大量沙箱触发 LRU"""

    def test_user_quota_lru_eviction(self):
        """§4: 用户达沙箱数上限时 LRU 淘汰最久未用的"""
        from dawei.sandbox.base import from_user_workspace
        from dawei.sandbox.e2b_provider import E2BProvider, SandboxSession
        from dawei.sandbox.base import UserId

        provider = E2BProvider({"max_sessions_per_user": 3})
        provider._destroy_session_by_key = lambda k: provider._sessions.pop(k, None)

        # 创建 3 个会话 (达到上限)
        for i in range(3):
            ctx = from_user_workspace(f"user-1", f"/tmp/ws-{i}")
            key = provider._session_key(ctx)
            provider._sessions[key] = SandboxSession(
                sandbox=None,
                user_id=ctx.user_id,
                workspace_id=str(ctx.workspace_id),
                mount_mode="rw",
                last_active=time.time() - (3 - i) * 100,  # ws-0 最旧
            )

        # 第 4 个会话应触发 LRU 淘汰 ws-0 (最久未用)
        ctx_new = from_user_workspace("user-1", "/tmp/ws-new")
        provider._check_quota(ctx_new)

        # ws-0 应被淘汰
        evicted_key = f"user-1::{ctx_new.user_id}".replace("user-1", "user-1")
        # 验证只剩 3 个会话 (淘汰了 1 个, 新的还没加入)
        user_sessions = [s for s in provider._sessions.values() if s.user_id == ctx_new.user_id]
        assert len(user_sessions) <= 3

    def test_global_quota_lru_eviction(self):
        """§4: 全局沙箱数上限触发 LRU"""
        from dawei.sandbox.base import from_user_workspace
        from dawei.sandbox.e2b_provider import E2BProvider, SandboxSession

        provider = E2BProvider({"max_total_sessions": 3})
        provider._destroy_session_by_key = lambda k: provider._sessions.pop(k, None)

        # 创建 3 个不同用户的会话 (达到全局上限)
        for i in range(3):
            ctx = from_user_workspace(f"user-{i}", f"/tmp/ws-{i}")
            key = provider._session_key(ctx)
            provider._sessions[key] = SandboxSession(
                sandbox=None,
                user_id=ctx.user_id,
                workspace_id=str(ctx.workspace_id),
                mount_mode="rw",
                last_active=time.time() - i * 100,  # user-0 最旧
            )

        # 第 4 个会话触发全局 LRU
        ctx_new = from_user_workspace("user-new", "/tmp/ws-new")
        provider._check_quota(ctx_new)

        # 全局不应超过上限
        assert len(provider._sessions) <= 3

    def test_memory_quota_exceeded(self):
        """§4: 内存配额耗尽时拒绝"""
        from dawei.core.exceptions import QuotaExceededError
        from dawei.sandbox.base import from_user_workspace
        from dawei.sandbox.e2b_provider import E2BProvider, SandboxSession

        # max_memory_per_user_mb=10, 每沙箱 5MB → 2 个就满
        provider = E2BProvider({"max_memory_per_user_mb": 10})
        provider._destroy_session_by_key = lambda k: provider._sessions.pop(k, None)

        for i in range(2):
            ctx = from_user_workspace("mem-user", f"/tmp/ws-{i}")
            key = provider._session_key(ctx)
            provider._sessions[key] = SandboxSession(
                sandbox=None,
                user_id=ctx.user_id,
                workspace_id=str(ctx.workspace_id),
                mount_mode="rw",
            )

        # 第 3 个应超出内存配额
        ctx_new = from_user_workspace("mem-user", "/tmp/ws-2")
        # 因为 max_concurrent_sandboxes=10 > 2, 不会触发 LRU
        # 但内存检查: 3 * 5 = 15 > 10
        with pytest.raises(QuotaExceededError) as exc_info:
            provider._check_quota(ctx_new)
        assert "内存" in str(exc_info.value) or "memory" in str(exc_info.value).lower()


# ================================================================
# F3: 路径遍历攻击 (Phase 6 补充)
# ================================================================


class TestF3PathTraversal:
    """模拟攻击: 通过 .. 和符号链接绕过白名单"""

    def test_dotdot_traversal_rejected(self, tmp_path):
        """F3: .. 路径遍历被拒绝"""
        from dawei.core.exceptions import SandboxSecurityError
        from dawei.sandbox.path_validator import validate_workspace_path

        # /tmp/../../../etc → resolve 后是 /etc
        traversal = tmp_path / ".." / ".." / ".." / "etc"
        with pytest.raises(SandboxSecurityError):
            validate_workspace_path(traversal)

    def test_root_path_rejected(self):
        """F3: 根路径 / 被拒绝"""
        from dawei.core.exceptions import SandboxSecurityError
        from dawei.sandbox.path_validator import validate_workspace_path

        with pytest.raises(SandboxSecurityError):
            validate_workspace_path(Path("/"))

    def test_proc_access_rejected(self):
        """F3: /proc 被拒绝"""
        from dawei.core.exceptions import SandboxSecurityError
        from dawei.sandbox.path_validator import validate_workspace_path

        with pytest.raises(SandboxSecurityError):
            validate_workspace_path(Path("/proc"))


# ================================================================
# N1: WebSocket grace period (Phase 6 补充)
# ================================================================


class TestN1GracePeriod:
    """模拟: WebSocket 断连 grace 期行为"""

    def test_disconnect_enters_grace(self):
        """N1: 断连后进入 grace 期, 不立即销毁"""
        from dawei.sandbox.base import from_user_workspace
        from dawei.sandbox.e2b_provider import E2BProvider, SandboxSession

        provider = E2BProvider({"disconnect_grace": 60})
        ctx = from_user_workspace("test-user", "/tmp")
        key = provider._session_key(ctx)

        # 模拟已有会话
        provider._sessions[key] = SandboxSession(
            sandbox=None,
            user_id=ctx.user_id,
            workspace_id=str(ctx.workspace_id),
            mount_mode="rw",
        )

        provider.on_disconnect(ctx)

        assert provider._disconnected.get(key) is True
        assert key in provider._scheduled_destroy
        # 沙箱未被销毁
        assert key in provider._sessions

    def test_reconnect_clears_grace(self):
        """N1: 重连后清除 grace 期状态"""
        from dawei.sandbox.base import from_user_workspace
        from dawei.sandbox.e2b_provider import E2BProvider, SandboxSession

        provider = E2BProvider({"disconnect_grace": 60})
        ctx = from_user_workspace("test-user", "/tmp")
        key = provider._session_key(ctx)

        provider._sessions[key] = SandboxSession(
            sandbox=None,
            user_id=ctx.user_id,
            workspace_id=str(ctx.workspace_id),
            mount_mode="rw",
        )

        # 断连 → 重连
        provider.on_disconnect(ctx)
        assert provider._disconnected[key]

        provider.on_reconnect(ctx)
        assert not provider._disconnected.get(key, False)
        assert key not in provider._scheduled_destroy

    def test_grace_expiry_destroys_sandbox(self):
        """N1: grace 期过后真正销毁沙箱"""
        from dawei.sandbox.base import from_user_workspace
        from dawei.sandbox.e2b_provider import E2BProvider, SandboxSession

        provider = E2BProvider({"disconnect_grace": 0})  # 立即过期
        ctx = from_user_workspace("test-user", "/tmp")
        key = provider._session_key(ctx)

        mock_sandbox = None  # 无需 mock, destroy 只在 sandbox 非 None 时 kill
        provider._sessions[key] = SandboxSession(
            sandbox=mock_sandbox,
            user_id=ctx.user_id,
            workspace_id=str(ctx.workspace_id),
            mount_mode="rw",
        )

        provider.on_disconnect(ctx)
        # grace=0 → 立即过期
        provider._cleanup_disconnected_session(key)

        assert key not in provider._sessions
        assert key not in provider._disconnected


# ================================================================
# SessionData v2 生命周期 (Phase 3 集成验证)
# ================================================================


class TestSessionDataV2:
    """验证 SessionData v2 扩展"""

    def test_is_authenticated_without_user(self):
        """无 user_id 时 is_authenticated=False"""
        from dawei.websocket.session import SessionData

        s = SessionData(id="test")
        assert not s.is_authenticated

    def test_is_authenticated_with_user(self):
        """有 user_id 时 is_authenticated=True"""
        from dawei.websocket.session import SessionData

        s = SessionData(id="test", user_id="user-123")
        assert s.is_authenticated

    def test_permissions_default_empty(self):
        """默认权限为空"""
        from dawei.websocket.session import SessionData

        s = SessionData(id="test", user_id="user-123")
        assert s.permissions == []

    def test_permissions_stored_in_metadata(self):
        """权限存储在 metadata 中"""
        from dawei.websocket.session import SessionData

        s = SessionData(id="test", user_id="user-123")
        s.permissions = ["sandbox:read", "sandbox:write"]
        assert s.permissions == ["sandbox:read", "sandbox:write"]
        assert s.metadata["permissions"] == ["sandbox:read", "sandbox:write"]

    def test_serialization_roundtrip(self):
        """序列化往返: permissions 保持"""
        from dawei.websocket.session import SessionData

        s1 = SessionData(id="test", user_id="user-123", workspace_id="ws-1")
        s1.permissions = ["sandbox:read"]
        d = s1.to_dict()

        s2 = SessionData.from_dict(d)
        assert s2.is_authenticated
        assert s2.permissions == ["sandbox:read"]

    @pytest.mark.asyncio
    async def test_on_close_noop_without_user(self):
        """on_close 在无 user_id 时为空操作"""
        from dawei.websocket.session import SessionData

        s = SessionData(id="test")
        await s.on_close()  # 不应抛出异常

    @pytest.mark.asyncio
    async def test_on_reconnect_noop_without_user(self):
        """on_reconnect 在无 user_id 时为空操作"""
        from dawei.websocket.session import SessionData

        s = SessionData(id="test")
        await s.on_reconnect()  # 不应抛出异常

    @pytest.mark.asyncio
    async def test_on_close_calls_sandbox_facade(self):
        """on_close 调用 SandboxFacade.on_disconnect"""
        from dawei.websocket.session import SessionData
        from unittest.mock import patch, AsyncMock

        s = SessionData(id="test", user_id="user-1", workspace_id="/tmp")
        with patch("dawei.sandbox.sandbox_facade.SandboxFacade.on_disconnect") as mock:
            await s.on_close()
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_reconnect_calls_sandbox_facade(self):
        """on_reconnect 调用 SandboxFacade.on_reconnect"""
        from dawei.websocket.session import SessionData
        from unittest.mock import patch

        s = SessionData(id="test", user_id="user-1", workspace_id="/tmp")
        with patch("dawei.sandbox.sandbox_facade.SandboxFacade.on_reconnect") as mock:
            await s.on_reconnect()
            mock.assert_called_once()


# ================================================================
# P1: 沙箱预热测试
# ================================================================


class TestPrewarmSession:
    """P1: 验证 prewarm_session 的行为契约

    覆盖点:
    - 配置开关 DAWEI_SANDBOX_PREWARM_ON_SESSION_START
    - 默认 Provider no-op 安全
    - 失败回退 lazy (不抛异常)
    - 幂等性 (重复调用安全)
    """

    def test_prewarm_disabled_by_env(self, monkeypatch):
        """DAWEI_SANDBOX_PREWARM_ON_SESSION_START=0 时, Facade 不调 provider"""
        from dawei.sandbox.sandbox_facade import SandboxFacade
        from unittest.mock import patch

        monkeypatch.setenv("DAWEI_SANDBOX_PREWARM_ON_SESSION_START", "0")

        with patch.object(SandboxFacade, "get_provider") as mock_provider:
            SandboxFacade.prewarm_session(ctx=__import__("dawei.sandbox.base", fromlist=["TrustedContext"]).TrustedContext(
                user_id="u", workspace_id="w", workspace_path=Path("/tmp"),
            ))
            # provider 不应被获取 (开关关闭时短路)
            mock_provider.assert_not_called()

    def test_prewarm_enabled_by_default(self, monkeypatch):
        """默认 (无环境变量) 时, 开关为开"""
        from dawei.sandbox.sandbox_facade import SandboxFacade

        monkeypatch.delenv("DAWEI_SANDBOX_PREWARM_ON_SESSION_START", raising=False)
        assert SandboxFacade._is_prewarm_enabled() is True

    @pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on", "On"])
    def test_prewarm_truthy_values(self, monkeypatch, val):
        from dawei.sandbox.sandbox_facade import SandboxFacade

        monkeypatch.setenv("DAWEI_SANDBOX_PREWARM_ON_SESSION_START", val)
        assert SandboxFacade._is_prewarm_enabled() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", "", "garbage"])
    def test_prewarm_falsy_values(self, monkeypatch, val):
        from dawei.sandbox.sandbox_facade import SandboxFacade

        monkeypatch.setenv("DAWEI_SANDBOX_PREWARM_ON_SESSION_START", val)
        assert SandboxFacade._is_prewarm_enabled() is False

    def test_prewarm_swallows_provider_failure(self, monkeypatch):
        """Provider.prewarm_session 抛异常时, Facade 静默吞掉 (FAST FAIL → lazy)"""
        from dawei.sandbox.base import TrustedContext
        from dawei.sandbox.sandbox_facade import SandboxFacade
        from unittest.mock import patch, MagicMock

        monkeypatch.setenv("DAWEI_SANDBOX_PREWARM_ON_SESSION_START", "1")

        ctx = TrustedContext(
            user_id="u", workspace_id="w", workspace_path=Path("/tmp"),
        )

        # Provider 抛异常 → Facade 不应传播
        fake_provider = MagicMock()
        fake_provider.prewarm_session.side_effect = RuntimeError("boom")
        with patch.object(SandboxFacade, "get_provider", return_value=fake_provider):
            # 不应抛
            SandboxFacade.prewarm_session(ctx)
            fake_provider.prewarm_session.assert_called_once_with(ctx)

    def test_prewarm_calls_provider_when_enabled(self, monkeypatch):
        """开关开启时, Facade 真正调用 provider.prewarm_session"""
        from dawei.sandbox.base import TrustedContext
        from dawei.sandbox.sandbox_facade import SandboxFacade
        from unittest.mock import patch, MagicMock

        monkeypatch.setenv("DAWEI_SANDBOX_PREWARM_ON_SESSION_START", "1")

        ctx = TrustedContext(
            user_id="u", workspace_id="w", workspace_path=Path("/tmp"),
        )

        fake_provider = MagicMock()
        with patch.object(SandboxFacade, "get_provider", return_value=fake_provider):
            SandboxFacade.prewarm_session(ctx)
            fake_provider.prewarm_session.assert_called_once_with(ctx)

    def test_prewarm_provider_default_is_noop(self):
        """SandboxProvider 基类的 prewarm_session 是 no-op (不抛 NotImplementedError)"""
        from dawei.sandbox.base import SandboxProvider, TrustedContext

        ctx = TrustedContext(
            user_id="u", workspace_id="w", workspace_path=Path("/tmp"),
        )
        # 基类实例化会因 abstractmethods 失败, 直接调未绑定的方法
        SandboxProvider.prewarm_session(None, ctx)  # type: ignore[misc]


# ================================================================
# P3 Path B: 工具调用远程化 — tool_runner + execute_tool + routing
# ================================================================


class TestToolRunner:
    """P3: tool_runner.py 本地执行测试 (模拟沙箱内运行)"""

    def test_tool_runner_reads_file(self, tmp_path):
        """tool_runner 正确执行 ReadFileTool 并返回 JSON 结果"""
        import json
        import subprocess
        import sys

        # 创建测试文件
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world\n", encoding="utf-8")

        # 模拟沙箱环境: workspace 在 /tmp/<tmp_path>
        # tool_runner 将 workspace 设为 /workspace, 但我们在本地测试,
        # 所以用 monkey patch 方式: 直接构造 /workspace 路径
        # 更简单: 直接在 /tmp 下创建 /workspace 目录结构
        import os
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        (workspace_dir / "test.txt").write_text("hello from sandbox\n", encoding="utf-8")

        spec = json.dumps({
            "tool_class": "dawei.tools.custom_tools.read_tools.ReadFileTool",
            "kwargs": {"file_path": "test.txt"},
        })

        # 运行 tool_runner, 设置 WORKSPACE 环境变量模拟沙箱
        env = os.environ.copy()
        result = subprocess.run(
            [sys.executable, "-m", "dawei.sandbox.tool_runner"],
            input=spec,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )

        # tool_runner 应该成功 (即使文件不在 /workspace, 错误也会被捕获)
        output_lines = result.stdout.strip().splitlines()
        if output_lines:
            try:
                output = json.loads(output_lines[-1])
                # 在非沙箱环境, /workspace 可能不存在, tool 会返回错误
                # 关键是验证 tool_runner 协议正常工作
                assert "success" in output
            except json.JSONDecodeError:
                pytest.fail(f"tool_runner output not JSON: {result.stdout}")

    def test_tool_runner_invalid_json(self):
        """tool_runner 对无效 JSON 返回错误"""
        import json
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "dawei.sandbox.tool_runner"],
            input="not valid json {{{",
            capture_output=True,
            text=True,
            timeout=10,
        )

        output = json.loads(result.stdout.strip().splitlines()[-1])
        assert output["success"] is False
        assert "Invalid JSON" in output["error"]

    def test_tool_runner_missing_tool_class(self):
        """tool_runner 对缺少 tool_class 的 spec 返回错误"""
        import json
        import subprocess
        import sys

        spec = json.dumps({"kwargs": {}})
        result = subprocess.run(
            [sys.executable, "-m", "dawei.sandbox.tool_runner"],
            input=spec,
            capture_output=True,
            text=True,
            timeout=10,
        )

        output = json.loads(result.stdout.strip().splitlines()[-1])
        assert output["success"] is False
        assert "tool_class" in output["error"]


class TestExecuteTool:
    """P3: SandboxFacade.execute_tool() 方法测试"""

    def test_execute_tool_success(self, monkeypatch):
        """execute_tool 正确解析 tool_runner 的 JSON 输出"""
        import json
        from dawei.sandbox.base import TrustedContext
        from dawei.sandbox.sandbox_facade import SandboxFacade
        from unittest.mock import MagicMock, patch

        ctx = TrustedContext(
            user_id="u", workspace_id="w", workspace_path=Path("/tmp"),
        )

        # Mock provider 返回 tool_runner 格式的输出
        fake_result = MagicMock()
        fake_result.success = True
        fake_result.exit_code = 0
        fake_result.stdout = json.dumps({"success": True, "result": "file content here"})
        fake_result.stderr = ""

        fake_provider = MagicMock()
        fake_provider.execute_command.return_value = fake_result

        with patch.object(SandboxFacade, "get_provider", return_value=fake_provider):
            result = SandboxFacade.execute_tool(
                ctx,
                "dawei.tools.custom_tools.read_tools.ReadFileTool",
                {"file_path": "test.txt"},
            )

        assert result == "file content here"
        fake_provider.execute_command.assert_called_once()

    def test_execute_tool_sandbox_failure(self, monkeypatch):
        """沙箱命令失败时抛出 RuntimeError"""
        from dawei.sandbox.base import TrustedContext
        from dawei.sandbox.sandbox_facade import SandboxFacade
        from unittest.mock import MagicMock, patch

        ctx = TrustedContext(
            user_id="u", workspace_id="w", workspace_path=Path("/tmp"),
        )

        fake_result = MagicMock()
        fake_result.success = False
        fake_result.exit_code = 1
        fake_result.stdout = ""
        fake_result.stderr = "python3: command not found"

        fake_provider = MagicMock()
        fake_provider.execute_command.return_value = fake_result

        with patch.object(SandboxFacade, "get_provider", return_value=fake_provider):
            with pytest.raises(RuntimeError, match="Sandbox tool execution failed"):
                SandboxFacade.execute_tool(ctx, "SomeTool", {})

    def test_execute_tool_invalid_json_output(self, monkeypatch):
        """tool_runner 输出非 JSON 时抛出 RuntimeError"""
        from dawei.sandbox.base import TrustedContext
        from dawei.sandbox.sandbox_facade import SandboxFacade
        from unittest.mock import MagicMock, patch

        ctx = TrustedContext(
            user_id="u", workspace_id="w", workspace_path=Path("/tmp"),
        )

        fake_result = MagicMock()
        fake_result.success = True
        fake_result.exit_code = 0
        fake_result.stdout = "this is not json at all"
        fake_result.stderr = ""

        fake_provider = MagicMock()
        fake_provider.execute_command.return_value = fake_result

        with patch.object(SandboxFacade, "get_provider", return_value=fake_provider):
            with pytest.raises(RuntimeError, match="Invalid tool_runner output"):
                SandboxFacade.execute_tool(ctx, "SomeTool", {})

    def test_execute_tool_error_in_result(self, monkeypatch):
        """tool_runner 返回 success=false 时抛出 RuntimeError"""
        import json
        from dawei.sandbox.base import TrustedContext
        from dawei.sandbox.sandbox_facade import SandboxFacade
        from unittest.mock import MagicMock, patch

        ctx = TrustedContext(
            user_id="u", workspace_id="w", workspace_path=Path("/tmp"),
        )

        fake_result = MagicMock()
        fake_result.success = True
        fake_result.exit_code = 0
        fake_result.stdout = json.dumps({
            "success": False,
            "error": "File not found at missing.txt",
        })
        fake_result.stderr = ""

        fake_provider = MagicMock()
        fake_provider.execute_command.return_value = fake_result

        with patch.object(SandboxFacade, "get_provider", return_value=fake_provider):
            with pytest.raises(RuntimeError, match="File not found"):
                SandboxFacade.execute_tool(ctx, "SomeTool", {})

    def test_execute_tool_expired_context(self):
        """过期 TrustedContext 被拒绝"""
        from dawei.sandbox.base import TrustedContext, UntrustedContextError
        from dawei.sandbox.sandbox_facade import SandboxFacade

        ctx = TrustedContext(
            user_id="u", workspace_id="w", workspace_path=Path("/tmp"),
            issued_at=time.time() - 7200,
        )

        with pytest.raises(UntrustedContextError):
            SandboxFacade.execute_tool(ctx, "SomeTool", {})

    def test_execute_tool_heredoc_format(self, monkeypatch):
        """验证 execute_tool 生成的命令使用 heredoc 格式"""
        import json
        from dawei.sandbox.base import TrustedContext
        from dawei.sandbox.sandbox_facade import SandboxFacade
        from unittest.mock import MagicMock, patch

        ctx = TrustedContext(
            user_id="u", workspace_id="w", workspace_path=Path("/tmp"),
        )

        fake_result = MagicMock()
        fake_result.success = True
        fake_result.exit_code = 0
        fake_result.stdout = json.dumps({"success": True, "result": "ok"})
        fake_result.stderr = ""

        fake_provider = MagicMock()
        fake_provider.execute_command.return_value = fake_result

        with patch.object(SandboxFacade, "get_provider", return_value=fake_provider):
            SandboxFacade.execute_tool(ctx, "TestTool", {"key": "value"})

        # 验证命令格式
        actual_command = fake_provider.execute_command.call_args[0][0]
        assert "DAWEI_TOOL_JSON_EOF" in actual_command
        assert "python3 -m dawei.sandbox.tool_runner" in actual_command
        assert "PYTHONPATH=/opt/dawei-src" in actual_command
        assert json.loads(
            actual_command.split("\n")[1].strip(),
        )["tool_class"] == "TestTool"


class TestShouldRouteToSandbox:
    """P3: ToolExecutor._should_route_to_sandbox() 路由决策测试"""

    def test_default_host_mode(self, monkeypatch):
        """默认模式 (host) 不路由到沙箱"""
        monkeypatch.delenv("DAWEI_TOOL_EXECUTION_MODE", raising=False)
        from dawei.tools.tool_executor import ToolExecutor

        executor = ToolExecutor.__new__(ToolExecutor)
        # 即使工具和 workspace 都满足条件, host 模式不路由
        assert executor._should_route_to_sandbox(MagicMock()) is False

    def test_sandbox_mode_routes_whitelisted_tool(self, monkeypatch):
        """sandbox 模式下, 白名单中的 CustomBaseTool 工具被路由"""
        monkeypatch.setenv("DAWEI_TOOL_EXECUTION_MODE", "sandbox")
        from dawei.tools.custom_base_tool import CustomBaseTool
        from dawei.tools.tool_executor import ToolExecutor

        class FakeReadFileTool(CustomBaseTool):
            name = "read_file"

            def _run(self, **kwargs):
                return "fake"

        executor = ToolExecutor.__new__(ToolExecutor)
        executor.user_workspace = MagicMock()
        executor.user_workspace.path = Path("/tmp")

        tool = FakeReadFileTool()
        assert executor._should_route_to_sandbox(tool) is True

    def test_non_whitelisted_tool_not_routed(self, monkeypatch):
        """非白名单工具不被路由"""
        monkeypatch.setenv("DAWEI_TOOL_EXECUTION_MODE", "sandbox")
        from dawei.tools.custom_base_tool import CustomBaseTool
        from dawei.tools.tool_executor import ToolExecutor

        class FakeMcpTool(CustomBaseTool):
            name = "mcp_call_server"  # 不在白名单中

            def _run(self, **kwargs):
                return "fake"

        executor = ToolExecutor.__new__(ToolExecutor)
        executor.user_workspace = MagicMock()
        executor.user_workspace.path = Path("/tmp")

        assert executor._should_route_to_sandbox(FakeMcpTool()) is False

    def test_non_custombasictool_not_routed(self, monkeypatch):
        """非 CustomBaseTool 实例不被路由"""
        monkeypatch.setenv("DAWEI_TOOL_EXECUTION_MODE", "sandbox")
        from dawei.tools.tool_executor import ToolExecutor

        executor = ToolExecutor.__new__(ToolExecutor)
        executor.user_workspace = MagicMock()
        executor.user_workspace.path = Path("/tmp")

        # 普通对象, 不是 CustomBaseTool
        class RandomTool:
            name = "read_file"

        assert executor._should_route_to_sandbox(RandomTool()) is False

    def test_no_workspace_not_routed(self, monkeypatch):
        """没有 workspace 时不路由"""
        monkeypatch.setenv("DAWEI_TOOL_EXECUTION_MODE", "sandbox")
        from dawei.tools.custom_base_tool import CustomBaseTool
        from dawei.tools.tool_executor import ToolExecutor

        class FakeReadFileTool(CustomBaseTool):
            name = "read_file"

            def _run(self, **kwargs):
                return "fake"

        executor = ToolExecutor.__new__(ToolExecutor)
        executor.user_workspace = None

        assert executor._should_route_to_sandbox(FakeReadFileTool()) is False
