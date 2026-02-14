# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""HelpScreen

Displays help information and keyboard shortcuts.
"""

from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static


class HelpScreen(Screen):
    """Help screen with keyboard shortcuts and commands"""

    BINDINGS = [
        ("q", "app.pop_screen", "Close"),
        ("escape", "app.pop_screen", "Close"),
    ]

    def compose(self):
        """Compose help screen"""
        yield Header()

        yield Vertical(
            Static(
                """[bold cyan]Dawei TUI - Help[/bold cyan]

[bold yellow]Keyboard Shortcuts:[/bold yellow]

  [bold green]Global:[/bold green]
    Ctrl+C / Ctrl+Q    Quit application
    ? (empty input)    Show this help screen
    Tab                Switch between panels
    Ctrl+P             Command palette
    Ctrl+R             Session history
    Ctrl+S             Save session
    Ctrl+L             Clear chat
    Ctrl+,             Settings

  [bold green]Input Box:[/bold green]
    Enter              Send message
    Type "/help"       Show this help screen (PowerShell-friendly!)
    Type "?"           Show this help screen (PowerShell-friendly!)
    Ctrl+U             Clear input
    Ctrl+W             Delete word

  [bold green]Navigation:[/bold green]
    Up / Down          Scroll chat history
    Page Up / Down     Scroll page
    Home / End         Jump to top/bottom

[bold yellow]Agent Modes (PDCA Cycle):[/bold yellow]

  [bold cyan]PDCA-Based Universal Agent System[/bold cyan]
  The agent uses a PDCA (Plan-Do-Check-Act) cycle that works
  across ALL domains: software, data, writing, research, business, etc.

  [bold green]🪃 Orchestrator[/bold green]
  - Intelligent coordinator for PDCA cycles
  - Decides when to use PDCA vs direct execution
  - Detects domain and task complexity
  - Manages mode transitions

  [bold green]📋 Plan[/bold green]
  - Understand requirements and explore context
  - Design solutions and create implementation plans
  - [bold]READ-ONLY mode[/bold] (except plan files)
  - Works for ANY domain: code, data, writing, research, business

  [bold green]⚙️ Do[/bold green]
  - Execute the plan systematically
  - Complete tasks step by step
  - Track progress and document results
  - Full execution capabilities

  [bold green]✓ Check[/bold green]
  - Verify results against goals
  - Assess quality and identify issues
  - Provide specific feedback
  - Validate outcomes

  [bold green]🚀 Act[/bold green]
  - Standardize successful approaches
  - Document learnings and create templates
  - Decide: complete task or start new cycle
  - Knowledge transfer and improvement

[bold yellow]Usage Examples:[/bold yellow]

  # Basic chat
  [dim]你好[/dim]

  # Code generation
  [dim]创建一个Python函数来计算斐波那契数列[/dim]

  # File operations
  [dim]读取README.md文件[/dim]

  # PDCA cycle example
  [dim]帮我分析这个项目并生成优化建议[/dim]

  # Complex tasks
  [dim]分析这个项目的结构并生成文档[/dim]

[bold yellow]UI Panels:[/bold yellow]

  [bold]Chat Area[/bold]       - Main conversation display
  [bold]Input Box[/bold]       - Type your messages here
  [bold]Status Bar[/bold]      - Agent status, mode, model
  [bold]Thinking Panel[/bold]  - Agent reasoning process
  [bold]Tool Panel[/bold]      - Tool execution info

[bold yellow]Configuration:[/bold yellow]

  Command-line options:
    --workspace, -w     Path to workspace (required)
    --llm, -l           LLM model to use
    --mode, -m          Agent mode (orchestrator|plan|do|check|act)
    --verbose, -v       Enable verbose logging
    --refresh-rate      UI refresh rate (default: 0.1s)

[bold yellow]Tips:[/bold yellow]

  • The agent uses PDCA cycles for complex tasks automatically
  • Orchestrator mode decides the best approach for your task
  • Plan mode is READ-ONLY (except for creating plan files)
  • File references are automatically detected: @path/to/file
  • The TUI connects directly to Agent (no WebSocket needed)
  • All events are streamed in real-time via CORE_EVENT_BUS
  • Type "/help" or "?" in the input box to show this help (works in PowerShell!)
  • Note: Ctrl+H and F1 may not work in PowerShell due to key interception

[bold dim]Press Q, Escape, or click Close button to exit[/bold dim]
""",
                id="help_content",
            ),
            # Add a close button
            Center(
                Button("Close", id="close_button", variant="primary"),
            ),
            id="help_container",
        )

        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events.

        Args:
            event: Button pressed event
        """
        if event.button.id == "close_button":
            self.app.pop_screen()
