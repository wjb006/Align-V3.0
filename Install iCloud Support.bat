@echo off
setlocal
cd /d "%~dp0"
title Install Align iCloud support
echo This installs optional iCloud libraries into Align's own .venv folder.
echo It does not connect to your Apple Account.
if exist ".venv\Scripts\python.exe" goto install
py -3 -m venv .venv
if errorlevel 1 python -m venv .venv
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install -r requirements-icloud.txt
if errorlevel 1 goto failed
echo Installed. Restart Align using its usual Start Align launcher.
pause
exit /b 0
:failed
echo Installation failed. Check Python and your internet connection, then retry.
pause
exit /b 1
