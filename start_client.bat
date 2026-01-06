@echo off
REM Start Cloud Security Client
REM This script starts the interactive client

echo.
echo ============================================
echo    Cloud Security Client Startup
echo ============================================
echo.

cd /d C:\Users\HP VICTUS\Documents\cloudTemplateProject\auth

if not exist "..\venv_fixed\Scripts\python.exe" (
    echo ERROR: Virtual environment not found!
    echo Please run setup first.
    pause
    exit /b 1
)

echo Starting interactive client...
echo Make sure the server is running on localhost:51234
echo.

"..\venv_fixed\Scripts\python.exe" client.py

pause
