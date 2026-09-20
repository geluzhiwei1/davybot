# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""命令读写分类器 (§沙箱系统升级 v2 — N3)

用途:
- 将命令分类为 READ_ONLY / WRITE / UNKNOWN
- ro 挂载模式下, WRITE 命令提前失败并给出友好错误信息
- 不替代白名单 (command_whitelist.py), 仅用于 ro/rw 沙箱路由决策

设计原则:
- 保守策略: UNKNOWN → WRITE (宁可误判为写, 不可漏判)
- 不处理 DANGEROUS 命令 (rm -rf / curl|sh 等), 由既有白名单拦截
"""

from __future__ import annotations

import re
from enum import Enum, StrEnum


class CommandRisk(StrEnum):
    """命令风险分类"""

    READ_ONLY = "read_only"  # 只读命令 (ls, cat, grep, git status)
    WRITE = "write"  # 写入命令 (rm, mv, pip install, git commit)
    UNKNOWN = "unknown"  # 未知 → 保守视为 WRITE


# ================================================================
# 命令模式定义
# ================================================================

# 只读命令前缀 (精确匹配命令名)
READ_ONLY_COMMANDS = frozenset(
    {
        "ls",
        "cat",
        "head",
        "tail",
        "less",
        "more",
        "grep",
        "rg",
        "ag",
        "find",
        "tree",
        "stat",
        "wc",
        "diff",
        "file",
        "which",
        "echo",
        "pwd",
        "type",
        "alias",
        "history",
        "env",
        "printenv",
        "du",
        "df",
        "free",
        "top",
        "ps",
        "lsof",
        "who",
        "whoami",
        "id",
        "uname",
        "hostname",
        "date",
        "cal",
        "uptime",
        # git 只读操作
        "git status",
        "git log",
        "git diff",
        "git show",
        "git branch",
        "git remote",
        "git tag",
        "git stash list",
        "git blame",
        # 包管理器查询
        "npm list",
        "npm ls",
        "npm outdated",
        "pip list",
        "pip show",
        "pip freeze",
        "pnpm list",
        "pnpm why",
        # 测试 / lint (不修改源码)
        "pytest --collect-only",
        "ruff check",
        "mypy",
    }
)

# 写入命令前缀
WRITE_COMMANDS = frozenset(
    {
        # 文件操作
        "rm",
        "mv",
        "cp",
        "mkdir",
        "rmdir",
        "touch",
        "chmod",
        "chown",
        "ln",
        "truncate",
        "dd",
        "tar",
        "zip",
        "unzip",
        "gzip",
        "gunzip",
        # 重定向写入 (echo > / echo >> / tee)
        "tee",
        # 包安装
        "npm install",
        "npm i ",
        "npm ci",
        "npm uninstall",
        "npm rm ",
        "pip install",
        "pip uninstall",
        "pip download",
        "pnpm install",
        "pnpm add",
        "pnpm remove",
        "pnpm update",
        "uv pip install",
        "uv pip uninstall",
        # git 写入操作
        "git commit",
        "git push",
        "git checkout",
        "git reset",
        "git clean",
        "git merge",
        "git rebase",
        "git cherry-pick",
        "git stash",
        "git add",
        "git rm",
        "git mv",
        "git init",
        "git clone",
        # 编辑器 / sed 写入
        "sed -i",
        "awk -i",
        # 编译 / 构建
        "make",
        "cmake",
        "gcc",
        "g++",
        "rustc",
        "cargo build",
        "cargo install",
        # 网络写入 (curl/wget 下载到本地)
        "curl",
        "wget",
    }
)

# 重定向写入模式 (echo > file, printf >> file 等)
_REDIRECT_PATTERN = re.compile(
    r"^(echo|printf|cat)\s.*?>>?\s",
    re.IGNORECASE,
)

# 管道写入模式 (echo xxx | tee, echo xxx | sudo tee)
_PIPE_WRITE_PATTERN = re.compile(
    r">\s*(/|\.|\~)",
    re.IGNORECASE,
)


def classify_command(command: str) -> CommandRisk:
    """将命令分类为 READ_ONLY / WRITE / UNKNOWN

    Args:
        command: 命令字符串

    Returns:
        CommandRisk 枚举值

    分类逻辑:
        1. 检查重定向写入模式 (echo > file)
        2. 匹配 WRITE_COMMANDS 前缀
        3. 匹配 READ_ONLY_COMMANDS 前缀
        4. 默认 UNKNOWN (保守视为 WRITE)

    注意:
        - 此分类器不替代白名单, 仅用于 ro/rw 沙箱路由决策
        - UNKNOWN 视为 WRITE, 宁可误拦不漏放
    """
    if not command or not command.strip():
        return CommandRisk.UNKNOWN

    cmd_normalized = command.strip()

    # 1. 检查重定向写入模式 (echo > / printf >> )
    if _REDIRECT_PATTERN.match(cmd_normalized):
        return CommandRisk.WRITE
    if _PIPE_WRITE_PATTERN.search(cmd_normalized):
        return CommandRisk.WRITE
    # 检查 > 或 >> 重定向操作符
    if ">>" in cmd_normalized or (">" in cmd_normalized and "2>" not in cmd_normalized.split(">")[0]):
        # 排除 2> / &> (stderr 重定向) 中的误判
        # 简单检查: 如果 > 前面不是 2 或 &, 则视为写入
        gt_pos = cmd_normalized.find(">")
        if gt_pos > 0:
            prefix = cmd_normalized[gt_pos - 1]
            if prefix not in ("2", "&", "="):
                return CommandRisk.WRITE

    cmd_lower = cmd_normalized.lower()

    # 2. 匹配 WRITE_COMMANDS
    for write_pattern in WRITE_COMMANDS:
        if cmd_lower.startswith(write_pattern):
            return CommandRisk.WRITE

    # 3. 匹配 READ_ONLY_COMMANDS
    for read_pattern in READ_ONLY_COMMANDS:
        if cmd_lower.startswith(read_pattern):
            return CommandRisk.READ_ONLY

    # 4. 默认 UNKNOWN (保守视为 WRITE)
    return CommandRisk.UNKNOWN
