@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [0/4] Closing old server on port 5050 if exists...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5050 ^| findstr LISTENING') do (
  taskkill /PID %%a /F >nul 2>nul
)

echo [1/4] Checking Python...
python --version >nul 2>nul
if errorlevel 1 (
  echo Python is not installed or not in PATH.
  echo Install from https://www.python.org/downloads/
  echo and enable "Add python.exe to PATH".
  pause
  exit /b 1
)

echo [2/4] Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency install failed.
  pause
  exit /b 1
)

echo [3/4] Launching app...
start "" http://127.0.0.1:5050

echo [4/4] Starting web server at http://127.0.0.1:5050 ...
python moel_web_app.py

pause
