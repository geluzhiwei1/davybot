# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""WorkspaceShareManager — 工作区分享索引 (类百度网盘, project/docs/工作区分享功能方案.md)

职责 (纯存储层, 不碰 HTTP):
1. $DAWEI_HOME/workspace_shares.json 的读写 (tmp+rename 原子写)
2. 提取码: PBKDF2 哈希 (verify 比对) + AES-GCM 可逆加密 (owner 回显)
3. share-token 签发/校验 (独立 scope="workspace-share", 与用户 JWT 双向隔离)
4. 有效期: 仅 1/3/7 天三档 (SHARE_EXPIRY_DAYS 枚举), expires_at 惰性判定

风格照抄 deep_research_framework.py 的「全局索引 JSON + 原子写」先例。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 有效期仅三档 (R6: 服务端枚举, 其余 422 FAST FAIL)
SHARE_EXPIRY_DAYS = (1, 3, 7)

# 提取码自动生成字符集 (去混淆: 无 0/o/1/l/i)
PASSWORD_CHARSET = "23456789abcdefghjkmnpqrstuvwxyz"
AUTO_PASSWORD_LENGTH = 4
PASSWORD_MIN_LENGTH = 4
PASSWORD_MAX_LENGTH = 32

# PBKDF2 参数
PBKDF2_ITERATIONS = 100_000
PBKDF2_ALGO = "sha256"

# share-token 的独立 scope — 与用户 JWT 双向不可冒充
SHARE_TOKEN_SCOPE = "workspace-share"

# clone_log FIFO 上限 (clone_count 为全量计数)
CLONE_LOG_MAX = 100


class ShareError(Exception):
    """分享操作失败基类 (HTTP 层转 4xx)"""


class ShareNotFoundError(ShareError):
    """工作区尚无分享记录"""


class ShareRevokedError(ShareError):
    """分享已永久撤销, 只能重新生成"""


class ShareNeedsExpiryError(ShareError):
    """分享已过期, 重新开启必须指定有效期"""


# ================================================================
# 可逆加密 (owner 回显提取码) — cryptography 缺失时优雅降级
# ================================================================

try:  # cryptography 是 pyproject 硬依赖, 但保持降级容错
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    _CRYPTO_OK = True
except ImportError:  # pragma: no cover - 环境异常兜底
    _CRYPTO_OK = False


def _password_enc_key() -> bytes:
    """HKDF(jwt_secret) 派生 32B 密钥 — 磁盘文件泄露不直接暴露提取码明文"""
    from dawei.config.settings import get_settings

    secret = get_settings().security.jwt_secret.encode()
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"dawei-workspace-share-v1", info=b"password-reveal").derive(secret)


def _encrypt_password(plaintext: str) -> str:
    if not _CRYPTO_OK:
        return ""
    nonce = secrets.token_bytes(12)
    ct = AESGCM(_password_enc_key()).encrypt(nonce, plaintext.encode(), None)
    return (nonce + ct).hex()


def _decrypt_password(enc_hex: str) -> str | None:
    if not enc_hex or not _CRYPTO_OK:
        return None
    try:
        raw = bytes.fromhex(enc_hex)
        return AESGCM(_password_enc_key()).decrypt(raw[:12], raw[12:], None).decode()
    except Exception:
        logger.warning("[WorkspaceShare] password_enc 解密失败 (jwt_secret 是否变更?)")
        return None


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


# ================================================================
# WorkspaceShareManager
# ================================================================


