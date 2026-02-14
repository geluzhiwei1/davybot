# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Docker沙箱管理器 - 提供容器化的命令执行环境

该模块实现了基于Docker的命令隔离执行，包括：
- 容器创建和销毁
- 资源限制（CPU、内存、磁盘、网络）
- 安全配置（只读文件系统、capabilities降级）
- 审计日志

依赖: docker-py (pip install docker)
"""

import asyncio
import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import docker

from dawei.core.exceptions import (
    ConfigurationError,
    DockerConnectionError,
    ResourceLimitError,
    SandboxError,
    SandboxTimeoutError,
)
from dawei.logg.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SandboxConfig:
    """沙箱配置"""

    image: str = "alpine:latest"  # 基础镜像
    memory_limit: str = "512m"  # 内存限制
    cpu_quota: int = 100000  # CPU配额（100000 = 1个CPU）
    cpu_period: int = 100000  # CPU周期
    pids_limit: int = 100  # 进程数限制
    timeout: int = 30  # 执行超时（秒）
    network_disabled: bool = True  # 禁用网络
    read_only_root: bool = True  # 只读根文件系统
    tmpfs_size: str = "100m"  # 临时文件系统大小

    # 工作区挂载配置
    workspace_mount_mode: str = "ro"  # ro = 只读, rw = 读写


class SandboxManager:
    """Docker沙箱管理器"""

    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()

        try:
            self.client = docker.from_env()
            # 测试连接
            self.client.ping()
            logger.info("[SANDBOX] Docker连接成功")
        except docker.errors.DockerException as e:
            logger.exception("[SANDBOX] Docker连接失败: ")
            raise DockerConnectionError(f"Docker daemon不可用: {e}")
        except (OSError, ConnectionError) as e:
            # Network or OS-level errors (e.g., Docker socket not found)
            logger.exception("[SANDBOX] Docker连接错误: ")
            raise DockerConnectionError(f"无法连接到Docker: {e}")

    def execute_command(
        self,
        command: str,
        workspace_path: Path,
        user_id: str = "unknown",
    ) -> dict[str, Any]:
        """在沙箱中执行命令

        Args:
            command: 要执行的命令
            workspace_path: 工作区路径
            user_id: 用户ID（用于审计）

        Returns:
            执行结果字典

        """
        start_time = time.time()

        temp_mount = None

        try:
            # 1. 准备挂载点
            # 创建临时挂载点以支持可能的写操作
            temp_mount = tempfile.mkdtemp(prefix="sandbox_mount_")

            # 2. 验证路径安全性 - 修复异常1: 路径不存在或不可访问
            if not workspace_path.exists():
                raise ConfigurationError(f"工作区路径不存在: {workspace_path}")

            if not workspace_path.is_dir():
                raise ConfigurationError(f"工作区路径不是目录: {workspace_path}")

            workspace_resolved = workspace_path.resolve()
            logger.info(f"[SANDBOX] 工作区路径: {workspace_resolved}")

            # 检查路径长度和安全性
            if len(str(workspace_resolved)) > 4096:
                raise ConfigurationError(
                    f"工作区路径过长: {len(str(workspace_resolved))} characters",
                )

            # 3. 准备卷挂载 - 修复异常2: 路径过长或包含特殊字符
            # 验证挂载模式
            if self.config.workspace_mount_mode not in ("ro", "rw"):
                raise ConfigurationError(f"无效的挂载模式: {self.config.workspace_mount_mode}")

            volumes = {
                str(workspace_resolved): {
                    "bind": "/workspace",
                    "mode": self.config.workspace_mount_mode,
                },
                temp_mount: {"bind": "/tmp", "mode": "rw"},
            }

            # 4. 准备环境变量 (Docker容器内通常是Linux环境)
            environment = {
                "WORKSPACE": "/workspace",
                "HOME": "/tmp",
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",  # 容器内Linux路径
                "TERM": "xterm",
            }

            # 5. 创建容器并执行 - 修复异常3: 镜像不存在或timeout命令缺失
            logger.info(f"[SANDBOX] 执行命令: {command[:100]}")

            # 检查timeout命令是否可用
            timeout_cmd = "timeout"
            if self.config.timeout > 0:
                timeout_cmd = f"timeout {self.config.timeout}s"

            # 使用run方法（自动删除容器）
            try:
                output = self.client.containers.run(
                    image=self.config.image,
                    command=["sh", "-c", f"{timeout_cmd} {command}"],
                    volumes=volumes,
                    environment=environment,
                    mem_limit=self.config.memory_limit,
                    cpu_quota=self.config.cpu_quota,
                    cpu_period=self.config.cpu_period,
                    pids_limit=self.config.pids_limit,
                    network_disabled=self.config.network_disabled,
                    read_only=self.config.read_only_root,
                    # 安全选项
                    cap_drop=["ALL"],  # 移除所有capabilities
                    security_opt=["no-new-privileges"],
                    # 自动删除容器
                    remove=True,
                    # 捕获输出
                    stdout=True,
                    stderr=True,
                    detach=False,
                    # 添加超时保护
                    # runtime_timeout=self.config.timeout + 10 if self.config.timeout > 0 else 60
                )
            except docker.errors.ImageNotFound:
                # 尝试拉取镜像
                logger.warning(f"[SANDBOX] 镜像不存在，尝试拉取: {self.config.image}")
                try:
                    self.client.images.pull(self.config.image)
                    # 重新尝试执行
                    output = self.client.containers.run(
                        image=self.config.image,
                        command=["sh", "-c", f"{timeout_cmd} {command}"],
                        volumes=volumes,
                        environment=environment,
                        mem_limit=self.config.memory_limit,
                        cpu_quota=self.config.cpu_quota,
                        cpu_period=self.config.cpu_period,
                        pids_limit=self.config.pids_limit,
                        network_disabled=self.config.network_disabled,
                        read_only=self.config.read_only_root,
                        cap_drop=["ALL"],
                        security_opt=["no-new-privileges"],
                        remove=True,
                        stdout=True,
                        stderr=True,
                        detach=False,
                    )
                except docker.errors.ImageNotFound:
                    # 镜像拉取后仍然找不到
                    raise DockerConnectionError(f"镜像不存在且拉取失败: {self.config.image}")
                except docker.errors.APIError as e:
                    # Docker API错误（网络、权限等）
                    raise DockerConnectionError(f"Docker API错误（拉取镜像时）: {e}")
            except docker.errors.ContainerError as e:
                if "exit code: 137" in str(e) or "OOM" in str(e):
                    raise ResourceLimitError(f"容器因内存不足被终止: {e}")
                if "exit code: 124" in str(e):
                    raise SandboxTimeoutError(f"容器执行超时: {e}")
                raise SandboxError(f"容器执行失败: {e}")
            except docker.errors.APIError as e:
                raise SandboxError(f"Docker API错误: {e}")

            # 6. 解析输出
            # output是容器的stdout和stderr的组合
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            elif output is None:
                output = ""

            # 由于使用了detach=False和remove=True，容器已经被删除
            # 我们需要通过捕获的输出来判断结果
            exit_code = 0  # 如果没有抛出异常，假设成功
            stdout = output
            stderr = ""

            execution_time = int((time.time() - start_time) * 1000)

            # 7. 记录审计日志 - 修复异常4: 审计日志写入失败
            # LEGITIMATE TOLERANCE: 审计日志失败不应影响命令执行结果
            try:
                self._audit_log(
                    user_id=user_id,
                    command=command,
                    exit_code=exit_code,
                    execution_time=execution_time,
                )
            except OSError as audit_error:
                # 文件系统错误（权限、磁盘空间等）
                logger.warning(f"[SANDBOX] 审计日志记录失败（文件系统错误）: {audit_error}")
            except (TypeError, ValueError) as audit_error:
                # 日志数据格式错误
                logger.warning(f"[SANDBOX] 审计日志记录失败（数据格式错误）: {audit_error}")

            logger.info(f"[SANDBOX] 命令执行成功: exit_code={exit_code}, time={execution_time}ms")

            return {
                "success": True,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "execution_time": execution_time,
                "workspace": str(workspace_resolved),
            }

        except docker.errors.ContainerError as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.exception("[SANDBOX] 容器执行错误: ")

            # 尝试从错误中提取stderr
            stderr = str(e)
            stdout = ""

            return {
                "success": False,
                "error": str(e),
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": e.exit_status if hasattr(e, "exit_status") else -1,
                "execution_time": execution_time,
            }

        except (ConfigurationError, SandboxError, DockerConnectionError):
            # 自定义异常直接抛出（Fast Fail）
            raise
        except Exception as e:
            # 未知错误 - 记录详细信息并返回错误结果
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"[SANDBOX] 沙箱执行失败（未知错误）: {e}", exc_info=True)

            return {
                "success": False,
                "error": f"Sandbox execution failed: {e!s}",
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "execution_time": execution_time,
            }

        finally:
            # 清理临时挂载点 - 修复异常5: 临时目录清理失败
            # LEGITIMATE TOLERANCE: 清理失败不应影响命令执行结果
            if temp_mount and Path(temp_mount).exists():
                try:
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            shutil.rmtree(temp_mount)
                            logger.debug(f"[SANDBOX] 清理临时挂载点: {temp_mount}")
                            break
                        except PermissionError as pe:
                            if attempt == max_retries - 1:
                                # 最后一次尝试仍然失败
                                logger.exception(f"[SANDBOX] 无法清理临时挂载点（权限不足）: {pe}")
                                # 尝试标记为待删除（见下方）
                                raise
                            logger.warning(f"[SANDBOX] 清理重试 {attempt + 1}/{max_retries}: {pe}")
                            time.sleep(1)
                        except OSError as ose:
                            # 文件系统错误（文件被占用、只读文件系统等）
                            logger.warning(f"[SANDBOX] 清理临时挂载点失败（文件系统错误）: {ose}")
                            break
                except Exception as e:
                    logger.warning(f"[SANDBOX] 无法清理临时挂载点 {temp_mount}: {e}")
                    # 标记为删除，下次启动时清理
                    try:
                        flag_path = Path(f"{temp_mount}.delete_flag")
                        with flag_path.open("w", encoding="utf-8") as f:
                            f.write(f"待删除目录: {temp_mount}")
                        logger.info(f"[SANDBOX] 标记临时挂载点待删除: {temp_mount}")
                    except OSError as flag_error:
                        # 标记文件创建失败也容忍
                        logger.exception(f"[SANDBOX] 无法创建删除标记: {flag_error}")

    def _audit_log(self, user_id: str, command: str, exit_code: int, execution_time: int):
        """记录审计日志"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "command": command[:1000],  # 限制长度
            "exit_code": exit_code,
            "execution_time_ms": execution_time,
            "sandbox_config": {
                "image": self.config.image,
                "memory_limit": self.config.memory_limit,
                "timeout": self.config.timeout,
            },
        }

        # 写入审计日志文件 - 修复异常: 日志目录权限问题
        try:
            # 使用更安全的方式确定日志路径

            audit_log_path = Path("logs/sandbox_audit.log")

            # 确保日志目录存在且有正确的权限
            try:
                audit_log_path.parent.mkdir(exist_ok=True, mode=0o755)
                logger.debug(f"[SANDBOX] 日志目录创建/确认: {audit_log_path.parent}")
            except (PermissionError, OSError) as dir_error:
                # 如果无法创建标准日志目录，使用临时目录
                temp_log_dir = Path(tempfile.gettempdir()) / "dawei_logs" / "sandbox"
                try:
                    temp_log_dir.mkdir(exist_ok=True, mode=0o755)
                except (PermissionError, OSError):
                    # 临时目录也无法创建，使用系统临时目录
                    temp_log_dir = Path(tempfile.gettempdir())
                    logger.warning(f"[SANDBOX] 使用系统临时目录: {temp_log_dir}")
                audit_log_path = temp_log_dir / "sandbox_audit.log"
                logger.warning(
                    f"[SANDBOX] 使用备用日志目录: {audit_log_path} (原目录错误: {dir_error})",
                )

            # 写入日志文件，使用追加模式确保数据不丢失
            with Path(audit_log_path, "a").open(encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")

            logger.debug(f"[SANDBOX] 审计日志已写入: {audit_log_path}")

        except (PermissionError, OSError) as pe:
            # 文件系统错误（权限、磁盘空间等）
            logger.exception(f"[SANDBOX] 审计日志文件系统错误: {pe}")
            # 尝试写入系统临时目录作为最后的尝试（跨平台兼容）
            try:
                temp_dir = tempfile.gettempdir()
                temp_audit_path = Path(temp_dir) / "sandbox_audit.log"
                with Path(temp_audit_path, "a").open(encoding="utf-8") as f:
                    f.write(json.dumps(log_entry) + "\n")
                logger.info(f"[SANDBOX] 审计日志已写入系统临时文件: {temp_audit_path}")
            except (PermissionError, OSError) as temp_error:
                # 所有尝试都失败 - 只能记录到日志
                logger.exception(f"[SANDBOX] 所有审计日志写入尝试均失败: {temp_error}")
        except (TypeError, ValueError) as json_error:
            # JSON序列化错误（数据格式问题）
            logger.exception(f"[SANDBOX] 审计日志JSON序列化失败: {json_error}")

    async def execute_command_async(
        self,
        command: str,
        workspace_path: Path,
        user_id: str = "unknown",
    ) -> dict[str, Any]:
        """异步执行命令"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.execute_command(command, workspace_path, user_id),
        )

    def health_check(self) -> bool:
        """健康检查"""
        try:
            self.client.ping()
            return True
        except docker.errors.DockerException as e:
            # Docker daemon 未运行或无法连接
            logger.warning(f"[SANDBOX] Docker daemon不可用: {e}")
            return False
        except (ConnectionError, OSError) as e:
            # 网络或操作系统级别错误
            logger.warning(f"[SANDBOX] Docker连接错误: {e}")
            return False
