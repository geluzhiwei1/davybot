# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""workspace_path 白名单校验 (§沙箱系统升级 v2 — F3)

三层校验:
1. 路径必须在 WORKSPACE_ROOT_ALLOWLIST 之下
2. 符号链接解析后仍在白名单内 (防 .. 和 symlink 绕过)
3. 当前进程对该路径有读/执行权限

环境变量:
  DAWEI_WORKSPACE_ROOT_ALLOWLIST=/workspace:/home:/srv/workspaces
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from dawei.core.exceptions import SandboxSecurityError

logger = logging.getLogger(__name__)


def _get_allowlist() -> frozenset[Path]:
    """从环境变量加载白名单根目录"""
    raw = os.environ.get(
        "DAWEI_WORKSPACE_ROOT_ALLOWLIST",
        "/workspace:/home:/srv/workspaces:/tmp:/var/tmp",
    )
    result: set[Path] = set()
    for part in raw.split(":"):
        part = part.strip()
        if part:
            try:
                result.add(Path(part).resolve())
            except OSError:
                logger.warning("[PATH_VALIDATOR] 无法解析白名单路径: %s", part)
    return frozenset(result)


def validate_workspace_path(
    workspace_path: Path,
    ctx_workspace_id: str = "",
) -> Path:
    """三层校验 workspace_path 安全性

    Args:
        workspace_path: 待校验的工作区物理路径
        ctx_workspace_id: TrustedContext.workspace_id (用于一致性软校验)

    Returns:
        解析后的绝对路径

    Raises:
        SandboxSecurityError: 任一层校验失败
    """
    allowlist = _get_allowlist()

    # === 第 1 层: 白名单根目录 ===
    try:
        abs_path = workspace_path.resolve(strict=True)
    except FileNotFoundError:
        raise SandboxSecurityError(f"workspace_path 不存在: {workspace_path}")
    except OSError as e:
        raise SandboxSecurityError(f"workspace_path 解析失败: {workspace_path}: {e}")

    in_allowlist = False
    for allowed_root in allowlist:
        try:
            abs_path.relative_to(allowed_root)
            in_allowlist = True
            break
        except ValueError:
            continue

    if not in_allowlist:
        raise SandboxSecurityError(
            f"workspace_path 越界: {abs_path} 不在白名单中",
            details={"path": str(abs_path), "allowlist": [str(p) for p in allowlist]},
        )

    # === 第 2 层: 符号链接解析后仍在白名单内 ===
    # resolve(strict=True) 已解析符号链接, 再检查父链
    current = abs_path
    for _ in range(40):  # Linux PATH_MAX = 4096, 40 层足够
        if current in allowlist:
            break
        parent = current.parent
        if parent == current:
            raise SandboxSecurityError(f"路径解析超出文件系统根: {abs_path}")
        current = parent
    else:
        raise SandboxSecurityError(f"路径层级过深, 可能存在逃逸: {abs_path}")

    # === 第 3 层: 进程级访问权限 ===
    try:
        if not os.access(abs_path, os.R_OK | os.X_OK, effective_ids=True):
            raise SandboxSecurityError(
                f"当前进程无访问权限: {abs_path} (uid={os.geteuid()})",
            )
    except OSError as e:
        raise SandboxSecurityError(f"权限检查失败: {abs_path}: {e}")

    # === 第 4 层: workspace_id 与路径一致性 (软校验) ===
    if ctx_workspace_id:
        expected_id = hashlib.sha256(str(abs_path).encode()).hexdigest()[:16]
        if str(ctx_workspace_id) != expected_id and not ctx_workspace_id.startswith("user-"):
            logger.warning(
                "[PATH_VALIDATOR] workspace_id 与路径哈希不一致: id=%s hash=%s (软警告, 不阻断)",
                ctx_workspace_id,
                expected_id,
            )

    return abs_path
