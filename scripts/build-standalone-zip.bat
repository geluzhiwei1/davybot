@echo off
REM Windows standalone ZIP packager script
REM This script creates a portable ZIP package that users can extract and run

setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0.."
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "WEB_DIR=%PROJECT_ROOT%\webui"
set "TAURI_DIR=%WEB_DIR%\src-tauri"
set "TARGET_DIR=%TAURI_DIR%\target\release"

echo ========================================
echo   Tauri Windows Standalone ZIP Packager
echo ========================================
echo.

REM Get version from Cargo.toml
for /f "tokens=2 delims==" %%a in ('findstr "name" "%TAURI_DIR%\Cargo.toml"') do set "APP_NAME=%%a"
set "APP_NAME=%APP_NAME: " =%"
set "APP_NAME=%APP_NAME:" =%"

for /f "tokens=2 delims==" %%a in ('findstr "version" "%TAURI_DIR%\Cargo.toml"') do set "APP_VERSION=%%a"
set "APP_VERSION=%APP_VERSION: " =%"
set "APP_VERSION=%APP_VERSION:" =%"

echo App: %APP_NAME% v%APP_VERSION%
echo.

REM 1. Build Tauri application (release mode)
echo [1/5] Building Tauri application...
cd /d "%WEB_DIR%"

echo Building frontend...
call pnpm build-only
if %errorlevel% neq 0 (
    echo ❌ Frontend build failed
    exit /b 1
)

echo Building Tauri app...
call pnpm tauri build --config "%TAURI_DIR%\tauri.conf.standalone.json" --no-bundle
if %errorlevel% neq 0 (
    echo ❌ Tauri build failed
    exit /b 1
)

echo ✓ Tauri build completed
echo.

REM 2. Prepare portable package directory
echo [2/5] Preparing portable package...
set "ZIP_DIR=%TARGET_DIR%\%APP_NAME%-standalone-win-portable-v%APP_VERSION%"
set "ZIP_NAME=%APP_NAME%-standalone-win-portable-v%APP_VERSION%.zip"

if exist "%ZIP_DIR%" (
    echo Cleaning old package...
    rmdir /s /q "%ZIP_DIR%"
)

mkdir "%ZIP_DIR%"
mkdir "%ZIP_DIR%\resources"

REM 3. Copy application files
echo [3/5] Copying application files...

REM Main executable
echo Copying main executable...
copy "%TARGET_DIR%\%APP_NAME%.exe" "%ZIP_DIR%\\" >nul

REM Resources
echo Copying Python environment...
if exist "%TAURI_DIR%\resources\python-env" (
    xcopy "%TAURI_DIR%\resources\python-env" "%ZIP_DIR%\resources\python-env\" /E /I /H /Y >nul
    echo ✓ Python environment copied
) else (
    echo ⚠ Warning: Python environment not found at "%TAURI_DIR%\resources\python-env"
    echo   Please run scripts/copy-resources.py first
)

echo Copying backend scripts...
copy "%TAURI_DIR%\start-backend.bat" "%ZIP_DIR%\resources\" >nul 2>&1
copy "%TAURI_DIR%\stop-backend.bat" "%ZIP_DIR%\resources\" >nul 2>&1
copy "%TAURI_DIR%\start-backend.sh" "%ZIP_DIR%\resources\" >nul 2>&1
copy "%TAURI_DIR%\stop-backend.sh" "%ZIP_DIR%\resources\" >nul 2>&1

echo Copying icons...
if exist "%TAURI_DIR%\icons" (
    xcopy "%TAURI_DIR%\icons" "%ZIP_DIR%\icons\" /E /I /Y >nul
)

echo ✓ Application files copied
echo.

REM 4. Create README
echo [4/5] Creating README...
set "README_FILE=%ZIP_DIR%\README.txt"

(
echo # 大微 AI 助手 - Standalone 便携版
echo.
echo 版本: %APP_VERSION%
echo.
echo ## 使用方法
echo.
echo 1. 解压缩此 ZIP 文件到任意目录
echo 2. 双击 %APP_NAME%.exe 启动应用
echo.
echo 应用会在首次启动时自动启动后端服务。
echo.
echo ## 目录结构
echo.
echo - %APP_NAME%.exe              : 主应用程序
echo - resources\                  : 资源文件目录
echo   - python-env\               : Python 运行时环境 ^(Windows venv^)
echo     - Scripts\python.exe      : Python 解释器
echo     - Scripts\pip.exe         : Python 包管理器
echo     - Lib\                    : Python 标准库
echo     - Lib\site-packages\      : 第三方库 ^(FastAPI, uvicorn 等^)
echo   - start-backend.bat         : Windows 后端启动脚本
echo   - stop-backend.bat          : Windows 后端停止脚本
echo   - start-backend.sh          : Linux/Mac 后端启动脚本
echo   - stop-backend.sh           : Linux/Mac 后端停止脚本
echo - icons\                      : 应用图标
echo.
echo ## 系统要求
echo.
echo - Windows 10 或更高版本 ^(64位^)
echo - 约 500 MB 可用磁盘空间
echo.
echo ## 注意事项
echo.
echo - 首次运行可能需要几秒钟来初始化
echo - 请勿移动或删除 resources 目录
echo - 如遇问题，请查看应用日志
echo - Windows 版本使用 Scripts\python.exe，Linux/Mac 使用 bin/python
echo.
echo ## 技术支持
echo.
echo 项目主页: https://github.com/dawei/patent-agent
echo.
echo Copyright © 2026 大微团队. All rights reserved.
) > "%README_FILE%"

echo ✓ README created
echo.

REM 5. Create ZIP package
echo [5/5] Creating ZIP package...

REM Use PowerShell to create ZIP (Windows 10+ built-in)
powershell -Command "Compress-Archive -Path '%ZIP_DIR%' -DestinationPath '%TARGET_DIR%\%ZIP_NAME%' -Force"

if %errorlevel% neq 0 (
    echo ❌ Failed to create ZIP package
    echo.
    echo Alternative: You can manually compress the folder:
    echo   %ZIP_DIR%
    exit /b 1
)

echo ✓ ZIP package created
echo.

REM 6. Show results
echo ========================================
echo   Build Completed!
echo ========================================
echo.

for %%F in ("%TARGET_DIR%\%ZIP_NAME%") do (
    set SIZE=%%~zF
    set /a SIZE_MB=!SIZE! / 1048576
    echo ✅ Portable ZIP Package:
    echo    Name:     %%~nxF
    echo    Location: %%~dpnxF
    echo    Size:     !SIZE_MB! MB
    echo.
)

echo 📦 Package Contents:
echo    - %APP_NAME%.exe ^(Main application^)
echo    - resources/python-env/ ^(Python runtime + dependencies^)
echo    - resources/start-backend.bat  ^(Backend startup script^)
echo    - resources/stop-backend.bat   ^(Backend shutdown script^)
echo    - README.txt ^(Usage instructions^)
echo.

echo 📋 Distribution Instructions:
echo.
echo   1. Upload the ZIP file to your distribution platform
echo   2. Users can:
echo      - Download the ZIP file
echo      - Extract it to any folder
echo      - Run %APP_NAME%.exe directly
echo      - No installation required!
echo.

echo ========================================
echo.

endlocal
