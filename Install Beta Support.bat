@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Align - Install Beta Support
echo ==============================================
echo          ALIGN - INSTALL BETA SUPPORT
echo ==============================================
echo.
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 python -m venv .venv
  if errorlevel 1 goto FAILED
)
".venv\Scripts\python.exe" -m pip install -r requirements-beta.txt
if errorlevel 1 goto FAILED
where cloudflared.exe >nul 2>&1
if %errorlevel%==0 goto DONE
where winget.exe >nul 2>&1
if not %errorlevel%==0 (
  echo cloudflared is not installed and winget was not found.
  echo Install it from https://developers.cloudflare.com/tunnel/downloads/
  goto FAILED
)
echo Installing Cloudflare Tunnel...
winget install --id Cloudflare.cloudflared --exact --accept-source-agreements --accept-package-agreements
if errorlevel 1 goto FAILED
:DONE
echo.
echo Beta Support is ready.
echo Next run "Set Up Beta Owner.bat", then "Start Align Public Beta.bat".
pause
exit /b 0
:FAILED
echo.
echo Beta Support installation did not complete. Check the message above and retry.
pause
exit /b 1
