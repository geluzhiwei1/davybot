#!/usr/bin/env python3
# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Dawei TUI - Interactive Demo

Demonstrates TUI features without running full Agent.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dawei.core.events import TaskEventType
from dawei.tui.utils.message_formatter import MessageFormatter


def demo_message_formatter():
    """Demonstrate message formatting capabilities"""
    print("\n" + "=" * 60)
    print("Message Formatter Demo")
    print("=" * 60)

    formatter = MessageFormatter()

    # User message
    print("\n[User Message]")
    print(formatter.format_user_message("创建一个Python函数"))

    # Assistant message
    print("\n[Assistant Message]")
    print(formatter.format_assistant_message("我会为你创建一个函数..."))

    # System message
    print("\n[System Message]")
    print(formatter.format_system_message("Switching to code mode"))

    # Error message
    print("\n[Error Message]")
    print(formatter.format_error_message("File not found", "read_file"))

    # Info message
    print("\n[Info Message]")
    print(formatter.format_info_message("Task completed successfully"))

    # Tool call
    print("\n[Tool Call]")
    print(formatter.format_tool_call("write_to_file", {"path": "test.py"}))

    # Tool result
    print("\n[Tool Result]")
    print(formatter.format_tool_result("write_to_file", True, 0.15))

    # Thinking
    print("\n[Thinking]")
    print(formatter.format_thinking("Analyzing requirements..."))

    # Mode switch
    print("\n[Mode Switch]")
    print(formatter.format_mode_switch("ask", "code"))

    # Model selection
    print("\n[Model Selection]")
    print(formatter.format_model_selection("gpt-4", "Code generation task", 0.95))

    # Truncation
    print("\n[Truncation]")
    long_text = "This is a very long text that should be truncated" * 10
    print(f"Original length: {len(long_text)}")
    print(f"Truncated: {formatter.truncate(long_text, 50)}")

    # Code block
    print("\n[Code Block]")
    print(formatter.format_code_block("print('Hello, World!')", "python"))

    # File reference
    print("\n[File Reference]")
    print(formatter.format_file_reference("src/main.py", (10, 20)))


def demo_event_types():
    """Demonstrate available event types"""
    print("\n" + "=" * 60)
    print("Event Types Demo")
    print("=" * 60)

    events = [
        ("Content Stream", TaskEventType.CONTENT_STREAM),
        ("Reasoning", TaskEventType.REASONING),
        ("Tool Call Start", TaskEventType.TOOL_CALL_START),
        ("Tool Call Result", TaskEventType.TOOL_CALL_RESULT),
        ("Task Started", TaskEventType.TASK_STARTED),
        ("Task Completed", TaskEventType.TASK_COMPLETED),
        ("Mode Switched", TaskEventType.MODE_SWITCHED),
        ("Error Occurred", TaskEventType.ERROR_OCCURRED),
        ("Model Selected", TaskEventType.MODEL_SELECTED),
        ("Files Referenced", TaskEventType.FILES_REFERENCED),
    ]

    print("\nAvailable Event Types:\n")
    for name, event_type in events:
        print(f"  • {name:20s} → {event_type.value}")

    print("\nThese events are subscribed by AgentBridge and forwarded to UI.")


def demo_config():
    """Demonstrate configuration"""
    print("\n" + "=" * 60)
    print("Configuration Demo")
    print("=" * 60)

    from dawei.tui.config import create_tui_config

    config = create_tui_config(
        workspace="./demo-workspace",
        llm="deepseek/deepseek-chat",
        mode="code",
        verbose=True,
        refresh_rate=0.1,
    )

    print("\nConfiguration:")
    print(f"  Workspace: {config.workspace}")
    print(f"  Absolute Path: {config.workspace_absolute}")
    print(f"  LLM Model: {config.llm}")
    print(f"  Mode: {config.mode}")
    print(f"  Refresh Rate: {config.refresh_rate}s")
    print(f"  Show Thinking: {config.show_thinking}")
    print(f"  Show Tools: {config.show_tools}")

    is_valid, error = config.validate()
    print(f"\nValidation: {'✓ Valid' if is_valid else f'✗ {error}'}")


