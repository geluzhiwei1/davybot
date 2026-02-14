@echo off
REM Build standalone desktop application with full Python venv (Windows)
REM Usage: scripts\build-standalone.bat

setlocal enabledelayedexpansion

REM Project paths
set "PROJECT_ROOT=%~dp0.."
set "BACKEND_DIR=%PROJECT_ROOT%\services\agent-api"
set "BACKEND_VENV=%BACKEND_DIR%\.venv"
set "TAURI_RESOURCES=%PROJECT_ROOT%\apps\web\src-tauri\resources\python-env"
set "REQUIREMENTS_FILE=%BACKEND_DIR%\requirements-freeze.txt"

echo ========================================
echo   Build Standalone Desktop App (venv)
echo ========================================
echo.
echo Project: %PROJECT_ROOT%
echo Backend: %BACKEND_DIR%
echo.

REM 1. Detect Python
echo [1/7] Detecting Python...
set "PYTHON_CMD="
set "PYTHON_VERSION="

REM Try UV Python 3.12
where uv >nul 2>&1
if !errorlevel! equ 0 (
    echo Found UV, checking Python 3.12...
    for /f "tokens=*" %%i in ('uv python list 2^>nul ^| findstr "3.12"') do (
        set "PYTHON_CMD=uv run --python 3.12 python"
        set "PYTHON_VERSION=3.12"
        echo Using Python: !PYTHON_VERSION! (via UV)
        goto :python_found
    )
)

REM Fallback to system Python
where python >nul 2>&1
if !errorlevel! equ 0 (
    set "PYTHON_CMD=python"
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PYTHON_VERSION=%%i"
    echo Using Python: !PYTHON_VERSION!
    goto :python_found
)

echo ERROR: Python not found
exit /b 1

:python_found
REM 2. Check venv
echo.
echo [2/7] Checking virtual environment...
cd /d "%BACKEND_DIR%"

if not exist "%BACKEND_VENV%" (
    echo Creating new virtual environment...
    %PYTHON_CMD% -m venv .venv
    if !errorlevel! neq 0 (
        echo ERROR: Failed to create venv
        exit /b 1
    )
    echo Virtual environment created
) else (
    echo Virtual environment exists
)

REM 3. Check if UV-created venv
echo.
echo [3/7] Detecting venv type...
set "USE_UV=0"
if exist "%BACKEND_VENV%\pyvenv.cfg" (
    findstr /C:"uv =" "%BACKEND_VENV%\pyvenv.cfg" >nul 2>&1
    if !errorlevel! equ 0 (
        set "USE_UV=1"
        echo UV-created venv detected
    ) else (
        echo Standard venv detected
    )
) else (
    echo Standard venv detected
)

REM 4. Install dependencies
echo.
echo [4/7] Installing dependencies...

if "!USE_UV!"=="1" (
    echo Using UV pip...
    if exist "pyproject.toml" (
        cd /d "%BACKEND_DIR%"
        uv pip install -e .
        if !errorlevel! neq 0 (
            echo ERROR: Failed to install dawei
            exit /b 1
        )
        echo dawei package installed
    ) else (
        echo ERROR: pyproject.toml not found
        exit /b 1
    )

    REM Export requirements
    echo Exporting requirements...
    uv pip freeze > "%REQUIREMENTS_FILE%"
    if !errorlevel! neq 0 (
        echo WARNING: Failed to export requirements
    ) else (
        echo Requirements saved
    )
) else (
    REM Standard venv
    call "%BACKEND_VENV%\Scripts\activate.bat"
    if !errorlevel! neq 0 (
        echo ERROR: Failed to activate venv
        exit /b 1
    )

    echo Upgrading pip...
    python -m pip install --upgrade pip setuptools wheel -i https://mirrors.aliyun.com/pypi/simple/ >nul 2>&1

    echo Installing dawei package...
    if exist "pyproject.toml" (
        pip install -e . -i https://mirrors.aliyun.com/pypi/simple/
        if !errorlevel! neq 0 (
            echo ERROR: Failed to install dawei
            exit /b 1
        )
        echo dawei package installed
    ) else (
        echo ERROR: pyproject.toml not found
        exit /b 1
    )

    REM Export requirements
    echo Exporting requirements...
    pip freeze > "%REQUIREMENTS_FILE%"
    if !errorlevel! neq 0 (
        echo WARNING: Failed to export requirements
    ) else (
        echo Requirements saved
    )
)

