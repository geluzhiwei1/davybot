@echo off
REM Full build test without Tauri
setlocal enabledelayedexpansion

echo ========================================
echo   Full Build Test (No Tauri)
echo ========================================
echo.

set "PROJECT_ROOT=%~dp0.."
set "BACKEND_DIR=%PROJECT_ROOT%\services\agent-api"
set "BACKEND_VENV=%BACKEND_DIR%\.venv"
set "TAURI_RESOURCES=%PROJECT_ROOT%\apps\web\src-tauri\resources\python-env"
set "REQUIREMENTS_FILE=%BACKEND_DIR%\requirements-freeze.txt"

REM 1. Check Python
echo [1/6] Checking Python...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PYTHON_VERSION=%%i"
echo [OK] Python: %PYTHON_VERSION%

REM 2. Check venv
echo.
echo [2/6] Checking venv...
if not exist "%BACKEND_VENV%" (
    echo [ERROR] venv not found
    exit /b 1
)
echo [OK] venv exists

REM 3. Test dawei
echo.
echo [3/6] Testing dawei...
"%BACKEND_VENV%\Scripts\python.exe" -c "import dawei; print(f'dawei version: {dawei.__version__}')" 2>nul
if errorlevel 1 (
    echo [ERROR] dawei import failed
    exit /b 1
)
echo [OK] dawei works

REM 4. Export requirements
echo.
echo [4/6] Exporting requirements...
cd /d "%BACKEND_DIR%"
uv pip freeze > "%REQUIREMENTS_FILE%"
if errorlevel 1 (
    echo [ERROR] Failed to export
    exit /b 1
)
for %%f in ("%REQUIREMENTS_FILE%") do set SIZE=%%~zf
echo [OK] Exported %SIZE% bytes

REM 5. Copy venv
echo.
echo [5/6] Copying venv to Tauri...
if exist "%TAURI_RESOURCES%" (
    rmdir /s /q "%TAURI_RESOURCES%" 2>nul
)
xcopy "%BACKEND_VENV%" "%TAURI_RESOURCES%" /E /I /H /Y >nul
if errorlevel 1 (
    echo [ERROR] Copy failed
    exit /b 1
)
echo [OK] Venv copied

REM 6. Test copied venv
echo.
echo [6/6] Testing copied venv...
"%TAURI_RESOURCES%\Scripts\python.exe" -c "import dawei; print(f'dawei version: {dawei.__version__}')" 2>nul
if errorlevel 1 (
    echo [ERROR] Copy verification failed
    exit /b 1
)
echo [OK] Copied venv works

REM Calculate sizes
for /f "tokens=3" %%s in ('dir /s "%BACKEND_VENV%" ^| find "个文件" ^| findstr /r "[0-9]*"') do set SRC=%%s
for /f "tokens=3" %%s in ('dir /s "%TAURI_RESOURCES%" ^| find "个文件" ^| findstr /r "[0-9]*"') do set DST=%%s

echo.
echo ========================================
echo   [OK] All Tests Passed!
echo ========================================
echo.
echo Source:      %SRC% bytes
echo Destination: %DST% bytes
echo Requirements: %REQUIREMENTS_FILE%
echo Tauri resources: %TAURI_RESOURCES%
echo.

endlocal
