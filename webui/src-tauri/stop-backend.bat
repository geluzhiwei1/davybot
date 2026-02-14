@echo off
REM Backend stop script for Tauri desktop application (Windows)

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "LOG_FILE=%SCRIPT_DIR%backend.log"

echo [Dawei Backend] Stopping server...

REM Kill all Python processes running dawei.server
for /f "tokens=2" %%a in ('tasklist ^| findstr /i "python.exe"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [Dawei Backend] Server stopped
endlocal
