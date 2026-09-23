# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""WorkspaceStore — 统一工作区存储 (S3/RustFS)

设计原则 (SaaS 沙箱方案 §4):
1. 后端可选: rustfs | minio | s3 | local(本地 fallback)
2. AES-GCM 客户端加密 .dawei/ 敏感子树 (可选)
3. SDK 模式下与 Sandbox VM 做双向增量同步
4. fail-fast: 显式配置 rustfs/minio/s3 但 boto3 缺失时抛异常,
   不再静默降级 local (静默降级会让生产"看起来正常实际没上 S3")

环境变量:
  WORKSPACE_STORE_BACKEND       rustfs | minio | s3 | local (默认 local)
  WORKSPACE_STORE_ENDPOINT       S3 endpoint URL
  WORKSPACE_STORE_BUCKET         bucket 名 (默认 nn-bot-workspaces)
  WORKSPACE_STORE_ACCESS_KEY     S3 access key
  WORKSPACE_STORE_SECRET_KEY     S3 secret key
  WORKSPACE_STORE_ENCRYPTION_KEY 32字节 hex (AES-256 key for .dawei/)
  WORKSPACE_STORE_LOCAL_ROOT     local 后端根目录 (默认 $DAWEI_HOME/workspace-store)
  WORKSPACE_STORE_SSE            aes256 = 开启服务端 SSE (默认关 — 未配 KMS 的
                                 rustfs/minio 会拒绝 SSE-S3 请求, web02 实测)
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ================================================================
# 数据结构
# ================================================================


@dataclass
class FileMeta:
    """文件元数据 (用于增量同步)"""

    rel: str  # 相对 workspace 根的路径 (e.g. "src/main.py")
    size: int = 0
    etag: str = ""  # S3 ETag 或本地 md5
    mtime: float = 0.0

    @classmethod
    def from_s3(cls, obj: dict[str, Any]) -> FileMeta:
        rel = obj["Key"].split("/", 1)[1] if "/" in obj["Key"] else ""
        return cls(
            rel=rel,
            size=int(obj.get("Size", 0)),
            etag=obj.get("ETag", "").strip('"'),
            mtime=obj.get("LastModified", type("X", (), {"timestamp": lambda _: 0.0})()).timestamp() if hasattr(obj.get("LastModified"), "timestamp") else 0.0,
        )

    @classmethod
    def from_local(cls, rel: str, p: Path) -> FileMeta:
        st = p.stat()
        return cls(
            rel=rel,
            size=st.st_size,
            etag=hashlib.md5(p.read_bytes() if st.st_size < 8 * 1024 * 1024 else b"").hexdigest(),
            mtime=st.st_mtime,
        )


@dataclass
class SyncStats:
    """同步统计"""

    uploaded: int = 0
    downloaded: int = 0
    skipped: int = 0
    errors: int = 0
    bytes_transferred: int = 0
    duration_ms: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "uploaded": self.uploaded,
            "downloaded": self.downloaded,
            "skipped": self.skipped,
            "errors": self.errors,
            "bytes_transferred": self.bytes_transferred,
            "duration_ms": self.duration_ms,
        }


# ================================================================
# StorageBackend 抽象
# ================================================================


class StorageBackend(ABC):
    """存储后端抽象"""

    @abstractmethod
    def put(self, key: str, data: bytes) -> str:
        """存储对象, 返回 ETag"""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """读取对象"""

    @abstractmethod
    def list(self, prefix: str) -> list[FileMeta]:
        """列举前缀下的所有对象 (懒, 仅返回元数据)"""

    @abstractmethod
    def delete(self, key: str) -> None:
        """删除对象"""

    @abstractmethod
    def health(self) -> bool:
        """健康检查"""


# ================================================================
# LocalBackend — 本地文件系统 fallback (开发/测试用)
# ================================================================


