# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""命令白名单 - 验证和限制可执行的命令

该模块提供命令白名单验证功能，包括：
- 允许的安全命令及其参数限制
- 危险命令黑名单
- 参数数量和flag验证
- Git子命令限制

使用示例:
    from dawei.sandbox.command_whitelist import CommandWhitelist

    is_valid, error_msg = CommandWhitelist.validate_command("ls -la")
    if is_valid:
        print("命令允许执行")
    else:
        print(f"命令被拒绝: {error_msg}")
"""

import re
import shlex
from typing import ClassVar


class CommandWhitelist:
    """命令白名单管理器"""

    # 允许的命令及其配置
    ALLOWED_COMMANDS: ClassVar[dict[str, dict[str, any]]] = {
        # 文件操作
        "ls": {
            "max_args": 10,
            "allowed_flags": ["-a", "-l", "-h", "-F", "-R", "-t", "-r", "-S"],
            "description": "列出文件",
        },
        "pwd": {"max_args": 0, "allowed_flags": [], "description": "显示当前目录"},
        "cat": {
            "max_args": 5,
            "allowed_flags": ["-n", "-b", "-s", "-A"],
            "description": "显示文件内容",
        },
        "head": {
            "max_args": 10,
            "allowed_flags": ["-n", "-c", "-q", "-v"],
            "description": "显示文件开头",
        },
        "tail": {
            "max_args": 10,
            "allowed_flags": ["-n", "-c", "-f", "-q", "-v"],
            "description": "显示文件结尾",
        },
        "grep": {
            "max_args": 10,
            "allowed_flags": [
                "-i",
                "-v",
                "-r",
                "-n",
                "-c",
                "-l",
                "-w",
                "-x",
                "--include",
                "--exclude",
                "--exclude-dir",
            ],
            "description": "搜索文本",
        },
        "find": {
            "max_args": 10,
            "allowed_flags": [
                "-name",
                "-type",
                "-maxdepth",
                "-mindepth",
                "-size",
                "-delete",
                "-exec",
            ],
            "description": "查找文件",
        },
        "wc": {
            "max_args": 10,
            "allowed_flags": ["-l", "-w", "-c", "-m", "-L"],
            "description": "统计行数",
        },
        "diff": {
            "max_args": 10,
            "allowed_flags": ["-u", "-r", "-q", "-y"],
            "description": "文件比较",
        },
        # Git操作
        "git": {
            "max_args": 20,
            "allowed_subcommands": [
                "status",
                "log",
                "diff",
                "show",
                "branch",
                "remote",
                "config",
                "help",
                "version",
            ],
            "description": "Git操作",
        },
        # Python
        "python": {
            "max_args": 10,
            "allowed_flags": ["-c", "-m", "-V"],
            "description": "执行Python脚本",
        },
        "python3": {
            "max_args": 10,
            "allowed_flags": ["-c", "-m", "-V"],
            "description": "执行Python3脚本",
        },
        # 文本处理
        "echo": {
            "max_args": 20,
            "allowed_flags": ["-n", "-e"],
            "description": "输出文本",
        },
        "sort": {
            "max_args": 10,
            "allowed_flags": ["-r", "-n", "-u", "-k", "-t"],
            "description": "排序",
        },
        "uniq": {
            "max_args": 5,
            "allowed_flags": ["-c", "-d", "-u"],
            "description": "去重",
        },
        "sed": {
            "max_args": 10,
            "allowed_flags": ["-n", "-e", "-i"],
            "description": "流编辑器",
        },
        "awk": {"max_args": 10, "description": "文本处理"},
        # 系统信息
        "df": {
            "max_args": 5,
            "allowed_flags": ["-h", "-H", "-i", "-T"],
            "description": "磁盘使用",
        },
        "du": {
            "max_args": 10,
            "allowed_flags": ["-h", "-s", "-d", "-c"],
            "description": "目录大小",
        },
        "date": {
            "max_args": 5,
            "allowed_flags": ["-d", "-r"],
            "description": "显示日期",
        },
        "uname": {
            "max_args": 5,
            "allowed_flags": ["-a", "-r", "-s", "-n"],
            "description": "系统信息",
        },
        "whoami": {"max_args": 0, "description": "当前用户"},
        "id": {
            "max_args": 5,
            "allowed_flags": ["-u", "-g", "-G"],
            "description": "用户ID",
        },
        "sleep": {"max_args": 1, "description": "延迟命令"},
        # 压缩/解压
        "tar": {
            "max_args": 10,
            "allowed_flags": ["-c", "-x", "-t", "-v", "-f", "-z"],
            "description": "打包工具",
        },
        "gzip": {
            "max_args": 5,
            "allowed_flags": ["-d", "-k", "-v"],
            "description": "gzip压缩",
        },
        "gunzip": {
            "max_args": 5,
            "allowed_flags": ["-k", "-v"],
            "description": "gzip解压",
        },
        # 网络（只读）
        "curl": {
            "max_args": 10,
            "allowed_flags": ["-I", "-i", "-s", "-o"],
            "description": "HTTP请求（只读）",
        },
        "wget": {
            "max_args": 10,
            "allowed_flags": ["-O", "-q", "-S"],
            "description": "HTTP下载（只读）",
        },
    }

    # 危险命令黑名单
    DANGEROUS_COMMANDS: ClassVar[set[str]] = {
        "rm",
        "rmdir",
        "del",
        "delete",
        "erase",
        "dd",
        "mkfs",
        "fdisk",
        "parted",
        "sudo",
        "su",
        "doas",
        "pkexec",
        "nc",
        "netcat",
        "nmap",
        "tcpdump",
        "useradd",
        "usermod",
        "userdel",
        "chmod",
        "chown",
        "chgrp",
        "iptables",
        "ufw",
        "firewall-cmd",
        "systemctl",
        "service",
        "initctl",
        "apt",
        "apt-get",
        "yum",
        "dnf",
        "pacman",
        "apk",
        "pip",
        "pip3",
        "npm",
        "yarn",
        "kill",
        "killall",
        "pkill",
        "reboot",
        "shutdown",
        "halt",
        "crontab",
        "at",
        "batch",
        "mount",
        "umount",
        "passwd",
        "chpasswd",
        "ssh",
        "scp",
        "rsync",
        "sftp",
        "vi",
        "vim",
        "nano",
        "emacs",  # 交互式命令
        "top",
        "htop",
        "less",
        "more",  # 交互式命令
        "man",
        "info",  # 文档浏览（交互式）
        "bash",
        "sh",
        "zsh",
        "fish",
        "csh",
        "tcsh",  # 直接启动shell
        ":(){ :|:& };:",  # Fork bomb
    }

    # 危险模式（正则表达式）
    DANGEROUS_PATTERNS = [
        r">\s*/\s*dev\s*/\s*[a-z]",  # 重定向到设备文件
        r":\s*\{\s*:\s*\|\s*:&\s*\}\s*;",  # Fork bomb
        r"rm\s+-rf\s+/",  # 删除根目录
        r"chmod\s+000\s+/",  # 破坏系统权限
        r"dd\s+if=/dev/zero",  # 磁盘破坏
        r"mkfs\.",  # 文件系统格式化
        r"curl\s+.*\|.*sh",  # 下载并执行脚本
        r"wget\s+.*\|.*sh",  # 下载并执行脚本
        r"eval\s+\$",  # eval注入
        r"exec\s+[0-9]",  # exec重定向
    ]

    @classmethod
    def validate_command(cls, command: str) -> tuple[bool, str]:
        """验证命令是否在白名单中

        Args:
            command: 要验证的命令字符串

        Returns:
            (is_valid, error_message)

        """
        try:
            # 1. 使用shlex正确解析命令
            parts = shlex.split(command)

            if not parts:
                return False, "空命令"

            cmd_name = parts[0]

            # 2. 检查后台执行（在参数计数之前）
            if command.strip().endswith("&"):
                return False, "不允许后台执行(&)"

            # 3. 检查管道命令（pipe）
            if "|" in command:
                return False, "暂不支持管道命令(|)"

            # 4. 检查命令替换
            if "$(" in command or "`" in command:
                return False, "不允许命令替换"

            # 5. 检查危险模式
            for pattern in cls.DANGEROUS_PATTERNS:
                if re.search(pattern, command):
                    return False, f"命令包含危险模式: {pattern}"

            # 6. 检查黑名单
            if cmd_name in cls.DANGEROUS_COMMANDS:
                return False, f"命令 '{cmd_name}' 在黑名单中（危险命令）"

            # 7. 检查白名单
            if cmd_name not in cls.ALLOWED_COMMANDS:
                return False, f"命令 '{cmd_name}' 不在白名单中"

            # 8. 检查参数数量
            config = cls.ALLOWED_COMMANDS[cmd_name]
            max_args = config.get("max_args", 10)
            if len(parts) - 1 > max_args:
                return (
                    False,
                    f"参数过多（最多 {max_args} 个，实际 {len(parts) - 1} 个）",
                )

            # 9. 检查flag（如果有）
            allowed_flags = config.get("allowed_flags", [])
            if allowed_flags:
                for part in parts[1:]:
                    # 检查是否是flag（以-开头）
                    if part.startswith("-"):
                        # 如果是--开头的长flag（如 --help）
                        if part.startswith("--"):
                            # 检查整个flag或带=的flag
                            flag_base = part.split("=")[0]
                            if flag_base not in allowed_flags:
                                return False, f"Flag '{part}' 不在允许列表中"
                        else:
                            # -开头的flag
                            # 判断是短flag组合（如 -la）还是长flag（如 -name）
                            flag_content = part[1:]  # 去掉-

                            # 如果flag内容长度 > 1 且不包含其他-，可能是长flag（如 -name）
                            # 或者是短flag组合（如 -la）
                            if len(flag_content) > 1 and "-" not in flag_content:
                                # 可能是 -name 这样的长flag
                                if part in allowed_flags:
                                    # 直接匹配
                                    continue
                                # 尝试作为短flag组合处理（-la -> -l, -a）
                                for char in flag_content:
                                    short_flag = f"-{char}"
                                    if short_flag not in allowed_flags:
                                        # 如果拆分后不在允许列表，返回错误
                                        # 但如果整个flag在允许列表中，则通过（上面已经检查）
                                        return (
                                            False,
                                            f"Flag '{short_flag}' 不在允许列表中",
                                        )
                            # 单字符短flag（如 -n, -a）
                            elif part not in allowed_flags:
                                return False, f"Flag '{part}' 不在允许列表中"

            # 7. 检查git子命令
            if cmd_name == "git" and len(parts) > 1:
                git_subcommand = parts[1]
                allowed_subcommands = config.get("allowed_subcommands", [])
                if git_subcommand not in allowed_subcommands:
                    return (
                        False,
                        f"Git子命令 '{git_subcommand}' 不允许（允许: {', '.join(allowed_subcommands)}）",
                    )

            # 8. 检查管道命令（pipe）
            # 必须在危险模式检查之后，但也要独立检查
            if "|" in command:
                return False, "暂不支持管道命令(|)"

            # 9. 检查命令替换
            if "$(" in command or "`" in command:
                return False, "不允许命令替换"

            # 10. 检查后台执行
            if "&" in command and command.strip().endswith("&"):
                return False, "不允许后台执行"

            return True, ""

        except ValueError as e:
            # shlex.split raises ValueError for unbalanced quotes
            return False, f"命令解析错误: {e!s}"
        except re.error as e:
            # Regex pattern matching errors
            return False, f"正则表达式错误: {e!s}"
        except (AttributeError, TypeError) as e:
            # Input validation errors - wrong type passed to validation
            return False, f"输入验证错误: {e!s}"

    @classmethod
    def get_command_info(cls, command_name: str) -> dict[str, any]:
        """获取命令配置信息"""
        return cls.ALLOWED_COMMANDS.get(command_name, {})

    @classmethod
    def list_allowed_commands(cls) -> list[str]:
        """列出所有允许的命令"""
        return sorted(cls.ALLOWED_COMMANDS.keys())

    @classmethod
    def list_dangerous_commands(cls) -> list[str]:
        """列出所有危险命令"""
        return sorted(cls.DANGEROUS_COMMANDS)
