# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""modes.yaml 批量剥离 groups/aliases 字段（一次性，幂等）

project/docs/mode工具解耦方案.md §5.2：mode-工具解耦后 ModeConfig 不再
有 groups/aliases 语义（D2/D3），加载端仅对残留字段告警。本脚本把
market 源 / 工作区已装副本 / builtin 的 modes.yaml 中残留的
`groups:` / `aliases:` 块整体删除（文本级处理，保留其余格式与注释）。

幂等：剥离后再运行无匹配行 → 零变更。

用法（agent/ 目录下）：
    uv run python scripts/strip_mode_groups.py --dry-run
    uv run python scripts/strip_mode_groups.py            # 落盘
    uv run python scripts/strip_mode_groups.py --root /path/to/dir
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# 键行：`groups:` / `aliases:`（可带行内注释或行内列表）
_KEY_LINE = re.compile(r"^(?P<indent>\s*)(?P<key>groups|aliases)\s*:\s*(?P<rest>.*)$")

AGENT_REPO = Path(__file__).resolve().parents[1]

DEFAULT_ROOTS = [
    AGENT_REPO / "dawei" / "mode" / "builtin",  # builtin 框架模式（2 个）
]


def strip_text(text: str) -> tuple[str, int]:
    """删除 groups:/aliases: 键及其列表块，返回 (新文本, 删除键数)。"""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    removed = 0
    i = 0
    while i < len(lines):
        m = _KEY_LINE.match(lines[i].rstrip("\n"))
        if not m:
            out.append(lines[i])
            i += 1
            continue
        removed += 1
        rest = m.group("rest").strip()
        # 行内形式（groups: [a, b] 或 groups: ""）或注释 → 单行删除
        if rest and not rest.startswith("#"):
            i += 1
            continue
        # 块形式：吞掉后续更深缩进的行 + 同缩进的序列项（YAML 允许 seq 项与
        # mapping key 同缩进——2026-09-19 审查实锤：ip-team/patent-team 用该
        # 风格，只吞更深缩进会留下孤儿 `- read` 项把文件打坏）
        key_indent = len(m.group("indent"))
        i += 1
        while i < len(lines):
            raw = lines[i].rstrip("\n")
            if not raw.strip():  # 块内空行 → 删（避免悬空空行堆积）
                i += 1
                continue
            line_indent = len(raw) - len(raw.lstrip())
            if line_indent > key_indent:
                i += 1
                continue
            if line_indent == key_indent and raw.lstrip().startswith("- "):
                i += 1
                continue
            break
    return "".join(out), removed


def strip_file(path: Path, dry: bool) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"WARN skip unreadable {path}: {e}")
        return 0
    new_text, removed = strip_text(text)
    if removed and not dry:
        # 解析护栏：剥离后必须仍是合法 YAML，否则放弃落盘（审查教训：
        # 同缩进序列曾产出孤儿列表项打坏 patent-team/modes.yaml）
        try:
            import yaml

            yaml.safe_load(new_text)
        except ImportError:
            pass  # 无 pyyaml 环境跳过护栏（仅告警降级）
        except Exception as e:  # noqa: BLE001
            print(f"WARN parse guard failed, NOT writing {path}: {e}")
            return 0
        path.write_text(new_text, encoding="utf-8")
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="modes.yaml 批量剥离 groups/aliases（幂等）")
    parser.add_argument("--root", action="append", default=None, help="待扫描目录（可多次指定；缺省 = builtin + market 源 + 工作区树）")
    parser.add_argument(
        "--market-root",
        action="append",
        default=None,
        help="market 源目录（可多次指定；缺省取 MARKET_RESOURCES_ROOT env，两者皆无则跳过。E4: 不再内置绝对路径）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只统计，不落盘")
    args = parser.parse_args()

    market_roots = (
        [Path(r).expanduser() for r in (args.market_root or [])]
        or (
            [Path(os.environ["MARKET_RESOURCES_ROOT"]).expanduser()]
            if os.environ.get("MARKET_RESOURCES_ROOT")
            else []
        )
    )
    roots = (
        [Path(r).expanduser() for r in args.root]
        if args.root
        else DEFAULT_ROOTS
        + market_roots
        + [
            # 工作区已安装副本（~/.normnomos/web_workspaces/**/.dawei/agents/*/modes.yaml）
            Path.home() / ".normnomos" / "web_workspaces",
        ]
    )

    total_files = total_keys = 0
    for root in roots:
        if not root.is_dir():
            print(f"WARN root not found: {root}")
            continue
        for path in sorted(root.glob("**/modes.yaml")):
            if not path.is_file():
                continue
            n = strip_file(path, args.dry_run)
            if n:
                total_files += 1
                total_keys += n
                print(f"{'DRY ' if args.dry_run else ''}{path}: removed {n} key(s)")
    print(f"done: {total_files} file(s), {total_keys} key(s){'' if args.dry_run else ' (written)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
