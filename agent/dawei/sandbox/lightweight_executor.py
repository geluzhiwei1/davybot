# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""轻量级沙箱执行器 - 不依赖Docker的安全命令执行

使用multiprocessing + resource限制实现轻量级隔离
适用于不想使用Docker的场景

优势:
- 无需Docker
- 轻量级
- 启动快速
- 跨平台兼容
"""

import logging
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from dawei.sandbox.command_whitelist import CommandWhitelist

# 跨平台资源限制支持
# resource 模块仅在 Unix 系统上可用 (Linux/macOS)
# 在 Windows 上，我们跳过资源限制但保持功能完整
_is_unix = sys.platform != "win32"
if _is_unix:
    import resource

logger = logging.getLogger(__name__)


class LightweightSandbox:
    """轻量级沙箱 - 使用subprocess + 资源限制"""

    def __init__(self):
        self.whitelist = CommandWhitelist()

    def execute_command(
        self,
        command: str,
        workspace_path: Path,
        _user_id: str = "unknown",
    ) -> dict[str, Any]:
        """在轻量级沙箱中执行命令

        Args:
            command: 命令字符串
            workspace_path: 工作区路径
            user_id: 用户ID

        Returns:
            执行结果字典

        """
        start_time = time.time()

        try:
            # 1. 验证命令白名单
            is_valid, error_msg = self.whitelist.validate_command(command)
            if not is_valid:
                return {
                    "success": False,
                    "error": error_msg,
                    "stdout": "",
                    "stderr": error_msg,
                    "exit_code": -1,
                    "execution_time": 0,
                }

            # 2. 解析命令
            args = shlex.split(command)

            # 3. 准备环境变量（跨平台兼容）
            env = {
                "PATH": os.environ.get("PATH", ""),  # 继承系统PATH，支持跨平台
                "TERM": "xterm",
            }

            # 设置HOME目录（Unix使用HOME，Windows使用USERPROFILE）
            if _is_unix:
                env["HOME"] = str(workspace_path)
            else:
                # Windows上同时设置HOME和USERPROFILE（兼容Unix工具）
                env["HOME"] = str(workspace_path)
                env["USERPROFILE"] = str(workspace_path)

            # 清理潜在的危险环境变量（仅Unix特定的）
            if _is_unix:
                for key in list(os.environ.keys()):
                    if key.upper() in [
                        "LD_PRELOAD",
                        "LD_LIBRARY_PATH",
                        "IFS",
                        "CDPATH",
                    ]:
                        env.pop(key, None)

            # 4. 设置资源限制并执行命令
            try:
                # 设置资源限制（仅在 Unix 系统上可用）
                if _is_unix:
                    try:
                        resource.setrlimit(resource.RLIMIT_CPU, (30, 30))  # CPU限制30秒
                        resource.setrlimit(
                            resource.RLIMIT_AS,
                            (512 * 1024 * 1024, 512 * 1024 * 1024),
                        )  # 内存限制512MB
                        resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))  # 文件描述符限制
                        resource.setrlimit(resource.RLIMIT_NPROC, (100, 100))  # 进程数限制
                    except (ValueError, OSError) as e:
                        # 资源限制设置失败，继续执行（安全性降低但不会崩溃）
                        logger.warning(
                            f"[LIGHTWEIGHT_SANDBOX] 无法设置资源限制（可能需要root权限）: {e}",
                        )

                # 直接使用subprocess执行（简单但仍然安全）
                result = subprocess.run(
                    args,
                    cwd=workspace_path,
                    capture_output=True,
                    text=True,
                    timeout=30,  # 30秒超时
                    env=env,
                )
            except resource.error if _is_unix else Exception as e:
                execution_time = int((time.time() - start_time) * 1000)
                logger.exception("[LIGHTWEIGHT_SANDBOX] 资源限制设置失败: ")
                return {
                    "success": False,
                    "error": f"Resource limit error: {e!s}",
                    "stdout": "",
                    "stderr": f"Failed to set resource limits: {e!s}",
                    "exit_code": -1,
                    "execution_time": execution_time,
                }

            execution_time = int((time.time() - start_time) * 1000)

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
            logger.exception(f"[LIGHTWEIGHT_SANDBOX] 命令执行超时: {command}")
            return {
                "success": False,
                "error": "Command timeout (30s)",
                "stdout": "",
                "stderr": "Command execution timeout (30s)",
                "exit_code": -1,
                "execution_time": execution_time,
            }
        except FileNotFoundError:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"[LIGHTWEIGHT_SANDBOX] 命令未找到: {command}", exc_info=True)
            return {
                "success": False,
                "error": f"Command not found: {args[0] if args else command}",
                "stdout": "",
                "stderr": f"Command '{args[0] if args else command}' not found in PATH",
                "exit_code": 127,
                "execution_time": execution_time,
            }
        except subprocess.CalledProcessError as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.exception(f"[LIGHTWEIGHT_SANDBOX] 命令执行失败: {command}")
            return {
                "success": False,
                "error": f"Command execution failed: {e}",
                "stdout": e.stdout,
                "stderr": e.stderr,
                "exit_code": e.returncode,
                "execution_time": execution_time,
            }
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"[LIGHTWEIGHT_SANDBOX] 执行失败: {e}", exc_info=True)
            # Intentional tolerance: Sandbox API contract requires graceful degradation
            # Return error dict instead of raising to maintain stable API for callers
            return {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "execution_time": execution_time,
            }


class ChrootSandbox:
    """使用chroot的文件系统隔离（需要root权限）"""

    def __init__(self, chroot_root: Path):
        self.chroot_root = chroot_root
        self.whitelist = CommandWhitelist()

    def execute_command(
        self,
        command: str,
        workspace_path: Path,
        _user_id: str = "unknown",
    ) -> dict[str, Any]:
        """在chroot环境中执行命令

        注意：需要root权限才能执行chroot
        """
        # 验证白名单
        is_valid, error_msg = self.whitelist.validate_command(command)
        if not is_valid:
            return {
                "success": False,
                "error": error_msg,
                "exit_code": -1,
                "execution_time": 0,
            }

        # 检查平台兼容性 - chroot仅在Unix系统上可用
        if not _is_unix:
            return {
                "success": False,
                "error": "Chroot sandbox is not supported on Windows (requires Unix chroot)",
                "exit_code": -1,
                "execution_time": 0,
            }

        # 检查是否有root权限 (Unix系统)
        if os.geteuid() != 0:
            return {
                "success": False,
                "error": "Chroot requires root privileges",
                "exit_code": -1,
                "execution_time": 0,
            }

        start_time = time.time()

        try:
            # 使用chroot执行命令
            # 这需要root权限
            chroot_cmd = ["chroot", str(self.chroot_root), *shlex.split(command)]
            result = subprocess.run(chroot_cmd, capture_output=True, text=True, timeout=30)

            execution_time = int((time.time() - start_time) * 1000)

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
            logger.exception(f"[CHROOT_SANDBOX] 命令执行超时: {command}")
            return {
                "success": False,
                "error": "Command timeout (30s)",
                "stdout": "",
                "stderr": "Command execution timeout (30s)",
                "exit_code": -1,
                "execution_time": execution_time,
            }
        except subprocess.CalledProcessError as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.exception(f"[CHROOT_SANDBOX] 命令执行失败: {command}")
            return {
                "success": False,
                "error": f"Command execution failed: {e}",
                "stdout": e.stdout,
                "stderr": e.stderr,
                "exit_code": e.returncode,
                "execution_time": execution_time,
            }
        except FileNotFoundError:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(
                f"[CHROOT_SANDBOX] 命令未找到: {chroot_cmd[0] if chroot_cmd else command}",
                exc_info=True,
            )
            return {
                "success": False,
                "error": f"Command not found: {chroot_cmd[0] if chroot_cmd else command}",
                "stdout": "",
                "stderr": f"Command '{chroot_cmd[0] if chroot_cmd else command}' not found in chroot environment",
                "exit_code": 127,
                "execution_time": execution_time,
            }
        except PermissionError as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.exception(f"[CHROOT_SANDBOX] 权限错误: {command}")
            return {
                "success": False,
                "error": "Permission denied for chroot operation",
                "stdout": "",
                "stderr": str(e),
                "exit_code": 126,
                "execution_time": execution_time,
            }
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"[CHROOT_SANDBOX] 执行失败: {e}", exc_info=True)
            # Intentional tolerance: Sandbox API contract requires graceful degradation
            # Return error dict instead of raising to maintain stable API for callers
            return {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "execution_time": execution_time,
            }


class FirejailSandbox:
    """使用Firejail的沙箱（Linux专用，无需root）"""

    def __init__(self):
        self.whitelist = CommandWhitelist()
        # 检查firejail是否可用
        try:
            subprocess.run(["firejail", "--version"], capture_output=True, check=True)
            self.available = True
            logger.info("Firejail is available for sandbox execution")
        except FileNotFoundError:
            # 明确：Firejail 未安装
            logger.warning(
                "Firejail not found. Sandbox commands will run WITHOUT isolation. Install firejail for better security: sudo apt install firejail",
            )
            self.available = False
        except PermissionError:
            # 明确：权限问题
            logger.error(
                "Permission denied when checking firejail. Firejail is available but cannot be executed.",
                exc_info=True,
            )
            self.available = False
        except subprocess.CalledProcessError as e:
            # 明确：Firejail 执行失败
            logger.error(f"Firejail check failed with return code {e.returncode}", exc_info=True)
            self.available = False
        except Exception as e:
            # 未预期的错误 - 快速失败
            logger.critical(f"Unexpected error checking firejail: {e}", exc_info=True)
            raise  # Fast fail

    def execute_command(
        self,
        command: str,
        workspace_path: Path,
        _user_id: str = "unknown",
    ) -> dict[str, Any]:
        """使用Firejail执行命令"""
        if not self.available:
            return {
                "success": False,
                "error": "Firejail is not available",
                "exit_code": -1,
                "execution_time": 0,
            }

        # 验证白名单
        is_valid, error_msg = self.whitelist.validate_command(command)
        if not is_valid:
            return {
                "success": False,
                "error": error_msg,
                "exit_code": -1,
                "execution_time": 0,
            }

        start_time = time.time()

        try:
            # 使用firejail执行命令
            # firejail参数:
            # --private=目录: 使用临时目录
            # --whitelist=目录: 允许访问指定目录
            # --quiet: 安静模式
            # --net=none: 禁用网络
            firejail_cmd = [
                "firejail",
                "--quiet",
                "--net=none",
                f"--whitelist={workspace_path}",
                "--",
                *shlex.split(command),
            ]

            result = subprocess.run(
                firejail_cmd,
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            execution_time = int((time.time() - start_time) * 1000)

            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "execution_time": execution_time,
            }

        except subprocess.TimeoutExpired:
            execution_time = int((time.time() - start_time) * 1000)
            logger.exception(f"[FIREJAIL_SANDBOX] 命令执行超时: {command}")
            return {
                "success": False,
                "error": "Command timeout (30s)",
                "stdout": "",
                "stderr": "Command execution timeout (30s)",
                "exit_code": -1,
                "execution_time": execution_time,
            }
        except subprocess.CalledProcessError as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.exception(f"[FIREJAIL_SANDBOX] 命令执行失败: {command}")
            return {
                "success": False,
                "error": f"Command execution failed: {e}",
                "stdout": e.stdout,
                "stderr": e.stderr,
                "exit_code": e.returncode,
                "execution_time": execution_time,
            }
        except FileNotFoundError:
            execution_time = int((time.time() - start_time) * 1000)
            logger.exception(f"[FIREJAIL_SANDBOX] Firejail not found: {command}")
            return {
                "success": False,
                "error": "Firejail executable not found",
                "stdout": "",
                "stderr": "Firejail is not installed or not in PATH",
                "exit_code": 127,
                "execution_time": execution_time,
            }
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"[FIREJAIL_SANDBOX] 执行失败: {e}", exc_info=True)
            # Intentional tolerance: Sandbox API contract requires graceful degradation
            # Return error dict instead of raising to maintain stable API for callers
            return {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "execution_time": execution_time,
            }


class HybridSandboxExecutor:
    """混合沙箱执行器 - 自动选择最佳的隔离方案

    优先级:
    1. Firejail (Linux，轻量级，无需root)
    2. Docker (如果已安装)
    3. Lightweight (multiprocessing + resource limits)
    """

    def __init__(self):
        self.whitelist = CommandWhitelist()

        # 尝试初始化Firejail
        self.firejail = FirejailSandbox()
        self.has_firejail = self.firejail.available

        # 尝试初始化Docker
        try:
            from dawei.sandbox.sandbox_manager import SandboxManager

            self.docker_manager = SandboxManager()
            self.has_docker = True
            logger.info("Docker sandbox is available")
        except ImportError:
            # 明确：Docker 模块未安装
            logger.warning(
                "Docker dependencies not installed. Docker sandbox unavailable. Install with: pip install docker",
            )
            self.docker_manager = None
            self.has_docker = False
        except Exception as e:
            # Docker 初始化失败，记录但不阻止启动
            logger.error(f"Failed to initialize Docker sandbox: {e}", exc_info=True)
            logger.warning("Docker sandbox will not be available")
            self.docker_manager = None
            self.has_docker = False

        # 初始化轻量级沙箱（总是可用）
        self.lightweight = LightweightSandbox()

        logger.info(f"[HYBRID_SANDBOX] Firejail: {self.has_firejail}, Docker: {self.has_docker}")

    def execute(
        self,
        command: str,
        workspace_path: Path,
        user_id: str = "unknown",
    ) -> dict[str, Any]:
        """使用最佳的可用方法执行命令"""
        # 1. 验证白名单（所有方法共享）
        try:
            is_valid, error_msg = self.whitelist.validate_command(command)
        except TypeError as e:
            logger.exception(f"[HYBRID_SANDBOX] 命令验证类型错误: {command}")
            return {
                "success": False,
                "error": f"Command validation type error: {e!s}",
                "stdout": "",
                "stderr": f"Command validation failed due to type error: {e!s}",
                "exit_code": -1,
                "execution_time": 0,
            }
        except (ValueError, TypeError) as e:
            # Programming errors: invalid input types/values - Fast Fail
            logger.error(f"[HYBRID_SANDBOX] 命令验证类型错误: {command}", exc_info=True)
            return {
                "success": False,
                "error": f"Command validation type error: {e!s}",
                "stdout": "",
                "stderr": f"Command validation failed due to type error: {e!s}",
                "exit_code": -1,
                "execution_time": 0,
            }
        except Exception as e:
            # Unexpected validation errors - log and return error
            logger.error(f"[HYBRID_SANDBOX] 命令验证异常: {command}", exc_info=True)
            return {
                "success": False,
                "error": f"Command validation error: {e!s}",
                "stdout": "",
                "stderr": f"Command validation failed: {e!s}",
                "exit_code": -1,
                "execution_time": 0,
            }

        if not is_valid:
            return {
                "success": False,
                "error": error_msg,
                "stdout": "",
                "stderr": error_msg,
                "exit_code": -1,
                "execution_time": 0,
            }

        # 2. 选择执行方法
        if self.has_firejail:
            logger.debug("[HYBRID_SANDBOX] 使用Firejail")
            return self.firejail.execute_command(command, workspace_path, user_id)

        if self.has_docker:
            logger.debug("[HYBRID_SANDBOX] 使用Docker")
            return self.docker_manager.execute_command(command, workspace_path, user_id)

        logger.debug("[HYBRID_SANDBOX] 使用轻量级模式")
        return self.lightweight.execute_command(command, workspace_path, user_id)

    async def execute_async(
        self,
        command: str,
        workspace_path: Path,
        user_id: str = "unknown",
    ) -> dict[str, Any]:
        """异步执行"""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.execute(command, workspace_path, user_id),
        )

    def health_check(self) -> dict[str, Any]:
        """健康检查"""
        return {
            "executor": "HybridSandboxExecutor",
            "has_firejail": self.has_firejail,
            "has_docker": self.has_docker,
            "lightweight_available": True,
        }
