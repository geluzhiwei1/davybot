# Windows Standalone ZIP Build Script for Tauri using UV
# Builds complete standalone ZIP package with Python environment using UV

param(
    [switch]$SkipTests = $false,
    [switch]$Verbose = $false,
    [string]$PyPIIndex = "https://pypi.org/simple"
)

$ErrorActionPreference = "Stop"

# Color functions
function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

function Write-Success { Write-ColorOutput Green @args }
function Write-Info { Write-ColorOutput Cyan @args }
function Write-Warning { Write-ColorOutput Yellow @args }
function Write-Error { Write-ColorOutput Red @args }

# Paths
$ScriptPath = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $ScriptPath
$WebDir = Join-Path $ProjectRoot "webui"
$TauriDir = Join-Path $WebDir "src-tauri"
$TargetDir = Join-Path $TauriDir "target\release"
$AgentDir = Join-Path $ProjectRoot "agent"

Write-Info "========================================"
Write-Info "  Tauri Windows Standalone ZIP Builder (UV)"
Write-Info "========================================"
Write-Output ""
Write-Output "Project Root: $ProjectRoot"
Write-Output ""

# Check prerequisites
Write-Info "[0/6] Checking prerequisites..."

# Check Node.js
$nodeVersion = node --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "❌ Node.js not found"
    exit 1
}
Write-Success "  ✓ Node.js: $nodeVersion"

# Check pnpm
$pnpmVersion = pnpm --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "❌ pnpm not found"
    exit 1
}
Write-Success "  ✓ pnpm: $pnpmVersion"

# Check Rust
$rustVersion = rustc --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "❌ Rust not found"
    exit 1
}
Write-Success "  ✓ Rust: $rustVersion"

# Check UV
$uvVersion = uv --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "❌ UV not found"
    Write-Output "  Install UV: powershell -c `"irm https://astral.sh/uv/install.ps1 | iex`""
    exit 1
}
Write-Success "  ✓ UV: $uvVersion"

Write-Output ""

# Step 1: Prepare Python environment using UV
Write-Info "[1/6] Preparing Python environment with UV..."
Set-Location $AgentDir

# Remove old .venv if exists
if (Test-Path ".venv") {
    Write-Output "  Removing old virtual environment..."
    Remove-Item -Path ".venv" -Recurse -Force
}

Write-Output "  Creating virtual environment with UV..."
uv venv --python 3.12
if ($LASTEXITCODE -ne 0) {
    Write-Error "❌ Failed to create virtual environment with UV"
    exit 1
}

Write-Output "  Installing dawei package with UV..."
Write-Output "  Using PyPI index: $PyPIIndex"
uv pip install -e . --index-url $PyPIIndex
if ($LASTEXITCODE -ne 0) {
    Write-Error "❌ Failed to install dawei package with UV"
    exit 1
}

Write-Success "  ✓ Python environment ready with UV"
Write-Output ""

# Step 2: Copy Python environment to Tauri
Write-Info "[2/6] Copying Python environment to Tauri resources..."

$VenvSrc = Join-Path $AgentDir ".venv"
$VenvDst = Join-Path $TauriDir "resources\python-env"

if (Test-Path $VenvDst) {
    Write-Output "  Removing old environment..."
    Remove-Item -Path $VenvDst -Recurse -Force
}

Write-Output "  Copying files (this may take a few minutes)..."
Copy-Item -Path $VenvSrc -Destination $VenvDst -Recurse -Force

# Clean up cache
Write-Output "  Cleaning cache..."
Get-ChildItem -Path $VenvDst -Recurse -Filter "__pycache__" -Directory | Remove-Item -Recurse -Force
Get-ChildItem -Path $VenvDst -Recurse -Filter "*.pyc" | Remove-Item -Force

$VenvSize = (Get-ChildItem -Path $VenvDst -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Success "  ✓ Python environment copied ($([math]::Round($VenvSize, 1)) MB)"
Write-Output ""

# Step 3: Build frontend
Write-Info "[3/6] Building frontend..."
Set-Location $WebDir

pnpm build-only
if ($LASTEXITCODE -ne 0) {
    Write-Error "❌ Frontend build failed"
    exit 1
}

Write-Success "  ✓ Frontend built"
Write-Output ""

# Step 4: Build Tauri
Write-Info "[4/6] Building Tauri application..."
Set-Location $WebDir

# Clean previous build
if (Test-Path (Join-Path $TargetDir "bundle")) {
    Remove-Item -Path (Join-Path $TargetDir "bundle") -Recurse -Force
}

# Build with standalone config (no bundle for ZIP)
pnpm tauri build --config (Join-Path $TauriDir "tauri.conf.standalone.json") --no-bundle
if ($LASTEXITCODE -ne 0) {
    Write-Error "❌ Tauri build failed"
    exit 1
}

Write-Success "  ✓ Tauri built"
Write-Output ""

# Step 5: Create portable ZIP package
Write-Info "[5/6] Creating portable ZIP package..."

# Get version from Cargo.toml
$cargoToml = Join-Path $TauriDir "Cargo.toml"
$cargoContent = Get-Content $cargoToml -Raw
if ($cargoContent -match 'name\s*=\s*"([^"]+)"') {
    $appName = $matches[1]
}
if ($cargoContent -match 'version\s*=\s*"([^"]+)"') {
    $appVersion = $matches[1]
}

$zipDir = Join-Path $TargetDir "$appName-standalone-win-portable-v$appVersion"
$zipName = "$appName-standalone-win-portable-v$appVersion.zip"

if (Test-Path $zipDir) {
    Write-Output "  Cleaning old package..."
    Remove-Item -Path $zipDir -Recurse -Force
}

New-Item -ItemType Directory -Path $zipDir -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $zipDir "resources") -Force | Out-Null

