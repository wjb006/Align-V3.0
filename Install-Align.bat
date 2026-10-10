@echo off
setlocal
title Align v1.3 Beta Build 156 - Installer

echo ============================================================
echo   ALIGN v1.3 BETA - BUILD 156 INSTALLER
echo ============================================================
echo.
echo This installs and verifies Align in the folder containing this file.
echo.
pause

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Align.ps1"
set "EXITCODE=%ERRORLEVEL%"
echo.
if "%EXITCODE%"=="0" (
  echo ============================================================
  echo   ALIGN INSTALLATION COMPLETE
  echo ============================================================
  echo.
  echo Run Start-Align.bat to start Align.
) else (
  echo ============================================================
  echo   ALIGN INSTALLATION FAILED
  echo ============================================================
  echo.
  echo Read the error above and the latest log in:
  echo %~dp0install-logs\
)
echo.
pause
exit /b %EXITCODE%
