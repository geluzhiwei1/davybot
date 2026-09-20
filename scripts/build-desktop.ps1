# Full NormNomos Desktop build: frontend + sidecar + Tauri + updater signing.
# Must run from repo root on Windows. Windows mirror of build-desktop.sh.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/build-desktop.ps1          # full build: frontend + sidecar + tauri
#   powershell -ExecutionPolicy Bypass -File scripts/build-desktop.ps1 sidecar # sidecar only (no frontend)
#   powershell -ExecutionPolicy Bypass -File scripts/build-desktop.ps1 tauri   # tauri only (assumes sidecar + frontend exist)
#   powershell -ExecutionPolicy Bypass -File scripts/build-desktop.ps1 all     # full build (default)
#
# Environment variables (for CI signing):
#   TAURI_SIGNING_PRIVATE_KEY         Ed25519 private key for updater signing
#   TAURI_SIGNING_PRIVATE_KEY_PASSWORD Optional password for the key

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$TauriDir = Join-Path $RepoRoot "app"

# ---- Detect platform target triple ----
function Detect-Target {
    # Resolve arch from two independent signals and string-normalize BEFORE
    # matching. Reading [RuntimeInformation]::OSArchitecture and switching on the
    # enum directly is fragile: on some Windows PowerShell 5.1 sessions the enum
    # comes back blank / fails to coerce against the string literals, which
    # aborted the build with "unsupported arch: " (empty). $env:PROCESSOR_ARCHITECTURE
    # is the most reliable Windows signal (AMD64 / ARM64 / x86); the .NET enum
    # is a fallback. Match via a lowercased string + regex so it never misfires.
    $raw = "$env:PROCESSOR_ARCHITECTURE".Trim().ToLower()
    if (-not $raw) {
        $raw = "$([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture)".Trim().ToLower()
    }

    $archStr = switch -Regex ($raw) {
        '^(amd64|x64)$'     { "x86_64" }
        '^(arm64|aarch64)$' { "aarch64" }
        '^(x86|i386)$'      { throw "ERROR: 32-bit Windows (x86) is not supported" }
        default {
            throw "ERROR: unsupported arch (PROCESSOR_ARCHITECTURE='$env:PROCESSOR_ARCHITECTURE', OSArchitecture='$([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture)')"
        }
    }
    return "$archStr-pc-windows-msvc"
}

# ---- Bundle output dir ----
# `tauri build --target <triple>` writes under target\<triple>\release\bundle\,
# not target\release\bundle\, so the triple must be part of the path.
function Get-BundleDir {
    param([string]$TargetTriple)
    return Join-Path $TauriDir "src-tauri\target\$TargetTriple\release\bundle"
}

# ---- Resolve version from git (single source of truth, same as build-desktop.sh) ----
# git describe: v0.2.11-44-g326ada4 → 0.2.11-post.1.dev.44
#                v0.2.11-0-gxxx      → 0.2.11 (release, exact tag)
function Resolve-Version {
    $agentDir = Join-Path $RepoRoot "engine\agent"
    $version = $null
    Push-Location $agentDir
    try {
        # Relax EAP around the native call: on Windows PowerShell 5.1, redirecting
        # a failing native command's stderr (2>$null) under ErrorActionPreference
        # Stop throws NativeCommandError before we can check $LASTEXITCODE.
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $desc = git describe --tags --long 2>$null
            $gitOk = ($LASTEXITCODE -eq 0)
        } finally {
            $ErrorActionPreference = $prevEap
        }

        if ($gitOk -and $desc) {
            $desc = $desc -replace '^v', ''
            if ($desc -match '-0-g[0-9a-f]+$') {
                # Exact tag
                $version = $desc -replace '-0-g[0-9a-f]+$', ''
            } elseif ($desc -match '-\d+-g[0-9a-f]+$') {
                # Dev build past the tag
                $version = $desc -replace '-(\d+)-g[0-9a-f]+$', '-post.1.dev.$1'
            } else {
                $version = $desc
            }
        }
    } finally {
        Pop-Location
    }

    if (-not $version) {
        Write-Host "WARN: Could not resolve version from git, using 0.0.0" -ForegroundColor Yellow
        $version = "0.0.0"
    }
    return $version
}