REM 5. Verify installation
echo.
echo [5/7] Verifying installation...
"%BACKEND_VENV%\Scripts\python.exe" -c "import dawei; print(f'dawei version: {dawei.__version__}')" 2>nul
if !errorlevel! neq 0 (
    echo WARNING: dawei import may have issues
) else (
    echo dawei import successful
)

REM 6. Copy venv to Tauri
echo.
echo [6/7] Copying venv to Tauri resources...

REM Create target directory
if not exist "%TAURI_RESOURCES%\.." (
    mkdir "%TAURI_RESOURCES%\.."
)

REM Clean old files
if exist "%TAURI_RESOURCES%" (
    echo Cleaning old files...
    rmdir /s /q "%TAURI_RESOURCES%" 2>nul
)

REM Copy venv
echo Copying virtual environment...
xcopy "%BACKEND_VENV%" "%TAURI_RESOURCES%" /E /I /H /Y >nul
if !errorlevel! neq 0 (
    echo ERROR: Failed to copy venv
    exit /b 1
)
echo Venv copied successfully

REM Optimize venv
echo Optimizing venv size...
cd /d "%TAURI_RESOURCES%"

for /d /r . %%d in (__pycache__) do @if exist "%%d" (
    rmdir /s /q "%%d" 2>nul
)

del /s /q *.pyc 2>nul
del /s /q *.pyo 2>nul

for /d /r . %%d in (*.egg-info) do @if exist "%%d" (
    rmdir /s /q "%%d" 2>nul
)

for /d /r . %%d in (*.dist-info) do @if exist "%%d\tests" (
    rmdir /s /q "%%d\tests" 2>nul
)

for /d /r . %%d in (tests) do @if exist "%%d" (
    rmdir /s /q "%%d" 2>nul
)
for /d /r . %%d in (test) do @if exist "%%d" (
    rmdir /s /q "%%d" 2>nul
)

cd /d "%PROJECT_ROOT%"

echo Venv optimized

REM 7. Build frontend and Tauri
echo.
echo [7/7] Building frontend and Tauri application...
cd /d "%PROJECT_ROOT%\apps\web"

echo Building frontend resources...
call pnpm build-only
if !errorlevel! neq 0 (
    echo ERROR: Frontend build failed
    exit /b 1
)
echo Frontend built successfully

echo.
echo Building Tauri desktop application...
echo This may take 5-10 minutes...
pnpm tauri build --config src-tauri\tauri.conf.standalone.json
if !errorlevel! neq 0 (
    echo ERROR: Tauri build failed
    exit /b 1
)
echo Tauri built successfully

REM Build complete
echo.
echo ========================================
echo   Build Complete!
echo ========================================
echo.

REM Find build artifacts
set "BUNDLE_DIR=%PROJECT_ROOT%\apps\web\src-tauri\target\release\bundle"
set "EXE_PATH=%PROJECT_ROOT%\apps\web\src-tauri\target\release\dawei-standalone.exe"

if exist "%BUNDLE_DIR%" (
    echo Build artifacts:
    echo.

    if exist "%BUNDLE_DIR%\msi\*.msi" (
        echo Windows MSI Installer:
        dir /b "%BUNDLE_DIR%\msi\*.msi" 2>nul
        echo.
    )

    if exist "%BUNDLE_DIR%\nsis\*.exe" (
        echo NSIS Installer:
        dir /b "%BUNDLE_DIR%\nsis\*.exe" 2>nul
        echo.
    )
)

if exist "%EXE_PATH%" (
    echo Standalone Executable:
    echo   dawei-standalone.exe
    for %%f in ("%EXE_PATH%") do (
        echo   Size: %%~zf bytes
    )
    echo.
)

echo Application Features:
echo   - Full Python runtime (venv)
echo   - All Python dependencies
echo   - Frontend app (Vue 3 + TypeScript)
echo   - Fully standalone
echo   - No external dependencies
echo.

echo ========================================
echo   SUCCESS
echo ========================================
echo.

endlocal
