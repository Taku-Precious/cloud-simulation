@echo off
REM Start Cloud Security Server
REM This script starts the cloud.py server using the fixed virtual environment

echo.
echo ============================================
echo    Cloud Security Server Startup
echo ============================================
echo.

cd /d C:\Users\HP VICTUS\Documents\cloudTemplateProject\auth

if not exist "..\venv_fixed\Scripts\python.exe" (
    echo ERROR: Virtual environment not found!
    echo Please run setup first.
    pause
    exit /b 1
)

echo Starting server on localhost:51234...
echo.
echo Press Ctrl+C to stop the server.
echo.

"..\venv_fixed\Scripts\python.exe" cloud.py

pause