# ---- Inject version into Tauri config files ----
# In-place injection with backup + restore-on-exit (try/finally in Main): the
# build sees the right version, but the working tree stays clean afterwards.
# Same .build-bak approach as build-desktop.sh / mac-build-and-sign.sh.
function Inject-Version {
    param([string]$Version)

    Write-Host "     Version: $Version"

    $conf = Join-Path $TauriDir "src-tauri\tauri.conf.json"
    $cargo = Join-Path $TauriDir "src-tauri\Cargo.toml"

    # Backup originals once (kept if a previous run crashed); Main's finally restores.
    foreach ($f in @($conf, $cargo)) {
        if (-not (Test-Path "$f.build-bak")) {
            Copy-Item $f "$f.build-bak"
        }
    }

    # [System.IO.File]::ReadAllLines/WriteAllLines preserve UTF-8 without BOM and
    # existing line endings — Set-Content's default encoding would add a BOM /
    # re-encode the JSON, which some Tauri toolchains reject.
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)

    # tauri.conf.json — replace the first top-level "version" key (jq-equivalent).
    $lines = [System.IO.File]::ReadAllLines($conf)
    for ($i = 0; $i -lt $lines.Length; $i++) {
        if ($lines[$i] -match '"version"\s*:\s*"[^"]*"') {
            $lines[$i] = $lines[$i] -replace '"version"\s*:\s*"[^"]*"', ('"version": "' + $Version + '"')
            break
        }
    }
    [System.IO.File]::WriteAllLines($conf, $lines, $utf8NoBom)

    # Cargo.toml — replace "version = "..." lines (same match as the bash sed).
    $lines = [System.IO.File]::ReadAllLines($cargo)
    for ($i = 0; $i -lt $lines.Length; $i++) {
        if ($lines[$i] -match '^\s*version\s*=\s*"[^"]*"') {
            $lines[$i] = $lines[$i] -replace '^\s*version\s*=\s*"[^"]*"', ('version = "' + $Version + '"')
        }
    }
    [System.IO.File]::WriteAllLines($cargo, $lines, $utf8NoBom)

    Write-Host "     Injected into tauri.conf.json, Cargo.toml (auto-restored on exit)"
}

# ---- Restore the backed-up Tauri config files (no-op if none were made) ----
function Restore-VersionFiles {
    $conf = Join-Path $TauriDir "src-tauri\tauri.conf.json"
    $cargo = Join-Path $TauriDir "src-tauri\Cargo.toml"
    foreach ($f in @($conf, $cargo)) {
        if (Test-Path "$f.build-bak") {
            Move-Item "$f.build-bak" $f -Force
        }
    }
}

# ---- Build frontend (nn-bot-app → agent\dawei\frontend\) ----
function Build-Frontend {
    Write-Host "==> Building frontend (nn-bot-app web SPA)..." -ForegroundColor Cyan
    Push-Location $TauriDir
    try {
        if (-not (Test-Path (Join-Path $TauriDir "node_modules"))) {
            Write-Host "     Installing frontend dependencies..."
            npm install
            if ($LASTEXITCODE -ne 0) {
                Write-Host "ERROR: npm install failed" -ForegroundColor Red
                exit 1
            }
        }

        # Build pure web SPA for server-embedded mode (uses vite.config.ts, base /app-ui/)
        # --mode server loads .env.server (empty API/WS URLs → runtime derives from window.location)
        npm run build:server
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Frontend build failed (npm run build:server)" -ForegroundColor Red
            exit 1
        }
    } finally {
        Pop-Location
    }

    $frontendDist = Join-Path $TauriDir "dist"
    if (-not (Test-Path $frontendDist)) {
        Write-Host "ERROR: Frontend build failed: $frontendDist not found" -ForegroundColor Red
        exit 1
    }

    # Copy into dawei package so PyInstaller can bundle it
    $targetFrontend = Join-Path $RepoRoot "engine\agent\dawei\frontend"
    if (Test-Path $targetFrontend) {
        Remove-Item $targetFrontend -Recurse -Force
    }
    Copy-Item $frontendDist $targetFrontend -Recurse

    Write-Host "     OK: Frontend bundled: $targetFrontend" -ForegroundColor Green
}

