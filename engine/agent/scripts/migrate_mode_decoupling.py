# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""mode-工具解耦 数据迁移脚本（一次性，幂等，无须兼容）

project/docs/mode工具解耦方案.md §5.1/§5.3：
1. workspace.json：user_ui_context.current_mode / current_experts
   - 别名 → canonical slug（alias 映射从 builtin + 本工作区已装 modes.yaml 的
     原始 aliases 字段构建 —— 加载端已删除别名语义，映射只能取自 yaml 源）；
   - 未知 current_mode → 重置 "orchestrator"；
   - 未知 expert 条目 → 剔除（列表空且原非空 → ["orchestrator"]）。
2. tasks.json：递归归一字典键 "mode" 的别名引用（未知值不动 —— 运行期
   ModeNotFoundError FAST FAIL，见方案 §8，不静默改写任务数据）。
3. 历史对话中的 mode 引用不回填（展示层容忍，方案 §5.3）。

幂等性（方案 §7 验收 #6）：归一后的 canonical slug 不是 alias、也必在
registered 集合内 → 重复运行零变更。

用法（agent/ 目录下）：
    uv run python scripts/migrate_mode_decoupling.py --dry-run   # 演练
    uv run python scripts/migrate_mode_decoupling.py             # 落盘
    uv run python scripts/migrate_mode_decoupling.py --root /path/to/web_workspaces
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate_mode_decoupling")

DEFAULT_RESET_MODE = "orchestrator"
AGENT_REPO_ROOT = Path(__file__).resolve().parents[1]  # .../engine/agent


# ---------------------------------------------------------------- yaml 源读取


def _read_mode_entries(yaml_path: Path) -> list[dict]:
    """读单个 modes.yaml / .roomode(s) 的 customModes 原始条目（不做 ModeConfig 解析）。"""
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001 — 单文件损坏只告警，不中断全局迁移
        logger.warning("skip unreadable %s: %s", yaml_path, e)
        return []
    entries = data.get("customModes") if isinstance(data, dict) else None
    return [m for m in (entries or []) if isinstance(m, dict) and m.get("slug")]


def _collect_from_dir(root: Path) -> tuple[set[str], dict[str, str]]:
    """扫描 root 下 agents/*/modes.yaml、agents/modes.yaml 与 .roomode(s)，返回 (slugs, alias→canonical)。"""
    slugs: set[str] = set()
    alias_map: dict[str, str] = {}
    candidates: list[Path] = []
    if root.is_dir():
        candidates.extend(sorted(root.glob("agents/*/modes.yaml")))
        # builtin 布局是 agents/modes.yaml（无 agent 子目录）
        flat = root / "agents" / "modes.yaml"
        if flat.exists():
            candidates.append(flat)
        for name in (".roomode", ".roomodes"):
            p = root / name
            if p.exists():
                candidates.append(p)
    for path in candidates:
        for m in _read_mode_entries(path):
            slug = str(m["slug"]).strip()
            slugs.add(slug)
            raw = m.get("aliases") or []
            if isinstance(raw, str):
                raw = [raw]
            for a in raw:
                alias = str(a).strip()
                if not alias or alias == slug:
                    continue
                owner = alias_map.get(alias)
                if owner is not None and owner != slug:
                    logger.warning("alias conflict: '%s' claimed by '%s' and '%s' — keep '%s'", alias, owner, slug, owner)
                    continue
                alias_map[alias] = slug
    return slugs, alias_map


def build_builtin_tables() -> tuple[set[str], dict[str, str]]:
    """builtin modes（framework×2；随包分发，DAWEI_HOME 之外的事实源）。"""
    return _collect_from_dir(AGENT_REPO_ROOT / "dawei" / "mode" / "builtin")


# ---------------------------------------------------------------- 迁移逻辑


def _normalize_mode_value(value: str, slugs: set[str], alias_map: dict[str, str]) -> str | None:
    """返回归一后的 slug；None 表示无需变更。"""
    if value in slugs:
        return None
    canonical = alias_map.get(value)
    return canonical if canonical is not None else ""  # "" = 未知


