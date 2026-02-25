# Tauri Multi-Platform CI/CD Guide

本文档说明如何使用 GitHub Actions 构建 Tauri Standalone 应用的多平台版本。

## 架构概述

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions Workflow                   │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   macOS      │  │   Windows    │  │   Linux      │      │
│  │  Runner      │  │  Runner      │  │  Runner      │      │
│  │              │  │              │  │              │      │
│  │  • Node.js   │  │  • Node.js   │  │  • Node.js   │      │
│  │  • Rust      │  │  • Rust      │  │  • Rust      │      │
│  │  • Python    │  │  • Python    │  │  • Python    │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                 │               │
│         └─────────────────┴─────────────────┘               │
│                           │                                  │
│                    ┌──────▼──────┐                          │
│                    │   Tauri     │                          │
│                    │   Build     │                          │
│                    └──────┬──────┘                          │
│                           │                                  │
│              ┌────────────┴────────────┐                    │
│              │    Build Artifacts       │                    │
│              │  • .dmg (macOS)         │                    │
│              │  • .exe (Windows)       │                    │
│              │  • .deb/.AppImage (Lin) │                    │
│              └────────────┬────────────┘                    │
└───────────────────────────┼─────────────────────────────────┘
                            │
                    ┌───────▼────────┐
                    │  GitHub        │
                    │  Release       │
                    └────────────────┘
```

## 快速开始

### 1. 触发构建

#### 方式 A：推送标签（推荐）
```bash
git tag v1.0.0
git push origin v1.0.0
```

#### 方式 B：手动触发
1. 访问 GitHub Actions 页面
2. 选择 "Build Tauri Standalone" workflow
3. 点击 "Run workflow"
4. 可选：输入版本号

### 2. 查看构建进度

```
https://github.com/YOUR_USERNAME/davybot/actions
```

每个平台会并行构建，预计时间：
- macOS: ~15-20 分钟（包含 Universal Binary）
- Windows: ~10-15 分钟
- Linux: ~10-15 分钟

### 3. 下载构建产物

构建完成后，在 Release 页面下载：

```
https://github.com/YOUR_USERNAME/davybot/releases
```

## 构建产物说明

| 平台 | 文件格式 | 大小 (约) | 说明 |
|------|---------|----------|------|
| **macOS** | `.dmg` | 50-70 MB | Universal Binary (Intel + Apple Silicon) |
| **Windows** | `.exe` | 14-20 MB | NSIS 安装程序 |
| **Linux** | `.deb` / `.AppImage` | 50-70 MB | Debian 包 / 便携式应用 |

所有版本都包含：
- 完整的 Python 3.12 运行时
- 所有 dawei 依赖包
- 无需用户安装任何额外依赖

## 配置说明

### Workflow 文件

`.github/workflows/tauri-build.yml`

```yaml
strategy:
  matrix:
    include:
      - platform: 'macos-latest'
        target: 'universal-apple-darwin'
      - platform: 'windows-latest'
      - platform: 'linux-latest'
```

### Standalone 配置

`webui/src-tauri/tauri.conf.standalone.json`

关键配置：
```json
{
  "productName": "dawei-standalone",
  "build": {
    "beforeBuildCommand": "pnpm build-only && python ../../../scripts/copy-resources.py"
  },
  "bundle": {
    "targets": ["nsis", "dmg", "appimage", "deb"],
    "resources": [
      "start-backend.sh",
      "stop-backend.sh",
      "start-backend.bat",
      "stop-backend.bat",
      "resources/python-env"
    ]
  }
}
```

## 高级配置

### 代码签名（可选但推荐）

#### macOS 代码签名
1. 在 Apple Developer 获取证书
2. 添加到 GitHub Secrets：
   - `APPLE_CERTIFICATE`: Base64 编码的 .p12 证书
   - `APPLE_CERTIFICATE_PASSWORD`: 证书密码
   - `APPLE_ID`: Apple ID
   - `APPLE_PASSWORD`: App 专用密码
   - `APPLE_TEAM_ID`: 团队 ID

#### Windows 代码签名
1. 获取代码签名证书
2. 添加到 GitHub Secrets：
   - `WINDOWS_CERTIFICATE`: Base64 编码的 .pfx 证书
   - `WINDOWS_CERTIFICATE_PASSWORD`: 证书密码

在 workflow 中添加：
```yaml
- name: Import certificate (macOS)
  if: matrix.platform == 'macos-latest'
  run: |
    echo $APPLE_CERTIFICATE | base64 --decode > certificate.p12
    security create-keychain -p "" build.keychain
    security import certificate.p12 -k build.keychain -P $APPLE_CERTIFICATE_PASSWORD -T /usr/bin/codesign
    security list-keychains -s build.keychain
    security default-keychain -s build.keychain
    security unlock-keychain -p "" build.keychain
    security set-key-partition-list -S apple-tool:,apple: -s -k "" build.keychain

