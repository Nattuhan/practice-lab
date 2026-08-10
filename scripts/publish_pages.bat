@echo off
setlocal
cd /d "%~dp0.."

set EXPORT_ARG=
set ORIGIN_URL=
if /I "%~1"=="--metadata-only" set EXPORT_ARG=--metadata-only

for /f "usebackq delims=" %%i in (`git remote get-url origin`) do set ORIGIN_URL=%%i
if not defined ORIGIN_URL goto :fail

python scripts\export_static.py %EXPORT_ARG%
if errorlevel 1 goto :fail

if exist .publish-temp rmdir /s /q .publish-temp
mkdir .publish-temp
if errorlevel 1 goto :fail

xcopy public .publish-temp\ /e /i /y >nul
if errorlevel 1 goto :fail

pushd .publish-temp
git init >nul
if errorlevel 1 goto :fail_pop

git checkout -b gh-pages >nul
if errorlevel 1 goto :fail_pop

git add .
if errorlevel 1 goto :fail_pop

git -c user.name="publish-bot" -c user.email="publish-bot@local" commit -m "Publish GitHub Pages" >nul
if errorlevel 1 goto :fail_pop

git remote add origin "%ORIGIN_URL%"
if errorlevel 1 goto :fail_pop

git push origin gh-pages:gh-pages --force
if errorlevel 1 goto :fail_pop

popd
rmdir /s /q .publish-temp
echo Published current public/ contents to gh-pages.
exit /b 0

:fail_pop
popd

:fail
if exist .publish-temp rmdir /s /q .publish-temp
echo Publish failed.
exit /b 1
