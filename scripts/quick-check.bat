@echo off
REM Quick check script for build prerequisites
setlocal enabledelayedexpansion

echo ========================================
echo   Quick Build Prerequisites Check
echo ========================================
echo.

set "ERRORS=0"

REM Check Python
echo [1] Checking Python...
where python >nul 2>&1
if !errorlevel! neq 0 (
    echo   [ERROR] Python not found
    set /a ERRORS+=1
) else (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do echo   [OK] Python %%i
)

REM Check UV
echo.
echo [2] Checking UV...
where uv >nul 2>&1
if !errorlevel! neq 0 (
    echo   [WARN] UV not found (optional)
) else (
    for /f "tokens=2" %%i in ('uv --version 2^>^&1') do echo   [OK] UV %%i
)

REM Check Node.js
echo.
echo [3] Checking Node.js...
where node >nul 2>&1
if !errorlevel! neq 0 (
    echo   [ERROR] Node.js not found
    set /a ERRORS+=1
) else (
    for /f "tokens=2" %%i in ('node --version 2^>^&1') do echo   [OK] Node.js %%i
)

REM Check pnpm
echo.
echo [4] Checking pnpm...
where pnpm >nul 2>&1
if !errorlevel! neq 0 (
    echo   [ERROR] pnpm not found
    set /a ERRORS+=1
) else (
    for /f "tokens=2" %%i in ('pnpm --version 2^>^&1') do echo   [OK] pnpm %%i
)

REM Check Rust
echo.
echo [5] Checking Rust...
where cargo >nul 2>&1
if !errorlevel! neq 0 (
    echo   [ERROR] Rust/Cargo not found
    set /a ERRORS+=1
) else (
    for /f "tokens=2" %%i in ('cargo --version 2^>^&1') do echo   [OK] %%i
)

REM Check backend venv
echo.
echo [6] Checking backend venv...
set "BACKEND_VENV=%~dp0..\agent\.venv"
if not exist "%BACKEND_VENV%" (
    echo   [ERROR] Backend venv not found
    set /a ERRORS+=1
) else (
    echo   [OK] Backend venv exists
)

REM Check dawei import
echo.
echo [7] Checking dawei...
"%BACKEND_VENV%\Scripts\python.exe" -c "import dawei" 2>nul
if !errorlevel! neq 0 (
    echo   [ERROR] dawei import failed
    set /a ERRORS+=1
) else (
    "%BACKEND_VENV%\Scripts\python.exe" -c "print(f'   [OK] dawei {dawei.__version__}')" 2>nul
)

REM Check frontend dist
echo.
echo [8] Checking frontend build...
if not exist "%~dp0..\webui\dist\index.html" (
    echo   [WARN] Frontend not built yet
    echo   Run: cd webui ^&^& pnpm build-only
) else (
    echo   [OK] Frontend built
)

REM Check Tauri config
echo.
echo [9] Checking Tauri config...
if not exist "%~dp0..\webui\src-tauri\tauri.conf.standalone.json" (
    echo   [ERROR] Tauri standalone config not found
    set /a ERRORS+=1
) else (
    echo   [OK] Tauri config exists
)

REM Summary
echo.
echo ========================================
if !ERRORS! equ 0 (
    echo   [OK] All Critical Checks Passed
    echo.
    echo Ready to build!
    echo Run: scripts\build-standalone.bat
) else (
    echo   [ERROR] !ERRORS! Error(s) Found
    echo.
    echo Please fix the errors above before building
)
echo ========================================
echo.

endlocal