# ---- Env 一致性校验 (多模式统一方案 §L1; PS 版, 与 build-desktop.sh 同语义) ----
# desktop 构建配了 saas/server 的 env 文件 → FAST FAIL。
function Check-RuntimeModeEnv {
    param([string]$EnvPath, [string]$ExpectedMode)
    if (-not (Test-Path $EnvPath)) { return }
    $line = Select-String -Path $EnvPath -Pattern '^\s*DAWEI_RUNTIME_MODE\s*=(.*)$' | Select-Object -Last 1
    if (-not $line) {
        Write-Host "     WARN: $EnvPath 未声明 DAWEI_RUNTIME_MODE (建议补, 见 .env.desktop.*.example)" -ForegroundColor Yellow
        return
    }
    $got = ($line.Matches[0].Groups[1].Value -replace '#.*$', '' -replace '["'']', '').Trim()
    if ($got -ne $ExpectedMode) {
        Write-Host "ERROR: $EnvPath 声明 DAWEI_RUNTIME_MODE=$got, 与目标模式 '$ExpectedMode' 不符 (多模式统一方案 §L1)" -ForegroundColor Red
        exit 1
    }
    Write-Host "     OK: $EnvPath DAWEI_RUNTIME_MODE=$got" -ForegroundColor Green
}

function Check-ModeEnv {
    $agentDir = Join-Path $RepoRoot "engine\agent"
    foreach ($f in @(".env.desktop", ".env.desktop.dev", ".env.desktop.prod")) {
        Check-RuntimeModeEnv (Join-Path $agentDir $f) "desktop"
    }
}

# ---- Build sidecar ----
function Build-Sidecar {
    Write-Host "==> [1/4] Building sidecar (build-binary.py / PyInstaller)..." -ForegroundColor Cyan
    $agentDir = Join-Path $RepoRoot "engine\agent"
    $buildScript = Join-Path $agentDir "scripts\build-binary.py"
    if (-not (Test-Path $buildScript)) {
        Write-Host "ERROR: Sidecar builder not found at $buildScript" -ForegroundColor Red
        exit 1
    }
    Check-ModeEnv
    Push-Location $agentDir
    try {
        # Delegate to the canonical builder (same args as `npm run sidecar:build:clean`).
        # build-binary.py bundles HIDDEN_IMPORTS (fastapi/uvicorn/pydantic...),
        # --collect-all dawei, and --add-data dawei:dawei so the embedded sidecar runs
        # (the bare PyInstaller call omits these and yields a broken sidecar).
        # --with pyinstaller injects the tool (it is not a project dependency).
        # Use Python 3.12 (onnxruntime not compatible with 3.14).
        # --runtime-mode desktop: 产物盖戳 (多模式统一方案 §L1) — 桌面包只允许 desktop。
        uv run --python 3.12 --with pyinstaller python scripts/build-binary.py --clean --runtime-mode desktop
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Sidecar build failed" -ForegroundColor Red
            exit 1
        }
    } finally {
        Pop-Location
    }
    $bin = Join-Path $agentDir "dist\dawei.exe"
    $size = (Get-Item $bin).Length
    $sizeStr = if ($size -gt 1MB) { "{0:N1} MB" -f ($size / 1MB) } else { "{0:N1} KB" -f ($size / 1KB) }
    Write-Host "     OK: $bin ($sizeStr)"

    # Smoke-test the freshly built sidecar: a binary that imports cleanly and
    # serves /api/health is the only real proof it'll run inside the desktop app.
    # Catches import-time / encoding / missing-native-lib crashes BEFORE packaging
    # (e.g. the GBK-vs-UTF-8 crash that shipped as "本地引擎健康检查超时").
    Test-Sidecar $bin
}

