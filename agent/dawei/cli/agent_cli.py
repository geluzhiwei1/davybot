# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei CLI - Fire命令行接口

使用Python Fire库提供友好的命令行界面。
"""

import io
import sys

import fire

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    # Only wrap if stdout/stderr have buffer attribute (avoid double-wrapping)
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dawei.cli.runner import run_agent_sync
from dawei.logg.logging import get_logger


class CLIMain:
    """Dawei CLI主类

    提供命令行工具来直接调用Agent，无需HTTP/WebSocket。

    使用示例:
        # 运行agent（简化格式）
        python -m dawei.cli run ./my-workspace openai/gpt-4 code "创建一个hello world程序"

        # 运行agent（完整参数）
        python -m dawei.cli run --workspace ./my-workspace --llm openai/gpt-4 --mode code --message "创建一个hello world程序"

        # 启用详细日志
        python -m dawei.cli run ./my-workspace openai/gpt-4 ask "什么是专利？" --verbose
    """

    def run(
        self,
        workspace: str,
        llm: str,
        mode: str,
        message: str,
        verbose: bool = False,
        timeout: int = 1800,
    ) -> None:
        """运行Agent任务

        Args:
            workspace: 工作区路径（相对或绝对路径）
            llm: LLM模型名称（如 openai/gpt-4, deepseek/deepseek-chat, ollama/llama2）
            mode: Agent模式（code, ask, architect, plan, debug, orchestrator）
            message: 用户消息或指令
            verbose: 是否输出详细日志（默认: False）
            timeout: 执行超时时间（秒，默认: 1800，即30分钟）

        示例:
            # 代码生成
            cli run ./test openai/gpt-4 code "创建一个快速排序算法"

            # 问答
            cli run ./test deepseek/deepseek-chat ask "什么是专利？"

            # 架构设计
            cli run ./test openai/gpt-4 architect "设计一个RESTful API"

            # 启用详细日志
            cli run ./test openai/gpt-4 code "创建hello world" --verbose

        """
        get_logger(__name__)

        # 打印开始信息
        print("=" * 70)
        print("🤖 Dawei Agent CLI")
        print("=" * 70)
        print(f"📁 Workspace: {workspace}")
        print(f"🧠 LLM: {llm}")
        print(f"🎯 Mode: {mode}")
        print(f"💬 Message: {message[:80]}{'...' if len(message) > 80 else ''}")
        print(f"⏱️  Timeout: {timeout}s")
        if verbose:
            print("📝 Verbose mode: Enabled")
        print("=" * 70)
        print()

        try:
            # 执行Agent
            result = run_agent_sync(
                workspace=workspace,
                llm=llm,
                mode=mode,
                message=message,
                verbose=verbose,
                timeout=timeout,
            )

            # 打印结果
            print()
            print("=" * 70)
            if result["success"]:
                print("✅ Execution completed successfully")
                print(f"⏱️  Duration: {result['duration']:.2f} seconds")
            else:
                print("❌ Execution failed")
                print(f"📄 Message: {result['message']}")
                if result.get("error"):
                    print(f"❌ Error: {result['error']}")
            print("=" * 70)

            # 设置退出码
            sys.exit(0 if result["success"] else 1)

        except KeyboardInterrupt:
            print()
            print("=" * 70)
            print("⚠️  Execution interrupted by user")
            print("=" * 70)
            sys.exit(130)  # 标准的interrupt退出码

        # Fast fail on specific, actionable errors
        except (FileNotFoundError, ValueError) as e:
            print()
            print("=" * 70)
            print("❌ Configuration Error")
            print(f"❌ Error: {e}")
            print("=" * 70)
            if verbose:
                import traceback

                print("\n📋 Stack trace:")
                traceback.print_exc()
            sys.exit(1)

        except OSError as e:
            print()
            print("=" * 70)
            print("❌ System Error")
            print(f"❌ Error: {e}")
            print("=" * 70)
            sys.exit(1)

        except Exception as e:
            # This is a CLI entry point - broad exception handling is acceptable here
            # to provide user-friendly error messages before exiting
            print()
            print("=" * 70)
            print("❌ Unexpected error occurred")
            print(f"❌ Error: {e}")
            print("=" * 70)
            if verbose:
                import traceback

                print("\n📋 Stack trace:")
                traceback.print_exc()
            sys.exit(1)

    def version(self) -> None:
        """显示版本信息"""
        from dawei.cli import __version__

        print(f"Dawei CLI version: {__version__}")
        print(f"Python version: {sys.version}")

    def help(self) -> None:
        """显示帮助信息"""
        print("""
🤖 Dawei CLI - Agent命令行工具

📚 命令列表:
    run              运行Agent任务（主要命令）
    version          显示版本信息
    help             显示此帮助信息

📖 主要命令用法:
    python -m dawei.cli run <workspace> <llm> <mode> <message> [options]

    参数说明:
        workspace    工作区路径（必需）
        llm          LLM模型名称（必需）
                    示例: openai/gpt-4, deepseek/deepseek-chat, ollama/llama2
        mode         Agent模式（必需）
                    可选值: code, ask, architect, plan, debug, orchestrator
        message      用户消息或指令（必需）

    可选参数:
        --verbose    启用详细日志
        --timeout    超时时间（秒），默认1800（30分钟）

💡 使用示例:

    # 代码生成
    python -m dawei.cli run ./my-workspace openai/gpt-4 code "创建一个快速排序算法"

    # 问答
    python -m dawei.cli run ./my-workspace deepseek/deepseek-chat ask "什么是专利？"

    # 架构设计
    python -m dawei.cli run ./my-workspace openai/gpt-4 architect "设计一个RESTful API"

    # 启用详细日志
    python -m dawei.cli run ./my-workspace openai/gpt-4 code "创建hello world" --verbose

    # 使用完整参数名
    python -m dawei.cli run \\
        --workspace ./my-workspace \\
        --llm openai/gpt-4 \\
        --mode code \\
        --message "创建一个快速排序算法" \\
        --verbose \\
        --timeout 3600

📖 更多信息:
    查看在线文档: https://github.com/your-repo/dawei
    报告问题: https://github.com/your-repo/dawei/issues
        """)


def main() -> None:
    """CLI主入口点

    使用Fire将CLIMain类暴露为命令行接口
    """
    # 配置日志级别
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stderr)],
    )

    # 启动Fire CLI
    fire.Fire(CLIMain, name="dawei-cli")


if __name__ == "__main__":
    main()
