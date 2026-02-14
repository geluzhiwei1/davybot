# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""安全命令执行器 - 集成白名单验证和Docker沙箱隔离

该模块是沙箱系统的主要入口点,提供:
- 命令白名单验证
- Docker容器隔离执行
- 降级方案(subprocess执行)
- 统一的错误处理

使用示例:
    from dawei.sandbox.secure_executor import SecureCommandExecutor
    from pathlib import Path

    executor = SecureCommandExecutor(use_sandbox=True)
    result = executor.execute(
        command="ls -la",
        workspace_path=Path("/workspace"),
        user_id="user123"
    )

    if result['success']:
        print(result['stdout'])
    else:
        print(f"Error: {result['error']}")
"""

import asyncio
import logging
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from dawei.sandbox.command_whitelist import CommandWhitelist
from dawei.sandbox.sandbox_manager import SandboxConfig, SandboxManager

logger = logging.getLogger(__name__)


class SecureCommandExecutor:
    """安全的命令执行器"""

    def __init__(
        self,
        use_sandbox: bool = True,
        sandbox_config: SandboxConfig = None,
        prefer_lightweight: bool = False,
    ):
        """初始化安全执行器

        Args:
            use_sandbox: 是否使用沙箱(Docker或轻量级)
            sandbox_config: Docker沙箱配置(可选)
            prefer_lightweight: 优先使用轻量级模式(无需Docker)

        """
        self.use_sandbox = use_sandbox
        self.whitelist = CommandWhitelist()
        self.sandbox_config = sandbox_config or SandboxConfig()
        self.prefer_lightweight = prefer_lightweight

        # 初始化执行器
        if prefer_lightweight:
            # 优先使用轻量级模式
            try:
                from dawei.sandbox.lightweight_executor import HybridSandboxExecutor

                self.lightweight_executor = HybridSandboxExecutor()
                self.execution_mode = "lightweight"
                self.sandbox_available = False
                logger.info("[SECURE_EXECUTOR] 使用轻量级混合模式(无需Docker)")
            except ImportError as e:
                logger.warning(f"[SECURE_EXECUTOR] 轻量级模式不可用: {e}")
                self.lightweight_executor = None
                self.execution_mode = "subprocess"
                self.sandbox_available = False
        elif use_sandbox:
            # 使用Docker沙箱
            try:
                self.sandbox_manager = SandboxManager(config=self.sandbox_config)
                self.sandbox_available = True
                self.execution_mode = "docker"
                logger.info("[SECURE_EXECUTOR] Docker沙箱已启用")
            except RuntimeError as e:
                logger.warning(f"[SECURE_EXECUTOR] Docker沙箱不可用: {e}")
                # 尝试降级到轻量级模式
                try:
                    from dawei.sandbox.lightweight_executor import HybridSandboxExecutor

                    self.lightweight_executor = HybridSandboxExecutor()
                    self.execution_mode = "lightweight"
                    self.sandbox_available = False
                    logger.info("[SECURE_EXECUTOR] 降级到轻量级混合模式")
                except ImportError:
                    self.execution_mode = "subprocess"
                    self.sandbox_available = False
                    logger.warning("[SECURE_EXECUTOR] 所有沙箱模式均不可用,使用subprocess")
        else:
            self.sandbox_available = False
            self.execution_mode = "subprocess"
            logger.warning("[SECURE_EXECUTOR] 沙箱已禁用,使用subprocess执行")

        logger.info(f"[SECURE_EXECUTOR] 执行模式: {self.execution_mode}")

    def execute(
        self,
        command: str,
        workspace_path: Path,
        user_id: str = "unknown",
    ) -> dict[str, Any]:
        """安全地执行命令

        Args:
            command: 命令字符串
            workspace_path: 工作区路径
            user_id: 用户ID

        Returns:
            执行结果字典,包含:
            - success: bool - 是否成功
            - stdout: str - 标准输出
            - stderr: str - 标准错误
            - exit_code: int - 退出码
            - execution_time: int - 执行时间(毫秒)
            - error: str (可选) - 错误信息
            - workspace: str (可选) - 工作区路径

        """
        logger.info(f"[SECURE_EXECUTOR] 执行命令: {command[:50]}...")

        # 1. 验证命令白名单
        is_valid, error_msg = self.whitelist.validate_command(command)
        if not is_valid:
            logger.warning(f"[SECURE_EXECUTOR] 命令验证失败: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "stdout": "",
                "stderr": error_msg,
                "exit_code": -1,
                "execution_time": 0,
            }

        # 2. 尝试使用沙箱
        if self.execution_mode == "docker" and self.sandbox_available:
            try:
                logger.debug("[SECURE_EXECUTOR] 使用Docker沙箱执行")
                return self.sandbox_manager.execute_command(command, workspace_path, user_id)
            except RuntimeError:
                logger.exception("[SECURE_EXECUTOR] Docker沙箱执行失败: ")
                # 降级到subprocess
                logger.warning("[SECURE_EXECUTOR] 降级到subprocess执行(受白名单保护)")
                return self._execute_with_subprocess(command, workspace_path)
            except ConnectionError:
                logger.exception("[SECURE_EXECUTOR] Docker沙箱连接失败: ")
                # 降级到subprocess
                logger.warning(
                    "[SECURE_EXECUTOR] Docker连接失败,降级到subprocess执行(受白名单保护)",
                )
                return self._execute_with_subprocess(command, workspace_path)
            except (OSError, ValueError, TypeError) as e:
                logger.error(f"[SECURE_EXECUTOR] Docker沙箱执行失败: {e}", exc_info=True)
                # 降级到subprocess
                logger.warning("[SECURE_EXECUTOR] 降级到subprocess执行(受白名单保护)")
                return self._execute_with_subprocess(command, workspace_path)

        elif self.execution_mode == "lightweight" and self.lightweight_executor:
            try:
                logger.debug("[SECURE_EXECUTOR] 使用轻量级混合模式执行")
                return self.lightweight_executor.execute(command, workspace_path, user_id)
            except RuntimeError:
                logger.exception("[SECURE_EXECUTOR] 轻量级执行失败: ")
                # 降级到subprocess
                logger.warning("[SECURE_EXECUTOR] 降级到subprocess执行(受白名单保护)")
                return self._execute_with_subprocess(command, workspace_path)
            except ConnectionError:
                logger.exception("[SECURE_EXECUTOR] 轻量级执行连接失败: ")
                # 降级到subprocess
                logger.warning(
                    "[SECURE_EXECUTOR] 轻量级执行连接失败,降级到subprocess执行(受白名单保护)",
                )
                return self._execute_with_subprocess(command, workspace_path)
            except (OSError, ValueError, TypeError) as e:
                logger.error(f"[SECURE_EXECUTOR] 轻量级执行失败: {e}", exc_info=True)
                # 降级到subprocess
                logger.warning("[SECURE_EXECUTOR] 降级到subprocess执行(受白名单保护)")
                return self._execute_with_subprocess(command, workspace_path)

        # 3. 使用subprocess(有白名单保护)
        logger.debug("[SECURE_EXECUTOR] 使用subprocess执行")
        return self._execute_with_subprocess(command, workspace_path)

    def _execute_with_subprocess(self, command: str, workspace_path: Path) -> dict[str, Any]:
        """使用subprocess执行(带限制)"""
        start_time = time.time()

        try:
            # 解析命令
            args = shlex.split(command)

            logger.debug(f"[SECURE_EXECUTOR] subprocess参数: {args}")

            # 资源限制(通过subprocess)
            # 准备环境变量 - 继承系统PATH以支持跨平台
            env = {
                "PATH": os.environ.get("PATH", ""),
            }

            # 设置HOME目录(Unix使用HOME,Windows使用USERPROFILE)
            if sys.platform != "win32":
                env["HOME"] = str(workspace_path)
            else:
                # Windows上同时设置HOME和USERPROFILE(兼容Unix工具)
                env["HOME"] = str(workspace_path)
                env["USERPROFILE"] = str(workspace_path)

            result = subprocess.run(
                args,
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=30,  # 超时
                env=env,
            )

            execution_time = int((time.time() - start_time) * 1000)

            logger.info(
                f"[SECURE_EXECUTOR] 命令执行完成: exit_code={result.returncode}, time={execution_time}ms",
            )

            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "execution_time": execution_time,
                "workspace": str(workspace_path),
            }

        except subprocess.TimeoutExpired:
            execution_time = int((time.time() - start_time) * 1000)
            logger.exception("[SECURE_EXECUTOR] 命令执行超时")
            return {
                "success": False,
                "error": "Command timeout",
                "stdout": "",
                "stderr": "Command execution timeout (30s)",
                "exit_code": -1,
                "execution_time": execution_time,
            }
        except FileNotFoundError as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.exception("[SECURE_EXECUTOR] 命令未找到: ")
            return {
                "success": False,
                "error": f"Command not found: {e}",
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "execution_time": execution_time,
            }
        except subprocess.PermissionError as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.exception("[SECURE_EXECUTOR] 权限错误: ")
            return {
                "success": False,
                "error": f"Permission denied: {e}",
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "execution_time": execution_time,
            }
        except OSError as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.exception("[SECURE_EXECUTOR] 系统错误: ")
            return {
                "success": False,
                "error": f"System error: {e}",
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "execution_time": execution_time,
            }
        except (shlex.Error, ValueError) as e:
            # Command parsing errors - should fail fast
            execution_time = int((time.time() - start_time) * 1000)
            logger.exception("[SECURE_EXECUTOR] 命令解析错误: ")
            return {
                "success": False,
                "error": f"Command parsing error: {e}",
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "execution_time": execution_time,
            }
        except Exception as e:
            # LEGITIMATE TOLERANCE: Subprocess execution has many external factors
            # (permissions, OS errors, etc.) - catch-all is appropriate here
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"[SECURE_EXECUTOR] Subprocess执行失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Subprocess execution failed: {e}",
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "execution_time": execution_time,
            }

    async def execute_async(
        self,
        command: str,
        workspace_path: Path,
        user_id: str = "unknown",
    ) -> dict[str, Any]:
        """异步执行命令

        Args:
            command: 命令字符串
            workspace_path: 工作区路径
            user_id: 用户ID

        Returns:
            执行结果字典

        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.execute(command, workspace_path, user_id),
        )

    def health_check(self) -> dict[str, Any]:
        """健康检查

        Returns:
            健康状态字典

        """
        status = {
            "executor": "SecureCommandExecutor",
            "execution_mode": self.execution_mode,
            "use_sandbox": self.use_sandbox,
            "sandbox_available": self.sandbox_available,
            "prefer_lightweight": self.prefer_lightweight,
            "whitelist_enabled": True,
        }

        if self.execution_mode == "docker" and self.sandbox_available:
            try:
                status["docker_healthy"] = self.sandbox_manager.health_check()
            except RuntimeError:
                logger.exception("Docker health check runtime error: ")
                status["docker_healthy"] = False
            except ConnectionError:
                logger.exception("Docker health check connection error: ")
                status["docker_healthy"] = False
            except Exception as e:
                # LEGITIMATE TOLERANCE: Health check should never crash
                # External dependencies may fail in various ways
                logger.error(f"Failed to check Docker health: {e}", exc_info=True)
                status["docker_healthy"] = False
        elif self.execution_mode == "lightweight" and self.lightweight_executor:
            try:
                status["lightweight_health"] = self.lightweight_executor.health_check()
            except RuntimeError:
                logger.exception("Lightweight executor health check runtime error: ")
                status["lightweight_health"] = False
            except ConnectionError:
                logger.exception("Lightweight executor health check connection error: ")
                status["lightweight_health"] = False
            except Exception as e:
                # LEGITIMATE TOLERANCE: Health check should never crash
                # External dependencies may fail in various ways
                logger.error(f"Failed to check lightweight executor health: {e}", exc_info=True)
                status["lightweight_health"] = False
        else:
            status["docker_healthy"] = False
            status["lightweight_health"] = None

        return status
