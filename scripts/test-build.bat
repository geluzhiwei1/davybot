@echo off
REM Test build script components
setlocal enabledelayedexpansion

echo ========================================
echo   Testing Build Script Components
echo ========================================
echo.

REM Test 1: Python Detection
echo [Test 1] Python Detection...
set "PYTHON_CMD="
set "PYTHON_VERSION="

where uv >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] UV found
    for /f "tokens=*" %%i in ('uv python list 2^>nul ^| findstr "3.12"') do (
        set "PYTHON_CMD=uv run --python 3.12 python"
        set "PYTHON_VERSION=3.12"
        echo [OK] Using Python: !PYTHON_VERSION! (via UV)
        goto :python_found
    )
)

where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PYTHON_VERSION=%%i"
    echo [OK] Using Python: !PYTHON_VERSION!
    goto :python_found
)

echo [ERROR] Python not found
exit /b 1

:python_found
echo.
echo [Test 2] Virtual Environment Creation...
cd /d "%~dp0..\services\agent-api"

if not exist ".venv" (
    echo Creating .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv
        exit /b 1
    )
    echo [OK] venv created
) else (
    echo [OK] venv exists
)

echo.
echo [Test 3] Virtual Environment Activation...
call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Failed to activate venv
    exit /b 1
)
echo [OK] venv activated

echo.
echo [Test 4] Python in venv...
python --version
if errorlevel 1 (
    echo [ERROR] Python not working in venv
    exit /b 1
)
echo [OK] Python working in venv

echo.
echo [Test 5] Installing dawei package...
if exist "pyproject.toml" (
    pip install -e . -i https://mirrors.aliyun.com/pypi/simple/
    if errorlevel 1 (
        echo [ERROR] Failed to install dawei
        exit /b 1
    )
    echo [OK] dawei installed
) else (
    echo [ERROR] pyproject.toml not found
    exit /b 1
)

echo.
echo [Test 6] Verify dawei import...
python -c "import dawei; print(f'dawei version: {dawei.__version__}')"
if errorlevel 1 (
    echo [ERROR] dawei import failed
    exit /b 1
)
echo [OK] dawei import successful

echo.
echo ========================================
echo   [SUCCESS] All Tests Passed!
echo ========================================
echo.
echo Python: !PYTHON_VERSION!
echo Venv: %cd%\.venv
echo.

endlocal
