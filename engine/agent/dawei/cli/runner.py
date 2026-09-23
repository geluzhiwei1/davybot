# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Agent执行封装器

负责初始化Agent并执行任务，不经过HTTP/WebSocket。
"""

import asyncio
import os
import time
from pathlib import Path
from typing import List, Dict, Any

from dawei.agentic.agent import Agent
from dawei.cli.config import CLIConfig
from dawei.entity.user_input_message import UserInputText
from dawei.logg.logging import get_logger
from dawei.tools.custom_tools.async_utils import set_main_loop
from dawei.workspace.user_workspace import UserWorkspace


def _acquire_workspace_run_lock(workspace_path: str) -> tuple[int | None, str | None]:
    """获取工作区级运行锁（防同工作区并发 run）。

    【2026-09-21】同一工作区并发 `dawei agent run` 会交叉写 task_graph /
    conversations / output（tui-review 实测 4 个重复 run 同时在跑，产物互踩）。
    flock(LOCK_EX|LOCK_NB) 排他：后到者立即失败退出；锁随进程退出自动释放，
    无陈旧锁问题。锁文件写入持锁 pid 便于诊断。

    Returns:
        (fd, None): 成功持锁，fd 由调用方持有并在结束时关闭
        (None, error): 已被持锁 / 获取失败（FAST FAIL，附原因）
        (None, None): 显式跳过（DAWEI_RUN_LOCK=0）或平台无 fcntl
    """
    if os.environ.get("DAWEI_RUN_LOCK", "1").lower() in ("0", "false", "no", "off"):
        return None, None
    try:
        import fcntl
    except ImportError:  # 非 POSIX 平台无 flock，放行
        return None, None

    lock_dir = Path(workspace_path) / ".dawei" / ".locks"
    lock_file = lock_dir / "agent-run.lock"
    fd: int | None = None
    try:
        lock_dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(lock_file, os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        holder = "?"
        try:
            holder = lock_file.read_text(encoding="utf-8").strip() or "?"
        except OSError:
            pass
        if fd is not None:
            os.close(fd)
        return None, (f"工作区已有 agent run 在执行（持锁 pid={holder}）：{workspace_path}。请等待其完成后再运行；若确认持锁进程已死亡，删除 {lock_file} 后重试。如确需并发（不推荐），设 DAWEI_RUN_LOCK=0。")
    except OSError as e:
        # 锁目录不可写等：FAST FAIL——宁可不跑，不可并发写坏工作区
        if fd is not None:
            os.close(fd)
        return None, f"获取工作区运行锁失败: {e}"

    try:
        os.truncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
    except OSError:
        pass  # pid 写失败仅影响诊断信息，不影响锁语义
    return fd, None


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
        self._execution_result: Dict[str, Any] = {}

    async def initialize(self) -> None:
        """初始化工作区和Agent"""
        self.logger.info(f"Initializing workspace: {self.config.workspace_absolute}")

        # 1. 创建UserWorkspace
        self.user_workspace = UserWorkspace(workspace_path=self.config.workspace_absolute)

        # 2. 初始化workspace
        await self.user_workspace.initialize()
        self.logger.info("Workspace initialized successfully")

        # 3. 创建Agent（使用默认执行引擎）
        agent_config: Dict[str, Any] = {
            "enable_auto_mode_switch": False,  # CLI模式不需要自动切换
            "enable_skills": True,
            "enable_mcp": False,  # CLI模式默认不启用MCP
            "max_iterations": 100,
            "checkpoint_interval": 60.0,
        }
        if self.config.llm:
            agent_config["llm_model"] = self.config.llm

        self.agent = await Agent.create_with_default_engine(
            user_workspace=self.user_workspace,
            config=agent_config,
        )

        # 4. 设置Agent mode
        if self.config.verbose:
            self.logger.info(f"Setting agent mode to: {self.config.mode}")
        self.user_workspace.mode = self.config.mode

        # 5. 设置LLM provider (如果指定了 --llm 则覆盖 workspace 默认)
        if self.config.llm:
            if self.config.verbose:
                self.logger.info(f"Setting LLM provider to: {self.config.llm}")
            self.user_workspace.llm_manager.set_provider(self.config.llm)
        else:
            # 使用 workspace 默认 LLM 配置
            default_config = self.user_workspace.llm_manager.get_current_config_name()
            if self.config.verbose:
                self.logger.info(f"Using workspace default LLM: {default_config}")

        self.logger.info("Agent initialized successfully")

    async def run(self) -> Dict[str, Any]:
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
            # 0. 注册主事件循环（对齐 server_app lifespan 的 bug#5 修复）：
            # CLI 模式下同步 MCP 工具经 run_on_main_loop 把协程投递回主
            # loop；不注册则每个 MCP 调用都报 "main loop not registered"
            # （server 启动时注册过，CLI 路径此前缺失）。
            set_main_loop(asyncio.get_running_loop())

            # 1. 确保已初始化
            if not self.agent:
                await self.initialize()

            self.logger.info("=" * 60)
            self.logger.info("Starting agent execution")
            self.logger.info(f"  Mode: {self.config.mode}")
            self.logger.info(f"  LLM: {self.config.llm or 'workspace default'}")
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

            # 4.5 【FAST FAIL】根任务终态决定退出码：process_message 正常返回
            # 不代表根成功（2026-09-23 UC-ENG-002 七跑实锤：根 212k 触崖 FAILED，
            # CLI 仍报 completed/rc=0，用例断言与真实状态脱节）。best-effort 查询，
            # 读取失败不吞执行成功。
            root_status: str | None = None
            try:
                task_graph = getattr(self.user_workspace, "task_graph", None)
                if task_graph is not None:
                    root_task = await task_graph.get_root_task()
                    if root_task is not None and getattr(root_task, "status", None) is not None:
                        root_status = str(getattr(root_task.status, "value", root_task.status))
            except Exception:  # noqa: BLE001 — 状态查询失败不改变成功语义
                self.logger.debug("run: failed to read root task terminal status", exc_info=True)

            duration = time.time() - start_time
            if root_status in ("failed", "aborted", "cancelled"):
                self.logger.warning(f"Root task ended in terminal state '{root_status}' (duration {duration:.0f}s)")
                return {
                    "success": False,
                    "message": f"Root task ended in '{root_status}'",
                    "duration": duration,
                    "error": f"root task terminal status: {root_status}",
                }

            # 5. 返回成功结果
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
    llm: str | None,
    mode: str,
    message: str,
    verbose: bool = False,
    timeout: int = 1800,
) -> Dict[str, Any]:
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

    # 【2026-09-21 运行锁】同工作区并发 run 排他（见 _acquire_workspace_run_lock）
    lock_fd, lock_error = _acquire_workspace_run_lock(config.workspace_absolute)
    if lock_error is not None:
        return {
            "success": False,
            "message": "Workspace is locked by another run",
            "duration": 0,
            "error": lock_error,
        }

    # 创建runner
    runner = AgentRunner(config)

    try:
        # 执行
        return await runner.run()

    finally:
        # 确保清理资源
        await runner.cleanup()
        if lock_fd is not None:
            os.close(lock_fd)


def run_agent_sync(
    workspace: str,
    llm: str | None,
    mode: str,
    message: str,
    verbose: bool = False,
    timeout: int = 1800,
) -> Dict[str, Any]:
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


# ==================== Evolution Mode ====================


async def run_evolution_directly(
    workspace: str,
    llm: str | None,
    message: str,
    verbose: bool = False,
    timeout: int = 1800,
    dao_path: str | None = None,
) -> Dict[str, Any]:
    """直接运行Evolution Cycle（同步阻塞，等待cycle完成）

    与start_cycle()不同，此函数会阻塞直到整个PDCA cycle完成或失败。

    Args:
        workspace: 工作区路径
        llm: LLM模型名称
        message: 用户消息（作为evolution目标）
        verbose: 是否输出详细日志
        timeout: 执行超时时间（秒）
        dao_path: 自定义dao文件路径，覆盖默认的workspace/dao.md

    Returns:
        执行结果字典，包含：
        - success: 是否成功
        - message: 执行消息
        - cycle_id: evolution cycle ID
        - duration: 执行时长（秒）
        - error: 错误信息（如果失败）

    """
    start_time = time.time()
    log = get_logger(__name__)

    try:
        # 0. 解析路径为绝对路径，加载.env
        workspace_path = str(Path(workspace).resolve())
        from dotenv import find_dotenv, load_dotenv

        env_path = find_dotenv()
        if env_path:
            load_dotenv(env_path, override=True)
        else:
            env_fallback = Path(workspace_path) / ".env"
            if env_fallback.exists():
                load_dotenv(env_fallback, override=True)

        # 1. 创建并初始化UserWorkspace
        log.info(f"[EVOLUTION_CLI] Initializing workspace: {workspace_path}")
        user_workspace = UserWorkspace(workspace_path=workspace_path)
        await user_workspace.initialize()

        # 2. 设置LLM provider (如果指定了 --llm 则覆盖 workspace 默认)
        if llm:
            user_workspace.llm_manager.set_provider(llm)
            if verbose:
                log.info(f"[EVOLUTION_CLI] LLM provider set to: {llm}")
        else:
            default_config = user_workspace.llm_manager.get_current_config_name()
            if verbose:
                log.info(f"[EVOLUTION_CLI] Using workspace default LLM: {default_config}")

        # 3. 创建EvolutionCycleManager
        from dawei.evolution.evolution_manager import EvolutionCycleManager

        manager = EvolutionCycleManager(user_workspace, dao_path=dao_path)
        log.info("[EVOLUTION_CLI] EvolutionCycleManager created")

        # 4. 直接运行phases（同步等待完成），而非start_cycle（异步后台）
        cycle_id = await manager._generate_cycle_id()
        await manager.storage.create_cycle_directory(cycle_id)
        prev_cycle_id = await manager.storage.get_latest_completed_cycle_id()

        task_graph = await manager._create_cycle_task_graph(cycle_id, prev_cycle_id)
        manager._task_graphs[cycle_id] = task_graph

        metadata = manager._init_metadata(cycle_id, prev_cycle_id)
        metadata["context"]["task_graph_id"] = f"evolution-{cycle_id}"
        await manager.storage.save_metadata(cycle_id, metadata)

        log.info(f"[EVOLUTION_CLI] Starting evolution cycle {cycle_id} (blocking)")

        # 5. 同步执行phases（带超时）
        try:
            await asyncio.wait_for(
                manager._run_phases(cycle_id, prev_cycle_id, task_graph),
                timeout=timeout,
            )
        except TimeoutError:
            log.exception(f"[EVOLUTION_CLI] Evolution cycle {cycle_id} timeout after {timeout}s")
            await manager.abort_cycle(cycle_id, reason=f"CLI timeout after {timeout}s")
            return {
                "success": False,
                "message": "Evolution cycle timeout",
                "cycle_id": cycle_id,
                "duration": time.time() - start_time,
                "error": f"Timeout after {timeout} seconds",
            }

        # 6. 读取最终状态
        final_metadata = await manager.storage.load_metadata(cycle_id)
        duration = time.time() - start_time

        if final_metadata["status"] == "completed":
            log.info(f"[EVOLUTION_CLI] Evolution cycle {cycle_id} completed in {duration:.2f}s")
            return {
                "success": True,
                "message": "Evolution cycle completed successfully",
                "cycle_id": cycle_id,
                "duration": duration,
                "error": None,
            }
        if final_metadata["status"] == "aborted":
            log.info(f"[EVOLUTION_CLI] Evolution cycle {cycle_id} aborted")
            return {
                "success": False,
                "message": "Evolution cycle aborted",
                "cycle_id": cycle_id,
                "duration": duration,
                "error": final_metadata.get("abort_reason", "Aborted"),
            }
        log.info(f"[EVOLUTION_CLI] Evolution cycle {cycle_id} ended with status: {final_metadata['status']}")
        return {
            "success": False,
            "message": f"Evolution cycle ended with status: {final_metadata['status']}",
            "cycle_id": cycle_id,
            "duration": duration,
            "error": final_metadata.get("abort_reason", "Unknown status"),
        }

    except Exception as e:
        log.error(f"[EVOLUTION_CLI] Evolution cycle failed: {e}", exc_info=True)
        return {
            "success": False,
            "message": "Evolution cycle failed",
            "cycle_id": None,
            "duration": time.time() - start_time,
            "error": str(e),
        }


def run_evolution_sync(
    workspace: str,
    llm: str | None,
    message: str,
    verbose: bool = False,
    timeout: int = 1800,
    dao_path: str | None = None,
) -> Dict[str, Any]:
    """同步版本的Evolution执行器（用于Click CLI）

    Args:
        workspace: 工作区路径
        llm: LLM模型名称
        message: 用户消息（evolution目标）
        verbose: 是否输出详细日志
        timeout: 执行超时时间（秒）
        dao_path: 自定义dao文件路径，覆盖默认的workspace/dao.md

    Returns:
        执行结果字典

    """
    return asyncio.run(
        run_evolution_directly(
            workspace=workspace,
            llm=llm,
            message=message,
            verbose=verbose,
            timeout=timeout,
            dao_path=dao_path,
        ),
    )