class LocalBackend(StorageBackend):
    """本地文件系统后端 — 仅供 dev/test, 非生产"""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # 阻止路径逃逸
        p = (self.root / key).resolve()
        p.relative_to(self.root)
        return p

    def put(self, key: str, data: bytes) -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return hashlib.md5(data).hexdigest()

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def list(self, prefix: str) -> list[FileMeta]:
        base = self.root / prefix.rstrip("/")
        if not base.exists():
            return []
        results = []
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            # 与 S3Backend.list 对齐: 剥掉 key 首段 (ws-<id>/),
            # rel 统一含 FILES_NS 前缀 (e.g. "files/foo.docx")
            rel = str(p.relative_to(self.root))
            if "/" in rel:
                rel = rel.split("/", 1)[1]
            else:
                rel = ""
            results.append(FileMeta.from_local(rel, p))
        return results

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            pass

    def health(self) -> bool:
        return self.root.exists() and os.access(self.root, os.W_OK)


# ================================================================
# S3Backend — boto3 实现的 S3/RustFS/MinIO 后端
# ================================================================


class S3Backend(StorageBackend):
    """S3-compatible 后端 (rustfs / minio / aws s3)

    boto3 是可选依赖, 导入失败时构造抛出 ImportError。
    【2026-09-13 fail-fast】WorkspaceStore.create 不再捕获该 ImportError
    降级到 LocalBackend —— 显式配置 S3 后端时缺依赖必须炸出来。

    SSE (2026-09-22): 服务端加密改为 opt-in (sse="aes256")。
    无条件发 ServerSideEncryption=AES256 会被未配 KMS/
    RUSTFS_SSE_S3_MASTER_KEY 的 rustfs/minio 直接拒掉 (InvalidRequest,
    web02 实测)。敏感数据保护走客户端 AESCipher (WORKSPACE_STORE_ENCRYPTION_KEY),
    不依赖服务端 SSE。
    """

    def __init__(
        self,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        sse: str = "",
    ):
        try:
            import boto3
            from botocore.client import Config
        except ImportError as e:
            raise ImportError(
                "S3Backend 需要 boto3, 安装: uv pip install boto3",
            ) from e

        self.bucket = bucket
        self.sse = sse.strip().lower()
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(retries={"max_attempts": 3, "mode": "standard"}),
        )
        # 确保 bucket 存在
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            try:
                self.client.create_bucket(Bucket=self.bucket)
                logger.info("[WorkspaceStore] 创建 bucket: %s", self.bucket)
            except Exception as e:
                logger.warning("[WorkspaceStore] bucket 创建失败 (可能已存在): %s", e)

    def put(self, key: str, data: bytes) -> str:
        kwargs: dict[str, Any] = {}
        if self.sse == "aes256":
            kwargs["ServerSideEncryption"] = "AES256"
        resp = self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            **kwargs,
        )
        return resp.get("ETag", "").strip('"')

    def get(self, key: str) -> bytes:
        resp = self.client.get_object(Bucket=self.bucket, Key=key)
        return resp["Body"].read()

    def list(self, prefix: str) -> list[FileMeta]:
        results: list[FileMeta] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                rel = obj["Key"]
                if "/" in rel:
                    rel = rel.split("/", 1)[1]
                else:
                    rel = ""
                results.append(
                    FileMeta(
                        rel=rel,
                        size=int(obj.get("Size", 0)),
                        etag=obj.get("ETag", "").strip('"'),
                        mtime=obj.get("LastModified").timestamp() if obj.get("LastModified") else 0.0,
                    ),
                )
        return results

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as e:
            logger.warning("[WorkspaceStore] delete %s 失败: %s", key, e)

    def health(self) -> bool:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True
        except Exception:
            return False


# ================================================================
# 加密工具 (.dawei/ 客户端加密)
# ================================================================


class AESCipher:
    """AES-GCM 客户端加密 (用于 .dawei/ 敏感子树)

    cryptography 是可选依赖, 缺包时所有加密降级为 no-op,
    但仍依赖 S3 服务端 SSE (ServerSideEncryption=AES256)。
    """

    def __init__(self, key: bytes | None = None):
        self.key = key
        self._fernet = None
        if key:
            self._init_cipher(key)

    def _init_cipher(self, key: bytes) -> None:
        try:
            import base64

            from cryptography.fernet import Fernet

            # key 必须是 32 字节 url-safe-base64; 接受 hex / 任意 32 字节
            if len(key) == 32:
                fernet_key = base64.urlsafe_b64encode(key)
            elif len(key) == 44:  # 已是 base64
                fernet_key = key
            else:
                # 取 sha256 派生 32 字节
                fernet_key = base64.urlsafe_b64encode(hashlib.sha256(key).digest())
            self._fernet = Fernet(fernet_key)
        except ImportError:
            logger.warning(
                "[WorkspaceStore] cryptography 未安装, 客户端加密不可用, 依赖 S3 服务端 SSE",
            )
            self._fernet = None

    def encrypt(self, data: bytes) -> bytes:
        if self._fernet is None:
            return data
        return self._fernet.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        if self._fernet is None:
            return data
        return self._fernet.decrypt(data)


