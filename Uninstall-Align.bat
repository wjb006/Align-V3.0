@echo off
setlocal
title Align v1.3 Beta Build 156 - Uninstaller

echo ============================================================
echo   ALIGN v1.3 BETA - BUILD 156 UNINSTALLER
echo ============================================================
echo.
echo This removes the local Align virtual environment and
echo installer/launcher files.
echo.
echo IMPORTANT: align.sqlite3 is NOT deleted by default.
echo.
choice /C YN /N /M "Continue with uninstall? [Y/N]: "
if errorlevel 2 exit /b 0
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Uninstall-Align.ps1"
set "EXITCODE=%ERRORLEVEL%"
echo.
if "%EXITCODE%"=="0" (
  echo ============================================================
  echo   ALIGN UNINSTALL COMPLETE
  echo ============================================================
  echo.
  echo Your align.sqlite3 database was preserved unless you
  echo explicitly selected database deletion.
) else (
  echo ============================================================
  echo   ALIGN UNINSTALL FAILED
  echo ============================================================
  echo.
  echo Check the error above and the latest uninstall log in:
  echo %~dp0install-logs\
)
echo.
pause
exit /b %EXITCODE%
