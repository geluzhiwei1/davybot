# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""WorkspaceStore rustfs 链路单测 (2026-09-22)

覆盖:
1. 本地 → Store 同步: .dawei 白名单 (files/agents/skills) + 敏感子树排除
2. Store → 沙箱 push / 沙箱 → Store pull 的 files/ namespace 一致性
   (回归: 旧 pull 裸写 rel, 回传文件对 push 不可见)
3. Store → 本地回写
4. CubeSandboxProvider: store 同步开启时不 emit 工作区 host-mount
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from dawei.sandbox.workspace_store import LocalBackend, WorkspaceStore

if TYPE_CHECKING:
    from pathlib import Path

# ================================================================
# Fake 沙箱 (e2b SDK 形状的最小实现)
# ================================================================


class _FakeFiles:
    def __init__(self, fs: dict[str, bytes]):
        self.fs = fs

    def write(self, path: str, data: bytes) -> None:
        rel = path[len("/workspace/") :] if path.startswith("/workspace/") else path
        self.fs[rel] = bytes(data)

    # 签名对齐 e2b 2.x Filesystem.read(path): 不接受 timeout 等额外 kwarg —
    # 一旦实现代码传了多余参数, 这里会 TypeError 而不是静默通过 (web02 实测教训)
    def read(self, path: str) -> bytes:
        rel = path[len("/workspace/") :] if path.startswith("/workspace/") else path
        return self.fs[rel]


@dataclass
class _FakeCommandResult:
    stdout: str = ""
    exit_code: int = 0


class FakeSandbox:
    """files.write/read + commands.run(find ...) 的内存沙箱"""

    def __init__(self):
        self.fs: dict[str, bytes] = {}
        self.commands = self
        self.files = _FakeFiles(self.fs)
        self._marker_touched = False

    def run(self, cmd: str, cwd: str = "", timeout: int = 30, **kwargs):
        if "find /workspace" in cmd:
            lines = [f"1.0 {len(v)} /workspace/{k}" for k, v in sorted(self.fs.items())]
            return _FakeCommandResult(stdout="\n".join(lines))
        if "touch /tmp/.ws-init" in cmd:
            self._marker_touched = True
            return _FakeCommandResult()
        return _FakeCommandResult()


# ================================================================
# fixtures
# ================================================================


@pytest.fixture
def store(tmp_path: Path) -> WorkspaceStore:
    return WorkspaceStore(backend=LocalBackend(root=tmp_path / "store"))


@pytest.fixture
def local_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "sub").mkdir(parents=True)
    (ws / ".dawei" / "files").mkdir(parents=True)
    (ws / ".dawei" / "agents").mkdir(parents=True)
    (ws / ".dawei" / "chat-history").mkdir(parents=True)
    (ws / ".git").mkdir(parents=True)
    (ws / "a.txt").write_bytes(b"hello")
    (ws / "sub" / "b.txt").write_bytes(b"world")
    (ws / ".dawei" / "files" / "up.docx").write_bytes(b"docx-bytes")
    (ws / ".dawei" / "agents" / "agent.yaml").write_bytes(b"name: x")
    (ws / ".dawei" / "settings.json").write_bytes(b'{"apiKeys": "SECRET"}')
    (ws / ".dawei" / "chat-history" / "s.json").write_bytes(b'{"chat": "SECRET"}')
    (ws / ".git" / "junk").write_bytes(b"junk")
    return ws


# ================================================================
# 1. 本地 → Store
# ================================================================


def test_sync_local_to_store_whitelist(store: WorkspaceStore, local_ws: Path):
    stats = store.sync_local_to_store("ws1", local_ws)

    # 白名单内 4 个文件全部上传
    assert stats.uploaded == 4
    assert stats.errors == 0
    rels = {fm.rel for fm in store.list_files("ws1")}
    assert rels == {
        "files/a.txt",
        "files/sub/b.txt",
        "files/.dawei/files/up.docx",
        "files/.dawei/agents/agent.yaml",
    }
    # 敏感/忽略内容绝不能进 Store
    raw_keys = {fm.rel for fm in store.backend.list("ws-ws1/")}
    assert not any("settings.json" in k for k in raw_keys)
    assert not any("chat-history" in k for k in raw_keys)
    assert not any(".git" in k for k in raw_keys)


