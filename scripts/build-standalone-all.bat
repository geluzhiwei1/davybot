@echo off
REM Complete standalone build script
REM Creates both NSIS installer and portable ZIP package

setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0.."
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "WEB_DIR=%PROJECT_ROOT%\webui"
set "TAURI_DIR=%WEB_DIR%\src-tauri"
set "TARGET_DIR=%TAURI_DIR%\target\release"
set "SCRIPT_DIR=%PROJECT_ROOT%\scripts"

echo ========================================
echo   Dawei Standalone Build Script
echo   ================================
echo   Creates both installer and ZIP
echo ========================================
echo.

REM Build NSIS installer
echo [1/2] Building NSIS installer...
call "%SCRIPT_DIR%\bundle-standalone-win.bat"
if %errorlevel% neq 0 (
    echo ⚠ Warning: NSIS installer build failed
    echo   Continuing with ZIP package...
)
echo.

REM Build ZIP package
echo [2/2] Building portable ZIP package...
call "%SCRIPT_DIR%\build-standalone-zip.bat"
if %errorlevel% neq 0 (
    echo ❌ ZIP package build failed
    exit /b 1
)
echo.

echo ========================================
echo   All Builds Completed!
echo ========================================
echo.

echo 📦 Build Artifacts:
echo.
echo   NSIS Installer: %TARGET_DIR%\dawei-standalone-setup.exe
echo   ZIP Package:   %TARGET_DIR%\dawei-standalone-win-portable-v*.zip
echo.
echo   Users can choose:
echo     - Installer:   Traditional setup wizard with shortcuts
echo     - ZIP:         Portable version, extract and run
echo.

endlocal
