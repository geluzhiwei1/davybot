# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""
许可证管理 API 路由

支持企业版许可证的激活、验证、续期和吊销。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dawei.config.settings import get_settings
from dawei.core.datetime_compat import UTC

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/license", tags=["license"])


def _get_license_secret() -> str:
    """获取许可证签名密钥（从配置中读取，生产环境必须通过 LICENSE_SECRET 环境变量设置）"""
    return get_settings().security.license_secret


# ─── License Models ───


class LicenseActivateRequest(BaseModel):
    """许可证激活请求"""
    license_key: str = Field(..., description="许可证密钥 (格式: DVBYT-XXXX-XXXX-XXXX-XXXX)")
    machine_id: str = Field(..., description="机器标识 (硬件指纹)")
    product: str = Field("normnomos-enterprise", description="产品标识")


class LicenseActivateResponse(BaseModel):
    """许可证激活响应"""
    success: bool
    token: str | None = None  # JWT 激活 token
    expires_at: str | None = None
    features: list[str] | None = None
    message: str = ""
    error_code: str | None = None


class LicenseVerifyRequest(BaseModel):
    """许可证验证请求"""
    token: str = Field(..., description="激活 token")
    machine_id: str = Field(..., description="机器标识")


class LicenseVerifyResponse(BaseModel):
    """许可证验证响应"""
    valid: bool
    expires_at: str | None = None
    remaining_days: int | None = None
    features: list[str] | None = None
    error_code: str | None = None


class LicenseRenewRequest(BaseModel):
    """许可证续期请求"""
    token: str = Field(..., description="当前激活 token")
    extension_days: int = Field(365, ge=30, le=1095, description="续期天数 (30-1095)")


class LicenseRenewResponse(BaseModel):
    """许可证续期响应"""
    success: bool
    token: str | None = None
    new_expires_at: str | None = None
    message: str = ""


class LicenseRevokeRequest(BaseModel):
    """许可证吊销请求"""
    token: str = Field(..., description="激活 token")
    reason: str = Field("", description="吊销原因")


class LicenseInfoResponse(BaseModel):
    """许可证信息"""
    token: str
    product: str
    issue_date: str
    expires_at: str
    remaining_days: int
    machine_id: str
    features: list[str]
    is_active: bool


# ─── Constants ───

LICENSE_FILE = Path("~/.normnomos/licenses.json").expanduser()
_FEATURES_ALL = [
    "ip-module",           # IP 知识产权 8 大模块
    "sanctions",           # 制裁合规
    "contract-review",     # 合同审查
    "regulatory",          # 法规情报
    "multi-agent",         # 多 Agent 协作
    "batch-processing",    # 批量处理
    "api-access",          # API 访问
    "custom-skills",       # 自定义技能
]
_FEATURES_IP = [
    "ip-module",           # IP 模块基础功能
    "patent-search",       # 专利检索
    "trademark-search",    # 商标检索
]


# ─── Helpers ───


