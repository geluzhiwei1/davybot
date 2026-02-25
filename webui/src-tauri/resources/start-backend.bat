@echo off
REM Backend startup script for Tauri desktop application (Windows)

setlocal enabledelayedexpansion

REM Get script directory
set "SCRIPT_DIR=%~dp0"

REM Check for bundled Python environment first (production)
if exist "%SCRIPT_DIR%resources\python-env\Scripts\python.exe" (
    set "PYTHON=%SCRIPT_DIR%resources\python-env\Scripts\python.exe"
    set "WORK_DIR=%SCRIPT_DIR%resources\python-env"
    echo [Dawei Backend] Using bundled Python environment
REM Fall back to development mode
) else if exist "%SCRIPT_DIR%..\..\services\agent-api\.venv\Scripts\python.exe" (
    set "BACKEND_DIR=%SCRIPT_DIR%..\..\services\agent-api"
    set "PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"
    set "WORK_DIR=%BACKEND_DIR%"
    echo [Dawei Backend] Development mode detected
REM Last resort: system Python
) else (
    set "PYTHON=python"
    set "WORK_DIR=%SCRIPT_DIR%"
    echo [Dawei Backend] Using system Python (not recommended)
)

REM Start backend server
echo [Dawei Backend] Starting server...
echo [Dawei Backend] Python: %PYTHON%
echo [Dawei Backend] Working directory: %WORK_DIR%
echo [Dawei Backend] Log file: %SCRIPT_DIR%backend.log

cd /d "%WORK_DIR%"

start /B "" "%PYTHON%" -m dawei.server --host 127.0.0.1 --port 8465 > "%SCRIPT_DIR%backend.log" 2>&1

REM Save PID (Windows doesn't have a simple way, so we skip it)
echo [Dawei Backend] Server started
echo [Dawei Backend] Waiting for server to be ready...

REM Wait for server to be ready (max 30 seconds)
set /a COUNT=0
:waitloop
if !COUNT! GEQ 30 (
    echo [Dawei Backend] WARNING: Server may not be ready. Check log file: %SCRIPT_DIR%backend.log
    exit /b 0
)

curl -s http://127.0.0.1:8465/health >nul 2>&1
if !errorlevel! EQU 0 (
    echo [Dawei Backend] Server is ready!
    exit /b 0
)

timeout /t 1 /nobreak >nul
set /a COUNT+=1
goto waitloop
