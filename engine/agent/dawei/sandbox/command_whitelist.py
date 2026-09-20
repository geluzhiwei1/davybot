# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""命令白名单 - 验证和限制可执行的命令

该模块提供命令白名单验证功能，包括：
- 允许的安全命令及其参数限制（可从 JSON 配置文件加载）
- 危险命令黑名单
- 参数数量和flag验证
- Git子命令限制

配置文件路径: ~/.normnomos/command_whitelist.json

使用示例:
    from dawei.sandbox.command_whitelist import CommandWhitelist

    # 加载配置（可选，会话级调用一次）
    CommandWhitelist.load_from_config()

    is_valid, error_msg = CommandWhitelist.validate_command("ls -la")
    if is_valid:
        print("命令允许执行")

    # 获取所有允许的命令名
    allowed = CommandWhitelist.list_allowed_commands()
"""

import json
import re
import shlex
from pathlib import Path
from typing import Any, Dict, List, ClassVar

from dawei import get_dawei_home


# ============================================================================
# Hardcoded Defaults (fallback when no config file exists)
# ============================================================================

_DEFAULT_ALLOWED_COMMANDS: ClassVar[Dict[str, Dict[str, Any]]] = {
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
            "-i", "-v", "-r", "-n", "-c", "-l", "-w", "-x",
            "--include", "--exclude", "--exclude-dir",
        ],
        "description": "搜索文本",
    },
    "find": {
        "max_args": 10,
        "allowed_flags": [
            "-name", "-type", "-maxdepth", "-mindepth", "-size",
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
    "git": {
        "max_args": 20,
        "allowed_subcommands": [
            "status", "log", "diff", "show", "branch", "remote",
            "config", "help", "version",
        ],
        "description": "Git操作",
    },
    "python": {
        "max_args": 50,
        "allowed_flags": ["-V", "--version", "-c", "-m", "-u", "-B", "-O", "-q", "-s", "-E", "-I", "-W"],
        "description": "Python 解释器（脚本/模块运行；脚本位置参数本已放行，-c/-m 不扩大能力面）",
    },
    "python3": {
        "max_args": 50,
        "allowed_flags": ["-V", "--version", "-c", "-m", "-u", "-B", "-O", "-q", "-s", "-E", "-I", "-W"],
        "description": "Python3 解释器（脚本/模块运行；脚本位置参数本已放行，-c/-m 不扩大能力面）",
    },
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
        "allowed_flags": ["-n", "-e"],
        "description": "流编辑器",
    },
    "awk": {"max_args": 10, "description": "文本处理"},
    "where": {"max_args": 5, "description": "查找命令位置(Windows)"},
    "which": {"max_args": 5, "description": "查找命令位置(Unix)"},
    "uv": {
        "max_args": 20,
        "allowed_flags": [
            "--version", "-V", "pip", "sync", "add", "remove",
            "init", "venv", "lock", "tree", "cache",
        ],
        "description": "Python 包管理器（安全子命令）",
    },
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
    "tar": {
        "max_args": 10,
        "allowed_flags": ["-c", "-x", "-t", "-v", "-f", "-z"],
        "description": "打包工具",
    },
    "unzip": {
        "max_args": 10,
        "allowed_flags": ["-l", "-t", "-o", "-n", "-q", "-v", "-d"],
        "description": "ZIP 解压工具（E2E 94b38bde：子任务解压被白名单拦截）",
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
    "curl": {
        "max_args": 10,
        "allowed_flags": ["-I", "-i", "-s", "-o", "-L", "-H", "--max-time"],
        "description": "HTTP请求（只读；-L 跟随重定向、-H 加请求头、--max-time 限时，均不扩大写能力）",
    },
    "wget": {
        "max_args": 10,
        "allowed_flags": ["-O", "-q", "-S"],
        "description": "HTTP下载（只读）",
    },
}

_DEFAULT_DANGEROUS_COMMANDS: ClassVar[set[str]] = {
    "nc", "ncat", "telnet", "socat", "ssh", "scp", "ftp", "tftp",
}

_DEFAULT_DANGEROUS_PATTERNS: ClassVar[list[str]] = [
    r">\s*/\s*dev\s*/\s*[a-z]",
    r":\s*\{\s*:\s*\|\s*:&\s*\}\s*;",
    r"rm\s+-rf\s+/",
    r"chmod\s+000\s+/",
    r"dd\s+if=/dev/zero",
    r"mkfs\.",
    r"curl\s+.*\|.*sh",
    r"wget\s+.*\|.*sh",
    r"eval\s+\$",
    r"exec\s+[0-9]",
]


class CommandWhitelist:
    """命令白名单管理器

    支持从 JSON 配置文件加载系统白名单，配置文件路径为:
    ~/.normnomos/command_whitelist.json

    配置格式:
    {
        "version": 1,
        "allowed_commands": {
            "ls": {
                "max_args": 10,
                "allowed_flags": ["-a", "-l"],
                "allowed_subcommands": null,
                "description": "List directory"
            }
        },
        "dangerous_commands": ["nc", "telnet"],
        "dangerous_patterns": ["rm\\s+-rf\\s+/"]
    }
    """

    # 运行时配置（从 JSON 加载或保持默认值）
    _config: ClassVar[Dict[str, Any]] = {
        "version": 1,
        "allowed_commands": _DEFAULT_ALLOWED_COMMANDS,
        "dangerous_commands": list(_DEFAULT_DANGEROUS_COMMANDS),
        "dangerous_patterns": _DEFAULT_DANGEROUS_PATTERNS,
    }
    _loaded: ClassVar[bool] = False

    @classmethod
    def load_from_config(cls, config_path: Path | str | None = None) -> bool:
        """从 JSON 配置文件加载白名单配置

        Args:
            config_path: 配置文件路径，默认为 ~/.normnomos/command_whitelist.json

        Returns:
            True if loaded successfully, False if fell back to defaults
        """
        if config_path is None:
            config_path = get_dawei_home() / "command_whitelist.json"
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            import logging
            logging.getLogger(__name__).debug(
                f"Command whitelist config not found at {config_path}, using defaults"
            )
            cls._config = {
                "version": 1,
                "allowed_commands": _DEFAULT_ALLOWED_COMMANDS,
                "dangerous_commands": list(_DEFAULT_DANGEROUS_COMMANDS),
                "dangerous_patterns": _DEFAULT_DANGEROUS_PATTERNS,
            }
            cls._loaded = True
            return False

        try:
            with config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            # Validate basic structure
            if not isinstance(data.get("allowed_commands"), dict):
                raise ValueError("allowed_commands must be a dict")

            cls._config = {
                "version": data.get("version", 1),
                "allowed_commands": data.get("allowed_commands", _DEFAULT_ALLOWED_COMMANDS),
                "dangerous_commands": data.get(
                    "dangerous_commands", list(_DEFAULT_DANGEROUS_COMMANDS)
                ),
                "dangerous_patterns": data.get(
                    "dangerous_patterns", _DEFAULT_DANGEROUS_PATTERNS
                ),
            }
            cls._loaded = True
            import logging
            logging.getLogger(__name__).info(
                f"Command whitelist loaded from {config_path}, "
                f"{len(cls._config['allowed_commands'])} commands configured"
            )
            return True
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Failed to load command whitelist config: {e}, using defaults"
            )
            cls._config = {
                "version": 1,
                "allowed_commands": _DEFAULT_ALLOWED_COMMANDS,
                "dangerous_commands": list(_DEFAULT_DANGEROUS_COMMANDS),
                "dangerous_patterns": _DEFAULT_DANGEROUS_PATTERNS,
            }
            cls._loaded = True
            return False

    @classmethod
    def save_to_config(cls, config_path: Path | str | None = None) -> bool:
        """保存当前白名单配置到 JSON 文件

        Args:
            config_path: 配置文件路径，默认为 ~/.normnomos/command_whitelist.json

        Returns:
            True if saved successfully
        """
        if config_path is None:
            config_path = get_dawei_home() / "command_whitelist.json"
        else:
            config_path = Path(config_path)

        config_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with config_path.open("w", encoding="utf-8") as f:
                json.dump(cls._config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to save command whitelist config: {e}")
            return False

    @classmethod
    def get_all_commands(cls) -> Dict[str, Dict[str, Any]]:
        """返回所有配置允许的命令及其配置（用于前端展示）"""
        return dict(cls._config.get("allowed_commands", {}))

    @classmethod
    def list_allowed_commands(cls) -> List[str]:
        """列出所有允许的命令名"""
        return sorted(cls._config.get("allowed_commands", {}).keys())

    @classmethod
    def list_dangerous_commands(cls) -> List[str]:
        """列出所有危险命令"""
        return sorted(cls._config.get("dangerous_commands", []))

    @classmethod
    def get_dangerous_patterns(cls) -> List[str]:
        """列出所有危险模式正则"""
        return list(cls._config.get("dangerous_patterns", []))

    @classmethod
    def get_command_info(cls, command_name: str) -> Dict[str, Any]:
        """获取命令配置信息"""
        return cls._config.get("allowed_commands", {}).get(command_name, {})

    @classmethod
    def validate_command(cls, command: str) -> tuple[bool, str]:
        """验证命令是否在白名单中

        Args:
            command: 要验证的命令字符串

        Returns:
            (is_valid, error_message)
        """
        try:
            parts = shlex.split(command)

            if not parts:
                return False, "空命令"

            cmd_name = parts[0]

            # 检查后台执行
            if command.strip().endswith("&"):
                return False, "不允许后台执行(&)"

            # 检查管道命令
            if "|" in command:
                return False, "暂不支持管道命令(|)"

            # 检查命令替换
            if "$(" in command or "`" in command:
                return False, "不允许命令替换"

            # 检查危险模式
            dangerous_patterns = cls._config.get("dangerous_patterns", _DEFAULT_DANGEROUS_PATTERNS)
            for pattern in dangerous_patterns:
                if re.search(pattern, command):
                    return False, f"命令包含危险模式: {pattern}"

            # 检查黑名单
            dangerous_commands = set(
                cls._config.get("dangerous_commands", _DEFAULT_DANGEROUS_COMMANDS)
            )
            if cmd_name in dangerous_commands:
                return False, f"命令 '{cmd_name}' 在黑名单中（危险命令）"

            # 检查白名单
            allowed_commands = cls._config.get("allowed_commands", _DEFAULT_ALLOWED_COMMANDS)
            if cmd_name not in allowed_commands:
                return False, f"命令 '{cmd_name}' 不在白名单中"

            # 检查参数数量
            config = allowed_commands[cmd_name]
            max_args = config.get("max_args", 10)
            if len(parts) - 1 > max_args:
                return (
                    False,
                    f"参数过多（最多 {max_args} 个，实际 {len(parts) - 1} 个）",
                )

            # 检查flag
            allowed_flags = config.get("allowed_flags", [])
            if allowed_flags:
                for part in parts[1:]:
                    if part.startswith("-"):
                        if part.startswith("--"):
                            flag_base = part.split("=")[0]
                            if flag_base not in allowed_flags:
                                return False, f"Flag '{part}' 不在允许列表中"
                        else:
                            flag_content = part[1:]
                            if len(flag_content) > 1 and "-" not in flag_content:
                                if part in allowed_flags:
                                    continue
                                for char in flag_content:
                                    short_flag = f"-{char}"
                                    if short_flag not in allowed_flags:
                                        return (
                                            False,
                                            f"Flag '{short_flag}' 不在允许列表中",
                                        )
                            elif part not in allowed_flags:
                                return False, f"Flag '{part}' 不在允许列表中"

            # 检查git子命令
            if cmd_name == "git" and len(parts) > 1:
                git_subcommand = parts[1]
                allowed_subcommands = config.get("allowed_subcommands", [])
                if allowed_subcommands and git_subcommand not in allowed_subcommands:
                    return (
                        False,
                        f"Git子命令 '{git_subcommand}' 不允许（允许: {', '.join(allowed_subcommands)}）",
                    )

            # 检查管道命令
            if "|" in command:
                return False, "暂不支持管道命令(|)"

            # 检查命令替换
            if "$(" in command or "`" in command:
                return False, "不允许命令替换"

            # 检查后台执行
            if "&" in command and command.strip().endswith("&"):
                return False, "不允许后台执行"

            return True, ""

        except ValueError as e:
            return False, f"命令解析错误: {e!s}"
        except re.error as e:
            return False, f"正则表达式错误: {e!s}"
        except (AttributeError, TypeError) as e:
            return False, f"输入验证错误: {e!s}"

