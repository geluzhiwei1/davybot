# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""CLI配置管理模块

负责解析和验证命令行参数，加载环境变量和配置文件。
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from dawei.logg.logging import get_logger


@dataclass
class CLIConfig:
    """CLI配置类

    Attributes:
        workspace: 工作区路径
        llm: LLM模型名称（如 openai/gpt-4, deepseek/deepseek-chat）
        mode: Agent模式（code, ask, architect, plan, debug）
        message: 用户消息/指令
        verbose: 是否输出详细日志
        timeout: 执行超时时间（秒）

    """

    workspace: str
    llm: str
    mode: str
    message: str
    verbose: bool = False
    timeout: int = 1800  # 默认30分钟

    # 内部使用
    _workspace_path: Path = field(init=False, default=None)
    _logger: Any = field(init=False, default=None)

    def __post_init__(self):
        """初始化后处理"""
        # 转换为绝对路径
        self._workspace_path = Path(self.workspace).resolve()

        # 设置logger
        self._logger = get_logger(__name__)

        # 加载环境变量
        self._load_env_vars()

    def _load_env_vars(self):
        """加载环境变量"""
        # 尝试从workspace目录加载.env
        env_paths = [
            self._workspace_path / ".env",
            Path.cwd() / ".env",
        ]

        for env_path in env_paths:
            if env_path.exists():
                load_dotenv(env_path)
                if self.verbose:
                    self._logger.info(f"Loaded environment variables from: {env_path}")
                break

    def validate(self) -> tuple[bool, str | None]:
        """验证配置是否有效

        Returns:
            (是否有效, 错误信息)

        """
        # 验证workspace路径
        if not self._workspace_path.exists():
            return False, f"Workspace path does not exist: {self._workspace_path}"

        # 验证mode是否有效 (PDCA modes)
        valid_modes = ["orchestrator", "plan", "do", "check", "act"]
        if self.mode.lower() not in valid_modes:
            return (
                False,
                f"Invalid mode '{self.mode}'. Must be one of: {', '.join(valid_modes)}",
            )

        # 验证message不为空
        if not self.message or not self.message.strip():
            return False, "Message cannot be empty"

        # 验证LLM配置（如果有API key要求）
        if not os.getenv("LITELLM_API_KEY") and not os.getenv("OPENAI_API_KEY"):
            # 某些本地模型可能不需要API key，这里只发出警告
            self._logger.warning("No LITELLM_API_KEY or OPENAI_API_KEY found in environment")

        return True, None

    def ensure_workspace_initialized(self) -> None:
        """确保workspace已初始化

        如果workspace的.dawei目录不存在，自动创建基本结构
        """
        dawei_dir = self._workspace_path / ".dawei"

        if not dawei_dir.exists():
            if self.verbose:
                self._logger.info(f"Creating .dawei directory in workspace: {self._workspace_path}")

            dawei_dir.mkdir(parents=True, exist_ok=True)

            # 创建子目录
            (dawei_dir / "chat-history").mkdir(exist_ok=True)
            (dawei_dir / "checkpoints").mkdir(exist_ok=True)

            # 创建基本配置文件（如果不存在）
            settings_file = dawei_dir / "settings.json"
            if not settings_file.exists():
                import json

                default_settings = {
                    "name": self._workspace_path.name,
                    "description": "Workspace created by CLI",
                    "allowed_commands": [],
                }
                with settings_file.open("w", encoding="utf-8") as f:
                    json.dump(default_settings, f, indent=2, ensure_ascii=False)

                if self.verbose:
                    self._logger.info(f"Created default settings file: {settings_file}")

    @property
    def workspace_path(self) -> Path:
        """获取工作区路径对象"""
        return self._workspace_path

    @property
    def workspace_absolute(self) -> str:
        """获取工作区绝对路径字符串"""
        return str(self._workspace_path)


def create_config(
    workspace: str,
    llm: str,
    mode: str,
    message: str,
    verbose: bool = False,
    timeout: int = 1800,
) -> CLIConfig:
    """创建CLI配置对象

    Args:
        workspace: 工作区路径
        llm: LLM模型名称
        mode: Agent模式
        message: 用户消息
        verbose: 是否输出详细日志
        timeout: 执行超时时间（秒）

    Returns:
        CLIConfig对象

    """
    config = CLIConfig(
        workspace=workspace,
        llm=llm,
        mode=mode,
        message=message,
        verbose=verbose,
        timeout=timeout,
    )

    # 验证配置
    is_valid, error_msg = config.validate()
    if not is_valid:
        print(f"❌ Configuration error: {error_msg}", file=sys.stderr)
        sys.exit(1)

    # 确保workspace已初始化
    config.ensure_workspace_initialized()

    return config
