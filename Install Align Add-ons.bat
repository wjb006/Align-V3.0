@echo off
setlocal
cd /d "%~dp0"
title Align V3.0 - Optional Setup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Align-AddOns.ps1"
set "EXITCODE=%ERRORLEVEL%"
echo.
if not "%EXITCODE%"=="0" echo Align optional setup did not complete. Review the message above and retry.
pause
exit /b %EXITCODE%
