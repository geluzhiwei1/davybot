# Windows Standalone Build Script for Tauri
# Builds complete standalone installer with Python environment

param(
    [switch]$SkipTests = $false,
    [switch]$Verbose = $false
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
$WebDir = Join-Path $ProjectRoot "apps\web"
$TauriDir = Join-Path $WebDir "src-tauri"
$TargetDir = Join-Path $TauriDir "target\release"

Write-Info "========================================"
Write-Info "  Tauri Windows Standalone Builder"
Write-Info "========================================"
Write-Output ""
Write-Output "Project Root: $ProjectRoot"
Write-Output ""

# Check prerequisites
Write-Info "[0/5] Checking prerequisites..."

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

# Check Python
$pythonVersion = python --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "❌ Python not found"
    exit 1
}
Write-Success "  ✓ Python: $pythonVersion"

Write-Output ""

# Step 1: Prepare Python environment
Write-Info "[1/5] Preparing Python environment..."
Set-Location (Join-Path $ProjectRoot "services\agent-api")

if (-not (Test-Path ".venv")) {
    Write-Output "  Creating virtual environment..."
    python -m venv .venv
}

& .\.venv\Scripts\Activate.ps1
Write-Output "  Installing dawei package..."
pip install -e . -i https://pypi.org/simple --quiet
Write-Success "  ✓ Python environment ready"
Write-Output ""

# Step 2: Copy Python environment to Tauri
Write-Info "[2/5] Copying Python environment to Tauri resources..."

$VenvSrc = Join-Path $ProjectRoot "services\agent-api\.venv"
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
Write-Info "[3/5] Building frontend..."
Set-Location $WebDir

pnpm build-only
if ($LASTEXITCODE -ne 0) {
    Write-Error "❌ Frontend build failed"
    exit 1
}

Write-Success "  ✓ Frontend built"
Write-Output ""

# Step 4: Build Tauri
Write-Info "[4/5] Building Tauri application..."
Set-Location $WebDir

# Clean previous build
if (Test-Path (Join-Path $TargetDir "bundle")) {
    Remove-Item -Path (Join-Path $TargetDir "bundle") -Recurse -Force
}

# Build with standalone config
pnpm tauri build --config (Join-Path $TauriDir "tauri.conf.standalone.json")
if ($LASTEXITCODE -ne 0) {
    Write-Error "❌ Tauri build failed"
    exit 1
}

Write-Success "  ✓ Tauri built"
Write-Output ""

# Step 5: Check results
Write-Info "[5/5] Checking build artifacts..."
Write-Output ""

$BundleDir = Join-Path $TargetDir "bundle"

if (Test-Path $BundleDir) {
    Write-Success "✅ Build Artifacts:"
    Write-Output ""

    # NSIS installer
    $NsisExe = Get-ChildItem -Path (Join-Path $BundleDir "nsis") -Filter "*.exe" -ErrorAction SilentlyContinue
    if ($NsisExe) {
        foreach ($exe in $NsisExe) {
            $size = [math]::Round($exe.Length / 1MB, 2)
            Write-Output "  NSIS Installer:"
            Write-Output "    Location: $($exe.FullName)"
            Write-Output "    Size:     $size MB"
            Write-Output ""
        }
    }

    # MSI installer
    $MsiFile = Get-ChildItem -Path (Join-Path $BundleDir "msi") -Filter "*.msi" -ErrorAction SilentlyContinue
    if ($MsiFile) {
        foreach ($msi in $MsiFile) {
            $size = [math]::Round($msi.Length / 1MB, 2)
            Write-Output "  MSI Installer:"
            Write-Output "    Location: $($msi.FullName)"
            Write-Output "    Size:     $size MB"
            Write-Output ""
        }
    }
}

Write-Success "📦 Package Contents:"
Write-Output "  - ip-agent.exe (Main application)"
Write-Output "  - python-env/ (Python runtime + dependencies)"
Write-Output "  - Backend scripts (start/stop for Windows/Linux)"
Write-Output ""

Write-Success "✅ Build Complete!"
Write-Output ""

Write-Info "Installation Instructions:"
Write-Output "  1. Run the NSIS or MSI installer"
Write-Output "  2. Follow the installation wizard"
Write-Output "  3. Launch from Start Menu or Desktop shortcut"
Write-Output ""

# Return to project root
Set-Location $ProjectRoot
