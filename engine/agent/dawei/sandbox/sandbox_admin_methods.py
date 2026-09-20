# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""SandboxManager admin 方法扩展 — §14.19.4.3

为现有 SandboxManager 类附加 7 个 admin 方法, 通过 MethodType 绑定为实例方法。
不修改 sandbox_manager.py 主体, 保持向后兼容。

接口契约 (供 dawei.api.admin_sandbox 调用):
- list_active_sandboxes() -> List[Dict]
- list_user_quotas(search, skip, limit) -> List[Dict]
- update_user_quota(user_id_hash, quota) -> Dict
- list_policies() -> List[Dict]
- update_policy(tenant_id, yaml_content) -> Dict
- query_audit(...) -> List[Dict]
- get_provider_health() -> List[Dict]

数据源:
- 活跃沙箱: Docker SDK 列出带 dawei.sandbox 标签的容器
- 用户配额: DAWEI_HOME/sandbox_quotas.json (JSON 字典)
- 网络策略: DAWEI_HOME/sandbox_policies/<tenant_id>.yaml
- 审计日志: logs/sandbox_audit.log (JSONL, 与 _audit_log() 同源)
- Provider 健康: SandboxManager.health_check() + docker/podman 检测
"""
import json
import logging
import time
from pathlib import Path
from types import MethodType
from typing import Any, Dict, List, Optional

from dawei import get_dawei_home

logger = logging.getLogger(__name__)

# 沙箱容器在 Docker 中的标签 (约定: execute_command 中如未来需要可加上此标签)
SANDBOX_LABEL_KEY = "dawei.sandbox"
SANDBOX_LABEL_VALUE = "true"


# ==================== 存储路径辅助 ====================

def _quotas_file() -> Path:
    return get_dawei_home() / "sandbox_quotas.json"


def _policies_dir() -> Path:
    p = get_dawei_home() / "sandbox_policies"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _audit_log_file() -> Path:
    """与 sandbox_manager.py _audit_log 中的默认路径一致: logs/sandbox_audit.log"""
    return Path("logs/sandbox_audit.log")


def _load_quotas() -> Dict[str, Dict[str, Any]]:
    p = _quotas_file()
    if not p.exists():
        return {}
    try:
        with p.open(encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("sandbox_quotas.json 读取失败: %s", e)
        return {}


def _save_quotas(data: Dict[str, Dict[str, Any]]) -> None:
    p = _quotas_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    # 原子写入: 写临时文件再 rename
    tmp = p.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(p)


# ==================== 方法实现 (self = SandboxManager 实例) ====================

def _list_active_sandboxes(self) -> List[Dict[str, Any]]:
    """列出所有活跃的 dawei 沙箱容器"""
    results: List[Dict[str, Any]] = []
    try:
        # 优先按标签过滤 (约定); 若无标签容器, 退化到按 image 名匹配
        try:
            containers = self.client.containers.list(
                all=False,
                filters={"label": f"{SANDBOX_LABEL_KEY}={SANDBOX_LABEL_VALUE}"},
            )
        except Exception:
            containers = []

        if not containers:
            # 退化策略: 列出所有容器, 按 image 启发式匹配 (alpine/python 等)
            all_containers = self.client.containers.list(all=False)
            for c in all_containers:
                image_tags = getattr(c.image, "tags", []) or []
                if any(t.startswith(("alpine", "python", "ubuntu")) for t in image_tags):
                    containers.append(c)

        for c in containers:
            try:
                attrs = c.attrs or {}
                state = attrs.get("State", {}) or {}
                config = attrs.get("Config", {}) or {}
                results.append({
                    "container_id": c.id[:12],
                    "name": c.name,
                    "image": (config.get("Image") or "").split(":")[0],
                    "state": (state.get("Status") or "unknown").lower(),
                    "memory_mb": int((state.get("MemoryUsage") or 0) / 1024 / 1024) if state.get("MemoryUsage") else 0,
                    "created_at": attrs.get("Created", ""),
                    "user_id_hash": (c.labels or {}).get("dawei.user_id_hash", ""),
                    "workspace_id": (c.labels or {}).get("dawei.workspace_id", ""),
                })
            except Exception as e:
                logger.debug("跳过容器 %s: %s", getattr(c, "id", "?"), e)
    except Exception as e:
        logger.error("list_active_sandboxes 失败: %s", e)
    return results


def _list_user_quotas(self, search: Optional[str] = None,
                       skip: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
    """列出用户配额 (分页 + 搜索)"""
    data = _load_quotas()
    items = []
    for user_id_hash, q in data.items():
        if search and search not in user_id_hash and search not in (q.get("display_name") or ""):
            continue
        items.append({
            "user_id_hash": user_id_hash,
            "display_name": q.get("display_name"),
            "sandbox_count": q.get("sandbox_count", 0),
            "sandbox_limit": q.get("sandbox_limit", 10),
            "memory_mb": q.get("memory_mb", 0),
            "memory_limit_mb": q.get("memory_limit_mb", 1024),
            "rate_per_min": q.get("rate_per_min", 0),
            "rate_limit": q.get("rate_limit", 60),
        })
    # 稳定排序 (按 user_id_hash)
    items.sort(key=lambda x: x["user_id_hash"])
    return items[skip:skip + limit]


def _update_user_quota(self, user_id_hash: str, quota: Dict[str, Any]) -> Dict[str, Any]:
    """更新用户配额 (热加载, 写回 JSON)"""
    data = _load_quotas()
    existing = data.get(user_id_hash, {})
    existing.update({
        "sandbox_limit": quota.get("max_sessions", existing.get("sandbox_limit", 10)),
        "memory_limit_mb": quota.get("max_memory_mb", existing.get("memory_limit_mb", 1024)),
        "rate_limit": quota.get("max_rate_per_min", existing.get("rate_limit", 60)),
    })
    data[user_id_hash] = existing
    _save_quotas(data)
    return {
        "user_id_hash": user_id_hash,
        "display_name": existing.get("display_name"),
        "sandbox_count": existing.get("sandbox_count", 0),
        "sandbox_limit": existing["sandbox_limit"],
        "memory_mb": existing.get("memory_mb", 0),
        "memory_limit_mb": existing["memory_limit_mb"],
        "rate_per_min": existing.get("rate_per_min", 0),
        "rate_limit": existing["rate_limit"],
    }


def _list_policies(self) -> List[Dict[str, Any]]:
    """列出 per-tenant 网络策略"""
    results: List[Dict[str, Any]] = []
    pdir = _policies_dir()
    for yfile in sorted(pdir.glob("*.yaml")):
        tenant_id = yfile.stem
        try:
            content = yfile.read_text(encoding="utf-8")
            stat = yfile.stat()
            # 简化: version 从文件名/修改时间推断
            results.append({
                "tenant_id": tenant_id,
                "version": int(stat.st_mtime),
                "yaml_content": content,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime)),
                "updated_by_admin_id": None,
                "rollout_status": "complete",
            })
        except OSError as e:
            logger.warning("读取策略 %s 失败: %s", yfile, e)
    return results


def _update_policy(self, tenant_id: str, yaml_content: str) -> Dict[str, Any]:
    """更新 per-tenant 策略 (热加载, 写 YAML 文件)"""
    # tenant_id 合法性校验: 仅允许 [a-z0-9_-]
    if not tenant_id or not all(c.isalnum() or c in "-_" for c in tenant_id):
        raise ValueError(f"非法 tenant_id: {tenant_id!r}")
    if not yaml_content or len(yaml_content) > 65536:
        raise ValueError("yaml_content 长度必须在 1..65536 字节")

    yfile = _policies_dir() / f"{tenant_id}.yaml"
    # 原子写入
    tmp = yfile.with_suffix(".yaml.tmp")
    tmp.write_text(yaml_content, encoding="utf-8")
    tmp.replace(yfile)
    stat = yfile.stat()
    return {
        "tenant_id": tenant_id,
        "version": int(stat.st_mtime),
        "yaml_content": yaml_content,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime)),
        "updated_by_admin_id": None,
        "rollout_status": "complete",
    }


def _query_audit(
    self,
    user_id_hash: Optional[str] = None,
    action: Optional[str] = None,
    workspace_id: Optional[str] = None,
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """审计日志查询 (JSONL 流式读取, 过滤后分页)"""
    log_file = _audit_log_file()
    if not log_file.exists():
        return []

    events: List[Dict[str, Any]] = []
    try:
        with log_file.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # 时间戳转换: ISO -> epoch ms (容错)
                ts_ms: int = 0
                ts_str = entry.get("timestamp", "")
                if ts_str:
                    try:
                        from datetime import datetime
                        # 兼容 "...Z" 格式
                        if ts_str.endswith("Z"):
                            ts_str = ts_str[:-1] + "+00:00"
                        dt = datetime.fromisoformat(ts_str)
                        ts_ms = int(dt.timestamp() * 1000)
                    except (ValueError, TypeError):
                        ts_ms = int(time.time() * 1000)  # fallback

                # 过滤
                if start_ts and ts_ms < start_ts:
                    continue
                if end_ts and ts_ms > end_ts:
                    continue
                if user_id_hash and entry.get("user_id") != user_id_hash:
                    continue
                # 'action' 字段: 审计记录里实际是 'command' (沙箱执行), 映射:
                # admin 通过 action 过滤时, 我们用 command 包含 action 关键字的方式
                if action and action not in (entry.get("command") or ""):
                    continue
                if workspace_id and entry.get("workspace_id") != workspace_id:
                    continue

                events.append({
                    "id": f"{ts_ms}-{lineno}",
                    "ts": ts_ms,
                    "user_id_hash": entry.get("user_id", "unknown"),
                    "action": entry.get("command", "")[:200],
                    "workspace_id": entry.get("workspace_id"),
                    "result": "success" if entry.get("exit_code") == 0 else "failure",
                    "detail": {
                        "exit_code": entry.get("exit_code"),
                        "execution_time_ms": entry.get("execution_time_ms"),
                        "sandbox_config": entry.get("sandbox_config"),
                    },
                })
    except OSError as e:
        logger.error("query_audit 读取失败: %s", e)

    # 按时间倒序
    events.sort(key=lambda e: e["ts"], reverse=True)
    return events[skip:skip + limit]


def _get_provider_health(self) -> List[Dict[str, Any]]:
    """Provider 健康状态 (docker, podman, subprocess)"""
    out: List[Dict[str, Any]] = []
    now_ms = int(time.time() * 1000)

    # Docker
    t0 = time.time()
    docker_ok = False
    try:
        self.client.ping()
        docker_ok = True
    except Exception:
        pass
    latency_ms = int((time.time() - t0) * 1000)
    # active_sandboxes 数
    active = 0
    try:
        active = len(self.client.containers.list(filters={
            "label": f"{SANDBOX_LABEL_KEY}={SANDBOX_LABEL_VALUE}",
        }))
    except Exception:
        # 退化: 按 image 启发式
        try:
            for c in self.client.containers.list(all=False):
                tags = getattr(c.image, "tags", []) or []
                if any(t.startswith(("alpine", "python", "ubuntu")) for t in tags):
                    active += 1
        except Exception:
            pass
    out.append({
        "provider": "docker",
        "healthy": docker_ok,
        "latency_ms": latency_ms,
        "active_sandboxes": active,
        "last_check_ts": now_ms,
    })

    # Podman (可选, 仅在有 SANDBOX_PODMAN_ENABLED 时检测)
    # 这里仅做基础检查, 避免拖慢响应
    import shutil
    podman_bin = shutil.which("podman")
    out.append({
        "provider": "podman",
        "healthy": bool(podman_bin),
        "latency_ms": 0 if not podman_bin else None,
        "active_sandboxes": 0,
        "last_check_ts": now_ms,
    })

    # subprocess (内置, 始终 healthy)
    out.append({
        "provider": "subprocess",
        "healthy": True,
        "latency_ms": 0,
        "active_sandboxes": 0,
        "last_check_ts": now_ms,
    })

    return out


# ==================== 绑定入口 ====================

# 方法名 -> 实现函数 映射
_ADMIN_METHODS = {
    "list_active_sandboxes": _list_active_sandboxes,
    "list_user_quotas": _list_user_quotas,
    "update_user_quota": _update_user_quota,
    "list_policies": _list_policies,
    "update_policy": _update_policy,
    "query_audit": _query_audit,
    "get_provider_health": _get_provider_health,
}


def install_admin_methods(sandbox_manager_cls) -> None:
    """将 admin 方法绑定到 SandboxManager 类 (幂等)

    在 dawei.api.admin_sandbox 模块加载时调用一次。
    """
    for name, fn in _ADMIN_METHODS.items():
        if not hasattr(sandbox_manager_cls, name):
            setattr(sandbox_manager_cls, name, fn)
            logger.debug("SandboxManager.%s 已绑定", name)


def uninstall_admin_methods(sandbox_manager_cls) -> None:
    """移除 admin 方法 (主要用于测试回滚)"""
    for name in _ADMIN_METHODS:
        if hasattr(sandbox_manager_cls, name):
            delattr(sandbox_manager_cls, name)


# ==================== 直接调用 (无需绑定到类) ====================

def list_active_sandboxes(sandbox_manager) -> List[Dict[str, Any]]:
    return _list_active_sandboxes(sandbox_manager)


def list_user_quotas(sandbox_manager, search=None, skip=0, limit=20):
    return _list_user_quotas(sandbox_manager, search=search, skip=skip, limit=limit)


def update_user_quota(sandbox_manager, user_id_hash, quota):
    return _update_user_quota(sandbox_manager, user_id_hash, quota)


def list_policies(sandbox_manager):
    return _list_policies(sandbox_manager)


def update_policy(sandbox_manager, tenant_id, yaml_content):
    return _update_policy(sandbox_manager, tenant_id, yaml_content)


def query_audit(sandbox_manager, **kwargs):
    return _query_audit(sandbox_manager, **kwargs)


def get_provider_health(sandbox_manager):
    return _get_provider_health(sandbox_manager)