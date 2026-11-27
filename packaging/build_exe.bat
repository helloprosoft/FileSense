@echo off
setlocal
cd /d "%~dp0\.."

where py >nul 2>nul
if errorlevel 1 (
    echo Python Launcher was not found. Install Python 3.10 or newer to build FileSense.
    exit /b 1
)

py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo Python 3.10 or newer is required to build FileSense.
    exit /b 1
)

if not exist ".venv-build\Scripts\python.exe" (
    py -3 -m venv .venv-build
    if errorlevel 1 exit /b 1
)

set "BUILD_PY=.venv-build\Scripts\python.exe"
"%BUILD_PY%" -m pip install --disable-pip-version-check -r requirements.txt -r packaging\requirements-build.txt
if errorlevel 1 exit /b 1

where upx >nul 2>nul
if errorlevel 1 echo UPX not found; the build will use PyInstaller's standard compression.

"%BUILD_PY%" -m PyInstaller --noconfirm --clean packaging\FileSense.spec
if errorlevel 1 exit /b 1

echo.
echo FileSense 2.0.0 build complete:
echo %CD%\dist\FileSense\FileSense.exe
endlocal
