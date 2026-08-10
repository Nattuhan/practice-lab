@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
set EXIT_CODE=%errorlevel%
echo.
echo Exit code: %EXIT_CODE%
pause
