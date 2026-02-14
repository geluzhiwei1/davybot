@echo off
REM 准备 Python 虚拟环境脚本 (Windows)
REM 用法: scripts\prepare-python-env.bat

setlocal enabledelayedexpansion

echo =========================================
echo 准备 Python 虚拟环境
echo =========================================
echo.

REM 进入后端目录
cd /d "%~dp0..\services\agent-api"

REM 检测 Python
set "PYTHON_CMD="
set "PYTHON_VERSION="

REM 优先使用 UV 的 Python 3.12
where uv >nul 2>&1
if %errorlevel% equ 0 (
    echo 检测到 UV，尝试使用 Python 3.12...
    for /f "tokens=*" %%i in ('uv python list 2^>nul ^| findstr "3.12"') do (
        set "PYTHON_CMD=uv run --python 3.12 python"
        set "PYTHON_VERSION=3.12.12 (via UV)"
        echo ✓ 检测到 Python 版本: !PYTHON_VERSION!
        goto :python_found
    )
)

REM 回退到系统 Python
where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PYTHON_VERSION=%%i"
    echo ✓ 检测到 Python 版本: !PYTHON_VERSION!

    REM 检查版本（简单检查）
    echo !PYTHON_VERSION! | findstr /r "3\.1[2-9]" >nul
    if errorlevel 1 (
        echo ❌ 错误: Python 版本过低 (需要 ^>= 3.12)
        echo 当前版本: !PYTHON_VERSION!
        echo.
        echo 建议: 安装 UV 并使用 Python 3.12
        echo   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
        exit /b 1
    )
    goto :python_found
)

REM 未找到 Python
echo ❌ 错误: 未找到 python
echo 请安装 Python 3.12 或更高版本
exit /b 1

:python_found
REM 创建虚拟环境（如果不存在）
if not exist ".venv" (
    echo 创建虚拟环境...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo ❌ 虚拟环境创建失败
        exit /b 1
    )
    echo ✓ 虚拟环境创建成功
) else (
    echo ✓ 虚拟环境已存在
)

REM 激活虚拟环境
echo 激活虚拟环境...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo ❌ 虚拟环境激活失败
    exit /b 1
)

REM 升级 pip
echo 升级 pip...
python -m pip install --upgrade pip setuptools wheel >nul 2>&1

REM 安装 dawei 包
echo 安装 dawei 包...
if exist "pyproject.toml" (
    pip install -e . >nul 2>&1
    if errorlevel 1 (
        echo ❌ dawei 包安装失败
        exit /b 1
    )
) else (
    echo ❌ 错误: 未找到 pyproject.toml
    exit /b 1
)

REM 验证安装
echo.
echo 验证安装...
python -c "import dawei; print(f'✓ dawei 版本: {dawei.__version__}')" 2>nul
if errorlevel 1 (
    echo ❌ 错误: dawei 包安装失败
    exit /b 1
)

REM 计算已安装的包数量
for /f %%i in ('pip list ^| find /c /v ""') do set package_count=%%i
set /a package_count-=2
echo ✓ 已安装 %package_count% 个包

echo.
echo =========================================
echo ✅ 虚拟环境准备完成！
echo =========================================
echo 📍 位置: %cd%\.venv
echo.
echo 要使用虚拟环境，请运行:
echo   .venv\Scripts\activate.bat
echo.

endlocal