def test_sync_local_to_store_incremental(store: WorkspaceStore, local_ws: Path):
    store.sync_local_to_store("ws1", local_ws)
    stats2 = store.sync_local_to_store("ws1", local_ws)
    # 未变化 → 不重复上传 (skipped = 4 未变 + 3 敏感/忽略排除)
    assert stats2.uploaded == 0
    assert stats2.skipped == 7

    (local_ws / "a.txt").write_bytes(b"changed")
    stats3 = store.sync_local_to_store("ws1", local_ws)
    assert stats3.uploaded == 1


# ================================================================
# 2. namespace 一致性 (push / pull)
# ================================================================


def test_push_then_pull_roundtrip(store: WorkspaceStore, local_ws: Path):
    store.sync_local_to_store("ws1", local_ws)

    sb = FakeSandbox()
    push_stats = store.push_to_sandbox(sb, "ws1")
    assert push_stats.uploaded == 4
    # push 剥掉 files/ namespace: 沙箱内布局与 virtiofs 一致
    assert sb.fs == {
        "a.txt": b"hello",
        "sub/b.txt": b"world",
        ".dawei/files/up.docx": b"docx-bytes",
        ".dawei/agents/agent.yaml": b"name: x",
    }

    # 沙箱内生成新文件 → pull 回 Store 必须落在 files/ namespace
    sb.fs["gen.txt"] = b"generated"
    pull_stats = store.pull_from_sandbox(sb, "ws1")
    assert pull_stats.downloaded == 5  # find 返回全部 (真实场景 marker 过滤)
    rels = {fm.rel for fm in store.list_files("ws1")}
    assert "files/gen.txt" in rels


def test_pull_output_visible_to_next_push(store: WorkspaceStore):
    """回归: 旧实现 pull 裸写 rel (无 files/ 前缀), 回传文件对 push 不可见"""
    sb = FakeSandbox()
    sb.fs["only-in-sandbox.txt"] = b"data"
    store.pull_from_sandbox(sb, "ws1")

    sb2 = FakeSandbox()
    push_stats = store.push_to_sandbox(sb2, "ws1")
    assert push_stats.uploaded == 1
    assert sb2.fs["only-in-sandbox.txt"] == b"data"


# ================================================================
# 3. Store → 本地
# ================================================================


def test_sync_store_to_local(store: WorkspaceStore, local_ws: Path, tmp_path: Path):
    store.sync_local_to_store("ws1", local_ws)
    sb = FakeSandbox()
    store.push_to_sandbox(sb, "ws1")
    sb.fs["gen.txt"] = b"generated"
    store.pull_from_sandbox(sb, "ws1")

    local2 = tmp_path / "ws-mirror"
    stats = store.sync_store_to_local("ws1", local2)
    assert stats.downloaded == 5
    assert (local2 / "a.txt").read_bytes() == b"hello"
    assert (local2 / "gen.txt").read_bytes() == b"generated"
    assert (local2 / ".dawei" / "files" / "up.docx").read_bytes() == b"docx-bytes"


def test_sync_store_to_local_never_writes_sensitive(store: WorkspaceStore, tmp_path: Path):
    """Store 里即使被塞入敏感 key (防御), 也不得落盘到 .dawei 敏感子树"""
    store.put_file("ws1", "files/.dawei/settings.json", b"evil")
    store.put_file("ws1", "files/.dawei/chat-history/x.json", b"evil")

    local2 = tmp_path / "ws-mirror2"
    store.sync_store_to_local("ws1", local2)
    assert not (local2 / ".dawei" / "settings.json").exists()
    assert not (local2 / ".dawei" / "chat-history").exists()


def test_encrypt_covers_namespaced_dawei(store: WorkspaceStore):
    assert store._should_encrypt(".dawei/settings.json")
    assert store._should_encrypt("files/.dawei/files/up.docx")
    assert not store._should_encrypt("files/a.txt")


