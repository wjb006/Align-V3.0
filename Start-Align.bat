@echo off
setlocal
cd /d "%~dp0"
title Align V3.0
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not defined ALIGN_PORT set "ALIGN_PORT=8001"
if not exist "%PYTHON%" (
  echo ERROR: Align virtual environment not found.
  echo Run Install-Align.bat first.
  pause
  exit /b 1
)
if not exist "%ROOT%app.py" (
  echo ERROR: app.py was not found.
  pause
  exit /b 1
)
echo ALIGN V3.0
echo Starting Align...
if /I "%~1"=="--network" goto run
start "" "http://127.0.0.1:%ALIGN_PORT%/"
:run
"%PYTHON%" "%ROOT%launch.py" %*
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" pause
exit /b %EXITCODE%