# ================================================================
# WorkspaceStore — 主入口
# ================================================================


class WorkspaceStore:
    """统一工作区存储 — 工作区 = S3/RustFS 上的 prefix

    路径布局:
        {bucket}/ws-{workspace_id}/files/...
        {bucket}/ws-{workspace_id}/.dawei/...    (加密)
        {bucket}/ws-{workspace_id}/manifest.json  (元数据缓存)

    用法:
        store = WorkspaceStore.create()  # 自动从环境变量选择后端
        store.push_to_sandbox(sandbox, "ws-abc123", mode="rw")
        store.pull_from_sandbox(sandbox, "ws-abc123")
    """

    # 需要加密的子树 (按路径段匹配, 兼容 "files/.dawei/x" 带 namespace 前缀的 key)
    ENCRYPT_PREFIXES = (".dawei/",)
    # 单文件大小限制 (避免 SDK 10MB 限制)
    MAX_INLINE_FILE_SIZE = 10 * 1024 * 1024
    # Store 内工作区内容的 namespace 前缀:
    #   store key = ws-<id>/files/<workspace-rel>  ↔  沙箱 /workspace/<workspace-rel>
    # pull/push/本地同步三端必须共用同一约定, 否则回传文件对 push 不可见。
    FILES_NS = "files/"
    # .dawei/ 下允许进出 Store 的子目录 (与 CubeSandboxProvider F2 PASSTHROUGH 对齐);
    # 其余 .dawei/ 子树为服务端状态 (会话/凭据/任务图), 不得进 Store。
    DAWEI_SYNC_WHITELIST = frozenset({"files", "agents", "skills"})
    # 同步时跳过的路径
    DEFAULT_IGNORE = frozenset(
        {
            ".git",
            "__pycache__",
            "node_modules",
            ".venv",
            ".cache",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
        },
    )

    def __init__(
        self,
        backend: StorageBackend,
        workspace_prefix: str = "ws-",
        cipher: AESCipher | None = None,
    ):
        self.backend = backend
        self.prefix = workspace_prefix
        self.cipher = cipher or AESCipher()

    @classmethod
    def create(
        cls,
        backend: str | None = None,
        encryption_key: bytes | None = None,
    ) -> WorkspaceStore:
        """从环境变量构造 WorkspaceStore

        后端选择:
          rustfs / minio / s3 → S3Backend
          local → LocalBackend
          未配置 → LocalBackend (默认)

        fail-fast (2026-09-13):
          - 显式配置 rustfs/minio/s3 但 boto3 缺失 → 抛 RuntimeError
            (静默降级 local 会让生产"看起来正常实际没上 S3")
          - 未知 backend 值 → 抛 ValueError (配置拼写错误必须炸出来)
        """
        backend = (backend or os.environ.get("WORKSPACE_STORE_BACKEND", "local")).lower()
        if backend in ("rustfs", "minio", "s3"):
            try:
                s3 = S3Backend(
                    endpoint=os.environ.get("WORKSPACE_STORE_ENDPOINT", ""),
                    bucket=os.environ.get(
                        "WORKSPACE_STORE_BUCKET",
                        "nn-bot-workspaces",
                    ),
                    access_key=os.environ.get("WORKSPACE_STORE_ACCESS_KEY", ""),
                    secret_key=os.environ.get("WORKSPACE_STORE_SECRET_KEY", ""),
                    region=os.environ.get("WORKSPACE_STORE_REGION", "us-east-1"),
                    sse=os.environ.get("WORKSPACE_STORE_SSE", ""),
                )
                logger.info("[WorkspaceStore] S3 后端已就绪: %s", backend)
                actual = s3
            except ImportError as e:
                raise RuntimeError(
                    f"WORKSPACE_STORE_BACKEND={backend} 但 boto3 不可用: {e}. 安装: uv pip install 'davybot[workspace-store]' 或 uv pip install boto3. 如确实要用本地存储, 显式设 WORKSPACE_STORE_BACKEND=local",
                ) from e
        elif backend == "local":
            actual = cls._local_backend()
        else:
            raise ValueError(
                f"未知 WORKSPACE_STORE_BACKEND={backend!r}, 合法值: rustfs | minio | s3 | local",
            )

        # 加密
        if encryption_key is None:
            hex_key = os.environ.get("WORKSPACE_STORE_ENCRYPTION_KEY", "")
            if hex_key:
                try:
                    encryption_key = bytes.fromhex(hex_key)
                except ValueError:
                    logger.warning(
                        "[WorkspaceStore] WORKSPACE_STORE_ENCRYPTION_KEY 不是 hex, 忽略",
                    )
        cipher = AESCipher(encryption_key)

        return cls(backend=actual, cipher=cipher)

    @staticmethod
    def _local_backend() -> LocalBackend:
        dawei_home = os.environ.get("DAWEI_HOME", str(Path.home() / ".normnomos"))
        root = Path(os.environ.get("WORKSPACE_STORE_LOCAL_ROOT", dawei_home + "/workspace-store"))
        return LocalBackend(root=root)

    # ================================================================
    # Key 构造
    # ================================================================

    def _ws_key(self, workspace_id: str, *parts: str) -> str:
        """workspace 内对象的完整 key"""
        key = f"{self.prefix}{workspace_id}"
        if parts:
            key += "/" + "/".join(parts)
        return key

    def _should_encrypt(self, rel: str) -> bool:
        # 按路径段匹配: ".dawei/x" 与 "files/.dawei/x" (带 namespace 前缀) 都命中
        return ".dawei" in rel.split("/")

    def _should_ignore(self, rel: str, ignore: frozenset[str] | None = None) -> bool:
        ignore = ignore or self.DEFAULT_IGNORE
        parts = rel.split("/")
        return any(p in ignore for p in parts)

    # ================================================================
    # 基本 CRUD
    # ================================================================

    def put_file(
        self,
        workspace_id: str,
        rel: str,
        data: bytes,
    ) -> str:
        """写入一个文件"""
        key = self._ws_key(workspace_id, rel)
        if self._should_encrypt(rel):
            data = self.cipher.encrypt(data)
        return self.backend.put(key, data)

    def get_file(self, workspace_id: str, rel: str) -> bytes:
        """读取一个文件"""
        key = self._ws_key(workspace_id, rel)
        data = self.backend.get(key)
        if self._should_encrypt(rel):
            data = self.cipher.decrypt(data)
        return data

    def list_files(
        self,
        workspace_id: str,
        subdir: str = "files/",
    ) -> list[FileMeta]:
        """列出 workspace 文件"""
        return self.backend.list(self._ws_key(workspace_id, subdir))

    def delete_file(self, workspace_id: str, rel: str) -> None:
        self.backend.delete(self._ws_key(workspace_id, rel))

    def health(self) -> bool:
        return self.backend.health()

    # ================================================================
    # 增量同步: WorkspaceStore ↔ Sandbox VM
    # ================================================================

    def push_to_sandbox(
        self,
        sandbox: Any,
        workspace_id: str,
        ignore: frozenset[str] | None = None,
    ) -> SyncStats:
        """S3 → VM (sandbox.files.write)

        增量策略: 用 ETag 对比,只传变化文件 (TODO: 实现)
        当前 v1: 全量推送(简单可靠)
        """
        stats = SyncStats()
        start = time.time()
        files = self.list_files(workspace_id)

        for fm in files:
            rel = fm.rel
            if not rel or rel.endswith("manifest.json"):
                stats.skipped += 1
                continue
            if self._should_ignore(rel, ignore):
                stats.skipped += 1
                continue
            if fm.size > self.MAX_INLINE_FILE_SIZE:
                # 大文件暂不分块, 跳过(后续 phase 补)
                logger.warning(
                    "[WorkspaceStore] 跳过超大文件 %s (%d bytes, 限制 %d)",
                    rel,
                    fm.size,
                    self.MAX_INLINE_FILE_SIZE,
                )
                stats.skipped += 1
                continue
            try:
                data = self.get_file(workspace_id, rel)
                # store "files/" namespace 剥离后映射到沙箱工作区根,
                # 与 virtiofs 布局一致 (agent 在沙箱内看到 /workspace/<rel>)
                ws_rel = rel[len(self.FILES_NS) :] if rel.startswith(self.FILES_NS) else rel
                sandbox.files.write(f"/workspace/{ws_rel}", data)
                stats.uploaded += 1
                stats.bytes_transferred += len(data)
            except Exception as e:
                logger.warning("[WorkspaceStore] push %s 失败: %s", rel, e)
                stats.errors += 1

        stats.duration_ms = int((time.time() - start) * 1000)
        logger.info(
            "[WorkspaceStore] push_to_sandbox: %s",
            stats.as_dict(),
        )
        return stats

    def pull_from_sandbox(
        self,
        sandbox: Any,
        workspace_id: str,
    ) -> SyncStats:
        """VM → S3 (拉回 Agent 修改的文件)

        策略: 用 VM 内 `find -newer /tmp/.ws-init` 找出本次会话写入的文件
        """
        stats = SyncStats()
        start = time.time()

        try:
            # 找出本次会话变更的文件 (相对 /tmp/.ws-init, 沙箱启动时 touch)
            list_cmd = "find /workspace -type f -not -path '*/.dawei/*' -not -path '*/.git/*' -newer /tmp/.ws-init -printf '%T@ %s %p\\n' 2>/dev/null"
            result = sandbox.commands.run(list_cmd, cwd="/workspace", timeout=30)
        except Exception as e:
            logger.warning("[WorkspaceStore] pull 列举失败: %s", e)
            stats.errors += 1
            stats.duration_ms = int((time.time() - start) * 1000)
            return stats

        for line in (result.stdout if hasattr(result, "stdout") else "").splitlines():
            parts = line.split(" ", 2)
            if len(parts) != 3:
                continue
            _mtime, _size, path = parts
            if path.startswith("/workspace/"):
                rel = path[len("/workspace/") :]
            else:
                continue

            try:
                # e2b 2.x Filesystem.read(path) 不接受 timeout kwarg (web02 实测
                # 2.49.1: TypeError: unexpected keyword argument 'timeout')
                data = sandbox.files.read(path)
                # 写入统一 files/ namespace —— pull 的产物必须对
                # push_to_sandbox / sync_store_to_local 可见 (2026-09-22 修复:
                # 旧实现裸写 rel, 回传文件落在 namespace 外, 下次 push 不可见)
                self.put_file(workspace_id, f"{self.FILES_NS}{rel}", data)
                stats.downloaded += 1
                stats.bytes_transferred += len(data)
            except Exception as e:
                logger.warning("[WorkspaceStore] pull %s 失败: %s", rel, e)
                stats.errors += 1

        stats.duration_ms = int((time.time() - start) * 1000)
        logger.info(
            "[WorkspaceStore] pull_from_sandbox: %s",
            stats.as_dict(),
        )
        return stats

    # ================================================================
    # 本地 ↔ Store 同步 (CubeSandboxProvider rustfs 链路, 2026-09-22)
    # ================================================================

    def _dawei_sync_allowed(self, ws_rel: str) -> bool:
        """.dawei/ 子树白名单: 仅 files/agents/skills 可进出 Store。

        其余 .dawei/ 内容 (chat-history/configs/task_graphs/凭据等) 是
        服务端状态, 进 Store 即跨信任边界泄露 —— fail-closed 拒绝。
        """
        parts = ws_rel.split("/")
        if parts[0] != ".dawei":
            return True
        return len(parts) >= 2 and parts[1] in self.DAWEI_SYNC_WHITELIST

    def sync_local_to_store(
        self,
        workspace_id: str,
        local_root: Path | str,
        ignore: frozenset[str] | None = None,
    ) -> SyncStats:
        """本地工作区目录 → Store (etags 增量, 未变化跳过)

        上传范围: 工作区根文件 + .dawei/{files,agents,skills};
        与 F2 PASSTHROUGH 对齐, 敏感子树 fail-closed 排除。
        """
        stats = SyncStats()
        start = time.time()
        root = Path(local_root)
        if not root.is_dir():
            stats.duration_ms = int((time.time() - start) * 1000)
            return stats

        remote = {fm.rel: fm for fm in self.list_files(workspace_id)}

        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.is_symlink():
                continue
            ws_rel = p.relative_to(root).as_posix()
            if self._should_ignore(ws_rel, ignore) or not self._dawei_sync_allowed(ws_rel):
                stats.skipped += 1
                continue
            size = p.stat().st_size
            if size > self.MAX_INLINE_FILE_SIZE:
                logger.warning(
                    "[WorkspaceStore] 跳过超大文件 %s (%d bytes, 限制 %d)",
                    ws_rel,
                    size,
                    self.MAX_INLINE_FILE_SIZE,
                )
                stats.skipped += 1
                continue
            key_rel = f"{self.FILES_NS}{ws_rel}"
            fm = remote.get(key_rel)
            local_etag = hashlib.md5(p.read_bytes()).hexdigest() if size < 8 * 1024 * 1024 else ""
            if fm and fm.size == size and local_etag and fm.etag == local_etag:
                stats.skipped += 1
                continue
            try:
                self.put_file(workspace_id, key_rel, p.read_bytes())
                stats.uploaded += 1
                stats.bytes_transferred += size
            except Exception as e:
                logger.warning("[WorkspaceStore] local→store %s 失败: %s", ws_rel, e)
                stats.errors += 1

        stats.duration_ms = int((time.time() - start) * 1000)
        logger.info("[WorkspaceStore] sync_local_to_store: %s", stats.as_dict())
        return stats

    def sync_store_to_local(
        self,
        workspace_id: str,
        local_root: Path | str,
        ignore: frozenset[str] | None = None,
    ) -> SyncStats:
        """Store → 本地工作区目录 (沙箱产物回写, 供 web 文件管理器/上传方读取)

        同样受 .dawei 白名单约束: Store 里即使出现敏感子树 key 也不落盘。
        """
        stats = SyncStats()
        start = time.time()
        root = Path(local_root)
        root.mkdir(parents=True, exist_ok=True)

        for fm in self.list_files(workspace_id):
            rel = fm.rel
            if not rel.startswith(self.FILES_NS):
                stats.skipped += 1
                continue
            ws_rel = rel[len(self.FILES_NS) :]
            if self._should_ignore(ws_rel, ignore) or not self._dawei_sync_allowed(ws_rel):
                stats.skipped += 1
                continue
            if fm.size > self.MAX_INLINE_FILE_SIZE:
                logger.warning(
                    "[WorkspaceStore] 跳过超大对象 %s (%d bytes)",
                    ws_rel,
                    fm.size,
                )
                stats.skipped += 1
                continue
            try:
                data = self.get_file(workspace_id, rel)
                dest = root / ws_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                stats.downloaded += 1
                stats.bytes_transferred += len(data)
            except Exception as e:
                logger.warning("[WorkspaceStore] store→local %s 失败: %s", ws_rel, e)
                stats.errors += 1

        stats.duration_ms = int((time.time() - start) * 1000)
        logger.info("[WorkspaceStore] sync_store_to_local: %s", stats.as_dict())
        return stats

    # ================================================================
    # 辅助: 沙箱内初始化 (touch marker)
    # ================================================================

    @staticmethod
    def init_marker(sandbox: Any) -> None:
        """在沙箱内创建变更基准点 (用于 pull 增量)"""
        try:
            sandbox.commands.run(
                "touch /tmp/.ws-init && mkdir -p /workspace",
                timeout=5,
            )
        except Exception as e:
            logger.warning("[WorkspaceStore] init_marker 失败: %s", e)


# ================================================================
# 模块级单例 (懒加载)
# ================================================================

_default_store: WorkspaceStore | None = None


def get_workspace_store() -> WorkspaceStore:
    """获取全局默认 WorkspaceStore (单例)"""
    global _default_store
    if _default_store is None:
        _default_store = WorkspaceStore.create()
        logger.info(
            "[WorkspaceStore] 全局单例已创建: backend=%s",
            type(_default_store.backend).__name__,
        )
    return _default_store


def reset_workspace_store() -> None:
    """重置全局单例 (测试用)"""
    global _default_store
    _default_store = None
