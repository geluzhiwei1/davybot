@echo off
REM Windows standalone bundler script
REM This script bundles Python environment into the Tauri Windows installer

setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0.."
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "WEB_DIR=%PROJECT_ROOT%\apps\web"
set "TAURI_DIR=%WEB_DIR%\src-tauri"
set "TARGET_DIR=%TAURI_DIR%\target\release"
set "NSIS_DIR=%TARGET_DIR%\nsis\x64"

echo ========================================
echo   Tauri Windows Standalone Bundler
echo ========================================
echo.

REM 1. Check if NSIS exists
where makensis >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Error: makensis not found
    echo Please install NSIS from: https://nsis.sourceforge.io/
    exit /b 1
)

REM 2. Build Tauri application
echo [1/4] Building Tauri application...
cd /d "%WEB_DIR%"
call pnpm build-only
if %errorlevel% neq 0 (
    echo ❌ Frontend build failed
    exit /b 1
)

call pnpm tauri build --config "%TAURI_DIR%\tauri.conf.standalone.json" --no-bundle
if %errorlevel% neq 0 (
    echo ❌ Tauri build failed
    exit /b 1
)

echo ✓ Tauri build completed
echo.

REM 3. Prepare resource directory
echo [2/4] Preparing resource directory...
set "PACKAGE_DIR=%TARGET_DIR%\dawei-standalone-win"

if exist "%PACKAGE_DIR%" (
    echo Cleaning old package...
    rmdir /s /q "%PACKAGE_DIR%"
)

mkdir "%PACKAGE_DIR%"
mkdir "%PACKAGE_DIR%\resources"

REM Copy main executable
echo Copying main executable...
copy "%TARGET_DIR%\davybot.exe" "%PACKAGE_DIR%\"

REM Copy resources
echo Copying Python environment...
xcopy "%TAURI_DIR%\resources\python-env" "%PACKAGE_DIR%\resources\python-env\" /E /I /H /Y >nul

echo Copying backend scripts...
copy "%TAURI_DIR%\start-backend.bat" "%PACKAGE_DIR%\resources\"
copy "%TAURI_DIR%\stop-backend.bat" "%PACKAGE_DIR%\resources\"
copy "%TAURI_DIR%\start-backend.sh" "%PACKAGE_DIR%\resources\"
copy "%TAURI_DIR%\stop-backend.sh" "%PACKAGE_DIR%\resources\"

echo ✓ Resources prepared
echo.

REM 4. Create NSIS installer
echo [3/4] Creating NSIS installer...

REM Create NSIS script
set "NSI_SCRIPT=%TARGET_DIR%\standalone-installer.nsi"

(
echo !include "MUI2.nsh"
echo.
echo ; Installer configuration
echo Name "大微 AI 助手 ^(Standalone^)"
echo OutFile "%TARGET_DIR%\dawei-standalone-setup.exe"
echo InstallDir "$PROGRAMFILES64\大微 AI 助手"
echo InstallDirRegKey HKCU "Software\大微 AI 助手" ""
echo RequestExecutionLevel admin
echo.
echo ; Set maximum compression
echo SetCompressor /SOLID lzma
echo SetCompressorDictSize 64
echo.
echo ; Interface settings
echo !define MUI_ABORTWARNING
echo !define MUI_ICON "%TAURI_DIR%\icons\icon.ico"
echo !define MUI_UNICON "%TAURI_DIR%\icons\icon.ico"
echo.
echo ; Pages
echo !insertmacro MUI_PAGE_WELCOME
echo !insertmacro MUI_PAGE_LICENSE "%PROJECT_ROOT%\LICENSE"
echo !insertmacro MUI_PAGE_DIRECTORY
echo !insertmacro MUI_PAGE_INSTFILES
echo !insertmacro MUI_PAGE_FINISH
echo.
echo !insertmacro MUI_UNPAGE_WELCOME
echo !insertmacro MUI_UNPAGE_CONFIRM
echo !insertmacro MUI_UNPAGE_INSTFILES
echo !insertmacro MUI_UNPAGE_FINISH
echo.
echo ; Languages
echo !insertmacro MUI_LANGUAGE "SimpChinese"
echo !insertmacro MUI_LANGUAGE "English"
echo.
echo ; Installer sections
echo Section "Main" SecMain
echo   SetOutPath "$INSTDIR"
echo   File /r "%PACKAGE_DIR%\*"
echo.
echo   ; Create uninstaller
echo   WriteUninstaller "$INSTDIR\uninstall.exe"
echo.
echo   ; Create shortcuts
echo   CreateDirectory "$SMPROGRAMS\大微 AI 助手"
echo   CreateShortcut "$SMPROGRAMS\大微 AI 助手\大微 AI 助手.lnk" "$INSTDIR\davybot.exe"
echo   CreateShortcut "$SMPROGRAMS\大微 AI 助手\卸载.lnk" "$INSTDIR\uninstall.exe"
echo   CreateShortCut "$DESKTOP\大微 AI 助手.lnk" "$INSTDIR\davybot.exe"
echo.
echo   ; Write registry keys
echo   WriteRegStr HKCU "Software\大微 AI 助手" "" "$INSTDIR"
echo   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\大微 AI 助手" "DisplayName" "大微 AI 助手"
echo   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\大微 AI 助手" "UninstallString" "$INSTDIR\uninstall.exe"
echo   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\大微 AI 助手" "Publisher" "大微团队"
echo   WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\大微 AI 助手" "DisplayVersion" "0.1.0"
echo   WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\大微 AI 助手" "NoModify" 1
echo   WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\大微 AI 助手" "NoRepair" 1
echo SectionEnd
echo.
echo ; Uninstaller section
echo Section "Uninstall"
echo   ; Delete shortcuts
echo   Delete "$SMPROGRAMS\大微 AI 助手\大微 AI 助手.lnk"
echo   Delete "$SMPROGRAMS\大微 AI 助手\卸载.lnk"
echo   Delete "$DESKTOP\大微 AI 助手.lnk"
echo   RMDir "$SMPROGRAMS\大微 AI 助手"
echo.
echo   ; Delete files
echo   RMDir /r "$INSTDIR"
echo.
echo   ; Remove registry keys
echo   DeleteRegKey HKCU "Software\大微 AI 助手"
echo   DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\大微 AI 助手"
echo SectionEnd
) > "%NSI_SCRIPT%"

echo Building installer with NSIS...
makensis "%NSI_SCRIPT%"

if %errorlevel% neq 0 (
    echo ❌ NSIS build failed
    exit /b 1
)

echo ✓ NSIS installer created
echo.

REM 5. Show results
echo [4/4] Build completed!
echo.
echo ========================================
echo   Build Artifacts
echo ========================================
echo.

if exist "%TARGET_DIR%\dawei-standalone-setup.exe" (
    for %%F in ("%TARGET_DIR%\dawei-standalone-setup.exe") do (
        set SIZE=%%~zF
        set /a SIZE_MB=!SIZE! / 1048576
        echo ✅ NSIS Installer:
        echo    Location: %%~dpnxF
        echo    Size:     !SIZE_MB! MB
        echo.
    )
)

echo 📦 Package Contents:
echo    - davybot.exe ^(Main application^)
echo    - python-env/ ^(Python 3.14 runtime + dependencies^)
echo    - Backend scripts ^(start/stop for Windows/Linux^)
echo.

echo Installation Instructions:
echo   1. Double-click dawei-standalone-setup.exe
echo   2. Follow the installation wizard
echo   3. Launch from Start Menu or Desktop
echo.

endlocal
