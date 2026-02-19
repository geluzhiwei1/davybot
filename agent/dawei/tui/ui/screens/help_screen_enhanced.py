# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Enhanced HelpScreen

Improved help screen with better organization and styling using Textual 7.5.0 features.
"""

import Center
import Horizontal
import Vertical
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Markdown


class EnhancedHelpScreen(Screen):
    """Enhanced help screen with keyboard shortcuts and commands"""

    BINDINGS = [
        ("q", "app.pop_screen", "Close"),
        ("escape", "app.pop_screen", "Close"),
        ("ctrl+c", "app.pop_screen", "Close"),
    ]

    def compose(self):
        """Compose help screen with better layout"""
        yield Header()

        # Use Markdown widget for better rendering
        yield Vertical(
            Horizontal(
                Markdown(
                    self._get_help_content(),
                    id="help_markdown",
                ),
                id="help_content",
            ),
            Center(
                Button("Close Help", id="close_button", variant="primary"),
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

    def _get_help_content(self) -> str:
        """Get help content in Markdown format

        Returns:
            Markdown formatted help text
        """
        return """# Dawei TUI - Help

## 🔧 Keyboard Shortcuts

### Global
| Key | Action |
|-----|--------|
| `Ctrl+C` / `Ctrl+Q` | Quit application |
| `?` (empty input) | Show help screen |
| `Tab` | Switch between panels |
| `Ctrl+P` | Command palette |
| `Ctrl+R` | Session history |
| `Ctrl+S` | Save session |
| `Ctrl+L` | Clear chat |
| `Ctrl+,` | Settings |

### Input Box
| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Ctrl+U` | Clear input |
| `Ctrl+W` | Delete word |
| `Ctrl+A` | Move to start |
| `Ctrl+E` | Move to end |

### Navigation
| Key | Action |
|-----|--------|
| `↑` / `↓` | Scroll chat history |
| `Page Up/Down` | Scroll page |
| `Home` / `End` | Jump to top/bottom |

---

## 🤖 Agent Modes

| Mode | Description |
|------|-------------|
| **plan** | Read-only: Analysis only, no file modifications |
| **build** | Full mode: All operations enabled |
| **ask** | Question answering |
| **code** | Code writing and editing |
| **debug** | Error diagnosis and fixing |

---

## 💡 Usage Examples

### Basic Chat
```
你好
Hello, how are you?
```

### Code Generation
```
创建一个Python函数来计算斐波那契数列
Create a function to sort a list in Python
```

### File Operations
```
读取README.md文件
What files are in the current directory?
```

### Mode Switching
```
切换到ask模式
Switch to plan mode
```

### Complex Tasks
```
分析这个项目的结构并生成文档
Refactor this code for better performance
```

---

## 📊 UI Panels

| Panel | Description |
|-------|-------------|
| **Chat Area** | Main conversation display |
| **Input Box** | Type your messages here |
| **Status Bar** | Agent status, mode, model |
| **Thinking Panel** | Agent reasoning process |
| **Tool Panel** | Tool execution info |
| **PDCA Panel** | PDCA cycle status (if enabled) |

---

## ⚙️ Configuration

### Command-line Options
| Option | Description |
|--------|-------------|
| `--workspace`, `-w` | Path to workspace (required) |
| `--llm`, `-l` | LLM model to use |
| `--mode`, `-m` | Agent mode |
| `--verbose`, `-v` | Enable verbose logging |
| `--refresh-rate` | UI refresh rate (default: 0.1s) |

### Environment Variables
```bash
# LLM Provider
LITELLM_API_KEY=your_api_key
LITELLM_MODEL=deepseek/deepseek-chat

# DAWEI Home (all workspace data root, default ~/.dawei)
DAWEI_HOME=~/.dawei
```

---

## 💡 Tips & Tricks

- ✅ Use `@skill:name` to reference specific skills
- ✅ File references are auto-detected: `@path/to/file`
- ✅ The TUI connects directly to Agent (no WebSocket overhead)
- ✅ All events are streamed in real-time via CORE_EVENT_BUS
- ✅ Type `/help` or `?` in input to show help (PowerShell-friendly!)
- ✅ Use command palette (`Ctrl+P`) for quick actions
- ✅ Sessions are auto-saved, use `Ctrl+S` to force save

---

## 🎨 Color Scheme

The TUI uses a modern color scheme:
- 🔵 **Blue** - Information and navigation
- 🟢 **Green** - Success indicators
- 🟡 **Orange** - Warnings
- 🔴 **Red** - Errors
- ⚪ **Cyan** - Accent color

---

## 🐛 Troubleshooting

### TUI not starting
- Ensure `textual>=0.80.0` is installed
- Check terminal compatibility
- Verify `dawei` command is in PATH

### Agent not responding
- Check LLM API keys in `.env`
- Verify network connection
- Check agent logs with `--verbose`

### Display issues
- Try reducing terminal font size
- Ensure terminal supports Unicode
- Check terminal color support

---

For more information, see the [project documentation](../../../../docs/user/tui.md).
"""


# Export the original HelpScreen as well for backward compatibility
from dawei.tui.ui.screens.help_screen import HelpScreen

__all__ = ["EnhancedHelpScreen", "HelpScreen"]