# ---- Smoke-test the sidecar: launch it, poll /api/health, fail the build if unhealthy ----
function Test-Sidecar {
    param([string]$SidecarBin)

    Write-Host "==> [smoke] Launching sidecar health check..." -ForegroundColor Cyan
    if (-not (Test-Path $SidecarBin)) {
        Write-Host "ERROR: sidecar binary not found at $SidecarBin" -ForegroundColor Red
        exit 1
    }

    # Let the OS pick a free localhost port (same trick the Tauri host uses).
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $port = ($listener.LocalEndpoint).Port
    $listener.Stop()

    # In --sidecar mode with a non-tty stdout the server redirects its Python
    # output to ~/.normnomos/logs/dawei-sidecar-<port>.log — that's where the real
    # traceback lands on failure. Capture pre-redirect / bootloader output too.
    $sidecarLog = Join-Path $env:USERPROFILE ".normnomos\logs\dawei-sidecar-$port.log"
    $bootOut = Join-Path $env:TEMP "dawei-smoke-$port.out"
    $bootErr = Join-Path $env:TEMP "dawei-smoke-$port.err"

    $p = Start-Process -FilePath $SidecarBin `
        -ArgumentList "server","start","--host","127.0.0.1","--port","$port","--sidecar" `
        -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $bootOut -RedirectStandardError $bootErr

    $healthy = $false
    for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 2
        if ($p.HasExited) { break }
        try {
            $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 3
            if ($resp.StatusCode -eq 200) { $healthy = $true; break }
        } catch { }
    }

    # Always tear down the sidecar.
    if ($p -and -not $p.HasExited) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
    $exitCode = if ($p) { $p.ExitCode } else { -1 }

    if ($healthy) {
        Write-Host "     OK: sidecar healthy on port $port (/api/health 200)" -ForegroundColor Green
        return
    }

    Write-Host "ERROR: sidecar did not become healthy within ~90s (exit code $exitCode)" -ForegroundColor Red
    foreach ($f in @($bootErr, $bootOut, $sidecarLog)) {
        if (Test-Path $f) {
            $tail = Get-Content $f -Tail 40 -ErrorAction SilentlyContinue
            if ($tail) {
                Write-Host "       --- tail of $f ---" -ForegroundColor Yellow
                $tail | ForEach-Object { Write-Host "       $_" }
            }
        }
    }
    exit 1
}

# ---- Copy sidecar to Tauri binaries ----
function Copy-Sidecar {
    param([string]$TargetTriple)

    $sidecarBin = Join-Path $RepoRoot "engine\agent\dist\dawei.exe"
    if (-not (Test-Path $sidecarBin)) {
        Write-Host "ERROR: Sidecar binary not found at $sidecarBin. Run sidecar build first." -ForegroundColor Red
        exit 1
    }

    $dest = Join-Path $TauriDir "src-tauri\binaries\dawei-$TargetTriple.exe"
    $destDir = Split-Path -Parent $dest
    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }

    Write-Host "==> [2/4] Copying sidecar: $sidecarBin -> $dest" -ForegroundColor Cyan
    Copy-Item $sidecarBin $dest -Force

    $size = (Get-Item $dest).Length
    $sizeStr = if ($size -gt 1MB) { "{0:N1} MB" -f ($size / 1MB) } else { "{0:N1} KB" -f ($size / 1KB) }
    Write-Host "     OK ($sizeStr)"
}

# ---- Build Tauri (with optional updater signing) ----
function Build-Tauri {
    Write-Host "==> [3/4] Building Tauri desktop app..." -ForegroundColor Cyan

    $targetTriple = Detect-Target
    # Fail fast on unmapped targets (same as resolve_build_cmd in build-desktop.sh).
    # There is no package:windows-arm64 script yet — aarch64-pc-windows-msvc throws
    # instead of silently falling back to a wrong-target `npm run tauri:build`.
    $buildCmd = switch ($targetTriple) {
        "x86_64-pc-windows-msvc" { "npm run package:windows" }
        default { throw "ERROR: no package script for target: $targetTriple" }
    }

    Push-Location $TauriDir
    try {
        Invoke-Expression $buildCmd
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Tauri build failed with exit code $LASTEXITCODE" -ForegroundColor Red
            exit $LASTEXITCODE
        }
    } finally {
        Pop-Location
    }

    Write-Host "==> Desktop build complete."
    Write-Host "     Bundles: $(Get-BundleDir $targetTriple)"
}

