@echo off
REM 复制 Python 虚拟环境到 Tauri 资源目录 (Windows)
REM 用法: scripts\copy-python-env.bat

setlocal enabledelayedexpansion

REM 路径配置
set "BACKEND_VENV=%~dp0..\services\agent-api\.venv"
set "TAURI_RESOURCES=%~dp0..\apps\web\src-tauri\resources\python-env"

echo =========================================
echo 复制 Python 虚拟环境到 Tauri
echo =========================================
echo.

REM 检查源虚拟环境
if not exist "%BACKEND_VENV%" (
    echo ❌ 错误: 虚拟环境不存在
    echo    期望位置: %BACKEND_VENV%
    echo.
    echo 请先运行: scripts\prepare-python-env.bat
    exit /b 1
)

echo ✓ 源虚拟环境: %BACKEND_VENV%
echo.

REM 创建目标目录
echo 创建目标目录: %TAURI_RESOURCES%
if not exist "%TAURI_RESOURCES%\.." (
    mkdir "%TAURI_RESOURCES%\.."
)

REM 清理旧文件
if exist "%TAURI_RESOURCES%" (
    echo 清理旧文件...
    rmdir /s /q "%TAURI_RESOURCES%" 2>nul
)

REM 复制虚拟环境
echo 复制虚拟环境（这可能需要几分钟）...
xcopy "%BACKEND_VENV%" "%TAURI_RESOURCES%" /E /I /H /Y >nul
if errorlevel 1 (
    echo ❌ 复制失败
    exit /b 1
)

REM 优化虚拟环境大小
echo 优化虚拟环境...
cd /d "%TAURI_RESOURCES%"

REM 删除 Python 缓存
echo   - 删除 __pycache__ ...
for /d /r . %%d in (__pycache__) do @if exist "%%d" (
    rmdir /s /q "%%d" 2>nul
)

REM 删除 .pyc 文件
echo   - 删除 .pyc 文件...
del /s /q *.pyc 2>nul

REM 删除 .egg-info 目录
echo   - 删除 .egg-info 目录...
for /d /r . %%d in (*.egg-info) do @if exist "%%d" (
    rmdir /s /q "%%d" 2>nul
)

REM 删除测试目录
echo   - 删除 tests 目录...
for /d /r . %%d in (tests) do @if exist "%%d" (
    rmdir /s /q "%%d" 2>nul
)
for /d /r . %%d in (test) do @if exist "%%d" (
    rmdir /s /q "%%d" 2>nul
)

cd /d "%~dp0.."

echo.
echo =========================================
echo ✅ 虚拟环境复制完成！
echo =========================================
echo 位置: %TAURI_RESOURCES%
echo.
echo 下一步:
echo   1. 更新 tauri.conf.json 包含 resources/python-env/*
echo   2. 运行 pnpm tauri build
echo.

endlocal