class WorkspaceShareManager:
    """分享索引管理器 — 一个工作区同时最多一个 active share (重新生成=轮换)"""

    def __init__(self, shares_file: Path | None = None):
        # None = 惰性解析 $DAWEI_HOME/workspace_shares.json (每次调用时解析, 便于测试隔离)
        self._shares_file_override = shares_file
        self._lock = threading.Lock()

    # ---------- 存储层 ----------

    def _shares_file(self) -> Path:
        if self._shares_file_override is not None:
            return self._shares_file_override
        from dawei import get_dawei_home

        return Path(get_dawei_home()) / "workspace_shares.json"

    def _load(self) -> dict[str, Any]:
        path = self._shares_file()
        if not path.exists():
            return {"version": 1, "shares": {}}
        data = json.loads(path.read_text(encoding="utf-8"))  # 损坏即炸 (FAST FAIL, 原子写保证基本不可能)
        data.setdefault("version", 1)
        data.setdefault("shares", {})
        return data

    def _save(self, data: dict[str, Any]) -> None:
        path = self._shares_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    # ---------- 查询 ----------

    def get_share(self, share_id: str) -> dict[str, Any] | None:
        with self._lock:
            share = self._load()["shares"].get(share_id)
        return dict(share) if share else None

    def get_share_for_workspace(self, workspace_id: str) -> dict[str, Any] | None:
        """owner 侧: 该工作区当前的 share (含 revoked, 供 UI 展示状态)"""
        with self._lock:
            for share in self._load()["shares"].values():
                if share.get("workspace_id") == workspace_id:
                    return dict(share)
        return None

    @staticmethod
    def is_expired(share: dict[str, Any]) -> bool:
        expires_at = share.get("expires_at")
        if not expires_at:
            return True
        try:
            return _parse_iso(expires_at) <= _now()
        except ValueError:
            return True

    # ---------- 创建 / 轮换 ----------

    def create_share(
        self,
        workspace_id: str,
        owner_user_id: str,
        tenant_id: str,
        password: str | None = None,
        expires_in_days: int = 3,
    ) -> dict[str, Any]:
        """创建或轮换分享 (同工作区旧 share 覆盖, 旧链接立即失效)

        返回 share 记录 + 短暂携带明文 password (仅本次响应, 不落盘明文)。
        """
        if expires_in_days not in SHARE_EXPIRY_DAYS:
            raise ShareError(f"expires_in_days 仅允许 {list(SHARE_EXPIRY_DAYS)}")
        if password is None:
            password = "".join(secrets.choice(PASSWORD_CHARSET) for _ in range(AUTO_PASSWORD_LENGTH))
        else:
            password = password.strip()
            if not (PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH) or not all(33 <= ord(c) <= 126 for c in password):
                raise ShareError(f"提取码须为 {PASSWORD_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} 位可见字符")

        salt = secrets.token_bytes(16)
        share = {
            "share_id": secrets.token_urlsafe(12),  # 16 字符
            "workspace_id": workspace_id,
            "owner_user_id": owner_user_id,
            "tenant_id": tenant_id,
            "password_salt": salt.hex(),
            "password_hash": hashlib.pbkdf2_hmac(PBKDF2_ALGO, password.encode(), salt, PBKDF2_ITERATIONS).hex(),
            "password_enc": _encrypt_password(password),
            "created_at": _now().isoformat(),
            "expires_at": (_now() + timedelta(days=expires_in_days)).isoformat(),
            "status": "active",  # active | closed
            "revoked": False,
            "view_count": 0,
            "clone_count": 0,
            "clone_log": [],
        }
        with self._lock:
            data = self._load()
            # 一工作区一 share: 轮换 = 换 share_id + 提取码, 旧记录直接删除
            data["shares"] = {sid: s for sid, s in data["shares"].items() if s.get("workspace_id") != workspace_id}
            data["shares"][share["share_id"]] = share
            self._save(data)
        logger.info("[WorkspaceShare] 创建分享 share_id=%s workspace=%s expires=%sd", share["share_id"], workspace_id, expires_in_days)
        return {**share, "password": password}

    # ---------- 状态机: close / open / 续期 / 撤销 ----------

    def _mutate_for_workspace(self, workspace_id: str) -> dict[str, Any]:
        """锁内取记录; 调用方在 with 块内改完落盘"""
        data = self._load()
        for sid, share in data["shares"].items():
            if share.get("workspace_id") == workspace_id:
                return data, share
        raise ShareNotFoundError(f"workspace {workspace_id} 尚无分享")

    def close_share_for_workspace(self, workspace_id: str) -> dict[str, Any]:
        """关闭 (可逆): 链接/提取码保留, 立即失效"""
        with self._lock:
            data, share = self._mutate_for_workspace(workspace_id)
            share["status"] = "closed"
            self._save(data)
            logger.info("[WorkspaceShare] 关闭分享 share_id=%s", share["share_id"])
            return dict(share)

    def open_share_for_workspace(self, workspace_id: str, expires_in_days: int | None = None) -> dict[str, Any]:
        """重新开启: 原链接+原提取码继续可用; 已过期须带新有效期一步复活"""
        if expires_in_days is not None and expires_in_days not in SHARE_EXPIRY_DAYS:
            raise ShareError(f"expires_in_days 仅允许 {list(SHARE_EXPIRY_DAYS)}")
        with self._lock:
            data, share = self._mutate_for_workspace(workspace_id)
            if share.get("revoked"):
                raise ShareRevokedError("分享已撤销, 无法重新开启, 请重新生成")
            if self.is_expired(share):
                if expires_in_days is None:
                    raise ShareNeedsExpiryError("分享已过期, 请选择有效期")
                share["expires_at"] = (_now() + timedelta(days=expires_in_days)).isoformat()
            share["status"] = "active"
            self._save(data)
            logger.info("[WorkspaceShare] 开启分享 share_id=%s", share["share_id"])
            return dict(share)

    def update_expiry_for_workspace(self, workspace_id: str, expires_in_days: int) -> dict[str, Any]:
        """续期/改期: 不换链接不换码; 对 active/closed/已过期均可 (过期即复活, 仅 revoked 拒绝)"""
        if expires_in_days not in SHARE_EXPIRY_DAYS:
            raise ShareError(f"expires_in_days 仅允许 {list(SHARE_EXPIRY_DAYS)}")
        with self._lock:
            data, share = self._mutate_for_workspace(workspace_id)
            if share.get("revoked"):
                raise ShareRevokedError("分享已撤销, 无法续期, 请重新生成")
            share["expires_at"] = (_now() + timedelta(days=expires_in_days)).isoformat()
            self._save(data)
            logger.info("[WorkspaceShare] 续期分享 share_id=%s -> %sd", share["share_id"], expires_in_days)
            return dict(share)

    def revoke_share_for_workspace(self, workspace_id: str) -> dict[str, Any]:
        """撤销 (永久): 只能重新生成; 记录保留供 owner GET 展示"""
        with self._lock:
            data, share = self._mutate_for_workspace(workspace_id)
            share["revoked"] = True
            self._save(data)
            logger.info("[WorkspaceShare] 撤销分享 share_id=%s", share["share_id"])
            return dict(share)

    # ---------- verify / 计数 ----------

    def verify_password(self, share_id: str, password: str) -> bool:
        with self._lock:
            share = self._load()["shares"].get(share_id)
        if not share:
            return False
        salt = bytes.fromhex(share.get("password_salt", ""))
        expected = share.get("password_hash", "")
        if not salt or not expected:
            return False
        actual = hashlib.pbkdf2_hmac(PBKDF2_ALGO, password.encode(), salt, PBKDF2_ITERATIONS).hex()
        return hmac.compare_digest(actual, expected)

    def reveal_password(self, share_id: str) -> str | None:
        """owner 回显提取码明文 (AES-GCM 解密; jwt_secret 变更或未存 enc 时返回 None)"""
        share = self.get_share(share_id)
        if not share:
            return None
        return _decrypt_password(share.get("password_enc", ""))

    def record_view(self, share_id: str) -> None:
        with self._lock:
            data = self._load()
            share = data["shares"].get(share_id)
            if share:
                share["view_count"] = int(share.get("view_count", 0)) + 1
                self._save(data)

    def record_clone(self, share_id: str, user_id: str, tenant_id: str, new_workspace_id: str) -> None:
        with self._lock:
            data = self._load()
            share = data["shares"].get(share_id)
            if not share:
                return
            share["clone_count"] = int(share.get("clone_count", 0)) + 1
            share.setdefault("clone_log", []).append(
                {"user_id": user_id, "tenant_id": tenant_id, "new_workspace_id": new_workspace_id, "at": _now().isoformat()},
            )
            share["clone_log"] = share["clone_log"][-CLONE_LOG_MAX:]  # FIFO 上限
            self._save(data)

    # ---------- share-token ----------

    def issue_share_token(self, share: dict[str, Any]) -> tuple[str, str]:
        """签发无状态 share-token; exp = 分享的 expires_at (浏览中途不踢人, 关闭/撤销靠逐请求重查即时失效)"""
        import jwt as pyjwt

        from dawei.config.settings import get_settings

        security = get_settings().security
        expires_at = _parse_iso(share["expires_at"])
        payload = {
            "scope": SHARE_TOKEN_SCOPE,
            "sid": share["share_id"],
            "iat": int(_now().timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = pyjwt.encode(payload, security.jwt_secret, algorithm=security.jwt_algorithm)
        return token, expires_at.isoformat()


def decode_share_token(token: str) -> dict[str, Any]:
    """校验 share-token (签名/过期/scope); 任何失败抛 ValueError (HTTP 层转 401)。

    用户 JWT 拿来当 share-token → scope 不符 → 拒绝, 反之亦然。
    """
    import jwt as pyjwt

    from dawei.config.settings import get_settings

    security = get_settings().security
    try:
        payload = pyjwt.decode(token, security.jwt_secret, algorithms=[security.jwt_algorithm])
    except pyjwt.InvalidTokenError as e:
        raise ValueError(f"invalid share token: {e}") from e
    if payload.get("scope") != SHARE_TOKEN_SCOPE:
        raise ValueError("token scope mismatch")
    return payload


# ================================================================
# 模块级单例 (懒加载; 测试可整体替换)
# ================================================================

_manager: WorkspaceShareManager | None = None


def get_share_manager() -> WorkspaceShareManager:
    global _manager
    if _manager is None:
        _manager = WorkspaceShareManager()
    return _manager


def reset_share_manager() -> None:
    """重置单例 (测试用)"""
    global _manager
    _manager = None
