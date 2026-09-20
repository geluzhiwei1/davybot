# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""BackendSelector — workspace → 后端类型 选择 (SaaS 沙箱方案 §5.2)

决策优先级:
1. workspace_meta.backend (显式绑定, 例如来自 admin 后台)
2. tenant_cfg.default_backend (租户级配置)
3. 环境变量 DAWEI_SANDBOX_BACKEND 默认值
4. round-robin 跨集群 fallback (least-loaded)

环境变量:
  DAWEI_SANDBOX_BACKEND                  全局默认 backend (默认 cubesandbox)
  DAWEI_SANDBOX_BACKEND_BY_TENANT        JSON: {"tenant-a":"cubesandbox","tenant-b":"agentenv"}
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any

from dawei.sandbox.base import BackendType, TrustedContext

logger = logging.getLogger(__name__)


@dataclass
class WorkspaceMeta:
    """workspace 后端绑定 (来自数据库 / 缓存)"""

    workspace_id: str
    tenant_id: str
    backend: BackendType = BackendType.CUBESANDBOX
    region: str = "default"
    pinned_node: str | None = None
    priority: int = 50  # 0=low, 100=high


@dataclass
class ClusterStatus:
    """集群负载状态 (用于 least-loaded fallback)"""

    name: str
    backend: BackendType
    current_load: int = 0      # 当前沙箱数
    max_capacity: int = 1000   # 上限
    healthy: bool = True

    @property
    def load_ratio(self) -> float:
        return self.current_load / max(self.max_capacity, 1)


class BackendSelector:
    """workspace → backend 路由选择器 (单例)"""

    _instance: BackendSelector | None = None
    _lock = threading.Lock()

    def __init__(self):
        self._meta_cache: dict[str, WorkspaceMeta] = {}
        self._tenant_backend: dict[str, BackendType] = self._load_tenant_config()
        self._default_backend: BackendType = self._load_default_backend()
        # 集群状态 (用于 least-loaded fallback)
        self._clusters: dict[str, ClusterStatus] = {}
        # round-robin 计数器
        self._rr_counter = 0

    @classmethod
    def instance(cls) -> BackendSelector:
        """单例获取 (线程安全)"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ================================================================
    # 配置加载
    # ================================================================

    def _load_default_backend(self) -> BackendType:
        raw = os.environ.get("DAWEI_SANDBOX_BACKEND", "cubesandbox").strip().lower()
        try:
            return BackendType(raw)
        except ValueError:
            logger.warning(
                "[BACKEND_SELECTOR] 未知 DAWEI_SANDBOX_BACKEND=%s, 降级 cubesandbox",
                raw,
            )
            return BackendType.CUBESANDBOX

    def _load_tenant_config(self) -> dict[str, BackendType]:
        raw = os.environ.get("DAWEI_SANDBOX_BACKEND_BY_TENANT", "").strip()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return {tid: BackendType(v) for tid, v in data.items()}
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                "[BACKEND_SELECTOR] DAWEI_SANDBOX_BACKEND_BY_TENANT 解析失败: %s",
                e,
            )
            return {}

    # ================================================================
    # 集群状态 (least-loaded fallback)
    # ================================================================

    def register_cluster(self, status: ClusterStatus) -> None:
        """注册集群状态 (由 Provider 健康检查调用)"""
        self._clusters[status.name] = status

    def update_load(self, cluster_name: str, current_load: int) -> None:
        cs = self._clusters.get(cluster_name)
        if cs:
            cs.current_load = current_load

    def _least_loaded_cluster(self, backend: BackendType) -> ClusterStatus | None:
        """选择同 backend 中负载最低的集群"""
        candidates = [
            cs for cs in self._clusters.values()
            if cs.backend == backend and cs.healthy
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda c: c.load_ratio)

    # ================================================================
    # 选择入口
    # ================================================================

    def select(self, ctx: TrustedContext) -> WorkspaceMeta:
        """选择 workspace 的 backend

        返回 WorkspaceMeta, 含 backend + pinned_node (用于细粒度路由)
        """
        workspace_uuid = getattr(ctx, "workspace_uuid", "") or str(ctx.workspace_id)
        tenant_id = getattr(ctx, "tenant_id", "") or "_default"

        # 1. workspace 显式绑定 (缓存命中)
        meta = self._meta_cache.get(workspace_uuid)
        if meta:
            return meta

        # 2. tenant 级默认
        tenant_backend = self._tenant_backend.get(tenant_id)
        if tenant_backend:
            return WorkspaceMeta(
                workspace_id=workspace_uuid,
                tenant_id=tenant_id,
                backend=tenant_backend,
            )

        # 3. 全局默认 + least-loaded cluster
        cluster = self._least_loaded_cluster(self._default_backend)
        meta = WorkspaceMeta(
            workspace_id=workspace_uuid,
            tenant_id=tenant_id,
            backend=self._default_backend,
            pinned_node=cluster.name if cluster else None,
        )
        # round-robin 仅在完全无集群时退化
        if not cluster:
            self._rr_counter += 1
            meta.pinned_node = f"rr-{self._rr_counter % 2}"

        logger.debug(
            "[BACKEND_SELECTOR] %s/%s → backend=%s node=%s",
            tenant_id, workspace_uuid, meta.backend.value, meta.pinned_node,
        )
        return meta

    def bind_workspace(self, workspace_uuid: str, meta: WorkspaceMeta) -> None:
        """显式绑定 workspace 到 backend (admin 后台调用)"""
        self._meta_cache[workspace_uuid] = meta
        logger.info(
            "[BACKEND_SELECTOR] 已绑定 %s → backend=%s",
            workspace_uuid, meta.backend.value,
        )

    def unbind_workspace(self, workspace_uuid: str) -> None:
        self._meta_cache.pop(workspace_uuid, None)


# 便捷函数
def select_backend(ctx: TrustedContext) -> WorkspaceMeta:
    return BackendSelector.instance().select(ctx)