# ================================================================
# 3.5 S3Backend SSE opt-in (回归: 无条件 SSE-S3 被 rustfs 拒绝, web02 实测)
# ================================================================


@pytest.fixture
def fake_boto3(monkeypatch):
    """注入 stub boto3/botocore — S3Backend 构造不再依赖真实 boto3"""
    from unittest.mock import MagicMock

    fake_client = MagicMock()
    fake_client.head_bucket.side_effect = Exception("no net")  # _ensure_bucket 走 catch 分支
    boto3_mod = MagicMock()
    boto3_mod.client.return_value = fake_client
    botocore_mod = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", boto3_mod)
    monkeypatch.setitem(sys.modules, "botocore", MagicMock())
    monkeypatch.setitem(sys.modules, "botocore.client", botocore_mod)
    return fake_client


def _make_s3_backend(sse: str = "") -> S3Backend:
    from dawei.sandbox.workspace_store import S3Backend

    return S3Backend(endpoint="http://x", bucket="b", access_key="a", secret_key="s", sse=sse)


def test_s3_put_sse_off_by_default(fake_boto3):
    backend = _make_s3_backend()
    backend.put("k", b"data")
    kwargs = fake_boto3.put_object.call_args.kwargs
    assert "ServerSideEncryption" not in kwargs


def test_s3_put_sse_opt_in(fake_boto3):
    backend = _make_s3_backend(sse="AES256")
    backend.put("k", b"data")
    kwargs = fake_boto3.put_object.call_args.kwargs
    assert kwargs.get("ServerSideEncryption") == "AES256"


# ================================================================
# 4. Provider 挂载配置
# ================================================================


@pytest.fixture
def provider_env(tmp_path: Path, monkeypatch):
    """隔离全局单例与本地根目录, 防止污染真实 ~/.normnomos"""
    monkeypatch.setenv("WORKSPACE_STORE_BACKEND", "local")
    monkeypatch.setenv("WORKSPACE_STORE_LOCAL_ROOT", str(tmp_path / "ws-store"))
    from dawei.sandbox import workspace_store

    workspace_store.reset_workspace_store()
    yield
    workspace_store.reset_workspace_store()


def _make_provider():
    from dawei.sandbox.cubesandbox_provider import CubeSandboxProvider

    return CubeSandboxProvider(config={})


def test_provider_default_uses_host_mount(provider_env, local_ws: Path):
    provider = _make_provider()
    assert provider._use_store_sync is False

    cfg = provider._build_mount_config(local_ws, "rw")
    mounts = json.loads(cfg["metadata"]["host-mount"])
    ws_mounts = [m for m in mounts if m["mountPath"] == "/workspace"]
    assert len(ws_mounts) == 1
    assert ws_mounts[0]["hostPath"] == str(local_ws.resolve())


def test_provider_store_sync_omits_workspace_host_mount(provider_env, store: WorkspaceStore, local_ws: Path):
    provider = _make_provider()
    provider._workspace_store = store
    provider._use_store_sync = True

    cfg = provider._build_mount_config(local_ws, "rw")
    mounts = json.loads(cfg["metadata"]["host-mount"])
    # 工作区 host-mount 必须消失 (dawei-src 只读挂载允许保留)
    assert all(m["mountPath"] != "/workspace" for m in mounts)


def test_provider_sync_sandbox_back_writes_local(provider_env, store: WorkspaceStore, local_ws: Path):
    from dawei.sandbox.cubesandbox_provider import SandboxSession

    store.sync_local_to_store("ws1", local_ws)
    sb = FakeSandbox()
    store.push_to_sandbox(sb, "ws1")
    sb.fs["gen.txt"] = b"generated"

    provider = _make_provider()
    provider._workspace_store = store
    provider._use_store_sync = True

    session = SandboxSession(
        sandbox=sb,
        user_id="u1",
        workspace_id="wid",
        mount_mode="rw",
        workspace_key="ws1",
        workspace_path=str(local_ws),
    )
    provider._sync_sandbox_back(session)

    assert (local_ws / "gen.txt").read_bytes() == b"generated"
