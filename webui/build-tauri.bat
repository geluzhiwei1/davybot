@echo off
REM Build script for Tauri desktop application (Windows)

setlocal enabledelayedexpansion

echo =========================================
echo Building Dawei Tauri Desktop App
echo =========================================

REM Navigate to frontend directory
cd /d "%~dp0"

REM Check if Rust is installed
where cargo >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: Rust is not installed!
    echo Please install Rust from https://rustup.rs/
    exit /b 1
)

REM Check if Node.js is installed
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: Node.js is not installed!
    echo Please install Node.js from https://nodejs.org/
    exit /b 1
)

REM Install dependencies
echo Installing dependencies...
call pnpm install

REM Build backend for bundling
echo.
echo Building backend...
cd ..\..\services\agent-api

REM Check if UV is available
where uv >nul 2>nul
if %errorlevel% equ 0 (
    echo Using UV to package backend...
    if not exist ".venv" (
        uv venv .venv
    )
    uv pip install -e .
) else (
    echo Using venv to package backend...
    if not exist ".venv" (
        python -m venv .venv
    )
    call .venv\Scripts\activate.bat
    call pip install -e .
)

cd ..\..\apps\web

REM Build frontend
echo.
echo Building frontend...
call pnpm build

REM Build Tauri app
echo.
echo Building Tauri application...
call pnpm tauri build

echo.
echo =========================================
echo Build completed successfully!
echo =========================================
echo.
echo Desktop application bundles:
dir /b src-tauri\target\release\bundle\
echo.
echo To install and run:
echo   - Windows: Run the .exe installer in src-tauri\target\release\bundle\
echo.

endlocal
