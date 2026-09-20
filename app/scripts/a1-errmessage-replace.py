#!/usr/bin/env python3
"""A1 批量替换:err instanceof Error ? err.message : FALLBACK  →  apiErrorMessage(err) ?? FALLBACK

方向修正(可用性升级 v1.1 域 4.2/R1):翻译层优先,页面 i18n 兜底。
只替换条件与前支,不动 FALLBACK(可能是带插值的 t("x", {...}))。
"""
import re
import sys
from pathlib import Path

ROOTS = [Path("src/routes/normflow"), Path("src/routes/smart-firm")]
PAT = re.compile(r"(\w+)\s+instanceof\s+Error\s+\?\s+\1\.message\s+:")
IMPORT_LINE = 'import { apiErrorMessage } from "@/lib/api/errors";'

total = 0
files = 0
for root in ROOTS:
    for f in sorted(root.glob("*.tsx")):
        src = f.read_text(encoding="utf-8")
        new, n = PAT.subn(lambda m: f"apiErrorMessage({m.group(1)}) ??", src)
        if n == 0:
            continue
        if "apiErrorMessage" not in src:
            lines = new.split("\n")
            last_import = -1
            for i, line in enumerate(lines):
                if line.startswith("import ") or line.startswith("} from "):
                    last_import = i
            if last_import < 0:
                print(f"SKIP(no import block): {f}", file=sys.stderr)
                continue
            lines.insert(last_import + 1, IMPORT_LINE)
            new = "\n".join(lines)
        f.write_text(new, encoding="utf-8")
        total += n
        files += 1
        print(f"{f}: {n}")

print(f"---\nfiles={files} replacements={total}")
