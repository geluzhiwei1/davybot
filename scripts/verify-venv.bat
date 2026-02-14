@echo off
REM Verify virtual environment integrity (Windows)
REM Usage: scripts\verify-venv.bat

setlocal enabledelayedexpansion

REM Path configuration
set "BACKEND_DIR=%~dp0..\services\agent-api"
set "BACKEND_VENV=%BACKEND_DIR%\.venv"
set "TAURI_RESOURCES=%~dp0..\apps\web\src-tauri\resources\python-env"

echo ========================================
echo   Verify Virtual Environment
echo ========================================
echo.

REM Verify backend venv
echo [1/3] Verifying backend venv...
if not exist "%BACKEND_VENV%" (
    echo [ERROR] Backend venv does not exist
    echo   Expected location: %BACKEND_VENV%
    echo.
    echo Please run: scripts\build-standalone.bat
    exit /b 1
)
echo [OK] Backend venv exists

REM Check Python executable
if not exist "%BACKEND_VENV%\Scripts\python.exe" (
    echo [ERROR] Python executable not found
    exit /b 1
)
echo [OK] Python executable exists

REM Check if UV-created venv
set "USE_UV=0"
if exist "%BACKEND_VENV%\pyvenv.cfg" (
    findstr /C:"uv =" "%BACKEND_VENV%\pyvenv.cfg" >nul 2>&1
    if not errorlevel 1 (
        set "USE_UV=1"
        echo [OK] UV-created venv detected
    )
)

REM Verify dawei package
echo.
echo [2/3] Verifying dawei package...
"%BACKEND_VENV%\Scripts\python.exe" -c "import dawei; print(f'dawei version: {dawei.__version__}')" 2>nul
if errorlevel 1 (
    echo [ERROR] dawei package not installed or cannot be imported
    exit /b 1
)

REM Check key dependencies
echo.
echo Verifying key dependencies...
set "MISSING_DEPS="

REM Use venv Python directly for imports
for %%p in (fastapi uvicorn pydantic litellm textual) do (
    "%BACKEND_VENV%\Scripts\python.exe" -c "import %%p" 2>nul
    if errorlevel 1 (
        echo   [ERROR] %%p - missing
        set "MISSING_DEPS=1"
    ) else (
        echo   [OK] %%p
    )
)

if defined MISSING_DEPS (
    echo.
    echo [ERROR] Some dependencies are missing
    exit /b 1
)

REM Count packages using UV if available
if "%USE_UV%"=="1" (
    for /f %%i in ('uv pip list ^| find /c /v ""') do set package_count=%%i
    set /a package_count-=2
) else (
    for /f %%i in ('"%BACKEND_VENV%\Scripts\python.exe" -m pip list ^| find /c /v ""') do set package_count=%%i
    set /a package_count-=2
)
echo.
echo [OK] %package_count% packages installed

REM Verify Tauri resources
echo.
echo [3/3] Verifying Tauri resources...
if not exist "%TAURI_RESOURCES%" (
    echo [WARN] Tauri resources directory does not exist
    echo   Expected location: %TAURI_RESOURCES%
    echo.
    echo Please run: scripts\build-standalone.bat
    exit /b 1
)
echo [OK] Tauri resources directory exists

REM Check Tauri Python
if not exist "%TAURI_RESOURCES%\Scripts\python.exe" (
    echo [ERROR] Tauri Python executable not found
    exit /b 1
)
echo [OK] Tauri Python executable exists

REM Calculate directory sizes
for /f "tokens=3" %%s in ('dir /s "%BACKEND_VENV%" ^| find "个文件" ^| findstr /r "[0-9]*"') do (
    set BACKEND_SIZE=%%s
)
for /f "tokens=3" %%s in ('dir /s "%TAURI_RESOURCES%" ^| find "个文件" ^| findstr /r "[0-9]*"') do (
    set TAURI_SIZE=%%s
)

echo.
echo ========================================
echo   [SUCCESS] Verification Passed!
echo ========================================
echo.
echo Environment Info:
echo   Backend venv: %BACKEND_SIZE% bytes
echo   Tauri resources: %TAURI_SIZE% bytes
echo   Packages installed: %package_count%
echo   UV-based: %USE_UV%
echo.

endlocal