async def demo_ui_components():
    """Demonstrate UI component concepts"""
    print("\n" + "=" * 60)
    print("UI Components Demo")
    print("=" * 60)

    components = [
        ("ChatArea", "Display chat history with streaming support"),
        ("InputBox", "User input with command history"),
        ("StatusBar", "Show status, mode, model"),
        ("ThinkingPanel", "Display Agent reasoning"),
        ("ToolPanel", "Show tool execution"),
    ]

    print("\nUI Components:\n")
    for name, description in components:
        print(f"  [bold cyan]{name}[/bold cyan]")
        print(f"    {description}")

    print("\nLayout:\n")
    print("  ┌─────────────────────────────────────────────┐")
    print("  │              Header                         │")
    print("  ├─────────────────────┬───────────────────────┤")
    print("  │  Chat Area (70%)    │  Right Panel (30%)    │")
    print("  │  - Messages         │  - Status Bar         │")
    print("  │  - Streaming        │  - Thinking           │")
    print("  │  - Errors           │  - Tools              │")
    print("  ├─────────────────────┴───────────────────────┤")
    print("  │  Input Box                                  │")
    print("  └─────────────────────────────────────────────┘")


def demo_workflow():
    """Demonstrate typical workflow"""
    print("\n" + "=" * 60)
    print("Typical Workflow Demo")
    print("=" * 60)

    workflow = [
        ("1. User Input", "User types message in InputBox"),
        ("2. Submit", "InputBox submits message to TUIApp"),
        ("3. Forward", "TUIApp forwards to AgentBridge"),
        ("4. Process", "AgentBridge calls agent.process_message()"),
        ("5. Emit Events", "Agent emits events to CORE_EVENT_BUS"),
        ("6. Subscribe", "AgentBridge subscribes and forwards to queue"),
        ("7. Poll", "TUIApp polls queue for events"),
        ("8. Update UI", "TUIApp routes events to UI components"),
        ("9. Display", "Components update with new information"),
    ]

    print("\nEvent Flow:\n")
    for step, description in workflow:
        print(f"  {step:15s} → {description}")

    print("\nKey Points:")
    print("  • No WebSocket - direct Agent integration")
    print("  • Event-driven - real-time updates")
    print("  • Async-first - full asyncio support")
    print("  • Streaming - see responses as they arrive")


async def main():
    """Run all demos"""
    print("\n" + "=" * 60)
    print("Dawei TUI - Interactive Demo")
    print("=" * 60)
    print("\nThis demo showcases TUI features without running the Agent.")
    print("Press Ctrl+C to exit at any time.\n")

    try:
        # Message formatter demo
        demo_message_formatter()
        await asyncio.sleep(0.5)

        # Event types demo
        demo_event_types()
        await asyncio.sleep(0.5)

        # Configuration demo
        demo_config()
        await asyncio.sleep(0.5)

        # UI components demo
        await demo_ui_components()
        await asyncio.sleep(0.5)

        # Workflow demo
        demo_workflow()

        # Summary
        print("\n" + "=" * 60)
        print("Demo Complete!")
        print("=" * 60)
        print("\nTo run the actual TUI:")
        print("  python -m dawei.tui --workspace ./my-workspace")
        print("\nOr use the quick start script:")
        print("  python dawei/tui/quick_start.py")
        print("\nPress Ctrl+H in the TUI for help\n")

        return 0

    except KeyboardInterrupt:
        print("\n\nDemo interrupted.")
        return 0
    except ImportError as e:
        print(f"\n❌ Import Error: {e}")
        print("\nMake sure you're running from the project root directory.")
        return 1
    except (AttributeError, NameError) as e:
        print(f"\n❌ Demo Error: {e}")
        print("\nThis may indicate missing or incompatible components.")
        return 1
    except Exception as e:
        # Demo script entry point - broad exception handling acceptable
        # for graceful error reporting
        print(f"\n❌ Unexpected Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
