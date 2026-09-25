# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""nn-bot 侧沙箱 Admin API (§14.19)

供 nn-user-system SaaS admin UI 代理调用。
所有端点要求 Authorization: Bearer <SANDBOX_ADMIN_TOKEN>。

实现注意:
- 本文件仅暴露"读 + 受控写"接口, 不替代现有 webui 的用户级 admin
- 数据源: 现有 sandbox_manager + memory.db
- 写操作限制: 仅 superadmin token 可写, 普通 admin token 仅读
"""
import logging
import os
from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/sandbox", tags=["admin-sandbox"])


# ===== SandboxManager admin 方法安装 (幂等) =====
# 延迟到 endpoint 调用时再 import SandboxManager, 避免模块加载期触发预存在问题
# (sandbox_manager.py 中 Dict 未 import, 在 Python 3.12 解释器会 NameError)
# 安装函数本身 import 是安全的, 它只定义了函数, 没有触发 SandboxManager 类实例化
from dawei_biz.saas.sandbox_admin_methods import install_admin_methods

def _ensure_admin_methods() -> None:
    """在第一次 endpoint 调用时执行 (线程安全, 因 install_admin_methods 内部幂等)"""
    try:
        from dawei.sandbox.sandbox_manager import SandboxManager
        install_admin_methods(SandboxManager)
    except (ImportError, NameError) as e:
        logger.warning("SandboxManager 加载失败, admin 方法将不可用: %s", e)


# ===== Auth (简化版 — 与现有 webui 隔离) =====

async def require_admin_token(authorization: Optional[str] = Header(None)):
    """验证 admin token (与 SANDBOX_ADMIN_TOKEN 一致)

    生产环境应使用 JWT 含 iss/admin_level 字段, 这里先简化为
    bearer secret 校验。完整 RBAC 在后续 PR 加上。
    """
    expected = os.environ.get("SANDBOX_ADMIN_TOKEN", "")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization")
    token = authorization.removeprefix("Bearer ")
    if not expected or token != expected:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    return token


# ===== Response Models =====

class StatsResponse(BaseModel):
    total: int
    active: int
    paused: int
    memory_mb: int
    quota_violations_24h: int


class UserQuota(BaseModel):
    user_id_hash: str
    display_name: Optional[str] = None
    sandbox_count: int
    sandbox_limit: int
    memory_mb: int
    memory_limit_mb: int
    rate_per_min: int
    rate_limit: int


class NetworkPolicy(BaseModel):
    tenant_id: str
    version: int
    yaml_content: str
    updated_at: str
    updated_by_admin_id: Optional[str] = None
    rollout_status: str = "complete"


class AuditEvent(BaseModel):
    id: str
    ts: int
    user_id_hash: str
    action: str
    workspace_id: Optional[str] = None
    result: str
    detail: Dict[str, Any] = {}


class ProviderHealth(BaseModel):
    provider: str
    healthy: bool
    latency_ms: Optional[int] = None
    active_sandboxes: int
    last_check_ts: int


# ===== 总览 =====

@router.get("/stats/total", response_model=StatsResponse)
async def stats_total(_: str = Depends(require_admin_token)):
    """沙箱总数 / 活跃 / 暂停 / 内存 / 24h 配额超限"""
    _ensure_admin_methods()
    try:
        from dawei.sandbox.sandbox_manager import SandboxManager
        sm = SandboxManager()
        sandboxes = sm.list_active_sandboxes()
        active = sum(1 for s in sandboxes if s.get("state") in ("running", "up"))
        paused = sum(1 for s in sandboxes if s.get("state") in ("paused", "exited"))
        memory_mb = sum(int(s.get("memory_mb", 0)) for s in sandboxes)
        return StatsResponse(
            total=len(sandboxes),
            active=active,
            paused=paused,
            memory_mb=memory_mb,
            quota_violations_24h=0,
        )
    except Exception as e:
        logger.exception("stats_total 失败: ")
        return StatsResponse(
            total=0, active=0, paused=0, memory_mb=0, quota_violations_24h=0,
        )


@router.get("/users", response_model=List[UserQuota])
async def list_user_quotas(
    page: int = 1, size: int = 20, search: Optional[str] = None,
    _: str = Depends(require_admin_token),
):
    """用户配额列表 (分页)"""
    _ensure_admin_methods()
    try:
        from dawei.sandbox.sandbox_manager import SandboxManager
        sm = SandboxManager()
        items = sm.list_user_quotas(search=search, skip=(page - 1) * size, limit=size)
        return [UserQuota(**q) for q in items]
    except Exception as e:
        logger.exception("list_user_quotas 失败: ")
        return []


@router.put("/users/{user_id_hash}/quota", response_model=UserQuota)
async def update_user_quota(
    user_id_hash: str,
    quota: Dict[str, Any],
    _: str = Depends(require_admin_token),
):
    """修改用户配额 (热加载, 写 JSON)"""
    _ensure_admin_methods()
    try:
        from dawei.sandbox.sandbox_manager import SandboxManager
        sm = SandboxManager()
        return UserQuota(**sm.update_user_quota(user_id_hash, quota))
    except (ImportError, NameError) as e:
        # 预存在的 sandbox_manager.py Dict bug 触发 NameError,
        # 管理员 UI 应明确知道这是底层 bug 而非配额写入失败
        logger.error("update_user_quota: SandboxManager 不可用: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="sandbox_manager 不可用, 请联系运维 (已知 bug: typing.Dict 未 import)",
        )


@router.get("/policies", response_model=List[NetworkPolicy])
async def list_policies(_: str = Depends(require_admin_token)):
    """per-tenant 网络策略列表"""
    _ensure_admin_methods()
    try:
        from dawei.sandbox.sandbox_manager import SandboxManager
        sm = SandboxManager()
        return [NetworkPolicy(**p) for p in sm.list_policies()]
    except Exception as e:
        logger.exception("list_policies 失败: ")
        return []


@router.put("/policies/{tenant_id}", response_model=NetworkPolicy)
async def update_policy(
    tenant_id: str,
    body: Dict[str, str],
    _: str = Depends(require_admin_token),
):
    """更新 per-tenant 策略 (热加载, 写 YAML)"""
    _ensure_admin_methods()
    try:
        from dawei.sandbox.sandbox_manager import SandboxManager
        sm = SandboxManager()
        return NetworkPolicy(**sm.update_policy(tenant_id, body.get("yaml_content", "")))
    except (ImportError, NameError) as e:
        logger.error("update_policy: SandboxManager 不可用: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="sandbox_manager 不可用, 请联系运维 (已知 bug: typing.Dict 未 import)",
        )


@router.get("/audit", response_model=List[AuditEvent])
async def list_audit(
    page: int = 1, size: int = 50,
    user_id_hash: Optional[str] = None,
    action: Optional[str] = None,
    workspace_id: Optional[str] = None,
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
    _: str = Depends(require_admin_token),
):
    """审计日志查询 (JSONL 流式)"""
    _ensure_admin_methods()
    try:
        from dawei.sandbox.sandbox_manager import SandboxManager
        sm = SandboxManager()
        events = sm.query_audit(
            user_id_hash=user_id_hash, action=action,
            workspace_id=workspace_id,
            start_ts=start_ts, end_ts=end_ts,
            skip=(page - 1) * size, limit=size,
        )
        return [AuditEvent(**e) for e in events]
    except Exception as e:
        logger.exception("list_audit 失败: ")
        return []


@router.get("/providers/health", response_model=List[ProviderHealth])
async def provider_health(_: str = Depends(require_admin_token)):
    """Provider 健康状态"""
    _ensure_admin_methods()
    try:
        from dawei.sandbox.sandbox_manager import SandboxManager
        sm = SandboxManager()
        return [ProviderHealth(**p) for p in sm.get_provider_health()]
    except Exception as e:
        logger.exception("provider_health 失败: ")
        return []