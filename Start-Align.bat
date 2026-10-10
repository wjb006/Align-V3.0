@echo off
setlocal
title Align V2.0 - Build 156
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
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
echo ALIGN V2.0 - BUILD 156
echo Starting Align...
start "" "http://127.0.0.1:8001/"
"%PYTHON%" "%ROOT%launch.py"
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" pause
exit /b %EXITCODE%
