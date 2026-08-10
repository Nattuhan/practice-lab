@echo off
cd /d "%~dp0.."

set EXPORT_ARG=
if /I "%~1"=="--metadata-only" set EXPORT_ARG=--metadata-only

python scripts\export_static.py %EXPORT_ARG%
exit /b %errorlevel%