# ---- Locate the installer and verify updater signing artifacts ----
function Verify-Signing {
    param([string]$TargetTriple)

    Write-Host "==> [4/4] Locating installer and verifying signatures..." -ForegroundColor Cyan

    $bundleDir = Get-BundleDir $TargetTriple

    # Locate the NSIS installer (the concrete deliverable).
    $nsisDir = Join-Path $bundleDir "nsis"
    $installers = @(Get-ChildItem -Path $nsisDir -Filter "*-setup.exe" -ErrorAction SilentlyContinue)
    if ($installers.Count -gt 0) {
        foreach ($inst in $installers) {
            $sizeStr = if ($inst.Length -gt 1MB) { "{0:N1} MB" -f ($inst.Length / 1MB) } else { "{0:N1} KB" -f ($inst.Length / 1KB) }
            Write-Host "     Installer: $($inst.FullName) ($sizeStr)" -ForegroundColor Green
        }
    } else {
        Write-Host "     WARN: No *-setup.exe found under $nsisDir" -ForegroundColor Yellow
        Write-Host "     The Tauri build may not have produced an installer"
    }

    # Updater signatures.
    $sigFiles = @(Get-ChildItem -Path $bundleDir -Filter "*.sig" -Recurse -ErrorAction SilentlyContinue)

    if ($sigFiles.Count -gt 0) {
        Write-Host "     Found $($sigFiles.Count) signature file(s)"
    } elseif ($env:TAURI_SIGNING_PRIVATE_KEY) {
        Write-Host "     WARN: TAURI_SIGNING_PRIVATE_KEY is set but no .sig files found" -ForegroundColor Yellow
        Write-Host "     The build may not have produced updater artifacts"
    } else {
        Write-Host "     No .sig files found (local/dev build - TAURI_SIGNING_PRIVATE_KEY not set)"
        Write-Host "     For signed release builds, set TAURI_SIGNING_PRIVATE_KEY env var"
        Write-Host ""
        Write-Host "     Generate a key: cargo tauri signer generate -w ~/.normnomos/keys/enterprise.key"
    }
}

# ---- Main ----
$targetTriple = Detect-Target

$mode = if ($args.Count -gt 0) { $args[0] } else { "all" }

Write-Host "Target: $targetTriple"
Write-Host "Mode:  $mode"
Write-Host ""

try {
    switch ($mode) {
        "sidecar" {
            Build-Sidecar
        }
        "tauri" {
            # Inject version before any build (restored by finally below)
            Inject-Version (Resolve-Version)
            # Tauri-only: warn if the sidecar-embedded frontend is missing (the
            # sidecar bundles whatever sits in agent\dawei\frontend\).
            $frontendIdx = Join-Path $RepoRoot "engine\agent\dawei\frontend\index.html"
            if (-not (Test-Path $frontendIdx)) {
                Write-Host "WARN: agent\dawei\frontend\index.html missing — sidecar will embed a stale/absent web UI." -ForegroundColor Yellow
                Write-Host "      Run 'powershell -File scripts/build-desktop.ps1 all' for a full build (frontend + sidecar + tauri)."
            }
            Copy-Sidecar $targetTriple
            Build-Tauri
            Verify-Signing $targetTriple
        }
        "all" {
            # Inject version before any build (restored by finally below)
            Inject-Version (Resolve-Version)
            # Frontend FIRST: PyInstaller --collect-all dawei bundles whatever sits
            # in agent\dawei\frontend\, so it must be fresh before the sidecar build.
            Build-Frontend
            Build-Sidecar
            Copy-Sidecar $targetTriple
            Build-Tauri
            Verify-Signing $targetTriple
        }
        default {
            Write-Host "Usage: powershell -File $PSCommandPath {sidecar|tauri|all}"
            exit 1
        }
    }
} finally {
    # Restore the original tauri.conf.json / Cargo.toml (no-op when nothing was
    # injected, e.g. sidecar-only mode) so the working tree stays clean.
    Restore-VersionFiles
}