def _load_licenses() -> dict[str, Any]:
    """加载所有已激活的许可证"""
    if not LICENSE_FILE.exists():
        return {"licenses": {}}
    with open(LICENSE_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_licenses(data: dict[str, Any]) -> None:
    """保存许可证数据"""
    LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LICENSE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _hash_token(data: str) -> str:
    """生成 token 的哈希值"""
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def _sign(license_key: str, machine_id: str, expires: int) -> str:
    """对许可证数据进行 HMAC 签名"""
    payload = f"{license_key}:{machine_id}:{expires}"
    return hmac.new(_get_license_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()


def _verify_signature(license_key: str, machine_id: str, expires: int, signature: str) -> bool:
    """验证 HMAC 签名"""
    expected = _sign(license_key, machine_id, expires)
    return hmac.compare_digest(expected, signature)


def _parse_license_key(key: str) -> tuple[str, str]:
    """解析许可证密钥，返回 (product_code, serial)

    Format: DVBYT-ENT-XXXX-XXXX-XXXX or DVBYT-IP-XXXX-XXXX-XXXX
    """
    parts = key.strip().upper().replace("-", "").replace(" ", "")
    if len(parts) < 12:
        raise ValueError("Invalid license key format")
    return parts[:7], parts[7:]


def _validate_license_key(key: str) -> bool:
    """验证许可证密钥格式"""
    parts = key.strip().split("-")
    if len(parts) != 5:
        return False
    if parts[0] != "DVBYT":
        return False
    return all(len(p) == 4 for p in parts[1:])


def _get_features(product_code: str) -> list[str]:
    """根据产品代码返回功能列表"""
    if "ENT" in product_code:
        return _FEATURES_ALL
    if "IP" in product_code:
        return _FEATURES_IP
    return []


# ─── Endpoints ───


@router.post("/activate", response_model=LicenseActivateResponse)
async def activate_license(request: LicenseActivateRequest):
    """激活企业版许可证

    流程:
    1. 验证许可证密钥格式
    2. 检查是否已激活
    3. 计算过期时间
    4. 生成激活 token
    5. 存储许可证记录
    6. 返回激活 token 和功能列表

    当前版本为本地离线验证模式，生产环境需连接 license.normnomos.com 进行服务端验证。
    """
    if not _validate_license_key(request.license_key):
        return LicenseActivateResponse(
            success=False,
            message="许可证密钥格式不正确。格式: DVBYT-XXXX-XXXX-XXXX-XXXX",
            error_code="INVALID_KEY_FORMAT",
        )

    product_code, serial = _parse_license_key(request.license_key)
    features = _get_features(product_code)

    # 检查是否已经激活
    licenses = _load_licenses()
    token_hash = _hash_token(request.license_key + request.machine_id)

    if token_hash in licenses["licenses"]:
        existing = licenses["licenses"][token_hash]
        # 如果仍然有效，直接返回已有 token
        if existing.get("expires_at"):
            expires_dt = datetime.fromisoformat(existing["expires_at"])
            if expires_dt > datetime.now(UTC):
                return LicenseActivateResponse(
                    success=True,
                    token=existing["token"],
                    expires_at=existing["expires_at"],
                    features=existing.get("features", features),
                    message="许可证已激活，无需重复操作",
                )

    # 计算过期时间（默认1年）
    expires_at = datetime.now(UTC) + timedelta(days=365)
    expires_ts = int(expires_at.timestamp())

    # 生成激活 token
    token_payload = {
        "key": request.license_key,
        "mid": request.machine_id,
        "product": request.product,
        "code": product_code,
        "exp": expires_ts,
        "sig": _sign(request.license_key, request.machine_id, expires_ts),
    }
    token = "|".join(f"{k}:{v}" for k, v in token_payload.items())

    # 存储许可证
    licenses["licenses"][token_hash] = {
        "token": token,
        "product": request.product,
        "machine_id": request.machine_id,
        "issue_date": datetime.now(UTC).isoformat(),
        "expires_at": expires_at.isoformat(),
        "features": features,
        "is_active": True,
    }
    _save_licenses(licenses)

    logger.info(f"License activated: product={request.product} machine={request.machine_id[:8]}...")

    return LicenseActivateResponse(
        success=True,
        token=token,
        expires_at=expires_at.isoformat(),
        features=features,
        message="许可证激活成功",
    )


@router.post("/verify", response_model=LicenseVerifyResponse)
async def verify_license(request: LicenseVerifyRequest):
    """验证许可证是否有效

    每次应用启动时调用，验证激活 token 的签名和有效期。
    """
    try:
        parts = dict(item.split(":", 1) for item in request.token.split("|"))
    except ValueError:
        return LicenseVerifyResponse(valid=False, error_code="INVALID_TOKEN_FORMAT")

    key = parts.get("key", "")
    mid = parts.get("mid", "")
    exp = int(parts.get("exp", "0"))
    sig = parts.get("sig", "")
    code = parts.get("code", "")

    # 验证机器ID
    if mid != request.machine_id:
        return LicenseVerifyResponse(valid=False, error_code="MACHINE_MISMATCH")

    # 验证签名
    if not _verify_signature(key, mid, exp, sig):
        return LicenseVerifyResponse(valid=False, error_code="SIGNATURE_INVALID")

    # 检查过期
    expires_dt = datetime.fromtimestamp(exp, tz=UTC)
    now = datetime.now(UTC)
    if expires_dt <= now:
        return LicenseVerifyResponse(valid=False, error_code="LICENSE_EXPIRED", expires_at=expires_dt.isoformat(), remaining_days=0)

    remaining_days = (expires_dt - now).days
    features = _get_features(code)

    return LicenseVerifyResponse(
        valid=True,
        expires_at=expires_dt.isoformat(),
        remaining_days=remaining_days,
        features=features,
    )


@router.post("/renew", response_model=LicenseRenewResponse)
async def renew_license(request: LicenseRenewRequest):
    """续期许可证

    延长许可证有效期。当前为本地模式，生产环境需服务端处理续期费用。
    """
    try:
        parts = dict(item.split(":", 1) for item in request.token.split("|"))
    except ValueError:
        return LicenseRenewResponse(success=False, message="无效的激活 token")

    key = parts.get("key", "")
    mid = parts.get("mid", "")

    # 计算新的过期时间
    new_expires = datetime.now(UTC) + timedelta(days=request.extension_days)
    new_exp_ts = int(new_expires.timestamp())

    # 重新生成 token
    code = parts.get("code", "")
    token_payload = {
        "key": key,
        "mid": mid,
        "product": parts.get("product", ""),
        "code": code,
        "exp": str(new_exp_ts),
        "sig": _sign(key, mid, new_exp_ts),
    }
    new_token = "|".join(f"{k}:{v}" for k, v in token_payload.items())

    # 更新存储
    token_hash = _hash_token(key + mid)
    licenses = _load_licenses()
    if token_hash in licenses["licenses"]:
        licenses["licenses"][token_hash]["token"] = new_token
        licenses["licenses"][token_hash]["expires_at"] = new_expires.isoformat()
        _save_licenses(licenses)

    logger.info(f"License renewed: extension={request.extension_days}d new_expiry={new_expires.isoformat()}")

    return LicenseRenewResponse(
        success=True,
        token=new_token,
        new_expires_at=new_expires.isoformat(),
        message=f"许可证已续期 {request.extension_days} 天",
    )


@router.post("/revoke")
async def revoke_license(request: LicenseRevokeRequest):
    """吊销许可证"""
    try:
        parts = dict(item.split(":", 1) for item in request.token.split("|"))
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的激活 token")

    key = parts.get("key", "")
    mid = parts.get("mid", "")

    token_hash = _hash_token(key + mid)
    licenses = _load_licenses()
    if token_hash in licenses["licenses"]:
        licenses["licenses"][token_hash]["is_active"] = False
        licenses["licenses"][token_hash]["revoked_at"] = datetime.now(UTC).isoformat()
        licenses["licenses"][token_hash]["revoke_reason"] = request.reason
        _save_licenses(licenses)

    logger.info(f"License revoked: reason='{request.reason}'")

    return {"success": True, "message": "许可证已吊销"}


@router.get("/info", response_model=LicenseInfoResponse)
async def get_license_info(token: str):
    """获取当前许可证详细信息"""
    try:
        parts = dict(item.split(":", 1) for item in token.split("|"))
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的激活 token")

    key = parts.get("key", "")
    mid = parts.get("mid", "")
    exp = int(parts.get("exp", "0"))
    code = parts.get("code", "")
    product = parts.get("product", "")

    token_hash = _hash_token(key + mid)
    licenses = _load_licenses()
    info = licenses["licenses"].get(token_hash)

    if not info:
        raise HTTPException(status_code=404, detail="许可证未激活")

    expires_dt = datetime.fromtimestamp(exp, tz=UTC) if exp else datetime.now(UTC)
    remaining = max(0, (expires_dt - datetime.now(UTC)).days)

    return LicenseInfoResponse(
        token=info["token"],
        product=info.get("product", product),
        issue_date=info.get("issue_date", ""),
        expires_at=expires_dt.isoformat(),
        remaining_days=remaining,
        machine_id=info.get("machine_id", mid),
        features=info.get("features", _get_features(code)),
        is_active=info.get("is_active", True),
    )
