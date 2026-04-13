# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""命令执行器 - 通过 subprocess 执行命令，配合白名单做安全检查"""

import logging
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

from dawei.sandbox.command_whitelist import CommandWhitelist

logger = logging.getLogger(__name__)


class CommandExecutor:
    """命令执行器 - subprocess + 白名单验证"""

    def __init__(self):
        self.whitelist = CommandWhitelist()

    def execute_command(
        self,
        command: str,
        workspace_path: Path,
        user_id: str = "unknown",
    ) -> Dict[str, Any]:
        """执行命令

        Args:
            command: 命令字符串
            workspace_path: 工作区路径
            user_id: 用户ID

        Returns:
            执行结果字典
        """
        start_time = time.time()

        try:
            # 检查白名单（仅在启用时）
            from dawei.core.security_manager import security_manager

            sec = security_manager.get_settings()
            if sec.get("enable_command_whitelist", True):
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

            # 解析命令
            args = shlex.split(command)

            # 准备环境变量
            env = {
                "PATH": os.environ.get("PATH", ""),
                "TERM": "xterm",
            }

            if sys.platform != "win32":
                env["HOME"] = str(workspace_path)
            else:
                env["HOME"] = str(workspace_path)
                env["USERPROFILE"] = str(workspace_path)

            # Unix: 清理危险环境变量
            if sys.platform != "win32":
                for key in list(os.environ.keys()):
                    if key.upper() in ["LD_PRELOAD", "LD_LIBRARY_PATH", "IFS", "CDPATH"]:
                        env.pop(key, None)

            # 获取超时配置
            timeout = sec.get("command_execution_timeout", 30) if sec else 30

            result = subprocess.run(
                args,
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )

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
            return {
                "success": False,
                "error": f"Command timeout ({timeout}s)",
                "stdout": "",
                "stderr": f"Command execution timeout ({timeout}s)",
                "exit_code": -1,
                "execution_time": execution_time,
            }
        except FileNotFoundError:
            execution_time = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "error": f"Command not found: {args[0] if 'args' in dir() else command}",
                "stdout": "",
                "stderr": f"Command not found in PATH",
                "exit_code": 127,
                "execution_time": execution_time,
            }
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"[COMMAND_EXECUTOR] 执行失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "execution_time": execution_time,
            }
