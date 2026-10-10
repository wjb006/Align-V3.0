@echo off
setlocal
cd /d "%~dp0"
title Align v1.3 Beta - Public Beta
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start Align Public Beta.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo Align Public Beta stopped with code %RC%.
pause
exit /b %RC%
