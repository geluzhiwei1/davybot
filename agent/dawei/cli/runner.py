# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Agent执行封装器

负责初始化Agent并执行任务，不经过HTTP/WebSocket。
"""

import asyncio
import time
from typing import Any

from dawei.agentic.agent import Agent
from dawei.cli.config import CLIConfig
from dawei.entity.user_input_message import UserInputText
from dawei.logg.logging import get_logger
from dawei.workspace.user_workspace import UserWorkspace


class AgentRunner:
    """Agent执行器

    封装Agent的完整执行流程，用于CLI环境。
    """

    def __init__(self, config: CLIConfig):
        """初始化执行器

        Args:
            config: CLI配置对象

        """
        self.config = config
        self.logger = get_logger(__name__)
        self.user_workspace: UserWorkspace | None = None
        self.agent: Agent | None = None
        self._execution_result: dict[str, Any] = {}

    async def initialize(self) -> None:
        """初始化工作区和Agent"""
        self.logger.info(f"Initializing workspace: {self.config.workspace_absolute}")

        # 1. 创建UserWorkspace
        self.user_workspace = UserWorkspace(workspace_path=self.config.workspace_absolute)

        # 2. 初始化workspace
        await self.user_workspace.initialize()
        self.logger.info("Workspace initialized successfully")

        # 3. 创建Agent（使用默认执行引擎）
        self.agent = await Agent.create_with_default_engine(
            user_workspace=self.user_workspace,
            config={
                "llm_model": self.config.llm,
                "enable_auto_mode_switch": False,  # CLI模式不需要自动切换
                "enable_skills": True,
                "enable_mcp": False,  # CLI模式默认不启用MCP
                "max_iterations": 100,
                "checkpoint_interval": 60.0,
            },
        )

        # 4. 设置Agent mode
        if self.config.verbose:
            self.logger.info(f"Setting agent mode to: {self.config.mode}")
        self.user_workspace.mode = self.config.mode

        # 5. 设置LLM provider
        if self.config.verbose:
            self.logger.info(f"Setting LLM provider to: {self.config.llm}")
        self.user_workspace.llm_manager.set_provider(self.config.llm)

        self.logger.info("Agent initialized successfully")

    async def run(self) -> dict[str, Any]:
        """执行Agent任务

        Returns:
            执行结果字典，包含：
            - success: 是否成功
            - message: 执行消息
            - duration: 执行时长（秒）
            - error: 错误信息（如果失败）

        """
        start_time = time.time()

        try:
            # 1. 确保已初始化
            if not self.agent:
                await self.initialize()

            self.logger.info("=" * 60)
            self.logger.info("Starting agent execution")
            self.logger.info(f"  Mode: {self.config.mode}")
            self.logger.info(f"  LLM: {self.config.llm}")
            self.logger.info(f"  Message: {self.config.message[:100]}...")
            self.logger.info("=" * 60)

            # 2. 创建用户消息
            user_message = UserInputText(
                text=self.config.message,
                task_node_id=None,  # 让系统自动创建根任务
            )

            # 3. 执行消息处理（带超时控制）
            try:
                # 使用 asyncio.wait_for 以兼容 Python 3.10
                await asyncio.wait_for(
                    self.agent.process_message(user_message),
                    timeout=self.config.timeout,
                )

                self.logger.info("Agent execution completed successfully")

            except TimeoutError:
                self.logger.exception(f"Agent execution timeout after {self.config.timeout}s")
                return {
                    "success": False,
                    "message": "Execution timeout",
                    "duration": time.time() - start_time,
                    "error": f"Timeout after {self.config.timeout} seconds",
                }

            # 4. 等待任务完成（确保所有异步操作完成）
            await asyncio.sleep(0.5)

            # 5. 返回成功结果
            duration = time.time() - start_time
            return {
                "success": True,
                "message": "Agent execution completed successfully",
                "duration": duration,
                "error": None,
            }

        except Exception as e:
            self.logger.error(f"Agent execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "message": "Agent execution failed",
                "duration": time.time() - start_time,
                "error": str(e),
            }

    async def cleanup(self) -> None:
        """清理资源"""
        self.logger.info("Cleaning up resources...")

        try:
            # 清理Agent
            if self.agent:
                await self.agent.cleanup()

            # 清理workspace
            if self.user_workspace:
                await self.user_workspace.cleanup()

            self.logger.info("Resources cleaned up successfully")

        except (OSError, RuntimeError) as e:
            # Cleanup failures should be logged but not crash the system
            # These are typically resource cleanup errors that we can tolerate
            self.logger.error(f"Error during cleanup: {e}", exc_info=True)


async def run_agent_directly(
    workspace: str,
    llm: str,
    mode: str,
    message: str,
    verbose: bool = False,
    timeout: int = 1800,
) -> dict[str, Any]:
    """直接运行Agent（不经过HTTP/WebSocket）

    Args:
        workspace: 工作区路径
        llm: LLM模型名称
        mode: Agent模式
        message: 用户消息
        verbose: 是否输出详细日志
        timeout: 执行超时时间（秒）

    Returns:
        执行结果字典

    """
    # 创建配置
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
        return {
            "success": False,
            "message": "Configuration validation failed",
            "duration": 0,
            "error": error_msg,
        }

    # 创建runner
    runner = AgentRunner(config)

    try:
        # 执行
        return await runner.run()

    finally:
        # 确保清理资源
        await runner.cleanup()


def run_agent_sync(
    workspace: str,
    llm: str,
    mode: str,
    message: str,
    verbose: bool = False,
    timeout: int = 1800,
) -> dict[str, Any]:
    """同步版本的Agent执行器（用于Fire等同步环境）

    Args:
        workspace: 工作区路径
        llm: LLM模型名称
        mode: Agent模式
        message: 用户消息
        verbose: 是否输出详细日志
        timeout: 执行超时时间（秒）

    Returns:
        执行结果字典

    """
    return asyncio.run(
        run_agent_directly(
            workspace=workspace,
            llm=llm,
            mode=mode,
            message=message,
            verbose=verbose,
            timeout=timeout,
        ),
    )
