# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Slash命令管理器 - 实现slash commands

支持3级优先级系统（从高到低）：
1. Workspace commands - {workspace}/.dawei/commands/
2. User commands - ~/.dawei/commands/
3. Built-in commands - 代码内置

命令文件格式（Markdown + Frontmatter）：
---
description: "命令描述"
argument-hint: "[可选参数]"
mode: code  # 可选：指定agent模式
---

命令内容（实际的操作步骤）
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dawei.config import get_workspaces_root

import frontmatter

logger = logging.getLogger(__name__)


@dataclass
class Command:
    """表示一个slash命令"""

    name: str
    content: str
    source: str  # "workspace", "user", "builtin"
    path: Path
    description: str | None = None
    argument_hint: str | None = None
    mode: str | None = None  # 指定agent模式

    def __hash__(self):
        return hash((self.name, self.source, self.path))

    def __eq__(self, other):
        if not isinstance(other, Command):
            return False
        return (self.name, self.source, self.path) == (
            other.name,
            other.source,
            other.path,
        )


class CommandManager:
    """Slash命令管理器

    负责发现、管理和加载slash命令
    """

    def __init__(self, workspace_root: Path | None = None, user_root: Path | None = None):
        """初始化CommandManager

        Args:
            workspace_root: 工作区根路径（最高优先级）
            user_root: 用户根路径（第二优先级，默认 ~/.dawei）

        """
        self.workspace_root = workspace_root
        self.user_root = user_root or Path(get_workspaces_root())

        # 命令注册表: name -> Command（高优先级覆盖低优先级）
        self._commands: dict[str, Command] = {}
        self._builtin_commands: dict[str, Command] = {}

        # 标记是否已扫描
        self._scanned = False

    def register_builtin_command(
        self,
        name: str,
        content: str,
        description: str | None = None,
        argument_hint: str | None = None,
        mode: str | None = None,
    ):
        """注册内置命令"""
        if not name or not name.strip():
            raise ValueError("Command name cannot be empty or None")
        if not content or not content.strip():
            raise ValueError("Command content cannot be empty or None")

        command = Command(
            name=name.strip(),
            content=content,
            source="builtin",
            path=Path("<builtin>"),
            description=description,
            argument_hint=argument_hint,
            mode=mode,
        )
        self._builtin_commands[command.name] = command
        logger.info(f"Registered builtin command: /{command.name}")

    def scan_commands(self, force: bool = False) -> dict[str, Command]:
        """扫描所有命令来源并返回合并后的命令列表

        优先级：workspace > user > builtin

        Args:
            force: 是否强制重新扫描

        Returns:
            合并后的命令字典

        """
        if self._scanned and not force:
            return self._commands

        # 从低到高加载，让高优先级覆盖低优先级
        self._commands.clear()

        # 1. 加载内置命令（最低优先级）
        self._commands.update(self._builtin_commands)
        logger.info(f"Loaded {len(self._builtin_commands)} builtin commands: {list(self._builtin_commands.keys())}")

        # 2. 加载用户命令（覆盖内置）
        user_commands = self._scan_directory(self.user_root / "commands", "user")
        for cmd in user_commands:
            self._commands[cmd.name] = cmd
        logger.info(f"Loaded {len(user_commands)} user commands")

        # 3. 加载工作区命令（最高优先级，覆盖所有）
        if self.workspace_root:
            workspace_commands = self._scan_directory(
                self.workspace_root / ".dawei" / "commands",
                "workspace",
            )
            for cmd in workspace_commands:
                self._commands[cmd.name] = cmd
            logger.info(f"Loaded {len(workspace_commands)} workspace commands")

        self._scanned = True
        logger.info(f"Total commands available: {len(self._commands)} - {list(self._commands.keys())}")

        return self._commands

    def _scan_directory(self, dir_path: Path, source: str) -> list[Command]:
        """扫描指定目录下的命令文件

        Args:
            dir_path: 目录路径
            source: 来源标识（"workspace", "user", "builtin"）

        Returns:
            命令列表

        """
        commands = []

        if not dir_path.exists() or not dir_path.is_dir():
            logger.debug(f"Command directory does not exist: {dir_path}")
            return commands

        try:
            # 扫描所有 .md 文件
            for file_path in dir_path.rglob("*.md"):
                try:
                    command = self._load_command_file(file_path, source)
                    if command:
                        commands.append(command)
                        logger.debug(f"Loaded command '{command.name}' from {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to load command from {file_path}: {e}")

        except Exception as e:
            logger.exception(f"Failed to scan command directory {dir_path}: {e}")

        return commands

    def _load_command_file(self, file_path: Path, source: str) -> Command | None:
        """从文件加载单个命令

        Args:
            file_path: 命令文件路径
            source: 来源标识

        Returns:
            Command对象或None

        """
        try:
            with Path(file_path).open(encoding="utf-8") as f:
                content = f.read()

            # 提取命令名称（文件名去掉.md扩展名）
            command_name = file_path.stem

            # 解析frontmatter
            description = None
            argument_hint = None
            mode = None
            command_content = content

            # 使用python-frontmatter库解析
            try:
                if not content or not content.strip():
                    logger.warning(f"Empty content in command file {file_path}")
                    return None
                post = frontmatter.loads(content)
                description = post.get("description")
                argument_hint = post.get("argument-hint")
                mode = post.get("mode")
                command_content = post.content
            except Exception as e:
                logger.debug(f"Failed to parse frontmatter with python-frontmatter: {e}")
                # 尝试手动解析
                description, argument_hint, mode, command_content = self._parse_frontmatter(content)

            return Command(
                name=command_name,
                content=command_content.strip(),
                source=source,
                path=file_path,
                description=description,
                argument_hint=argument_hint,
                mode=mode,
            )

        except Exception as e:
            logger.exception(f"Failed to load command file {file_path}: {e}")
            return None

    def _parse_frontmatter(self, content: str) -> tuple:
        """手动解析frontmatter（简单的YAML格式）

        Returns:
            (description, argument_hint, mode, content)

        """
        description = None
        argument_hint = None
        mode = None
        command_content = content

        if content.startswith("---"):
            # 找到第二个---
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter_text = parts[1]
                command_content = parts[2].strip()

                # 解析简单的key: value格式
                for line in frontmatter_text.split("\n"):
                    line = line.strip()
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip().lower()
                        value = value.strip().strip('"').strip("'")

                        if key == "description":
                            description = value
                        elif key == "argument-hint":
                            argument_hint = value
                        elif key == "mode":
                            mode = value

        return description, argument_hint, mode, command_content

    def get_command(self, name: str) -> Command | None:
        """获取指定名称的命令

        Args:
            name: 命令名称（不含/前缀）

        Returns:
            Command对象或None

        """
        # 确保已扫描
        if not self._scanned:
            self.scan_commands()

        # 支持带/和不带/的命令名
        command_name = name.lstrip("/")
        return self._commands.get(command_name)

    def get_all_commands(self) -> dict[str, Command]:
        """获取所有可用命令"""
        if not self._scanned:
            self.scan_commands()
        return self._commands.copy()

    def get_command_names(self) -> list[str]:
        """获取所有命令名称列表"""
        if not self._scanned:
            self.scan_commands()
        return sorted(self._commands.keys())

    def reload(self):
        """重新扫描命令目录"""
        self._scanned = False
        return self.scan_commands(force=True)

    def create_default_builtin_commands(self):
        """创建默认的内置命令"""
        builtin_commands = {
            "help": {
                "content": """# Available Slash Commands

This is a list of all available slash commands. Use them by typing `/command-name`.

## Builtin Commands
- `/help` - Show this help message
- `/clear` - Clear the conversation context
- `/date` - Show current date and time
- `/pwd` - Show current working directory
- `/version` - Show system version information

## Market Commands
- `/skill search <query>` - Search for skills in the market
- `/skill install <name>` - Install a skill from the market
- `/skill list` - List installed skills
- `/agent search <query>` - Search for agents in the market
- `/agent install <name>` - Install an agent from the market
- `/agent list` - List installed agents
- `/plugin search <query>` - Search for plugins in the market
- `/plugin install <name>` - Install a plugin from the market
- `/plugin list` - List installed plugins
- `/plugin uninstall <name>` - Uninstall a plugin

## Custom Commands
Custom commands can be added to:
- Workspace: `{workspace}/.dawei/commands/`
- User: `~/.dawei/commands/`
""",
                "description": "Show available slash commands",
                "argument_hint": None,
                "mode": None,
            },
            "clear": {
                "content": """# Clear Conversation

This command clears the current conversation context.

Note: This is a mock command. The actual clear functionality should be implemented by the agent.
""",
                "description": "Clear the conversation context",
                "argument_hint": None,
                "mode": None,
            },
            "date": {
                "content": """# Current Date and Time

Please use the execute_command tool to run:
```bash
date
```

This will show the current date and time in the system.
""",
                "description": "Show current date and time",
                "argument_hint": None,
                "mode": None,
            },
            "pwd": {
                "content": """# Current Working Directory

Please use the execute_command tool to run:
```bash
pwd
```

This will show the current working directory.
""",
                "description": "Show current working directory",
                "argument_hint": None,
                "mode": None,
            },
            "version": {
                "content": """# System Version Information

Please use the execute_command tool to run:
```bash
python --version
uname -a
```

This will show Python version and system information.
""",
                "description": "Show system version information",
                "argument_hint": None,
                "mode": None,
            },
        }

        # Add market commands (if market module is available)
        try:
            from dawei.market import MARKET_AVAILABLE

            if MARKET_AVAILABLE:
                builtin_commands.update(
                    {
                        "skill": {
                            "content": """# Skill Market Commands

## Search Skills
Search for skills in the market:
```
/skill search <query>
```

## Install Skill
Install a skill from the market:
```
/skill install <skill-name>
```

## List Installed Skills
List all installed skills in the workspace:
```
/skill list
```
""",
                            "description": "Manage skills from the market (search, install, list)",
                            "argument_hint": "<action> [args]",
                            "mode": None,
                        },
                        "agent": {
                            "content": """# Agent Market Commands

## Search Agents
Search for agents in the market:
```
/agent search <query>
```

## Install Agent
Install an agent from the market:
```
/agent install <agent-name>
```

## List Installed Agents
List all installed agents in the workspace:
```
/agent list
```
""",
                            "description": "Manage agents from the market (search, install, list)",
                            "argument_hint": "<action> [args]",
                            "mode": None,
                        },
                        "plugin": {
                            "content": """# Plugin Market Commands

## Search Plugins
Search for plugins in the market:
```
/plugin search <query>
```

## Install Plugin
Install a plugin from the market:
```
/plugin install <plugin-name>
```

## List Installed Plugins
List all installed plugins in the workspace:
```
/plugin list
```

## Uninstall Plugin
Uninstall a plugin from the workspace:
```
/plugin uninstall <plugin-name>
```
""",
                            "description": "Manage plugins from the market (search, install, list, uninstall)",
                            "argument_hint": "<action> [args]",
                            "mode": None,
                        },
                    },
                )
        except ImportError:
            # Market module not available, skip market commands
            pass

        for name, config in builtin_commands.items():
            self.register_builtin_command(name=name, **config)