Write-Output "  Copying application files..."

# Main executable
$exePath = Join-Path $TargetDir "$appName.exe"
if (Test-Path $exePath) {
    Copy-Item -Path $exePath -Destination $zipDir -Force
    Write-Success "  ✓ Main executable copied"
} else {
    Write-Error "❌ Main executable not found: $exePath"
    exit 1
}

# Python environment
if (Test-Path $VenvDst) {
    Copy-Item -Path $VenvDst -Destination (Join-Path $zipDir "resources\python-env") -Recurse -Force
    Write-Success "  ✓ Python environment copied"
} else {
    Write-Warning "  ⚠ Warning: Python environment not found at $VenvDst"
}

# Backend scripts
$scriptsToCopy = @("start-backend.bat", "stop-backend.bat", "start-backend.sh", "stop-backend.sh")
foreach ($script in $scriptsToCopy) {
    $scriptPath = Join-Path $TauriDir $script
    if (Test-Path $scriptPath) {
        Copy-Item -Path $scriptPath -Destination (Join-Path $zipDir "resources") -Force
    }
}
Write-Success "  ✓ Backend scripts copied"

# Icons
$iconsDir = Join-Path $TauriDir "icons"
if (Test-Path $iconsDir) {
    Copy-Item -Path $iconsDir -Destination (Join-Path $zipDir "icons") -Recurse -Force
    Write-Success "  ✓ Icons copied"
}

# Create README
$readmePath = Join-Path $zipDir "README.txt"
$readmeContent = @"
# 大微 AI 助手 - Standalone 便携版

版本: $appVersion

## 使用方法

1. 解压缩此 ZIP 文件到任意目录
2. 双击 $appName.exe 启动应用

应用会在首次启动时自动启动后端服务。

## 目录结构

- $appName.exe              : 主应用程序
- resources\                  : 资源文件目录
  - python-env\               : Python 运行时环境 (使用 UV 管理)
    - Scripts\python.exe      : Python 解释器
    - Scripts\pip.exe         : Python 包管理器
    - Lib\                    : Python 标准库
    - Lib\site-packages\      : 第三方库 (FastAPI, uvicorn 等)
  - start-backend.bat         : Windows 后端启动脚本
  - stop-backend.bat          : Windows 后端停止脚本
  - start-backend.sh          : Linux/Mac 后端启动脚本
  - stop-backend.sh           : Linux/Mac 后端停止脚本
- icons\                      : 应用图标

## 系统要求

- Windows 10 或更高版本 (64位)
- 约 500 MB 可用磁盘空间

## 注意事项

- 首次运行可能需要几秒钟来初始化
- 请勿移动或删除 resources 目录
- 如遇问题，请查看应用日志
- Windows 版本使用 Scripts\python.exe，Linux/Mac 使用 bin/python

## 技术支持

项目主页: https://github.com/geluzhiwei1/davybot.git

Copyright © 2026 大微团队. All rights reserved.
"@
Set-Content -Path $readmePath -Value $readmeContent -Encoding UTF8
Write-Success "  ✓ README created"

# Create ZIP package
Write-Output "  Creating ZIP package..."
$zipPath = Join-Path $TargetDir $zipName
Compress-Archive -Path $zipDir -DestinationPath $zipPath -Force

if ($LASTEXITCODE -ne 0) {
    Write-Error "❌ Failed to create ZIP package"
    exit 1
}

$zipSize = (Get-Item $zipPath).Length / 1MB
Write-Success "  ✓ ZIP package created ($([math]::Round($zipSize, 1)) MB)"
Write-Output ""

# Step 6: Show results
Write-Info "[6/6] Build completed!"
Write-Output ""

Write-Success "✅ Build Artifacts:"
Write-Output ""
Write-Output "  Portable ZIP Package:"
Write-Output "    Name:     $zipName"
Write-Output "    Location: $zipPath"
Write-Output "    Size:     $([math]::Round($zipSize, 1)) MB"
Write-Output ""

Write-Success "📦 Package Contents:"
Write-Output "  - $appName.exe (Main application)"
Write-Output "  - resources/python-env/ (Python runtime + dependencies via UV)"
Write-Output "  - resources/start-backend.bat  (Backend startup script)"
Write-Output "  - resources/stop-backend.bat   (Backend shutdown script)"
Write-Output "  - README.txt (Usage instructions)"
Write-Output ""

Write-Info "📋 Distribution Instructions:"
Write-Output ""
Write-Output "  1. Upload the ZIP file to your distribution platform"
Write-Output "  2. Users can:"
Write-Output "     - Download the ZIP file"
Write-Output "     - Extract it to any folder"
Write-Output "     - Run $appName.exe directly"
Write-Output "     - No installation required!"
Write-Output ""

Write-Success "✅ Build Complete!"
Write-Output ""

# Return to project root
Set-Location $ProjectRoot