def migrate_workspace_json(ws_json: Path, slugs: set[str], alias_map: dict[str, str], dry: bool) -> list[str]:
    """§5.1：current_mode / current_experts 归一。返回变更描述列表。"""
    try:
        data = json.loads(ws_json.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("skip unreadable %s: %s", ws_json, e)
        return []
    if not isinstance(data, dict):
        return []

    ctx = data.get("user_ui_context")
    if not isinstance(ctx, dict):
        return []

    changes: list[str] = []

    mode = ctx.get("current_mode")
    if isinstance(mode, str) and mode:
        normalized = _normalize_mode_value(mode, slugs, alias_map)
        if normalized == "":  # 未知 → 重置（方案 §5.1）
            ctx["current_mode"] = DEFAULT_RESET_MODE
            changes.append(f"current_mode: '{mode}' -> '{DEFAULT_RESET_MODE}' (unknown)")
        elif normalized:
            ctx["current_mode"] = normalized
            changes.append(f"current_mode: '{mode}' -> '{normalized}' (alias)")

    experts = ctx.get("current_experts")
    if isinstance(experts, list) and experts:
        had_entries = bool([e for e in experts if isinstance(e, str) and e])
        new_experts: list[str] = []
        for e in experts:
            if not (isinstance(e, str) and e):
                continue
            normalized = _normalize_mode_value(e, slugs, alias_map)
            if normalized == "":
                changes.append(f"current_experts: drop unknown '{e}'")
            elif normalized:
                new_experts.append(normalized)
                changes.append(f"current_experts: '{e}' -> '{normalized}' (alias)")
            else:
                new_experts.append(e)
        if had_entries and not new_experts:
            new_experts = [DEFAULT_RESET_MODE]
            changes.append(f"current_experts: reset to ['{DEFAULT_RESET_MODE}']")
        if new_experts != experts:
            ctx["current_experts"] = new_experts

    if changes and not dry:
        ws_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changes


def _walk_normalize_mode_keys(node, slugs: set[str], alias_map: dict[str, str], changes: list[str], path: str) -> None:
    """递归归一 dict 键 "mode" 的字符串值（仅 alias→canonical；未知不动）。"""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "mode" and isinstance(v, str) and v:
                normalized = _normalize_mode_value(v, slugs, alias_map)
                if normalized and normalized != "":
                    node[k] = normalized
                    changes.append(f"{path}.mode: '{v}' -> '{normalized}' (alias)")
            else:
                _walk_normalize_mode_keys(v, slugs, alias_map, changes, f"{path}.{k}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk_normalize_mode_keys(item, slugs, alias_map, changes, f"{path}[{i}]")


def migrate_tasks_json(tasks_json: Path, slugs: set[str], alias_map: dict[str, str], dry: bool) -> list[str]:
    """§5.3：TaskGraph 节点旧 slug 归一（未知值留待运行期 FAST FAIL）。"""
    try:
        data = json.loads(tasks_json.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("skip unreadable %s: %s", tasks_json, e)
        return []

    changes: list[str] = []
    _walk_normalize_mode_keys(data, slugs, alias_map, changes, "$")

    if changes and not dry:
        tasks_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description="mode-工具解耦 一次性数据迁移（幂等）")
    parser.add_argument(
        "--root",
        default=os.environ.get("DAWEI_HOME", str(Path.home() / ".normnomos")),
        help="工作区树根（默认 DAWEI_HOME 或 ~/.normnomos）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印将要发生的变更，不落盘")
    args = parser.parse_args()

    root = Path(args.root).expanduser()
    if not root.is_dir():
        logger.error("root not found: %s", root)
        return 2

    builtin_slugs, builtin_alias_map = build_builtin_tables()
    logger.info("builtin: %d slug(s), %d alias(es)", len(builtin_slugs), len(builtin_alias_map))

    # 实测布局：web_workspaces/<user>/<scope>/<ws-id>/.dawei（3 层通配）
    dawei_dirs = sorted(root.glob("web_workspaces/*/*/*/.dawei")) or sorted(root.glob("web_workspaces/*/.dawei"))
    # 兜底：root 本身就是含多个 workspace 的父目录时，扫两层 .dawei
    if not dawei_dirs:
        dawei_dirs = sorted(p.parent for p in root.glob("*/.dawei/workspace.json"))
    logger.info("found %d workspace(s) under %s%s", len(dawei_dirs), root, " (dry-run)" if args.dry_run else "")

    total_changes = 0
    for dawei_dir in dawei_dirs:
        ws_slugs, ws_alias_map = _collect_from_dir(dawei_dir)
        slugs = builtin_slugs | ws_slugs
        alias_map = {**builtin_alias_map, **ws_alias_map}

        ws_json = dawei_dir / "workspace.json"
        if ws_json.exists():
            changes = migrate_workspace_json(ws_json, slugs, alias_map, args.dry_run)
            for c in changes:
                logger.info("%s: %s", ws_json, c)
            total_changes += len(changes)

        tasks_json = dawei_dir / "tasks.json"
        if tasks_json.exists():
            changes = migrate_tasks_json(tasks_json, slugs, alias_map, args.dry_run)
            for c in changes:
                logger.info("%s: %s", tasks_json, c)
            total_changes += len(changes)

    logger.info("done: %d change(s)%s", total_changes, " (not written)" if args.dry_run else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
