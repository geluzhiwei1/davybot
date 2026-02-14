# Tauri 应用图标

此目录需要包含应用的图标文件。

## 如何生成图标

### 方法 1: 使用 Tauri CLI (推荐)

1. 准备一个 1024x1024 像素的 PNG 图标文件（例如 `app-icon.png`）
2. 在项目根目录运行：
   ```bash
   pnpm tauri icon app-icon.png
   ```
   这将自动生成所有需要的图标尺寸。

### 方法 2: 手动创建

需要创建以下图标文件：
- `32x32.png` - 32x32 像素 PNG
- `128x128.png` - 128x128 像素 PNG
- `128x128@2x.png` - 256x256 像素 PNG (高分辨率)
- `icon.icns` - macOS 图标文件
- `icon.ico` - Windows 图标文件

### 临时方案

对于开发测试，可以修改 `src-tauri/tauri.conf.json` 中的 `bundle.icon` 配置为空数组或注释掉图标配置。
