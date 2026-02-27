
[English](README.md) | [中文](README_CN.md) | 

# Dawei AI Personal Assistant

## Design Philosophy

- Based on the PDCA (Plan, Do, Check, Act) principle to process user instructions
- Easy to use

## Features

- Visual UI: Installation and editing of agents and agent teams
- Open and integrated agent and skills marketplace with one-click install and uninstall. For skills reference, see [docs/user/skills/work-with-skills_en.md](docs/user/skills/work-with-skills_en.md)
- Data Security: No file uploads, privacy protection
- Cross-platform, easy to install
  - pip version: Install davybot via pip, access webui via browser on local or other machines; especially suitable for Linux systems without GUI
  - standalone version: Download zip package, extract and run, no additional installation required
- Minimal dependencies, complete agent system building
- Scheduled task system

## Videos
- Installation and Configuration: https://www.bilibili.com/video/BV1XDZfBvEit?t=7.0
- Installation and Usage of Skills: https://www.bilibili.com/video/BV1whZfBJEde?t=122.5

# Quick Installation

## pip

```bash
# Install
pip install davybot
# or
pip install -i https://pypi.org/simple/ davybot

# Start
dawei server start
# or
python -m dawei.cli.dawei server start
# Ctrl + C to exit

# Access
http://localhost:8465/app

```

# Web UI

![Main Interface](asserts/web-ui/main.png)

[Web UI Details](asserts/web-ui/README.md)

# Coming Soon

## combot: Computer Bot

Developing plugins for Feishu, WeChat, and other platforms to implement agent control features through instant messaging tools, similar to openclaw.

# Tech Stack
| Component | Version | Description |
|-----------|---------|-------------|
| **Tauri** | 2.x | Rust frontend framework |
| **Rust** | stable | via dtolnay/rust-toolchain |
| **Node.js** | 22 | Frontend build |
| **pnpm** | 9 | Package manager |
| **Python** | 3.12 | Backend runtime (embedded) |
| **UV** | 0.10.6 | Python package manager (embedded) |

# Platform Support
## ✅ Supported Platforms

| Platform | Architecture | Build Status | Package Format | Notes |
|----------|--------------|---------------|----------------|-------|
| **Linux** | x86_64 | ✅ Full Support | ZIP | Verified, 135M |
| **Linux** | aarch64 | ✅ CI Support | ZIP | ARM64 cross-compile |
| **macOS** | x86_64 | ✅ CI Support | ZIP | Intel Macs |
| **macOS** | aarch64 | ✅ CI Support | ZIP | Apple Silicon |
| **macOS** | Universal | ✅ CI Support | ZIP | Intel + ARM (lipo merged) |
| **Windows** | x86_64 | ⚠️ Config Exists | ZIP/NSIS | Local build unverified |

### 📈 Support Coverage

- **Desktop Platforms**: 100% (Linux, macOS, Windows full coverage)
- **Architecture Support**: 90% (x86_64 all platforms, ARM64 Linux/macOS support)
- **CI/CD**: 100% (All platforms have GitHub Actions workflow)

# Release Plan
- [√] Developer Preview (Multi-platform): For experienced professional developers. Requires cloning code and self-installation. See [docs/development/local-development.md](docs/development/local-development.md)
- [√] Tech Version (Multi-platform): For tech-savvy users or those with some computer background. Install via pip install
- Windows App Version: Download and install on Windows for direct use
- Linux App Version: Download and install on Ubuntu for direct use
- Mobile App Version (Cross-platform): Mobile version, install and use directly

# Dependency Repositories

## Market and Resources
- https://github.com/geluzhiwei1/davybot-market-cli
- https://github.com/geluzhiwei1/davybot-skills
- https://github.com/geluzhiwei1/davybot-agents

## Plugins - Instant Messaging Tools

- https://github.com/geluzhiwei1/davybot-plugins-im.git

# WeChat Group Chat
![alt text](asserts/group.png)
