# Dawei TUI

Terminal User Interface for Dawei Agent - a modern, async TUI that interacts directly with the Agent system without WebSocket overhead.

## 📚 Documentation

Complete documentation is available in the project docs:

- **[User Guide](../../../../docs/user/tui.md)** - Full documentation with features, architecture, and troubleshooting
- **[Quick Start](../../../../docs/user/tui-quickstart.md)** - 5-minute quick start guide
- **[Examples](../../../../docs/user/tui-examples.md)** - Practical usage examples

## 🚀 Quick Start

```bash
cd services/agent-api

# Install TUI dependencies
uv pip install textual

# Launch TUI (auto-setup workspace)
python dawei/tui/quick_start.py

# Or run with custom workspace
python -m dawei.tui --workspace ./my-workspace
```

## ⌨️ Keyboard Shortcuts

- `Ctrl+H` - Show help screen
- `Ctrl+C` - Quit
- `Ctrl+P` - Command palette
- `Ctrl+R` - Session history
- `Up/Down` - Navigate command history
- `Tab` - Switch panels

## 📖 Features

- Direct Agent integration (no WebSocket overhead)
- Real-time streaming responses
- Multi-panel layout (chat, thinking, tools)
- Command history navigation
- Markdown rendering
- Session persistence
- Settings screen
- Export functionality

## 🧪 Testing

```bash
# Run feature demo
python dawei/tui/demo.py

# Run test suite
python dawei/tui/test_tui.py

# Verify installation
python dawei/tui/verify_installation.py
```

For detailed documentation, see [docs/user/tui.md](../../../../docs/user/tui.md).
