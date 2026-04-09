@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "dist\NewsCommentAnalyzer.exe" (
  echo Executable not found. Building first...
  python -m PyInstaller --noconfirm --onefile --windowed --name NewsCommentAnalyzer news_comment_desktop.py
  if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
  )
)

set "TARGET=%~dp0dist\NewsCommentAnalyzer.exe"
set "SHORTCUT=%USERPROFILE%\Desktop\News Comment Analyzer.lnk"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$W=New-Object -ComObject WScript.Shell; $S=$W.CreateShortcut('%SHORTCUT%'); $S.TargetPath='%TARGET%'; $S.WorkingDirectory='%~dp0dist'; $S.IconLocation='%TARGET%'; $S.Description='News Comment Analyzer'; $S.Save()"

if errorlevel 1 (
  echo Shortcut creation failed. You can still run:
  echo %TARGET%
  pause
  exit /b 1
)

echo Installed successfully.
echo Desktop shortcut created: %SHORTCUT%
pause