- name: Import certificate (Windows)
  if: matrix.platform == 'windows-latest'
  run: |
    echo $WINDOWS_CERTIFICATE | base64 --decode > certificate.pfx
```

### 自定义构建参数

修改 workflow 中的 `args`：
```yaml
- name: Build Tauri app
  uses: tauri-apps/tauri-action@v0
  with:
    args: '--config src-tauri/tauri.conf.standalone.json --debug'
```

### 修改 Python 镜像源

在 `scripts/copy-resources.py` 中修改 pip 安装源：
```python
pip install -e . -i https://pypi.org/simple/  # 官方源
pip install -e . -i https://mirrors.aliyun.com/pypi/simple/  # 阿里云
```

## 故障排查

### 问题 1: macOS 构建失败 "xcode not found"

**解决方案**：
- GitHub Actions 的 macOS runner 会自动安装 Xcode
- 如果仍有问题，尝试添加：
  ```yaml
  - name: Install Xcode
    run: sudo xcode-select --switch /Applications/Xcode_15.app
  ```

### 问题 2: Python 环境太大导致超时

**解决方案**：
- 在 `copy-resources.py` 中已包含清理 `__pycache__` 的逻辑
- 可以进一步清理：
  ```python
  # 删除测试文件
  find python-env -type d -name "test" -o -name "tests" | xargs rm -rf
  # 删除文档
  find python-env -type d -name "__doc__" | xargs rm -rf
  ```

### 问题 3: Linux 构建缺少依赖

**解决方案**：
```yaml
- name: Install system dependencies (Linux)
  if: matrix.platform == 'linux-latest'
  run: |
    sudo apt-get update
    sudo apt-get install -y \
      libgtk-3-dev \
      libwebkit2gtk-4.0-dev \
      libappindicator3-dev \
      librsvg2-dev \
      patchelf \
      libssl-dev
```

### 问题 4: Windows 构建路径问题

**解决方案**：
- 确保 Git Bash 或 WSL 可用
- 使用 `shell: bash` 而不是默认的 PowerShell
- 路径使用正斜杠 `/` 而不是反斜杠 `\`

## 本地测试

在推送前，可以在本地测试构建：

```bash
# 测试脚本
python scripts/copy-resources.py

# 测试 standalone 构建
cd webui
pnpm tauri build --config src-tauri/tauri.conf.standalone.json
```

## 成本估算

GitHub Actions 使用情况：

| 平台 | 构建时间 | 分钟/月 (假设 10 次发布) |
|------|---------|------------------------|
| macOS | 20 分钟 | 200 分钟 |
| Windows | 15 分钟 | 150 分钟 |
| Linux | 15 分钟 | 150 分钟 |

**总计**: 500 分钟/月

- **GitHub Free**: 2000 分钟/月 ✅ 足够使用
- **GitHub Pro**: 3000 分钟/月 ✅ 更加充裕
- **GitHub Team**: 10000 分钟/月 ✅ 大型项目

## 最佳实践

1. **版本标签规范**
   ```bash
   # 推荐使用语义化版本
   git tag v1.0.0
   git tag v1.0.1
   git tag v2.0.0-beta.1
   ```

2. **构建前验证**
   ```bash
   # 在推送标签前先在本地验证
   pnpm test
   pnpm build-only
   python scripts/copy-resources.py
   ```

3. **使用 draft releases**
   - 构建后先创建 draft release
   - 手动测试后再发布
   ```yaml
   - name: Create GitHub Release (Draft)
    run: |
      gh release create "$TAG" --draft --notes "Draft"
   ```

4. **缓存优化**
   - Workflow 已配置 cargo 和 pnpm 缓存
   - 首次构建会较慢，后续构建会快很多

5. **通知**
   添加 Slack/Discord 通知：
   ```yaml
   - name: Notify on success
    if: success()
    uses: 8398a7/action-slack@v3
    with:
      status: ${{ job.status }}
      text: 'Build succeeded!'
   ```

## 参考资源

- [Tauri 官方文档](https://tauri.app/)
- [tauri-action GitHub](https://github.com/tauri-apps/tauri-action)
- [GitHub Actions 文档](https://docs.github.com/en/actions)
- [语义化版本](https://semver.org/lang/zh-CN/)

## 支持

如有问题，请：
1. 查看 [GitHub Issues](https://github.com/YOUR_USERNAME/davybot/issues)
2. 检查 Actions 日志获取详细错误信息
3. 参考本文档的故障排查部分
