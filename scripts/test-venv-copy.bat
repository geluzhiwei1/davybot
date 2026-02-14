@echo off
REM Test venv copy to Tauri resources
setlocal enabledelayedexpansion

echo ========================================
echo   Test Venv Copy to Tauri
echo ========================================
echo.

set "PROJECT_ROOT=%~dp0.."
set "BACKEND_DIR=%PROJECT_ROOT%\services\agent-api"
set "BACKEND_VENV=%BACKEND_DIR%\.venv"
set "TAURI_RESOURCES=%PROJECT_ROOT%\apps\web\src-tauri\resources\python-env"
set "REQUIREMENTS_FILE=%BACKEND_DIR%\requirements-freeze.txt"

echo Backend venv: %BACKEND_VENV%
echo Tauri resources: %TAURI_RESOURCES%
echo.

REM Check backend venv
if not exist "%BACKEND_VENV%" (
    echo [ERROR] Backend venv not found
    exit /b 1
)
echo [OK] Backend venv exists

REM Check Python executable
if not exist "%BACKEND_VENV%\Scripts\python.exe" (
    echo [ERROR] Python executable not found
    exit /b 1
)
echo [OK] Python executable exists

REM Test dawei import
"%BACKEND_VENV%\Scripts\python.exe" -c "import dawei; print(f'dawei version: {dawei.__version__}')" 2>nul
if errorlevel 1 (
    echo [ERROR] dawei import failed
    exit /b 1
)
echo [OK] dawei import successful

REM Export requirements with UV
echo.
echo Exporting requirements with UV...
cd /d "%BACKEND_DIR%"
uv pip freeze > "%REQUIREMENTS_FILE%"
if errorlevel 1 (
    echo [ERROR] Failed to export requirements
    exit /b 1
)
echo [OK] Requirements exported to %REQUIREMENTS_FILE%

REM Show file size
for %%f in ("%REQUIREMENTS_FILE%") do (
    echo [INFO] File size: %%~zf bytes
)

REM Create target directory
echo.
echo Creating target directory...
if not exist "%TAURI_RESOURCES%\.." (
    mkdir "%TAURI_RESOURCES%\.."
)

REM Clean old files
if exist "%TAURI_RESOURCES%" (
    echo Cleaning old files...
    rmdir /s /q "%TAURI_RESOURCES%" 2>nul
)

REM Copy venv
echo.
echo Copying venv to Tauri resources...
echo This may take a few minutes...
xcopy "%BACKEND_VENV%" "%TAURI_RESOURCES%" /E /I /H /Y
if errorlevel 1 (
    echo [ERROR] Failed to copy venv
    exit /b 1
)
echo [OK] Venv copied successfully

REM Verify copy
echo.
echo Verifying copy...
if not exist "%TAURI_RESOURCES%\Scripts\python.exe" (
    echo [ERROR] Tauri Python not found
    exit /b 1
)
echo [OK] Tauri Python exists

REM Test import in copied venv
"%TAURI_RESOURCES%\Scripts\python.exe" -c "import dawei; print(f'dawei version: {dawei.__version__}')" 2>nul
if errorlevel 1 (
    echo [WARN] dawei import may have issues in copied venv
) else (
    echo [OK] dawei import works in copied venv
)

REM Calculate sizes
for /f "tokens=3" %%s in ('dir /s "%BACKEND_VENV%" ^| find "个文件" ^| findstr /r "[0-9]*"') do (
    set SRC_SIZE=%%s
)
for /f "tokens=3" %%s in ('dir /s "%TAURI_RESOURCES%" ^| find "个文件" ^| findstr /r "[0-9]*"') do (
    set DST_SIZE=%%s
)

echo.
echo ========================================
echo   Test Complete!
echo ========================================
echo.
echo Source size: !SRC_SIZE! bytes
echo Destination size: !DST_SIZE! bytes
echo Tauri resources: %TAURI_RESOURCES%
echo.

endlocal
