@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_windows.ps1"
set "exit_code=%errorlevel%"
echo.
if not "%exit_code%"=="0" echo セットアップに失敗しました。上のメッセージを確認してください。
pause
exit /b %exit_code%
