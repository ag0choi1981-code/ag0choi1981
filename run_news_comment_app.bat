@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/3] Checking Python...
python --version >nul 2>nul
if errorlevel 1 (
  echo Python is not installed or not in PATH.
  echo Install from https://www.python.org/downloads/
  echo and enable "Add python.exe to PATH".
  pause
  exit /b 1
)

echo [2/3] Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency install failed.
  pause
  exit /b 1
)

echo [3/3] Starting News Comment Analyzer...
python -m streamlit run news_comment_app.py

pause
