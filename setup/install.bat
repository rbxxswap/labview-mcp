@echo off
REM LabVIEW MCP Server — Windows Setup Script
REM Run this once after installing the labview-mcp plugin.
REM This installs the required Python packages.

echo ================================================
echo  LabVIEW MCP Plugin — Dependency Installer
echo ================================================
echo.

REM Check Python is available
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python not found in PATH.
    echo Please install Python 3.10+ from https://python.org and add it to PATH.
    pause
    exit /b 1
)

echo Python found:
python --version
echo.

REM Core install (required for all backends)
echo Installing core dependencies...
pip install "mcp[cli]>=1.3.0" "pydantic>=2.0.0" "nptdms>=1.5.0" --break-system-packages
if %ERRORLEVEL% NEQ 0 goto :error

REM COM backend (Windows, recommended)
echo.
echo Installing COM backend (pywin32)...
pip install "pywin32>=306" --break-system-packages
if %ERRORLEVEL% NEQ 0 goto :error
python -m pywin32_postinstall -install

REM HTTP backend (optional)
echo.
echo Installing HTTP backend (httpx)...
pip install "httpx>=0.27.0" --break-system-packages
if %ERRORLEVEL% NEQ 0 goto :error

echo.
echo ================================================
echo  Installation complete!
echo.
echo  Restart Claude Desktop to activate the plugin.
echo ================================================
pause
exit /b 0

:error
echo.
echo ERROR: Installation failed. See messages above.
pause
exit /b 1
